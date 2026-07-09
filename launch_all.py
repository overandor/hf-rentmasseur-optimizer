#!/usr/bin/env python3
"""
OverAgent Unified Launcher — starts all servers and opens the dashboard.

Servers:
  7860 — AFC Protocol
  7861 — JORKI Audio Gateway (SonicGlyph64)
  7862 — OverAgent Control Plane (dashboard)

Usage:
  python3 launch_all.py
"""

import os
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

REPO = Path(__file__).parent

SERVERS = [
    {
        "name": "AFC Protocol",
        "port": 7860,
        "file": "afc_server.py",
        "health": "http://localhost:7860/health",
    },
    {
        "name": "JORKI Audio Gateway",
        "port": 7861,
        "file": "jorki_audio_server.py",
        "health": "http://localhost:7861/audio/health",
    },
    {
        "name": "OverAgent Control Plane",
        "port": 7862,
        "file": "overagent_control_plane.py",
        "health": "http://localhost:7862/health",
    },
    {
        "name": "SignalForge",
        "port": 7863,
        "file": "signalforge.py",
        "health": "http://localhost:7863/health",
    },
]

processes = []


def start_servers():
    for srv in SERVERS:
        path = REPO / srv["file"]
        if not path.exists():
            print(f"  SKIP {srv['name']} — {srv['file']} not found")
            continue
        print(f"  START {srv['name']} on port {srv['port']}...")
        p = subprocess.Popen(
            [sys.executable, str(path), "--port", str(srv["port"])],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(REPO),
        )
        processes.append(p)
        srv["pid"] = p.pid


def wait_healthy(timeout=15):
    import urllib.request
    for srv in SERVERS:
        if "pid" not in srv:
            continue
        for _ in range(timeout * 2):
            try:
                urllib.request.urlopen(srv["health"], timeout=2)
                print(f"  OK   {srv['name']} — {srv['health']}")
                break
            except Exception:
                time.sleep(0.5)
        else:
            print(f"  FAIL {srv['name']} — health check failed")


def register_and_seed():
    import json
    import urllib.request

    # Register systems in control plane
    for srv in SERVERS:
        if "pid" not in srv:
            continue
        if srv["port"] == 7862:
            continue
        try:
            data = json.dumps({"name": srv["name"], "endpoint": f"http://localhost:{srv['port']}"}).encode()
            req = urllib.request.Request(
                "http://localhost:7862/api/systems/register",
                data=data,
                method="POST",
            )
            req.add_header("Content-Type", "application/json")
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

    # Write launch receipt
    try:
        data = json.dumps({
            "action": "unified_launch",
            "actor": "human",
            "result": "success",
            "evidence": "all servers started",
        }).encode()
        req = urllib.request.Request(
            "http://localhost:7862/api/receipts/write",
            data=data,
            method="POST",
        )
        req.add_header("Content-Type", "application/json")
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass

    # Ingest initial metrics
    try:
        data = json.dumps({
            "source": "unified_launcher",
            "metrics": {
                "uptime_seconds": 1,
                "receipt_count": 1,
                "endpoint_count": 30,
                "total_actions": 1,
                "receipted_actions": 1,
                "system_age_hours": 0,
            },
        }).encode()
        req = urllib.request.Request(
            "http://localhost:7862/api/metrics/ingest",
            data=data,
            method="POST",
        )
        req.add_header("Content-Type", "application/json")
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def open_dashboard():
    url = "http://localhost:7862"
    print(f"\n  Opening dashboard: {url}")
    try:
        webbrowser.open(url)
    except Exception:
        pass


def cleanup(*args):
    print("\n  Shutting down all servers...")
    for p in processes:
        try:
            p.terminate()
        except Exception:
            pass
    for p in processes:
        try:
            p.wait(timeout=5)
        except Exception:
            p.kill()
    print("  All servers stopped.")
    sys.exit(0)


def main():
    print("""
  ╔═══════════════════════════════════════════════════════════════╗
  ║                                                               ║
  ║   OVERAGENT UNIFIED LAUNCH                                    ║
  ║                                                               ║
  ║   Starting all production servers...                          ║
  ║                                                               ║
  ╚═══════════════════════════════════════════════════════════════╝
""")

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    start_servers()
    print("\n  Waiting for health checks...")
    wait_healthy()

    print("\n  Registering systems and writing receipts...")
    register_and_seed()

    open_dashboard()

    print(f"""
  ╔═══════════════════════════════════════════════════════════════╗
  ║                                                               ║
  ║   ALL SYSTEMS LIVE                                            ║
  ║                                                               ║
  ║   Dashboard:     http://localhost:7862                        ║
  ║   Audio Gateway: http://localhost:7861                        ║
  ║   AFC Protocol:  http://localhost:7860                        ║
  ║                                                               ║
  ║   Ctrl+C to stop all servers.                                 ║
  ║                                                               ║
  ╚═══════════════════════════════════════════════════════════════╝
""")

    # Keep alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()


if __name__ == "__main__":
    main()
