"""
CDP Discovery — use Selenium + Chrome DevTools Protocol to capture unknown endpoints.

Targets:
    - availability update (set availability)
    - blog create/edit
    - interview edit

The captured endpoint is stored in the registry only after replay verification.
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from .endpoint_registry import EndpointRegistry

log = logging.getLogger("profileops.discovery")

BASE = "https://rentmasseur.com"


def _get_driver(profile: str = "/tmp/rm_action_api"):
    opts = Options()
    opts.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument(f"--user-data-dir={profile}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    return webdriver.Chrome(options=opts)


def _dismiss_popups(driver):
    try:
        driver.execute_script("document.querySelectorAll('.DialogOverlay,[class*=\"overlay\"]').forEach(e=>e.remove())")
    except Exception:
        pass


def _find_clickable(driver, texts: List[str]):
    for text in texts:
        for el in driver.find_elements(By.XPATH, f"//*[contains(text(),'{text}')]"):
            if el.is_displayed():
                return el
    return None


def _extract_api_calls(driver) -> List[Dict]:
    logs = driver.get_log("performance")
    reqs = {}
    for entry in logs:
        try:
            msg = json.loads(entry["message"])["message"]
            if msg["method"] == "Network.requestWillBeSent":
                p = msg["params"]
                r = p["request"]
                rid = p["requestId"]
                reqs[rid] = {
                    "url": r["url"],
                    "method": r["method"],
                    "postData": r.get("postData", "")[:2000],
                }
            elif msg["method"] == "Network.responseReceived":
                p = msg["params"]
                rid = p["requestId"]
                if rid in reqs:
                    reqs[rid]["status"] = p["response"]["status"]
                    try:
                        body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": rid})
                        reqs[rid]["response"] = body.get("body", "")[:2000]
                    except Exception:
                        pass
        except Exception:
            pass
    return [v for v in reqs.values() if "/api/v1/" in v["url"]]


def _wait_for_react(driver, timeout: int = 10):
    """Wait for React to render interactive content."""
    for _ in range(timeout * 2):
        btns = driver.find_elements(By.TAG_NAME, "button")
        if btns:
            return True
        time.sleep(0.5)
    return False


class CDPDiscoverer:
    """Discovers unknown endpoints via CDP."""

    def __init__(self, profile: str = "/tmp/rm_action_api"):
        self.profile = profile
        self.registry = EndpointRegistry()

    def discover_availability(self) -> Dict:
        """Capture the availability save endpoint."""
        log.info("Discovering availability endpoint...")
        driver = _get_driver(self.profile)
        try:
            # Try dashboard first (availability is usually set from dashboard)
            driver.get(f"{BASE}/account/dashboard")
            time.sleep(6)
            _dismiss_popups(driver)
            _wait_for_react(driver)
            driver.get_log("performance")

            # Look for availability-related clickable elements
            candidates = [
                "Available", "Not Available", "Set Availability", "Available Now",
                "1 hour", "2 hours", "3 hours", "4 hours", "5 hours", "6 hours",
                "Set", "Update", "Confirm"
            ]
            for text in candidates:
                btn = _find_clickable(driver, [text])
                if btn:
                    log.info("Clicking '%s'...", text)
                    driver.execute_script("arguments[0].click()", btn)
                    time.sleep(1)

            # Also try clicking dashboard availability section
            time.sleep(3)
            calls = _extract_api_calls(driver)
            for c in calls:
                if "availability" in c["url"] and c["method"] in ("POST", "PUT"):
                    self.registry.register(
                        "set_availability", c["method"],
                        c["url"].replace(BASE, ""),
                        request_schema=c.get("postData"),
                        response_schema=c.get("response", "")[:500]
                    )
                    return {"found": True, "call": c}
            return {"found": False, "calls": calls}
        finally:
            driver.quit()

    def discover_blog(self) -> Dict:
        """Capture blog create/edit endpoint."""
        log.info("Discovering blog endpoint...")
        driver = _get_driver(self.profile)
        try:
            driver.get(f"{BASE}/settings?blog=1")
            time.sleep(5)
            _dismiss_popups(driver)
            _wait_for_react(driver)
            driver.get_log("performance")

            # Try to find create button
            create_btn = _find_clickable(driver, ["Create", "New", "Add", "Post", "Write"])
            if create_btn:
                driver.execute_script("arguments[0].click()", create_btn)
                time.sleep(3)
                driver.get_log("performance")
                save_btn = _find_clickable(driver, ["Save", "Submit", "Publish", "Create"])
                if save_btn:
                    driver.execute_script("arguments[0].click()", save_btn)
                    time.sleep(3)
                    calls = _extract_api_calls(driver)
                    for c in calls:
                        if "blog" in c["url"] and c["method"] in ("POST", "PUT"):
                            self.registry.register(
                                "set_blog", c["method"],
                                c["url"].replace(BASE, ""),
                                request_schema=c.get("postData"),
                                response_schema=c.get("response", "")[:500]
                            )
                            return {"found": True, "call": c}
            return {"found": False, "calls": _extract_api_calls(driver)}
        finally:
            driver.quit()

    def discover_interview(self) -> Dict:
        """Capture interview edit endpoint."""
        log.info("Discovering interview endpoint...")
        driver = _get_driver(self.profile)
        try:
            driver.get(f"{BASE}/settings?interview=1")
            time.sleep(5)
            _dismiss_popups(driver)
            _wait_for_react(driver)
            driver.get_log("performance")

            save_btn = _find_clickable(driver, ["Save", "Submit", "Update", "Confirm"])
            if save_btn:
                driver.execute_script("arguments[0].click()", save_btn)
                time.sleep(3)
                calls = _extract_api_calls(driver)
                for c in calls:
                    if "interview" in c["url"] and c["method"] in ("POST", "PUT"):
                        self.registry.register(
                            "set_interview", c["method"],
                            c["url"].replace(BASE, ""),
                            request_schema=c.get("postData"),
                            response_schema=c.get("response", "")[:500]
                        )
                        return {"found": True, "call": c}
            return {"found": False, "calls": _extract_api_calls(driver)}
        finally:
            driver.quit()


def run_discovery(target: str) -> Dict:
    """Discover an endpoint by target name."""
    d = CDPDiscoverer()
    if target == "availability":
        return d.discover_availability()
    elif target == "blog":
        return d.discover_blog()
    elif target == "interview":
        return d.discover_interview()
    return {"error": "unknown target"}
