"""
Python bridge to AppleScript and shell commands for macOS automation.

Safe, accessible, voice-over friendly.
"""

import subprocess
import time
from typing import List, Optional, Dict


def run_applescript(script: str) -> str:
    """Execute AppleScript and return output."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=30
        )
        return result.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"


def run_shell(cmd: List[str], timeout: int = 30) -> str:
    """Run a shell command and return stdout."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"


# ---------------------------------------------------------------------------
# App Control
# ---------------------------------------------------------------------------

def list_running_apps() -> List[str]:
    """List all running applications."""
    script = '''
    tell application "System Events"
        set appNames to name of every application process
        return appNames as string
    end tell
    '''
    result = run_applescript(script)
    return [x.strip() for x in result.split(",") if x.strip()]


def launch_app(app_name: str) -> str:
    """Launch an application."""
    script = f'''
    tell application "{app_name}"
        activate
        return "launched"
    end tell
    '''
    return run_applescript(script)


def quit_app(app_name: str) -> str:
    """Quit an application."""
    script = f'''
    tell application "{app_name}" to quit
    return "quit"
    '''
    return run_applescript(script)


def focus_app(app_name: str) -> str:
    """Bring an application to front."""
    return launch_app(app_name)


def get_app_windows(app_name: str) -> List[str]:
    """List windows of an application."""
    script = f'''
    tell application "System Events"
        tell application process "{app_name}"
            return name of every window
        end tell
    end tell
    '''
    result = run_applescript(script)
    return [x.strip() for x in result.split(",") if x.strip()]


# ---------------------------------------------------------------------------
# UI Interaction
# ---------------------------------------------------------------------------

def type_text(text: str) -> str:
    """Type text into the focused application."""
    script = f'''
    tell application "System Events"
        keystroke "{text}"
    end tell
    return "typed"
    '''
    return run_applescript(script)


def press_key(key: str, modifiers: Optional[List[str]] = None) -> str:
    """Press a key with optional modifiers (command, control, option, shift)."""
    mods = ""
    if modifiers:
        mods = " using {" + ", ".join(modifiers) + "}"
    script = f'''
    tell application "System Events"
        key code {keycode_for_key(key)}{mods}
    end tell
    return "pressed"
    '''
    return run_applescript(script)


def keycode_for_key(key: str) -> int:
    """Map common key names to AppleScript key codes."""
    codes = {
        "return": 36, "enter": 36, "tab": 48, "space": 49,
        "escape": 53, "delete": 51, "forward_delete": 117,
        "home": 123, "end": 119, "page_up": 116, "page_down": 121,
        "left": 123, "right": 124, "down": 125, "up": 126,
        "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96,
        "f6": 97, "f7": 98, "f8": 100, "f9": 101, "f10": 109,
        "f11": 103, "f12": 111,
    }
    return codes.get(key.lower(), 0)


def click_button(app_name: str, button_name: str) -> str:
    """Click a button by name in an application."""
    script = f'''
    tell application "System Events"
        tell application process "{app_name}"
            click button "{button_name}" of front window
        end tell
    end tell
    return "clicked"
    '''
    return run_applescript(script)


def read_ui_element(app_name: str, element_type: str = "static text") -> List[str]:
    """Read UI elements of a given type from front window."""
    script = f'''
    tell application "System Events"
        tell application process "{app_name}"
            return value of every {element_type} of front window
        end tell
    end tell
    '''
    result = run_applescript(script)
    return [x.strip() for x in result.split(",") if x.strip()]


def click_menu_item(app_name: str, menu: str, item: str) -> str:
    """Click a menu item."""
    script = f'''
    tell application "System Events"
        tell application process "{app_name}"
            click menu item "{item}" of menu 1 of menu bar item "{menu}" of menu bar 1
        end tell
    end tell
    return "menu clicked"
    '''
    return run_applescript(script)


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

def toggle_wifi(power: str = "on") -> str:
    """Turn Wi-Fi on or off."""
    return run_shell(["networksetup", "-setairportpower", "en0", power])


def connect_hotspot(name: str, password: str) -> str:
    """Connect to a Wi-Fi network by name and password."""
    return run_shell(["networksetup", "-setairportnetwork", "en0", name, password])


def list_wifi_networks() -> str:
    """List preferred Wi-Fi networks."""
    return run_shell(["networksetup", "-listpreferredwirelessnetworks", "en0"])


def current_ip() -> str:
    """Get current public IP address."""
    return run_shell(["curl", "-s", "https://ipinfo.io/ip"])


# ---------------------------------------------------------------------------
# VoiceOver / Speech
# ---------------------------------------------------------------------------

def speak(text: str) -> str:
    """Speak text using system text-to-speech."""
    return run_shell(["say", text])


def voiceover_status() -> str:
    """Check if VoiceOver is running."""
    script = '''
    tell application "System Events"
        return UI elements enabled
    end tell
    '''
    return run_applescript(script)


def toggle_voiceover() -> str:
    """Toggle VoiceOver on/off."""
    return run_shell(["osascript", "-e", "tell application \"System Events\" to key code 96 using {command down, option down}"])


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

def set_volume(level: int) -> str:
    """Set system volume (0-100)."""
    return run_shell(["osascript", "-e", f"set volume output volume {level}"])


def get_volume() -> str:
    """Get current system volume."""
    return run_shell(["osascript", "-e", "output volume of (get volume settings)"])


def set_brightness(level: int) -> str:
    """Set screen brightness (0-100)."""
    return run_shell(["brightness", str(level / 100)])


def do_not_disturb(enabled: bool) -> str:
    """Toggle Do Not Disturb."""
    state = "on" if enabled else "off"
    return run_shell(["defaults", "write", "com.apple.ncprefs", "dndEnabled", "-bool", "true" if enabled else "false"])


def sleep_display() -> str:
    """Put the display to sleep."""
    return run_shell(["pmset", "displaysleepnow"])


def screenshot(path: str) -> str:
    """Take a screenshot and save to path."""
    return run_shell(["screencapture", path])


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

def reveal_in_finder(path: str) -> str:
    """Open a file or folder in Finder."""
    return run_shell(["open", "-R", path])


def open_folder(path: str) -> str:
    """Open a folder in Finder."""
    return run_shell(["open", path])


def empty_trash() -> str:
    """Empty the trash."""
    return run_shell(["osascript", "-e", "tell application \"Finder\" to empty trash"])


# ---------------------------------------------------------------------------
# Keyboard Shortcuts
# ---------------------------------------------------------------------------

def shortcut(key: str, command: bool = False, option: bool = False, control: bool = False, shift: bool = False) -> str:
    """Send a keyboard shortcut."""
    mods = []
    if command:
        mods.append("command down")
    if option:
        mods.append("option down")
    if control:
        mods.append("control down")
    if shift:
        mods.append("shift down")
    mods_str = " using {" + ", ".join(mods) + "}" if mods else ""
    script = f'''
    tell application "System Events"
        key code {keycode_for_key(key)}{mods_str}
    end tell
    return "shortcut sent"
    '''
    return run_applescript(script)


def paste() -> str:
    """Paste clipboard."""
    return shortcut("v", command=True)


def copy_selection() -> str:
    """Copy current selection."""
    return shortcut("c", command=True)


def select_all() -> str:
    """Select all."""
    return shortcut("a", command=True)


# ---------------------------------------------------------------------------
# Browser Helpers
# ---------------------------------------------------------------------------

def open_url(url: str, browser: str = "Safari") -> str:
    """Open a URL in a browser."""
    script = f'''
    tell application "{browser}"
        open location "{url}"
        activate
    end tell
    return "opened"
    '''
    return run_applescript(script)


def chrome_new_tab(url: str) -> str:
    """Open URL in new Chrome tab."""
    script = f'''
    tell application "Google Chrome"
        activate
        set newTab to make new tab at end of window 1
        set URL of newTab to "{url}"
    end tell
    return "chrome tab opened"
    '''
    return run_applescript(script)


# ---------------------------------------------------------------------------
# Advanced: Accessibility Tree
# ---------------------------------------------------------------------------

def get_ui_tree(app_name: str) -> Dict:
    """Get a simple accessibility tree of the front window."""
    script = f'''
    tell application "System Events"
        tell application process "{app_name}"
            set elements to {{}}
            repeat with e in UI elements of front window
                set end of elements to (role description of e & ": " & (value of e as string))
            end repeat
            return elements as string
        end tell
    end tell
    '''
    result = run_applescript(script)
    return {"app": app_name, "elements": [x.strip() for x in result.split(",") if x.strip()]}
