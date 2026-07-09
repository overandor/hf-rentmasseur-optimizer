"""
MacOS Automation CLI — control your Mac from the terminal.

Usage:
    python3 -m macos_automation.cli list-apps
    python3 -m macos_automation.cli launch "Safari"
    python3 -m macos_automation.cli type "Hello"
    python3 -m macos_automation.cli hotspot "MyHotspot" "password"
    python3 -m macos_automation.cli speak "Hello"
    python3 -m macos_automation.cli volume 50
    python3 -m macos_automation.cli wifi off
    python3 -m macos_automation.cli screenshot /tmp/screen.png
"""

import argparse
import sys

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
    list_wifi_networks,
    current_ip,
    speak,
    set_volume,
    get_volume,
    set_brightness,
    sleep_display,
    screenshot,
    open_url,
    chrome_new_tab,
    paste,
    copy_selection,
    select_all,
    get_ui_tree,
    reveal_in_finder,
    open_folder,
    empty_trash,
)


def main():
    parser = argparse.ArgumentParser(description="MacOS Automation CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-apps", help="List running applications")
    sub.add_parser("ip", help="Show current public IP")
    sub.add_parser("wifi-nets", help="List preferred Wi-Fi networks")
    sub.add_parser("volume", help="Get current volume")
    sub.add_parser("ui-tree", help="Get UI tree of front app")

    p = sub.add_parser("launch", help="Launch an app")
    p.add_argument("app")

    p = sub.add_parser("quit", help="Quit an app")
    p.add_argument("app")

    p = sub.add_parser("focus", help="Focus an app")
    p.add_argument("app")

    p = sub.add_parser("type", help="Type text")
    p.add_argument("text")

    p = sub.add_parser("key", help="Press a key")
    p.add_argument("key")

    p = sub.add_parser("click", help="Click a button")
    p.add_argument("app")
    p.add_argument("button")

    p = sub.add_parser("read-ui", help="Read UI elements")
    p.add_argument("app")
    p.add_argument("--type", default="static text")

    p = sub.add_parser("hotspot", help="Connect to a Wi-Fi hotspot")
    p.add_argument("name")
    p.add_argument("password")

    p = sub.add_parser("wifi", help="Turn Wi-Fi on/off")
    p.add_argument("state", choices=["on", "off"])

    p = sub.add_parser("speak", help="Speak text")
    p.add_argument("text")

    p = sub.add_parser("set-volume", help="Set volume 0-100")
    p.add_argument("level", type=int)

    p = sub.add_parser("brightness", help="Set brightness 0-100")
    p.add_argument("level", type=int)

    p = sub.add_parser("sleep", help="Put display to sleep")

    p = sub.add_parser("screenshot", help="Take screenshot")
    p.add_argument("path")

    p = sub.add_parser("open", help="Open a URL")
    p.add_argument("url")
    p.add_argument("--browser", default="Safari")

    p = sub.add_parser("chrome-tab", help="Open URL in Chrome tab")
    p.add_argument("url")

    p = sub.add_parser("paste", help="Paste clipboard")
    p = sub.add_parser("copy", help="Copy selection")
    p = sub.add_parser("select-all", help="Select all")

    p = sub.add_parser("reveal", help="Reveal file in Finder")
    p.add_argument("path")

    p = sub.add_parser("open-folder", help="Open folder in Finder")
    p.add_argument("path")

    p = sub.add_parser("empty-trash", help="Empty trash")

    args = parser.parse_args()

    cmd = args.command
    if cmd == "list-apps":
        print("\n".join(list_running_apps()))
    elif cmd == "ip":
        print(current_ip())
    elif cmd == "wifi-nets":
        print(list_wifi_networks())
    elif cmd == "volume":
        print(get_volume())
    elif cmd == "launch":
        print(launch_app(args.app))
    elif cmd == "quit":
        print(quit_app(args.app))
    elif cmd == "focus":
        print(focus_app(args.app))
    elif cmd == "type":
        print(type_text(args.text))
    elif cmd == "key":
        print(press_key(args.key))
    elif cmd == "click":
        print(click_button(args.app, args.button))
    elif cmd == "read-ui":
        print("\n".join(read_ui_element(args.app, args.type)))
    elif cmd == "hotspot":
        print(connect_hotspot(args.name, args.password))
    elif cmd == "wifi":
        print(toggle_wifi(args.state))
    elif cmd == "speak":
        print(speak(args.text))
    elif cmd == "set-volume":
        print(set_volume(args.level))
    elif cmd == "brightness":
        print(set_brightness(args.level))
    elif cmd == "sleep":
        print(sleep_display())
    elif cmd == "screenshot":
        print(screenshot(args.path))
    elif cmd == "open":
        print(open_url(args.url, args.browser))
    elif cmd == "chrome-tab":
        print(chrome_new_tab(args.url))
    elif cmd == "paste":
        print(paste())
    elif cmd == "copy":
        print(copy_selection())
    elif cmd == "select-all":
        print(select_all())
    elif cmd == "ui-tree":
        import json
        print(json.dumps(get_ui_tree("System Events"), indent=2))
    elif cmd == "reveal":
        print(reveal_in_finder(args.path))
    elif cmd == "open-folder":
        print(open_folder(args.path))
    elif cmd == "empty-trash":
        print(empty_trash())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
