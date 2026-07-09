"""
App Store Connect API client — real JWT auth, create app records, upload builds, pull metrics.
"""

import json
import time
import subprocess
from pathlib import Path
from datetime import datetime, timezone

try:
    import jwt
    import requests
except ImportError:
    pass

ASC_BASE = "https://api.appstoreconnect.apple.com/v1"

class AppStoreConnectClient:
    def __init__(self, key_id, issuer_id, key_path):
        self.key_id = key_id
        self.issuer_id = issuer_id
        self.key_path = key_path
        self._token = None
        self._token_exp = 0

    def _get_token(self):
        if self._token and time.time() < self._token_exp - 60:
            return self._token

        with open(self.key_path, 'rb') as f:
            private_key = f.read()

        now = int(time.time())
        payload = {
            "iss": self.issuer_id,
            "iat": now,
            "exp": now + 1200,
            "aud": "appstoreconnect-v1",
        }
        headers = {
            "alg": "ES256",
            "kid": self.key_id,
            "typ": "JWT",
        }
        self._token = jwt.encode(payload, private_key, algorithm="ES256", headers=headers)
        self._token_exp = now + 1200
        return self._token

    def _headers(self):
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    def list_apps(self):
        r = requests.get(f"{ASC_BASE}/apps", headers=self._headers(), timeout=30)
        if r.status_code == 200:
            return r.json().get("data", [])
        return []

    def create_app(self, name, bundle_id, primary_locale="en-US", sku=None):
        data = {
            "data": {
                "type": "apps",
                "attributes": {
                    "name": name,
                    "bundleId": bundle_id,
                    "primaryLocale": primary_locale,
                    "sku": sku or bundle_id.replace(".", "-"),
                }
            }
        }
        r = requests.post(f"{ASC_BASE}/apps", headers=self._headers(), json=data, timeout=30)
        if r.status_code == 201:
            return r.json()["data"]
        elif r.status_code == 409:
            # App already exists — find it
            apps = self.list_apps()
            for app in apps:
                if app["attributes"].get("bundleId") == bundle_id:
                    return app
        return None

    def get_app(self, app_id):
        r = requests.get(f"{ASC_BASE}/apps/{app_id}", headers=self._headers(), timeout=30)
        if r.status_code == 200:
            return r.json()["data"]
        return None

    def create_version(self, app_id, version_string="1.0.0", platform="MACOS"):
        data = {
            "data": {
                "type": "appStoreVersions",
                "attributes": {
                    "versionString": version_string,
                    "platform": platform,
                    "releaseType": "MANUAL",
                },
                "relationships": {
                    "app": {
                        "data": {"type": "apps", "id": app_id}
                    }
                }
            }
        }
        r = requests.post(f"{ASC_BASE}/appStoreVersions", headers=self._headers(), json=data, timeout=30)
        if r.status_code == 201:
            return r.json()["data"]
        return None

    def upload_build(self, app_bundle_path, app_id):
        """Upload a .app via altool (notarytool for notarization, altool for App Store)."""
        cmd = [
            "xcrun", "altool", "--upload-app",
            "--type", "macos",
            "--file", str(app_bundle_path),
            "--apiKey", self.key_id,
            "--apiIssuer", self.issuer_id,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        return r.returncode == 0, r.stdout + r.stderr

    def get_sales_metrics(self, app_id, report_date=None):
        """Pull download/revenue metrics from App Store Connect."""
        if not report_date:
            report_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Get app downloads
        params = {
            "filter[frequency]": "DAILY",
            "filter[reportDate]": report_date,
            "filter[appId]": app_id,
        }
        r = requests.get(
            f"{ASC_BASE}/salesReports",
            headers=self._headers(),
            params=params,
            timeout=30,
        )
        if r.status_code == 200:
            return r.json().get("data", [])
        return []

    def get_app_analytics(self, app_id):
        """Get analytics (impressions, downloads, revenue) for an app."""
        data = {
            "filter": {
                "startTime": datetime.now(timezone.utc).isoformat(),
                "endTime": datetime.now(timezone.utc).isoformat(),
            },
            "group": "app",
            "measure": "installs,impressions,proceeds",
        }
        r = requests.post(
            f"{ASC_BASE}/analyticsReports",
            headers=self._headers(),
            json=data,
            timeout=30,
        )
        if r.status_code == 200:
            return r.json().get("data", [])
        return []

    def create_screenshot_set(self, version_id, device_type="desktop"):
        """Create a screenshot set for an app version."""
        data = {
            "data": {
                "type": "appScreenshotSets",
                "attributes": {
                    "screenshotDisplayType": "APP_DESKTOP" if device_type == "desktop" else "APP_IPAD_PRO",
                },
                "relationships": {
                    "appStoreVersion": {
                        "data": {"type": "appStoreVersions", "id": version_id}
                    }
                }
            }
        }
        r = requests.post(f"{ASC_BASE}/appScreenshotSets", headers=self._headers(), json=data, timeout=30)
        if r.status_code == 201:
            return r.json()["data"]
        return None

    def upload_screenshot(self, screenshot_set_id, image_path):
        """Upload a screenshot to a screenshot set."""
        # Step 1: Reserve upload
        file_size = Path(image_path).stat().st_size
        data = {
            "data": {
                "type": "appScreenshots",
                "attributes": {
                    "fileSize": file_size,
                    "fileName": Path(image_path).name,
                },
                "relationships": {
                    "appScreenshotSet": {
                        "data": {"type": "appScreenshotSets", "id": screenshot_set_id}
                    }
                }
            }
        }
        r = requests.post(f"{ASC_BASE}/appScreenshots", headers=self._headers(), json=data, timeout=30)
        if r.status_code != 201:
            return False, r.text

        screenshot = r.json()["data"]
        upload_ops = screenshot.get("attributes", {}).get("uploadOperations", [])
        screenshot_id = screenshot["id"]

        # Step 2: Upload the file bytes
        with open(image_path, 'rb') as f:
            for op in upload_ops:
                url = op.get("url")
                method = op.get("method", "PUT")
                headers = {k: v for k, v in op.get("requestHeaders", [])}
                r = requests.put(url, data=f.read(), headers=headers, timeout=120)
                if r.status_code not in (200, 201):
                    return False, f"Upload failed: {r.status_code}"

        # Step 3: Commit
        commit_data = {
            "data": {
                "type": "appScreenshots",
                "id": screenshot_id,
                "attributes": {"uploaded": True},
            }
        }
        r = requests.patch(
            f"{ASC_BASE}/appScreenshots/{screenshot_id}",
            headers=self._headers(),
            json=commit_data,
            timeout=30,
        )
        return r.status_code == 200, r.text

    def set_app_price(self, app_id, price_tier="0"):
        """Set app price tier (0 = free)."""
        # Get default price point
        r = requests.get(f"{ASC_BASE}/appPricePoints", headers=self._headers(), timeout=30)
        if r.status_code != 200:
            return False

        points = r.json().get("data", [])
        target = None
        for p in points:
            if p["attributes"].get("priceTier") == price_tier:
                target = p
                break
        if not target:
            return False

        data = {
            "data": {
                "type": "appPrices",
                "attributes": {},
                "relationships": {
                    "app": {"data": {"type": "apps", "id": app_id}},
                    "pricePoint": {"data": {"type": "appPricePoints", "id": target["id"]}},
                }
            }
        }
        r = requests.post(f"{ASC_BASE}/appPrices", headers=self._headers(), json=data, timeout=30)
        return r.status_code == 201
