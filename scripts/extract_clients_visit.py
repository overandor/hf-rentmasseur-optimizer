#!/usr/bin/env python3
"""
RentMasseur Client Extraction + Visit — 3 Methods, Verified, Proven.

3 EXTRACTION METHODS:
  1. WhoSawMe API  — /api/v1/settings/whosawme?page=N (clients who viewed you)
  2. Mailbox API   — /api/v1/mailbox?page=N (clients who messaged you)
  3. Reviews API   — /api/v1/account/reviews (clients who reviewed you)

VERIFICATION:
  - Deduplicate across all 3 methods
  - Verify each username resolves to a real profile (HTTP HEAD/GET)
  - Tag each client with extraction source(s)

PROOF OF VISIT:
  - Browser visit via Playwright/Puppeteer/Selenium (auto-fallback)
  - Screenshot saved per client
  - Page title + URL + timestamp captured
  - SHA-256 hash of screenshot for tamper-evidence
  - JSON receipt with full audit trail

Usage:
    python3 scripts/extract_clients_visit.py
    python3 scripts/extract_clients_visit.py --dry-run
    python3 scripts/extract_clients_visit.py --engine playwright
    python3 scripts/extract_clients_visit.py --headless
    python3 scripts/extract_clients_visit.py --visit-only
"""
import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://rentmasseur.com"
API = f"{BASE}/api/v1"
USERNAME = os.getenv("RENTMASSEUR_USERNAME", "karpathianwolf")
PASSWORD = os.getenv("RENTMASSEUR_PASSWORD", os.environ.get("RM_PASSWORD", ""))
PHONE = os.getenv("WOLF_PHONE", "347-453-5129")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RECEIPTS_DIR = Path(__file__).resolve().parent.parent / "receipts"
PROOF_DIR = Path(__file__).resolve().parent.parent / "receipts" / "visit_proofs"
PROFILE_DIR = "/tmp/rm_client_extract"

DEFAULT_MESSAGE = (
    f"Hey! Thanks for checking out my profile. "
    f"I'm available today — feel free to text me at {PHONE}. "
    f"Happy to set something up."
)

SKIP_USERNAMES = {
    "settings", "gay-massage", "stream", "masseurcams", "advertise",
    "about", "login", "sitemap", "topics", "robots", "api", "build-stream",
    "terms", "privacy", "contact", "help", "blog", "blogs", "search",
    "register", "signup", "forgot-password", "reset-password",
}


# ─── Utilities ────────────────────────────────────────────────────────────────

def write_receipt(action, data, success=True):
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
    receipt = {
        "action": action,
        "success": success,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **data,
    }
    rpath = RECEIPTS_DIR / f"{action}_{ts}.json"
    rpath.write_text(json.dumps(receipt, indent=2))
    return str(rpath)


def save_data(filename, payload):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / filename).write_text(json.dumps(payload, indent=2))


def file_sha256(filepath):
    """Compute SHA-256 hash of a file for tamper-evidence."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def load_saved_clients():
    p = DATA_DIR / "clients_extracted.json"
    if p.exists():
        return json.loads(p.read_text())
    return None


# ─── API Login ────────────────────────────────────────────────────────────────

def api_login():
    """Login via API and return an authenticated requests session.
    
    Falls back to browser-assisted login if CrowdSec blocks direct API login.
    """
    import requests

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": f"{BASE}/settings",
        "Origin": BASE,
    })

    r = s.get(f"{BASE}/login")
    m = re.search(r'csrf["\s:=]+([A-Za-z0-9+/=]{20,})', r.text)
    csrf = m.group(1) if m else ""

    for attempt in range(3):
        r = s.post(f"{API}/login", json={
            "email": USERNAME, "password": PASSWORD, "csrf": csrf, "remember": True
        })
        if r.status_code != 200:
            print(f"  API login attempt {attempt+1}: HTTP {r.status_code}")
            time.sleep(3)
            r2 = s.get(f"{BASE}/login")
            m = re.search(r'csrf["\s:=]+([A-Za-z0-9+/=]{20,})', r2.text)
            csrf = m.group(1) if m else csrf
            continue
        try:
            token = r.json().get("accessToken", "")
        except Exception:
            print(f"  API login attempt {attempt+1}: captcha blocking direct API login")
            time.sleep(5)
            r2 = s.get(f"{BASE}/login")
            m = re.search(r'csrf["\s:=]+([A-Za-z0-9+/=]{20,})', r2.text)
            csrf = m.group(1) if m else csrf
            continue
        if not token:
            print("  No accessToken in login response")
            continue
        s.headers["Authorization"] = f"Bearer {token}"
        print("  API login OK")
        return s

    # Fallback: browser-assisted login (Playwright bypasses CrowdSec)
    print("  API login blocked by CrowdSec. Trying browser-assisted login...")
    return browser_login(s)


def browser_login(api_session):
    """Use undetected-chromedriver to login (bypasses CrowdSec automatically),
    extract token + cookies, inject into requests session."""
    try:
        import undetected_chromedriver as uc
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
    except ImportError:
        print("  undetected-chromedriver not installed. Cannot do browser login.")
        return None

    print("  [BROWSER LOGIN] Launching undetected-chromedriver (auto-bypasses CrowdSec)...")
    os.makedirs(PROFILE_DIR, exist_ok=True)
    opts = uc.ChromeOptions()
    opts.add_argument("--window-size=1280,900")
    opts.add_argument(f"--user-data-dir={PROFILE_DIR}")
    opts.add_argument("--disable-blink-features=AutomationControlled")

    driver = uc.Chrome(options=opts, version_main=149)

    try:
        driver.get(f"{BASE}/login")
        time.sleep(5)

        # undetected-chromedriver usually bypasses CrowdSec automatically
        # Wait for password field to appear (up to 60s)
        pwd = None
        for _ in range(30):
            try:
                src = driver.page_source or ""
                if "crowdsec" in src.lower() or "captcha" in src.lower():
                    time.sleep(3)
                    continue
                elements = driver.find_elements(By.CSS_SELECTOR, 'input[type="password"]')
                if elements and elements[0].is_displayed():
                    pwd = elements[0]
                    break
            except Exception:
                pass
            time.sleep(2)

        if not pwd:
            print("  No password field (captcha not bypassed). Aborting.")
            driver.quit()
            return None

        print("  Captcha bypassed. Filling login form...")

        # Fill via JS for SPA compatibility
        driver.execute_script("""
            const pwd = document.querySelector('input[type="password"]');
            const user = document.querySelector('input[type="text"], input[type="email"]');
            const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            if (user) { ns.call(user, arguments[0]); user.dispatchEvent(new Event('input', {bubbles: true})); }
            if (pwd) { ns.call(pwd, arguments[1]); pwd.dispatchEvent(new Event('input', {bubbles: true})); }
        """, USERNAME, PASSWORD)
        time.sleep(1)
        pwd.send_keys(Keys.ENTER)
        time.sleep(5)

        # Wait for post-login captcha to clear
        for _ in range(20):
            src = driver.page_source or ""
            if "crowdsec" not in src.lower() and "captcha" not in src.lower():
                break
            time.sleep(3)

        if "login" in driver.current_url.lower():
            print("  Browser login FAILED.")
            driver.quit()
            return None

        print(f"  Browser login OK: {driver.current_url}")

        # Extract token from localStorage
        token = ""
        try:
            token = driver.execute_script("return localStorage.getItem('accessToken') || '';") or ""
        except Exception:
            pass

        # Extract all cookies and inject into requests session
        for c in driver.get_cookies():
            api_session.cookies.set(c["name"], c["value"], domain=c.get("domain", ""), path=c.get("path", "/"))
            if "token" in c["name"].lower() or "auth" in c["name"].lower():
                if not token:
                    token = c["value"]

        driver.quit()

        if not token:
            print("  No token found in browser session.")
            return None

        api_session.headers["Authorization"] = f"Bearer {token}"
        print("  Browser-assisted login OK — token + cookies extracted")
        return api_session

    except Exception as e:
        driver.quit()
        print(f"  Browser login error: {e}")
        return None


# ─── METHOD 1: WhoSawMe API ──────────────────────────────────────────────────

def extract_whosawme(api_session):
    """Extract all clients from /api/v1/settings/whosawme (paginated)."""
    print("\n[METHOD 1] WhoSawMe API — /api/v1/settings/whosawme")
    clients = {}
    total_pages = None

    for page in range(1, 100):
        try:
            r = api_session.get(f"{API}/settings/whosawme", params={"page": page}, timeout=15)
            if r.status_code != 200:
                print(f"  page {page}: HTTP {r.status_code} — stopping")
                break
            data = r.json()
            pagination = data.get("pagination", {})
            if total_pages is None:
                total_pages = pagination.get("total", 0)
                total_items = pagination.get("totalItems", 0)
                print(f"  Pagination: {total_items} clients across {total_pages} pages")

            users = data.get("users", [])
            new_count = 0
            for u in users:
                uc = u.get("userCard", {})
                uname = uc.get("username", "")
                if uname and uname.lower() not in SKIP_USERNAMES and uname not in clients:
                    clients[uname] = {
                        "username": uname,
                        "userId": uc.get("userId"),
                        "url": f"{BASE}/{uname}",
                        "sources": ["whosawme"],
                        "isOnline": uc.get("status", {}).get("isOnline", False),
                        "location": uc.get("location", ""),
                        "photo": uc.get("userPhoto", ""),
                    }
                    new_count += 1

            print(f"  page {page}/{total_pages}: +{new_count} new (total: {len(clients)})")

            if page >= (total_pages or 0):
                break
            if not users:
                break
            time.sleep(0.5)
        except Exception as e:
            print(f"  page {page}: error — {e}")
            break

    print(f"  METHOD 1 COMPLETE: {len(clients)} clients from WhoSawMe")
    return clients


# ─── METHOD 2: Mailbox API ───────────────────────────────────────────────────

def extract_mailbox(api_session):
    """Extract all clients from /api/v1/mailbox (paginated)."""
    print("\n[METHOD 2] Mailbox API — /api/v1/mailbox")
    clients = {}

    for page in range(1, 50):
        try:
            r = api_session.get(f"{API}/mailbox", params={"page": page, "folder": 1, "sort": 1}, timeout=15)
            if r.status_code != 200:
                print(f"  page {page}: HTTP {r.status_code} — stopping")
                break
            data = r.json()
            emails = data.get("emails", [])
            if not emails:
                print(f"  page {page}: no emails — stopping")
                break

            new_count = 0
            for e in emails:
                uc = e.get("userCard", {})
                uname = uc.get("username", "")
                if uname and uname.lower() not in SKIP_USERNAMES:
                    if uname not in clients:
                        clients[uname] = {
                            "username": uname,
                            "userId": uc.get("userId"),
                            "url": f"{BASE}/{uname}",
                            "sources": ["mailbox"],
                            "subject": e.get("subject", "")[:80],
                            "emailId": e.get("id"),
                        }
                        new_count += 1
                    else:
                        if "mailbox" not in clients[uname].get("sources", []):
                            clients[uname]["sources"].append("mailbox")

            print(f"  page {page}: +{new_count} new (total: {len(clients)})")
            time.sleep(0.5)
        except Exception as e:
            print(f"  page {page}: error — {e}")
            break

    print(f"  METHOD 2 COMPLETE: {len(clients)} clients from Mailbox")
    return clients


# ─── METHOD 3: Reviews API ───────────────────────────────────────────────────

def extract_reviews(api_session):
    """Extract all clients from /api/v1/account/reviews (clients who reviewed you)."""
    print("\n[METHOD 3] Reviews API — /api/v1/account/reviews")
    clients = {}

    for path in ["/api/v1/account/reviews", "/api/v1/settings/reviews", "/api/v1/account/dashboard/reviews"]:
        try:
            r = api_session.get(f"{API}{path.replace('/api/v1', '')}", timeout=15)
            if r.status_code != 200:
                continue
            data = r.json()
            reviews = data if isinstance(data, list) else data.get("reviews", data.get("items", []))
            if not reviews:
                continue

            print(f"  Found {len(reviews)} reviews via {path}")
            for rv in reviews:
                uc = rv.get("userCard", rv.get("user", rv.get("reviewer", {})))
                uname = uc.get("username", rv.get("username", ""))
                if uname and uname.lower() not in SKIP_USERNAMES:
                    if uname not in clients:
                        clients[uname] = {
                            "username": uname,
                            "userId": uc.get("userId", rv.get("userId")),
                            "url": f"{BASE}/{uname}",
                            "sources": ["reviews"],
                            "rating": rv.get("rating", rv.get("ratingAverage")),
                            "reviewText": (rv.get("text", rv.get("body", rv.get("review", ""))) or "")[:120],
                        }
                    else:
                        if "reviews" not in clients[uname].get("sources", []):
                            clients[uname]["sources"].append("reviews")
            break
        except Exception as e:
            print(f"  {path}: error — {e}")
            continue

    # Also try paginated
    if not clients:
        for page in range(1, 20):
            try:
                r = api_session.get(f"{API}/account/reviews", params={"page": page}, timeout=10)
                if r.status_code != 200:
                    break
                data = r.json()
                reviews = data if isinstance(data, list) else data.get("reviews", [])
                if not reviews:
                    break
                for rv in reviews:
                    uc = rv.get("userCard", rv.get("user", {}))
                    uname = uc.get("username", "")
                    if uname and uname.lower() not in SKIP_USERNAMES:
                        if uname not in clients:
                            clients[uname] = {
                                "username": uname,
                                "userId": uc.get("userId"),
                                "url": f"{BASE}/{uname}",
                                "sources": ["reviews"],
                                "rating": rv.get("rating"),
                            }
                time.sleep(0.5)
            except Exception:
                break

    print(f"  METHOD 3 COMPLETE: {len(clients)} clients from Reviews")
    return clients


# ─── Merge + Verify ──────────────────────────────────────────────────────────

def merge_clients(*method_dicts):
    """Merge all client dicts, combining sources."""
    merged = {}
    for method_dict in method_dicts:
        for uname, data in method_dict.items():
            if uname not in merged:
                merged[uname] = data
            else:
                # Combine sources
                existing_sources = merged[uname].get("sources", [])
                for src in data.get("sources", []):
                    if src not in existing_sources:
                        existing_sources.append(src)
                merged[uname]["sources"] = existing_sources
                # Fill in missing fields
                for k, v in data.items():
                    if k not in merged[uname] or not merged[uname][k]:
                        merged[uname][k] = v
    return merged


def verify_clients(api_session, clients_dict):
    """Verify each client username resolves to a real profile."""
    print(f"\n[VERIFY] Checking {len(clients_dict)} client profiles...")
    verified = {}
    failed = {}

    for i, (uname, data) in enumerate(clients_dict.items()):
        url = data["url"]
        try:
            r = api_session.head(url, timeout=10, allow_redirects=True)
            status = r.status_code
            if status in (200, 301, 302):
                data["verified"] = True
                data["verify_status"] = status
                verified[uname] = data
            else:
                data["verified"] = False
                data["verify_status"] = status
                failed[uname] = data
                print(f"  [{i+1}] {uname}: HTTP {status} — FAILED")
        except Exception as e:
            data["verified"] = False
            data["verify_status"] = "error"
            data["verify_error"] = str(e)[:80]
            failed[uname] = data
            print(f"  [{i+1}] {uname}: error — {e}")

        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(clients_dict)}] verified={len(verified)} failed={len(failed)}")
        time.sleep(0.2)

    print(f"\n  VERIFIED: {len(verified)} clients")
    print(f"  FAILED: {len(failed)} clients")
    return verified, failed


# ─── Playwright Visit Engine ─────────────────────────────────────────────────

def visit_playwright(clients_list, dry_run, headless):
    from playwright.sync_api import sync_playwright

    print("[ENGINE] Playwright — visiting + proof capture")
    PROOF_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--window-size=1280,900"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        # Login
        print("  Logging in (Playwright)...")
        page.goto(f"{BASE}/login", wait_until="networkidle")
        _pw_wait_captcha(page)
        try:
            page.wait_for_selector('input[type="password"]', timeout=15000)
        except Exception:
            print("  No password field. Aborting.")
            browser.close()
            return None

        page.fill('input[type="text"], input[type="email"]', USERNAME)
        page.fill('input[type="password"]', PASSWORD)
        page.keyboard.press("Enter")
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        _pw_wait_captcha(page)

        if "login" in page.url.lower():
            print("  Login FAILED.")
            browser.close()
            return None
        print(f"  Login OK: {page.url}")

        results = []
        for i, client in enumerate(clients_list):
            uname = client["username"]
            url = client["url"]
            print(f"  [{i+1}/{len(clients_list)}] {uname}...")

            result = {
                "username": uname,
                "url": url,
                "sources": client.get("sources", []),
                "visited": False,
                "verified": client.get("verified", False),
                "visited_at": datetime.now(timezone.utc).isoformat(),
            }

            if dry_run:
                print(f"    [DRY] would visit {uname}")
                result["dry_run"] = True
                results.append(result)
                continue

            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
                time.sleep(2)
                result["visited"] = True
                result["page_title"] = page.title()[:100]
                result["final_url"] = page.url

                # Screenshot for proof
                ss_path = PROOF_DIR / f"{uname}_{int(time.time())}.png"
                page.screenshot(path=str(ss_path), full_page=False)
                result["screenshot"] = str(ss_path)
                result["screenshot_sha256"] = file_sha256(str(ss_path))
                result["proof_captured"] = True
                print(f"    visited: {result['page_title'][:40]} | proof: {ss_path.name}")

            except Exception as e:
                result["error"] = str(e)[:120]
                result["proof_captured"] = False
                print(f"    error: {e}")

            results.append(result)
            time.sleep(1.5)

        browser.close()
        return results


def _pw_wait_captcha(page, max_wait=90):
    try:
        src = page.content()
    except Exception:
        return
    if "crowdsec" not in src.lower() and "captcha" not in src.lower():
        return
    print("  [CAPTCHA] Detected. Waiting for clearance...")
    for _ in range(max_wait // 3):
        time.sleep(3)
        try:
            src = page.content()
        except Exception:
            continue
        if "crowdsec" not in src.lower() and "captcha" not in src.lower():
            print("  [CAPTCHA] Cleared!")
            return
    print("  [CAPTCHA] Timeout.")


# ─── Puppeteer Visit Engine ──────────────────────────────────────────────────

async def visit_puppeteer_async(clients_list, dry_run, headless):
    import pyppeteer

    print("[ENGINE] Puppeteer — visiting + proof capture")
    PROOF_DIR.mkdir(parents=True, exist_ok=True)
    os.makedirs(PROFILE_DIR, exist_ok=True)

    browser = await pyppeteer.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox",
              "--window-size=1280,900", f"--user-data-dir={PROFILE_DIR}"],
    )
    page = await browser.newPage()
    await page.setUserAgent(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    await page.setViewport({"width": 1280, "height": 900})

    print("  Logging in (Puppeteer)...")
    await page.goto(f"{BASE}/login", {"waitUntil": "networkidle2"})
    await _pp_wait_captcha(page)
    try:
        await page.waitForSelector('input[type="password"]', {"timeout": 15000})
    except Exception:
        print("  No password field. Aborting.")
        await browser.close()
        return None

    await page.type('input[type="text"], input[type="email"]', USERNAME)
    await page.type('input[type="password"]', PASSWORD)
    await page.keyboard.press("Enter")
    try:
        await asyncio.wait_for(page.waitForNavigation({"waitUntil": "networkidle2"}), timeout=15)
    except Exception:
        pass
    time.sleep(5)
    await _pp_wait_captcha(page)

    if "login" in page.url.lower():
        print("  Login FAILED.")
        await browser.close()
        return None
    print(f"  Login OK: {page.url}")

    results = []
    for i, client in enumerate(clients_list):
        uname = client["username"]
        url = client["url"]
        print(f"  [{i+1}/{len(clients_list)}] {uname}...")

        result = {
            "username": uname, "url": url,
            "sources": client.get("sources", []),
            "visited": False, "verified": client.get("verified", False),
            "visited_at": datetime.now(timezone.utc).isoformat(),
        }

        if dry_run:
            print(f"    [DRY] would visit {uname}")
            result["dry_run"] = True
            results.append(result)
            continue

        try:
            await page.goto(url, {"waitUntil": "networkidle2"})
            time.sleep(2)
            result["visited"] = True
            result["page_title"] = (await page.title())[:100]
            result["final_url"] = page.url

            ss_path = PROOF_DIR / f"{uname}_{int(time.time())}.png"
            await page.screenshot({"path": str(ss_path)})
            result["screenshot"] = str(ss_path)
            result["screenshot_sha256"] = file_sha256(str(ss_path))
            result["proof_captured"] = True
            print(f"    visited: {result['page_title'][:40]} | proof: {ss_path.name}")
        except Exception as e:
            result["error"] = str(e)[:120]
            result["proof_captured"] = False
            print(f"    error: {e}")

        results.append(result)
        time.sleep(1.5)

    await browser.close()
    return results


async def _pp_wait_captcha(page, max_wait=90):
    try:
        src = await page.content()
    except Exception:
        return
    if "crowdsec" not in src.lower() and "captcha" not in src.lower():
        return
    print("  [CAPTCHA] Detected. Waiting for clearance...")
    for _ in range(max_wait // 3):
        time.sleep(3)
        try:
            src = await page.content()
        except Exception:
            continue
        if "crowdsec" not in src.lower() and "captcha" not in src.lower():
            print("  [CAPTCHA] Cleared!")
            return
    print("  [CAPTCHA] Timeout.")


def visit_puppeteer(clients_list, dry_run, headless):
    return asyncio.get_event_loop().run_until_complete(
        visit_puppeteer_async(clients_list, dry_run, headless)
    )


# ─── Selenium Visit Engine ───────────────────────────────────────────────────

def visit_selenium(clients_list, dry_run, headless):
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    print("[ENGINE] Selenium — visiting + proof capture")
    PROOF_DIR.mkdir(parents=True, exist_ok=True)
    os.makedirs(PROFILE_DIR, exist_ok=True)

    opts = uc.ChromeOptions()
    opts.add_argument("--window-size=1280,900")
    opts.add_argument(f"--user-data-dir={PROFILE_DIR}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    if headless:
        opts.add_argument("--headless=new")
    driver = uc.Chrome(options=opts, version_main=149)

    try:
        print("  Logging in (Selenium)...")
        driver.get(f"{BASE}/login")
        time.sleep(4)
        _sel_wait_captcha(driver)

        pwd = None
        for _ in range(15):
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, 'input[type="password"]')
                if elements and elements[0].is_displayed():
                    pwd = elements[0]
                    break
            except Exception:
                pass
            time.sleep(1)

        if not pwd:
            print("  No password field. Aborting.")
            driver.quit()
            return None

        driver.execute_script("""
            const pwd = document.querySelector('input[type="password"]');
            const user = document.querySelector('input[type="text"], input[type="email"]');
            const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            if (user) { ns.call(user, arguments[0]); user.dispatchEvent(new Event('input', {bubbles: true})); }
            if (pwd) { ns.call(pwd, arguments[1]); pwd.dispatchEvent(new Event('input', {bubbles: true})); }
        """, USERNAME, PASSWORD)
        time.sleep(1)
        pwd.send_keys(Keys.ENTER)
        time.sleep(5)
        _sel_wait_captcha(driver)

        if "login" in driver.current_url.lower():
            print("  Login FAILED.")
            driver.quit()
            return None
        print(f"  Login OK: {driver.current_url}")

        results = []
        for i, client in enumerate(clients_list):
            uname = client["username"]
            url = client["url"]
            print(f"  [{i+1}/{len(clients_list)}] {uname}...")

            result = {
                "username": uname, "url": url,
                "sources": client.get("sources", []),
                "visited": False, "verified": client.get("verified", False),
                "visited_at": datetime.now(timezone.utc).isoformat(),
            }

            if dry_run:
                print(f"    [DRY] would visit {uname}")
                result["dry_run"] = True
                results.append(result)
                continue

            try:
                driver.get(url)
                time.sleep(2)
                result["visited"] = True
                result["page_title"] = driver.title[:100]
                result["final_url"] = driver.current_url

                ss_path = PROOF_DIR / f"{uname}_{int(time.time())}.png"
                driver.save_screenshot(str(ss_path))
                result["screenshot"] = str(ss_path)
                result["screenshot_sha256"] = file_sha256(str(ss_path))
                result["proof_captured"] = True
                print(f"    visited: {result['page_title'][:40]} | proof: {ss_path.name}")
            except Exception as e:
                result["error"] = str(e)[:120]
                result["proof_captured"] = False
                print(f"    error: {e}")

            results.append(result)
            time.sleep(1.5)

        driver.quit()
        return results
    except Exception as e:
        driver.quit()
        raise


def _sel_wait_captcha(driver, max_wait=90):
    src = driver.page_source or ""
    if "crowdsec" not in src.lower() and "captcha" not in src.lower():
        return
    print("  [CAPTCHA] Detected. Waiting for clearance...")
    for _ in range(max_wait // 3):
        time.sleep(3)
        src = driver.page_source or ""
        if "crowdsec" not in src.lower() and "captcha" not in src.lower():
            print("  [CAPTCHA] Cleared!")
            return
    print("  [CAPTCHA] Timeout.")


# ─── Engine Registry ─────────────────────────────────────────────────────────

VISIT_ENGINES = {
    "playwright": visit_playwright,
    "puppeteer": visit_puppeteer,
    "selenium": visit_selenium,
}
ENGINE_FALLBACK = ["playwright", "puppeteer", "selenium"]


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extract clients (3 methods) + visit with proof — Playwright/Puppeteer/Selenium"
    )
    parser.add_argument("--dry-run", action="store_true", help="Extract + verify only, no visiting")
    parser.add_argument("--engine", type=str, default="auto", choices=["auto", "playwright", "puppeteer", "selenium"])
    parser.add_argument("--headless", action="store_true", help="Run browser headless")
    parser.add_argument("--visit-only", action="store_true", help="Skip extraction, use saved data/clients_extracted.json")
    parser.add_argument("--skip-verify", action="store_true", help="Skip HTTP verification step")
    parser.add_argument("--method", type=str, default="all", choices=["all", "whosawme", "mailbox", "reviews"],
                        help="Use only one extraction method")
    args = parser.parse_args()

    print("=== RENTMASSEUR CLIENT EXTRACTION + VISIT (3 Methods, Verified, Proven) ===")
    print(f"  Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print(f"  Engine: {args.engine}")
    print(f"  Headless: {args.headless}")
    print(f"  Method: {args.method}")

    # ── Phase 1: Extract clients ──
    if args.visit_only:
        saved = load_saved_clients()
        if not saved:
            print("  No saved clients found. Run without --visit-only first.")
            sys.exit(1)
        all_clients = saved.get("clients", {})
        print(f"  Loaded {len(all_clients)} saved clients.")
    else:
        print("\n[EXTRACTION] Logging in via API...")
        api_session = api_login()
        if not api_session:
            print("  API login failed. Cannot extract clients.")
            sys.exit(1)

        method1 = {}
        method2 = {}
        method3 = {}

        if args.method in ("all", "whosawme"):
            method1 = extract_whosawme(api_session)
        if args.method in ("all", "mailbox"):
            method2 = extract_mailbox(api_session)
        if args.method in ("all", "reviews"):
            method3 = extract_reviews(api_session)

        # Merge all methods
        all_clients = merge_clients(method1, method2, method3)

        print(f"\n[MERGE] Total unique clients across all methods: {len(all_clients)}")

        # Source breakdown
        source_counts = {"whosawme": 0, "mailbox": 0, "reviews": 0}
        for c in all_clients.values():
            for s in c.get("sources", []):
                source_counts[s] = source_counts.get(s, 0) + 1
        print(f"  Source breakdown: {json.dumps(source_counts)}")

        # Multi-source clients (appeared in 2+ methods)
        multi_source = sum(1 for c in all_clients.values() if len(c.get("sources", [])) >= 2)
        print(f"  Clients in 2+ methods: {multi_source}")

        # ── Phase 2: Verify ──
        if not args.skip_verify:
            verified, failed = verify_clients(api_session, all_clients)
            all_clients = verified
            if failed:
                save_data("clients_failed_verification.json", {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "count": len(failed),
                    "clients": failed,
                })
                print(f"  Failed clients saved to data/clients_failed_verification.json")

        # Save extracted clients
        save_data("clients_extracted.json", {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total": len(all_clients),
            "methods": {
                "whosawme": len(method1),
                "mailbox": len(method2),
                "reviews": len(method3),
            },
            "clients": all_clients,
        })
        print(f"\n  Saved {len(all_clients)} clients to data/clients_extracted.json")

    if not all_clients:
        print("\n  No clients found. Exiting.")
        write_receipt("client_extract_visit", {"clients": 0, "visited": 0}, success=False)
        return

    # ── Phase 3: Visit with proof ──
    clients_list = list(all_clients.values())
    print(f"\n[VISIT] Visiting {len(clients_list)} clients with proof capture...")

    engine_order = ENGINE_FALLBACK if args.engine == "auto" else [args.engine]
    visit_results = None
    errors = []

    for engine_name in engine_order:
        engine_fn = VISIT_ENGINES[engine_name]
        try:
            print(f"\n>>> Trying engine: {engine_name}")
            visit_results = engine_fn(clients_list, args.dry_run, args.headless)
            if visit_results is not None:
                print(f">>> Engine {engine_name} succeeded.")
                break
            else:
                errors.append(f"{engine_name}: returned None (login failed?)")
                print(f">>> Engine {engine_name} failed, trying next...")
        except Exception as e:
            errors.append(f"{engine_name}: {e}")
            print(f">>> Engine {engine_name} error: {e}")
            print(f">>> Trying next engine...")

    if visit_results is None:
        print("\n=== ALL ENGINES FAILED ===")
        for err in errors:
            print(f"  - {err}")
        write_receipt("client_extract_visit", {"errors": errors, "dry_run": args.dry_run}, success=False)
        sys.exit(1)

    visited_count = sum(1 for r in visit_results if r.get("visited"))
    proof_count = sum(1 for r in visit_results if r.get("proof_captured"))

    # ── Phase 4: Receipt + Data ──
    rpath = write_receipt("client_extract_visit", {
        "clients_extracted": len(all_clients),
        "clients_visited": visited_count,
        "proofs_captured": proof_count,
        "dry_run": args.dry_run,
        "engine_used": engine_name,
        "methods": args.method,
        "errors": errors,
        "results": visit_results,
    })

    save_data("client_visit_latest.json", {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "engine": engine_name,
        "clients_extracted": len(all_clients),
        "clients_visited": visited_count,
        "proofs_captured": proof_count,
        "results": visit_results,
    })

    print(f"\n=== COMPLETE ===")
    print(f"  Clients extracted: {len(all_clients)}")
    print(f"  Clients visited: {visited_count}")
    print(f"  Proofs captured: {proof_count}")
    print(f"  Proof directory: {PROOF_DIR}")
    print(f"  Receipt: {rpath}")
    print(f"  Data: {DATA_DIR / 'client_visit_latest.json'}")


if __name__ == "__main__":
    main()
