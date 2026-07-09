#!/usr/bin/env python3
"""Scroll down in ChatGPT and capture screenshots to read full response."""

import subprocess
import time
from PIL import Image
import pytesseract

def ascript(s):
    r = subprocess.run(["osascript", "-e", s], capture_output=True, text=True, timeout=30)
    return r.stdout.strip()

# Activate ChatGPT
subprocess.run(["open", "-a", "ChatGPT"], capture_output=True)
time.sleep(2)
ascript('tell application "ChatGPT" to activate')
time.sleep(1)

# Get window position
pos = ascript('tell application "System Events" to tell process "ChatGPT" to get position of window 1')
size = ascript('tell application "System Events" to tell process "ChatGPT" to get size of window 1')
pos_parts = [int(x) for x in pos.split(", ")]
size_parts = [int(x) for x in size.split(", ")]

print(f"Window: {pos_parts} {size_parts}")

all_text = ""

for i in range(5):
    # Screenshot
    shot = f"/tmp/chatgpt_scroll_{i}.png"
    subprocess.run(["screencapture", "-R",
                    f"{pos_parts[0]},{pos_parts[1]},{size_parts[0]},{size_parts[1]}",
                    shot], capture_output=True, timeout=10)
    time.sleep(0.3)
    
    # OCR
    img = Image.open(shot)
    w, h = img.size
    conv = img.crop((280, 50, w, h - 120))
    text = pytesseract.image_to_string(conv)
    
    print(f"\n=== Scroll {i} ({len(text)} chars) ===")
    print(text[:500])
    all_text += text + "\n"
    
    # Scroll down with Page Down
    ascript('tell application "System Events" to keystroke (ASCII character 12)')
    # Or use arrow down multiple times
    for _ in range(10):
        ascript('tell application "System Events" to keystroke (ASCII character 31)')
    time.sleep(1)

# Save all text
with open("/tmp/chatgpt_full_response.txt", "w") as f:
    f.write(all_text)

print(f"\n\nTotal text: {len(all_text)} chars")
print(f"Saved to /tmp/chatgpt_full_response.txt")
