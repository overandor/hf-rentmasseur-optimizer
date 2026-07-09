#!/usr/bin/env python3
"""Task 3: Interview posting via Selenium. Independent tiny Chrome window.
Brute-forces the interview editor: opens settings?interview=1, fills answers, clicks save.
Captures the network call to discover the real API endpoint."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json, time, os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

PROFILE_DIR = "/tmp/rm_task3"
BASE = "https://rentmasseur.com"

INTERVIEW_ANSWERS = {
    "style": "My style is focused and intentional. I don't do generic relaxation — I target the specific areas where you carry stress: neck, shoulders, back, hips, legs. Deep tissue, sports recovery, Swedish flow, pressure-forward bodywork.",
    "benefits": "Clients report immediate relief from chronic neck and shoulder tension. Many say they sleep better the night after a session. The targeted approach means we address the root pattern, not just the symptom.",
    "training": "Years of hands-on experience in Manhattan with a diverse clientele — from athletes to office workers to frequent travelers. Every body is different, and I adapt the session to what your tissue needs that day.",
    "philosophy": "If your shoulders live near your ears, you are my kind of client. I believe in focused recovery over generic relaxation. The body keeps score — I help it reset.",
    "advice": "Hydrate before and after. Don't schedule anything intense right after a deep tissue session. And be specific about where you're holding tension — the more precise you are, the better I can target the work.",
}

def get_driver():
    opts = Options()
    opts.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=400,300")
    opts.add_argument("--window-position=840,0")
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

        print("[task3] Opening interview editor...")
        driver.get(f"{BASE}/settings?interview=1")
        time.sleep(5)
        dismiss_popups(driver)
        print(f"[task3] URL: {driver.current_url}")

        # Find all textareas and fill with answers
        textareas = driver.find_elements(By.TAG_NAME, "textarea")
        inputs = driver.find_elements(By.TAG_NAME, "input")
        buttons = driver.find_elements(By.TAG_NAME, "button")
        print(f"[task3] Found {len(textareas)} textareas, {len(inputs)} inputs, {len(buttons)} buttons")

        # Print textarea details for debugging
        for i, ta in enumerate(textareas):
            ph = ta.get_attribute("placeholder") or "N/A"
            name = ta.get_attribute("name") or "N/A"
            print(f"[task3] textarea[{i}]: name={name} placeholder={ph}")

        # Fill textareas with interview answers
        answer_keys = list(INTERVIEW_ANSWERS.keys())
        filled = 0
        for i, ta in enumerate(textareas):
            if i < len(answer_keys):
                ta.clear()
                ta.send_keys(INTERVIEW_ANSWERS[answer_keys[i]])
                filled += 1
                print(f"[task3] Filled textarea[{i}] with {answer_keys[i]} answer")

        print(f"[task3] Filled {filled}/{len(textareas)} textareas")

        # Clear logs before save
        driver.get_log("performance")

        # Click Save
        save_btn = find_clickable(driver, ["Save", "Submit", "Update", "Confirm", "Save Changes", "Save Interview"])
        if save_btn:
            print("[task3] Clicking save...")
            driver.execute_script("arguments[0].click()", save_btn)
            time.sleep(5)

            # Capture API calls
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

            print(f"[task3] Captured {len(api_calls)} API calls during save")
            for c in api_calls:
                print(f"  {c['method']} {c['url'][:80]}")
                if c["postData"]:
                    print(f"    body: {c['postData'][:200]}")

            result = {"status": "GREEN_REAL" if api_calls else "YELLOW_RUNNING",
                      "answers_filled": filled,
                      "api_calls_captured": api_calls,
                      "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ")}
        else:
            btn_texts = [b.text.strip()[:30] for b in buttons if b.text.strip()]
            print(f"[task3] No save button. Buttons: {btn_texts}")
            result = {"status": "RED_FAILED", "reason": "No save button found",
                      "buttons": btn_texts, "textareas": len(textareas),
                      "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ")}

        with open("data/task3_interview_post.json", "w") as f:
            json.dump(result, f, indent=2)
        print(f"[task3] Done: {result['status']}")

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
