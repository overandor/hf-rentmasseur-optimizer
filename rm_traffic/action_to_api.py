"""
Selenium Action → API Endpoint Capture

Performs real actions on rentmasseur.com via Selenium, captures the exact
API calls each action triggers, and outputs a clean API mapping:

  action_name → method, url, headers, body, response

This is the bridge: Selenium does the clicking, we capture the network traffic,
and produce a callable API spec you can use without Selenium.
"""

import json
import os
import re
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from collections import OrderedDict

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    NoSuchElementException, StaleElementReferenceException, WebDriverException,
)

BASE_URL = "https://rentmasseur.com"
USERNAME = "karpathianwolf"
PASSWORD = os.environ.get("RM_PASSWORD", "")
CHROME_PROFILE = "/tmp/rm_action_api"
OUT = Path(__file__).parent
CAPTURE_FILE = OUT / "action_api_map.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("action_api")

# ---------------------------------------------------------------------------
# CDP Network Capture — uses Performance Log + CDP to grab all requests
# ---------------------------------------------------------------------------

INTERCEPT_SCRIPT = r"""
(function() {
    window.__net = [];
    const origFetch = window.fetch;
    window.fetch = function(input, init) {
        const url = typeof input === 'string' ? input : (input?.url || String(input));
        const method = (init?.method) || (typeof input === 'object' ? input?.method : 'GET') || 'GET';
        const body = init?.body || null;
        const headers = {};
        if (init?.headers) {
            if (init.headers instanceof Headers) {
                init.headers.forEach((v,k) => headers[k] = v);
            } else {
                Object.assign(headers, init.headers);
            }
        }
        const entry = { type: 'fetch', url, method, body: body ? String(body).substring(0,3000) : null, headers, ts: Date.now() };
        window.__net.push(entry);
        return origFetch.apply(this, arguments).then(resp => {
            entry.status = resp.status;
            const clone = resp.clone();
            clone.text().then(t => { entry.response = t.substring(0,5000); }).catch(()=>{});
            return resp;
        });
    };
    const origOpen = XMLHttpRequest.prototype.open;
    const origSend = XMLHttpRequest.prototype.send;
    const origSetHeader = XMLHttpRequest.prototype.setRequestHeader;
    XMLHttpRequest.prototype.open = function(method, url) {
        this.__net = { type: 'xhr', url, method, body: null, headers: {}, ts: Date.now() };
        return origOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.setRequestHeader = function(k, v) {
        if (this.__net) this.__net.headers[k] = v;
        return origSetHeader.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function(body) {
        if (this.__net) {
            this.__net.body = body ? String(body).substring(0,3000) : null;
            window.__net.push(this.__net);
            this.addEventListener('load', function() {
                this.__net.status = this.status;
                this.__net.response = this.responseText.substring(0,5000);
            });
        }
        return origSend.apply(this, arguments);
    };
})();
"""


class ActionCapture:
    """Run a Selenium action and capture the API calls it triggered."""

    def __init__(self, driver):
        self.driver = driver
        self._marker = 0
        self._installed = False

    def install(self):
        """Install interceptor AFTER login to avoid breaking login page JS."""
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": INTERCEPT_SCRIPT
        })
        self._installed = True
        log.info("Network interceptor installed")

    def _get_net(self):
        try:
            return self.driver.execute_script(
                "return (window.__net || []).slice();"
            ) or []
        except WebDriverException:
            return []

    def mark(self):
        """Set a marker — call before an action to know which calls are new."""
        self._marker = len(self._get_net())
        return self._marker

    def capture_new(self):
        """Get all network entries since last mark."""
        all_net = self._get_net()
        new = all_net[self._marker:]
        self._marker = len(all_net)
        return new

    def capture_all(self):
        return self._get_net()


# ---------------------------------------------------------------------------
# Browser setup
# ---------------------------------------------------------------------------

def create_driver():
    opts = Options()
    opts.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument(f"--user-data-dir={CHROME_PROFILE}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    return webdriver.Chrome(options=opts)


def dismiss_popups(driver):
    time.sleep(1)
    # First remove any overlay dialogs via JS
    try:
        driver.execute_script("""
            document.querySelectorAll('.DialogOverlay, [class*="overlay"]').forEach(e => e.remove());
        """)
    except Exception:
        pass
    for xpath in [
        "//button[contains(text(),'Not now')]",
        "//button[contains(text(),'Accept all')]",
        "//button[contains(text(),'Close')]",
        "//*[contains(@aria-label,'Close')]",
    ]:
        try:
            for el in driver.find_elements(By.XPATH, xpath):
                if el.is_displayed():
                    driver.execute_script("arguments[0].click();", el)
                    time.sleep(0.5)
        except Exception:
            pass


def login(driver):
    log.info("Logging in...")
    driver.get(f"{BASE_URL}/login")
    time.sleep(4)
    dismiss_popups(driver)

    for inp in driver.find_elements(By.CSS_SELECTOR, "input"):
        itype = (inp.get_attribute("type") or "").lower()
        iname = (inp.get_attribute("name") or "").lower()
        if (itype == "email" or "email" in iname or "user" in iname) and inp.is_displayed():
            inp.clear()
            inp.send_keys(USERNAME)
        if itype == "password" and inp.is_displayed():
            inp.clear()
            inp.send_keys(PASSWORD)

    time.sleep(0.3)
    for by, sel in [
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.XPATH, "//button[contains(text(),'LOG')]"),
        (By.XPATH, "//button[contains(text(),'Log')]"),
        (By.CSS_SELECTOR, "form button"),
    ]:
        for el in driver.find_elements(by, sel):
            if el.is_displayed():
                driver.execute_script("arguments[0].click();", el)
                time.sleep(6)
                break
        else:
            continue
        break

    dismiss_popups(driver)
    ok = "/login" not in driver.current_url
    log.info("Login: %s", "OK" if ok else "FAILED")
    return ok


# ---------------------------------------------------------------------------
# Actions — each returns (action_name, captured_api_calls)
# ---------------------------------------------------------------------------

def action_load_settings(cap):
    """Load settings dashboard."""
    cap.mark()
    cap.driver.get(f"{BASE_URL}/settings")
    time.sleep(5)
    dismiss_popups(cap.driver)
    return "load_settings", cap.capture_new()


def action_open_availability_modal(cap):
    """Open the availability modal."""
    cap.driver.get(f"{BASE_URL}/settings?availability=1")
    time.sleep(5)
    dismiss_popups(cap.driver)
    cap.mark()
    try:
        panel = cap.driver.find_element(By.CSS_SELECTOR, ".AvailabilityPanel")
        panel.click()
        time.sleep(3)
    except Exception:
        pass
    return "open_availability_modal", cap.capture_new()


def action_set_availability(cap):
    """Set availability to Available with 1 hour duration."""
    driver = cap.driver
    driver.get(f"{BASE_URL}/settings?availability=1")
    time.sleep(5)
    dismiss_popups(driver)

    # Open modal
    try:
        panel = driver.find_element(By.CSS_SELECTOR, ".AvailabilityPanel")
        panel.click()
        time.sleep(2)
    except Exception:
        pass

    cap.mark()

    # Select "Available"
    for by, sel in [
        (By.XPATH, "//label[contains(text(),'Available')]"),
        (By.XPATH, "//*[contains(text(),'Available') and not(contains(text(),'Not')) and not(contains(text(),'Status'))]"),
        (By.CSS_SELECTOR, "input[type='radio']"),
    ]:
        try:
            els = driver.find_elements(by, sel)
            for el in els:
                if el.is_displayed():
                    el.click()
                    time.sleep(0.5)
                    break
        except Exception:
            pass

    # Select duration 1 Hour
    from selenium.webdriver.support.ui import Select
    for sel_el in driver.find_elements(By.CSS_SELECTOR, "select"):
        try:
            s = Select(sel_el)
            if "1 Hour" in [o.text for o in s.options]:
                s.select_by_visible_text("1 Hour")
                time.sleep(0.3)
                break
        except Exception:
            pass

    # Click SET
    for by, sel in [
        (By.XPATH, "//button[contains(text(),'SET')]"),
        (By.XPATH, "//button[contains(text(),'Set')]"),
    ]:
        for el in driver.find_elements(by, sel):
            if el.is_displayed():
                el.click()
                time.sleep(3)
                break

    return "set_availability", cap.capture_new()


def action_toggle_visibility(cap):
    """Toggle profile visibility."""
    cap.driver.get(f"{BASE_URL}/settings")
    time.sleep(4)
    dismiss_popups(cap.driver)
    cap.mark()
    try:
        vis = cap.driver.find_element(By.CSS_SELECTOR, "#visibility")
        vis.click()
        time.sleep(3)
    except Exception:
        pass
    return "toggle_visibility", cap.capture_new()


def action_toggle_sms(cap):
    """Toggle SMS alerts."""
    cap.driver.get(f"{BASE_URL}/settings")
    time.sleep(4)
    dismiss_popups(cap.driver)
    cap.mark()
    try:
        sms = cap.driver.find_element(By.CSS_SELECTOR, "#sms")
        sms.click()
        time.sleep(3)
    except Exception:
        pass
    return "toggle_sms_alerts", cap.capture_new()


def action_toggle_track_actions(cap):
    """Toggle track actions."""
    cap.driver.get(f"{BASE_URL}/settings")
    time.sleep(4)
    dismiss_popups(cap.driver)
    cap.mark()
    try:
        track = cap.driver.find_element(By.CSS_SELECTOR, "#trackActions")
        track.click()
        time.sleep(3)
    except Exception:
        pass
    return "toggle_track_actions", cap.capture_new()


def action_search_city(cap):
    """Search masseurs in a city."""
    cap.mark()
    cap.driver.get(f"{BASE_URL}/gay-massage/manhattan-ny/")
    time.sleep(5)
    dismiss_popups(cap.driver)
    # Scroll to trigger lazy load
    cap.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(3)
    return "search_city", cap.capture_new()


def action_search_available(cap):
    """Search available-now masseurs."""
    cap.mark()
    cap.driver.get(f"{BASE_URL}/gay-massage/manhattan-ny/?available=1")
    time.sleep(5)
    dismiss_popups(cap.driver)
    return "search_available_now", cap.capture_new()


def action_load_more(cap):
    """Click 'Load more' on search results."""
    cap.driver.get(f"{BASE_URL}/gay-massage/manhattan-ny/")
    time.sleep(4)
    dismiss_popups(cap.driver)
    cap.mark()
    try:
        btn = cap.driver.find_element(By.XPATH, "//button[contains(text(),'Load more')]")
        btn.click()
        time.sleep(3)
    except Exception:
        pass
    return "load_more_results", cap.capture_new()


def action_view_profile(cap):
    """View a masseur profile."""
    cap.mark()
    cap.driver.get(f"{BASE_URL}/ArmyMike")
    time.sleep(4)
    return "view_profile", cap.capture_new()


def action_load_mailbox(cap):
    """Load mailbox."""
    cap.mark()
    cap.driver.get(f"{BASE_URL}/settings/mailbox")
    time.sleep(4)
    dismiss_popups(cap.driver)
    return "load_mailbox", cap.capture_new()


def action_get_stats(cap):
    """Scroll to stats section to trigger stats API."""
    cap.driver.get(f"{BASE_URL}/settings")
    time.sleep(4)
    dismiss_popups(cap.driver)
    cap.mark()
    # Scroll to bottom to trigger lazy stats loading
    cap.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(5)
    return "load_stats", cap.capture_new()


# ---------------------------------------------------------------------------
# Process captured calls into clean API spec
# ---------------------------------------------------------------------------

def clean_url(url):
    """Remove base URL prefix, keep path + query."""
    if url.startswith(BASE_URL):
        return url[len(BASE_URL):]
    if url.startswith("https://rentmasseur.com"):
        return url[len("https://rentmasseur.com"):]
    return url


def is_api_call(entry):
    """Filter out static assets, JS chunks, images."""
    url = entry.get("url", "").lower()
    if not url:
        return False
    if any(url.endswith(ext) for ext in [
        ".js", ".css", ".png", ".jpg", ".jpeg", ".svg", ".gif",
        ".woff", ".woff2", ".ico", ".webp", ".map",
    ]):
        return False
    if "/_next/static/" in url:
        return False
    if "/images/" in url:
        return False
    if "google" in url or "gstatic" in url or "cloudflare" in url:
        return False
    if "fonts." in url:
        return False
    return True


def parse_response(resp_text):
    """Try to parse response as JSON, return structured data."""
    if not resp_text:
        return None
    try:
        data = json.loads(resp_text)
        if isinstance(data, dict):
            return {"keys": list(data.keys())[:20], "sample": json.dumps(data, default=str)[:1000]}
        if isinstance(data, list) and data:
            if isinstance(data[0], dict):
                return {"type": "array", "count": len(data), "item_keys": list(data[0].keys())[:15]}
            return {"type": "array", "count": len(data)}
        return {"type": type(data).__name__, "value": str(data)[:200]}
    except (json.JSONDecodeError, TypeError):
        return {"raw": resp_text[:300]}


def parse_body(body_text):
    """Parse request body."""
    if not body_text:
        return None
    try:
        return json.loads(body_text)
    except (json.JSONDecodeError, TypeError):
        return body_text[:300]


def build_api_map(action_results):
    """Build the action → API mapping."""
    api_map = OrderedDict()

    for action_name, calls in action_results:
        api_calls = []
        for call in calls:
            if not is_api_call(call):
                continue

            url = call.get("url", "")
            method = (call.get("method") or "GET").upper()
            clean = clean_url(url)

            api_call = {
                "method": method,
                "path": clean,
                "full_url": url,
                "request_body": parse_body(call.get("body")),
                "request_headers": call.get("headers", {}),
                "response_status": call.get("status"),
                "response": parse_response(call.get("response")),
            }
            api_calls.append(api_call)

        api_map[action_name] = {
            "action": action_name,
            "api_calls": api_calls,
            "call_count": len(api_calls),
        }

    return api_map


def write_output(api_map):
    """Write JSON + readable summary."""
    # JSON
    with open(CAPTURE_FILE, "w") as f:
        json.dump(api_map, f, indent=2, default=str)

    # Console summary
    print(f"\n{'='*60}")
    print(f"  ACTION → API ENDPOINT MAP")
    print(f"{'='*60}\n")

    for action_name, data in api_map.items():
        calls = data["api_calls"]
        print(f"  [{action_name}] — {len(calls)} API calls")
        for c in calls:
            status = c.get("response_status") or "?"
            body = ""
            if c.get("request_body"):
                body = f" body={json.dumps(c['request_body'], default=str)[:60]}"
            resp = ""
            if c.get("response") and isinstance(c["response"], dict):
                if "keys" in c["response"]:
                    resp = f" → {c['response']['keys'][:5]}"
                elif "type" in c["response"]:
                    resp = f" → {c['response']['type']}"
            print(f"    {c['method']:6s} {status} {c['path'][:60]}{body}{resp}")
        print()

    print(f"  Output: {CAPTURE_FILE}")
    print(f"  Total actions: {len(api_map)}")
    total = sum(d["call_count"] for d in api_map.values())
    print(f"  Total API calls captured: {total}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    log.info("=== Action → API Capture ===")
    driver = create_driver()
    cap = ActionCapture(driver)

    try:
        if not login(driver):
            log.error("Login failed")
            return

        # Install interceptor AFTER login
        cap.install()
        # Navigate to settings to reload with interceptor active
        driver.get(f"{BASE_URL}/settings")
        time.sleep(3)

        # Run all actions
        actions = [
            action_load_settings,
            action_open_availability_modal,
            action_set_availability,
            action_toggle_visibility,
            action_toggle_sms,
            action_toggle_track_actions,
            action_search_city,
            action_search_available,
            action_load_more,
            action_view_profile,
            action_load_mailbox,
            action_get_stats,
        ]

        results = []
        for action_fn in actions:
            log.info("Running: %s", action_fn.__name__)
            try:
                name, calls = action_fn(cap)
                api_calls = [c for c in calls if is_api_call(c)]
                log.info("  → %d API calls captured", len(api_calls))
                results.append((name, calls))
            except Exception as e:
                log.error("  FAILED: %s", e)

        # Build and write output
        api_map = build_api_map(results)
        write_output(api_map)

    except Exception as e:
        log.error("Fatal: %s", e)
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()
        log.info("Done")


if __name__ == "__main__":
    run()
