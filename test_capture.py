#!/usr/bin/env python3
"""Quick test: capture ChatGPT response via pyautogui triple-click."""

import subprocess
import time
import pyautogui

def ascript(s):
    r = subprocess.run(["osascript", "-e", s], capture_output=True, text=True, timeout=30)
    return r.stdout.strip()

# Activate ChatGPT
subprocess.run(["open", "-a", "ChatGPT"], capture_output=True)
time.sleep(2)
ascript('tell application "ChatGPT" to activate')
time.sleep(1)

# Get window info
pos = ascript('tell application "System Events" to tell process "ChatGPT" to get position of window 1')
size = ascript('tell application "System Events" to tell process "ChatGPT" to get size of window 1')
print(f"Window pos: {pos}, size: {size}")

pos_parts = [int(x) for x in pos.split(", ")]
size_parts = [int(x) for x in size.split(", ")]

# Click near bottom of conversation area (above composer)
click_x = pos_parts[0] + size_parts[0] // 2
click_y = pos_parts[1] + int(size_parts[1] * 0.85)
print(f"Triple-clicking at ({click_x}, {click_y})")

pyautogui.click(click_x, click_y)
time.sleep(0.2)
pyautogui.click(click_x, click_y)
time.sleep(0.2)
pyautogui.click(click_x, click_y)
time.sleep(0.5)

# Copy
pyautogui.hotkey("cmd", "c")
time.sleep(0.5)

# Get clipboard
r = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=10)
print(f"Clipboard length: {len(r.stdout)}")
print(f"Clipboard content: {r.stdout[:500]}")
