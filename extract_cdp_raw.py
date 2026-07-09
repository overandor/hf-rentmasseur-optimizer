#!/usr/bin/env python3
"""
Extract ChatGPT chats via raw CDP WebSocket (no Playwright).
Connects directly to Edge's remote debugging port.
"""

import json
import time
import re
import asyncio
import websockets
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "chatgpt_exports"
CDP_URL = "http://localhost:9222"


async def cdp_send(ws, method, params=None, msg_id=1):
    """Send a CDP command and wait for the result."""
    msg = {"id": msg_id, "method": method}
    if params:
        msg["params"] = params
    await ws.send(json.dumps(msg))
    
    # Wait for response with matching id
    while True:
        response = await asyncio.wait_for(ws.recv(), timeout=30)
        data = json.loads(response)
        if data.get("id") == msg_id:
            return data
        # Skip events


async def cdp_eval(ws, expression, msg_id=1):
    """Evaluate JavaScript in the page and return the result."""
    result = await cdp_send(ws, "Runtime.evaluate", {
        "expression": expression,
        "returnByValue": True,
        "awaitPromise": True,
    }, msg_id)
    
    if "error" in result:
        return None, result["error"]
    
    if "result" in result and "result" in result["result"]:
        return result["result"]["result"].get("value"), None
    return None, result.get("error", "Unknown error")


async def main():
    import urllib.request
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("ChatGPT Extractor via raw CDP WebSocket")
    print("=" * 60)
    
    # Get the ChatGPT tab's WebSocket URL
    with urllib.request.urlopen(f"{CDP_URL}/json/list") as resp:
        tabs = json.loads(resp.read())
    
    chatgpt_tab = None
    for tab in tabs:
        if "chatgpt" in tab.get("url", "").lower() and tab.get("type") == "page":
            chatgpt_tab = tab
            break
    
    if not chatgpt_tab:
        print("No ChatGPT tab found!")
        return
    
    ws_url = chatgpt_tab["webSocketDebuggerUrl"]
    print(f"Connecting to: {ws_url}")
    
    async with websockets.connect(ws_url, max_size=50*1024*1024) as ws:
        # Check login status
        print("\nChecking login status...")
        result, err = await cdp_eval(ws, """
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
                return JSON.stringify({
                    logged_in: !hasLogin,
                    chat_count: chatLinks.length,
                    body_preview: text.substring(0, 300)
                });
            })()
        """, 1)
        
        if err:
            print(f"Error: {err}")
            return
        
        print(f"Login check: {result}")
        
        if not result:
            print("No result from JS evaluation")
            return
        
        login_data = json.loads(result)
        
        if not login_data.get("logged_in", False):
            print("Not logged in. Waiting 15 seconds for session to restore...")
            await asyncio.sleep(15)
            
            # Retry
            result, err = await cdp_eval(ws, """
                (function() {
                    var text = document.body ? document.body.innerText : '';
                    var hasLogin = text.indexOf('Log in') > -1;
                    return JSON.stringify({logged_in: !hasLogin, body_preview: text.substring(0, 300)});
                })()
            """, 2)
            
            if result:
                login_data = json.loads(result)
                print(f"Retry: {login_data}")
        
        if not login_data.get("logged_in", False):
            print("Still not logged in. Saving debug info...")
            body_text, _ = await cdp_eval(ws, "document.body ? document.body.innerText.substring(0, 2000) : 'no body'", 3)
            (OUTPUT_DIR / "cdp_raw_debug.txt").write_text(body_text or "no body")
            print(f"Body: {body_text[:200] if body_text else 'none'}")
            return
        
        # Scroll sidebar
        print("\nScrolling sidebar...")
        await cdp_eval(ws, """
            (function() {
                var nav = document.querySelector('nav');
                if (nav) {
                    for (var i = 0; i < 100; i++) {
                        nav.scrollBy(0, 1000);
                    }
                    return 'scrolled';
                }
                return 'no_nav';
            })()
        """, 4)
        await asyncio.sleep(3)
        
        # Extract chat list
        print("Extracting chat list...")
        chats_json, err = await cdp_eval(ws, """
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
        """, 5)
        
        if err:
            print(f"Error extracting chats: {err}")
            return
        
        try:
            chats = json.loads(chats_json) if chats_json else []
        except:
            chats = []
        
        print(f"Found {len(chats)} chats.")
        
        if not chats:
            print("No chats found. Saving debug info...")
            body, _ = await cdp_eval(ws, "document.body ? document.body.innerText.substring(0, 2000) : 'no body'", 6)
            (OUTPUT_DIR / "cdp_raw_no_chats.txt").write_text(body or "no body")
            return
        
        # Save chat index
        (OUTPUT_DIR / "chat_index.json").write_text(json.dumps(chats, indent=2, ensure_ascii=False))
        print(f"Chat index saved.")
        
        # Extract each conversation
        print(f"\nExtracting {len(chats)} conversations...")
        all_conversations = []
        
        for i, chat in enumerate(chats):
            print(f"  [{i+1}/{len(chats)}] {chat['title'][:50]}...", end=" ", flush=True)
            
            # Navigate to chat
            await cdp_send(ws, "Page.navigate", {"url": chat["url"]}, 100 + i)
            await asyncio.sleep(5)
            
            # Extract messages
            msgs_json, err = await cdp_eval(ws, """
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
            """, 200 + i)
            
            try:
                messages = json.loads(msgs_json) if msgs_json else []
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
    asyncio.run(main())
