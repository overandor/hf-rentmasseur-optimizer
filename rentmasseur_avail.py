"""Selenium login + set hourly availability on rentmasseur.com/settings?availability=1"""

import json
import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
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
    opts.add_argument("--user-data-dir=/tmp/rm_chrome4")
    return webdriver.Chrome(options=opts)


def save(name, data=None, driver=None):
    path = os.path.join(OUTPUT, name)
    if driver:
        driver.save_screenshot(path)
    if data:
        with open(path, "w") as f:
            f.write(data)


def dismiss_popups(driver):
    """Dismiss notification popups, cookie banners, etc."""
    time.sleep(1)
    for xpath in [
        "//button[contains(text(),'Not now')]",
        "//button[contains(text(),'Accept all')]",
        "//button[contains(text(),'No thanks')]",
        "//button[contains(text(),'Dismiss')]",
        "//button[contains(text(),'Close')]",
        "//button[contains(text(),'Skip')]",
        "//*[contains(@class,'close') and (self::button or self::a or self::div)]",
        "//*[contains(@aria-label,'Close')]",
    ]:
        try:
            els = driver.find_elements(By.XPATH, xpath)
            for el in els:
                if el.is_displayed():
                    print(f"  Dismiss popup: '{el.text[:30]}'")
                    el.click()
                    time.sleep(1)
        except Exception:
            pass


def login(driver):
    """Login flow."""
    print("[1] Loading homepage...")
    driver.get("https://rentmasseur.com")
    time.sleep(4)
    dismiss_popups(driver)

    import re
    html = driver.page_source
    login_urls = re.findall(r'href=["\']([^"\']*login[^"\']*)["\']', html, re.I)
    print(f"  Login URLs: {login_urls[:5]}")

    if login_urls:
        url = login_urls[0]
        if url.startswith("/"):
            url = "https://rentmasseur.com" + url
        driver.get(url)
        time.sleep(4)
    else:
        driver.get("https://rentmasseur.com/login")
        time.sleep(4)

    dismiss_popups(driver)
    save("login_page.png", driver=driver)

    all_inputs = driver.find_elements(By.CSS_SELECTOR, "input")
    print(f"  Found {len(all_inputs)} inputs:")
    for inp in all_inputs:
        print(f"    type={inp.get_attribute('type')} name={inp.get_attribute('name')} "
              f"id={inp.get_attribute('id')} visible={inp.is_displayed()}")

    email = None
    for inp in all_inputs:
        iname = (inp.get_attribute("name") or "").lower()
        itype = (inp.get_attribute("type") or "").lower()
        if ("email" in iname or "user" in iname or itype == "email") and inp.is_displayed():
            email = inp
            break

    pwd = None
    for inp in all_inputs:
        if (inp.get_attribute("type") or "").lower() == "password" and inp.is_displayed():
            pwd = inp
            break

    if not email or not pwd:
        print("  [!] Could not find login fields")
        save("login_debug.html", data=driver.page_source)
        return False

    email.clear()
    email.send_keys("karpathianwolf")
    time.sleep(0.3)
    pwd.clear()
    pwd.send_keys("Lola369!")
    time.sleep(0.3)

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
                print(f"  Clicking: '{el.text}'")
                el.click()
                time.sleep(6)
                break
        else:
            continue
        break

    print(f"  Post-login URL: {driver.current_url}")
    save("after_login.png", driver=driver)
    dismiss_popups(driver)

    cookies = driver.get_cookies()
    with open(os.path.join(OUTPUT, "cookies.json"), "w") as f:
        json.dump(cookies, f, indent=2)
    print(f"  Cookies: {len(cookies)}")

    return True


def set_availability(driver):
    """Navigate to settings availability page and set every hour."""
    print("\n[2] Navigating to /settings?availability=1...")
    driver.get("https://rentmasseur.com/settings?availability=1")
    time.sleep(6)
    dismiss_popups(driver)

    print(f"  URL: {driver.current_url}")
    print(f"  Title: {driver.title}")
    save("settings_avail.png", driver=driver)
    save("settings_avail.html", data=driver.page_source)

    body = driver.find_element(By.TAG_NAME, "body").text
    save("settings_avail_text.txt", data=body)
    print(f"  Body text ({len(body)} chars):")
    print("  " + body[:1000])
    print()

    # Find all interactive elements
    checkboxes = driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
    toggles = driver.find_elements(By.CSS_SELECTOR, "[role='switch'],[role='checkbox'],.toggle,.switch")
    buttons = driver.find_elements(By.CSS_SELECTOR, "button")
    divs = driver.find_elements(By.CSS_SELECTOR,
        "[onclick],[class*='slot'],[class*='hour'],[class*='time'],"
        "[class*='avail'],[class*='day'],[class*='schedule'],[class*='toggle']")

    print(f"  Checkboxes: {len(checkboxes)}")
    print(f"  Toggles: {len(toggles)}")
    print(f"  Buttons: {len(buttons)}")
    print(f"  Slot divs: {len(divs)}")

    for b in buttons[:20]:
        try:
            t = b.text.strip()
            if t:
                print(f"    btn: '{t[:50]}'")
        except StaleElementReferenceException:
            pass

    for t in toggles[:10]:
        try:
            print(f"    toggle: {t.tag_name} class={t.get_attribute('class')[:60]} "
                  f"aria={t.get_attribute('aria-checked')} visible={t.is_displayed()}")
        except StaleElementReferenceException:
            pass

    for d in divs[:15]:
        try:
            print(f"    div: {d.tag_name} class={d.get_attribute('class')[:60]} "
                  f"text='{d.text.strip()[:40]}' visible={d.is_displayed()}")
        except StaleElementReferenceException:
            pass

    # Strategy 1: Click all unchecked checkboxes (re-query to avoid stale)
    if checkboxes:
        print("\n  Clicking checkboxes...")
        clicked = 0
        for i in range(len(checkboxes)):
            try:
                cbs = driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
                if i < len(cbs) and cbs[i].is_displayed() and not cbs[i].is_selected():
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", cbs[i])
                    time.sleep(0.1)
                    cbs[i].click()
                    clicked += 1
                    time.sleep(0.1)
            except StaleElementReferenceException:
                continue
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", cbs[i])
                    clicked += 1
                except Exception:
                    pass
        print(f"  Clicked {clicked} checkboxes")
        save("after_checkboxes.png", driver=driver)

    # Strategy 2: Click all toggles (re-query to avoid stale)
    if toggles:
        print("\n  Clicking toggles...")
        clicked = 0
        for i in range(len(toggles)):
            try:
                tgs = driver.find_elements(By.CSS_SELECTOR, "[role='switch'],[role='checkbox'],.toggle,.switch")
                if i < len(tgs) and tgs[i].is_displayed():
                    checked = tgs[i].get_attribute("aria-checked")
                    if checked != "true":
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tgs[i])
                        time.sleep(0.1)
                        tgs[i].click()
                        clicked += 1
                        time.sleep(0.2)
            except StaleElementReferenceException:
                continue
            except Exception:
                pass
        print(f"  Clicked {clicked} toggles")
        save("after_toggles.png", driver=driver)

    # Strategy 3: Click slot divs (re-query to avoid stale)
    if divs:
        print("\n  Clicking slot elements...")
        clicked = 0
        for i in range(len(divs)):
            try:
                ds = driver.find_elements(By.CSS_SELECTOR,
                    "[onclick],[class*='slot'],[class*='hour'],[class*='time'],"
                    "[class*='avail'],[class*='day'],[class*='schedule'],[class*='toggle']")
                if i < len(ds) and ds[i].is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", ds[i])
                    time.sleep(0.05)
                    ds[i].click()
                    clicked += 1
                    time.sleep(0.15)
            except StaleElementReferenceException:
                continue
            except Exception:
                pass
        print(f"  Clicked {clicked} slot elements")
        save("after_slots.png", driver=driver)

    # Strategy 4: Look for "Select All" / "Available All" button
    for by, sel in [
        (By.XPATH, "//button[contains(text(),'All')]"),
        (By.XPATH, "//button[contains(text(),'all')]"),
        (By.XPATH, "//a[contains(text(),'All')]"),
        (By.XPATH, "//*[contains(text(),'Select All')]"),
        (By.XPATH, "//*[contains(text(),'Available All')]"),
        (By.XPATH, "//button[contains(text(),'every')]"),
    ]:
        try:
            els = driver.find_elements(by, sel)
            for el in els:
                if el.is_displayed():
                    print(f"\n  Found bulk button: '{el.text}'")
                    el.click()
                    time.sleep(2)
                    save("after_bulk.png", driver=driver)
                    break
        except Exception:
            pass

    # Save
    print("\n  Looking for save button...")
    for by, sel in [
        (By.XPATH, "//button[contains(text(),'Save')]"),
        (By.XPATH, "//button[contains(text(),'save')]"),
        (By.XPATH, "//button[contains(text(),'Update')]"),
        (By.XPATH, "//button[contains(text(),'Submit')]"),
        (By.XPATH, "//button[contains(text(),'Confirm')]"),
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.CSS_SELECTOR, "button[class*='save']"),
        (By.CSS_SELECTOR, "button.btn-primary"),
    ]:
        try:
            els = driver.find_elements(by, sel)
            for el in els:
                if el.is_displayed():
                    print(f"  Clicking save: '{el.text}'")
                    el.click()
                    time.sleep(4)
                    save("after_save.png", driver=driver)
                    print("  Saved.")
                    return True
        except Exception:
            pass

    print("  No save button found (may auto-save)")
    return True


def verify(driver):
    """Verify availability was set."""
    print("\n[3] Verifying — reloading page...")
    driver.get("https://rentmasseur.com/settings?availability=1")
    time.sleep(6)
    dismiss_popups(driver)

    save("verify.png", driver=driver)
    save("verify.html", data=driver.page_source)

    body = driver.find_element(By.TAG_NAME, "body").text
    save("verify_text.txt", data=body)
    print(f"  Body text ({len(body)} chars):")
    print("  " + body[:1000])

    checkboxes = driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
    checked = sum(1 for cb in checkboxes if cb.is_selected())
    unchecked = sum(1 for cb in checkboxes if not cb.is_selected())
    print(f"\n  Checkboxes: {checked} checked, {unchecked} unchecked")

    toggles = driver.find_elements(By.CSS_SELECTOR, "[role='switch'],[role='checkbox']")
    active = sum(1 for t in toggles if t.get_attribute("aria-checked") == "true")
    print(f"  Toggles: {active} active, {len(toggles) - active} inactive")

    active_els = driver.find_elements(By.CSS_SELECTOR,
        ".active,.available,.selected,.checked,[aria-checked='true']")
    print(f"  Active elements: {len(active_els)}")

    body_lower = body.lower()
    if "saved" in body_lower or "success" in body_lower or "updated" in body_lower:
        print("  [OK] Success message found")
    else:
        print("  [?] No success message")

    return {"checked": checked, "unchecked": unchecked, "active": active}


def run():
    driver = create_driver()
    try:
        if not login(driver):
            print("Login failed")
            return

        set_availability(driver)
        result = verify(driver)
        print(f"\nVerification: {json.dumps(result, indent=2)}")
        print(f"\nAll files in {OUTPUT}/")

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
