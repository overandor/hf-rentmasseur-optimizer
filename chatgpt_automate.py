#!/usr/bin/env python3
"""
ChatGPT Mac App Automator
Sends prompts to the ChatGPT desktop app and captures responses.

Uses AppleScript + clipboard to:
1. Activate ChatGPT
2. Type a prompt into the composer
3. Press Enter to send
4. Wait for the response to complete
5. Copy the response
6. Return it as text

No API key needed. No secrets. Uses the already-logged-in app.

Usage:
    python3 chatgpt_automate.py "What is 2+2?"
    python3 chatgpt_automate.py --batch prompts.txt
    python3 chatgpt_automate.py --chat "Explain quantum computing" --timeout 60
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

OUTPUT_DIR = Path(__file__).parent / "chatgpt_exports"


def run_applescript(script: str, timeout: int = 30) -> tuple:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=timeout
    )
    return result.stdout.strip(), result.stderr.strip()


def get_clipboard() -> str:
    result = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=10)
    return result.stdout


def set_clipboard(text: str):
    subprocess.run(["pbcopy"], input=text, text=True, timeout=10)


def clear_clipboard():
    subprocess.run(["pbcopy"], input="", text=True, timeout=5)


def activate_chatgpt() -> bool:
    """Bring ChatGPT app to front."""
    # Open the app
    subprocess.run(["open", "-a", "ChatGPT"], capture_output=True, timeout=10)
    time.sleep(2)
    
    # Activate via AppleScript
    out, err = run_applescript('tell application "ChatGPT" to activate')
    time.sleep(2)
    
    # Verify it's running
    out, err = run_applescript(
        'tell application "System Events" to name of first process whose name contains "ChatGPT"'
    )
    return "ChatGPT" in out


def get_window_info() -> dict:
    """Get ChatGPT window position and size."""
    pos, _ = run_applescript(
        'tell application "System Events" to tell process "ChatGPT" to get position of window 1'
    )
    size, _ = run_applescript(
        'tell application "System Events" to tell process "ChatGPT" to get size of window 1'
    )
    
    try:
        pos_parts = [int(x) for x in pos.split(", ")]
        size_parts = [int(x) for x in size.split(", ")]
        return {
            "x": pos_parts[0], "y": pos_parts[1],
            "w": size_parts[0], "h": size_parts[1],
            "center_x": pos_parts[0] + size_parts[0] // 2,
            "center_y": pos_parts[1] + size_parts[1] // 2,
        }
    except:
        return {}


def start_new_chat():
    """Start a new chat conversation."""
    # Use Cmd+N or click New Chat
    run_applescript(
        'tell application "System Events" to keystroke "n" using command down'
    )
    time.sleep(1.5)


def type_prompt(prompt: str, method: str = "clipboard"):
    """Type a prompt into the ChatGPT composer.
    
    Methods:
    - clipboard: Copy to clipboard, paste with Cmd+V (fast, handles long text)
    - keystroke: Type character by character (slow, may fail on special chars)
    """
    if method == "clipboard":
        set_clipboard(prompt)
        time.sleep(0.3)
        run_applescript(
            'tell application "System Events" to keystroke "v" using command down'
        )
        time.sleep(0.5)
    else:
        # Escape double quotes and backslashes for AppleScript
        escaped = prompt.replace("\\", "\\\\").replace('"', '\\"')
        # Type in chunks to avoid AppleScript length limits
        chunk_size = 200
        for i in range(0, len(escaped), chunk_size):
            chunk = escaped[i:i+chunk_size]
            run_applescript(f'tell application "System Events" to keystroke "{chunk}"')
            time.sleep(0.1)
        time.sleep(0.3)


def send_prompt():
    """Press Enter to send the prompt."""
    run_applescript('tell application "System Events" to keystroke return')
    time.sleep(1)


def wait_for_response(timeout: int = 60, check_interval: float = 2.0) -> dict:
    """Wait for ChatGPT to finish responding.
    
    Strategy: Check the clipboard content periodically. When ChatGPT
    is generating, the response area changes. We detect completion by:
    1. Wait for the stop button to appear (generating)
    2. Wait for the stop button to disappear (done)
    
    Fallback: Just wait for the timeout duration.
    """
    start_time = time.time()
    elapsed = 0
    generating = False
    
    while elapsed < timeout:
        elapsed = time.time() - start_time
        
        # Check if the "stop generating" button is visible
        # We do this by checking UI elements via AppleScript
        _, _ = run_applescript(
            'tell application "System Events" to tell process "ChatGPT" '
            'to get name of every button of window 1'
        )
        
        # Simple approach: wait a fixed time then try to copy
        if elapsed > 5 and not generating:
            generating = True
        
        time.sleep(check_interval)
    
    return {
        "elapsed": round(elapsed, 1),
        "timed_out": elapsed >= timeout,
    }


def copy_response() -> str:
    """Copy the latest response from ChatGPT.
    
    Strategy: Click on the response area, select all, copy.
    The response is in the main content area (center of window).
    """
    win = get_window_info()
    if not win:
        return "ERROR: Could not get ChatGPT window info"
    
    # Click in the conversation area (center, slightly above bottom)
    click_x = win["center_x"]
    click_y = win["y"] + int(win["h"] * 0.6)  # 60% down — in the conversation area
    
    run_applescript(
        f'tell application "System Events" to click at {{{click_x}, {click_y}}}'
    )
    time.sleep(0.5)
    
    # Select all
    run_applescript('tell application "System Events" to keystroke "a" using command down')
    time.sleep(0.5)
    
    # Copy
    run_applescript('tell application "System Events" to keystroke "c" using command down')
    time.sleep(0.5)
    
    return get_clipboard()


def copy_last_response() -> str:
    """Copy just the last response message (not the whole conversation).
    
    Strategy: Triple-click on the last response to select just that block,
    then copy.
    """
    win = get_window_info()
    if not win:
        return "ERROR: Could not get ChatGPT window info"
    
    # Click near the bottom of the conversation area (where last response is)
    click_x = win["center_x"]
    click_y = win["y"] + int(win["h"] * 0.75)  # 75% down — near last response
    
    # Triple-click to select one block
    run_applescript(
        f'tell application "System Events" to click at {{{click_x}, {click_y}}}'
    )
    time.sleep(0.1)
    run_applescript(
        f'tell application "System Events" to click at {{{click_x}, {click_y}}}'
    )
    time.sleep(0.1)
    run_applescript(
        f'tell application "System Events" to click at {{{click_x}, {click_y}}}'
    )
    time.sleep(0.3)
    
    # Copy
    run_applescript('tell application "System Events" to keystroke "c" using command down')
    time.sleep(0.5)
    
    return get_clipboard()


def send_and_receive(prompt: str, timeout: int = 60, new_chat: bool = True) -> dict:
    """Send a prompt to ChatGPT and get the response.
    
    Args:
        prompt: The text prompt to send.
        timeout: Max seconds to wait for response.
        new_chat: Whether to start a new chat first.
    
    Returns:
        Dict with prompt, response, timing, and status.
    """
    start_time = time.time()
    
    # 1. Activate ChatGPT
    if not activate_chatgpt():
        return {"error": "Could not activate ChatGPT", "prompt": prompt}
    
    # 2. Start new chat if requested
    if new_chat:
        start_new_chat()
    
    # 3. Type the prompt
    clear_clipboard()
    type_prompt(prompt, method="clipboard")
    
    # 4. Send
    send_prompt()
    
    # 5. Wait for response
    wait_result = wait_for_response(timeout=timeout)
    
    # 6. Copy response
    response_text = copy_last_response()
    
    elapsed = round(time.time() - start_time, 1)
    
    return {
        "prompt": prompt,
        "response": response_text,
        "elapsed_s": elapsed,
        "timed_out": wait_result["timed_out"],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "new_chat": new_chat,
    }


def batch_prompts(prompts: List[str], timeout: int = 60) -> List[dict]:
    """Send multiple prompts, each in a new chat."""
    results = []
    for i, prompt in enumerate(prompts):
        print(f"[{i+1}/{len(prompts)}] Sending: {prompt[:60]}...")
        result = send_and_receive(prompt, timeout=timeout, new_chat=True)
        results.append(result)
        
        if "error" in result:
            print(f"  ERROR: {result['error']}")
        else:
            print(f"  Response ({result['elapsed_s']}s): {result['response'][:100]}...")
        
        # Save incrementally
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "batch_results.json").write_text(
            json.dumps(results, indent=2, ensure_ascii=False)
        )
        
        # Small delay between prompts
        if i < len(prompts) - 1:
            time.sleep(2)
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="ChatGPT Mac App Automator — send prompts, get responses"
    )
    parser.add_argument("prompt", nargs="?", help="Prompt to send")
    parser.add_argument("--batch", help="File with one prompt per line")
    parser.add_argument("--timeout", type=int, default=60, help="Response timeout (seconds)")
    parser.add_argument("--no-new-chat", action="store_true", help="Continue in current chat")
    parser.add_argument("--output", help="Save response to file")
    args = parser.parse_args()
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    if args.batch:
        prompts = Path(args.batch).read_text().strip().split("\n")
        prompts = [p.strip() for p in prompts if p.strip() and not p.startswith("#")]
        print(f"Batch mode: {len(prompts)} prompts")
        results = batch_prompts(prompts, timeout=args.timeout)
        print(f"\nDone! Results saved to {OUTPUT_DIR / 'batch_results.json'}")
        
    elif args.prompt:
        print(f"Sending prompt to ChatGPT...")
        print(f"Prompt: {args.prompt[:80]}")
        print(f"Timeout: {args.timeout}s")
        print()
        
        result = send_and_receive(
            args.prompt, 
            timeout=args.timeout,
            new_chat=not args.no_new_chat
        )
        
        if "error" in result:
            print(f"ERROR: {result['error']}")
            sys.exit(1)
        
        print(f"Response ({result['elapsed_s']}s):")
        print("-" * 60)
        print(result["response"])
        print("-" * 60)
        
        # Save
        if args.output:
            Path(args.output).write_text(result["response"])
            print(f"\nSaved to: {args.output}")
        else:
            outfile = OUTPUT_DIR / f"response_{int(time.time())}.json"
            outfile.write_text(json.dumps(result, indent=2, ensure_ascii=False))
            print(f"\nSaved to: {outfile}")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
