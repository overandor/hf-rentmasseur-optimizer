#!/usr/bin/env python3
"""
Extract ChatGPT chats from the native Mac app using UI automation.
The app is logged in, so we use keyboard shortcuts and clipboard to extract data.
"""

import time
import json
import re
import subprocess
import pyautogui
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "chatgpt_exports"


def run_applescript(script, timeout=30):
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=timeout
    )
    return result.stdout.strip(), result.stderr.strip()


def get_clipboard():
    result = subprocess.run(
        ["pbpaste"], capture_output=True, text=True, timeout=10
    )
    return result.stdout


def set_clipboard(text):
    subprocess.run(["pbcopy"], input=text, text=True, timeout=10)


def activate_chatgpt():
    """Bring ChatGPT app to front."""
    subprocess.run(["open", "-a", "ChatGPT"], capture_output=True, timeout=10)
    time.sleep(3)
    # Also activate via AppleScript
    run_applescript('tell application "ChatGPT" to activate')
    time.sleep(2)


def get_sidebar_text():
    """Try to get the sidebar text by clicking on it and selecting all."""
    # Take screenshot first to see layout
    img = pyautogui.screenshot()
    img.save(str(OUTPUT_DIR / "app_before_extract.png"))
    
    # Click on the sidebar area (left side of the window)
    # The ChatGPT app window has sidebar on the left
    # Let's click at approximately 200px from left, 400px from top
    screen_w, screen_h = pyautogui.size()
    
    # First, find the ChatGPT window position
    pos, _ = run_applescript(
        'tell application "System Events" to tell process "ChatGPT" to get position of window "ChatGPT"'
    )
    size, _ = run_applescript(
        'tell application "System Events" to tell process "ChatGPT" to get size of window "ChatGPT"'
    )
    
    print(f"Window position: {pos}")
    print(f"Window size: {size}")
    
    if pos and size:
        pos_parts = [int(x) for x in pos.split(",")]
        size_parts = [int(x) for x in size.split(",")]
        win_x, win_y = pos_parts[0], pos_parts[1]
        win_w, win_h = size_parts[0], size_parts[1]
        
        # Click on sidebar (left ~250px of window)
        sidebar_x = win_x + 150
        sidebar_y = win_y + 200
        print(f"Clicking sidebar at ({sidebar_x}, {sidebar_y})")
        pyautogui.click(sidebar_x, sidebar_y)
        time.sleep(1)
        
        # Try Cmd+A to select all in sidebar
        pyautogui.hotkey('cmd', 'a')
        time.sleep(1)
        
        # Copy
        pyautogui.hotkey('cmd', 'c')
        time.sleep(1)
        
        clipboard = get_clipboard()
        print(f"Clipboard length: {len(clipboard)}")
        print(f"Clipboard preview: {clipboard[:500]}")
        
        return clipboard
    
    return None


def search_and_extract():
    """Use the search feature to find all conversations."""
    # Click search in sidebar
    # Use Cmd+F or click search
    pyautogui.hotkey('cmd', 'f')
    time.sleep(2)
    
    # Type a space to match all conversations
    pyautogui.typewrite(' ')
    time.sleep(3)
    
    # Take screenshot to see search results
    img = pyautogui.screenshot()
    img.save(str(OUTPUT_DIR / "app_search_results.png"))
    
    # Select all and copy
    pyautogui.hotkey('cmd', 'a')
    time.sleep(1)
    pyautogui.hotkey('cmd', 'c')
    time.sleep(1)
    
    clipboard = get_clipboard()
    print(f"Search results clipboard: {len(clipboard)} chars")
    if clipboard:
        print(f"Preview: {clipboard[:500]}")
    
    return clipboard


def extract_via_menu():
    """Try to use ChatGPT app menu items to export."""
    # Check available menus
    menus, _ = run_applescript(
        'tell application "System Events" to tell process "ChatGPT" to return name of every menu bar item of menu bar 1'
    )
    print(f"Menus: {menus}")
    
    # Check each menu for export options
    for menu_name in menus.split(", "):
        menu_name = menu_name.strip()
        if not menu_name:
            continue
        items, err = run_applescript(
            f'tell application "System Events" to tell process "ChatGPT" to return name of every menu item of menu "{menu_name}" of menu bar item "{menu_name}" of menu bar 1'
        )
        if items and not err:
            print(f"  {menu_name}: {items[:200]}")
            if "export" in items.lower() or "save" in items.lower():
                print(f"  FOUND EXPORT/SAVE in {menu_name}!")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("ChatGPT Mac App Extractor")
    print("=" * 60)
    
    activate_chatgpt()
    
    # First, check menus for export options
    print("\nChecking menus...")
    extract_via_menu()
    
    # Try to get sidebar text
    print("\nGetting sidebar text...")
    sidebar = get_sidebar_text()
    
    if sidebar:
        (OUTPUT_DIR / "app_sidebar_text.txt").write_text(sidebar)
        
        # Parse conversation titles from sidebar text
        lines = sidebar.split('\n')
        chats = []
        for line in lines:
            line = line.strip()
            if line and line not in ("New chat", "Search chats", "ChatGPT", ""):
                chats.append({"title": line})
        
        print(f"\nFound {len(chats)} potential chat titles")
        for c in chats[:10]:
            print(f"  {c['title']}")
        
        (OUTPUT_DIR / "app_chat_titles.json").write_text(
            json.dumps(chats, indent=2, ensure_ascii=False)
        )
    
    # Try search
    print("\nTrying search...")
    search_results = search_and_extract()
    
    if search_results:
        (OUTPUT_DIR / "app_search_results.txt").write_text(search_results)
    
    print("\nDone!")


if __name__ == "__main__":
    main()
