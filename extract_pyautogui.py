#!/usr/bin/env python3
"""
Enable "Allow JavaScript from Apple Events" in Edge via pyautogui UI automation,
then use AppleScript to extract ChatGPT chats.
"""

import subprocess
import time
import json
import re
import pyautogui
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "chatgpt_exports"


def run_applescript(script, timeout=60):
    """Run AppleScript and return output."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=timeout
    )
    return result.stdout.strip(), result.stderr.strip()


def enable_js_apple_events():
    """Use pyautogui to click through Edge menus to enable JS from Apple Events."""
    print("Enabling 'Allow JavaScript from Apple Events' in Edge...")
    
    # Activate Edge
    subprocess.run(["osascript", "-e", 'tell application "Microsoft Edge" to activate'], 
                   capture_output=True, timeout=10)
    time.sleep(2)
    
    # Get screen size
    screen_w, screen_h = pyautogui.size()
    print(f"Screen: {screen_w}x{screen_h}")
    
    # Click "View" menu in the menu bar
    # The menu bar is at the top of the screen on macOS
    # "View" is usually the 4th or 5th menu item
    
    # First, let's try using keyboard shortcuts
    # Press F2 to access menu bar (or use mouse)
    
    # Method: Use keyboard to navigate menus
    # Ctrl+F2 focuses the menu bar on macOS
    pyautogui.hotkey('ctrl', 'f2')
    time.sleep(1)
    
    # Type to search for "View" menu
    pyautogui.typewrite('View')
    time.sleep(0.5)
    pyautogui.press('return')
    time.sleep(1)
    
    # Now we should be in the View menu
    # Type "Developer" to find it
    pyautogui.typewrite('Developer')
    time.sleep(0.5)
    pyautogui.press('return')
    time.sleep(1)
    
    # Now in Developer submenu
    # Type "Allow JavaScript"
    pyautogui.typewrite('Allow JavaScript')
    time.sleep(0.5)
    pyautogui.press('return')
    time.sleep(1)
    
    print("Done attempting to enable JS from Apple Events.")
    
    # Verify by trying to execute JS
    out, err = run_applescript(
        'tell application "Microsoft Edge" to tell front window to tell active tab to execute javascript "1+1"'
    )
    if err:
        print(f"  Still blocked: {err[:100]}")
        return False
    else:
        print(f"  JS execution works! Result: {out}")
        return True


def extract_via_applescript():
    """Extract ChatGPT chats using AppleScript JS injection."""
    
    print("\n" + "=" * 60)
    print("ChatGPT Extractor via AppleScript + JS")
    print("=" * 60)
    
    # Navigate to ChatGPT if not already there
    url, _ = run_applescript(
        'tell application "Microsoft Edge" to tell front window to tell active tab to return URL'
    )
    print(f"Current URL: {url}")
    
    if "chatgpt" not in url.lower():
        print("Navigating to ChatGPT...")
        run_applescript(
            'tell application "Microsoft Edge" to tell front window to tell active tab to set URL to "https://chatgpt.com"'
        )
        time.sleep(15)
    
    # Check login status
    print("Checking login status...")
    js = """
    (function() {
        var text = document.body ? document.body.innerText : '';
        var hasLogin = text.indexOf('Log in') > -1;
        var nav = document.querySelector('nav');
        var links = nav ? nav.querySelectorAll('a[href]') : [];
        var chatLinks = [];
        for (var i = 0; i < links.length; i++) {
            var href = links[i].getAttribute('href') || '';
            if (href.indexOf('/c/') > -1 || href.indexOf('/g/') > -1) {
                chatLinks.push({text: links[i].innerText.trim(), href: href});
            }
        }
        return JSON.stringify({logged_in: !hasLogin, chat_count: chatLinks.length, body_preview: text.substring(0, 300)});
    })()
    """
    
    # Escape JS for AppleScript
    escaped_js = js.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    result, err = run_applescript(
        f'tell application "Microsoft Edge" to tell front window to tell active tab to execute javascript "{escaped_js}"'
    )
    
    if err:
        print(f"Error: {err[:200]}")
        return
    
    print(f"Login check: {result}")
    
    try:
        login_data = json.loads(result)
    except:
        print(f"Failed to parse: {result[:200]}")
        return
    
    if not login_data.get("logged_in"):
        print("Not logged in. Waiting 15 seconds...")
        time.sleep(15)
        result, err = run_applescript(
            f'tell application "Microsoft Edge" to tell front window to tell active tab to execute javascript "{escaped_js}"'
        )
        if result:
            try:
                login_data = json.loads(result)
                print(f"Retry: {login_data}")
            except:
                pass
    
    if not login_data.get("logged_in"):
        print("Still not logged in.")
        # Save debug
        debug_js = "document.body ? document.body.innerText.substring(0, 1000) : 'no body'"
        debug_js_escaped = debug_js.replace('"', '\\"')
        debug_result, _ = run_applescript(
            f'tell application "Microsoft Edge" to tell front window to tell active tab to execute javascript "{debug_js_escaped}"'
        )
        (OUTPUT_DIR / "applescript_debug.txt").write_text(debug_result or "no result")
        print(f"Debug: {debug_result[:200] if debug_result else 'none'}")
        return
    
    # Scroll sidebar
    print("\nScrolling sidebar...")
    scroll_js = """
    (function() {
        var nav = document.querySelector('nav');
        if (nav) {
            for (var i = 0; i < 100; i++) nav.scrollBy(0, 1000);
            return 'scrolled';
        }
        return 'no_nav';
    })()
    """
    scroll_js_escaped = scroll_js.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    run_applescript(
        f'tell application "Microsoft Edge" to tell front window to tell active tab to execute javascript "{scroll_js_escaped}"'
    )
    time.sleep(3)
    
    # Extract chat list
    print("Extracting chat list...")
    extract_js = """
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
                    chats.push({title: text || ('chat_' + id.substring(0,8)), url: fullUrl, chat_id: id});
                }
            }
        }
        return JSON.stringify(chats);
    })()
    """
    extract_js_escaped = extract_js.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    chats_result, err = run_applescript(
        f'tell application "Microsoft Edge" to tell front window to tell active tab to execute javascript "{extract_js_escaped}"'
    )
    
    if err:
        print(f"Error: {err[:200]}")
        return
    
    try:
        chats = json.loads(chats_result)
    except:
        chats = []
        print(f"Failed to parse chats: {chats_result[:200]}")
    
    print(f"Found {len(chats)} chats.")
    
    if not chats:
        print("No chats found.")
        return
    
    # Save chat index
    (OUTPUT_DIR / "chat_index.json").write_text(json.dumps(chats, indent=2, ensure_ascii=False))
    
    # Extract each conversation
    print(f"\nExtracting {len(chats)} conversations...")
    all_conversations = []
    
    for i, chat in enumerate(chats):
        print(f"  [{i+1}/{len(chats)}] {chat['title'][:50]}...", end=" ", flush=True)
        
        # Navigate to chat
        nav_js = f'window.location.href = "{chat["url"]}";'
        nav_js_escaped = nav_js.replace('"', '\\"')
        run_applescript(
            f'tell application "Microsoft Edge" to tell front window to tell active tab to execute javascript "{nav_js_escaped}"'
        )
        time.sleep(5)
        
        # Extract messages
        msg_js = """
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
                if (main) messages.push({role: 'raw', content: main.innerText});
            }
            return JSON.stringify(messages);
        })()
        """
        msg_js_escaped = msg_js.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        msgs_result, err = run_applescript(
            f'tell application "Microsoft Edge" to tell front window to tell active tab to execute javascript "{msg_js_escaped}"',
            timeout=30
        )
        
        try:
            messages = json.loads(msgs_result) if msgs_result else []
        except:
            messages = []
        
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
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # First enable JS from Apple Events
    if not enable_js_apple_events():
        print("\nCould not enable JS from Apple Events automatically.")
        print("Trying extraction anyway in case it was enabled via preferences...")
    
    extract_via_applescript()
