"""Set hourly availability on rentmasseur.com and verify.

1. Log in with saved cookies (or fresh login)
2. Navigate to /build-stream (availability scheduling)
3. Set availability for every hour
4. Verify the schedule was saved correctly
"""

import json
import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

OUTPUT_DIR = "/tmp/rentmasseur_capture"
COOKIES_PATH = os.path.join(OUTPUT_DIR, "cookies.json")


def create_driver():
    options = Options()
    options.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--user-data-dir=/tmp/rentmasseur_chrome_profile2")
    return webdriver.Chrome(options=options)


def load_cookies(driver):
    """Load saved cookies into the driver."""
    if not os.path.exists(COOKIES_PATH):
        return False

    with open(COOKIES_PATH) as f:
        cookies = json.load(f)

    # Must visit the domain first before setting cookies
    driver.get("https://rentmasseur.com")
    time.sleep(2)

    for cookie in cookies:
        # Selenium doesn't accept all cookie fields, strip problematic ones
        clean = {k: v for k, v in cookie.items()
                 if k in ("name", "value", "domain", "path", "expiry", "secure", "httpOnly")}
        try:
            driver.add_cookie(clean)
        except Exception as e:
            print(f"  Cookie skip: {cookie.get('name')}: {e}")

    print(f"  Loaded {len(cookies)} cookies")
    return True


def login_if_needed(driver):
    """Check if logged in, if not do fresh login."""
    driver.get("https://rentmasseur.com")
    time.sleep(3)

    body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
    if "log out" in body_text or "logout" in body_text or "my account" in body_text:
        print("  [OK] Already logged in via cookies")
        return True

    print("  Not logged in, doing fresh login...")
    driver.get("https://rentmasseur.com/login")
    time.sleep(3)

    # Fill login form
    email_field = None
    for selector in [
        (By.CSS_SELECTOR, "input[name='email']"),
        (By.CSS_SELECTOR, "input[type='email']"),
        (By.CSS_SELECTOR, "input[id='email']"),
        (By.CSS_SELECTOR, "input[placeholder*='mail']"),
        (By.XPATH, "//input[@type='email' or @name='email' or @name='username']"),
    ]:
        elements = driver.find_elements(*selector)
        if elements and elements[0].is_displayed():
            email_field = elements[0]
            break

    password_field = None
    for selector in [
        (By.CSS_SELECTOR, "input[type='password']"),
        (By.CSS_SELECTOR, "input[name='password']"),
    ]:
        elements = driver.find_elements(*selector)
        if elements and elements[0].is_displayed():
            password_field = elements[0]
            break

    if not email_field or not password_field:
        print("  [!] Could not find login fields")
        driver.save_screenshot(os.path.join(OUTPUT_DIR, "login_debug.png"))
        with open(os.path.join(OUTPUT_DIR, "login_debug.html"), "w") as f:
            f.write(driver.page_source)
        return False

    email_field.clear()
    email_field.send_keys("karpathianwolf")
    password_field.clear()
    password_field.send_keys("Lola369!")
    time.sleep(0.5)

    # Find submit
    submit = None
    for selector in [
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.XPATH, "//button[contains(text(),'Log') or contains(text(),'Sign') or contains(text(),'Login')]"),
        (By.CSS_SELECTOR, "button"),
    ]:
        elements = driver.find_elements(*selector)
        if elements and elements[0].is_displayed():
            submit = elements[0]
            break

    if submit:
        submit.click()
    else:
        password_field.send_keys("\n")

    time.sleep(5)
    print(f"  Post-login URL: {driver.current_url}")

    # Save cookies
    cookies = driver.get_cookies()
    with open(COOKIES_PATH, "w") as f:
        json.dump(cookies, f, indent=2)
    print(f"  Cookies saved: {len(cookies)}")

    body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
    if "log out" in body_text or "logout" in body_text or "my account" in body_text:
        print("  [OK] Login successful")
        return True

    print("  [?] Login status unclear")
    return True  # Continue anyway


def navigate_to_build_stream(driver):
    """Navigate to /build-stream and capture the page."""
    print("\n[2] Navigating to /build-stream...")
    driver.get("https://rentmasseur.com/build-stream")
    time.sleep(5)

    print(f"  URL: {driver.current_url}")
    print(f"  Title: {driver.title}")
    driver.save_screenshot(os.path.join(OUTPUT_DIR, "build_stream.png"))

    # Save HTML
    html = driver.page_source
    with open(os.path.join(OUTPUT_DIR, "build_stream.html"), "w") as f:
        f.write(html)
    print(f"  HTML saved: {len(html)} chars")

    # Save body text
    body_text = driver.find_element(By.TAG_NAME, "body").text
    with open(os.path.join(OUTPUT_DIR, "build_stream_text.txt"), "w") as f:
        f.write(body_text)
    print(f"  Body text saved: {len(body_text)} chars")

    return body_text


def set_availability_every_hour(driver):
    """Set availability for every hour on the build-stream page."""
    print("\n[3] Setting availability for every hour...")

    # Take before screenshot
    driver.save_screenshot(os.path.join(OUTPUT_DIR, "availability_before.png"))

    # Look for time slots, checkboxes, or availability toggles
    # Try various patterns

    # Pattern 1: Look for checkboxes/toggles with time labels
    checkboxes = driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
    toggles = driver.find_elements(By.CSS_SELECTOR, "[role='switch'], [role='checkbox'], .toggle, .switch")
    buttons = driver.find_elements(By.CSS_SELECTOR, "button")
    time_elements = driver.find_elements(By.CSS_SELECTOR, "[data-time], [data-hour], [data-slot]")

    print(f"  Found: {len(checkboxes)} checkboxes, {len(toggles)} toggles, "
          f"{len(buttons)} buttons, {len(time_elements)} time elements")

    # Pattern 2: Look for a "select all" or "every hour" button
    for btn in buttons:
        text = btn.text.lower()
        if "all" in text and ("hour" in text or "select" in text or "available" in text):
            print(f"  Found select-all button: '{btn.text}'")
            btn.click()
            time.sleep(2)
            driver.save_screenshot(os.path.join(OUTPUT_DIR, "availability_after_selectall.png"))
            return True

    # Pattern 3: Click each checkbox/toggle for each hour
    targets = checkboxes + toggles
    if targets:
        print(f"  Clicking {len(targets)} availability toggles...")
        clicked = 0
        for i, target in enumerate(targets):
            try:
                if target.is_displayed() and not target.is_selected():
                    driver.execute_script("arguments[0].scrollIntoView(true);", target)
                    time.sleep(0.2)
                    target.click()
                    clicked += 1
                    time.sleep(0.1)
            except Exception as e:
                # Try JavaScript click
                try:
                    driver.execute_script("arguments[0].click();", target)
                    clicked += 1
                except Exception:
                    pass

        print(f"  Clicked {clicked} toggles")
        time.sleep(2)
        driver.save_screenshot(os.path.join(OUTPUT_DIR, "availability_after_clicks.png"))
        return True

    # Pattern 4: Look for time slot grid (common in scheduling UIs)
    slots = driver.find_elements(By.CSS_SELECTOR,
        ".time-slot, .hour-slot, .availability-slot, .slot, "
        "[class*='slot'], [class*='hour'], [class*='time'], [class*='avail']")
    if slots:
        print(f"  Found {len(slots)} slot elements")
        clicked = 0
        for slot in slots:
            try:
                if slot.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView(true);", slot)
                    time.sleep(0.1)
                    slot.click()
                    clicked += 1
                    time.sleep(0.1)
            except Exception:
                pass
        print(f"  Clicked {clicked} slots")
        time.sleep(2)
        driver.save_screenshot(os.path.join(OUTPUT_DIR, "availability_after_slots.png"))
        return True

    # Pattern 5: Try to find and interact with a schedule grid via JavaScript
    print("  Trying JavaScript-based slot detection...")
    js_result = driver.execute_script("""
        // Find all clickable elements that might be time slots
        var all = document.querySelectorAll('*');
        var slots = [];
        for (var i = 0; i < all.length; i++) {
            var el = all[i];
            var text = el.textContent || '';
            var cls = el.className || '';
            var dataAttrs = '';
            for (var j = 0; j < el.attributes.length; j++) {
                if (el.attributes[j].name.startsWith('data-')) {
                    dataAttrs += el.attributes[j].name + '=' + el.attributes[j].value + ' ';
                }
            }
            // Check if it looks like a time slot
            if (/\\d{1,2}[:\\s]*(AM|PM|am|pm)/.test(text) ||
                /slot|hour|time|avail|schedule/i.test(cls) ||
                /slot|hour|time|avail/i.test(dataAttrs)) {
                slots.push({
                    tag: el.tagName,
                    text: text.substring(0, 50),
                    cls: cls.substring(0, 80),
                    data: dataAttrs.substring(0, 80),
                    visible: el.offsetParent !== null
                });
            }
        }
        return slots;
    """)

    if js_result:
        print(f"  JS found {len(js_result)} potential slot elements:")
        for s in js_result[:10]:
            print(f"    {s['tag']} cls='{s['cls']}' text='{s['text']}' visible={s['visible']}")

    # Save page source for debugging
    with open(os.path.join(OUTPUT_DIR, "build_stream_debug.html"), "w") as f:
        f.write(driver.page_source)

    print("  [!] Could not find availability controls automatically")
    print("  Page source saved for analysis")
    return False


def save_availability(driver):
    """Look for and click a save button."""
    print("\n[4] Looking for save button...")

    for selector in [
        (By.XPATH, "//button[contains(text(),'Save')]"),
        (By.XPATH, "//button[contains(text(),'save')]"),
        (By.XPATH, "//button[contains(text(),'Update')]"),
        (By.XPATH, "//button[contains(text(),'Submit')]"),
        (By.XPATH, "//button[contains(text(),'Confirm')]"),
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.CSS_SELECTOR, "button.save"),
        (By.CSS_SELECTOR, "button.btn-primary"),
    ]:
        elements = driver.find_elements(*selector)
        if elements and elements[0].is_displayed():
            print(f"  Found save button: '{elements[0].text}'")
            elements[0].click()
            time.sleep(3)
            driver.save_screenshot(os.path.join(OUTPUT_DIR, "availability_saved.png"))
            print("  Save clicked.")
            return True

    print("  [!] No save button found")
    return False


def verify_availability(driver):
    """Verify the availability was set correctly."""
    print("\n[5] Verifying availability...")

    # Reload the page
    driver.get("https://rentmasseur.com/build-stream")
    time.sleep(5)

    driver.save_screenshot(os.path.join(OUTPUT_DIR, "availability_verify.png"))

    body_text = driver.find_element(By.TAG_NAME, "body").text
    with open(os.path.join(OUTPUT_DIR, "verify_text.txt"), "w") as f:
        f.write(body_text)

    # Check checkboxes state
    checkboxes = driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
    checked = 0
    unchecked = 0
    for cb in checkboxes:
        try:
            if cb.is_displayed():
                if cb.is_selected():
                    checked += 1
                else:
                    unchecked += 1
        except Exception:
            pass

    print(f"  Checkboxes: {checked} checked, {unchecked} unchecked")

    # Check for success messages
    body_lower = body_text.lower()
    if "success" in body_lower or "saved" in body_lower or "updated" in body_lower:
        print("  [OK] Success message found on page")
    else:
        print("  [?] No explicit success message found")

    # Look for active/available indicators
    active_elements = driver.find_elements(By.CSS_SELECTOR,
        ".active, .available, .selected, .checked, [aria-checked='true'], [data-active='true']")
    print(f"  Active/available elements: {len(active_elements)}")

    # Save verification HTML
    with open(os.path.join(OUTPUT_DIR, "verify_page.html"), "w") as f:
        f.write(driver.page_source)

    return {
        "checkboxes_checked": checked,
        "checkboxes_unchecked": unchecked,
        "active_elements": len(active_elements),
        "has_success_message": "success" in body_lower or "saved" in body_lower,
    }


def run():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    driver = create_driver()
    wait = WebDriverWait(driver, 15)

    try:
        # Step 1: Login
        print("[1] Logging in...")
        if not load_cookies(driver):
            print("  No saved cookies, doing fresh login...")

        logged_in = login_if_needed(driver)
        if not logged_in:
            print("  [!] Login failed")
            return

        # Step 2: Navigate to build-stream
        body_text = navigate_to_build_stream(driver)

        # Print what we see on the page
        print("\n  --- Page content (first 500 chars) ---")
        print(body_text[:500])
        print("  --- End ---\n")

        # Step 3: Set availability every hour
        success = set_availability_every_hour(driver)

        if success:
            # Step 4: Save
            save_availability(driver)

            # Step 5: Verify
            result = verify_availability(driver)
            print(f"\n  Verification result: {json.dumps(result, indent=2)}")
        else:
            print("\n  [!] Could not set availability automatically")
            print("  Taking screenshot for manual review...")
            driver.save_screenshot(os.path.join(OUTPUT_DIR, "availability_manual_review.png"))

            # Try to find any API calls the page makes
            print("\n  Checking for API endpoints in page source...")
            html = driver.page_source
            import re
            api_urls = re.findall(r'(?:fetch|axios|api)["\']?\s*[:(]\s*["\']([^"\']+)["\']', html)
            if api_urls:
                print(f"  Found API references:")
                for url in api_urls[:20]:
                    print(f"    {url}")

            # Also look for Next.js data
            next_data = re.findall(r'__NEXT_DATA__\s*=\s*({.*?})\s*</script>', html)
            if next_data:
                with open(os.path.join(OUTPUT_DIR, "next_data.json"), "w") as f:
                    f.write(next_data[0])
                print("  Next.js data saved to next_data.json")

        print("\n[6] Done. All captures in /tmp/rentmasseur_capture/")

    except Exception as e:
        print(f"\n  ERROR: {e}")
        import traceback
        traceback.print_exc()
        try:
            driver.save_screenshot(os.path.join(OUTPUT_DIR, "error.png"))
        except Exception:
            pass
    finally:
        time.sleep(3)
        driver.quit()
        print("  Browser closed.")


if __name__ == "__main__":
    run()
