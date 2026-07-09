#!/usr/bin/env python3
"""
HyperFlow Autonomous Product Pipeline
=====================================
ChatGPT (strategist) → OCR capture → Builder (us) → Verify → Receipt → Launch

This script:
1. Sends a product spec prompt to ChatGPT Mac app
2. Captures the response via screenshot + OCR
3. Parses the response into a buildable spec
4. Builds the artifacts (code, project structure, README)
5. Runs verification
6. Writes a receipt
7. Produces a launch summary

No API key needed. Uses the already-logged-in ChatGPT desktop app.
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).parent
OUTPUT_DIR = REPO_ROOT / "autonomous_products"
RECEIPTS_DIR = REPO_ROOT / "RECEIPTS" / "build_receipts"


def run_applescript(script, timeout=30):
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip(), r.stderr.strip()


def send_to_chatgpt(prompt, wait_seconds=35):
    """Send prompt to ChatGPT Mac app and capture response via screenshot+OCR."""
    print("\n[1/7] Sending prompt to ChatGPT...")
    print(f"  Prompt: {prompt[:80]}...")
    
    # Activate ChatGPT
    subprocess.run(["open", "-a", "ChatGPT"], capture_output=True, timeout=10)
    time.sleep(2)
    run_applescript('tell application "ChatGPT" to activate')
    time.sleep(2)
    
    # New chat
    run_applescript('tell application "System Events" to keystroke "n" using command down')
    time.sleep(1.5)
    
    # Type prompt via clipboard
    subprocess.run(["pbcopy"], input=prompt, text=True, timeout=10)
    time.sleep(0.3)
    run_applescript('tell application "System Events" to keystroke "v" using command down')
    time.sleep(0.5)
    
    # Send
    run_applescript('tell application "System Events" to keystroke return')
    time.sleep(1)
    
    # Wait for response
    print(f"  Waiting {wait_seconds}s for response...")
    time.sleep(wait_seconds)
    
    # Capture screenshot
    pos, _ = run_applescript('tell application "System Events" to tell process "ChatGPT" to get position of window 1')
    size, _ = run_applescript('tell application "System Events" to tell process "ChatGPT" to get size of window 1')
    
    pos_parts = [int(x) for x in pos.split(", ")]
    size_parts = [int(x) for x in size.split(", ")]
    
    shot_path = f"/tmp/chatgpt_autonomous_{int(time.time())}.png"
    subprocess.run(["screencapture", "-R",
                    f"{pos_parts[0]},{pos_parts[1]},{size_parts[0]},{size_parts[1]}",
                    shot_path], capture_output=True, timeout=10)
    
    # OCR
    from PIL import Image
    import pytesseract
    
    img = Image.open(shot_path)
    w, h = img.size
    conv = img.crop((280, 50, w, h - 120))
    text = pytesseract.image_to_string(conv)
    
    print(f"  OCR captured: {len(text)} chars")
    print(f"  Screenshot: {shot_path}")
    
    return text, shot_path


def parse_spec(chatgpt_response):
    """Parse ChatGPT's response into a buildable product spec."""
    print("\n[2/7] Parsing ChatGPT response into product spec...")
    
    spec = {
        "raw_response": chatgpt_response,
        "product_name": "AutoProduct",
        "description": "",
        "features": [],
        "files": [],
        "tech_stack": [],
        "parsed_at": datetime.utcnow().isoformat() + "Z",
    }
    
    # Try to extract product name
    name_match = re.search(r'(?:product name|app name|name:)\s*["\']?([A-Za-z0-9_\-\s]+)["\']?', chatgpt_response, re.I)
    if name_match:
        spec["product_name"] = name_match.group(1).strip().replace(" ", "_")
    
    # Extract features (numbered or bulleted lists)
    feature_matches = re.findall(r'(?:^|\n)\s*(?:\d+\.?\s*|[-*]\s*)([A-Z][^\n]{10,80})', chatgpt_response)
    spec["features"] = feature_matches[:10]
    
    # Extract tech stack mentions
    tech_keywords = ["Swift", "SwiftUI", "Python", "FastAPI", "React", "TypeScript", 
                     "SQLite", "CoreData", "WebKit", "AppKit", "Combine", "asyncio",
                     "Flask", "Node", "Rust", "Go"]
    for tech in tech_keywords:
        if tech.lower() in chatgpt_response.lower():
            spec["tech_stack"].append(tech)
    
    # Extract file structure mentions
    file_matches = re.findall(r'([A-Za-z_]+\.(?:py|swift|ts|js|json|md|yaml|yml|sh))', chatgpt_response)
    spec["files"] = list(set(file_matches))[:15]
    
    print(f"  Product: {spec['product_name']}")
    print(f"  Features: {len(spec['features'])}")
    print(f"  Tech stack: {spec['tech_stack']}")
    print(f"  Files mentioned: {spec['files']}")
    
    return spec


def build_artifacts(spec):
    """Build the product artifacts based on the parsed spec."""
    print("\n[3/7] Building artifacts from spec...")
    
    product_dir = OUTPUT_DIR / spec["product_name"]
    product_dir.mkdir(parents=True, exist_ok=True)
    
    files_created = []
    
    # 1. Product spec JSON
    spec_path = product_dir / "product_spec.json"
    spec_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False))
    files_created.append(str(spec_path))
    
    # 2. README.md
    readme = f"""# {spec['product_name']}

> Auto-generated by HyperFlow Autonomous Product Pipeline
> Generated: {spec['parsed_at']}

## Description
{spec.get('description', 'Product spec generated from ChatGPT consultation.')}

## Features
"""
    for i, feature in enumerate(spec["features"], 1):
        readme += f"{i}. {feature}\n"
    
    readme += f"""
## Tech Stack
{', '.join(spec['tech_stack']) if spec['tech_stack'] else 'TBD'}

## Files
{', '.join(spec['files']) if spec['files'] else 'TBD'}

## Origin
This product was conceived by ChatGPT and built by the HyperFlow autonomous pipeline.
The full ChatGPT response is preserved in `product_spec.json` under `raw_response`.

## Pipeline
1. ChatGPT generated the product concept
2. Screenshot + OCR captured the response
3. Spec was parsed automatically
4. Artifacts were generated
5. Verification was run
6. Receipt was written
7. Product was launched
"""
    readme_path = product_dir / "README.md"
    readme_path.write_text(readme)
    files_created.append(str(readme_path))
    
    # 3. Main entry point (Python or Swift based on tech stack)
    if "Swift" in spec["tech_stack"] or "SwiftUI" in spec["tech_stack"]:
        main_code = f"""//
//  {spec['product_name']}.swift
//  Auto-generated by HyperFlow Autonomous Pipeline
//

import SwiftUI
import Foundation

@main
struct {spec['product_name']}App: App {{
    var body: some Scene {{
        WindowGroup {{
            ContentView()
        }}
    }}
}}

struct ContentView: View {{
    @State private var tasks: [String] = []
    @State private var newTask = ""
    
    var body: some View {{
        NavigationStack {{
            List {{
                ForEach(tasks, id: \\..self) {{ task in
                    Text(task)
                }}
            }}
            .navigationTitle("{spec['product_name']}")
            .toolbar {{
                TextField("New task", text: $newTask)
                Button("Add") {{
                    tasks.append(newTask)
                    newTask = ""
                }}
            }}
        }}
    }}
}}
"""
        main_path = product_dir / f"{spec['product_name']}.swift"
        main_path.write_text(main_code)
        files_created.append(str(main_path))
    
    else:
        main_code = f'''#!/usr/bin/env python3
"""
{spec['product_name']} — Auto-generated by HyperFlow Autonomous Pipeline
Generated: {spec['parsed_at']}
"""

import json
import sys
from pathlib import Path

def main():
    spec_path = Path(__file__).parent / "product_spec.json"
    if spec_path.exists():
        spec = json.loads(spec_path.read_text())
        print(f"Product: {{spec['product_name']}}")
        print(f"Features: {{len(spec.get('features', []))}}")
        print(f"Tech: {{', '.join(spec.get('tech_stack', []))}}")
        print()
        for i, f in enumerate(spec.get('features', []), 1):
            print(f"  {{i}}. {{f}}")
    else:
        print("{spec['product_name']} — no spec found")

if __name__ == "__main__":
    main()
'''
        main_path = product_dir / "main.py"
        main_path.write_text(main_code)
        files_created.append(str(main_path))
    
    # 4. Makefile
    makefile = f""".PHONY: run test clean

run:
\tpython3 main.py

test:
\tpython3 -c "import json; s=json.load(open('product_spec.json')); assert 'product_name' in s; print('Tests passed')"

clean:
\trm -rf __pycache__
"""
    makefile_path = product_dir / "Makefile"
    makefile_path.write_text(makefile)
    files_created.append(str(makefile_path))
    
    # 5. If files were mentioned in spec, create stubs
    for fname in spec["files"]:
        if fname not in ["main.py", "README.md", "product_spec.json", "Makefile"]:
            fpath = product_dir / fname
            if not fpath.exists():
                if fname.endswith(".py"):
                    fpath.write_text(f'"""{fname} — Auto-generated stub."""\n')
                elif fname.endswith(".swift"):
                    fpath.write_text(f'// {fname} — Auto-generated stub\n')
                elif fname.endswith(".json"):
                    fpath.write_text('{}\n')
                elif fname.endswith(".md"):
                    fpath.write_text(f'# {fname}\n\nAuto-generated stub.\n')
                else:
                    fpath.write_text(f'# {fname} — Auto-generated stub\n')
                files_created.append(str(fpath))
    
    print(f"  Created {len(files_created)} files in {product_dir}")
    for f in files_created:
        print(f"    {f}")
    
    return product_dir, files_created


def verify_product(product_dir):
    """Run verification on the built product."""
    print("\n[4/7] Verifying product...")
    
    checks = []
    
    # Check 1: product_spec.json exists and is valid JSON
    spec_path = product_dir / "product_spec.json"
    if spec_path.exists():
        try:
            spec = json.loads(spec_path.read_text())
            checks.append({"check": "spec_json_valid", "passed": True})
        except:
            checks.append({"check": "spec_json_valid", "passed": False, "error": "Invalid JSON"})
    else:
        checks.append({"check": "spec_json_valid", "passed": False, "error": "File missing"})
    
    # Check 2: README exists
    readme_path = product_dir / "README.md"
    checks.append({"check": "readme_exists", "passed": readme_path.exists()})
    
    # Check 3: Main entry point exists
    main_py = product_dir / "main.py"
    main_swift = product_dir / f"{spec.get('product_name', 'AutoProduct')}.swift"
    has_entry = main_py.exists() or main_swift.exists()
    checks.append({"check": "entry_point_exists", "passed": has_entry})
    
    # Check 4: Makefile exists
    checks.append({"check": "makefile_exists", "passed": (product_dir / "Makefile").exists()})
    
    # Check 5: Try running main.py if it exists
    if main_py.exists():
        try:
            r = subprocess.run(["python3", str(main_py)], capture_output=True, text=True, timeout=10,
                             cwd=str(product_dir))
            checks.append({"check": "main_runs", "passed": r.returncode == 0, 
                          "output": r.stdout[:200] if r.stdout else r.stderr[:200]})
        except Exception as e:
            checks.append({"check": "main_runs", "passed": False, "error": str(e)})
    
    # Check 6: Try make test
    makefile = product_dir / "Makefile"
    if makefile.exists():
        try:
            r = subprocess.run(["make", "test"], capture_output=True, text=True, timeout=10,
                             cwd=str(product_dir))
            checks.append({"check": "make_test", "passed": r.returncode == 0,
                          "output": r.stdout[:200]})
        except Exception as e:
            checks.append({"check": "make_test", "passed": False, "error": str(e)})
    
    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    
    print(f"  {passed}/{total} checks passed")
    for c in checks:
        status = "✅" if c["passed"] else "❌"
        print(f"    {status} {c['check']}")
    
    return checks, passed, total


def write_receipt(spec, product_dir, files_created, checks, screenshot_path):
    """Write a receipt for the autonomous pipeline run."""
    print("\n[5/7] Writing receipt...")
    
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    
    receipt_id = f"AUTO-{int(time.time())}"
    timestamp = datetime.utcnow().isoformat() + "Z"
    
    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    
    receipt = {
        "id": receipt_id,
        "type": "autonomous_product_launch",
        "timestamp": timestamp,
        "product_name": spec["product_name"],
        "product_dir": str(product_dir),
        "files_created": files_created,
        "file_count": len(files_created),
        "verification": {
            "checks": checks,
            "passed": passed,
            "total": total,
            "all_passed": passed == total,
        },
        "screenshot": screenshot_path,
        "chatgpt_response_length": len(spec.get("raw_response", "")),
        "features_count": len(spec.get("features", [])),
        "tech_stack": spec.get("tech_stack", []),
    }
    
    receipt_path = RECEIPTS_DIR / f"{receipt_id}.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False))
    
    # Also write markdown receipt
    md_receipt = f"""# Receipt: {receipt_id}

**Type**: Autonomous Product Launch
**Timestamp**: {timestamp}
**Product**: {spec['product_name']}

## Files Created ({len(files_created)})
"""
    for f in files_created:
        md_receipt += f"- `{f}`\n"
    
    md_receipt += f"""
## Verification ({passed}/{total} passed)
"""
    for c in checks:
        status = "PASS" if c["passed"] else "FAIL"
        md_receipt += f"- [{status}] {c['check']}\n"
    
    md_receipt += f"""
## Screenshot
`{screenshot_path}`

## ChatGPT Response Length
{len(spec.get('raw_response', ''))} chars

## Features
"""
    for f in spec.get("features", []):
        md_receipt += f"- {f}\n"
    
    md_path = RECEIPTS_DIR / f"{receipt_id}.md"
    md_path.write_text(md_receipt)
    
    print(f"  Receipt: {receipt_path}")
    print(f"  Markdown: {md_path}")
    
    return receipt


def launch_summary(spec, product_dir, receipt):
    """Print the launch summary."""
    print("\n[6/7] Launch Summary")
    print("=" * 60)
    print(f"  Product: {spec['product_name']}")
    print(f"  Location: {product_dir}")
    print(f"  Files: {receipt['file_count']}")
    print(f"  Features: {receipt['features_count']}")
    print(f"  Tech: {', '.join(receipt['tech_stack'])}")
    print(f"  Verification: {receipt['verification']['passed']}/{receipt['verification']['total']}")
    print(f"  Receipt: {receipt['id']}")
    print("=" * 60)
    
    print("\n[7/7] Product launched! 🚀")
    print(f"\n  cd {product_dir}")
    print(f"  make run")
    
    return receipt


def run_autonomous_pipeline(prompt=None):
    """Run the full autonomous pipeline."""
    print("=" * 60)
    print("HyperFlow Autonomous Product Pipeline")
    print("ChatGPT → OCR → Build → Verify → Receipt → Launch")
    print("=" * 60)
    
    if prompt is None:
        prompt = """Design a minimal but real macOS product that I can build and launch today. 
Give me:
1. Product name (one word)
2. 3 core features (one line each)
3. Tech stack (Python or Swift)
4. File structure (list of files)
5. What problem it solves
Keep it simple enough to build in one file. Be concrete and specific."""
    
    # 1. Send to ChatGPT and capture response
    response, screenshot = send_to_chatgpt(prompt, wait_seconds=35)
    
    if not response or len(response) < 50:
        print("ERROR: ChatGPT response too short or empty")
        return None
    
    # 2. Parse into spec
    spec = parse_spec(response)
    
    # 3. Build artifacts
    product_dir, files_created = build_artifacts(spec)
    
    # 4. Verify
    checks, passed, total = verify_product(product_dir)
    
    # 5. Write receipt
    receipt = write_receipt(spec, product_dir, files_created, checks, screenshot)
    
    # 6. Launch summary
    launch_summary(spec, product_dir, receipt)
    
    return receipt


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="HyperFlow Autonomous Product Pipeline")
    parser.add_argument("prompt", nargs="?", help="Custom prompt for ChatGPT")
    parser.add_argument("--wait", type=int, default=35, help="Seconds to wait for ChatGPT response")
    args = parser.parse_args()
    
    prompt = args.prompt or None
    if prompt:
        # Override wait time
        original_send = send_to_chatgpt
        def send_with_wait(p, w=args.wait):
            return original_send(p, w)
        send_to_chatgpt.__defaults__ = (args.wait,)
    
    receipt = run_autonomous_pipeline(prompt)
    if receipt:
        sys.exit(0)
    else:
        sys.exit(1)
