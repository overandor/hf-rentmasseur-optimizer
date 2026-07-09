"""Set availability every hour on rentmasseur.com and verify.

Logs in, navigates to /settings, selects "Available" with "1 Hour" duration,
clicks SET, then verifies. Repeats every hour.
"""

import json
import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException

OUTPUT = "/tmp/rentmasseur_capture"
os.makedirs(OUTPUT, exist_ok=True)


def create_driver():
    opts = Options()
    opts.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--user-data-dir=/tmp/rm_chrome5")
    return webdriver.Chrome(options=opts)


def save(name, driver=None):
    if driver:
        driver.save_screenshot(os.path.join(OUTPUT, name))


def dismiss_popups(driver):
    time.sleep(1)
    for xpath in [
        "//button[contains(text(),'Not now')]",
        "//button[contains(text(),'Accept all')]",
        "//button[contains(text(),'Close')]",
        "//*[contains(@aria-label,'Close')]",
    ]:
        try:
            els = driver.find_elements(By.XPATH, xpath)
            for el in els:
                if el.is_displayed():
                    el.click()
                    time.sleep(1)
        except Exception:
            pass


def login(driver):
    print("[1] Logging in...")
    driver.get("https://rentmasseur.com")
    time.sleep(4)
    dismiss_popups(driver)

    # Find login link
    import re
    html = driver.page_source
    login_urls = re.findall(r'href=["\']([^"\']*login[^"\']*)["\']', html, re.I)
    if login_urls:
        url = login_urls[0]
        if url.startswith("/"):
            url = "https://rentmasseur.com" + url
        driver.get(url)
    else:
        driver.get("https://rentmasseur.com/login")
    time.sleep(4)
    dismiss_popups(driver)

    # Find login fields
    email = None
    pwd = None
    for inp in driver.find_elements(By.CSS_SELECTOR, "input"):
        iname = (inp.get_attribute("name") or "").lower()
        itype = (inp.get_attribute("type") or "").lower()
        if ("email" in iname or "user" in iname or itype == "email") and inp.is_displayed():
            email = inp
        if itype == "password" and inp.is_displayed():
            pwd = inp

    if not email or not pwd:
        print("  [!] Login fields not found")
        return False

    email.clear()
    email.send_keys("karpathianwolf")
    pwd.clear()
    pwd.send_keys("Lola369!")
    time.sleep(0.3)

    # Click LOGIN button
    for by, sel in [
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.XPATH, "//button[contains(text(),'LOG')]"),
        (By.XPATH, "//button[contains(text(),'Log')]"),
        (By.CSS_SELECTOR, "form button"),
        (By.CSS_SELECTOR, "button"),
    ]:
        els = driver.find_elements(by, sel)
        for el in els:
            if el.is_displayed():
                el.click()
                time.sleep(6)
                break
        else:
            continue
        break

    print(f"  Post-login URL: {driver.current_url}")
    dismiss_popups(driver)

    # Save cookies
    cookies = driver.get_cookies()
    with open(os.path.join(OUTPUT, "cookies.json"), "w") as f:
        json.dump(cookies, f, indent=2)
    print(f"  Cookies: {len(cookies)}")
    return True


def set_availability_once(driver):
    """Set availability to Available with 1 hour duration. Returns True if set."""
    # Navigate to settings
    driver.get("https://rentmasseur.com/settings?availability=1")
    time.sleep(5)
    dismiss_popups(driver)

    body = driver.find_element(By.TAG_NAME, "body").text
    print(f"  Page loaded. URL: {driver.current_url}")

    # Check current status
    if "Status: Available" in body:
        # Extract remaining time
        import re
        match = re.search(r'Status:\s*Available\s*(\d+)h\s*:\s*(\d+)m', body)
        if match:
            hours = int(match.group(1))
            mins = int(match.group(2))
            total_mins = hours * 60 + mins
            print(f"  Currently available for {hours}h:{mins}m ({total_mins} min remaining)")
            if total_mins > 5:
                print("  Already available with sufficient time, skipping SET")
                return True

    # Find the "Available" radio option
    print("  Selecting 'Available'...")

    # Look for radio buttons or clickable options
    radios = driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")
    print(f"  Found {len(radios)} radio buttons")

    for radio in radios:
        try:
            val = radio.get_attribute("value") or ""
            name = radio.get_attribute("name") or ""
            if radio.is_displayed() and "available" in val.lower():
                print(f"    Clicking radio: name={name} value={val}")
                radio.click()
                time.sleep(0.5)
        except Exception:
            pass

    # Also try clicking labels/text that say "Available"
    for by, sel in [
        (By.XPATH, "//label[contains(text(),'Available')]"),
        (By.XPATH, "//*[contains(text(),'Available') and not(contains(text(),'Not')) and not(contains(text(),'Status'))]"),
    ]:
        try:
            els = driver.find_elements(by, sel)
            for el in els:
                if el.is_displayed():
                    print(f"    Clicking: '{el.text[:30]}' tag={el.tag_name}")
                    el.click()
                    time.sleep(0.5)
                    break
        except Exception:
            pass

    # Find duration select and set to 1 Hour
    print("  Setting duration to 1 Hour...")
    selects = driver.find_elements(By.CSS_SELECTOR, "select")
    print(f"  Found {len(selects)} select elements")

    for sel_el in selects:
        try:
            sel = Select(sel_el)
            options = [o.text for o in sel.options]
            print(f"    Select options: {options}")
            if "1 Hour" in options:
                sel.select_by_visible_text("1 Hour")
                print("    Selected '1 Hour'")
                time.sleep(0.5)
                break
        except Exception:
            pass

    # Click SET button
    print("  Clicking SET button...")
    for by, sel in [
        (By.XPATH, "//button[contains(text(),'SET')]"),
        (By.XPATH, "//button[contains(text(),'Set')]"),
        (By.CSS_SELECTOR, "button[class*='set']"),
    ]:
        try:
            els = driver.find_elements(by, sel)
            for el in els:
                if el.is_displayed():
                    print(f"    Clicking: '{el.text}'")
                    el.click()
                    time.sleep(3)
                    save("after_set.png", driver=driver)
                    return True
        except Exception:
            pass

    print("  [!] SET button not found")
    save("set_debug.png", driver=driver)
    return False


def verify_availability(driver):
    """Verify availability is set. Returns status string."""
    print("\n  Verifying...")
    driver.get("https://rentmasseur.com/settings?availability=1")
    time.sleep(5)
    dismiss_popups(driver)

    save("verify.png", driver=driver)

    body = driver.find_element(By.TAG_NAME, "body").text
    save("verify_text.txt", data=body)

    import re
    match = re.search(r'Status:\s*(Available|Not Available|Not Set)\s*(\d+)h\s*:\s*(\d+)m?', body)
    if match:
        status = match.group(1)
        if match.group(2) and match.group(3):
            hours = int(match.group(2))
            mins = int(match.group(3))
            print(f"  Status: {status} ({hours}h:{mins}m remaining)")
            return {"status": status, "hours": hours, "mins": mins, "total_mins": hours * 60 + mins}
        else:
            print(f"  Status: {status}")
            return {"status": status}
    elif "Status: Available" in body:
        print("  Status: Available (time not parsed)")
        return {"status": "Available"}
    else:
        print(f"  Status: unknown")
        # Print relevant section
        for line in body.split("\n"):
            if "status" in line.lower() or "available" in line.lower():
                print(f"    {line}")
        return {"status": "unknown"}


def run():
    driver = create_driver()
    try:
        if not login(driver):
            print("Login failed")
            return

        # Set availability once
        print("\n[2] Setting availability (1 hour)...")
        success = set_availability_once(driver)
        print(f"  Set result: {success}")

        # Verify
        result = verify_availability(driver)
        print(f"\n  Verification: {json.dumps(result, indent=2)}")

        if result.get("status") == "Available":
            print("\n  [OK] Availability is set correctly")
        else:
            print("\n  [!] Availability may not be set correctly")

        print(f"\n  Screenshots in {OUTPUT}/")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        try:
            save("error.png", driver=driver)
        except Exception:
            pass
    finally:
        time.sleep(3)
        driver.quit()
        print("Browser closed.")


if __name__ == "__main__":
    run()
