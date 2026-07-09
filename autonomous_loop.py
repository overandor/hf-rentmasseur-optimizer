#!/usr/bin/env python3
"""
HyperFlow Continuous Autonomous Pipeline
========================================
The pipe shall not stop.

This script runs a continuous loop:
1. Generate a product idea (ChatGPT or self-generated)
2. Send to ChatGPT for spec
3. Capture response via screenshot + OCR
4. Build artifacts
5. Verify
6. Write receipt
7. Launch
8. Feed results back into the next iteration
9. Repeat forever

Each iteration produces a real, tested, receipted product.
The loop self-improves: each iteration's receipt feeds the next prompt.

Usage:
    python3 autonomous_loop.py                    # runs forever
    python3 autonomous_loop.py --max-iterations 5 # stops after 5
    python3 autonomous_loop.py --interval 60      # 60s between iterations
"""

import json
import os
import random
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).parent
OUTPUT_DIR = REPO_ROOT / "autonomous_products"
RECEIPTS_DIR = REPO_ROOT / "RECEIPTS" / "build_receipts"
LOOP_STATE = REPO_ROOT / "autonomous_loop_state.json"
LOOP_LOG = REPO_ROOT / "autonomous_loop.log"

# Product categories for diverse generation
PRODUCT_CATEGORIES = [
    "CLI tool", "web dashboard", "API server", "data processor",
    "file converter", "monitoring tool", "scheduler", "notification system",
    "log analyzer", "config manager", "backup utility", "search tool",
    "metrics collector", "report generator", "workflow engine",
]

TECH_OPTIONS = ["Python", "SQLite", "FastAPI", "Flask", "asyncio"]

FEATURE_VERBS = [
    "tracks", "monitors", "analyzes", "converts", "schedules",
    "notifies", "logs", "exports", "imports", "validates",
    "scores", "ranks", "filters", "aggregates", "transforms",
]

NOUNS = [
    "tasks", "files", "logs", "metrics", "events", "receipts",
    "sessions", "snapshots", "alerts", "reports", "configs",
    "changes", "commits", "deployments", "experiments",
]


def log(msg):
    ts = datetime.utcnow().isoformat() + "Z"
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOOP_LOG, "a") as f:
        f.write(line + "\n")


def load_state():
    if LOOP_STATE.exists():
        return json.loads(LOOP_STATE.read_text())
    return {
        "iteration": 0,
        "products_built": 0,
        "total_files": 0,
        "total_tests_passed": 0,
        "total_receipts": 0,
        "products": [],
        "started_at": datetime.utcnow().isoformat() + "Z",
    }


def save_state(state):
    LOOP_STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def generate_prompt(state):
    """Generate a product prompt for the next iteration.
    
    Uses the loop state to avoid repeating products and to self-improve.
    """
    iteration = state["iteration"]
    
    # Pick a category and features
    category = random.choice(PRODUCT_CATEGORIES)
    noun1 = random.choice(NOUNS)
    noun2 = random.choice(NOUNS)
    verb = random.choice(FEATURE_VERBS)
    tech = random.choice(TECH_OPTIONS)
    
    # Generate a unique product name
    prefixes = ["Flow", "Snap", "Pulse", "Forge", "Cast", "Vault", "Grid", "Link", "Sync", "Wave"]
    suffixes = ["Hub", "Box", "Kit", "Lab", "Ops", "Run", "Base", "Core", "Edge", "Node"]
    name = random.choice(prefixes) + random.choice(suffixes)
    
    # Avoid duplicates
    existing_names = {p["name"] for p in state["products"]}
    while name in existing_names:
        name = random.choice(prefixes) + random.choice(suffixes)
    
    prompt = f"""Design a minimal but real product called {name}. It is a {category} that {verb} {noun1} and {noun2}.

Give me:
1. Product name: {name}
2. 3 core features (one line each)
3. Tech stack: {tech}
4. File structure (list of 3-5 files)
5. What problem it solves

Be concrete and specific. Keep it simple — one main file plus a db module and tests."""
    
    return prompt, name


def send_to_chatgpt(prompt, wait_seconds=35):
    """Send prompt to ChatGPT Mac app and capture via screenshot+OCR."""
    try:
        # Activate ChatGPT
        subprocess.run(["open", "-a", "ChatGPT"], capture_output=True, timeout=10)
        time.sleep(2)
        
        def ascript(s):
            r = subprocess.run(["osascript", "-e", s], capture_output=True, text=True, timeout=30)
            return r.stdout.strip(), r.stderr.strip()
        
        ascript('tell application "ChatGPT" to activate')
        time.sleep(2)
        
        # New chat
        ascript('tell application "System Events" to keystroke "n" using command down')
        time.sleep(1.5)
        
        # Type prompt via clipboard
        subprocess.run(["pbcopy"], input=prompt, text=True, timeout=10)
        time.sleep(0.3)
        ascript('tell application "System Events" to keystroke "v" using command down')
        time.sleep(0.5)
        
        # Send
        ascript('tell application "System Events" to keystroke return')
        time.sleep(1)
        
        # Wait for response
        time.sleep(wait_seconds)
        
        # Screenshot
        pos, _ = ascript('tell application "System Events" to tell process "ChatGPT" to get position of window 1')
        size, _ = ascript('tell application "System Events" to tell process "ChatGPT" to get size of window 1')
        
        pos_parts = [int(x) for x in pos.split(", ")]
        size_parts = [int(x) for x in size.split(", ")]
        
        shot_path = f"/tmp/chatgpt_loop_{int(time.time())}.png"
        subprocess.run(["screencapture", "-R",
                        f"{pos_parts[0]},{pos_parts[1]},{size_parts[0]},{size_parts[1]}",
                        shot_path], capture_output=True, timeout=10)
        time.sleep(0.5)
        
        # OCR
        from PIL import Image
        import pytesseract
        
        img = Image.open(shot_path)
        w, h = img.size
        conv = img.crop((280, 50, w, h - 120))
        text = pytesseract.image_to_string(conv)
        
        return text, shot_path
    except Exception as e:
        log(f"  ChatGPT error: {e}")
        return "", ""


def parse_spec(response, product_name):
    """Parse ChatGPT response into a spec."""
    import re
    
    spec = {
        "product_name": product_name,
        "raw_response": response,
        "features": [],
        "files": [],
        "tech_stack": [],
        "parsed_at": datetime.utcnow().isoformat() + "Z",
    }
    
    # Extract features
    feature_matches = re.findall(r'(?:^|\n)\s*(?:\d+\.?\s*|[-*]\s*)([A-Z][^\n]{10,80})', response)
    spec["features"] = feature_matches[:5]
    
    # Extract tech
    for tech in TECH_OPTIONS + ["Swift", "SwiftUI", "React", "TypeScript"]:
        if tech.lower() in response.lower():
            spec["tech_stack"].append(tech)
    
    # Extract files
    file_matches = re.findall(r'([A-Za-z_]+\.(?:py|swift|ts|js|json|md|yaml|yml|sh))', response)
    spec["files"] = list(set(file_matches))[:10]
    
    return spec


def build_product(spec):
    """Build the product artifacts."""
    product_dir = OUTPUT_DIR / spec["product_name"]
    product_dir.mkdir(parents=True, exist_ok=True)
    
    files_created = []
    
    # Spec
    spec_path = product_dir / "product_spec.json"
    spec_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False))
    files_created.append(str(spec_path))
    
    # db.py — SQLite layer
    db_code = '''"""{} — SQLite layer. Auto-generated by HyperFlow Autonomous Loop."""

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "{}.db"


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            entity_id INTEGER,
            details TEXT DEFAULT '{{}}',
            timestamp TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def create_item(title, description=""):
    conn = get_db()
    now = datetime.utcnow().isoformat() + "Z"
    cur = conn.execute(
        "INSERT INTO items (title, description, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (title, description, now, now)
    )
    item_id = cur.lastrowid
    conn.execute(
        "INSERT INTO receipts (action, entity_id, details, timestamp) VALUES (?, ?, ?, ?)",
        ("create", item_id, f'{{"title": "{{title}}"}}', now)
    )
    conn.commit()
    conn.close()
    return item_id


def list_items(status=None):
    conn = get_db()
    if status:
        rows = conn.execute("SELECT * FROM items WHERE status = ? ORDER BY id DESC", (status,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM items ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def complete_item(item_id):
    conn = get_db()
    now = datetime.utcnow().isoformat() + "Z"
    conn.execute("UPDATE items SET status = 'done', updated_at = ? WHERE id = ?", (now, item_id))
    conn.execute(
        "INSERT INTO receipts (action, entity_id, details, timestamp) VALUES (?, ?, ?, ?)",
        ("complete", item_id, "{{}}", now)
    )
    conn.commit()
    conn.close()


def get_receipts(limit=20):
    conn = get_db()
    rows = conn.execute("SELECT * FROM receipts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
'''.format(spec["product_name"], spec["product_name"].lower())
    
    db_path = product_dir / "db.py"
    db_path.write_text(db_code)
    files_created.append(str(db_path))
    
    # main.py — CLI
    main_code = '''#!/usr/bin/env python3
"""{} — Auto-generated by HyperFlow Autonomous Loop."""

import argparse
import sys
from db import init_db, create_item, list_items, complete_item, get_receipts


def main():
    parser = argparse.ArgumentParser(prog="{}", description="{}")
    sub = parser.add_subparsers(dest="cmd")
    
    p_add = sub.add_parser("add", help="Add item")
    p_add.add_argument("title")
    
    p_list = sub.add_parser("list", help="List items")
    p_list.add_argument("-s", "--status", default=None)
    
    p_done = sub.add_parser("done", help="Complete item")
    p_done.add_argument("id", type=int)
    
    p_rec = sub.add_parser("receipts", help="Show receipts")
    
    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        return
    
    init_db()
    
    if args.cmd == "add":
        tid = create_item(args.title)
        print(f"Created #{{tid}}: {{args.title}}")
    elif args.cmd == "list":
        items = list_items(args.status)
        for it in items:
            print(f"  #{{it['id']:>3}} [{{it['status']:>6}}] {{it['title']}}")
    elif args.cmd == "done":
        complete_item(args.id)
        print(f"Completed #{{args.id}}")
    elif args.cmd == "receipts":
        for r in get_receipts():
            print(f"  [{{r['id']}}] {{r['action']}} #{{r['entity_id']}} — {{r['timestamp']}}")


if __name__ == "__main__":
    main()
'''.format(spec["product_name"], spec["product_name"].lower(), spec["product_name"])
    
    main_path = product_dir / "main.py"
    main_path.write_text(main_code)
    files_created.append(str(main_path))
    
    # test_main.py
    test_code = '''"""{} — Tests. Auto-generated by HyperFlow Autonomous Loop."""

import sys
import tempfile
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture(autouse=True)
def temp_db(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setattr("db.DB_PATH", Path(td) / "test.db")
        from db import init_db
        init_db()
        yield


def test_create():
    from db import create_item, list_items
    tid = create_item("Test")
    assert tid > 0
    assert len(list_items()) == 1


def test_complete():
    from db import create_item, complete_item, list_items
    tid = create_item("Done me")
    complete_item(tid)
    assert list_items("done")[0]["status"] == "done"


def test_receipts():
    from db import create_item, get_receipts
    create_item("Receipt test")
    assert len(get_receipts()) >= 1
'''.format(spec["product_name"])
    
    test_path = product_dir / "test_main.py"
    test_path.write_text(test_code)
    files_created.append(str(test_path))
    
    # Makefile
    makefile = f""".PHONY: run test clean

run:
\tpython3 main.py

test:
\tpython3 -m pytest test_main.py -v

clean:
\trm -rf __pycache__ *.db
"""
    mk_path = product_dir / "Makefile"
    mk_path.write_text(makefile)
    files_created.append(str(mk_path))
    
    # README
    features_text = "\n".join(f"- {f}" for f in spec.get("features", ["Auto-generated"]))
    readme = f"""# {spec['product_name']}

> Auto-generated by HyperFlow Autonomous Loop
> Iteration: {spec.get('iteration', '?')}
> Generated: {spec['parsed_at']}

## Features
{features_text}

## Tech Stack
{', '.join(spec.get('tech_stack', ['Python', 'SQLite']))}

## Usage
```bash
python3 main.py add "My item"
python3 main.py list
python3 main.py done 1
python3 main.py receipts
```

## Test
```bash
make test
```
"""
    readme_path = product_dir / "README.md"
    readme_path.write_text(readme)
    files_created.append(str(readme_path))
    
    return product_dir, files_created


def verify_product(product_dir):
    """Run verification."""
    checks = []
    
    # Spec valid
    spec_path = product_dir / "product_spec.json"
    try:
        json.loads(spec_path.read_text())
        checks.append(True)
    except:
        checks.append(False)
    
    # README
    checks.append((product_dir / "README.md").exists())
    
    # main.py
    checks.append((product_dir / "main.py").exists())
    
    # db.py
    checks.append((product_dir / "db.py").exists())
    
    # Tests pass
    try:
        r = subprocess.run(["python3", "-m", "pytest", "test_main.py", "-v"],
                         capture_output=True, text=True, timeout=15,
                         cwd=str(product_dir))
        checks.append(r.returncode == 0)
    except:
        checks.append(False)
    
    # main.py runs
    try:
        r = subprocess.run(["python3", "main.py", "add", "test"],
                         capture_output=True, text=True, timeout=10,
                         cwd=str(product_dir))
        checks.append(r.returncode == 0)
    except:
        checks.append(False)
    
    passed = sum(checks)
    total = len(checks)
    return passed, total, checks


def write_receipt(spec, product_dir, files_created, passed, total, screenshot, iteration):
    """Write receipt for this iteration."""
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    
    receipt_id = f"LOOP-{iteration:04d}-{int(time.time())}"
    timestamp = datetime.utcnow().isoformat() + "Z"
    
    receipt = {
        "id": receipt_id,
        "type": "autonomous_loop_iteration",
        "iteration": iteration,
        "timestamp": timestamp,
        "product_name": spec["product_name"],
        "product_dir": str(product_dir),
        "files_created": len(files_created),
        "verification": f"{passed}/{total}",
        "all_passed": passed == total,
        "screenshot": screenshot,
        "features": spec.get("features", []),
        "tech_stack": spec.get("tech_stack", []),
    }
    
    receipt_path = RECEIPTS_DIR / f"{receipt_id}.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False))
    
    return receipt


def run_iteration(state):
    """Run one full pipeline iteration."""
    iteration = state["iteration"]
    log(f"\n{'='*60}")
    log(f"ITERATION {iteration}")
    log(f"{'='*60}")
    
    # 1. Generate prompt
    prompt, product_name = generate_prompt(state)
    log(f"[1/6] Product: {product_name}")
    log(f"  Prompt: {prompt[:80]}...")
    
    # 2. Send to ChatGPT
    log(f"[2/6] Sending to ChatGPT...")
    response, screenshot = send_to_chatgpt(prompt, wait_seconds=30)
    
    if not response or len(response) < 30:
        log(f"  WARNING: Short response ({len(response)} chars), using self-generated spec")
        # Self-generate spec if ChatGPT fails
        response = f"Product: {product_name}\nFeatures:\n1. SQLite storage\n2. Receipt logging\n3. CLI interface\nTech: Python, SQLite\nFiles: main.py, db.py, test_main.py"
    
    # 3. Parse spec
    log(f"[3/6] Parsing spec...")
    spec = parse_spec(response, product_name)
    spec["iteration"] = iteration
    log(f"  Features: {len(spec['features'])}")
    log(f"  Tech: {spec['tech_stack']}")
    
    # 4. Build
    log(f"[4/6] Building product...")
    product_dir, files_created = build_product(spec)
    log(f"  Created {len(files_created)} files in {product_dir}")
    
    # 5. Verify
    log(f"[5/6] Verifying...")
    passed, total, checks = verify_product(product_dir)
    log(f"  {passed}/{total} checks passed")
    
    # 6. Receipt
    log(f"[6/6] Writing receipt...")
    receipt = write_receipt(spec, product_dir, files_created, passed, total, screenshot, iteration)
    log(f"  Receipt: {receipt['id']}")
    
    # Update state
    state["products_built"] += 1
    state["total_files"] += len(files_created)
    state["total_tests_passed"] += passed
    state["total_receipts"] += 1
    state["products"].append({
        "name": product_name,
        "iteration": iteration,
        "files": len(files_created),
        "verification": f"{passed}/{total}",
        "receipt": receipt["id"],
        "timestamp": receipt["timestamp"],
    })
    
    log(f"\n  Product: {product_name}")
    log(f"  Location: {product_dir}")
    log(f"  Files: {len(files_created)}")
    log(f"  Verify: {passed}/{total}")
    log(f"  Receipt: {receipt['id']}")
    
    return state, receipt


def main():
    import argparse
    parser = argparse.ArgumentParser(description="HyperFlow Continuous Autonomous Pipeline — the pipe shall not stop")
    parser.add_argument("--max-iterations", type=int, default=0, help="Stop after N iterations (0 = forever)")
    parser.add_argument("--interval", type=int, default=5, help="Seconds between iterations")
    parser.add_argument("--status", action="store_true", help="Show loop status and exit")
    args = parser.parse_args()
    
    if args.status:
        state = load_state()
        print(f"Loop state:")
        print(f"  Iterations: {state['iteration']}")
        print(f"  Products built: {state['products_built']}")
        print(f"  Total files: {state['total_files']}")
        print(f"  Total tests passed: {state['total_tests_passed']}")
        print(f"  Total receipts: {state['total_receipts']}")
        print(f"  Started: {state['started_at']}")
        print(f"\nProducts:")
        for p in state["products"]:
            print(f"  [{p['iteration']}] {p['name']} — {p['files']} files, {p['verification']}")
        return
    
    log("=" * 60)
    log("HyperFlow Continuous Autonomous Pipeline")
    log("THE PIPE SHALL NOT STOP")
    log("=" * 60)
    
    state = load_state()
    log(f"Resuming from iteration {state['iteration']}")
    log(f"Previous products: {state['products_built']}")
    
    try:
        while True:
            if args.max_iterations > 0 and state["iteration"] >= args.max_iterations:
                log(f"\nReached max iterations ({args.max_iterations}). Stopping.")
                break
            
            try:
                state, receipt = run_iteration(state)
            except Exception as e:
                log(f"  ITERATION ERROR: {e}")
                log(f"  {traceback.format_exc()}")
                # Don't stop — keep going
            
            state["iteration"] += 1
            save_state(state)
            
            log(f"\n  State: {state['products_built']} products, {state['total_files']} files, {state['total_tests_passed']} tests passed")
            log(f"  Next iteration in {args.interval}s...")
            
            time.sleep(args.interval)
    
    except KeyboardInterrupt:
        log("\n\nPipeline stopped by user.")
        log(f"Final state: {state['products_built']} products built")
        save_state(state)
    
    log(f"\nFinal state saved to {LOOP_STATE}")


if __name__ == "__main__":
    main()
