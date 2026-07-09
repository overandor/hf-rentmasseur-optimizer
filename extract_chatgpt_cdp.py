#!/usr/bin/env python3
"""
Extract all ChatGPT chats from Microsoft Edge using Playwright.
Approach: Launch a fresh Edge with remote debugging, using a copied profile
that includes cookies. If the copied profile doesn't have the session,
the user can log in manually in the opened window.
"""

import json
import os
import time
import re
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright

EDGE_PATH = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
EDGE_PROFILE_ORIG = os.path.expanduser("~/Library/Application Support/Microsoft Edge")
EDGE_PROFILE_COPY = os.path.expanduser("~/tmp/edge_profile_copy")
OUTPUT_DIR = Path(__file__).parent / "chatgpt_exports"
CHATGPT_URL = "https://chatgpt.com"


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[^\w\s\-]', '', name).strip()
    name = re.sub(r'[\s]+', '_', name)
    if not name:
        name = "untitled"
    return name[:100]


def copy_profile():
    """Copy the Edge profile to a temp dir so we don't lock the original."""
    src = EDGE_PROFILE_ORIG
    dst = EDGE_PROFILE_COPY

    print(f"  Copying Edge profile to {dst}...")
    if os.path.exists(dst):
        shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    os.makedirs(dst, exist_ok=True)

    # Copy top-level files
    for item in os.listdir(src):
        src_path = os.path.join(src, item)
        dst_path = os.path.join(dst, item)
        if os.path.isfile(src_path) and item in ('Local State', 'First Run'):
            try:
                shutil.copy2(src_path, dst_path)
            except Exception:
                pass

    # Copy Default profile
    default_src = os.path.join(src, 'Default')
    default_dst = os.path.join(dst, 'Default')
    os.makedirs(default_dst, exist_ok=True)

    # Copy everything in Default except large/unnecessary dirs
    skip_dirs = {'Cache', 'Code Cache', 'GPUCache', 'Service Worker', 'Storage', 'databases'}
    skip_prefixes = ('ShaderCache', 'GrShaderCache')

    for item in os.listdir(default_src):
        src_path = os.path.join(default_src, item)
        dst_path = os.path.join(default_dst, item)

        if os.path.isdir(src_path):
            if item in skip_dirs or any(item.startswith(p) for p in skip_prefixes):
                continue
            try:
                shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
            except Exception as e:
                pass
        else:
            try:
                shutil.copy2(src_path, dst_path)
            except Exception as e:
                pass

    print("  Profile copy complete.")


def extract_chats_from_page(page):
    """Extract chat links from the ChatGPT sidebar."""
    chats = []
    seen_ids = set()

    selectors = [
        'nav ol li a',
        'nav[aria-label="Chat history"] a',
        'a[href*="/c/"]',
        'a[href*="/g/"]',
        '[data-testid="history-item"] a',
        'nav a[href]',
    ]

    for selector in selectors:
        try:
            links = page.query_selector_all(selector)
            if not links:
                continue
            for link in links:
                try:
                    href = link.get_attribute('href') or ''
                    text = link.inner_text().strip()
                    if not href:
                        continue
                    if '/c/' in href or '/g/' in href:
                        chat_id = href.split('/')[-1].split('?')[0]
                        if chat_id in seen_ids:
                            continue
                        seen_ids.add(chat_id)
                        full_url = href if href.startswith('http') else f"https://chatgpt.com{href}"
                        chats.append({
                            'title': text or f"chat_{chat_id[:8]}",
                            'url': full_url,
                            'chat_id': chat_id,
                        })
                except Exception:
                    continue
            if chats:
                break
        except Exception:
            continue

    return chats


def scroll_sidebar(page, max_scrolls=50):
    """Scroll the sidebar to load all chats."""
    for i in range(max_scrolls):
        try:
            scroll_selectors = [
                'nav [class*="scroll"]',
                'nav ol',
                'nav div[style*="overflow"]',
                'nav',
            ]
            scrolled = False
            for sel in scroll_selectors:
                try:
                    el = page.query_selector(sel)
                    if el:
                        el.evaluate('el => el.scrollBy(0, 1000)')
                        scrolled = True
                        break
                except Exception:
                    continue
            if not scrolled:
                page.evaluate('window.scrollBy(0, 1000)')
            time.sleep(0.3)
        except Exception:
            break


def extract_conversation(page):
    """Extract the full conversation from the current ChatGPT chat page."""
    messages = []

    # Strategy 1: article elements
    try:
        articles = page.query_selector_all('article')
        for article in articles:
            try:
                text = article.inner_text().strip()
                if text and len(text) > 2:
                    aria_label = article.get_attribute('aria-label') or ''
                    data_role = article.get_attribute('data-role') or ''
                    role = 'unknown'
                    if 'user' in aria_label.lower() or 'user' in data_role.lower():
                        role = 'user'
                    elif 'assistant' in aria_label.lower() or 'assistant' in data_role.lower():
                        role = 'assistant'
                    if role == 'unknown':
                        user_els = article.query_selector_all('[class*="user"], [data-testid*="user"]')
                        asst_els = article.query_selector_all('[class*="assistant"], [data-testid*="assistant"]')
                        if user_els:
                            role = 'user'
                        elif asst_els:
                            role = 'assistant'
                    messages.append({'role': role, 'content': text})
            except Exception:
                continue
    except Exception:
        pass

    # Strategy 2: data-testid message containers
    if not messages:
        try:
            msg_els = page.query_selector_all('[data-testid*="conversation"], [class*="message"], [class*="markdown"]')
            for el in msg_els:
                try:
                    text = el.inner_text().strip()
                    if text and len(text) > 2:
                        messages.append({'role': 'unknown', 'content': text})
                except Exception:
                    continue
        except Exception:
            pass

    # Strategy 3: grab main content
    if not messages:
        try:
            main = page.query_selector('main') or page.query_selector('#main')
            if main:
                full_text = main.inner_text()
                messages.append({'role': 'raw', 'content': full_text})
        except Exception:
            pass

    return messages


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("ChatGPT Chat Extractor for Microsoft Edge")
    print("=" * 60)

    # No copy needed — Edge is closed, use original profile directly
    print("  Using original Edge profile (Edge is closed)")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=EDGE_PROFILE_ORIG,
            executable_path=EDGE_PATH,
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-extensions',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-site-isolation-trials',
                '--disable-web-security',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
            ],
            viewport={'width': 1280, 'height': 900},
            timeout=120000,
        )

        page = context.pages[0] if context.pages else context.new_page()

        # Stealth: patch navigator.webdriver
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            window.chrome = { runtime: {} };
        """)

        print(f"\n[1/4] Navigating to {CHATGPT_URL}...")
        try:
            page.goto(CHATGPT_URL, wait_until='domcontentloaded', timeout=60000)
        except Exception as e:
            print(f"  Navigation warning: {e}")
            page.goto(CHATGPT_URL, timeout=60000)

        # Wait for Cloudflare challenge to resolve
        print("  Waiting for Cloudflare challenge to clear...")
        for attempt in range(30):
            time.sleep(2)
            current = page.url
            if '__cf_chl' not in current and 'challenge' not in current:
                break
            print(f"  Still on challenge... ({attempt+1}/30)")
        time.sleep(5)

        current_url = page.url
        print(f"  Current URL: {current_url}")

        # Check if logged in
        if 'auth0' in current_url or 'login' in current_url or 'auth' in current_url:
            print("\n  ⚠ Not logged in. Cookies may not be valid in headless mode.")
            print("  Saving debug info and exiting...")
            page.screenshot(path=str(OUTPUT_DIR / "debug_login.png"))
            (OUTPUT_DIR / "debug_login.html").write_text(page.content())
            context.close()
            return

        # Wait for sidebar
        print("\n[2/4] Waiting for sidebar to load...")
        time.sleep(5)

        # Scroll sidebar
        print("  Scrolling sidebar to load all chats...")
        scroll_sidebar(page, max_scrolls=50)
        time.sleep(2)

        # Extract chat list
        print("\n[3/4] Extracting chat list from sidebar...")
        chats = extract_chats_from_page(page)

        if not chats:
            print("  No chats found via selectors. Trying alternative approach...")
            try:
                more_buttons = page.query_selector_all('button[aria-label*="more"], button[aria-label*="Show"], button[aria-label*="expand"]')
                for btn in more_buttons[:5]:
                    try:
                        btn.click()
                        time.sleep(1)
                    except Exception:
                        continue
                chats = extract_chats_from_page(page)
            except Exception:
                pass

        print(f"  Found {len(chats)} chats.")

        if not chats:
            print("\n  No chats could be extracted. Saving debug info...")
            page.screenshot(path=str(OUTPUT_DIR / "debug_screenshot.png"))
            html = page.content()
            (OUTPUT_DIR / "debug_page.html").write_text(html)
            print(f"  Debug files saved to {OUTPUT_DIR}/")
            context.close()
            return

        # Save chat index
        index_path = OUTPUT_DIR / "chat_index.json"
        index_path.write_text(json.dumps(chats, indent=2, ensure_ascii=False))
        print(f"  Chat index saved to {index_path}")

        # Extract each conversation
        print(f"\n[4/4] Extracting {len(chats)} conversations...")
        all_conversations = []

        for i, chat in enumerate(chats):
            print(f"  [{i+1}/{len(chats)}] {chat['title'][:50]}...", end=" ", flush=True)
            try:
                page.goto(chat['url'], wait_until='domcontentloaded', timeout=30000)
                time.sleep(4)

                messages = extract_conversation(page)
                conversation = {
                    'title': chat['title'],
                    'url': chat['url'],
                    'chat_id': chat['chat_id'],
                    'messages': messages,
                    'message_count': len(messages),
                }
                all_conversations.append(conversation)

                # Save individual markdown
                safe_name = sanitize_filename(chat['title'])
                md_path = OUTPUT_DIR / f"{i+1:04d}_{safe_name}.md"
                md_lines = [f"# {chat['title']}\n", f"URL: {chat['url']}\n", f"Chat ID: {chat['chat_id']}\n", f"Messages: {len(messages)}\n", "---\n"]
                for msg in messages:
                    role = msg['role'].upper()
                    md_lines.append(f"\n## [{role}]\n")
                    md_lines.append(msg['content'])
                    md_lines.append("")
                md_path.write_text("\n".join(md_lines))

                print(f"({len(messages)} messages)")
            except Exception as e:
                print(f"ERROR: {e}")
                all_conversations.append({
                    'title': chat['title'],
                    'url': chat['url'],
                    'chat_id': chat['chat_id'],
                    'messages': [],
                    'message_count': 0,
                    'error': str(e),
                })

        # Save all as JSON
        all_json_path = OUTPUT_DIR / "all_chats.json"
        all_json_path.write_text(json.dumps(all_conversations, indent=2, ensure_ascii=False))

        print(f"\n{'=' * 60}")
        print(f"Extraction complete!")
        print(f"  Total chats: {len(all_conversations)}")
        print(f"  Total messages: {sum(c.get('message_count', 0) for c in all_conversations)}")
        print(f"  Output directory: {OUTPUT_DIR}")
        print(f"  All chats JSON: {all_json_path}")
        print(f"  Individual markdown files: {OUTPUT_DIR}/*.md")
        print(f"{'=' * 60}")

        print("\nClosing browser...")
        context.close()


if __name__ == "__main__":
    main()
