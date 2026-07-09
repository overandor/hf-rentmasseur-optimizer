#!/usr/bin/env python3
"""
Double proxy login: Open two ChatGPT tabs with different strategies.
Tab 1: Direct navigation with existing cookies (wait for session restore)
Tab 2: Navigate to auth.openai.com login flow directly
Both run simultaneously via CDP.
"""

import json
import time
import asyncio
import websockets
import urllib.request
from pathlib import Path

CDP_URL = "http://localhost:9222"
OUTPUT_DIR = Path(__file__).parent / "chatgpt_exports"


async def cdp_send(ws, method, params=None, msg_id=1):
    msg = {"id": msg_id, "method": method}
    if params:
        msg["params"] = params
    await ws.send(json.dumps(msg))
    while True:
        response = await asyncio.wait_for(ws.recv(), timeout=30)
        data = json.loads(response)
        if data.get("id") == msg_id:
            return data


async def cdp_eval(ws, expression, msg_id=1):
    result = await cdp_send(ws, "Runtime.evaluate", {
        "expression": expression,
        "returnByValue": True,
        "awaitPromise": True,
    }, msg_id)
    if "result" in result and "result" in result["result"]:
        return result["result"]["result"].get("value"), None
    return None, result.get("error", "unknown")


async def create_tab(url):
    """Create a new tab via CDP."""
    full_url = f"{CDP_URL}/json/new?{url}"
    req = urllib.request.Request(full_url, method="PUT")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
        return data


async def check_login(ws, label, msg_id_start):
    """Check if logged in and get page state."""
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
                url: window.location.href,
                title: document.title,
                body_preview: text.substring(0, 300)
            });
        })()
    """, msg_id_start)
    
    if err:
        print(f"  [{label}] Error: {err}")
        return None
    
    try:
        data = json.loads(result)
        logged = data.get("logged_in", False)
        chats = data.get("chat_count", 0)
        url = data.get("url", "?")
        print(f"  [{label}] logged_in={logged} chats={chats} url={url[:60]}")
        if not logged:
            preview = data.get("body_preview", "")[:150]
            print(f"  [{label}] body: {preview}")
        return data
    except:
        print(f"  [{label}] Parse error: {result[:200] if result else 'none'}")
        return None


async def tab_strategy_1(ws, label="TAB1"):
    """Strategy 1: Navigate to ChatGPT, wait for session restore from cookies."""
    print(f"\n[{label}] Strategy: Direct navigation + wait for session restore")
    
    # Navigate to ChatGPT
    await cdp_send(ws, "Page.navigate", {"url": "https://chatgpt.com/"}, 1)
    await asyncio.sleep(8)
    
    # Check login
    data = await check_login(ws, label, 10)
    
    if data and not data.get("logged_in"):
        # Try refreshing to trigger cookie-based session restore
        print(f"  [{label}] Not logged in. Trying refresh...")
        await cdp_eval(ws, "window.location.reload()", 20)
        await asyncio.sleep(10)
        data = await check_login(ws, label, 30)
    
    if data and not data.get("logged_in"):
        # Try navigating to the API auth session endpoint
        print(f"  [{label}] Trying /api/auth/session...")
        await cdp_send(ws, "Page.navigate", {"url": "https://chatgpt.com/api/auth/session"}, 40)
        await asyncio.sleep(5)
        
        session_json, err = await cdp_eval(ws, "document.body.innerText", 50)
        if session_json:
            print(f"  [{label}] Session response: {session_json[:300]}")
            try:
                session = json.loads(session_json)
                if session.get("user"):
                    print(f"  [{label}] USER FOUND: {session['user'].get('email', '?')}")
                    # Navigate back to ChatGPT
                    await cdp_send(ws, "Page.navigate", {"url": "https://chatgpt.com/"}, 60)
                    await asyncio.sleep(8)
                    data = await check_login(ws, label, 70)
            except:
                print(f"  [{label}] Session response not JSON")
    
    if data and not data.get("logged_in"):
        # Try adding cookies via CDP and reloading
        print(f"  [{label}] Trying to inject cookies via CDP...")
        # Get existing cookies from the browser
        cookie_result = await cdp_send(ws, "Network.getCookies", {"urls": ["https://chatgpt.com", "https://chat.openai.com"]}, 80)
        cookies = cookie_result.get("result", {}).get("cookies", [])
        print(f"  [{label}] Existing cookies: {len(cookies)}")
        for c in cookies:
            print(f"  [{label}]   {c.get('domain', '?'):20s} {c.get('name', '?'):40s} val_len={len(str(c.get('value', '')))}")
    
    return data


async def tab_strategy_2(ws, label="TAB2"):
    """Strategy 2: Navigate to auth.openai.com directly."""
    print(f"\n[{label}] Strategy: Direct auth.openai.com login flow")
    
    # Navigate to the ChatGPT auth callback
    await cdp_send(ws, "Page.navigate", {"url": "https://chatgpt.com/auth/login"}, 1)
    await asyncio.sleep(8)
    
    data = await check_login(ws, label, 10)
    
    if data and not data.get("logged_in"):
        # Check what URL we ended up at
        url_data, _ = await cdp_eval(ws, "window.location.href", 20)
        print(f"  [{label}] Redirected to: {url_data}")
        
        # Try the OpenAI auth flow
        print(f"  [{label}] Trying auth0 callback...")
        await cdp_send(ws, "Page.navigate", {"url": "https://auth.openai.com/authorize?client_id=DRivsnm2Mu42T3KOpqdtwB3NYviHYzwD&scope=openid%20email%20profile%20offline_access%20model.request%20model.read%20organization.read%20organization.write&response_type=code&redirect_uri=https%3A%2F%2Fchatgpt.com%2Fapi%2Fauth%2Fcallback%2Flogin-web&audience=https%3A%2F%2Fapi.openai.com%2Fv1&prompt=login&screen_hint=login"}, 30)
        await asyncio.sleep(10)
        
        url_data2, _ = await cdp_eval(ws, "window.location.href", 40)
        title, _ = await cdp_eval(ws, "document.title", 41)
        body, _ = await cdp_eval(ws, "document.body ? document.body.innerText.substring(0, 300) : 'no body'", 42)
        print(f"  [{label}] URL: {url_data2}")
        print(f"  [{label}] Title: {title}")
        print(f"  [{label}] Body: {body[:200] if body else 'none'}")
    
    if data and not data.get("logged_in"):
        # Try Google OAuth
        print(f"  [{label}] Trying Google OAuth flow...")
        await cdp_send(ws, "Page.navigate", {"url": "https://chatgpt.com/auth/login"}, 50)
        await asyncio.sleep(5)
        
        # Look for and click "Continue with Google" button
        click_result, _ = await cdp_eval(ws, """
            (function() {
                var buttons = document.querySelectorAll('button, a');
                for (var i = 0; i < buttons.length; i++) {
                    var text = buttons[i].innerText || '';
                    if (text.toLowerCase().indexOf('google') > -1) {
                        buttons[i].click();
                        return 'clicked: ' + text;
                    }
                }
                return 'no google button found';
            })()
        """, 60)
        print(f"  [{label}] Google OAuth: {click_result}")
        await asyncio.sleep(10)
        
        url_data3, _ = await cdp_eval(ws, "window.location.href", 70)
        print(f"  [{label}] After Google click URL: {url_data3}")
    
    return data


async def main():
    print("=" * 60)
    print("Double Proxy Login - Two Tab Strategy")
    print("=" * 60)
    
    # Get current tabs
    with urllib.request.urlopen(f"{CDP_URL}/json/list") as resp:
        tabs = json.loads(resp.read())
    
    page_tabs = [t for t in tabs if t.get("type") == "page"]
    print(f"Current page tabs: {len(page_tabs)}")
    
    # Create two new tabs
    print("\nCreating Tab 1 (ChatGPT direct)...")
    tab1 = await create_tab("https://chatgpt.com/")
    ws1_url = tab1["webSocketDebuggerUrl"]
    print(f"  Tab 1 WS: {ws1_url}")
    
    print("Creating Tab 2 (ChatGPT auth)...")
    tab2 = await create_tab("https://chatgpt.com/auth/login")
    ws2_url = tab2["webSocketDebuggerUrl"]
    print(f"  Tab 2 WS: {ws2_url}")
    
    # Run both strategies simultaneously
    async with websockets.connect(ws1_url, max_size=50*1024*1024) as ws1, \
               websockets.connect(ws2_url, max_size=50*1024*1024) as ws2:
        
        # Run both in parallel
        results = await asyncio.gather(
            tab_strategy_1(ws1, "TAB1"),
            tab_strategy_2(ws2, "TAB2")
        )
        
        data1, data2 = results
        
        print("\n" + "=" * 60)
        print("Results:")
        print(f"  Tab 1 (direct): logged_in={data1.get('logged_in') if data1 else 'error'}")
        print(f"  Tab 2 (auth):   logged_in={data2.get('logged_in') if data2 else 'error'}")
        
        # If either succeeded, extract chats
        for i, (label, data, ws) in enumerate([("TAB1", data1, ws1), ("TAB2", data2, ws2)]):
            if data and data.get("logged_in"):
                print(f"\n[{label}] SUCCESS! Extracting chats...")
                
                # Scroll sidebar
                await cdp_eval(ws, """
                    (function() {
                        var nav = document.querySelector('nav');
                        if (nav) { for (var i = 0; i < 100; i++) nav.scrollBy(0, 1000); return 'scrolled'; }
                        return 'no_nav';
                    })()
                """, 900 + i * 100)
                await asyncio.sleep(3)
                
                # Get chat list
                chats_json, _ = await cdp_eval(ws, """
                    (function() {
                        var links = document.querySelectorAll('nav a[href*="/c/"], nav a[href*="/g/"], a[href*="/c/"], a[href*="/g/"]');
                        var chats = []; var seen = {};
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
                """, 950 + i * 100)
                
                try:
                    chats = json.loads(chats_json) if chats_json else []
                    print(f"  [{label}] Found {len(chats)} chats!")
                    (OUTPUT_DIR / "double_proxy_chats.json").write_text(
                        json.dumps(chats, indent=2, ensure_ascii=False)
                    )
                except:
                    print(f"  [{label}] Failed to parse chats")
        
        print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
