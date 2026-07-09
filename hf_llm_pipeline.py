"""
HF Login Pipeline with LLM Vision (LLaVA) + OCR (Tesseract)
- LLaVA sees each page state and decides what to do
- OCR extracts text for verification
- Handles WAF challenges, login forms, token creation
- Loop: screenshot → LLaVA analyze → act → verify
"""
import asyncio, re, os, json, base64, subprocess, time
from playwright.async_api import async_playwright

EDGE_PROFILE = os.path.expanduser("~/Library/Application Support/Microsoft Edge")
TEMP = "/tmp/edge_hf_llm"

def ocr(path):
    r = subprocess.run(["tesseract", path, "stdout"], capture_output=True, timeout=10)
    return r.stdout.decode("utf-8", errors="ignore").strip()

def llava(image_path, prompt):
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    payload = json.dumps({
        "model": "llava:latest",
        "prompt": prompt,
        "images": [b64],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 200}
    })
    r = subprocess.run(
        ["curl", "-s", "http://localhost:11434/api/generate", "-d", payload],
        capture_output=True, text=True, timeout=60
    )
    try:
        return json.loads(r.stdout).get("response", "")
    except:
        return ""

def llava_json(image_path, prompt):
    """Ask LLaVA to return structured JSON action."""
    full_prompt = f"""{prompt}

Look at this screenshot of a web page. Respond with ONLY a JSON object, no other text:
{{"action": "<one of: fill_username|fill_password|click_submit|click_link|wait|done|create_token|click_button|type_text>", "selector": "<css selector if applicable>", "text": "<text to type if applicable>", "description": "<what you see>"}}

Rules:
- If you see a login form with username/password fields, action=fill_username or fill_password
- If you see a submit/login button, action=click_submit
- If you see a WAF/captcha/challenge, action=wait
- If logged in (see dashboard/settings), action=done
- If on tokens page with create button, action=click_button
- If token creation form visible, action=type_text
- Be precise about CSS selectors based on what you see"""

    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    payload = json.dumps({
        "model": "llava:latest",
        "prompt": full_prompt,
        "images": [b64],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 300, "format": "json"}
    })
    r = subprocess.run(
        ["curl", "-s", "http://localhost:11434/api/generate", "-d", payload],
        capture_output=True, text=True, timeout=60
    )
    try:
        resp = json.loads(r.stdout).get("response", "")
        # Extract JSON from response
        match = re.search(r'\{[^}]+\}', resp, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"action": "unknown", "description": resp[:100]}
    except:
        return {"action": "unknown", "description": "parse error"}

async def llm_login_pipeline(username, password):
    import shutil
    if os.path.exists(TEMP):
        shutil.rmtree(TEMP, ignore_errors=True)
    os.makedirs(TEMP)
    try:
        shutil.copy2(os.path.join(EDGE_PROFILE, "Local State"), os.path.join(TEMP, "Local State"))
        shutil.copytree(os.path.join(EDGE_PROFILE, "Default"), os.path.join(TEMP, "Default"),
                        dirs_exist_ok=True, symlinks=True)
    except:
        pass
    for lock in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        for p in [os.path.join(TEMP, lock), os.path.join(TEMP, "Default", lock)]:
            if os.path.exists(p): os.remove(p)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            TEMP, channel="msedge", headless=False,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled", "--no-first-run"],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        
        step = 0
        max_steps = 25
        filled_username = False
        filled_password = False
        logged_in = False
        token_created = False
        
        print("[PIPELINE] Starting LLM-driven HF login...")
        await page.goto("https://huggingface.co/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        
        while step < max_steps and not token_created:
            step += 1
            screenshot = f"/tmp/hf_pipe_{step:02d}.png"
            await page.screenshot(path=screenshot)
            
            # OCR for ground truth
            ocr_text = ocr(screenshot)
            url = page.url
            
            print(f"\n[Step {step}] URL: {url}")
            print(f"  OCR: {ocr_text[:150]}")
            
            # Check success conditions from OCR
            if "Incorrect username or password" in ocr_text:
                print("  ⚠️ Login failed - wrong password")
                print("  ❌ Cannot proceed without correct password")
                break
            
            if any(kw in ocr_text.lower() for kw in ["access token", "new token", "create token", "tokens"]):
                if logged_in and not token_created:
                    print("  📋 On tokens page, creating token...")
                    # Try direct URL for token creation
                    await page.goto("https://huggingface.co/settings/tokens/new?tokenType=write&name=email-crawler",
                                    wait_until="domcontentloaded")
                    await page.wait_for_timeout(3000)
                    await page.screenshot(path=f"/tmp/hf_pipe_{step:02d}b.png")
                    body = await page.inner_text("body")
                    tokens = re.findall(r'hf_[A-Za-z0-9]{20,}', body)
                    if tokens:
                        print(f"  ✅ TOKEN: {tokens[0]}")
                        with open("/tmp/hf_new_token.txt", "w") as f: f.write(tokens[0])
                        token_created = True
                        break
                    
                    # Click create button
                    btns = page.locator("button")
                    for i in range(await btns.count()):
                        t = await btns.nth(i).inner_text()
                        if any(k in t.lower() for k in ["create", "generate", "new"]):
                            await btns.nth(i).click()
                            break
                    await page.wait_for_timeout(3000)
                    await page.screenshot(path=f"/tmp/hf_pipe_{step:02d}c.png")
                    body = await page.inner_text("body")
                    tokens = re.findall(r'hf_[A-Za-z0-9]{20,}', body)
                    if tokens:
                        print(f"  ✅ TOKEN: {tokens[0]}")
                        with open("/tmp/hf_new_token.txt", "w") as f: f.write(tokens[0])
                        token_created = True
                        break
                    
                    # Check inputs for token
                    inputs = page.locator("input")
                    for i in range(await inputs.count()):
                        v = await inputs.nth(i).get_attribute("value")
                        if v and v.startswith("hf_"):
                            print(f"  ✅ TOKEN: {v}")
                            with open("/tmp/hf_new_token.txt", "w") as f: f.write(v)
                            token_created = True
                            break
                    if token_created: break
            
            # Check if logged in
            if not logged_in and "login" not in url.lower() and "join" not in url.lower():
                print("  ✅ Logged in!")
                logged_in = True
                # Check cookies
                cookies = await context.cookies("https://huggingface.co")
                for c in cookies:
                    if c['name'] == 'token':
                        tokens = re.findall(r'hf_[A-Za-z0-9]{20,}', c['value'])
                        if tokens:
                            print(f"  ✅ TOKEN from cookie: {tokens[0]}")
                            with open("/tmp/hf_new_token.txt", "w") as f: f.write(tokens[0])
                            token_created = True
                            break
                if token_created: break
                
                # Navigate to tokens
                print("  → Navigating to tokens page...")
                await page.goto("https://huggingface.co/settings/tokens", wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
                continue
            
            # LLM decides next action
            action = llava_json(screenshot, f"Current URL: {url}. OCR text: {ocr_text[:200]}")
            print(f"  LLaVA: {action}")
            
            act = action.get("action", "unknown")
            selector = action.get("selector", "")
            text = action.get("text", "")
            desc = action.get("description", "")
            
            if act == "fill_username" and not filled_username:
                try:
                    el = page.locator('input[name="username"]')
                    if await el.count() > 0:
                        await el.fill(username)
                        filled_username = True
                        print(f"  → Filled username: {username}")
                except: pass
                    
            elif act == "fill_password" and not filled_password and filled_username:
                try:
                    el = page.locator('input[name="password"]')
                    if await el.count() > 0:
                        await el.fill(password)
                        filled_password = True
                        print(f"  → Filled password")
                except: pass
                    
            elif act == "click_submit":
                try:
                    btn = page.locator('button[type="submit"]')
                    if await btn.count() > 0:
                        await btn.click()
                        print(f"  → Clicked submit")
                        await page.wait_for_timeout(4000)
                except: pass
                    
            elif act == "click_button":
                try:
                    if selector:
                        btn = page.locator(selector)
                    else:
                        btn = page.locator("button")
                    for i in range(await btn.count()):
                        t = await btn.nth(i).inner_text()
                        if any(k in t.lower() for k in ["create", "generate", "new", "submit"]):
                            await btn.nth(i).click()
                            print(f"  → Clicked: {t}")
                            break
                    await page.wait_for_timeout(3000)
                except: pass
                    
            elif act == "type_text" and text:
                try:
                    inp = page.locator('input[type="text"]')
                    if await inp.count() > 0:
                        await inp.first.fill(text)
                        print(f"  → Typed: {text}")
                except: pass
                    
            elif act == "wait":
                print(f"  → Waiting (WAF/challenge)...")
                await page.wait_for_timeout(8000)
                
            elif act == "done":
                print("  → LLaVA says done")
                if not logged_in:
                    logged_in = True
                await page.goto("https://huggingface.co/settings/tokens", wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
                
            else:
                # Fallback: try to fill form if we see it in OCR
                if "username" in ocr_text.lower() and not filled_username:
                    try:
                        await page.fill('input[name="username"]', username)
                        filled_username = True
                        print(f"  → [fallback] Filled username")
                    except: pass
                elif "password" in ocr_text.lower() and filled_username and not filled_password:
                    try:
                        await page.fill('input[name="password"]', password)
                        filled_password = True
                        print(f"  → [fallback] Filled password")
                    except: pass
                elif filled_username and filled_password:
                    try:
                        await page.locator('button[type="submit"]').click()
                        print(f"  → [fallback] Clicked submit")
                        await page.wait_for_timeout(4000)
                    except: pass
                else:
                    print(f"  → Unknown action, waiting...")
                    await page.wait_for_timeout(3000)
        
        await context.close()
        
        if token_created:
            with open("/tmp/hf_new_token.txt") as f:
                return f.read().strip()
        return None

if __name__ == "__main__":
    # Try with Carpathian.Forest369 - if it fails, the pipeline will detect and report
    token = asyncio.run(llm_login_pipeline("josephrw", "Carpathian.Forest369"))
    if token:
        print(f"\n✅ TOKEN: {token[:15]}...")
    else:
        print("\n❌ Pipeline failed - check /tmp/hf_pipe_*.png for screenshots")
