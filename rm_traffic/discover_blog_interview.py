"""
Discover Blog + Interview API endpoints via Selenium CDP.

Uses the existing logged-in Chrome profile to avoid login/captcha.
Opens the blog and interview editor pages and captures the exact network
requests when saving/publishing.

Usage:
    python3 rm_traffic/discover_blog_interview.py

Output:
    rm_traffic/blog_interview_endpoints.json
"""

import json
import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

BASE = "https://rentmasseur.com"
PROFILE = "/tmp/rm_action_api"


def get_driver():
    opts = Options()
    opts.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument(f"--user-data-dir={PROFILE}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    return webdriver.Chrome(options=opts)


def dismiss_popups(driver):
    time.sleep(1)
    try:
        driver.execute_script("document.querySelectorAll('.DialogOverlay,[class*=\"overlay\"]').forEach(e=>e.remove())")
    except Exception:
        pass


def get_api_calls(driver):
    logs = driver.get_log("performance")
    reqs = {}
    for entry in logs:
        try:
            msg = json.loads(entry["message"])["message"]
            if msg["method"] == "Network.requestWillBeSent":
                p = msg["params"]
                r = p["request"]
                rid = p["requestId"]
                reqs[rid] = {
                    "url": r["url"],
                    "method": r["method"],
                    "postData": r.get("postData", "")[:2000],
                }
            elif msg["method"] == "Network.responseReceived":
                p = msg["params"]
                rid = p["requestId"]
                if rid in reqs:
                    reqs[rid]["status"] = p["response"]["status"]
                    try:
                        body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": rid})
                        reqs[rid]["response"] = body.get("body", "")[:2000]
                    except Exception:
                        pass
        except Exception:
            pass
    return [v for v in reqs.values() if "/api/" in v["url"]]


def find_clickable(driver, texts):
    for text in texts:
        for el in driver.find_elements(By.XPATH, f"//*[contains(text(),'{text}')]"):
            if el.is_displayed():
                return el
    return None


def discover_blog(driver):
    print("\n=== BLOG DISCOVERY ===")
    driver.get(f"{BASE}/settings?blog=1")
    time.sleep(5)
    dismiss_popups(driver)
    print(f"URL: {driver.current_url}")

    # List possible buttons
    buttons = driver.find_elements(By.TAG_NAME, "button")
    print(f"Buttons found: {len(buttons)}")
    for b in buttons:
        txt = (b.text or "").strip()
        if txt:
            print(f"  Button: {txt[:50]}")

    # Try to click "Create" or "New"
    for action_text in ["Create", "New", "Add", "Write", "Post"]:
        el = find_clickable(driver, [action_text])
        if el:
            print(f"Clicking '{action_text}'...")
            driver.execute_script("arguments[0].click()", el)
            time.sleep(3)
            break

    # Clear logs and try to find form
    driver.get_log("performance")
    textareas = driver.find_elements(By.TAG_NAME, "textarea")
    inputs = driver.find_elements(By.TAG_NAME, "input")
    print(f"Textareas: {len(textareas)}, Inputs: {len(inputs)}")
    for i, ta in enumerate(textareas):
        print(f"  textarea[{i}]: placeholder={ta.get_attribute('placeholder') or 'N/A'}")
    for i, inp in enumerate(inputs):
        t = inp.get_attribute("type") or "text"
        if t in ("text", "email", "search"):
            print(f"  input[{i}]: type={t} placeholder={inp.get_attribute('placeholder') or 'N/A'}")

    # Save action
    save_btn = find_clickable(driver, ["Save", "Submit", "Publish", "Create", "Post"])
    if save_btn:
        print("Clicking save...")
        driver.execute_script("arguments[0].click()", save_btn)
        time.sleep(3)
        calls = get_api_calls(driver)
        print(f"Captured {len(calls)} API calls")
        for c in calls:
            print(f"  {c['method']:4s} {c.get('status','?')} {c['url'][:80]}")
        return calls
    else:
        print("No save button found")
        return []


def discover_interview(driver):
    print("\n=== INTERVIEW DISCOVERY ===")
    driver.get(f"{BASE}/settings?interview=1")
    time.sleep(5)
    dismiss_popups(driver)
    print(f"URL: {driver.current_url}")

    # List inputs and buttons
    textareas = driver.find_elements(By.TAG_NAME, "textarea")
    inputs = driver.find_elements(By.TAG_NAME, "input")
    buttons = driver.find_elements(By.TAG_NAME, "button")
    print(f"Textareas: {len(textareas)}, Inputs: {len(inputs)}, Buttons: {len(buttons)}")
    for i, ta in enumerate(textareas):
        print(f"  textarea[{i}]: placeholder={ta.get_attribute('placeholder') or 'N/A'}")
    for b in buttons:
        txt = (b.text or "").strip()
        if txt:
            print(f"  Button: {txt[:50]}")

    # Clear logs and try to save
    driver.get_log("performance")
    save_btn = find_clickable(driver, ["Save", "Submit", "Update", "Confirm"])
    if save_btn:
        print("Clicking save...")
        driver.execute_script("arguments[0].click()", save_btn)
        time.sleep(3)
        calls = get_api_calls(driver)
        print(f"Captured {len(calls)} API calls")
        for c in calls:
            print(f"  {c['method']:4s} {c.get('status','?')} {c['url'][:80]}")
        return calls
    else:
        print("No save button found")
        return []


def main():
    driver = get_driver()
    try:
        blog_calls = discover_blog(driver)
        interview_calls = discover_interview(driver)
        out = {
            "blog": blog_calls,
            "interview": interview_calls,
            "timestamp": time.time(),
        }
        Path("rm_traffic/blog_interview_endpoints.json").write_text(
            json.dumps(out, indent=2, default=str)
        )
        print("\nSaved to rm_traffic/blog_interview_endpoints.json")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
