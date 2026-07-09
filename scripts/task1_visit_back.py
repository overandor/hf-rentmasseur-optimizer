#!/usr/bin/env python3
"""Task 1: Visit-back via Selenium. Independent tiny Chrome window.
Visits every client profile page that messaged you."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json, time, os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

PROFILE_DIR = "/tmp/rm_task1"
BASE = "https://rentmasseur.com"

def get_driver():
    opts = Options()
    opts.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=400,300")
    opts.add_argument("--window-position=0,0")
    opts.add_argument(f"--user-data-dir={PROFILE_DIR}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    return webdriver.Chrome(options=opts)

def main():
    os.makedirs(PROFILE_DIR, exist_ok=True)
    driver = get_driver()
    try:
        from rm_traffic.api_client import RentMasseurAPI
        api = RentMasseurAPI()
        api.login(os.environ.get("RM_USER", ""), os.environ.get("RM_PASS", ""))
        token = api.session.headers.get("Authorization", "").replace("Bearer ", "")
        driver.get(BASE)
        time.sleep(1)
        for c in api.session.cookies:
            driver.add_cookie({"name": c.name, "value": c.value, "domain": c.domain or ".rentmasseur.com"})
        driver.add_cookie({"name": "accessToken", "value": token, "domain": ".rentmasseur.com"})

        usernames = set()
        for page in range(1, 5):
            mail = api.get_mailbox(page=page, folder=1)
            for e in mail.get("emails", []):
                u = e.get("userCard", {}).get("username", "")
                if u: usernames.add(u)
        usernames = sorted(usernames)
        print(f"[task1] {len(usernames)} clients to visit")

        visited = []
        for u in usernames:
            try:
                driver.get(f"{BASE}/{u}")
                time.sleep(0.5)
                visited.append({"username": u, "status": "visited", "title": driver.title[:40]})
                print(f"[task1] {u}: {driver.title[:40]}")
            except Exception as e:
                visited.append({"username": u, "status": "error", "error": str(e)[:60]})
        with open("data/task1_visit_back.json", "w") as f:
            json.dump({"count": len(visited), "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "visited": visited}, f, indent=2)
        print(f"[task1] Done: {len(visited)} visited")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
