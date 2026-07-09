#!/usr/bin/env python3
"""
Visit ALL profiles who visited you on RentMasseur.

Uses persistent Chrome profile to bypass CrowdSec.
First run: solve captcha manually in the browser window if needed.
Subsequent runs: cookies persist, no captcha.

Usage:
    python3 scripts/visit_all_visitors.py              # visit all
    python3 scripts/visit_all_visitors.py --limit 50   # limit
    python3 scripts/visit_all_visitors.py --dry-run     # list only
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

BASE = "https://rentmasseur.com"
USERNAME = "karpathianwolf"
PASSWORD = os.environ.get("RM_PASSWORD", "")
PROFILE_DIR = "/tmp/rm_visit_pipe"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RECEIPTS_DIR = Path(__file__).resolve().parent.parent / "receipts"


def get_driver():
    os.makedirs(PROFILE_DIR, exist_ok=True)
    opts = Options()
    opts.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1280,900")
    opts.add_argument(f"--user-data-dir={PROFILE_DIR}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    return webdriver.Chrome(options=opts)


def login(driver, max_wait=180):
    print("[1] Navigating to rentmasseur.com...")
    driver.get(BASE)
    time.sleep(4)

    # Check if already logged in (cookies from previous session)
    try:
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
        if "log out" in body or "logout" in body or "my account" in body or "settings" in body:
            print("  Already logged in via saved cookies!")
            return True
    except:
        pass

    # Check for CrowdSec captcha
    src = driver.page_source or ""
    if "crowdsec" in src.lower() or "captcha" in src.lower():
        print("  CrowdSec captcha detected. Solve it in the browser window.")
        print(f"  Waiting up to {max_wait}s for captcha clearance...")
        for i in range(max_wait // 3):
            time.sleep(3)
            src = driver.page_source or ""
            if "crowdsec" not in src.lower() and "captcha" not in src.lower():
                print("  Captcha cleared!")
                break
        else:
            print("  Captcha not cleared in time.")
            return False

    # Do fresh login
    print("  Doing fresh login...")
    driver.get(f"{BASE}/login")
    time.sleep(4)

    # Wait for password field
    pwd = None
    for _ in range(15):
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
            if elements and elements[0].is_displayed():
                pwd = elements[0]
                break
        except:
            pass
        time.sleep(1)

    if not pwd:
        print("  No password field found. Screenshot saved.")
        driver.save_screenshot("/tmp/rm_login_fail.png")
        return False

    # Fill email
    email = None
    for sel in ["input[name='email']", "input[type='email']", "input[type='text']", "input[placeholder*='mail']"]:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, sel)
            if elements and elements[0].is_displayed():
                email = elements[0]
                break
        except:
            pass

    if email:
        email.clear()
        email.send_keys(USERNAME)
    pwd.clear()
    pwd.send_keys(PASSWORD)
    time.sleep(0.5)

    # Submit
    for sel in ["button[type='submit']", "button"]:
        try:
            btn = driver.find_elements(By.CSS_SELECTOR, sel)
            if btn and btn[0].is_displayed():
                btn[0].click()
                break
        except:
            pass

    time.sleep(5)

    # Check captcha again after submit
    src = driver.page_source or ""
    if "crowdsec" in src.lower() or "captcha" in src.lower():
        print("  Captcha after submit. Solve in browser, waiting up to 120s...")
        for i in range(40):
            time.sleep(3)
            src = driver.page_source or ""
            if "crowdsec" not in src.lower() and "captcha" not in src.lower():
                break
        time.sleep(3)

    ok = "login" not in driver.current_url.lower()
    print(f"  Login {'OK' if ok else 'FAILED'}: {driver.current_url}")
    return ok


def scrape_whosawme(driver):
    """Scrape all visitor usernames from /settings/whosawme with pagination."""
    print("[2] Scraping Who Saw Me...")
    all_visitors = []
    seen = set()

    for page in range(1, 50):
        driver.get(f"{BASE}/settings/whosawme?page={page}")
        time.sleep(4)

        # Check for captcha
        src = driver.page_source or ""
        if "crowdsec" in src.lower():
            print(f"  Captcha on page {page}. Waiting for clearance...")
            for _ in range(30):
                time.sleep(3)
                src = driver.page_source or ""
                if "crowdsec" not in src.lower():
                    break

        # Scroll to load all content
        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

        visitors = driver.execute_script("""
            const result = [];
            const seen = new Set();
            const skip = new Set(['settings','gay-massage','stream','masseurcams','advertise',
                'about','login','sitemap','topics','robots','api','build-stream',
                'terms','privacy','contact','help','blog','blogs']);

            // Method 1: Links to profiles
            const links = Array.from(document.querySelectorAll('a[href]'));
            for (const a of links) {
                try {
                    const href = a.href;
                    if (!href.startsWith('https://rentmasseur.com/')) continue;
                    const path = new URL(href).pathname;
                    if (path && path !== '/' && path.split('/').length === 2) {
                        const username = path.replace('/', '').split('?')[0];
                        if (username && !seen.has(username) && !skip.has(username.toLowerCase())
                            && !username.startsWith('_') && username.length > 2
                            && !username.match(/^\\d+$/)) {
                            seen.add(username);
                            result.push({username: username, url: href.split('?')[0]});
                        }
                    }
                } catch(e) {}
            }

            // Method 2: Profile images with alt text
            const imgs = document.querySelectorAll('img[alt]');
            for (const img of imgs) {
                const alt = img.getAttribute('alt').toLowerCase();
                if (alt.includes('profile') || alt.includes('avatar') || alt.includes('user')) {
                    const a = img.closest('a');
                    if (a && a.href) {
                        try {
                            const path = new URL(a.href).pathname;
                            const username = path.replace('/', '').split('?')[0];
                            if (username && !seen.has(username) && !skip.has(username.toLowerCase())
                                && username.length > 2 && !username.match(/^\\d+$/)) {
                                seen.add(username);
                                result.push({username: username, url: a.href.split('?')[0]});
                            }
                        } catch(e) {}
                    }
                }
            }

            return result;
        """)

        new_count = 0
        for v in visitors:
            if v["username"] not in seen:
                seen.add(v["username"])
                all_visitors.append(v)
                new_count += 1

        print(f"  Page {page}: {len(visitors)} found, {new_count} new (total: {len(all_visitors)})")

        if new_count == 0 and page > 1:
            print("  No new visitors — reached end of list.")
            break

        if not visitors:
            print("  Empty page — done.")
            break

    print(f"  Total unique visitors: {len(all_visitors)}")
    return all_visitors


def visit_profiles_concurrent(visitors, token, cookies, limit=500, dry_run=False):
    """Visit profiles concurrently using requests (faster than Selenium)."""
    targets = visitors[:limit]
    print(f"\n[3] Visiting {len(targets)} profiles concurrently...")

    if dry_run:
        for v in targets:
            print(f"  [DRY] {v['username']}")
        return [{"username": v["username"], "status": "dry_run"} for v in targets]

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Authorization": token,
        "Referer": "https://rentmasseur.com/settings/whosawme",
    }

    results = []
    t0 = time.time()

    def visit_one(v):
        try:
            resp = requests.get(v["url"], headers=headers, cookies=cookies, timeout=15, allow_redirects=True)
            return {"username": v["username"], "status": resp.status_code, "bytes": len(resp.text)}
        except Exception as e:
            return {"username": v["username"], "status": "error", "error": str(e)[:80]}

    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(visit_one, v): v for v in targets}
        for i, fut in enumerate(as_completed(futures)):
            r = fut.result()
            results.append(r)
            if (i + 1) % 50 == 0 or i == len(targets) - 1:
                ok = sum(1 for x in results if x["status"] == 200)
                print(f"  [{i+1}/{len(targets)}] {r['username']}: {r['status']} (OK: {ok})")

    elapsed = time.time() - t0
    success = sum(1 for r in results if r["status"] == 200)
    print(f"\n  Done: {len(results)} visited, {success} OK, {elapsed:.1f}s")
    return results


def write_receipt(data):
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
    receipt = {
        "action": "visit_all_visitors",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **data,
    }
    rpath = RECEIPTS_DIR / f"visit_all_visitors_{ts}.json"
    rpath.write_text(json.dumps(receipt, indent=2))
    return str(rpath)


def main():
    parser = argparse.ArgumentParser(description="Visit all profiles who visited you")
    parser.add_argument("--dry-run", action="store_true", help="List visitors without visiting")
    parser.add_argument("--limit", type=int, default=500, help="Max profiles to visit")
    parser.add_argument("--scrape-only", action="store_true", help="Only scrape visitor list, don't visit")
    args = parser.parse_args()

    print("=== RENTMASSEUR VISIT ALL VISITORS ===")
    print(f"  Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print(f"  Limit: {args.limit}")

    driver = get_driver()
    try:
        if not login(driver):
            print("Login failed. Aborting.")
            sys.exit(1)

        # Scrape whosawme
        visitors = scrape_whosawme(driver)
        if not visitors:
            print("No visitors found. Exiting.")
            write_receipt({"visitors": 0, "visited": 0})
            return

        # Save visitor list
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "visitors_whosawme.json").write_text(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": len(visitors),
            "visitors": visitors,
        }, indent=2))
        print(f"  Saved visitor list: {DATA_DIR / 'visitors_whosawme.json'}")

        if args.scrape_only:
            print("\nScrape-only mode. Done.")
            write_receipt({"visitors": len(visitors), "visited": 0, "scrape_only": True})
            return

        # Extract token + cookies for concurrent visits
        token = ""
        cookies = {}
        for c in driver.get_cookies():
            cookies[c["name"]] = c["value"]
            if c["name"] == "accessToken":
                token = f"Bearer {c['value']}"

        # Also try getting token from localStorage
        if not token:
            try:
                ls_token = driver.execute_script("return localStorage.getItem('accessToken') || '';")
                if ls_token:
                    token = f"Bearer {ls_token}"
            except:
                pass

        if not token:
            print("  No auth token found. Falling back to Selenium visits (slower)...")
            results = []
            for i, v in enumerate(visitors[:args.limit]):
                try:
                    driver.get(v["url"])
                    time.sleep(1)
                    results.append({"username": v["username"], "status": 200, "title": driver.title[:40]})
                    if (i+1) % 50 == 0:
                        print(f"  [{i+1}/{min(len(visitors), args.limit)}] visited")
                except Exception as e:
                    results.append({"username": v["username"], "status": "error", "error": str(e)[:60]})
        else:
            results = visit_profiles_concurrent(visitors, token, cookies, args.limit, args.dry_run)

        # Write receipt
        success = sum(1 for r in results if r.get("status") == 200)
        rpath = write_receipt({
            "visitors_found": len(visitors),
            "visited": len(results),
            "success_200": success,
            "dry_run": args.dry_run,
            "results": results,
        })

        # Save final data
        (DATA_DIR / "visit_all_visitors_latest.json").write_text(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "visitors_found": len(visitors),
            "visited": len(results),
            "success": success,
            "results": results,
        }, indent=2))

        print(f"\n=== COMPLETE ===")
        print(f"  Visitors found: {len(visitors)}")
        print(f"  Visited: {len(results)}")
        print(f"  Success (200): {success}")
        print(f"  Receipt: {rpath}")
        print(f"  Data: {DATA_DIR / 'visit_all_visitors_latest.json'}")

    finally:
        input("\nPress Enter to close browser...")
        driver.quit()


if __name__ == "__main__":
    main()
