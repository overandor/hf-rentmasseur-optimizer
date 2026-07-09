#!/usr/bin/env python3
"""
Extract all ChatGPT chats from Microsoft Edge using Playwright.
Uses the existing Edge profile so you're already logged in.
Saves chats as JSON + Markdown.
"""

import json
import os
import time
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

EDGE_PATH = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
EDGE_PROFILE_ORIG = os.path.expanduser("~/Library/Application Support/Microsoft Edge")
EDGE_PROFILE_COPY = os.path.expanduser("~/tmp/edge_profile_copy")
OUTPUT_DIR = Path(__file__).parent / "chatgpt_exports"
CHATGPT_URL = "https://chatgpt.com"

def sanitize_filename(name: str) -> str:
    """Make a string safe for use as a filename."""
    name = re.sub(r'[^\w\s\-]', '', name).strip()
    name = re.sub(r'[\s]+', '_', name)
    if not name:
        name = "untitled"
    return name[:100]


def extract_chats_from_page(page):
    """
    Extract chat links from the ChatGPT sidebar.
    Returns list of dicts: {title, url, chat_id}
    """
    chats = []
    seen_ids = set()

    # Try multiple selector strategies for the sidebar chat list
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
                    # ChatGPT chat URLs look like /c/{id} or /g/{id}
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


def scroll_sidebar(page, max_scrolls=30):
    """Scroll the sidebar to load all chats."""
    for i in range(max_scrolls):
        try:
            # Try to find the scrollable sidebar container
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
                # Fallback: scroll the page itself
                page.evaluate('window.scrollBy(0, 1000)')
            time.sleep(0.5)
        except Exception:
            break
    return


def extract_conversation(page):
    """
    Extract the full conversation from the current ChatGPT chat page.
    Returns list of {role, content} dicts.
    """
    messages = []

    # Strategy 1: Look for article elements (ChatGPT uses <article> for messages)
    try:
        articles = page.query_selector_all('article')
        for article in articles:
            try:
                text = article.inner_text().strip()
                if text and len(text) > 2:
                    # Try to determine role (user vs assistant)
                    # User messages typically have specific markers
                    aria_label = article.get_attribute('aria-label') or ''
                    data_role = article.get_attribute('data-role') or ''

                    role = 'unknown'
                    if 'user' in aria_label.lower() or 'user' in data_role.lower():
                        role = 'user'
                    elif 'assistant' in aria_label.lower() or 'assistant' in data_role.lower():
                        role = 'assistant'

                    # Fallback: check for textarea-like elements (user input)
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

    # Strategy 2: Look for message containers with data-testid
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

    # Strategy 3: Grab all text blocks in the main content area
    if not messages:
        try:
            main = page.query_selector('main') or page.query_selector('#main')
            if main:
                # Split by common message separators
                full_text = main.inner_text()
                # This is a rough fallback
                messages.append({'role': 'raw', 'content': full_text})
        except Exception:
            pass

    return messages


def copy_profile():
    """Copy the Edge profile to a temp dir so we don't lock the original."""
    import shutil
    src = EDGE_PROFILE_ORIG
    dst = EDGE_PROFILE_COPY

    print(f"  Copying Edge profile to {dst}...")
    # Remove old copy if exists
    if os.path.exists(dst):
        shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(os.path.dirname(dst), exist_ok=True)

    # Copy only what we need — the Default profile and key files
    # Full copy is too large, so we copy selectively
    os.makedirs(dst, exist_ok=True)

    # Copy top-level files (Local State, etc.)
    for item in os.listdir(src):
        src_path = os.path.join(src, item)
        dst_path = os.path.join(dst, item)
        if os.path.isfile(src_path) and item in ('Local State', 'First Run'):
            try:
                shutil.copy2(src_path, dst_path)
            except Exception:
                pass

    # Copy the Default profile directory (selectively to keep size manageable)
    default_src = os.path.join(src, 'Default')
    default_dst = os.path.join(dst, 'Default')
    os.makedirs(default_dst, exist_ok=True)

    # Key files that contain cookies/session
    important_files = [
        'Cookies', 'Cookies-journal',
        'Local Storage', 'Local Storage-journal',
        'Session Storage', 'Session Storage-journal',
        'Login Data', 'Login Data-journal',
        'Web Data', 'Web Data-journal',
        'Preferences',
        'Secure Preferences',
        'Network', 'Network-journal',
        'Trust Database',
    ]

    for item in important_files:
        src_path = os.path.join(default_src, item)
        dst_path = os.path.join(default_dst, item)
        if os.path.exists(src_path):
            try:
                if os.path.isfile(src_path):
                    shutil.copy2(src_path, dst_path)
                elif os.path.isdir(src_path):
                    shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
            except Exception as e:
                print(f"    Warning: could not copy {item}: {e}")

    # Copy Local Storage directory if it exists as a folder
    ls_src = os.path.join(default_src, 'Local Storage')
    if os.path.isdir(ls_src):
        ls_dst = os.path.join(default_dst, 'Local Storage')
        os.makedirs(ls_dst, exist_ok=True)
        for item in os.listdir(ls_src):
            try:
                s = os.path.join(ls_src, item)
                d = os.path.join(ls_dst, item)
                if os.path.isfile(s):
                    shutil.copy2(s, d)
                elif os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
            except Exception:
                pass

    print("  Profile copy complete.")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("ChatGPT Chat Extractor for Microsoft Edge")
    print("=" * 60)

    # Copy profile to avoid locking the original
    copy_profile()

    with sync_playwright() as p:
        # Launch Edge with the copied profile
        context = p.chromium.launch_persistent_context(
            user_data_dir=EDGE_PROFILE_COPY,
            executable_path=EDGE_PATH,
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-first-run',
                '--no-default-browser-check',
            ],
            viewport={'width': 1280, 'height': 900},
        )

        page = context.pages[0] if context.pages else context.new_page()

        print(f"\n[1/4] Navigating to {CHATGPT_URL}...")
        page.goto(CHATGPT_URL, wait_until='networkidle', timeout=60000)
        time.sleep(5)  # Let the page fully load

        # Check if we're logged in
        current_url = page.url
        print(f"  Current URL: {current_url}")

        if 'auth0' in current_url or 'login' in current_url or 'auth' in current_url:
            print("\n  ⚠ You appear to be logged out. Please log in to ChatGPT in the browser window.")
            print("  Press Enter here once you're logged in and see the chat interface...")
            input()

        # Wait for sidebar to load
        print("\n[2/4] Waiting for sidebar to load...")
        time.sleep(3)

        # Scroll sidebar to load all chats
        print("  Scrolling sidebar to load all chats...")
        scroll_sidebar(page, max_scrolls=50)
        time.sleep(2)

        # Extract chat list
        print("\n[3/4] Extracting chat list from sidebar...")
        chats = extract_chats_from_page(page)

        if not chats:
            print("  No chats found via selectors. Trying alternative approach...")
            # Try clicking "more" or expand buttons
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
            print("\n  No chats could be extracted. The page structure may have changed.")
            print("  Saving a screenshot for debugging...")
            page.screenshot(path=str(OUTPUT_DIR / "debug_screenshot.png"))
            # Also save the page HTML for debugging
            html = page.content()
            (OUTPUT_DIR / "debug_page.html").write_text(html)
            print(f"  Screenshot and HTML saved to {OUTPUT_DIR}/")
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
                page.goto(chat['url'], wait_until='networkidle', timeout=30000)
                time.sleep(3)  # Let messages load

                messages = extract_conversation(page)
                conversation = {
                    'title': chat['title'],
                    'url': chat['url'],
                    'chat_id': chat['chat_id'],
                    'messages': messages,
                    'message_count': len(messages),
                }
                all_conversations.append(conversation)

                # Save individual chat as markdown
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

        # Save all conversations as JSON
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
