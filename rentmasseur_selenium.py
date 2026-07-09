"""Selenium browser session for rentmasseur.com.

Opens Chrome, navigates to the site, lets you log in manually,
then captures authenticated content (HTML, cookies, screenshots).

Usage:
  python3 rentmasseur_selenium.py              # interactive login
  python3 rentmasseur_selenium.py --url /build-stream  # capture specific page after login
  python3 rentmasseur_selenium.py --headless    # headless mode (won't work for manual login)
"""

import argparse
import json
import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def create_driver(headless=False):
    """Create a Chrome WebDriver."""
    options = Options()
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    options.binary_location = chrome_path

    if headless:
        options.add_argument("--headless=new")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--user-data-dir=/tmp/rentmasseur_chrome_profile")

    # Try chromedriver from common locations, fall back to auto-discovery
    try:
        driver = webdriver.Chrome(options=options)
    except Exception as e:
        print(f"Chrome WebDriver failed: {e}")
        print("Trying Safari as fallback...")
        from selenium.webdriver.safari.options import Options as SafariOptions
        safari_opts = SafariOptions()
        driver = webdriver.Safari(options=safari_opts)

    return driver


def wait_for_login(driver, timeout=120):
    """Wait for user to log in manually."""
    print("\n" + "=" * 60)
    print("  BROWSER OPENED — Log in to rentmasseur.com")
    print("  The script will wait up to 2 minutes for you to log in.")
    print("  Press Enter in this terminal when you're logged in.")
    print("=" * 60 + "\n")

    input("  Press Enter after you've logged in... ")

    # Save cookies
    cookies = driver.get_cookies()
    cookie_path = "/tmp/rentmasseur_cookies.json"
    with open(cookie_path, "w") as f:
        json.dump(cookies, f, indent=2)
    print(f"  Cookies saved: {cookie_path} ({len(cookies)} cookies)")

    return cookies


def capture_page(driver, path="/", output_dir="/tmp/rentmasseur_capture"):
    """Capture a page's content after login."""
    os.makedirs(output_dir, exist_ok=True)

    url = f"https://rentmasseur.com{path}" if path.startswith("/") else path
    print(f"  Navigating to: {url}")
    driver.get(url)

    time.sleep(3)  # Let page load

    # Capture HTML
    html = driver.page_source
    html_path = os.path.join(output_dir, "page.html")
    with open(html_path, "w") as f:
        f.write(html)
    print(f"  HTML saved: {html_path} ({len(html)} chars)")

    # Capture screenshot
    ss_path = os.path.join(output_dir, "screenshot.png")
    driver.save_screenshot(ss_path)
    print(f"  Screenshot saved: {ss_path}")

    # Capture cookies
    cookies = driver.get_cookies()
    cookie_path = os.path.join(output_dir, "cookies.json")
    with open(cookie_path, "w") as f:
        json.dump(cookies, f, indent=2)
    print(f"  Cookies saved: {cookie_path} ({len(cookies)} cookies)")

    # Capture page title and URL
    print(f"  Title: {driver.title}")
    print(f"  URL: {driver.current_url}")

    # Try to find interesting elements
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
        text_path = os.path.join(output_dir, "body_text.txt")
        with open(text_path, "w") as f:
            f.write(body_text)
        print(f"  Body text saved: {text_path} ({len(body_text)} chars)")
    except Exception:
        pass

    # Find all links
    try:
        links = driver.find_elements(By.TAG_NAME, "a")
        link_list = []
        for link in links:
            href = link.get_attribute("href")
            text = link.text.strip()
            if href:
                link_list.append({"text": text, "href": href})
        links_path = os.path.join(output_dir, "links.json")
        with open(links_path, "w") as f:
            json.dump(link_list, f, indent=2)
        print(f"  Links saved: {links_path} ({len(link_list)} links)")
    except Exception:
        pass

    # Find all forms
    try:
        forms = driver.find_elements(By.TAG_NAME, "form")
        form_list = []
        for form in forms:
            form_list.append({
                "action": form.get_attribute("action"),
                "method": form.get_attribute("method"),
                "id": form.get_attribute("id"),
            })
        forms_path = os.path.join(output_dir, "forms.json")
        with open(forms_path, "w") as f:
            json.dump(form_list, f, indent=2)
        print(f"  Forms saved: {forms_path} ({len(form_list)} forms)")
    except Exception:
        pass

    return {
        "url": driver.current_url,
        "title": driver.title,
        "html_path": html_path,
        "screenshot_path": ss_path,
        "cookies": len(cookies),
        "links": len(link_list) if 'link_list' in dir() else 0,
    }


def main():
    parser = argparse.ArgumentParser(description="Selenium session for rentmasseur.com")
    parser.add_argument("--url", default="/", help="Path to capture after login (e.g. /build-stream)")
    parser.add_argument("--headless", action="store_true", help="Run headless (no manual login)")
    parser.add_argument("--capture-only", action="store_true", help="Skip login, just capture (uses saved cookies)")
    args = parser.parse_args()

    driver = create_driver(headless=args.headless)

    try:
        # Navigate to the site
        driver.get("https://rentmasseur.com")
        time.sleep(2)
        print(f"  Loaded: {driver.current_url}")
        print(f"  Title: {driver.title}")

        if not args.capture_only:
            # Wait for manual login
            wait_for_login(driver)

        # Capture the requested page
        print()
        result = capture_page(driver, args.url)
        print()
        print("  Capture complete:")
        print(json.dumps(result, indent=2))

    except Exception as e:
        print(f"  Error: {e}")
        # Try to save screenshot on error
        try:
            driver.save_screenshot("/tmp/rentmasseur_error.png")
            print("  Error screenshot: /tmp/rentmasseur_error.png")
        except Exception:
            pass
    finally:
        input("\n  Press Enter to close browser...")
        driver.quit()
        print("  Browser closed.")


if __name__ == "__main__":
    main()
