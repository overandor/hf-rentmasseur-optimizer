#!/usr/bin/env python3
"""Task 2: Blog posting via Selenium. Independent tiny Chrome window.
Brute-forces the blog editor: opens settings?blog=1, fills form, clicks save.
Captures the network call to discover the real API endpoint."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json, time, os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

PROFILE_DIR = "/tmp/rm_task2"
BASE = "https://rentmasseur.com"

def get_driver():
    opts = Options()
    opts.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=400,300")
    opts.add_argument("--window-position=420,0")
    opts.add_argument(f"--user-data-dir={PROFILE_DIR}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    return webdriver.Chrome(options=opts)

def dismiss_popups(driver):
    time.sleep(1)
    try:
        driver.execute_script("document.querySelectorAll('.DialogOverlay,[class*=\"overlay\"]').forEach(e=>e.remove())")
    except: pass

def find_clickable(driver, texts):
    for text in texts:
        for el in driver.find_elements(By.XPATH, f"//*[contains(text(),'{text}')]"):
            if el.is_displayed(): return el
    return None

def main():
    title = os.getenv("BLOG_TITLE", "Deep Tissue Recovery: What 75,000 Profile Views Taught Me")
    body = os.getenv("BLOG_BODY", """Most clients don't know the difference between deep tissue and Swedish. Here's what I've learned from years of focused bodywork in Manhattan.

Deep tissue isn't about pressing harder. It's about targeting the right layers. When your shoulders live near your ears, you need someone who understands anatomy, not just pressure.

Key insights:
- Neck and shoulder tension accounts for 80% of complaints
- Hip flexor tightness is the hidden cause of lower back pain
- Consistent sessions outperform occasional deep work

If you're carrying stress in your body, focused recovery beats generic relaxation every time.""")

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

        # Navigate to blog editor
        print("[task2] Opening blog editor...")
        driver.get(f"{BASE}/settings?blog=1")
        time.sleep(5)
        dismiss_popups(driver)
        print(f"[task2] URL: {driver.current_url}")

        # Find and click Create/New button
        for action_text in ["Create", "New", "Add", "Write", "Post", "Create Blog", "New Post"]:
            el = find_clickable(driver, [action_text])
            if el:
                print(f"[task2] Clicking '{action_text}'...")
                driver.execute_script("arguments[0].click()", el)
                time.sleep(3)
                break

        # Find form fields and fill them
        textareas = driver.find_elements(By.TAG_NAME, "textarea")
        inputs = driver.find_elements(By.TAG_NAME, "input")
        print(f"[task2] Found {len(textareas)} textareas, {len(inputs)} inputs")

        # Fill title (usually first input or textarea)
        filled_title = False
        for inp in inputs:
            t = inp.get_attribute("type") or "text"
            if t in ("text", "search"):
                ph = inp.get_attribute("placeholder") or ""
                if "title" in ph.lower() or "title" in (inp.get_attribute("name") or "").lower() or not filled_title:
                    inp.clear()
                    inp.send_keys(title)
                    filled_title = True
                    print(f"[task2] Filled title in input: {ph}")
                    break

        if not filled_title and textareas:
            textareas[0].clear()
            textareas[0].send_keys(title)
            filled_title = True
            print("[task2] Filled title in first textarea")

        # Fill body (usually a textarea with description/body placeholder)
        filled_body = False
        for ta in textareas:
            ph = ta.get_attribute("placeholder") or ""
            name = ta.get_attribute("name") or ""
            if any(x in (ph + name).lower() for x in ["body", "content", "description", "blog", "post"]):
                ta.clear()
                ta.send_keys(body)
                filled_body = True
                print(f"[task2] Filled body in textarea: {ph}")
                break

        if not filled_body and len(textareas) > 1:
            textareas[1].clear()
            textareas[1].send_keys(body)
            filled_body = True
            print("[task2] Filled body in second textarea")
        elif not filled_body and textareas:
            # Maybe single textarea is body, title was in input
            textareas[0].clear()
            textareas[0].send_keys(body)
            filled_body = True
            print("[task2] Filled body in only textarea")

        # Clear performance logs before save
        driver.get_log("performance")

        # Click Save/Publish
        save_btn = find_clickable(driver, ["Save", "Submit", "Publish", "Create", "Post", "Save Blog"])
        if save_btn:
            print("[task2] Clicking save...")
            driver.execute_script("arguments[0].click()", save_btn)
            time.sleep(5)

            # Capture network calls
            logs = driver.get_log("performance")
            api_calls = []
            for entry in logs:
                try:
                    msg = json.loads(entry["message"])["message"]
                    if msg["method"] == "Network.requestWillBeSent":
                        r = msg["params"]["request"]
                        if "/api/" in r["url"]:
                            api_calls.append({
                                "url": r["url"],
                                "method": r["method"],
                                "postData": r.get("postData", "")[:1000],
                            })
                except: pass

            print(f"[task2] Captured {len(api_calls)} API calls during save")
            for c in api_calls:
                print(f"  {c['method']} {c['url'][:80]}")
                if c["postData"]:
                    print(f"    body: {c['postData'][:200]}")

            result = {"status": "GREEN_REAL" if api_calls else "YELLOW_RUNNING",
                      "title": title, "body_len": len(body),
                      "api_calls_captured": api_calls,
                      "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ")}
        else:
            print("[task2] No save button found")
            # Dump page state for debugging
            buttons = driver.find_elements(By.TAG_NAME, "button")
            btn_texts = [b.text.strip()[:30] for b in buttons if b.text.strip()]
            print(f"[task2] Buttons on page: {btn_texts}")
            result = {"status": "RED_FAILED", "reason": "No save button found",
                      "buttons": btn_texts, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ")}

        with open("data/task2_blog_post.json", "w") as f:
            json.dump(result, f, indent=2)
        print(f"[task2] Done: {result['status']}")

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
