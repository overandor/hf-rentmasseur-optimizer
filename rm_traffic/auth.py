"""
AuthSession — login, JWT, session health.

Never stores raw password in code. Reads from env vars or keychain.
"""

import json
import logging
import os
import subprocess
from typing import Optional

import requests

from .api_client import RentMasseurAPI

log = logging.getLogger("profileops.auth")


def get_credential(name: str) -> Optional[str]:
    """Read credential from environment or macOS keychain."""
    val = os.environ.get(name)
    if val:
        return val
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", f"rm_profileops_{name}", "-w"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def save_token_to_keychain(token: str):
    """Save access token to keychain (optional)."""
    try:
        subprocess.run(
            ["security", "add-generic-password", "-s", "rm_profileops_access_token",
             "-a", "rm_profileops", "-w", token, "-U"],
            capture_output=True, text=True, timeout=5
        )
    except Exception as e:
        log.warning("Could not save token to keychain: %s", e)


def load_session_from_file(path: str) -> Optional[list]:
    """Load cookies from a saved session JSON file."""
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return data.get("cookies", [])
    except Exception as e:
        log.warning("Could not load session file: %s", e)
        return None


class AuthSession:
    """Manages login and session state."""

    def __init__(self, api: RentMasseurAPI, session_file: Optional[str] = None):
        self.api = api
        self.session_file = session_file
        self.username = None

    def login(self, username: Optional[str] = None, password: Optional[str] = None) -> bool:
        """Login using credentials or saved session."""
        self.username = username or get_credential("RM_USER")
        password = password or get_credential("RM_PASS")

        if not self.username or not password:
            log.error("Credentials missing. Set RM_USER and RM_PASS environment variables.")
            return False

        # Try saved session first if available
        if self.session_file:
            cookies = load_session_from_file(self.session_file)
            if cookies:
                self.api.load_cookies(cookies)
                log.info("Loaded saved session cookies")
                # Test with a lightweight request
                try:
                    self.api.get_keeponline()
                    log.info("Saved session is valid")
                    return True
                except Exception:
                    log.info("Saved session expired, trying login")

        return self.api.login(self.username, password)

    def is_authenticated(self) -> bool:
        try:
            self.api.get_keeponline()
            return True
        except Exception:
            return False
