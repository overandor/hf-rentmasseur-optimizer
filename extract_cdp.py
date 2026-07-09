#!/usr/bin/env python3
"""
Connect to running Edge (with remote debugging port) via Playwright CDP.
Edge is launched normally with --remote-debugging-port=9222, giving:
- Full Keychain access (user is logged in to ChatGPT)
- Remote debugging port (we can control it via CDP)
- No automation flags (Cloudflare doesn't block it)
"""

import json
import time
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

OUTPUT_DIR = Path(__file__).parent / "chatgpt_exports"
CDP_URL = "http://localhost:9222"


def sanitize_filename(name):
    name = re.sub(r'[^\w\s\-]', '', name).strip()
    name = re.sub(r'[\s]+', '_', name)
    return (name or "untitled")[:100]


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("ChatGPT Extractor via CDP (remote debugging)")
    print("=" * 60)

    with sync_playwright() as p:
        # Connect to the running Edge instance
        print(f"\nConnecting to Edge via CDP at {CDP_URL}...")
        browser = p.chromium.connect_over_cdp(CDP_URL)
        
        contexts = browser.contexts
        if not contexts:
            print("No browser contexts found!")
            return
        
        context = contexts[0]
        pages = context.pages
        
        print(f"Found {len(pages)} tabs:")
        for i, page in enumerate(pages):
            print(f"  [{i}] {page.title()}: {page.url[:80]}")
        
        # Find the ChatGPT tab
        chatgpt_page = None
        for page in pages:
            if "chatgpt" in page.url.lower():
                chatgpt_page = page
                break
        
        if not chatgpt_page:
            print("\nNo ChatGPT tab found. Creating one...")
            chatgpt_page = context.new_page()
            chatgpt_page.goto("https://chatgpt.com", wait_until="domcontentloaded", timeout=60000)
            time.sleep(15)
        
        print(f"\nUsing tab: {chatgpt_page.title()}")
        print(f"URL: {chatgpt_page.url}")
        
        # Wait for page to fully load
        time.sleep(5)
        
        # Check if logged in
        print("\nChecking login status...")
        login_check = chatgpt_page.evaluate("""
            () => {
                var body = document.body;
                if (!body) return 'NO_BODY';
                var text = body.innerText;
                if (text.indexOf('Log in') > -1 && text.indexOf('Chat history') > -1) {
                    return 'NOT_LOGGED_IN';
                }
                var nav = document.querySelector('nav');
                if (nav) {
                    var links = nav.querySelectorAll('a[href*="/c/"], a[href*="/g/"]');
                    return 'LOGGED_IN:' + links.length + '_chats_visible';
                }
                return 'UNKNOWN:' + text.substring(0, 200);
            }
        """)
        print(f"  Login check: {login_check}")
        
        if "NOT_LOGGED_IN" in login_check:
            print("  Not logged in. Waiting 10 more seconds...")
            time.sleep(10)
            login_check = chatgpt_page.evaluate("""
                () => {
                    var text = document.body ? document.body.innerText : '';
                    var nav = document.querySelector('nav');
                    var links = nav ? nav.querySelectorAll('a[href*="/c/"], a[href*="/g/"]') : [];
                    if (links.length > 0) return 'LOGGED_IN:' + links.length + '_chats';
                    if (text.indexOf('Log in') > -1) return 'NOT_LOGGED_IN';
                    return 'UNKNOWN:' + text.substring(0, 200);
                }
            """)
            print(f"  Login check (retry): {login_check}")
        
        if "NOT_LOGGED_IN" in str(login_check):
            print("\n  Still not logged in. Saving debug info...")
            chatgpt_page.screenshot(path=str(OUTPUT_DIR / "cdp_debug.png"))
            body_text = chatgpt_page.evaluate("() => document.body ? document.body.innerText.substring(0, 1000) : 'no body'")
            (OUTPUT_DIR / "cdp_debug.txt").write_text(body_text)
            print(f"  Debug saved. Body text: {body_text[:200]}")
            # Don't close the browser since it's the user's real Edge
            return
        
        # Scroll sidebar to load all chats
        print("\nScrolling sidebar to load all chats...")
        chatgpt_page.evaluate("""
            () => {
                var nav = document.querySelector('nav');
                if (nav) {
                    for (var i = 0; i < 100; i++) {
                        nav.scrollBy(0, 1000);
                    }
                }
            }
        """)
        time.sleep(3)
        
        # Extract chat list
        print("Extracting chat list...")
        chats_json = chatgpt_page.evaluate("""
            () => {
                var links = document.querySelectorAll('nav a[href*="/c/"], nav a[href*="/g/"], a[href*="/c/"], a[href*="/g/"]');
                var chats = [];
                var seen = {};
                for (var i = 0; i < links.length; i++) {
                    var href = links[i].getAttribute('href') || '';
                    var text = links[i].innerText.trim();
                    if (href && (href.indexOf('/c/') > -1 || href.indexOf('/g/') > -1)) {
                        var id = href.split('/').pop().split('?')[0];
                        if (!seen[id]) {
                            seen[id] = true;
                            var fullUrl = href.startsWith('http') ? href : 'https://chatgpt.com' + href;
                            chats.push({title: text || ('chat_' + id.substring(0,8)), url: fullUrl, chat_id: id});
                        }
                    }
                }
                return JSON.stringify(chats);
            }
        """)
        
        try:
            chats = json.loads(chats_json)
        except:
            chats = []
            print(f"  Failed to parse: {chats_json[:200]}")
        
        print(f"  Found {len(chats)} chats.")
        
        if not chats:
            print("  No chats found. Saving debug info...")
            body_text = chatgpt_page.evaluate("() => document.body ? document.body.innerText.substring(0, 2000) : 'no body'")
            (OUTPUT_DIR / "cdp_no_chats.txt").write_text(body_text)
            chatgpt_page.screenshot(path=str(OUTPUT_DIR / "cdp_no_chats.png"))
            print(f"  Debug saved.")
            return
        
        # Save chat index
        index_path = OUTPUT_DIR / "chat_index.json"
        index_path.write_text(json.dumps(chats, indent=2, ensure_ascii=False))
        print(f"  Chat index saved to {index_path}")
        
        # Extract each conversation
        print(f"\nExtracting {len(chats)} conversations...")
        all_conversations = []
        
        for i, chat in enumerate(chats):
            print(f"  [{i+1}/{len(chats)}] {chat['title'][:50]}...", end=" ", flush=True)
            try:
                chatgpt_page.goto(chat["url"], wait_until="domcontentloaded", timeout=30000)
                time.sleep(4)
                
                # Extract messages
                messages = chatgpt_page.evaluate("""
                    () => {
                        var messages = [];
                        var articles = document.querySelectorAll('article');
                        for (var i = 0; i < articles.length; i++) {
                            var text = articles[i].innerText.trim();
                            if (text.length > 2) {
                                var aria = articles[i].getAttribute('aria-label') || '';
                                var role = 'unknown';
                                if (aria.toLowerCase().indexOf('user') > -1) role = 'user';
                                else if (aria.toLowerCase().indexOf('assistant') > -1) role = 'assistant';
                                messages.push({role: role, content: text});
                            }
                        }
                        if (messages.length === 0) {
                            var main = document.querySelector('main');
                            if (main) {
                                messages.push({role: 'raw', content: main.innerText});
                            }
                        }
                        return messages;
                    }
                """)
                
                conversation = {
                    "title": chat["title"],
                    "url": chat["url"],
                    "chat_id": chat["chat_id"],
                    "messages": messages,
                    "message_count": len(messages),
                }
                all_conversations.append(conversation)
                
                # Save markdown
                safe_name = sanitize_filename(chat["title"])
                md_path = OUTPUT_DIR / f"{i+1:04d}_{safe_name}.md"
                md_lines = [
                    f"# {chat['title']}\n",
                    f"URL: {chat['url']}\n",
                    f"Chat ID: {chat['chat_id']}\n",
                    f"Messages: {len(messages)}\n",
                    "---\n",
                ]
                for msg in messages:
                    md_lines.append(f"\n## [{msg['role'].upper()}]\n")
                    md_lines.append(msg["content"])
                    md_lines.append("")
                md_path.write_text("\n".join(md_lines))
                
                print(f"({len(messages)} msgs)")
            except Exception as e:
                print(f"ERROR: {e}")
                all_conversations.append({
                    "title": chat["title"],
                    "url": chat["url"],
                    "chat_id": chat["chat_id"],
                    "messages": [],
                    "message_count": 0,
                    "error": str(e),
                })
        
        # Save all as JSON
        all_json = OUTPUT_DIR / "all_chats.json"
        all_json.write_text(json.dumps(all_conversations, indent=2, ensure_ascii=False))
        
        print(f"\n{'=' * 60}")
        print(f"Extraction complete!")
        print(f"  Total chats: {len(all_conversations)}")
        print(f"  Total messages: {sum(c.get('message_count', 0) for c in all_conversations)}")
        print(f"  Output directory: {OUTPUT_DIR}")
        print(f"  All chats JSON: {all_json}")
        print(f"  Individual markdown files: {OUTPUT_DIR}/*.md")
        print(f"{'=' * 60}")
        
        # Don't close the browser - it's the user's real Edge


if __name__ == "__main__":
    main()
