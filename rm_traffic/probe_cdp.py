"""Capture interview + blog API endpoints via Selenium CDP."""
import json, time, re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

BASE = "https://rentmasseur.com"
opts = Options()
opts.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
opts.add_argument("--no-sandbox")
opts.add_argument("--disable-dev-shm-usage")
opts.add_argument("--window-size=1920,1080")
opts.add_argument("--user-data-dir=/tmp/rm_probe_cdp")
opts.add_argument("--disable-blink-features=AutomationControlled")
opts.add_experimental_option("excludeSwitches", ["enable-automation"])
opts.add_experimental_option("useAutomationExtension", False)
opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
d = webdriver.Chrome(options=opts)

def dismiss():
    time.sleep(1)
    try:
        d.execute_script("document.querySelectorAll('.DialogOverlay,[class*=\"overlay\"]').forEach(e=>e.remove())")
    except: pass
    for xp in ["//button[contains(text(),'Not now')]","//button[contains(text(),'Accept all')]","//button[contains(text(),'Close')]"]:
        try:
            for el in d.find_elements(By.XPATH, xp):
                if el.is_displayed(): d.execute_script("arguments[0].click()", el); time.sleep(0.5)
        except: pass

def get_api_calls():
    logs = d.get_log("performance")
    reqs = {}
    for entry in logs:
        try:
            msg = json.loads(entry["message"])["message"]
            if msg["method"] == "Network.requestWillBeSent":
                p = msg["params"]
                r = p["request"]
                rid = p["requestId"]
                reqs[rid] = {"url": r["url"], "method": r["method"], "postData": r.get("postData","")[:500]}
            elif msg["method"] == "Network.responseReceived":
                p = msg["params"]
                rid = p["requestId"]
                if rid in reqs:
                    reqs[rid]["status"] = p["response"]["status"]
                    try:
                        body = d.execute_cdp_cmd("Network.getResponseBody", {"requestId": rid})
                        reqs[rid]["response"] = body.get("body","")[:1000]
                    except: pass
        except: pass
    return [v for v in reqs.values() if "/api/" in v["url"]]

# Login
d.get(f"{BASE}/login")
time.sleep(4)
dismiss()
for inp in d.find_elements(By.CSS_SELECTOR, "input"):
    t = (inp.get_attribute("type") or "").lower()
    n = (inp.get_attribute("name") or "").lower()
    if (t=="email" or "email" in n or "user" in n) and inp.is_displayed():
        inp.clear(); inp.send_keys("karpathianwolf")
    if t=="password" and inp.is_displayed():
        inp.clear(); inp.send_keys("os.environ.get("RM_PASSWORD", "")")
time.sleep(0.3)
for el in d.find_elements(By.CSS_SELECTOR, "button[type='submit']"):
    if el.is_displayed(): d.execute_script("arguments[0].click()", el); break
time.sleep(6)
dismiss()
print("Login OK")

# Visit interview page
print("\n--- INTERVIEW PAGE ---")
d.get(f"{BASE}/settings?interview=1")
time.sleep(5)
dismiss()
calls = get_api_calls()
for c in calls:
    print(f"  {c['method']:4s} {c.get('status','?')} {c['url'][:80]}")
    if c.get("postData"): print(f"        body: {c['postData'][:200]}")
    if c.get("response"): print(f"        resp: {c['response'][:200]}")

# Try clicking interview edit/save
print("\n--- INTERVIEW INTERACTION ---")
try:
    # Look for edit buttons or text areas
    for el in d.find_elements(By.CSS_SELECTOR, "textarea"):
        print(f"  textarea: id={el.get_attribute('id')} name={el.get_attribute('name')}")
    for el in d.find_elements(By.XPATH, "//button[contains(text(),'Save')]"):
        if el.is_displayed():
            print(f"  Save button found, clicking...")
            d.execute_script("arguments[0].click()", el)
            time.sleep(3)
            calls = get_api_calls()
            for c in calls:
                if c not in calls[:len(calls)]:
                    print(f"  NEW: {c['method']:4s} {c.get('status','?')} {c['url'][:80]}")
                    if c.get("postData"): print(f"        body: {c['postData'][:200]}")
except Exception as e:
    print(f"  Error: {e}")

# Visit blog page
print("\n--- BLOG PAGE ---")
d.get(f"{BASE}/settings?blog=1")
time.sleep(5)
dismiss()
calls = get_api_calls()
for c in calls:
    print(f"  {c['method']:4s} {c.get('status','?')} {c['url'][:80]}")
    if c.get("postData"): print(f"        body: {c['postData'][:200]}")
    if c.get("response"): print(f"        resp: {c['response'][:200]}")

# Try to find blog create/edit
print("\n--- BLOG INTERACTION ---")
try:
    for el in d.find_elements(By.CSS_SELECTOR, "textarea"):
        print(f"  textarea: id={el.get_attribute('id')} name={el.get_attribute('name')}")
    for el in d.find_elements(By.XPATH, "//button[contains(text(),'Create')]"):
        if el.is_displayed():
            print(f"  Create button found")
            d.execute_script("arguments[0].click()", el)
            time.sleep(3)
            calls = get_api_calls()
            for c in calls[-5:]:
                print(f"  {c['method']:4s} {c.get('status','?')} {c['url'][:80]}")
                if c.get("postData"): print(f"        body: {c['postData'][:200]}")
    for el in d.find_elements(By.XPATH, "//button[contains(text(),'New')]"):
        if el.is_displayed():
            print(f"  New button found")
            d.execute_script("arguments[0].click()", el)
            time.sleep(3)
            calls = get_api_calls()
            for c in calls[-5:]:
                print(f"  {c['method']:4s} {c.get('status','?')} {c['url'][:80]}")
                if c.get("postData"): print(f"        body: {c['postData'][:200]}")
except Exception as e:
    print(f"  Error: {e}")

# Also check settings page for all available sections
print("\n--- SETTINGS SECTIONS ---")
d.get(f"{BASE}/settings")
time.sleep(4)
dismiss()
for el in d.find_elements(By.CSS_SELECTOR, "a[href*='settings']"):
    href = el.get_attribute("href") or ""
    text = el.text.strip()
    if text and "?" in href:
        print(f"  {text}: {href}")

d.quit()
print("\nDone")
