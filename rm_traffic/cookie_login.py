"""
Cookie-based reconnection — uses an existing logged-in Chrome profile to
extract a fresh token or valid cookies without solving captcha.

The earlier Selenium runs (rm_action_api, rm_cdp_api, rm_profileops) may
have valid session cookies in /tmp. This script tries them in order.
"""

import json
import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

BASE_URL = "https://rentmasseur.com"
API_URL = f"{BASE_URL}/api/v1"

PROFILES = [
    "/tmp/rm_action_api",
    "/tmp/rm_cdp_api",
    "/tmp/rm_profileops",
]


def create_driver(profile: str):
    opts = Options()
    opts.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument(f"--user-data-dir={profile}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    return webdriver.Chrome(options=opts)


def extract_session(driver):
    """Extract cookies and localStorage token from a logged-in session."""
    driver.get(f"{BASE_URL}/settings")
    time.sleep(5)
    url = driver.current_url
    cookies = driver.get_cookies()
    token = None
    try:
        token = driver.execute_script("return localStorage.getItem('accessToken') || sessionStorage.getItem('accessToken')")
    except Exception:
        pass
    return {
        "url": url,
        "cookies": cookies,
        "token": token,
    }


def try_profile(profile: str):
    print(f"Trying profile: {profile}")
    if not Path(profile).exists():
        print(f"  Profile not found: {profile}")
        return None
    driver = None
    try:
        driver = create_driver(profile)
        data = extract_session(driver)
        print(f"  URL: {data['url']}")
        print(f"  Token: {data['token'][:30] + '...' if data['token'] else 'None'}")
        print(f"  Cookies: {len(data['cookies'])}")
        if "/login" not in data["url"]:
            print(f"  ✓ Profile {profile} is logged in")
            return data
        else:
            print(f"  ✗ Profile {profile} is logged out")
            return None
    except Exception as e:
        print(f"  Error: {e}")
        return None
    finally:
        if driver:
            driver.quit()


def main():
    for profile in PROFILES:
        data = try_profile(profile)
        if data:
            print("\nSaving session to rm_traffic/session.json")
            with open("rm_traffic/session.json", "w") as f:
                json.dump(data, f, indent=2, default=str)
            print("Done. You can now use this session for API calls.")
            return
    print("\nNo valid logged-in profiles found. Need to wait for cooldown or login fresh.")


if __name__ == "__main__":
    main()
