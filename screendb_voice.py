#!/usr/bin/env python3
"""
ScreenDB Voice — Narrate screen state with macOS 'say' command.
Reads the live screen as text, then speaks it.
"""
import sys, os, time, subprocess, json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from screendb import capture_accessibility, accessibility_summary, get_receipts, verify_receipts
from mac_runtime import capture_windows, capture_processes, query as mr_query


def speak(text: str, voice: str = "Samantha", rate: int = 180):
    """Speak text via macOS say command."""
    subprocess.run(["say", "-v", voice, "-r", str(rate), text],
                   timeout=60, capture_output=True)


def screen_state_as_speech() -> str:
    """Convert current screen state into a natural speech description."""
    windows = capture_windows()
    ax = capture_accessibility()

    parts = []
    parts.append(f"Screen state at {datetime.now().strftime('%I:%M %p')}.")

    # Windows
    visible = [w for w in windows if not w.get("minimized")]
    focused = [w for w in windows if w.get("focused")]

    if focused:
        parts.append(f"Active application: {focused[0]['app']}. Window title: {focused[0]['title']}.")
    else:
        parts.append("No focused window detected.")

    parts.append(f"{len(visible)} visible windows: ")
    for w in visible:
        mark = "currently focused" if w.get("focused") else "in background"
        parts.append(f"{w['app']}, {mark}.")

    # Accessibility
    elements = ax.get("elements", [])
    if elements:
        interactive = [e for e in elements if e.get("enabled") and e.get("role") in
                       ("AXButton", "AXTextField", "AXPopUpButton", "AXComboBox", "AXMenuButton")]
        if interactive:
            parts.append(f"Interactive elements in frontmost window: {len(interactive)}.")
            for el in interactive[:5]:
                role = el["role"].replace("AX", "").lower()
                title = el.get("title", "") or el.get("description", "") or "untitled"
                parts.append(f"{role} named {title}.")
        else:
            parts.append("No interactive elements detected in frontmost window.")

    # Processes
    procs = capture_processes()
    top = sorted(procs, key=lambda p: p.get("cpu", 0), reverse=True)[:3]
    parts.append(f"Top processes by CPU: ")
    for p in top:
        parts.append(f"{p['name']} at {p.get('cpu', 0):.0f} percent CPU.")

    # Receipts
    receipts = get_receipts(5)
    if receipts:
        ok = sum(1 for r in receipts if r["result"]["success"])
        parts.append(f"Receipt ledger: {ok} successful actions out of {len(receipts)} recent.")

    return " ".join(parts)


def screen_state_as_compact_speech() -> str:
    """Shorter version for frequent narration."""
    windows = capture_windows()
    ax = capture_accessibility()
    focused = [w for w in windows if w.get("focused")]

    parts = []
    if focused:
        parts.append(f"You are in {focused[0]['app']}, looking at {focused[0]['title']}.")

    visible = [w for w in windows if not w.get("minimized")]
    bg = [w for w in visible if not w.get("focused")]
    if bg:
        parts.append(f"Background: {', '.join(w['app'] for w in bg[:4])}.")

    elements = ax.get("elements", [])
    buttons = [e for e in elements if e.get("role") == "AXButton" and e.get("enabled")]
    if buttons:
        parts.append(f"{len(buttons)} buttons available.")

    return " ".join(parts)


def cli():
    import argparse
    p = argparse.ArgumentParser(description="ScreenDB Voice — Narrate screen state")
    sub = p.add_subparsers(dest="cmd")

    p_speak = sub.add_parser("speak", help="Speak current screen state")
    p_speak.add_argument("--voice", default="Samantha", help="macOS voice name")
    p_speak.add_argument("--rate", type=int, default=180, help="Speech rate (words/min)")
    p_speak.add_argument("--compact", action="store_true", help="Shorter narration")

    sub.add_parser("text", help="Print speech text without speaking")

    p_loop = sub.add_parser("loop", help="Continuously narrate screen state")
    p_loop.add_argument("--interval", type=float, default=10.0, help="Seconds between narrations")
    p_loop.add_argument("--voice", default="Samantha")
    p_loop.add_argument("--rate", type=int, default=180)
    p_loop.add_argument("--compact", action="store_true")

    p_voices = sub.add_parser("voices", help="List available macOS voices")

    args = p.parse_args()

    if args.cmd == "speak":
        text = screen_state_as_compact_speech() if args.compact else screen_state_as_speech()
        print(f"\n  {text}\n")
        speak(text, args.voice, args.rate)

    elif args.cmd == "text":
        text = screen_state_as_speech()
        print(f"\n  {text}\n")

    elif args.cmd == "loop":
        print("ScreenDB Voice Loop — press Ctrl+C to stop\n")
        try:
            while True:
                text = screen_state_as_compact_speech() if args.compact else screen_state_as_speech()
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"  [{timestamp}] {text[:120]}...")
                speak(text, args.voice, args.rate)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n\nStopped.")

    elif args.cmd == "voices":
        r = subprocess.run(["say", "-v", "?"], capture_output=True, text=True)
        for line in r.stdout.strip().split("\n"):
            print(f"  {line}")

    else:
        p.print_help()


if __name__ == "__main__":
    cli()
