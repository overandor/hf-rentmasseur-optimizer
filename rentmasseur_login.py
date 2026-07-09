"""Automated Selenium login + capture for rentmasseur.com.

Logs in with provided credentials, captures /build-stream content.
"""

import json
import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def run():
    options = Options()
    options.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--user-data-dir=/tmp/rentmasseur_chrome_profile")

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 15)

    output_dir = "/tmp/rentmasseur_capture"
    os.makedirs(output_dir, exist_ok=True)

    try:
        # Step 1: Load homepage
        print("[1] Loading rentmasseur.com...")
        driver.get("https://rentmasseur.com")
        time.sleep(3)
        print(f"    Title: {driver.title}")

        # Step 2: Find and click login button/link
        print("[2] Looking for login link...")
        login_link = None
        try:
            # Try common login link patterns
            for selector in [
                "a[href*='login']",
                "a[href*='signin']",
                "a[href*='auth']",
                "button[contains(text(),'Log')]",
                "a[contains(text(),'Log')]",
            ]:
                if "contains" in selector:
                    xpath = f".//{selector.split('[')[0]}[{selector.split('[')[1]}"
                    elements = driver.find_elements(By.XPATH, xpath.replace("contains(text(),", "contains(text(),"))
                else:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    login_link = elements[0]
                    print(f"    Found login element: {login_link.tag_name} href={login_link.get_attribute('href')}")
                    break
        except Exception as e:
            print(f"    Search error: {e}")

        if login_link:
            login_link.click()
            time.sleep(3)
            print(f"    After click URL: {driver.current_url}")
        else:
            # Try direct navigation to login page
            print("    No login link found, trying /login directly...")
            driver.get("https://rentmasseur.com/login")
            time.sleep(3)
            print(f"    URL: {driver.current_url}")

        # Step 3: Fill login form
        print("[3] Filling login form...")

        # Save screenshot of login page
        driver.save_screenshot(os.path.join(output_dir, "login_page.png"))

        # Find username/email and password fields
        username_field = None
        password_field = None
        submit_button = None

        # Try various selectors for username
        for selector in [
            (By.CSS_SELECTOR, "input[name='email']"),
            (By.CSS_SELECTOR, "input[name='username']"),
            (By.CSS_SELECTOR, "input[type='email']"),
            (By.CSS_SELECTOR, "input[id='email']"),
            (By.CSS_SELECTOR, "input[id='username']"),
            (By.CSS_SELECTOR, "input[placeholder*='mail']"),
            (By.CSS_SELECTOR, "input[placeholder*='ser']"),
            (By.XPATH, "//input[@type='email' or @name='email' or @name='username']"),
        ]:
            try:
                elements = driver.find_elements(selector[0], selector[1])
                if elements and elements[0].is_displayed():
                    username_field = elements[0]
                    print(f"    Username field found: {selector[1]}")
                    break
            except Exception:
                continue

        # Try various selectors for password
        for selector in [
            (By.CSS_SELECTOR, "input[name='password']"),
            (By.CSS_SELECTOR, "input[type='password']"),
            (By.CSS_SELECTOR, "input[id='password']"),
            (By.XPATH, "//input[@type='password']"),
        ]:
            try:
                elements = driver.find_elements(selector[0], selector[1])
                if elements and elements[0].is_displayed():
                    password_field = elements[0]
                    print(f"    Password field found: {selector[1]}")
                    break
            except Exception:
                continue

        # Find submit button
        for selector in [
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.CSS_SELECTOR, "input[type='submit']"),
            (By.XPATH, "//button[contains(text(),'Log in') or contains(text(),'Sign in') or contains(text(),'Login')]"),
            (By.CSS_SELECTOR, "button"),
        ]:
            try:
                elements = driver.find_elements(selector[0], selector[1])
                if elements and elements[0].is_displayed():
                    submit_button = elements[0]
                    print(f"    Submit button found: {selector[1]}")
                    break
            except Exception:
                continue

        if username_field and password_field:
            username_field.clear()
            username_field.send_keys("karpathianwolf")
            time.sleep(0.5)

            password_field.clear()
            password_field.send_keys("Lola369!")
            time.sleep(0.5)

            driver.save_screenshot(os.path.join(output_dir, "login_filled.png"))
            print("    Credentials filled.")

            if submit_button:
                submit_button.click()
                print("    Submit clicked.")
            else:
                password_field.send_keys("\n")
                print("    Enter pressed.")

            time.sleep(5)
            print(f"    Post-login URL: {driver.current_url}")
            driver.save_screenshot(os.path.join(output_dir, "after_login.png"))

            # Check if logged in
            page_text = driver.find_element(By.TAG_NAME, "body").text
            if "log out" in page_text.lower() or "logout" in page_text.lower():
                print("    [OK] Login appears successful (logout link found)")
            elif "incorrect" in page_text.lower() or "invalid" in page_text.lower() or "error" in page_text.lower():
                print("    [!] Login may have failed (error text found)")
            else:
                print("    [?] Login status unclear")

            # Save cookies
            cookies = driver.get_cookies()
            with open(os.path.join(output_dir, "cookies.json"), "w") as f:
                json.dump(cookies, f, indent=2)
            print(f"    Cookies saved: {len(cookies)}")

            # Step 4: Navigate to /build-stream
            print("[4] Navigating to /build-stream...")
            driver.get("https://rentmasseur.com/build-stream")
            time.sleep(5)
            print(f"    URL: {driver.current_url}")
            print(f"    Title: {driver.title}")

            # Capture everything
            html = driver.page_source
            with open(os.path.join(output_dir, "build_stream.html"), "w") as f:
                f.write(html)
            print(f"    HTML saved: {len(html)} chars")

            driver.save_screenshot(os.path.join(output_dir, "build_stream.png"))

            body_text = driver.find_element(By.TAG_NAME, "body").text
            with open(os.path.join(output_dir, "build_stream_text.txt"), "w") as f:
                f.write(body_text)
            print(f"    Body text saved: {len(body_text)} chars")

            # Find links
            links = driver.find_elements(By.TAG_NAME, "a")
            link_list = [{"text": l.text.strip(), "href": l.get_attribute("href")} for l in links if l.get_attribute("href")]
            with open(os.path.join(output_dir, "build_stream_links.json"), "w") as f:
                json.dump(link_list, f, indent=2)
            print(f"    Links saved: {len(link_list)}")

            # Find all script/API references
            scripts = driver.find_elements(By.TAG_NAME, "script")
            script_srcs = [s.get_attribute("src") for s in scripts if s.get_attribute("src")]
            with open(os.path.join(output_dir, "build_stream_scripts.json"), "w") as f:
                json.dump(script_srcs, f, indent=2)
            print(f"    Scripts saved: {len(script_srcs)}")

            print("\n[5] Capture complete. Files in /tmp/rentmasseur_capture/")

        else:
            print("    [!] Could not find login form fields")
            print(f"    Username field: {username_field}")
            print(f"    Password field: {password_field}")
            # Dump page source for debugging
            with open(os.path.join(output_dir, "login_page_debug.html"), "w") as f:
                f.write(driver.page_source)
            print("    Debug HTML saved to login_page_debug.html")

    except Exception as e:
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()
        try:
            driver.save_screenshot(os.path.join(output_dir, "error.png"))
        except Exception:
            pass
    finally:
        time.sleep(2)
        driver.quit()
        print("  Browser closed.")


if __name__ == "__main__":
    run()
