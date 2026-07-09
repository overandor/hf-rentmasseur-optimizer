#!/usr/bin/env python3
"""
CrowdSec Captcha Solver using OCR.

Detects captcha type and solves accordingly:
- Image captcha: Tesseract OCR
- JS challenge (Cloudflare Turnstile): Click checkbox + wait
"""
import io
import re
import time
from PIL import Image
import pytesseract
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

BASE = "https://rentmasseur.com"
USERNAME = "karpathianwolf"
PASSWORD = os.environ.get("RM_PASSWORD", "")


def solve_captcha(driver, max_attempts=15):
    """Detect and solve CrowdSec captcha."""
    src = driver.page_source or ""
    if "crowdsec" not in src.lower() and "captcha" not in src.lower():
        print("  No captcha detected.")
        return True

    print("  Captcha detected. Analyzing type...")

    for attempt in range(max_attempts):
        print(f"  Attempt {attempt + 1}/{max_attempts}...")

        # Check for image captcha
        captcha_img = None
        for sel in [
            "img[src*='captcha']",
            "img[id*='captcha']",
            "img[class*='captcha']",
            "img[alt*='captcha']",
            "img[alt*='Captcha']",
            "#captcha img",
            ".captcha img",
            "img[src*='crowdsec']",
            "canvas",
        ]:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in elements:
                    if el.is_displayed():
                        captcha_img = el
                        break
            except:
                continue
            if captcha_img:
                break

        if captcha_img:
            print("  Image captcha found. Using OCR...")
            try:
                # Screenshot the captcha image
                png_data = captcha_img.screenshot_as_png
                img = Image.open(io.BytesIO(png_data))

                # Preprocess for better OCR
                img = img.convert("L")  # grayscale
                img = img.resize((img.width * 3, img.height * 3), Image.LANCZOS)  # upscale
                img = img.point(lambda x: 0 if x < 128 else 255, "1")  # threshold

                # OCR
                text = pytesseract.image_to_string(
                    img,
                    config="--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
                ).strip()
                text = re.sub(r'\s+', '', text)

                print(f"  OCR result: '{text}'")

                if not text or len(text) < 3:
                    print("  OCR returned empty/short. Refreshing captcha...")
                    try:
                        refresh_btn = driver.find_element(By.CSS_SELECTOR, "button[class*='refresh'], a[class*='refresh']")
                        refresh_btn.click()
                        time.sleep(2)
                    except:
                        driver.refresh()
                        time.sleep(3)
                    continue

                # Find input field and submit
                input_field = None
                for sel in [
                    "input[name*='captcha']",
                    "input[id*='captcha']",
                    "input[placeholder*='captcha']",
                    "input[type='text']",
                ]:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, sel)
                        for el in elements:
                            if el.is_displayed():
                                input_field = el
                                break
                    except:
                        continue
                    if input_field:
                        break

                if input_field:
                    input_field.clear()
                    input_field.send_keys(text)
                    time.sleep(0.5)

                    # Find submit button
                    submit = None
                    for sel in [
                        "button[type='submit']",
                        "input[type='submit']",
                        "button[class*='submit']",
                        "button",
                    ]:
                        try:
                            elements = driver.find_elements(By.CSS_SELECTOR, sel)
                            for el in elements:
                                if el.is_displayed():
                                    submit = el
                                    break
                        except:
                            continue
                        if submit:
                            break

                    if submit:
                        submit.click()
                    else:
                        from selenium.webdriver.common.keys import Keys
                        input_field.send_keys(Keys.ENTER)

                    time.sleep(4)

                    # Check if captcha is gone
                    src = driver.page_source or ""
                    if "crowdsec" not in src.lower() and "captcha" not in src.lower():
                        print("  Captcha solved via OCR!")
                        return True
                    print("  Still present after OCR submission. Retrying...")
                else:
                    print("  No input field found. Refreshing...")
                    driver.refresh()
                    time.sleep(3)

            except Exception as e:
                print(f"  OCR error: {e}")
                time.sleep(2)
        else:
            # JS-based challenge (Cloudflare Turnstile)
            print("  JS-based challenge detected (Cloudflare Turnstile).")
            print("  Trying to click checkbox...")

            try:
                checkbox = driver.find_element(By.CSS_SELECTOR, "input[type='checkbox'], .recaptcha-checkbox, .cf-turnstile")
                if checkbox.is_displayed():
                    checkbox.click()
                    print("  Clicked checkbox. Waiting for verification...")
                    time.sleep(15)
            except:
                print("  No checkbox found. Waiting for auto-clear...")

            # Wait for clearance
            for i in range(20):
                time.sleep(3)
                src = driver.page_source or ""
                if "crowdsec" not in src.lower() and "captcha" not in src.lower():
                    print("  JS challenge cleared!")
                    return True

            print("  JS challenge not cleared. Refreshing...")
            driver.refresh()
            time.sleep(5)

    print(f"  Failed after {max_attempts} attempts.")
    return False


def login_with_captcha_solve():
    """Login with automatic captcha solving."""
    opts = uc.ChromeOptions()
    opts.add_argument("--window-size=1280,900")
    driver = uc.Chrome(options=opts, version_main=149)

    try:
        driver.get(f"{BASE}/login")
        time.sleep(5)

        # Solve captcha if present
        if not solve_captcha(driver):
            print("Captcha solve failed.")
            driver.quit()
            return None, None

        # Fill login form
        print("  Filling login form...")
        driver.execute_script("""
            const pwd = document.querySelector('input[type="password"]');
            const user = document.querySelector('input[type="text"], input[type="email"]');
            const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            if (user) { ns.call(user, arguments[0]); user.dispatchEvent(new Event('input', {bubbles: true})); }
            if (pwd) { ns.call(pwd, arguments[1]); pwd.dispatchEvent(new Event('input', {bubbles: true})); }
        """, USERNAME, PASSWORD)
        time.sleep(1)

        try:
            pwd = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
            from selenium.webdriver.common.keys import Keys
            pwd.send_keys(Keys.ENTER)
        except:
            pass

        time.sleep(10)

        # Check if logged in
        if "login" in driver.current_url.lower():
            print("Login failed.")
            driver.quit()
            return None, None

        print("Login successful!")
        cookies = driver.get_cookies()
        return driver, cookies

    except Exception as e:
        print(f"Login error: {e}")
        driver.quit()
        return None, None


if __name__ == "__main__":
    print("=== CAPTCHA SOLVER TEST ===")
    driver, cookies = login_with_captcha_solve()
    if driver:
        print(f"Cookies: {len(cookies)}")
        input("Press Enter to close...")
        driver.quit()
