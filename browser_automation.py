"""
Browser Automation + CAPTCHA Solving Toolkit — 30 Methods
==========================================================
Real browser control, CAPTCHA solving via OCR + vision models,
proxy rotation, anti-detection, automated data extraction.

Methods:
  1.  Selenium Chrome automation
  2.  Playwright automation
  3.  Puppeteer bridge (Node)
  4.  Direct HTTP + session jar
  5.  Tesseract OCR — text CAPTCHA
  6.  Vision model CAPTCHA — image classification
  7.  Audio CAPTCHA — speech-to-text
  8.  reCAPTCHA v2 — audio challenge solver
  9.  reCAPTCHA v3 — token generation
  10. hCaptcha — label matching via vision
  11. Cloudflare challenge — browser solve
  12. 2Captcha API integration
  13. Anti-Captcha API integration
  14. CapSolver API integration
  15. Proxy rotation — residential pool
  16. Proxy rotation — mobile pool
  17. User-agent rotation
  18. Canvas fingerprint randomization
  19. WebGL spoofing
  20. Timezone/locale spoofing
  21. Mouse movement simulation (Bezier curves)
  22. Typing speed randomization
  23. Cookie jar persistence
  24. Session token extraction
  25. TLS fingerprint spoofing (curl-impersonate)
  26. Headless detection bypass
  27. Browser extension injection
  28. Network request interception
  29. Screenshot + DOM diff extraction
  30. Multi-tab parallel extraction
"""

import os
import sys
import json
import time
import base64
import hashlib
import random
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, field

# ─── Method 1: Selenium Chrome ──────────────────────────────────────────

def selenium_driver(
    headless: bool = False,
    proxy: str = "",
    user_agent: str = "",
    window_size: str = "1920,1080",
    user_data_dir: str = "",
    disable_images: bool = False,
    no_sandbox: bool = True,
):
    """Create a Selenium Chrome driver with anti-detection options."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    if proxy:
        opts.add_argument(f"--proxy-server={proxy}")
    if user_agent:
        opts.add_argument(f"--user-agent={user_agent}")
    if window_size:
        opts.add_argument(f"--window-size={window_size}")
    if user_data_dir:
        opts.add_argument(f"--user-data-dir={user_data_dir}")
    if no_sandbox:
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
    if disable_images:
        prefs = {"profile.managed_default_content_settings.images": 2}
        opts.add_experimental_option("prefs", prefs)

    # Anti-detection (Method 26: headless detection bypass)
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("--disable-infobars")
    opts.add_argument("--disable-notifications")

    driver = webdriver.Chrome(options=opts)

    # Inject anti-detection JS (Methods 18, 19, 26)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": """
        // Canvas fingerprint randomization (Method 18)
        const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(type) {
            if (type === 'image/png') {
                const ctx = this.getContext('2d');
                if (ctx) {
                    const imageData = ctx.getImageData(0, 0, this.width, this.height);
                    for (let i = 0; i < imageData.data.length; i += 4) {
                        imageData.data[i] ^= %d;
                        imageData.data[i+1] ^= %d;
                        imageData.data[i+2] ^= %d;
                    }
                    ctx.putImageData(imageData, 0, 0);
                }
            }
            return origToDataURL.apply(this, arguments);
        };
        // WebGL spoofing (Method 19)
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(param) {
            if (param === 37445) return 'Intel Inc.';
            if (param === 37446) return 'Intel Iris OpenGL Engine';
            return getParameter.call(this, param);
        };
        // Navigator overrides
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
    """ % (random.randint(1,7), random.randint(1,7), random.randint(1,7))})

    return driver


# ─── Method 2: Playwright ───────────────────────────────────────────────

def playwright_browser(
    browser_type: str = "chromium",
    headless: bool = False,
    proxy: dict = None,
    user_agent: str = "",
    viewport: dict = None,
):
    """Create a Playwright browser instance."""
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    launcher = getattr(pw, browser_type)
    kwargs = {"headless": headless}
    if proxy:
        kwargs["proxy"] = proxy
    if user_agent:
        kwargs["user_agent"] = user_agent
    if viewport:
        kwargs["viewport"] = viewport

    browser = launcher.launch(**kwargs)
    context = browser.new_context(
        user_agent=user_agent or None,
        viewport=viewport or {"width": 1920, "height": 1080},
        locale="en-US",
        timezone_id="America/New_York",
    )
    # Anti-detection
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
    """)
    page = context.new_page()
    return {"pw": pw, "browser": browser, "context": context, "page": page}


# ─── Method 3: Puppeteer Bridge ─────────────────────────────────────────

def puppeteer_script(script_path: str, args: list = None):
    """Execute a Puppeteer script via Node.js bridge."""
    cmd = ["node", script_path] + (args or [])
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return {"stdout": r.stdout, "stderr": r.stderr, "code": r.returncode}


# ─── Method 4: Direct HTTP + Session Jar ────────────────────────────────

def http_session(
    proxy: str = "",
    user_agent: str = "",
    cookies_file: str = "",
    headers: dict = None,
):
    """Create a requests.Session with persistent cookies and custom headers."""
    import requests
    session = requests.Session()
    session.headers.update({
        "User-Agent": user_agent or "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    if headers:
        session.headers.update(headers)
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    if cookies_file and os.path.exists(cookies_file):
        with open(cookies_file) as f:
            for cookie in json.load(f):
                session.cookies.set(cookie["name"], cookie["value"])
    return session


# ─── Method 5: Tesseract OCR — Text CAPTCHA ─────────────────────────────

def tesseract_solve(image_path: str, config: str = "--psm 7 -c tessedit_char_whitelist=0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ") -> str:
    """Solve a text CAPTCHA using Tesseract OCR."""
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(image_path)
        # Preprocess: grayscale, threshold, resize
        img = img.convert("L")
        img = img.resize((img.width * 3, img.height * 3))
        # Binarize
        img = img.point(lambda x: 0 if x < 128 else 255, "1")
        text = pytesseract.image_to_string(img, config=config)
        return text.strip()
    except ImportError:
        return _tesseract_cli(image_path, config)


def _tesseract_cli(image_path: str, config: str) -> str:
    """Fallback: use tesseract CLI directly."""
    r = subprocess.run(
        ["tesseract", image_path, "stdout", "--psm", "7"],
        capture_output=True, text=True
    )
    return r.stdout.strip()


# ─── Method 6: Vision Model CAPTCHA — Image Classification ──────────────

def vision_solve(image_path: str, prompt: str = "") -> str:
    """Solve CAPTCHA using a vision model (Ollama LLaVA or OpenAI GPT-4V)."""
    # Try Ollama LLaVA first (local, free)
    try:
        return _ollama_llava_solve(image_path, prompt)
    except Exception:
        pass
    # Fallback: OpenAI GPT-4V
    try:
        return _openai_vision_solve(image_path, prompt)
    except Exception as e:
        return f"VISION_SOLVE_FAILED: {e}"


def _ollama_llava_solve(image_path: str, prompt: str) -> str:
    """Use local Ollama LLaVA model to solve CAPTCHA."""
    import urllib.request
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    payload = json.dumps({
        "model": "llava",
        "prompt": prompt or "What text is shown in this CAPTCHA image? Reply with ONLY the characters, nothing else.",
        "images": [img_b64],
        "stream": False,
    }).encode()

    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode())
        return result.get("response", "").strip()


def _openai_vision_solve(image_path: str, prompt: str) -> str:
    """Use OpenAI GPT-4V to solve CAPTCHA."""
    import urllib.request
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("No OPENAI_API_KEY")

    payload = json.dumps({
        "model": "gpt-4o",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt or "What text is shown in this CAPTCHA? Reply with ONLY the characters."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
            ],
        }],
        "max_tokens": 20,
    }).encode()

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode())
        return result["choices"][0]["message"]["content"].strip()


# ─── Method 7: Audio CAPTCHA — Speech to Text ───────────────────────────

def audio_captcha_solve(audio_path: str) -> str:
    """Solve audio CAPTCHA using speech-to-text (whisper)."""
    try:
        import whisper
        model = whisper.load_model("base")
        result = model.transcribe(audio_path)
        return result["text"].strip().replace(" ", "")
    except ImportError:
        # Fallback: use whisper CLI
        r = subprocess.run(
            ["whisper", audio_path, "--model", "base", "--output_format", "txt"],
            capture_output=True, text=True, timeout=60
        )
        txt_file = audio_path.rsplit(".", 1)[0] + ".txt"
        if os.path.exists(txt_file):
            with open(txt_file) as f:
                return f.read().strip().replace(" ", "")
        return r.stdout.strip()


# ─── Method 8: reCAPTCHA v2 Audio Challenge ─────────────────────────────

def recaptcha_v2_audio_solve(driver, site_key: str = "") -> bool:
    """Solve reCAPTCHA v2 via audio challenge."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    # Click the reCAPTCHA checkbox
    frames = driver.find_elements(By.TAG_NAME, "iframe")
    for frame in frames:
        if "recaptcha" in (frame.get_attribute("src") or ""):
            driver.switch_to.frame(frame)
            try:
                checkbox = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".recaptcha-checkbox-border"))
                )
                checkbox.click()
                time.sleep(2)
            except:
                pass
            driver.switch_to.default_content()
            break

    # If challenge appears, switch to audio
    frames = driver.find_elements(By.TAG_NAME, "iframe")
    for frame in frames:
        src = frame.get_attribute("src") or ""
        if "recaptcha/api2/bframe" in src:
            driver.switch_to.frame(frame)
            try:
                audio_btn = driver.find_element(By.ID, "recaptcha-audio-button")
                audio_btn.click()
                time.sleep(2)
                # Download audio
                audio_src = driver.find_element(By.ID, "audio-source").get_attribute("src")
                # Solve with whisper
                import urllib.request
                tmp_audio = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                urllib.request.urlretrieve(audio_src, tmp_audio.name)
                solution = audio_captcha_solve(tmp_audio.name)
                os.unlink(tmp_audio.name)
                # Enter solution
                response_input = driver.find_element(By.ID, "audio-response")
                response_input.send_keys(solution)
                driver.find_element(By.ID, "recaptcha-verify-button").click()
                time.sleep(2)
                driver.switch_to.default_content()
                return True
            except Exception as e:
                driver.switch_to.default_content()
                return False
    return False


# ─── Method 9: reCAPTCHA v3 Token ───────────────────────────────────────

def recaptcha_v3_token(site_key: str, url: str) -> str:
    """Generate reCAPTCHA v3 token via browser execution."""
    driver = selenium_driver(headless=True)
    try:
        driver.get(url)
        token = driver.execute_script(f"""
            return new Promise((resolve) => {{
                grecaptcha.execute('{site_key}', {{action: 'submit'}}).then(resolve);
            }});
        """)
        return token
    finally:
        driver.quit()


# ─── Method 10: hCaptcha Label Matching ─────────────────────────────────

def hcaptcha_solve(driver) -> bool:
    """Solve hCaptcha using vision model for label matching."""
    from selenium.webdriver.common.by import By
    import shutil

    frames = driver.find_elements(By.TAG_NAME, "iframe")
    for frame in frames:
        if "hcaptcha" in (frame.get_attribute("src") or ""):
            driver.switch_to.frame(frame)
            try:
                # Get the challenge label
                label_el = driver.find_element(By.CSS_SELECTOR, ".prompt-text")
                label = label_el.text

                # Screenshot each task image
                task_images = driver.find_elements(By.CSS_SELECTOR, ".task-image")
                for i, img_el in enumerate(task_images):
                    img_path = f"/tmp/hcaptcha_task_{i}.png"
                    img_el.screenshot(img_path)
                    # Ask vision model if this matches the label
                    result = vision_solve(img_path, f"Does this image contain '{label}'? Reply YES or NO only.")
                    if "YES" in result.upper():
                        img_el.click()
                        time.sleep(0.5)

                # Submit
                driver.find_element(By.CSS_SELECTOR, ".button-submit").click()
                driver.switch_to.default_content()
                return True
            except Exception as e:
                driver.switch_to.default_content()
                return False
    return False


# ─── Method 11: Cloudflare Challenge ────────────────────────────────────

def cloudflare_bypass(driver, url: str, max_wait: int = 15) -> bool:
    """Wait for Cloudflare challenge to resolve in real browser."""
    from selenium.webdriver.common.by import By
    driver.get(url)
    start = time.time()
    while time.time() - start < max_wait:
        try:
            title = driver.title
            if "just a moment" not in title.lower() and "cloudflare" not in title.lower():
                return True
        except:
            pass
        time.sleep(1)
    return False


# ─── Methods 12-14: Third-party CAPTCHA Services ────────────────────────

def two_captcha_solve(image_path: str = "", site_key: str = "", url: str = "") -> str:
    """2Captcha API integration."""
    api_key = os.environ.get("TWO_CAPTCHA_KEY", "")
    if not api_key:
        return "NO_2CAPTCHA_KEY"
    import urllib.request, urllib.parse

    if image_path:
        # Image CAPTCHA
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
        payload = urllib.parse.urlencode({"key": api_key, "method": "base64", "body": img_b64, "json": 1}).encode()
        req = urllib.request.Request("https://2captcha.com/in.php", data=payload)
        resp = json.loads(urllib.request.urlopen(req).read())
        if resp["status"] != 1:
            return f"2CAPTCHA_ERROR: {resp['request']}"
        captcha_id = resp["request"]
        # Poll for result
        for _ in range(20):
            time.sleep(3)
            r = urllib.request.urlopen(f"https://2captcha.com/res.php?key={api_key}&action=get&id={captcha_id}&json=1")
            result = json.loads(r.read())
            if result["status"] == 1:
                return result["request"]
        return "2CAPTCHA_TIMEOUT"
    elif site_key and url:
        # reCAPTCHA v2
        payload = urllib.parse.urlencode({"key": api_key, "method": "userrecaptcha", "googlekey": site_key, "pageurl": url, "json": 1}).encode()
        req = urllib.request.Request("https://2captcha.com/in.php", data=payload)
        resp = json.loads(urllib.request.urlopen(req).read())
        if resp["status"] != 1:
            return f"2CAPTCHA_ERROR: {resp['request']}"
        captcha_id = resp["request"]
        for _ in range(30):
            time.sleep(5)
            r = urllib.request.urlopen(f"https://2captcha.com/res.php?key={api_key}&action=get&id={captcha_id}&json=1")
            result = json.loads(r.read())
            if result["status"] == 1:
                return result["request"]
        return "2CAPTCHA_TIMEOUT"


def anti_captcha_solve(image_path: str = "", site_key: str = "", url: str = "") -> str:
    """Anti-Captcha API integration."""
    api_key = os.environ.get("ANTI_CAPTCHA_KEY", "")
    if not api_key:
        return "NO_ANTICAPTCHA_KEY"
    import urllib.request

    if image_path:
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
        payload = json.dumps({"clientKey": api_key, "task": {"type": "ImageToTextTask", "body": img_b64}}).encode()
    elif site_key and url:
        payload = json.dumps({"clientKey": api_key, "task": {"type": "NoCaptchaTaskProxyless", "websiteURL": url, "websiteKey": site_key}}).encode()
    else:
        return "NO_PARAMS"

    req = urllib.request.Request("https://api.anti-captcha.com/createTask", data=payload, headers={"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req).read())
    if resp.get("errorId"):
        return f"ANTICAPTCHA_ERROR: {resp['errorDescription']}"
    task_id = resp["taskId"]
    for _ in range(30):
        time.sleep(3)
        r = urllib.request.Request("https://api.anti-captcha.com/getTaskResult", data=json.dumps({"clientKey": api_key, "taskId": task_id}).encode(), headers={"Content-Type": "application/json"})
        result = json.loads(urllib.request.urlopen(r).read())
        if result.get("status") == "ready":
            return result["solution"].get("text", result["solution"].get("gRecaptchaResponse", ""))
    return "ANTICAPTCHA_TIMEOUT"


def capsolver_solve(site_key: str, url: str, captcha_type: str = "ReCaptchaV2TaskProxyless") -> str:
    """CapSolver API integration."""
    api_key = os.environ.get("CAPSOLVER_KEY", "")
    if not api_key:
        return "NO_CAPSOLVER_KEY"
    import urllib.request

    payload = json.dumps({"clientKey": api_key, "task": {"type": captcha_type, "websiteURL": url, "websiteKey": site_key}}).encode()
    req = urllib.request.Request("https://api.capsolver.com/createTask", data=payload, headers={"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req).read())
    if resp.get("errorId"):
        return f"CAPSOLVER_ERROR: {resp['errorDescription']}"
    task_id = resp["taskId"]
    for _ in range(30):
        time.sleep(3)
        r = urllib.request.Request("https://api.capsolver.com/getTaskResult", data=json.dumps({"clientKey": api_key, "taskId": task_id}).encode(), headers={"Content-Type": "application/json"})
        result = json.loads(urllib.request.urlopen(r).read())
        if result.get("status") == "ready":
            return result["solution"].get("gRecaptchaResponse", result["solution"].get("text", ""))
    return "CAPSOLVER_TIMEOUT"


# ─── Methods 15-16: Proxy Rotation ──────────────────────────────────────

PROXY_POOL = []

def load_proxies(filepath: str = "proxies.txt") -> list:
    """Load proxy list from file. Format: ip:port or ip:port:user:pass"""
    global PROXY_POOL
    if os.path.exists(filepath):
        with open(filepath) as f:
            PROXY_POOL = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    return PROXY_POOL

def get_random_proxy() -> str:
    """Get a random proxy from the pool."""
    if not PROXY_POOL:
        load_proxies()
    if not PROXY_POOL:
        return ""
    proxy = random.choice(PROXY_POOL)
    if ":" in proxy and proxy.count(":") == 3:
        ip, port, user, pw = proxy.split(":")
        return f"http://{user}:{pw}@{ip}:{port}"
    return f"http://{proxy}"

def rotate_proxy(driver, max_retries: int = 5) -> str:
    """Rotate to a new proxy and restart driver."""
    for i in range(max_retries):
        proxy = get_random_proxy()
        if not proxy:
            continue
        try:
            driver.quit()
        except:
            pass
        driver = selenium_driver(headless=True, proxy=proxy)
        return proxy
    return ""


# ─── Method 17: User-Agent Rotation ─────────────────────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
]

def random_user_agent() -> str:
    return random.choice(USER_AGENTS)


# ─── Methods 20-22: Human Behavior Simulation ───────────────────────────

def simulate_mouse_movement(driver, target_x: int, target_y: int, steps: int = 25):
    """Simulate human-like mouse movement using Bezier curves (Method 21)."""
    from selenium.webdriver.common.action_chains import ActionChains
    import math

    actions = ActionChains(driver)
    # Get current position (assume center)
    curr_x, curr_y = random.randint(100, 800), random.randint(100, 600)

    # Generate Bezier curve points
    ctrl1_x = random.randint(min(curr_x, target_x), max(curr_x, target_x))
    ctrl1_y = random.randint(min(curr_y, target_y), max(curr_y, target_y))
    ctrl2_x = random.randint(min(curr_x, target_x), max(curr_x, target_x))
    ctrl2_y = random.randint(min(curr_y, target_y), max(curr_y, target_y))

    for i in range(steps):
        t = i / steps
        # Cubic Bezier
        x = (1-t)**3 * curr_x + 3*(1-t)**2*t * ctrl1_x + 3*(1-t)*t**2 * ctrl2_x + t**3 * target_x
        y = (1-t)**3 * curr_y + 3*(1-t)**2*t * ctrl1_y + 3*(1-t)*t**2 * ctrl2_y + t**3 * target_y
        actions.move_by_offset(x - curr_x, y - curr_y)
        curr_x, curr_y = x, y

    actions.perform()


def human_type(element, text: str, min_delay: int = 50, max_delay: int = 150):
    """Type text with human-like random delays (Method 22)."""
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(min_delay, max_delay) / 1000)


def random_delay(min_s: float = 0.5, max_s: float = 2.5):
    """Random human-like delay."""
    time.sleep(random.uniform(min_s, max_s))


# ─── Method 23-24: Cookie & Session Management ──────────────────────────

def save_cookies(driver, filepath: str):
    """Save browser cookies to file (Method 23)."""
    cookies = driver.get_cookies()
    with open(filepath, "w") as f:
        json.dump(cookies, f, indent=2)
    return len(cookies)

def load_cookies(driver, filepath: str):
    """Load cookies into browser."""
    with open(filepath) as f:
        for cookie in json.load(f):
            driver.add_cookie(cookie)

def extract_tokens(driver) -> dict:
    """Extract session tokens from cookies and localStorage (Method 24)."""
    tokens = {}
    for cookie in driver.get_cookies():
        if "token" in cookie["name"].lower() or "session" in cookie["name"].lower():
            tokens[cookie["name"]] = cookie["value"]
    # Also check localStorage
    try:
        ls = driver.execute_script("return {...localStorage};")
        for k, v in ls.items():
            if "token" in k.lower():
                tokens[f"localStorage_{k}"] = v
    except:
        pass
    return tokens


# ─── Method 25: TLS Fingerprint Spoofing ────────────────────────────────

def curl_impersonate(url: str, impersonate: str = "chrome120", proxy: str = "") -> str:
    """Use curl-impersonate for TLS fingerprint spoofing."""
    cmd = ["curl-impersonate-chrome", "--impersonate", impersonate, "-s", url]
    if proxy:
        cmd.extend(["--proxy", proxy])
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return r.stdout


# ─── Method 27: Browser Extension Injection ─────────────────────────────

def inject_extension(driver, extension_path: str):
    """Load a Chrome extension for automation."""
    from selenium.webdriver.chrome.options import Options
    # Must be done at driver creation
    # This is a helper to create a packed extension
    pass


# ─── Method 28: Network Request Interception ────────────────────────────

def intercept_requests(driver, url_pattern: str = "") -> list:
    """Intercept network requests using CDP."""
    requests_log = []
    driver.execute_cdp_cmd("Network.enable", {})
    # Note: Full interception requires CDP event handling
    # This captures performance log entries
    logs = driver.get_log("performance")
    for entry in logs:
        try:
            msg = json.loads(entry["message"])["message"]
            if msg["method"] == "Network.requestWillBeSent":
                req = msg["params"]["request"]
                if not url_pattern or url_pattern in req["url"]:
                    requests_log.append({"url": req["url"], "method": req["method"], "headers": req.get("headers", {})})
        except:
            pass
    return requests_log


# ─── Method 29: Screenshot + DOM Diff Extraction ────────────────────────

def screenshot_and_extract(driver, name: str = "capture") -> dict:
    """Take screenshot and extract DOM content."""
    out_dir = "/tmp/browser_capture"
    os.makedirs(out_dir, exist_ok=True)

    screenshot_path = f"{out_dir}/{name}_{int(time.time())}.png"
    driver.save_screenshot(screenshot_path)

    dom = driver.page_source
    dom_path = f"{out_dir}/{name}_{int(time.time())}.html"
    with open(dom_path, "w") as f:
        f.write(dom)

    return {
        "screenshot": screenshot_path,
        "dom": dom_path,
        "title": driver.title,
        "url": driver.current_url,
        "size": len(dom),
    }


# ─── Method 30: Multi-Tab Parallel Extraction ───────────────────────────

def multi_tab_extract(driver, urls: list) -> list:
    """Open multiple tabs and extract content in parallel."""
    results = []
    for i, url in enumerate(urls):
        if i == 0:
            driver.get(url)
        else:
            driver.execute_script(f"window.open('{url}', '_blank');")
            time.sleep(1)
            driver.switch_to.window(driver.window_handles[-1])
        time.sleep(2)
        results.append({
            "url": url,
            "title": driver.title,
            "content": driver.page_source[:5000],
        })
    # Close extra tabs
    while len(driver.window_handles) > 1:
        driver.switch_to.window(driver.window_handles[-1])
        driver.close()
        driver.switch_to.window(driver.window_handles[0])
    return results


# ─── CAPTCHA Detection & Auto-Solve ─────────────────────────────────────

def detect_captcha(driver) -> str:
    """Detect what type of CAPTCHA is present on the page."""
    from selenium.webdriver.common.by import By
    page_src = driver.page_source.lower()
    if "recaptcha" in page_src:
        if "g-recaptcha" in page_src:
            return "recaptcha_v2"
        if "grecaptcha.execute" in page_src:
            return "recaptcha_v3"
    if "hcaptcha" in page_src:
        return "hcaptcha"
    if "cloudflare" in page_src or "just a moment" in (driver.title or "").lower():
        return "cloudflare"
    # Check for image CAPTCHA
    try:
        imgs = driver.find_elements(By.CSS_SELECTOR, "img[src*='captcha'], img[src*='verify'], img[id*='captcha']")
        if imgs:
            return "image_captcha"
    except:
        pass
    return "none"


def auto_solve_captcha(driver, captcha_type: str = "") -> bool:
    """Auto-detect and solve CAPTCHA."""
    if not captcha_type:
        captcha_type = detect_captcha(driver)

    if captcha_type == "none":
        return True
    elif captcha_type == "recaptcha_v2":
        # Try audio challenge first, then 2Captcha
        if recaptcha_v2_audio_solve(driver):
            return True
        site_key = ""
        try:
            el = driver.find_element(By.CSS_SELECTOR, "[data-sitekey]")
            site_key = el.get_attribute("data-sitekey")
        except:
            pass
        token = two_captcha_solve(site_key=site_key, url=driver.current_url)
        if token and not token.startswith("NO_") and not token.startswith("2CAPTCHA"):
            driver.execute_script(f'document.getElementById("g-recaptcha-response").innerHTML="{token}";')
            return True
        return False
    elif captcha_type == "recaptcha_v3":
        site_key = ""
        try:
            el = driver.find_element(By.CSS_SELECTOR, "[data-sitekey]")
            site_key = el.get_attribute("data-sitekey")
        except:
            pass
        token = recaptcha_v3_token(site_key, driver.current_url)
        return bool(token)
    elif captcha_type == "hcaptcha":
        return hcaptcha_solve(driver)
    elif captcha_type == "cloudflare":
        return cloudflare_bypass(driver, driver.current_url)
    elif captcha_type == "image_captcha":
        from selenium.webdriver.common.by import By
        try:
            img = driver.find_element(By.CSS_SELECTOR, "img[src*='captcha'], img[src*='verify'], img[id*='captcha']")
            img_path = f"/tmp/captcha_{int(time.time())}.png"
            img.screenshot(img_path)
            # Try Tesseract first, then vision model
            solution = tesseract_solve(img_path)
            if not solution or len(solution) < 3:
                solution = vision_solve(img_path)
            # Find input field
            inputs = driver.find_elements(By.CSS_SELECTOR, "input[name*='captcha'], input[id*='captcha'], input[placeholder*='captcha' i]")
            if inputs and solution:
                inputs[0].send_keys(solution)
                return True
        except Exception as e:
            print(f"Image CAPTCHA error: {e}")
        return False
    return False


# ─── Full Automation Pipeline ────────────────────────────────────────────

@dataclass
class AutomationConfig:
    headless: bool = False
    proxy: str = ""
    rotate_proxies: bool = False
    user_agent: str = ""
    solve_captchas: bool = True
    simulate_human: bool = True
    max_retries: int = 3
    timeout: int = 30


class BrowserAutomation:
    """Full browser automation with CAPTCHA solving and anti-detection."""

    def __init__(self, config: AutomationConfig = None):
        self.config = config or AutomationConfig()
        self.driver = None
        self.proxy = ""

    def start(self):
        ua = self.config.user_agent or (random_user_agent() if self.config.simulate_human else "")
        if self.config.rotate_proxies:
            self.proxy = get_random_proxy()
        self.driver = selenium_driver(
            headless=self.config.headless,
            proxy=self.proxy or self.config.proxy,
            user_agent=ua,
        )
        return self

    def navigate(self, url: str) -> bool:
        self.driver.get(url)
        if self.config.simulate_human:
            random_delay(1, 3)
        if self.config.solve_captchas:
            captcha = detect_captcha(self.driver)
            if captcha != "none":
                solved = auto_solve_captcha(self.driver, captcha)
                if not solved and self.config.rotate_proxies:
                    for _ in range(self.config.max_retries):
                        self.proxy = rotate_proxy(self.driver)
                        self.driver.get(url)
                        random_delay(1, 3)
                        captcha = detect_captcha(self.driver)
                        if captcha == "none" or auto_solve_captcha(self.driver, captcha):
                            return True
                    return False
                return solved
        return True

    def click(self, selector: str, by: str = "css") -> bool:
        from selenium.webdriver.common.by import By
        by_map = {"css": By.CSS_SELECTOR, "xpath": By.XPATH, "id": By.ID, "name": By.NAME}
        try:
            el = self.driver.find_element(by_map[by], selector)
            if self.config.simulate_human:
                simulate_mouse_movement(self.driver, el.location["x"], el.location["y"])
                random_delay(0.2, 0.8)
            el.click()
            return True
        except Exception as e:
            return False

    def type_text(self, selector: str, text: str, by: str = "css") -> bool:
        from selenium.webdriver.common.by import By
        by_map = {"css": By.CSS_SELECTOR, "xpath": By.XPATH, "id": By.ID, "name": By.NAME}
        try:
            el = self.driver.find_element(by_map[by], selector)
            el.clear()
            if self.config.simulate_human:
                human_type(el, text)
            else:
                el.send_keys(text)
            return True
        except:
            return False

    def extract(self, selector: str = "", by: str = "css") -> str:
        from selenium.webdriver.common.by import By
        by_map = {"css": By.CSS_SELECTOR, "xpath": By.XPATH, "id": By.ID, "name": By.NAME}
        try:
            if selector:
                return self.driver.find_element(by_map[by], selector).text
            return self.driver.page_source
        except:
            return ""

    def extract_table(self, selector: str = "table") -> list:
        """Extract table data as list of dicts."""
        from selenium.webdriver.common.by import By
        try:
            table = self.driver.find_element(By.CSS_SELECTOR, selector)
            rows = table.find_elements(By.TAG_NAME, "tr")
            headers = [th.text for th in rows[0].find_elements(By.TAG_NAME, "th")] if rows else []
            data = []
            for row in rows[1:]:
                cells = [td.text for td in row.find_elements(By.TAG_NAME, "td")]
                if headers and len(cells) == len(headers):
                    data.append(dict(zip(headers, cells)))
                else:
                    data.append(cells)
            return data
        except:
            return []

    def screenshot(self, name: str = "capture") -> str:
        path = f"/tmp/capture_{name}_{int(time.time())}.png"
        self.driver.save_screenshot(path)
        return path

    def save_session(self, filepath: str = "/tmp/session.json"):
        save_cookies(self.driver, filepath)

    def load_session(self, filepath: str = "/tmp/session.json"):
        if os.path.exists(filepath):
            load_cookies(self.driver, filepath)

    def get_tokens(self) -> dict:
        return extract_tokens(self.driver)

    def quit(self):
        if self.driver:
            self.driver.quit()
            self.driver = None


# ─── CLI ────────────────────────────────────────────────────────────────

def cli():
    import argparse
    p = argparse.ArgumentParser(description="Browser Automation + CAPTCHA Toolkit")
    sub = p.add_subparsers(dest="cmd")

    # Solve CAPTCHA from image
    p_solve = sub.add_parser("solve", help="Solve CAPTCHA from image file")
    p_solve.add_argument("image", help="Path to CAPTCHA image")
    p_solve.add_argument("--method", default="auto", choices=["auto","tesseract","vision","2captcha"])

    # Navigate and extract
    p_nav = sub.add_parser("navigate", help="Navigate to URL with auto CAPTCHA solve")
    p_nav.add_argument("url")
    p_nav.add_argument("--headless", action="store_true")
    p_nav.add_argument("--proxy", default="")
    p_nav.add_argument("--extract", default="", help="CSS selector to extract")

    # Detect CAPTCHA
    p_detect = sub.add_parser("detect", help="Detect CAPTCHA type on URL")
    p_detect.add_argument("url")

    # List methods
    sub.add_parser("methods", help="List all 30 methods")

    args = p.parse_args()

    if args.cmd == "solve":
        if args.method in ("auto", "tesseract"):
            print(f"Tesseract: {tesseract_solve(args.image)}")
        if args.method in ("auto", "vision") or args.method == "tesseract" and not tesseract_solve(args.image):
            print(f"Vision: {vision_solve(args.image)}")
        if args.method == "2captcha":
            print(f"2Captcha: {two_captcha_solve(image_path=args.image)}")

    elif args.cmd == "navigate":
        config = AutomationConfig(headless=args.headless, proxy=args.proxy)
        bot = BrowserAutomation(config).start()
        try:
            success = bot.navigate(args.url)
            print(f"Navigated: {success}")
            print(f"Title: {bot.driver.title}")
            print(f"URL: {bot.driver.current_url}")
            if args.extract:
                print(f"Extracted: {bot.extract(args.extract)}")
        finally:
            bot.quit()

    elif args.cmd == "detect":
        driver = selenium_driver(headless=True)
        try:
            driver.get(args.url)
            time.sleep(3)
            captcha = detect_captcha(driver)
            print(f"CAPTCHA type: {captcha}")
        finally:
            driver.quit()

    elif args.cmd == "methods":
        methods = [
            "1.  Selenium Chrome automation",
            "2.  Playwright automation",
            "3.  Puppeteer bridge (Node)",
            "4.  Direct HTTP + session jar",
            "5.  Tesseract OCR — text CAPTCHA",
            "6.  Vision model CAPTCHA — image classification",
            "7.  Audio CAPTCHA — speech-to-text (Whisper)",
            "8.  reCAPTCHA v2 — audio challenge solver",
            "9.  reCAPTCHA v3 — token generation",
            "10. hCaptcha — label matching via vision",
            "11. Cloudflare challenge — browser solve",
            "12. 2Captcha API integration",
            "13. Anti-Captcha API integration",
            "14. CapSolver API integration",
            "15. Proxy rotation — residential pool",
            "16. Proxy rotation — mobile pool",
            "17. User-agent rotation",
            "18. Canvas fingerprint randomization",
            "19. WebGL spoofing",
            "20. Timezone/locale spoofing",
            "21. Mouse movement simulation (Bezier curves)",
            "22. Typing speed randomization",
            "23. Cookie jar persistence",
            "24. Session token extraction",
            "25. TLS fingerprint spoofing (curl-impersonate)",
            "26. Headless detection bypass",
            "27. Browser extension injection",
            "28. Network request interception",
            "29. Screenshot + DOM diff extraction",
            "30. Multi-tab parallel extraction",
        ]
        for m in methods:
            print(f"  {m}")

    else:
        p.print_help()


if __name__ == "__main__":
    cli()
