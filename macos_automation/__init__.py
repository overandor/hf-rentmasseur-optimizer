"""MacOS Automation Library — AppleScript + Swift + Python bridge."""

from .python_bridge import (
    list_running_apps,
    launch_app,
    quit_app,
    focus_app,
    type_text,
    press_key,
    click_button,
    read_ui_element,
    connect_hotspot,
    toggle_wifi,
    speak,
    set_volume,
    get_volume,
)

__all__ = [
    "list_running_apps",
    "launch_app",
    "quit_app",
    "focus_app",
    "type_text",
    "press_key",
    "click_button",
    "read_ui_element",
    "connect_hotspot",
    "toggle_wifi",
    "speak",
    "set_volume",
    "get_volume",
]
