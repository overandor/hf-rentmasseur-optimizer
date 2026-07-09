#!/usr/bin/env python3
"""
Manual captcha solve + cookie extractor.

Opens Chrome with undetected-chromedriver, navigates to rentmasseur.com/login.
You manually solve the captcha and login.
Once logged in, it extracts cookies and saves them for use by other scripts.

Usage:
    python3 scripts/extract_cookies.py
"""
import json
import os
import time
from pathlib import Path

import undetected_chromedriver as uc

BASE = "https://rentmasseur.com"
USERNAME = "karpathianwolf"
PASSWORD = os.environ.get("RM_PASSWORD", "")
COOKIE_FILE = Path(__file__).resolve().parent.parent / "data" / "rentmasseur_cookies.json"


def main():
    print("=== AUTO COOKIE EXTRACTOR ===")
    print("Using undetected-chromedriver to bypass captcha and auto-login...")

    opts = uc.ChromeOptions()
    opts.add_argument("--window-size=1280,900")
    driver = uc.Chrome(options=opts, version_main=149)

    try:
        driver.get(f"{BASE}/login")
        print("Waiting for page load and captcha bypass (60s)...")
        time.sleep(60)

        # Check if captcha is still present
        src = driver.page_source or ""
        if "crowdsec" in src.lower() or "captcha" in src.lower():
            print("Captcha still present. Trying to click checkbox...")
            try:
                checkbox = driver.find_element("css selector", "input[type='checkbox']")
                if checkbox.is_displayed():
                    checkbox.click()
                    time.sleep(10)
            except:
                pass

        # Try auto-login with JS
        print("Attempting auto-login...")
        driver.execute_script("""
            const pwd = document.querySelector('input[type="password"]');
            const user = document.querySelector('input[type="text"], input[type="email"]');
            const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            if (user) { ns.call(user, arguments[0]); user.dispatchEvent(new Event('input', {bubbles: true})); }
            if (pwd) { ns.call(pwd, arguments[1]); pwd.dispatchEvent(new Event('input', {bubbles: true})); }
        """, USERNAME, PASSWORD)
        time.sleep(1)
        try:
            pwd = driver.find_element("css selector", "input[type='password']")
            pwd.send_keys("\n")
        except:
            pass

        print("Waiting for login (10s)...")
        time.sleep(10)

        # Check if logged in
        src = driver.page_source or ""
        if "login" in driver.current_url.lower() or "crowdsec" in src.lower():
            print("Auto-login failed. Cookies not extracted.")
            driver.quit()
            return

        # Extract cookies
        cookies = []
        for c in driver.get_cookies():
            cookies.append({
                "name": c["name"],
                "value": c["value"],
                "domain": c.get("domain", ""),
                "path": c.get("path", "/"),
                "expiry": c.get("expiry"),
                "secure": c.get("secure", False),
                "httpOnly": c.get("httpOnly", False),
            })

        # Also get localStorage token
        try:
            access_token = driver.execute_script("return localStorage.getItem('accessToken') || '';")
            if access_token:
                cookies.append({"name": "accessToken", "value": access_token, "domain": ".rentmasseur.com", "path": "/"})
        except:
            pass

        # Save cookies
        COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(COOKIE_FILE, "w") as f:
            json.dump(cookies, f, indent=2)

        print(f"Saved {len(cookies)} cookies to: {COOKIE_FILE}")
        print("Success! Now run: python3 scripts/ny_visit_profile_cookies.py")

    finally:
        time.sleep(2)
        driver.quit()


if __name__ == "__main__":
    main()
