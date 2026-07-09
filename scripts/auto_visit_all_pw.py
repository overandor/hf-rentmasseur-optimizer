#!/usr/bin/env python3
"""
RentMasseur Visit-Back + Message ALL Visitors — Multi-Engine (Playwright + Puppeteer + Selenium).

Uses three browser automation engines with automatic fallback:
  1. Playwright (primary) — stealth-capable, fast, reliable
  2. Puppeteer / pyppeteer (fallback 1) — Python port of Puppeteer
  3. Selenium / undetected-chromedriver (fallback 2) — last resort

Features:
  - Scrapes ALL visitors from /settings/whosawme (full pagination, no limit)
  - Visits every visitor's profile
  - Sends a message to every visitor
  - Headless-capable (but runs visible by default for captcha solving)
  - Writes receipts + data JSON

Usage:
    python3 scripts/auto_visit_all_pw.py
    python3 scripts/auto_visit_all_pw.py --dry-run
    python3 scripts/auto_visit_all_pw.py --message "Hey, text me at XXX-XXX-XXXX"
    python3 scripts/auto_visit_all_pw.py --engine playwright
    python3 scripts/auto_visit_all_pw.py --engine puppeteer
    python3 scripts/auto_visit_all_pw.py --engine selenium
    python3 scripts/auto_visit_all_pw.py --headless
"""
import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://rentmasseur.com"
USERNAME = os.getenv("RENTMASSEUR_USERNAME", "karpathianwolf")
PASSWORD = os.getenv("RENTMASSEUR_PASSWORD", os.environ.get("RM_PASSWORD", ""))
PHONE = os.getenv("WOLF_PHONE", "347-453-5129")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RECEIPTS_DIR = Path(__file__).resolve().parent.parent / "receipts"
PROFILE_DIR = "/tmp/rm_auto_visit_pw"

DEFAULT_MESSAGE = (
    f"Hey! Thanks for checking out my profile. "
    f"I'm available today — feel free to text me at {PHONE}. "
    f"Happy to set something up."
)

SKIP_USERNAMES = {
    "settings", "gay-massage", "stream", "masseurcams", "advertise",
    "about", "login", "sitemap", "topics", "robots", "api", "build-stream",
    "terms", "privacy", "contact", "help", "blog", "blogs",
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

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


# ─── Playwright Engine ────────────────────────────────────────────────────────

def run_playwright(message_text, dry_run, headless):
    """Playwright sync API — primary engine."""
    from playwright.sync_api import sync_playwright

    print("[ENGINE] Playwright (sync)")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--window-size=1280,900",
            ],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        # ── Login ──
        print("[1] Logging in (Playwright)...")
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

        # ── Scrape Who Saw Me (full pagination) ──
        print("[2] Scraping Who Saw Me (Playwright)...")
        visitors = _pw_scrape_whosawme(page)
        print(f"  Total unique visitors: {len(visitors)}")

        if not visitors:
            browser.close()
            return {"visitors": 0, "visited": 0, "messaged": 0, "engine": "playwright"}

        # ── Visit + Message each ──
        print(f"\n[3] Visiting + messaging {len(visitors)} visitors...")
        results = []
        for i, v in enumerate(visitors):
            print(f"  [{i+1}/{len(visitors)}] {v['username']}...")
            r = _pw_visit_and_message(page, v, message_text, dry_run)
            results.append(r)
            if not dry_run:
                time.sleep(2)

        visited_count = sum(1 for r in results if r.get("visited"))
        messaged_count = sum(1 for r in results if r.get("messaged"))

        browser.close()
        return {
            "visitors": len(visitors),
            "visited": visited_count,
            "messaged": messaged_count,
            "engine": "playwright",
            "results": results,
            "visitors_data": visitors,
        }


def _pw_wait_captcha(page, max_wait=90):
    """Check for CrowdSec/captcha and wait for clearance."""
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


def _pw_scrape_whosawme(page):
    """Scrape all visitors with full pagination via Playwright."""
    all_visitors = []
    seen = set()

    for pg in range(1, 100):
        page.goto(f"{BASE}/settings/whosawme?page={pg}", wait_until="networkidle")
        time.sleep(3)
        _pw_wait_captcha(page)

        # Scroll to load lazy content
        for _ in range(3):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)

        visitors = page.evaluate("""
            (skipUsernames) => {
                const result = [];
                const seen = new Set();
                const links = Array.from(document.querySelectorAll('a[href]'));
                for (const a of links) {
                    try {
                        const href = a.href;
                        if (!href.startsWith('https://rentmasseur.com/')) continue;
                        const path = new URL(href).pathname;
                        if (path && path !== '/' && path.split('/').length === 2) {
                            const username = path.replace('/', '').split('?')[0];
                            if (username && !seen.has(username) && !skipUsernames.includes(username.toLowerCase())
                                && !username.startsWith('_') && username.length > 2
                                && !username.match(/^\\d+$/)) {
                                seen.add(username);
                                result.push({username: username, url: href.split('?')[0]});
                            }
                        }
                    } catch(e) {}
                }
                // Also check profile images
                const imgs = document.querySelectorAll('img[alt]');
                for (const img of imgs) {
                    const alt = (img.getAttribute('alt') || '').toLowerCase();
                    if (alt.includes('profile') || alt.includes('avatar') || alt.includes('user')) {
                        const a = img.closest('a');
                        if (a && a.href) {
                            try {
                                const path = new URL(a.href).pathname;
                                const username = path.replace('/', '').split('?')[0];
                                if (username && !seen.has(username) && !skipUsernames.includes(username.toLowerCase())
                                    && username.length > 2 && !username.match(/^\\d+$/)) {
                                    seen.add(username);
                                    result.push({username: username, url: a.href.split('?')[0]});
                                }
                            } catch(e) {}
                        }
                    }
                }
                return result;
            }
        """, list(SKIP_USERNAMES))

        new_count = 0
        for v in visitors:
            if v["username"] not in seen:
                seen.add(v["username"])
                all_visitors.append(v)
                new_count += 1

        print(f"  Page {pg}: {len(visitors)} found, {new_count} new (total: {len(all_visitors)})")

        if new_count == 0 and pg > 1:
            break
        if not visitors:
            break

    return all_visitors


def _pw_visit_and_message(page, visitor, message_text, dry_run):
    """Visit a profile and send a message via Playwright."""
    uname = visitor["username"]
    url = visitor["url"]
    result = {"username": uname, "url": url, "visited": False, "messaged": False}

    page.goto(url, wait_until="networkidle")
    time.sleep(3)
    result["visited"] = True
    try:
        result["page_title"] = page.title()[:60]
    except Exception:
        result["page_title"] = ""

    if dry_run:
        print(f"  [DRY] visited {uname}")
        return result

    try:
        # Find message button
        message_btn = None
        for selector in [
            'button[class*="message"]', 'a[class*="message"]',
            'button[class*="contact"]', 'a[class*="contact"]',
            'a[href*="message"]', 'a[href*="mail"]',
            'button[aria-label*="message"]', 'button[aria-label*="Message"]',
        ]:
            try:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    message_btn = el
                    break
            except Exception:
                continue

        # Fallback: search by text
        if not message_btn:
            for el in page.query_selector_all("button, a"):
                try:
                    txt = (el.inner_text() or "").lower().strip()
                    if txt in ["message", "contact", "send message", "email me"] and el.is_visible():
                        message_btn = el
                        break
                except Exception:
                    continue

        if not message_btn:
            print(f"  {uname}: no message button found")
            return result

        message_btn.click()
        time.sleep(3)

        # Find textarea
        textarea = None
        for selector in [
            "textarea", 'textarea[class*="message"]', 'textarea[class*="body"]',
            'textarea[placeholder*="message"]', 'div[contenteditable="true"]',
        ]:
            try:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    textarea = el
                    break
            except Exception:
                continue

        if not textarea:
            print(f"  {uname}: no textarea found after clicking message")
            return result

        textarea.click()
        time.sleep(0.5)
        textarea.fill("")
        textarea.type(message_text)
        time.sleep(1)

        # Find send button
        send_btn = None
        for selector in ['button[type="submit"]', 'button[class*="send"]', 'button[class*="submit"]']:
            try:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    send_btn = el
                    break
            except Exception:
                continue

        if not send_btn:
            for btn in page.query_selector_all("button"):
                try:
                    txt = (btn.inner_text() or "").lower().strip()
                    if txt in ["send", "submit", "reply", "send message"] and btn.is_visible():
                        send_btn = btn
                        break
                except Exception:
                    continue

        if send_btn:
            send_btn.click()
            time.sleep(3)
            result["messaged"] = True
            print(f"  MESSAGED {uname}: sent")
        else:
            page.keyboard.press("Control+Enter")
            time.sleep(3)
            result["messaged"] = True
            print(f"  MESSAGED {uname}: sent (Ctrl+Enter)")

    except Exception as e:
        result["error"] = str(e)[:100]
        print(f"  {uname}: error — {e}")

    return result


# ─── Puppeteer Engine (pyppeteer) ─────────────────────────────────────────────

async def run_puppeteer_async(message_text, dry_run, headless):
    """Puppeteer via pyppeteer — fallback engine 1."""
    import pyppeteer

    print("[ENGINE] Puppeteer (pyppeteer)")

    os.makedirs(PROFILE_DIR, exist_ok=True)
    browser = await pyppeteer.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--window-size=1280,900",
            f"--user-data-dir={PROFILE_DIR}",
        ],
    )
    page = await browser.newPage()
    await page.setUserAgent(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
    await page.setViewport({"width": 1280, "height": 900})

    # ── Login ──
    print("[1] Logging in (Puppeteer)...")
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
        await asyncio.wait_for(
            page.waitForNavigation({"waitUntil": "networkidle2"}),
            timeout=15,
        )
    except (asyncio.TimeoutError, Exception):
        pass
    time.sleep(5)

    await _pp_wait_captcha(page)

    url = page.url
    if "login" in url.lower():
        print("  Login FAILED.")
        await browser.close()
        return None
    print(f"  Login OK: {url}")

    # ── Scrape Who Saw Me ──
    print("[2] Scraping Who Saw Me (Puppeteer)...")
    visitors = await _pp_scrape_whosawme(page)
    print(f"  Total unique visitors: {len(visitors)}")

    if not visitors:
        await browser.close()
        return {"visitors": 0, "visited": 0, "messaged": 0, "engine": "puppeteer"}

    # ── Visit + Message ──
    print(f"\n[3] Visiting + messaging {len(visitors)} visitors...")
    results = []
    for i, v in enumerate(visitors):
        print(f"  [{i+1}/{len(visitors)}] {v['username']}...")
        r = await _pp_visit_and_message(page, v, message_text, dry_run)
        results.append(r)
        if not dry_run:
            time.sleep(2)

    visited_count = sum(1 for r in results if r.get("visited"))
    messaged_count = sum(1 for r in results if r.get("messaged"))

    await browser.close()
    return {
        "visitors": len(visitors),
        "visited": visited_count,
        "messaged": messaged_count,
        "engine": "puppeteer",
        "results": results,
        "visitors_data": visitors,
    }


async def _pp_wait_captcha(page, max_wait=90):
    """Wait for captcha clearance."""
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


async def _pp_scrape_whosawme(page):
    """Scrape all visitors with full pagination via Puppeteer."""
    all_visitors = []
    seen = set()

    for pg in range(1, 100):
        await page.goto(f"{BASE}/settings/whosawme?page={pg}", {"waitUntil": "networkidle2"})
        time.sleep(3)
        await _pp_wait_captcha(page)

        for _ in range(3):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)

        visitors = await page.evaluate("""
            (skipUsernames) => {
                const result = [];
                const seen = new Set();
                const links = Array.from(document.querySelectorAll('a[href]'));
                for (const a of links) {
                    try {
                        const href = a.href;
                        if (!href.startsWith('https://rentmasseur.com/')) continue;
                        const path = new URL(href).pathname;
                        if (path && path !== '/' && path.split('/').length === 2) {
                            const username = path.replace('/', '').split('?')[0];
                            if (username && !seen.has(username) && !skipUsernames.includes(username.toLowerCase())
                                && !username.startsWith('_') && username.length > 2
                                && !username.match(/^\\d+$/)) {
                                seen.add(username);
                                result.push({username: username, url: href.split('?')[0]});
                            }
                        }
                    } catch(e) {}
                }
                const imgs = document.querySelectorAll('img[alt]');
                for (const img of imgs) {
                    const alt = (img.getAttribute('alt') || '').toLowerCase();
                    if (alt.includes('profile') || alt.includes('avatar') || alt.includes('user')) {
                        const a = img.closest('a');
                        if (a && a.href) {
                            try {
                                const path = new URL(a.href).pathname;
                                const username = path.replace('/', '').split('?')[0];
                                if (username && !seen.has(username) && !skipUsernames.includes(username.toLowerCase())
                                    && username.length > 2 && !username.match(/^\\d+$/)) {
                                    seen.add(username);
                                    result.push({username: username, url: a.href.split('?')[0]});
                                }
                            } catch(e) {}
                        }
                    }
                }
                return result;
            }
        """, list(SKIP_USERNAMES))

        new_count = 0
        for v in visitors:
            if v["username"] not in seen:
                seen.add(v["username"])
                all_visitors.append(v)
                new_count += 1

        print(f"  Page {pg}: {len(visitors)} found, {new_count} new (total: {len(all_visitors)})")

        if new_count == 0 and pg > 1:
            break
        if not visitors:
            break

    return all_visitors


async def _pp_visit_and_message(page, visitor, message_text, dry_run):
    """Visit profile and send message via Puppeteer."""
    uname = visitor["username"]
    url = visitor["url"]
    result = {"username": uname, "url": url, "visited": False, "messaged": False}

    await page.goto(url, {"waitUntil": "networkidle2"})
    time.sleep(3)
    result["visited"] = True
    try:
        result["page_title"] = (await page.title())[:60]
    except Exception:
        result["page_title"] = ""

    if dry_run:
        print(f"  [DRY] visited {uname}")
        return result

    try:
        # Find message button
        message_btn = None
        for selector in [
            'button[class*="message"]', 'a[class*="message"]',
            'button[class*="contact"]', 'a[class*="contact"]',
            'a[href*="message"]', 'a[href*="mail"]',
        ]:
            el = await page.querySelector(selector)
            if el:
                visible = await el.boundingBox()
                if visible:
                    message_btn = el
                    break

        if not message_btn:
            elements = await page.querySelectorAll("button, a")
            for el in elements:
                try:
                    txt = await page.evaluate("(el) => el.textContent || ''", el)
                    txt = txt.lower().strip()
                    if txt in ["message", "contact", "send message", "email me"]:
                        visible = await el.boundingBox()
                        if visible:
                            message_btn = el
                            break
                except Exception:
                    continue

        if not message_btn:
            print(f"  {uname}: no message button found")
            return result

        await message_btn.click()
        time.sleep(3)

        # Find textarea
        textarea = None
        for selector in ["textarea", 'div[contenteditable="true"]']:
            el = await page.querySelector(selector)
            if el:
                visible = await el.boundingBox()
                if visible:
                    textarea = el
                    break

        if not textarea:
            print(f"  {uname}: no textarea found")
            return result

        await textarea.click()
        time.sleep(0.5)
        await page.evaluate("(el) => { el.value = ''; }", textarea)
        await textarea.type(message_text)
        time.sleep(1)

        # Find send button
        send_btn = None
        for selector in ['button[type="submit"]', 'button[class*="send"]', 'button[class*="submit"]']:
            el = await page.querySelector(selector)
            if el:
                visible = await el.boundingBox()
                if visible:
                    send_btn = el
                    break

        if not send_btn:
            buttons = await page.querySelectorAll("button")
            for btn in buttons:
                try:
                    txt = await page.evaluate("(el) => el.textContent || ''", btn)
                    txt = txt.lower().strip()
                    if txt in ["send", "submit", "reply", "send message"]:
                        visible = await btn.boundingBox()
                        if visible:
                            send_btn = btn
                            break
                except Exception:
                    continue

        if send_btn:
            await send_btn.click()
            time.sleep(3)
            result["messaged"] = True
            print(f"  MESSAGED {uname}: sent")
        else:
            await page.keyboard.press("Control+Enter")
            time.sleep(3)
            result["messaged"] = True
            print(f"  MESSAGED {uname}: sent (Ctrl+Enter)")

    except Exception as e:
        result["error"] = str(e)[:100]
        print(f"  {uname}: error — {e}")

    return result


def run_puppeteer(message_text, dry_run, headless):
    """Wrapper to run async puppeteer engine."""
    return asyncio.get_event_loop().run_until_complete(
        run_puppeteer_async(message_text, dry_run, headless)
    )


# ─── Selenium Engine (undetected-chromedriver) ────────────────────────────────

def run_selenium(message_text, dry_run, headless):
    """Selenium via undetected-chromedriver — fallback engine 2."""
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    print("[ENGINE] Selenium (undetected-chromedriver)")

    os.makedirs(PROFILE_DIR, exist_ok=True)
    opts = uc.ChromeOptions()
    opts.add_argument("--window-size=1280,900")
    opts.add_argument(f"--user-data-dir={PROFILE_DIR}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    if headless:
        opts.add_argument("--headless=new")
    driver = uc.Chrome(options=opts, version_main=149)

    try:
        # ── Login ──
        print("[1] Logging in (Selenium)...")
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
        _sel_wait_captcha(driver)

        if "login" in driver.current_url.lower():
            print("  Login FAILED.")
            driver.quit()
            return None
        print(f"  Login OK: {driver.current_url}")

        # ── Scrape Who Saw Me ──
        print("[2] Scraping Who Saw Me (Selenium)...")
        visitors = _sel_scrape_whosawme(driver)
        print(f"  Total unique visitors: {len(visitors)}")

        if not visitors:
            driver.quit()
            return {"visitors": 0, "visited": 0, "messaged": 0, "engine": "selenium"}

        # ── Visit + Message ──
        print(f"\n[3] Visiting + messaging {len(visitors)} visitors...")
        results = []
        for i, v in enumerate(visitors):
            print(f"  [{i+1}/{len(visitors)}] {v['username']}...")
            r = _sel_visit_and_message(driver, v, message_text, dry_run, By, Keys)
            results.append(r)
            if not dry_run:
                time.sleep(2)

        visited_count = sum(1 for r in results if r.get("visited"))
        messaged_count = sum(1 for r in results if r.get("messaged"))

        driver.quit()
        return {
            "visitors": len(visitors),
            "visited": visited_count,
            "messaged": messaged_count,
            "engine": "selenium",
            "results": results,
            "visitors_data": visitors,
        }
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


def _sel_scrape_whosawme(driver):
    all_visitors = []
    seen = set()

    for pg in range(1, 100):
        driver.get(f"{BASE}/settings/whosawme?page={pg}")
        time.sleep(4)
        _sel_wait_captcha(driver)

        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

        visitors = driver.execute_script("""
            const skipUsernames = Array.from(arguments[0]);
            const result = [];
            const seen = new Set();
            const links = Array.from(document.querySelectorAll('a[href]'));
            for (const a of links) {
                try {
                    const href = a.href;
                    if (!href.startsWith('https://rentmasseur.com/')) continue;
                    const path = new URL(href).pathname;
                    if (path && path !== '/' && path.split('/').length === 2) {
                        const username = path.replace('/', '').split('?')[0];
                        if (username && !seen.has(username) && !skipUsernames.includes(username.toLowerCase())
                            && !username.startsWith('_') && username.length > 2
                            && !username.match(/^\\d+$/)) {
                            seen.add(username);
                            result.push({username: username, url: href.split('?')[0]});
                        }
                    }
                } catch(e) {}
            }
            const imgs = document.querySelectorAll('img[alt]');
            for (const img of imgs) {
                const alt = (img.getAttribute('alt') || '').toLowerCase();
                if (alt.includes('profile') || alt.includes('avatar') || alt.includes('user')) {
                    const a = img.closest('a');
                    if (a && a.href) {
                        try {
                            const path = new URL(a.href).pathname;
                            const username = path.replace('/', '').split('?')[0];
                            if (username && !seen.has(username) && !skipUsernames.includes(username.toLowerCase())
                                && username.length > 2 && !username.match(/^\\d+$/)) {
                                seen.add(username);
                                result.push({username: username, url: a.href.split('?')[0]});
                            }
                        } catch(e) {}
                    }
                }
            }
            return result;
        """, list(SKIP_USERNAMES))

        new_count = 0
        for v in visitors:
            if v["username"] not in seen:
                seen.add(v["username"])
                all_visitors.append(v)
                new_count += 1

        print(f"  Page {pg}: {len(visitors)} found, {new_count} new (total: {len(all_visitors)})")

        if new_count == 0 and pg > 1:
            break
        if not visitors:
            break

    return all_visitors


def _sel_visit_and_message(driver, visitor, message_text, dry_run, By, Keys):
    uname = visitor["username"]
    url = visitor["url"]
    result = {"username": uname, "url": url, "visited": False, "messaged": False}

    driver.get(url)
    time.sleep(3)
    result["visited"] = True
    try:
        result["page_title"] = driver.title[:60]
    except Exception:
        result["page_title"] = ""

    if dry_run:
        print(f"  [DRY] visited {uname}")
        return result

    try:
        message_btn = None
        for selector in [
            'button[class*="message"]', 'a[class*="message"]',
            'button[class*="contact"]', 'a[class*="contact"]',
            'a[href*="message"]', 'a[href*="mail"]',
            'button[aria-label*="message"]', 'button[aria-label*="Message"]',
        ]:
            try:
                btn = driver.find_element(By.CSS_SELECTOR, selector)
                if btn.is_displayed():
                    message_btn = btn
                    break
            except Exception:
                continue

        if not message_btn:
            elements = driver.find_elements(By.CSS_SELECTOR, "button, a")
            for el in elements:
                try:
                    txt = (el.text or "").lower().strip()
                    if txt in ["message", "contact", "send message", "email me"] and el.is_displayed():
                        message_btn = el
                        break
                except Exception:
                    continue

        if not message_btn:
            print(f"  {uname}: no message button found")
            return result

        message_btn.click()
        time.sleep(3)

        textarea = None
        for selector in ["textarea", 'div[contenteditable="true"]']:
            try:
                ta = driver.find_element(By.CSS_SELECTOR, selector)
                if ta.is_displayed():
                    textarea = ta
                    break
            except Exception:
                continue

        if not textarea:
            print(f"  {uname}: no textarea found")
            return result

        textarea.click()
        time.sleep(0.5)
        textarea.send_keys(Keys.CONTROL, "a")
        textarea.send_keys(Keys.DELETE)
        textarea.send_keys(message_text)
        time.sleep(1)

        send_btn = None
        for selector in ['button[type="submit"]', 'button[class*="send"]', 'button[class*="submit"]']:
            try:
                btn = driver.find_element(By.CSS_SELECTOR, selector)
                if btn.is_displayed():
                    send_btn = btn
                    break
            except Exception:
                continue

        if not send_btn:
            buttons = driver.find_elements(By.CSS_SELECTOR, "button")
            for btn in buttons:
                try:
                    txt = (btn.text or "").lower().strip()
                    if txt in ["send", "submit", "reply", "send message"] and btn.is_displayed():
                        send_btn = btn
                        break
                except Exception:
                    continue

        if send_btn:
            send_btn.click()
            time.sleep(3)
            result["messaged"] = True
            print(f"  MESSAGED {uname}: sent")
        else:
            textarea.send_keys(Keys.CONTROL, Keys.ENTER)
            time.sleep(3)
            result["messaged"] = True
            print(f"  MESSAGED {uname}: sent (Ctrl+Enter)")

    except Exception as e:
        result["error"] = str(e)[:100]
        print(f"  {uname}: error — {e}")

    return result


# ─── Main ─────────────────────────────────────────────────────────────────────

ENGINES = {
    "playwright": run_playwright,
    "puppeteer": run_puppeteer,
    "selenium": run_selenium,
}

ENGINE_FALLBACK_ORDER = ["playwright", "puppeteer", "selenium"]


def main():
    parser = argparse.ArgumentParser(
        description="Visit + Message ALL WhoSawMe visitors — Playwright/Puppeteer/Selenium"
    )
    parser.add_argument("--dry-run", action="store_true", help="List targets without messaging")
    parser.add_argument("--message", type=str, default=DEFAULT_MESSAGE, help="Message to send")
    parser.add_argument("--engine", type=str, default="auto",
                        choices=["auto", "playwright", "puppeteer", "selenium"],
                        help="Browser engine to use (auto = try all with fallback)")
    parser.add_argument("--headless", action="store_true", help="Run headless (captcha may block)")
    parser.add_argument("--skip-message", action="store_true", help="Only visit, don't message")
    args = parser.parse_args()

    print("=== RENTMASSEUR VISIT + MESSAGE ALL (Multi-Engine) ===")
    print(f"  Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print(f"  Engine: {args.engine}")
    print(f"  Headless: {args.headless}")
    print(f"  Message: {args.message[:80]}...")
    print(f"  Limit: NONE (all visitors)")

    message_text = args.message
    if args.skip_message:
        message_text = None

    # Determine engine order
    if args.engine == "auto":
        engine_order = ENGINE_FALLBACK_ORDER
    else:
        engine_order = [args.engine]

    result = None
    errors = []

    for engine_name in engine_order:
        engine_fn = ENGINES[engine_name]
        try:
            print(f"\n>>> Trying engine: {engine_name}")
            result = engine_fn(message_text, args.dry_run, args.headless)
            if result is not None:
                print(f">>> Engine {engine_name} succeeded.")
                break
            else:
                errors.append(f"{engine_name}: returned None (login failed?)")
                print(f">>> Engine {engine_name} failed, trying next...")
        except Exception as e:
            errors.append(f"{engine_name}: {e}")
            print(f">>> Engine {engine_name} error: {e}")
            print(f">>> Trying next engine...")

    if result is None:
        print("\n=== ALL ENGINES FAILED ===")
        for err in errors:
            print(f"  - {err}")
        write_receipt("auto_visit_all_multi", {
            "errors": errors,
            "dry_run": args.dry_run,
        }, success=False)
        sys.exit(1)

    # Write receipt + data
    rpath = write_receipt("auto_visit_all_multi", {
        "visitors_found": result.get("visitors", 0),
        "visited": result.get("visited", 0),
        "messaged": result.get("messaged", 0),
        "engine_used": result.get("engine", "unknown"),
        "dry_run": args.dry_run,
        "message_sent": (args.message[:200] if not args.skip_message else "SKIPPED"),
        "errors": errors,
        "results": result.get("results", []),
    })

    save_data("auto_visit_all_latest.json", {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "engine": result.get("engine"),
        "visitors_found": result.get("visitors", 0),
        "visited": result.get("visited", 0),
        "messaged": result.get("messaged", 0),
        "visitors": result.get("visitors_data", []),
        "results": result.get("results", []),
    })

    print(f"\n=== COMPLETE ===")
    print(f"  Engine: {result.get('engine')}")
    print(f"  Visitors found: {result.get('visitors', 0)}")
    print(f"  Visited: {result.get('visited', 0)}")
    print(f"  Messaged: {result.get('messaged', 0)}")
    print(f"  Receipt: {rpath}")
    print(f"  Data: {DATA_DIR / 'auto_visit_all_latest.json'}")


if __name__ == "__main__":
    main()
