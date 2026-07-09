#!/usr/bin/env python3
"""
RentMasseur NYC Scraper + Visit All — Multi-Engine (Playwright + Puppeteer + Selenium).

Scrapes masseur/client profiles from NYC-area search results,
then visits every single one in the browser.

Engine fallback: Playwright → Puppeteer → Selenium.

Usage:
    python3 scripts/scrape_nyc_visit.py
    python3 scripts/scrape_nyc_visit.py --target 3000
    python3 scripts/scrape_nyc_visit.py --dry-run
    python3 scripts/scrape_nyc_visit.py --engine playwright
    python3 scripts/scrape_nyc_visit.py --headless
    python3 scripts/scrape_nyc_visit.py --visit-only
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
PROFILE_DIR = "/tmp/rm_nyc_scrape"

DEFAULT_MESSAGE = (
    f"Hey! I'm available today — feel free to text me at {PHONE}. "
    f"Happy to set something up."
)

NY_CITIES = [
    "manhattan-ny", "brooklyn-ny", "queens-ny", "bronx-ny",
    "staten-island-ny", "long-island-ny", "yonkers-ny", "new-york-ny",
    "jersey-city-nj", "hoboken-nj", "newark-nj", "astoria-ny",
    "harlem-ny", "flushing-ny", "bronxville-ny", "white-plains-ny",
    "scarsdale-ny", "fort-lee-nj", "union-city-nj", "bayonne-nj",
]

SKIP_USERNAMES = {
    "settings", "gay-massage", "stream", "masseurcams", "advertise",
    "about", "login", "sitemap", "topics", "robots", "api", "build-stream",
    "terms", "privacy", "contact", "help", "blog", "blogs", "search",
    "register", "signup", "forgot-password", "reset-password",
}

SCRAPE_JS = """
(skipUsernames) => {
    const result = [];
    const seen = new Set();
    const cards = document.querySelectorAll('[class*="card"], [class*="profile"], [class*="user"], [class*="listing"], [class*="result"]');
    for (const card of cards) {
        const a = card.querySelector('a[href]');
        if (a && a.href) {
            try {
                const href = a.href;
                if (!href.startsWith('https://rentmasseur.com/')) continue;
                const path = new URL(href).pathname;
                if (path && path !== '/' && path.split('/').length === 2) {
                    const username = path.replace('/', '').split('?')[0];
                    if (username && !seen.has(username) && !skipUsernames.includes(username.toLowerCase())
                        && !username.startsWith('_') && username.length > 2 && !username.match(/^\\d+$/)) {
                        seen.add(username);
                        const nameEl = card.querySelector('[class*="name"], h2, h3, h4, [class*="title"]');
                        const name = nameEl ? nameEl.textContent.trim().substring(0, 80) : username;
                        result.push({username: username, url: href.split('?')[0], name: name});
                    }
                }
            } catch(e) {}
        }
    }
    const links = Array.from(document.querySelectorAll('a[href]'));
    for (const a of links) {
        try {
            const href = a.href;
            if (!href.startsWith('https://rentmasseur.com/')) continue;
            const path = new URL(href).pathname;
            if (path && path !== '/' && path.split('/').length === 2 && path.split('/')[1] !== '') {
                const username = path.replace('/', '').split('?')[0];
                if (username && !seen.has(username) && !skipUsernames.includes(username.toLowerCase())
                    && !username.startsWith('_') && username.length > 2 && !username.match(/^\\d+$/)) {
                    seen.add(username);
                    const name = (a.textContent || a.getAttribute('alt') || username).trim().substring(0, 80);
                    result.push({username: username, url: href.split('?')[0], name: name});
                }
            }
        } catch(e) {}
    }
    const imgs = document.querySelectorAll('img[alt]');
    for (const img of imgs) {
        const alt = (img.getAttribute('alt') || '').toLowerCase();
        if (alt.includes('profile') || alt.includes('avatar') || alt.includes('user') || alt.includes('masseur')) {
            const a = img.closest('a');
            if (a && a.href) {
                try {
                    const path = new URL(a.href).pathname;
                    const username = path.replace('/', '').split('?')[0];
                    if (username && !seen.has(username) && !skipUsernames.includes(username.toLowerCase())
                        && username.length > 2 && !username.match(/^\\d+$/)) {
                        seen.add(username);
                        result.push({username: username, url: a.href.split('?')[0], name: img.getAttribute('alt').substring(0, 80)});
                    }
                } catch(e) {}
            }
        }
    }
    return result;
}
"""


def write_receipt(action, data, success=True):
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
    receipt = {"action": action, "success": success,
               "timestamp": datetime.now(timezone.utc).isoformat(), **data}
    rpath = RECEIPTS_DIR / f"{action}_{ts}.json"
    rpath.write_text(json.dumps(receipt, indent=2))
    return str(rpath)


def save_data(filename, payload):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / filename).write_text(json.dumps(payload, indent=2))


def load_saved_profiles():
    p = DATA_DIR / "nyc_scraped_profiles.json"
    if p.exists():
        return json.loads(p.read_text())
    return None


# ─── Playwright Engine ────────────────────────────────────────────────────────

def run_playwright(target_count, dry_run, headless, visit_only, message_text):
    from playwright.sync_api import sync_playwright

    print("[ENGINE] Playwright (sync)")
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

        if visit_only:
            saved = load_saved_profiles()
            if not saved:
                print("  No saved profiles. Run without --visit-only first.")
                browser.close()
                return None
            profiles = saved.get("profiles", [])
            print(f"  Loaded {len(profiles)} saved profiles.")
        else:
            profiles = _pw_scrape_nyc(page, target_count)
            save_data("nyc_scraped_profiles.json", {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "count": len(profiles), "profiles": profiles,
            })
            print(f"  Saved {len(profiles)} profiles to data/nyc_scraped_profiles.json")

        if not profiles:
            browser.close()
            return {"scraped": 0, "visited": 0, "engine": "playwright"}

        print(f"\n[3] Visiting {len(profiles)} NYC profiles...")
        results = []
        for i, v in enumerate(profiles):
            print(f"  [{i+1}/{len(profiles)}] {v['username']}...")
            r = _pw_visit(page, v, dry_run)
            results.append(r)
            if not dry_run:
                time.sleep(1.5)

        visited_ok = sum(1 for r in results if r.get("visited"))
        browser.close()
        return {"scraped": len(profiles), "visited": visited_ok,
                "engine": "playwright", "results": results, "profiles": profiles}


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


def _pw_scrape_nyc(page, target_count):
    print(f"[2] Scraping NYC search results (target: {target_count})...")
    all_profiles = []
    seen = set()

    for city in NY_CITIES:
        if len(all_profiles) >= target_count:
            break
        print(f"\n  >> {city}")
        for pg in range(1, 100):
            if len(all_profiles) >= target_count:
                break
            search_url = f"{BASE}/search?searchCity={city}&page={pg}"
            page.goto(search_url, wait_until="networkidle")
            time.sleep(2)
            _pw_wait_captcha(page)

            for _ in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(0.5)

            found = page.evaluate(SCRAPE_JS, list(SKIP_USERNAMES))
            new = 0
            for v in found:
                if v["username"] not in seen:
                    seen.add(v["username"])
                    v["city"] = city
                    all_profiles.append(v)
                    new += 1
                    if len(all_profiles) >= target_count:
                        break

            print(f"    page {pg}: +{new} (total: {len(all_profiles)})")
            if new == 0 and pg > 1:
                break
            if not found:
                break

    return all_profiles[:target_count]


def _pw_visit(page, profile, dry_run):
    uname = profile["username"]
    url = profile["url"]
    result = {"username": uname, "url": url, "visited": False, "city": profile.get("city", "")}

    page.goto(url, wait_until="networkidle")
    time.sleep(2)
    result["visited"] = True
    try:
        result["page_title"] = page.title()[:60]
    except Exception:
        result["page_title"] = ""

    if dry_run:
        print(f"  [DRY] visited {uname}")
    else:
        print(f"  visited {uname}: {result.get('page_title', '')}")
    return result


# ─── Puppeteer Engine (pyppeteer) ─────────────────────────────────────────────

async def run_puppeteer_async(target_count, dry_run, headless, visit_only, message_text):
    import pyppeteer

    print("[ENGINE] Puppeteer (pyppeteer)")
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
        await asyncio.wait_for(page.waitForNavigation({"waitUntil": "networkidle2"}), timeout=15)
    except Exception:
        pass
    time.sleep(5)
    await _pp_wait_captcha(page)

    url = page.url
    if "login" in url.lower():
        print("  Login FAILED.")
        await browser.close()
        return None
    print(f"  Login OK: {url}")

    if visit_only:
        saved = load_saved_profiles()
        if not saved:
            print("  No saved profiles. Run without --visit-only first.")
            await browser.close()
            return None
        profiles = saved.get("profiles", [])
        print(f"  Loaded {len(profiles)} saved profiles.")
    else:
        profiles = await _pp_scrape_nyc(page, target_count)
        save_data("nyc_scraped_profiles.json", {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": len(profiles), "profiles": profiles,
        })
        print(f"  Saved {len(profiles)} profiles to data/nyc_scraped_profiles.json")

    if not profiles:
        await browser.close()
        return {"scraped": 0, "visited": 0, "engine": "puppeteer"}

    print(f"\n[3] Visiting {len(profiles)} NYC profiles...")
    results = []
    for i, v in enumerate(profiles):
        print(f"  [{i+1}/{len(profiles)}] {v['username']}...")
        r = await _pp_visit(page, v, dry_run)
        results.append(r)
        if not dry_run:
            time.sleep(1.5)

    visited_ok = sum(1 for r in results if r.get("visited"))
    await browser.close()
    return {"scraped": len(profiles), "visited": visited_ok,
            "engine": "puppeteer", "results": results, "profiles": profiles}


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


async def _pp_scrape_nyc(page, target_count):
    print(f"[2] Scraping NYC search results (target: {target_count})...")
    all_profiles = []
    seen = set()

    for city in NY_CITIES:
        if len(all_profiles) >= target_count:
            break
        print(f"\n  >> {city}")
        for pg in range(1, 100):
            if len(all_profiles) >= target_count:
                break
            search_url = f"{BASE}/search?searchCity={city}&page={pg}"
            await page.goto(search_url, {"waitUntil": "networkidle2"})
            time.sleep(2)
            await _pp_wait_captcha(page)

            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(0.5)

            found = await page.evaluate(SCRAPE_JS, list(SKIP_USERNAMES))
            new = 0
            for v in found:
                if v["username"] not in seen:
                    seen.add(v["username"])
                    v["city"] = city
                    all_profiles.append(v)
                    new += 1
                    if len(all_profiles) >= target_count:
                        break

            print(f"    page {pg}: +{new} (total: {len(all_profiles)})")
            if new == 0 and pg > 1:
                break
            if not found:
                break

    return all_profiles[:target_count]


async def _pp_visit(page, profile, dry_run):
    uname = profile["username"]
    url = profile["url"]
    result = {"username": uname, "url": url, "visited": False, "city": profile.get("city", "")}

    await page.goto(url, {"waitUntil": "networkidle2"})
    time.sleep(2)
    result["visited"] = True
    try:
        result["page_title"] = (await page.title())[:60]
    except Exception:
        result["page_title"] = ""

    if dry_run:
        print(f"  [DRY] visited {uname}")
    else:
        print(f"  visited {uname}: {result.get('page_title', '')}")
    return result


def run_puppeteer(target_count, dry_run, headless, visit_only, message_text):
    return asyncio.get_event_loop().run_until_complete(
        run_puppeteer_async(target_count, dry_run, headless, visit_only, message_text)
    )


# ─── Selenium Engine (undetected-chromedriver) ────────────────────────────────

def run_selenium(target_count, dry_run, headless, visit_only, message_text):
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

        if visit_only:
            saved = load_saved_profiles()
            if not saved:
                print("  No saved profiles. Run without --visit-only first.")
                driver.quit()
                return None
            profiles = saved.get("profiles", [])
            print(f"  Loaded {len(profiles)} saved profiles.")
        else:
            profiles = _sel_scrape_nyc(driver, target_count)
            save_data("nyc_scraped_profiles.json", {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "count": len(profiles), "profiles": profiles,
            })
            print(f"  Saved {len(profiles)} profiles to data/nyc_scraped_profiles.json")

        if not profiles:
            driver.quit()
            return {"scraped": 0, "visited": 0, "engine": "selenium"}

        print(f"\n[3] Visiting {len(profiles)} NYC profiles...")
        results = []
        for i, v in enumerate(profiles):
            print(f"  [{i+1}/{len(profiles)}] {v['username']}...")
            r = _sel_visit(driver, v, dry_run)
            results.append(r)
            if not dry_run:
                time.sleep(1.5)

        visited_ok = sum(1 for r in results if r.get("visited"))
        driver.quit()
        return {"scraped": len(profiles), "visited": visited_ok,
                "engine": "selenium", "results": results, "profiles": profiles}
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


def _sel_scrape_nyc(driver, target_count):
    print(f"[2] Scraping NYC search results (target: {target_count})...")
    all_profiles = []
    seen = set()

    for city in NY_CITIES:
        if len(all_profiles) >= target_count:
            break
        print(f"\n  >> {city}")
        for pg in range(1, 100):
            if len(all_profiles) >= target_count:
                break
            search_url = f"{BASE}/search?searchCity={city}&page={pg}"
            driver.get(search_url)
            time.sleep(3)
            _sel_wait_captcha(driver)

            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(0.5)

            found = driver.execute_script(SCRAPE_JS, list(SKIP_USERNAMES))
            new = 0
            for v in found:
                if v["username"] not in seen:
                    seen.add(v["username"])
                    v["city"] = city
                    all_profiles.append(v)
                    new += 1
                    if len(all_profiles) >= target_count:
                        break

            print(f"    page {pg}: +{new} (total: {len(all_profiles)})")
            if new == 0 and pg > 1:
                break
            if not found:
                break

    return all_profiles[:target_count]


def _sel_visit(driver, profile, dry_run):
    uname = profile["username"]
    url = profile["url"]
    result = {"username": uname, "url": url, "visited": False, "city": profile.get("city", "")}

    driver.get(url)
    time.sleep(2)
    result["visited"] = True
    try:
        result["page_title"] = driver.title[:60]
    except Exception:
        result["page_title"] = ""

    if dry_run:
        print(f"  [DRY] visited {uname}")
    else:
        print(f"  visited {uname}: {result.get('page_title', '')}")
    return result


# ─── Main ─────────────────────────────────────────────────────────────────────

ENGINES = {
    "playwright": run_playwright,
    "puppeteer": run_puppeteer,
    "selenium": run_selenium,
}
ENGINE_FALLBACK_ORDER = ["playwright", "puppeteer", "selenium"]


def main():
    parser = argparse.ArgumentParser(description="Scrape NYC profiles + visit all — Playwright/Puppeteer/Selenium")
    parser.add_argument("--target", type=int, default=3000, help="Number of profiles to scrape (default 3000)")
    parser.add_argument("--dry-run", action="store_true", help="Scrape only, don't visit")
    parser.add_argument("--engine", type=str, default="auto", choices=["auto", "playwright", "puppeteer", "selenium"])
    parser.add_argument("--headless", action="store_true", help="Run headless (captcha may block)")
    parser.add_argument("--visit-only", action="store_true", help="Skip scraping, use saved data/nyc_scraped_profiles.json")
    args = parser.parse_args()

    print("=== RENTMASSEUR NYC SCRAPE + VISIT ALL (Multi-Engine) ===")
    print(f"  Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print(f"  Engine: {args.engine}")
    print(f"  Headless: {args.headless}")
    print(f"  Target: {args.target} NYC profiles")
    print(f"  Cities: {len(NY_CITIES)} NYC-area cities")

    engine_order = ENGINE_FALLBACK_ORDER if args.engine == "auto" else [args.engine]
    result = None
    errors = []

    for engine_name in engine_order:
        engine_fn = ENGINES[engine_name]
        try:
            print(f"\n>>> Trying engine: {engine_name}")
            result = engine_fn(args.target, args.dry_run, args.headless, args.visit_only, DEFAULT_MESSAGE)
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
        write_receipt("nyc_scrape_visit", {"errors": errors, "dry_run": args.dry_run}, success=False)
        sys.exit(1)

    rpath = write_receipt("nyc_scrape_visit", {
        "scraped": result.get("scraped", 0),
        "visited": result.get("visited", 0),
        "engine_used": result.get("engine", "unknown"),
        "dry_run": args.dry_run,
        "target": args.target,
        "cities": NY_CITIES,
        "errors": errors,
        "results": result.get("results", []),
    })

    save_data("nyc_scrape_visit_latest.json", {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "engine": result.get("engine"),
        "scraped": result.get("scraped", 0),
        "visited": result.get("visited", 0),
        "profiles": result.get("profiles", []),
        "results": result.get("results", []),
    })

    print(f"\n=== COMPLETE ===")
    print(f"  Engine: {result.get('engine')}")
    print(f"  Scraped: {result.get('scraped', 0)}")
    print(f"  Visited: {result.get('visited', 0)}")
    print(f"  Receipt: {rpath}")
    print(f"  Data: {DATA_DIR / 'nyc_scrape_visit_latest.json'}")


if __name__ == "__main__":
    main()
