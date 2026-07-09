#!/usr/bin/env python3
"""
ChatGPTPoller — 24/7 daemon that bridges the ChatGPT Mac app to the Agent Bridge server.

Two loops:
1. Outbound: Polls bridge for tasks (to_chatgpt) → types into ChatGPT → captures response → posts back
2. Inbound: Monitors ChatGPT conversation for /windsurf commands → posts as tasks (to_windsurf) → polls for response → types it back

The poller runs as a background process. It uses AppleScript + clipboard for ChatGPT automation
and HTTP to communicate with the bridge server.

Usage:
    python3 -m agent_bridge.chatgpt_poller                    # Run poller daemon
    python3 -m agent_bridge.chatgpt_poller --once             # Process one task then exit
    python3 -m agent_bridge.chatgpt_poller --interval 5       # Poll every 5 seconds
    python3 -m agent_bridge.chatgpt_poller --bridge-url http://127.0.0.1:8766
"""

import argparse
import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import urllib.request
import urllib.error

BRIDGE_URL = "http://127.0.0.1:8766"
POLLER_ID = f"chatgpt_poller_{os.getpid()}"
LAST_RESPONSE_HASH_FILE = Path(__file__).parent / "data" / ".last_response_hash"

LOG_DIR = Path(__file__).parent / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "chatgpt_poller.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("chatgpt_poller")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _api(method: str, path: str, data: Dict = None, base_url: str = BRIDGE_URL) -> Dict[str, Any]:
    """Make HTTP request to bridge server."""
    url = f"{base_url}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


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
    subprocess.run(["open", "-a", "ChatGPT"], capture_output=True, timeout=10)
    time.sleep(2)
    run_applescript('tell application "ChatGPT" to activate')
    time.sleep(2)
    out, _ = run_applescript(
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
    except Exception:
        return {}


def start_new_chat():
    """Start a new chat conversation."""
    run_applescript('tell application "System Events" to keystroke "n" using command down')
    time.sleep(1.5)


def type_prompt(prompt: str):
    """Type a prompt into the ChatGPT composer via clipboard."""
    set_clipboard(prompt)
    time.sleep(0.3)
    run_applescript('tell application "System Events" to keystroke "v" using command down')
    time.sleep(0.5)


def send_prompt():
    """Press Enter to send."""
    run_applescript('tell application "System Events" to keystroke return')
    time.sleep(1)


def capture_response_screenshot() -> Dict[str, str]:
    """Capture ChatGPT response via screenshot + OCR."""
    win = get_window_info()
    if not win:
        return {"text": "ERROR: Could not get window info", "screenshot": ""}

    shot_path = f"/tmp/chatgpt_bridge_{int(time.time())}.png"
    subprocess.run(
        ["screencapture", "-R", f"{win['x']},{win['y']},{win['w']},{win['h']}", shot_path],
        capture_output=True, timeout=10,
    )
    time.sleep(0.5)

    try:
        from PIL import Image
        import pytesseract
        img = Image.open(shot_path)
        w, h = img.size
        # Crop to conversation area (right of sidebar, above composer)
        conv = img.crop((280, 50, w, h - 120))
        text = pytesseract.image_to_string(conv)
        return {"text": text.strip(), "screenshot": shot_path}
    except ImportError:
        return {"text": "ERROR: pytesseract/PIL not installed — cannot OCR", "screenshot": shot_path}
    except Exception as e:
        return {"text": f"ERROR: {e}", "screenshot": shot_path}


def capture_response_clipboard() -> str:
    """Try to capture response via Cmd+A, Cmd+C (may not work with WebKit views)."""
    win = get_window_info()
    if not win:
        return "ERROR: Could not get window info"

    # Click in conversation area
    click_x = win["center_x"]
    click_y = win["y"] + int(win["h"] * 0.6)
    run_applescript(f'tell application "System Events" to click at {{{click_x}, {click_y}}}')
    time.sleep(0.3)

    # Select all and copy
    run_applescript('tell application "System Events" to keystroke "a" using command down')
    time.sleep(0.3)
    run_applescript('tell application "System Events" to keystroke "c" using command down')
    time.sleep(0.5)

    return get_clipboard()


def send_to_chatgpt(prompt: str, timeout: int = 60, new_chat: bool = True) -> Dict[str, Any]:
    """Send a prompt to ChatGPT and capture the response."""
    start = time.time()

    if not activate_chatgpt():
        return {"error": "Could not activate ChatGPT", "prompt": prompt}

    if new_chat:
        start_new_chat()

    clear_clipboard()
    type_prompt(prompt)
    send_prompt()

    # Wait for response
    time.sleep(min(timeout, 30))

    # Try clipboard first, fall back to OCR
    response_text = capture_response_clipboard()
    screenshot_path = ""

    if not response_text or response_text == get_clipboard() == prompt:
        # Clipboard didn't work, use OCR
        ocr_result = capture_response_screenshot()
        response_text = ocr_result["text"]
        screenshot_path = ocr_result["screenshot"]

    elapsed = round(time.time() - start, 1)

    return {
        "prompt": prompt,
        "response": response_text,
        "elapsed_s": elapsed,
        "timestamp": now_iso(),
        "new_chat": new_chat,
        "screenshot": screenshot_path,
        "method": "clipboard" if not screenshot_path else "ocr",
    }


def detect_windsurf_command(text: str) -> Optional[Dict[str, str]]:
    """Detect /windsurf commands in ChatGPT's response or user input.

    Patterns:
        /windsurf <request>
        /wf <request>
        /code <request>  (alias for code execution request)
    """
    patterns = [
        r'/windsurf\s+(.+)',
        r'/wf\s+(.+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return {"command": "windsurf", "request": match.group(1).strip()}

    # Code execution pattern
    code_match = re.search(r'/code\s+(.+)', text, re.IGNORECASE | re.DOTALL)
    if code_match:
        return {"command": "execute", "request": code_match.group(1).strip()}

    return None


def process_outbound_task(bridge_url: str, task: Dict[str, Any]) -> bool:
    """Process a task meant for ChatGPT: send prompt, capture response, post back."""
    task_id = task["id"]
    prompt = task["prompt"]
    context = task.get("context", "")

    full_prompt = prompt
    if context:
        full_prompt = f"Context: {context}\n\nRequest: {prompt}"

    print(f"[OUTBOUND] Processing task {task_id}: {prompt[:80]}...", flush=True)

    result = send_to_chatgpt(full_prompt, timeout=60, new_chat=True)

    if "error" in result:
        print(f"[OUTBOUND] ERROR: {result['error']}", flush=True)
        _api("POST", f"/tasks/{task_id}/fail", base_url=bridge_url)
        _api("POST", "/responses", {
            "task_id": task_id,
            "sender": "chatgpt_poller",
            "content": json.dumps(result),
            "metadata": {"error": result["error"]},
        }, base_url=bridge_url)
        return False

    response_text = result.get("response", "")

    # Check if ChatGPT's response contains a /windsurf command (inbound trigger)
    windsurf_cmd = detect_windsurf_command(response_text)
    if windsurf_cmd:
        print(f"[INBOUND] Detected /windsurf command: {windsurf_cmd['request'][:80]}...", flush=True)
        # Post as a new task for Windsurf
        _api("POST", "/tasks", {
            "direction": "to_windsurf",
            "sender": "chatgpt",
            "prompt": windsurf_cmd["request"],
            "context": f"Triggered from ChatGPT response to task {task_id}",
            "priority": 3,
        }, base_url=bridge_url)

    # Post response back to bridge
    _api("POST", "/responses", {
        "task_id": task_id,
        "sender": "chatgpt",
        "content": response_text,
        "metadata": {
            "elapsed_s": result.get("elapsed_s"),
            "method": result.get("method"),
            "screenshot": result.get("screenshot", ""),
            "timestamp": result.get("timestamp"),
        },
    }, base_url=bridge_url)

    # Mark task complete
    _api("POST", f"/tasks/{task_id}/complete", base_url=bridge_url)

    print(f"[OUTBOUND] Task {task_id} complete. Response: {response_text[:100]}...", flush=True)
    return True


def process_inbound_responses(bridge_url: str):
    """Check for responses to tasks ChatGPT posted to Windsurf, and type them back into ChatGPT."""
    unread = _api("GET", "/responses/unread?sender=windsurf", base_url=bridge_url)
    responses = unread.get("responses", [])

    for resp in responses:
        content = resp.get("content", "")
        task_id = resp.get("task_id", "")
        resp_id = resp.get("id", "")

        logger.info(f"[INBOUND] Typing Windsurf response back to ChatGPT: {content[:80]}...")

        # Type the response back into the current ChatGPT chat
        if activate_chatgpt():
            set_clipboard(f"[Windsurf Response]\n{content}")
            time.sleep(0.3)
            run_applescript('tell application "System Events" to keystroke "v" using command down')
            time.sleep(0.5)
            run_applescript('tell application "System Events" to keystroke return')
            time.sleep(1)

        # Mark response as read so we don't type it again
        _api("POST", f"/responses/{resp_id}/read", base_url=bridge_url)
        logger.info(f"[INBOUND] Response {resp_id} marked as read")


def poll_loop(bridge_url: str, interval: float = 3.0, once: bool = False, max_retries: int = 5):
    """Main poll loop — runs 24/7 with auto-restart and exponential backoff."""
    running = True
    consecutive_errors = 0
    tasks_processed = 0

    def handle_signal(signum, frame):
        nonlocal running
        running = False
        logger.info(f"Received signal {signum}, shutting down...")

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    logger.info(f"Starting ChatGPT poller (PID {os.getpid()})")
    logger.info(f"Bridge: {bridge_url}")
    logger.info(f"Interval: {interval}s")
    logger.info(f"Mode: {'once' if once else 'continuous'}")
    logger.info(f"Log file: {LOG_DIR / 'chatgpt_poller.log'}")

    # Health check with retry
    for attempt in range(max_retries):
        health = _api("GET", "/health", base_url=bridge_url)
        if "error" not in health:
            logger.info(f"Bridge server healthy: {health.get('status', 'unknown')}")
            break
        logger.warning(f"Cannot reach bridge (attempt {attempt+1}/{max_retries}): {health.get('error', '')}")
        if attempt < max_retries - 1:
            time.sleep(5 * (attempt + 1))
    else:
        logger.error(f"Cannot reach bridge server at {bridge_url} after {max_retries} attempts")
        logger.error(f"Start it with: python3 -m agent_bridge.bridge_server --port 8766")
        return

    while running:
        try:
            # 1. Check for outbound tasks (to_chatgpt)
            claim_result = _api("POST", "/tasks/claim", {
                "direction": "to_chatgpt",
                "claimer": POLLER_ID,
            }, base_url=bridge_url)

            task = claim_result.get("task")
            if task:
                logger.info(f"Claimed task {task['id']}: {task['prompt'][:80]}")
                try:
                    success = process_outbound_task(bridge_url, task)
                    if success:
                        tasks_processed += 1
                        consecutive_errors = 0
                    else:
                        consecutive_errors += 1
                except Exception as e:
                    logger.error(f"Failed to process task {task['id']}: {e}")
                    logger.debug(traceback.format_exc())
                    _api("POST", f"/tasks/{task['id']}/fail", base_url=bridge_url)
                    consecutive_errors += 1

            # 2. Check for inbound responses (from Windsurf to ChatGPT)
            try:
                process_inbound_responses(bridge_url)
            except Exception as e:
                logger.warning(f"Inbound processing error: {e}")

            # 3. Health check every 100 iterations
            if tasks_processed > 0 and tasks_processed % 100 == 0:
                health = _api("GET", "/health", base_url=bridge_url)
                if "error" in health:
                    logger.warning(f"Bridge health check failed: {health.get('error')}")
                    consecutive_errors += 1
                else:
                    logger.info(f"Health check OK. Tasks processed: {tasks_processed}")

            # 4. Geometric backoff on consecutive errors
            if consecutive_errors >= max_retries:
                backoff = min(30 * (2 ** (consecutive_errors - max_retries)), 300)
                logger.error(f"{consecutive_errors} consecutive errors, backing off {backoff}s")
                time.sleep(backoff)
                consecutive_errors = max_retries  # cap to avoid overflow

            if once:
                break

            time.sleep(interval)

        except Exception as e:
            logger.error(f"Error in poll loop: {e}")
            logger.debug(traceback.format_exc())
            consecutive_errors += 1
            backoff = min(interval * (2 ** consecutive_errors), 60)
            time.sleep(backoff)

    logger.info(f"Stopped. Total tasks processed: {tasks_processed}")


def main():
    parser = argparse.ArgumentParser(description="ChatGPT Poller — 24/7 bridge to Agent Bridge server")
    parser.add_argument("--bridge-url", default=BRIDGE_URL, help="Bridge server URL")
    parser.add_argument("--interval", type=float, default=3.0, help="Poll interval in seconds")
    parser.add_argument("--once", action="store_true", help="Process one task then exit")
    parser.add_argument("--test-connection", action="store_true", help="Test connection to bridge and exit")
    parser.add_argument("--max-retries", type=int, default=5, help="Max consecutive errors before backoff")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.test_connection:
        health = _api("GET", "/health", base_url=args.bridge_url)
        if "error" in health:
            print(f"FAIL: Cannot reach bridge at {args.bridge_url}: {health['error']}")
            sys.exit(1)
        print(f"OK: Bridge healthy at {args.bridge_url}")
        print(json.dumps(health, indent=2))
        return

    poll_loop(args.bridge_url, args.interval, args.once, args.max_retries)


if __name__ == "__main__":
    main()
