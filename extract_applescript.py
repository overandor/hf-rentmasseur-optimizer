#!/usr/bin/env python3
"""
Extract ChatGPT chats using AppleScript to control Microsoft Edge.
This launches Edge normally (not via WebDriver), so it has full Keychain
access and the user's session is intact.
Uses JavaScript injection via AppleScript to extract chat data.
"""

import os
import time
import json
import re
import subprocess
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "chatgpt_exports"
CHATGPT_URL = "https://chatgpt.com"


def run_applescript(script):
    """Run an AppleScript and return the output."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=120
    )
    return result.stdout.strip(), result.stderr.strip()


def run_applescript_file(script_path):
    """Run an AppleScript from a file."""
    result = subprocess.run(
        ["osascript", script_path],
        capture_output=True, text=True, timeout=300
    )
    return result.stdout.strip(), result.stderr.strip()


def launch_edge_and_navigate(url):
    """Launch Edge normally and navigate to a URL."""
    script = f'''
    tell application "Microsoft Edge"
        activate
        if (count of windows) = 0 then
            make new window
        end if
        set theURL to "{url}"
        set t to ""
        try
            tell front window
                set newTab to make new tab with properties {{URL:theURL}}
            end tell
        on error
            tell front window
                set URL of active tab to theURL
            end tell
        end try
    end tell
    '''
    out, err = run_applescript(script)
    if err:
        print(f"  AppleScript error: {err}")
    return out


def execute_js_in_edge(js_code):
    """Execute JavaScript in the active Edge tab and return the result."""
    # Escape the JS code for AppleScript
    escaped_js = js_code.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    script = f'''
    tell application "Microsoft Edge"
        tell front window
            tell active tab
                set jsResult to execute javascript "{escaped_js}"
                return jsResult
            end tell
        end tell
    end tell
    '''
    out, err = run_applescript(script)
    if err:
        print(f"  JS error: {err[:200]}")
    return out


def get_current_url():
    """Get the URL of the active Edge tab."""
    script = '''
    tell application "Microsoft Edge"
        tell front window
            tell active tab
                return URL
            end tell
        end tell
    end tell
    '''
    out, err = run_applescript(script)
    return out


def get_page_title():
    """Get the title of the active Edge tab."""
    script = '''
    tell application "Microsoft Edge"
        tell front window
            tell active tab
                return title
            end tell
        end tell
    end tell
    '''
    out, err = run_applescript(script)
    return out


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("ChatGPT Extractor via AppleScript + Edge")
    print("=" * 60)

    # First, make sure Edge is not running (we need to close it if Selenium left it open)
    print("\nClosing any existing Edge instances...")
    subprocess.run(["pkill", "-x", "Microsoft Edge"], capture_output=True)
    time.sleep(3)

    # Launch Edge normally (this gives it Keychain access)
    print("Launching Edge normally (with Keychain access)...")
    subprocess.Popen(["open", "-a", "Microsoft Edge", CHATGPT_URL])
    time.sleep(15)  # Wait for Edge to launch and load ChatGPT

    # Check current URL
    url = get_current_url()
    title = get_page_title()
    print(f"  URL: {url}")
    print(f"  Title: {title}")

    # Wait for Cloudflare to clear if needed
    for i in range(30):
        if "__cf_chl" not in url and "challenge" not in url.lower():
            break
        print(f"  Waiting for Cloudflare... ({i+1}/30)")
        time.sleep(3)
        url = get_current_url()

    # Check if logged in
    print("\nChecking login status...")
    js_check = """
    (function() {
        var body = document.body;
        if (!body) return 'NO_BODY';
        var text = body.innerText;
        if (text.indexOf('Log in') > -1 && text.indexOf('Chat history') > -1) {
            return 'NOT_LOGGED_IN';
        }
        // Check for sidebar with chat links
        var nav = document.querySelector('nav');
        if (nav) {
            var links = nav.querySelectorAll('a[href*=\"/c/\"], a[href*=\"/g/\"]');
            return 'LOGGED_IN:' + links.length + '_chats_visible';
        }
        return 'UNKNOWN:' + text.substring(0, 200);
    })()
    """
    result = execute_js_in_edge(js_check)
    print(f"  Login check: {result}")

    if "NOT_LOGGED_IN" in result:
        print("\n  Not logged in. Trying to wait longer...")
        time.sleep(10)
        result = execute_js_in_edge(js_check)
        print(f"  Login check (retry): {result}")

    if "NOT_LOGGED_IN" in result:
        print("  Still not logged in. Edge may need manual login.")
        print("  Saving debug info...")
        debug_js = "document.body ? document.body.innerText.substring(0, 500) : 'no body'"
        debug_text = execute_js_in_edge(debug_js)
        (OUTPUT_DIR / "applescript_debug.txt").write_text(debug_text)
        return

    # Extract chat list from sidebar
    print("\nExtracting chat list from sidebar...")

    # First, scroll the sidebar to load all chats
    scroll_js = """
    (function() {
        var nav = document.querySelector('nav');
        if (nav) {
            for (var i = 0; i < 50; i++) {
                nav.scrollBy(0, 1000);
            }
            return 'scrolled';
        }
        return 'no_nav';
    })()
    """
    execute_js_in_edge(scroll_js)
    time.sleep(3)

    # Extract chat links
    extract_chats_js = """
    (function() {
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
                    chats.push({title: text, url: fullUrl, chat_id: id});
                }
            }
        }
        return JSON.stringify(chats);
    })()
    """
    chats_json = execute_js_in_edge(extract_chats_js)
    
    try:
        chats = json.loads(chats_json)
    except (json.JSONDecodeError, Exception):
        # Try to fix common JSON issues
        try:
            chats_json = chats_json.replace('\n', '\\n').replace('\r', '\\r')
            chats = json.loads(chats_json)
        except:
            chats = []
            print(f"  Failed to parse chats JSON: {chats_json[:200]}")

    print(f"  Found {len(chats)} chats.")

    if not chats:
        print("  No chats found. Saving debug info...")
        debug_js = "document.body ? document.body.innerText.substring(0, 1000) : 'no body'"
        debug_text = execute_js_in_edge(debug_js)
        (OUTPUT_DIR / "applescript_no_chats.txt").write_text(debug_text)
        print(f"  Debug text: {debug_text[:200]}")
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
        
        # Navigate to the chat
        nav_js = f'window.location.href = "{chat["url"]}";'
        execute_js_in_edge(nav_js)
        time.sleep(5)  # Wait for page to load

        # Extract messages
        extract_msgs_js = """
        (function() {
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
            return JSON.stringify(messages);
        })()
        """
        msgs_json = execute_js_in_edge(extract_msgs_js)
        
        try:
            messages = json.loads(msgs_json)
        except:
            messages = []
            print(f"PARSE_ERROR", end=" ")

        conversation = {
            "title": chat["title"],
            "url": chat["url"],
            "chat_id": chat["chat_id"],
            "messages": messages,
            "message_count": len(messages),
        }
        all_conversations.append(conversation)

        # Save markdown
        safe_name = re.sub(r'[^\w\s\-]', '', chat["title"]).strip()
        safe_name = re.sub(r'[\s]+', '_', safe_name) or "untitled"
        md_path = OUTPUT_DIR / f"{i+1:04d}_{safe_name[:100]}.md"
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

    # Save all as JSON
    all_json = OUTPUT_DIR / "all_chats.json"
    all_json.write_text(json.dumps(all_conversations, indent=2, ensure_ascii=False))

    print(f"\n{'=' * 60}")
    print(f"Extraction complete!")
    print(f"  Total chats: {len(all_conversations)}")
    print(f"  Total messages: {sum(c.get('message_count', 0) for c in all_conversations)}")
    print(f"  Output: {OUTPUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
