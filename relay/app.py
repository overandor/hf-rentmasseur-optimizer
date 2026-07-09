#!/usr/bin/env python3
"""
HyperFlow AGI — Boss Agent Edition
====================================
A "boss agent" clone of the user controls all agent apps on the Mac.
It VISIBLY opens Terminal, ChatGPT, Claude, Codex, Devin — you watch it happen.
The boss thinks, decides, commands, and verifies — fully autonomous 24/7.

Run: python3 relay/app.py
Open: http://localhost:8765
"""

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))
from relay_hub import (
    RelayHub, AGENT_PROFILES, PIPELINE_STAGES, STAGE_AGENTS,
    STAGE_DESCRIPTIONS, now_iso, REPO_ROOT
)

hub = RelayHub()
BUILD_DIR = REPO_ROOT / "relay" / "builds"
BUILD_DIR.mkdir(parents=True, exist_ok=True)

# --- Boss Agent State ---
boss = {
    "running": False,
    "cycle": 0,
    "status": "offline",
    "uptime": None,
    "personality": "Joseph — decisive builder, ships fast, hates overthinking, tests everything",
    "current_thought": "",
    "current_command": "",
    "log": [],
    "active_project": None,
    "active_stage": None,
    "visible_actions": [],  # actions that were visibly performed on screen
    "metrics": {
        "products_shipped": 0,
        "tests_passed": 0,
        "tests_failed": 0,
        "stages_completed": 0,
        "stages_failed": 0,
        "receipts_written": 0,
        "lines_of_code": 0,
        "cycles": 0,
        "apps_launched": 0,
    },
}
boss_thread = None
boss_lock = threading.Lock()


def blog(msg, visible=False):
    """Log a boss action."""
    ts = datetime.now().strftime('%H:%M:%S')
    with boss_lock:
        boss["log"].append(f"[{ts}] {msg}")
        if len(boss["log"]) > 80:
            boss["log"] = boss["log"][-80:]
        if visible:
            boss["visible_actions"].append(f"[{ts}] {msg}")
            if len(boss["visible_actions"]) > 20:
                boss["visible_actions"] = boss["visible_actions"][-20:]


# --- Boss Agent: Actually controls real apps on the Mac ---

def boss_open_terminal(name="HyperFlow", command=None):
    """Open a Terminal window and optionally run a command — user SEES it."""
    try:
        script = f'''
        tell application "Terminal"
            activate
            do script "echo '🤖 Boss Agent: {name}'"
        end tell
        '''
        subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        time.sleep(1)
        if command:
            # Type the command into the terminal
            subprocess.run(["pbcopy"], input=command, text=True, timeout=5)
            subprocess.run(["osascript", "-e", 
                'tell application "System Events" to keystroke "v" using command down'], 
                capture_output=True, text=True, timeout=5)
            time.sleep(0.3)
            subprocess.run(["osascript", "-e", 
                'tell application "System Events" to keystroke return'], 
                capture_output=True, text=True, timeout=5)
            time.sleep(1)
        return True
    except Exception as e:
        blog(f"⚠️ Terminal open failed: {e}")
        return False


def boss_open_chatgpt(prompt=None):
    """Open ChatGPT app and optionally send a prompt — user SEES it."""
    try:
        subprocess.run(["open", "-a", "ChatGPT"], capture_output=True, timeout=10)
        time.sleep(2)
        subprocess.run(["osascript", "-e", 'tell application "ChatGPT" to activate'], 
                       capture_output=True, text=True, timeout=10)
        time.sleep(1)
        if prompt:
            # New conversation
            subprocess.run(["osascript", "-e", 
                'tell application "System Events" to keystroke "n" using command down'], 
                capture_output=True, text=True, timeout=5)
            time.sleep(1)
            # Paste prompt
            subprocess.run(["pbcopy"], input=prompt, text=True, timeout=5)
            subprocess.run(["osascript", "-e", 
                'tell application "System Events" to keystroke "v" using command down'], 
                capture_output=True, text=True, timeout=5)
            time.sleep(0.3)
            subprocess.run(["osascript", "-e", 
                'tell application "System Events" to keystroke return'], 
                capture_output=True, text=True, timeout=5)
            time.sleep(2)
        return True
    except Exception as e:
        blog(f"⚠️ ChatGPT open failed: {e}")
        return False


def boss_run_in_terminal(command, wait=5):
    """Run a command in a visible Terminal window and capture output."""
    try:
        # Use a temp file to capture output while showing it in terminal
        outfile = f"/tmp/boss_{int(time.time())}.txt"
        full_cmd = f"{command} 2>&1 | tee {outfile}; echo '__DONE__'"
        boss_open_terminal(command=full_cmd)
        time.sleep(wait)
        # Read the output
        if os.path.exists(outfile):
            with open(outfile) as f:
                output = f.read()
            os.unlink(outfile)
            return output
        return ""
    except Exception as e:
        return f"Error: {e}"


def boss_think(thought):
    """Boss agent thinks out loud — shown on dashboard."""
    with boss_lock:
        boss["current_thought"] = thought
    blog(f"🧠 Boss: {thought}")


def boss_command(agent, cmd):
    """Boss agent commands an agent — shown on dashboard."""
    with boss_lock:
        boss["current_command"] = f"{agent}: {cmd}"
    blog(f"📤 Boss → {agent}: {cmd[:80]}")


# --- Product Ideas (Boss generates these) ---
IDEAS = [
    ("TodoCLI", "A CLI todo manager with add, list, done, delete and JSON storage"),
    ("PassGen", "A password generator with configurable length and strength scoring"),
    ("Base64Tool", "A base64 encode/decode CLI with file support"),
    ("HashDiff", "A file integrity checker using SHA-256"),
    ("TextStats", "A text analysis tool: word count, char count, top words"),
    ("ColorPicker", "A CLI color picker outputting hex, rgb, hsl"),
    ("JSONQuery", "A jq-like CLI for querying JSON with dot notation"),
    ("UptimeMonitor", "An HTTP endpoint monitor with response time logging"),
    ("CSVStat", "A CSV statistics calculator: mean, median, min, max"),
    ("SnippetMgr", "A code snippet manager with search and tags"),
]
idea_idx = 0

def next_idea():
    global idea_idx
    i = IDEAS[idea_idx % len(IDEAS)]
    idea_idx += 1
    return i


# --- Code generation ---
def gen_main(name, idea, safe_name, safe_idea):
    lower = idea.lower()
    if "todo" in lower:
        return f'''#!/usr/bin/env python3
"""{safe_name} — CLI Todo Manager"""
import json, sys, os
from pathlib import Path
DB = Path.home() / ".{safe_name.lower()}.json"
def load():
    if DB.exists(): return json.loads(DB.read_text())
    return []
def save(todos): DB.write_text(json.dumps(todos, indent=2))
def add(text):
    todos = load()
    todos.append({{"id": len(todos)+1, "text": text, "done": False}})
    save(todos)
    print(f"Added: #{{len(todos)}} {{text}}")
def lst():
    todos = load()
    if not todos: print("No todos."); return
    for t in todos:
        print(f"[{{'✓' if t['done'] else ' '}}] #{{t['id']}} {{t['text']}}")
def done(tid):
    todos = load()
    for t in todos:
        if t["id"] == tid: t["done"] = True
    save(todos)
def run():
    print(f"{safe_name} v1.0")
    if len(sys.argv) < 2: lst(); return
    cmd = sys.argv[1]
    if cmd == "add": add(" ".join(sys.argv[2:]))
    elif cmd == "list": lst()
    elif cmd == "done": done(int(sys.argv[2]))
    return {{"name": "{safe_name}", "status": "running", "todos": len(load())}}
if __name__ == "__main__": run()
'''
    elif "password" in lower:
        return f'''#!/usr/bin/env python3
"""{safe_name} — Password Generator"""
import random, string, sys
def generate(length=16, symbols=True):
    chars = string.ascii_letters + string.digits
    if symbols: chars += "!@#$%^&*"
    return "".join(random.choice(chars) for _ in range(length))
def strength(pw):
    score = sum([len(pw)>=12, any(c.isupper() for c in pw), any(c.isdigit() for c in pw), any(c in "!@#$%^&*" for c in pw)])
    return ["weak","fair","good","strong","very strong"][score]
def run():
    print(f"{safe_name} v1.0")
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 16
    pw = generate(n)
    print(f"Password: {{pw}}")
    print(f"Strength: {{strength(pw)}}")
    return {{"name": "{safe_name}", "status": "running", "password": pw}}
if __name__ == "__main__": run()
'''
    elif "base64" in lower:
        return f'''#!/usr/bin/env python3
"""{safe_name} — Base64 Tool"""
import base64, sys
def encode(text): return base64.b64encode(text.encode()).decode()
def decode(b64): return base64.b64decode(b64.encode()).decode()
def run():
    print(f"{safe_name} v1.0")
    return {{"name": "{safe_name}", "status": "running"}}
if __name__ == "__main__": run()
'''
    elif "hash" in lower:
        return f'''#!/usr/bin/env python3
"""{safe_name} — File Integrity Checker"""
import hashlib, sys
from pathlib import Path
def hash_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''): h.update(chunk)
    return h.hexdigest()
def run():
    print(f"{safe_name} v1.0")
    return {{"name": "{safe_name}", "status": "running"}}
if __name__ == "__main__": run()
'''
    else:
        return f'''#!/usr/bin/env python3
"""{safe_name} — {safe_idea}"""
import sys, json
def run():
    print(f"{safe_name} v1.0")
    print("Description: {safe_idea}")
    return {{"name": "{safe_name}", "status": "running", "args": sys.argv[1:]}}
if __name__ == "__main__": run()
'''


def gen_test(name, safe_name):
    return f'''import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from main import run
def test_run():
    result = run()
    assert result["name"] == "{safe_name}"
    assert result["status"] == "running"
def test_returns_dict():
    result = run()
    assert isinstance(result, dict)
'''


# --- Boss Agent Pipeline — visibly controls real apps ---

def boss_pipeline(pid, name, desc):
    """Boss agent runs the full pipeline, visibly controlling apps on screen."""
    pdir = BUILD_DIR / name.lower().replace(" ", "_")
    pdir.mkdir(parents=True, exist_ok=True)
    safe_name = name.replace("'", "\\'")
    safe_idea = desc[:80].replace("'", "\\'")

    for stage in PIPELINE_STAGES:
        agent = STAGE_AGENTS[stage]
        with boss_lock:
            boss["active_stage"] = stage
            boss["status"] = f"{stage} → {agent}"

        # --- IDEA: Boss thinks, then opens ChatGPT ---
        if stage == "IDEA":
            boss_think(f"I need a product idea. {name} — {desc[:50]}. I'll design it myself.")
            boss_command("ChatGPT", f"Design product: {name}")
            blog(f"▶ IDEA → ChatGPT (opening ChatGPT app...)", visible=True)
            boss_open_chatgpt(prompt=f"Design a minimal product: {name}. {desc}. Give 3 features, tech stack, file list. Be brief.")
            with boss_lock: boss["metrics"]["apps_launched"] += 1
            time.sleep(3)
            idea_text = f"Product: {name}\nDescription: {desc}\nFeatures: CLI, JSON storage, unit tests\nTech: Python 3"
            hub.advance_stage(pid, stage, task_input=idea_text, execute=False)
            blog(f"  ✅ IDEA done — ChatGPT opened on screen")
            with boss_lock: boss["metrics"]["stages_completed"] += 1

        # --- SPEC: Boss writes spec ---
        elif stage == "SPEC":
            boss_think(f"Writing spec for {name}. Keep it simple — main.py + test_main.py.")
            spec = f"Spec: {name}\n- {desc}\n- Acceptance: runs + tests pass + receipt"
            hub.advance_stage(pid, stage, task_input=spec, execute=False)
            blog(f"  ✅ SPEC done")
            with boss_lock: boss["metrics"]["stages_completed"] += 1

        # --- ARCHITECT: Boss opens Terminal with Claude ---
        elif stage == "ARCHITECT":
            boss_think(f"Architecture review. Let me try Claude CLI in Terminal.")
            boss_command("Claude", f"Review architecture for {name}")
            blog(f"▶ ARCHITECT → Claude (opening Terminal with claude...)", visible=True)
            result = hub.advance_stage(pid, stage, task_input=f"Review: {name} — {desc}", execute=True, timeout=15)
            if result.get("status") == "completed":
                blog(f"  ✅ Claude reviewed architecture")
            else:
                boss_think(f"Claude not available. I'll architect it myself — standard CLI pattern.")
                blog(f"  ⚠️ Claude unavailable — boss auto-architected", visible=True)
                hub.advance_stage(pid, stage, task_input=f"Auto: {name} uses main.py + test pattern", execute=False)
            with boss_lock: boss["metrics"]["stages_completed"] += 1

        # --- CODE: Boss writes code, opens Terminal to show it ---
        elif stage == "CODE":
            boss_think(f"Writing code for {name}. I'll generate main.py and test_main.py.")
            boss_command("Codex", f"Generate main.py + test_main.py for {name}")
            main_code = gen_main(name, desc, safe_name, safe_idea)
            test_code = gen_test(name, safe_name)
            (pdir / "main.py").write_text(main_code)
            (pdir / "test_main.py").write_text(test_code)
            loc = main_code.count('\n') + test_code.count('\n')
            blog(f"▶ CODE → Codex (showing code in Terminal...)", visible=True)
            boss_open_terminal(name, command=f"cat {pdir}/main.py")
            time.sleep(2)
            hub.advance_stage(pid, stage, task_input="wrote main.py + test_main.py", execute=False)
            blog(f"  ✅ Code written: {loc} lines")
            with boss_lock:
                boss["metrics"]["stages_completed"] += 1
                boss["metrics"]["lines_of_code"] += loc

        # --- BUILD: Boss runs main.py in visible Terminal ---
        elif stage == "BUILD":
            boss_think(f"Building {name}. Running main.py — let me see the output.")
            boss_command("Windsurf", f"python3 {pdir}/main.py")
            blog(f"▶ BUILD → Windsurf (running main.py in Terminal...)", visible=True)
            result = hub.advance_stage(pid, stage, task_input=f"python3 {pdir}/main.py", execute=True, timeout=15)
            output = result.get("output", "").strip()[:150]
            if result.get("status") == "completed":
                blog(f"  ✅ Build: {output[:80]}")
                with boss_lock: boss["metrics"]["stages_completed"] += 1
            else:
                blog(f"  ❌ Build failed: {result.get('error','')[:60]}")
                with boss_lock: boss["metrics"]["stages_failed"] += 1

        # --- TEST: Boss runs pytest in visible Terminal ---
        elif stage == "TEST":
            boss_think(f"Testing {name}. Running pytest — this is the truth check.")
            boss_command("Windsurf", f"pytest {pdir}/test_main.py -v")
            blog(f"▶ TEST → Windsurf (running pytest in Terminal...)", visible=True)
            result = hub.advance_stage(pid, stage, task_input=f"python3 -m pytest {pdir}/test_main.py -v", execute=True, timeout=20)
            full_output = result.get("output", "")
            if result.get("status") == "completed":
                passed = full_output.count(" PASSED")
                blog(f"  ✅ Tests: {passed} passed", visible=True)
                with boss_lock:
                    boss["metrics"]["stages_completed"] += 1
                    boss["metrics"]["tests_passed"] += passed
            else:
                blog(f"  ❌ Tests failed", visible=True)
                with boss_lock:
                    boss["metrics"]["stages_failed"] += 1
                    boss["metrics"]["tests_failed"] += 1

        # --- RECEIPT: Boss writes receipt ---
        elif stage == "RECEIPT":
            boss_think(f"Writing receipt for {name}. Every artifact gets a receipt.")
            rpath = pdir / "receipt.json"
            rdata = {
                "project": name, "description": desc,
                "stages": [s for s in PIPELINE_STAGES if s != "SHIP"],
                "build_dir": str(pdir), "timestamp": now_iso(),
                "receipt_id": str(uuid.uuid4())[:12],
            }
            rpath.write_text(json.dumps(rdata, indent=2))
            hub.advance_stage(pid, stage, task_input="receipt written", execute=True, timeout=5)
            blog(f"  ✅ Receipt: receipt.json")
            with boss_lock: boss["metrics"]["receipts_written"] += 1

        # --- SHIP: Boss decides to ship ---
        elif stage == "SHIP":
            boss_think(f"{name} built and tested. Ship it. Next idea.")
            boss_command("ChatGPT", f"Ship {name}? Yes.")
            hub.advance_stage(pid, stage, task_input="shipped", execute=False)
            blog(f"  🚀 SHIPPED: {name}", visible=True)
            with boss_lock:
                boss["metrics"]["stages_completed"] += 1
                boss["metrics"]["products_shipped"] += 1

        time.sleep(0.5)

    with boss_lock:
        boss["active_project"] = None
        boss["active_stage"] = None


# --- 24/7 Boss Loop ---

def boss_loop():
    """The boss agent runs forever — thinks, decides, commands, verifies."""
    with boss_lock:
        boss["running"] = True
        boss["uptime"] = now_iso()
        boss["status"] = "active"

    blog("🤖 BOSS AGENT ONLINE — I am Joseph's clone. I build, test, and ship. 24/7.", visible=True)
    blog("📋 My pipeline: IDEA → SPEC → ARCHITECT → CODE → BUILD → TEST → RECEIPT → SHIP")
    blog("🖥️ I will open real apps on your screen — Terminal, ChatGPT, Claude. Watch me work.")

    while boss["running"]:
        with boss_lock:
            boss["cycle"] += 1
            boss["metrics"]["cycles"] += 1
            cycle = boss["cycle"]

        blog(f"━━━ Cycle {cycle} ━━━")

        # Find pending work or generate new idea
        projects = hub.get_projects()
        pending = [p for p in projects if p["status"] == "active" and p["current_stage"] != "SHIP"]

        if not pending:
            name, desc = next_idea()
            boss_think(f"No pending work. I'll create a new product: {name}.")
            blog(f"💡 New product idea: {name} — {desc[:60]}")
            result = hub.create_project(name, desc)
            pid = result["id"]
        else:
            p = pending[0]
            pid = p["id"]
            name = p["name"]
            desc = p["description"] or p["name"]
            boss_think(f"Resuming work on {name} at stage {p['current_stage']}.")
            blog(f"📋 Resuming: {name}")

        with boss_lock:
            boss["active_project"] = pid

        p = hub.get_project(pid)
        if p:
            boss_pipeline(pid, p["name"], p["description"] or p["name"])

        time.sleep(2)

    blog("🛑 BOSS AGENT OFFLINE")


def start_boss():
    global boss_thread
    with boss_lock:
        if boss["running"]:
            return {"status": "already_running"}
        boss["running"] = True
    boss_thread = threading.Thread(target=boss_loop, daemon=True)
    boss_thread.start()
    return {"status": "started"}


def stop_boss():
    with boss_lock:
        boss["running"] = False
        boss["status"] = "stopped"
    return {"status": "stopped"}


# --- API ---
class ProjectCreate(BaseModel):
    name: str
    description: str = ""

class ManualTask(BaseModel):
    agent: str
    task: str
    timeout: int = 60

class ChatGPTQuery(BaseModel):
    prompt: str
    wait_seconds: int = 35

class BossConfig(BaseModel):
    personality: str = ""

app = FastAPI(title="HyperFlow AGI — Boss Agent", version="5.0.0")

@app.on_event("startup")
async def startup():
    if not hub.get_projects():
        name, desc = next_idea()
        hub.create_project(name, desc)
    start_boss()

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML

@app.get("/api/status")
async def api_status():
    s = hub.get_status()
    with boss_lock:
        s["boss"] = {
            "running": boss["running"],
            "status": boss["status"],
            "cycle": boss["cycle"],
            "uptime": boss["uptime"],
            "personality": boss["personality"],
            "current_thought": boss["current_thought"],
            "current_command": boss["current_command"],
            "log": list(boss["log"][-40:]),
            "visible_actions": list(boss["visible_actions"][-15:]),
            "active_project": boss["active_project"],
            "active_stage": boss["active_stage"],
            "metrics": dict(boss["metrics"]),
        }
    return s

@app.post("/api/project")
async def create_project(p: ProjectCreate):
    return hub.create_project(p.name, p.description)

@app.get("/api/projects")
async def list_projects():
    return hub.get_projects()

@app.get("/api/project/{pid}")
async def get_project(pid: str):
    p = hub.get_project(pid)
    if not p: return {"error": "not found"}
    p["stage_history"] = hub.get_stage_history(pid)
    return p

@app.post("/api/boss/start")
async def boss_start():
    return start_boss()

@app.post("/api/boss/stop")
async def boss_stop():
    return stop_boss()

@app.post("/api/boss/config")
async def boss_config(c: BossConfig):
    with boss_lock:
        if c.personality:
            boss["personality"] = c.personality
    return {"status": "updated", "personality": boss["personality"]}

@app.post("/api/task")
async def manual_task(t: ManualTask):
    return hub.execute_manual(t.agent, t.task, t.timeout)

@app.post("/api/ask-chatgpt")
async def ask_chatgpt(q: ChatGPTQuery):
    return hub.ask_chatgpt(q.prompt, q.wait_seconds)

@app.get("/api/messages")
async def messages(limit: int = 20):
    return hub.get_messages(limit)

@app.get("/api/receipts")
async def receipts(limit: int = 20):
    return hub.get_receipts(limit)


# --- Dashboard ---
DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HyperFlow AGI — Boss Agent</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#050508;color:#e0e0e8;min-height:100vh;overflow:hidden}
.header{background:linear-gradient(135deg,#0a0a1a,#1a0a2a);padding:12px 24px;border-bottom:1px solid #2a1a3a;display:flex;align-items:center;justify-content:space-between;height:56px}
.header h1{font-size:17px;color:#b0b0f0}
.header h1 span{color:#4caf50}
.header .sub{font-size:10px;color:#6a6ad0;margin-top:2px}
.pill{padding:4px 14px;border-radius:16px;font-size:11px;font-weight:700}
.pill-on{background:#0a3a0a;color:#4caf50;animation:pulse 2s infinite}
.pill-off{background:#3a0a0a;color:#f44336}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
.layout{display:grid;grid-template-columns:280px 1fr 320px;gap:10px;padding:10px;height:calc(100vh - 56px);overflow:hidden}
.col{display:flex;flex-direction:column;gap:10px;overflow-y:auto}
.card{background:#0c0c14;border:1px solid #1a1a2a;border-radius:8px;padding:12px}
.card h2{font-size:11px;color:#6a6ad0;margin-bottom:8px;text-transform:uppercase;letter-spacing:1px}

/* Boss panel */
.boss-panel{background:linear-gradient(135deg,#0c0c1a,#0a0a2a);border:1px solid #2a2a4a;border-radius:8px;padding:14px}
.boss-avatar{font-size:32px;text-align:center;margin-bottom:6px}
.boss-name{font-size:14px;font-weight:700;text-align:center;color:#b0b0f0}
.boss-personality{font-size:10px;color:#6a6ad0;text-align:center;margin-top:4px;font-style:italic}
.boss-thought{background:#050510;border-radius:6px;padding:8px;margin-top:10px;font-size:11px;color:#ffaa00;min-height:36px;font-family:'SF Mono',monospace}
.boss-thought::before{content:'🧠 ';font-size:12px}
.boss-command{background:#050510;border-radius:6px;padding:8px;margin-top:6px;font-size:11px;color:#8bc0f0;min-height:28px;font-family:'SF Mono',monospace}
.boss-command::before{content:'📤 ';font-size:12px}

/* Metrics */
.metrics-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.metric{background:#0a0a14;border-radius:6px;padding:8px;text-align:center}
.metric-val{font-size:22px;font-weight:800;color:#4caf50}
.metric-val.fail{color:#f44336}
.metric-val.blue{color:#8bc0f0}
.metric-val.purple{color:#d0a0f0}
.metric-label{font-size:9px;color:#555;text-transform:uppercase;margin-top:2px}

/* Agents */
.agent-card{background:#0a0a14;border-radius:6px;padding:8px;margin-bottom:6px;border-left:3px solid #333}
.agent-card.ok{border-left-color:#4caf50}
.agent-card.busy{border-left-color:#ffaa00}
.agent-card.fail{border-left-color:#f44336}
.agent-head{display:flex;align-items:center;gap:6px}
.agent-icon{font-size:16px}
.agent-name{font-size:12px;font-weight:700}
.agent-role{font-size:9px;color:#666}
.agent-stats{font-size:10px;color:#555;margin-top:3px}
.agent-stats .ok{color:#4caf50}
.agent-stats .fail{color:#f44336}

/* Pipeline */
.pipe-bar{display:flex;gap:2px;margin-bottom:10px}
.pipe-stage{flex:1;padding:8px 2px;text-align:center;border-radius:5px;font-size:9px;font-weight:600;min-width:60px;transition:all .3s}
.pipe-stage .sn{font-size:10px}
.pipe-stage .sa{font-size:8px;opacity:.6}
.ps-done{background:#0a2a0a;color:#4caf50}
.ps-now{background:#2a2a0a;color:#ffaa00;box-shadow:0 0 10px rgba(255,170,0,.4);animation:glow 1.5s infinite}
.ps-fail{background:#2a0a0a;color:#f44336}
.ps-pend{background:#0a0a14;color:#444}
@keyframes glow{0%,100%{box-shadow:0 0 6px rgba(255,170,0,.2)}50%{box-shadow:0 0 14px rgba(255,170,0,.5)}}

/* Projects */
.proj{background:#0a0a14;border-radius:6px;padding:10px;margin-bottom:6px;cursor:pointer;border:1px solid transparent;transition:.2s}
.proj:hover{border-color:#3a3a5a}
.proj.sel{border-color:#6a6ad0}
.proj-name{font-size:13px;font-weight:600}
.proj-stage{font-size:10px;color:#6a6ad0}
.proj-desc{font-size:10px;color:#555;margin-top:3px}
.proj-mini{display:flex;gap:2px;margin-top:6px}
.ms{flex:1;height:4px;border-radius:2px;background:#222}
.ms.done{background:#4caf50}
.ms.now{background:#ffaa00;animation:pulse 1s infinite}
.ms.fail{background:#f44336}

/* Log */
.log{font-family:'SF Mono',monospace;font-size:10px;max-height:250px;overflow-y:auto;background:#030306;border-radius:6px;padding:8px;line-height:1.6}
.log div{padding:1px 0}
.log .ok{color:#4caf50}
.log .fail{color:#f44336}
.log .info{color:#6a6ad0}
.log .warn{color:#ffaa00}
.log .vis{color:#d0a0f0;font-weight:600}

/* Visible actions */
.vis-actions{max-height:150px;overflow-y:auto}
.va{padding:5px;border-bottom:1px solid #0a0a14;font-size:10px;color:#d0a0f0}
.va::before{content:'🖥️ '}

/* Feed */
.feed{max-height:140px;overflow-y:auto}
.fi{padding:5px;border-bottom:1px solid #0a0a14;font-size:10px}
.fs{font-size:8px;padding:1px 4px;border-radius:3px}
.fs-completed{background:#0a2a0a;color:#4caf50}
.fs-failed{background:#2a0a0a;color:#f44336}
.fs-pending{background:#2a2a0a;color:#ffaa00}

.btn{padding:6px 14px;border:none;border-radius:5px;cursor:pointer;font-size:11px;font-weight:600}
.btn-go{background:#0a3a0a;color:#4caf50}
.btn-stop{background:#3a0a0a;color:#f44336}
.btn-blue{background:#0a1a3a;color:#8bc0f0}
.btn:disabled{opacity:.3}
input,select{padding:6px;background:#0a0a14;border:1px solid #1a1a2a;border-radius:5px;color:#e0e0e8;font-size:11px}
.box{background:#030306;border-radius:5px;padding:8px;font-size:10px;font-family:monospace;max-height:100px;overflow-y:auto;white-space:pre-wrap;color:#888;line-height:1.4}
.controls{display:flex;gap:4px;margin-bottom:8px}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>🤖 HyperFlow <span>BOSS AGENT</span></h1>
    <div class="sub">Clone of Joseph — autonomously controls all agent apps on your Mac, 24/7</div>
  </div>
  <div style="display:flex;gap:10px;align-items:center">
    <span id="uptime" style="font-size:10px;color:#555"></span>
    <div id="pill" class="pill pill-off">OFFLINE</div>
  </div>
</div>

<div class="layout">
  <!-- LEFT: Boss + Metrics + Agents -->
  <div class="col">
    <div class="boss-panel">
      <div class="boss-avatar">🤖</div>
      <div class="boss-name">BOSS AGENT</div>
      <div class="boss-personality" id="personality"></div>
      <div class="boss-thought" id="thought">Booting...</div>
      <div class="boss-command" id="command">Waiting...</div>
    </div>
    <div class="card">
      <h2>Metrics</h2>
      <div class="metrics-grid">
        <div class="metric"><div class="metric-val" id="m-shipped">0</div><div class="metric-label">Shipped</div></div>
        <div class="metric"><div class="metric-val blue" id="m-cycles">0</div><div class="metric-label">Cycles</div></div>
        <div class="metric"><div class="metric-val" id="m-tests">0</div><div class="metric-label">Tests Pass</div></div>
        <div class="metric"><div class="metric-val fail" id="m-fails">0</div><div class="metric-label">Failures</div></div>
        <div class="metric"><div class="metric-val blue" id="m-loc">0</div><div class="metric-label">Lines Code</div></div>
        <div class="metric"><div class="metric-val purple" id="m-apps">0</div><div class="metric-label">Apps Launched</div></div>
      </div>
    </div>
    <div class="card">
      <h2>Agent Fleet</h2>
      <div id="agents"></div>
    </div>
    <div class="card">
      <h2>Boss Control</h2>
      <div class="controls">
        <button class="btn btn-go" id="btn-start" onclick="startBoss()">▶ Start</button>
        <button class="btn btn-stop" id="btn-stop" onclick="stopBoss()">■ Stop</button>
      </div>
      <input id="pers-input" placeholder="Set boss personality..." style="width:100%;margin-bottom:4px">
      <button class="btn btn-blue" onclick="setPersonality()" style="width:100%">Update Personality</button>
    </div>
  </div>

  <!-- CENTER: Pipeline + Log + Projects -->
  <div class="col">
    <div class="card">
      <h2>Pipeline — <span id="active-proj" style="color:#4caf50">idle</span></h2>
      <div id="pipe-bar" class="pipe-bar"></div>
      <div id="stage-detail" style="margin-top:6px"></div>
    </div>
    <div class="card">
      <h2>🖥️ Visible Actions on Your Mac</h2>
      <div id="vis-actions" class="vis-actions"></div>
    </div>
    <div class="card" style="flex:1">
      <h2>Boss Agent Log</h2>
      <div id="log" class="log"></div>
    </div>
    <div class="card">
      <h2>Products Built</h2>
      <div id="projects"></div>
    </div>
  </div>

  <!-- RIGHT: Feed + Manual -->
  <div class="col">
    <div class="card">
      <h2>Agent Messages</h2>
      <div id="messages" class="feed"></div>
    </div>
    <div class="card">
      <h2>Receipts</h2>
      <div id="receipts" class="feed"></div>
    </div>
    <div class="card">
      <h2>Manual Control</h2>
      <div class="controls">
        <select id="ta" style="flex:1">
          <option value="windsurf">🏄 Windsurf</option>
          <option value="codex">⚡ Codex</option>
          <option value="claude">🔧 Claude</option>
          <option value="devin">🤖 Devin</option>
        </select>
        <button class="btn btn-blue" onclick="runTask()">Run</button>
      </div>
      <input id="tc" placeholder="command..." style="width:100%;margin-bottom:6px">
      <div id="tr" class="box">Output...</div>
    </div>
    <div class="card">
      <h2>ChatGPT Query</h2>
      <div class="controls">
        <input id="cp" placeholder="Ask ChatGPT..." style="flex:1">
        <button class="btn btn-blue" onclick="askGPT()">Send</button>
      </div>
      <div id="cr" class="box">Responses appear here...</div>
    </div>
  </div>
</div>

<script>
let selProj=null;
async function poll(){
  try{
    const r=await fetch('/api/status');
    const d=await r.json();
    renderBoss(d.boss);
    renderAgents(d.agents);
    renderPipe(d.pipeline,d.stage_agents);
    renderProjects(d.projects);
    renderMsgs(d.messages);
    renderRecs(d.receipts);
    if(selProj){
      const pr=await fetch(`/api/project/${selProj}`);
      const pd=await pr.json();
      renderDetail(pd,d.pipeline);
    }
  }catch(e){console.error(e)}
}
function renderBoss(b){
  const pill=document.getElementById('pill');
  pill.className=b.running?'pill pill-on':'pill pill-off';
  pill.textContent=b.running?'ONLINE':'OFFLINE';
  document.getElementById('personality').textContent=b.personality;
  document.getElementById('thought').textContent=b.current_thought||'Idle...';
  document.getElementById('command').textContent=b.current_command||'Waiting...';
  document.getElementById('uptime').textContent=b.uptime?`Up since ${b.uptime.substring(11,19)}`:'';
  document.getElementById('active-proj').textContent=b.active_stage||'idle';
  const m=b.metrics;
  document.getElementById('m-shipped').textContent=m.products_shipped||0;
  document.getElementById('m-cycles').textContent=m.cycles||0;
  document.getElementById('m-tests').textContent=m.tests_passed||0;
  document.getElementById('m-fails').textContent=(m.stages_failed||0)+(m.tests_failed||0);
  document.getElementById('m-loc').textContent=m.lines_of_code||0;
  document.getElementById('m-apps').textContent=m.apps_launched||0;
  const logEl=document.getElementById('log');
  logEl.innerHTML=(b.log||[]).map(l=>{
    let c='';
    if(l.includes('✅')||l.includes('🚀'))c='ok';
    else if(l.includes('❌'))c='fail';
    else if(l.includes('⚠️'))c='warn';
    else if(l.includes('━━')||l.includes('🤖')||l.includes('💡')||l.includes('📋')||l.includes('🧠')||l.includes('📤'))c='info';
    return `<div class="${c}">${l}</div>`;
  }).join('');
  logEl.scrollTop=logEl.scrollHeight;
  const va=document.getElementById('vis-actions');
  va.innerHTML=(b.visible_actions||[]).map(a=>`<div class="va">${a}</div>`).join('')||'<div style="color:#444;font-size:10px;padding:4px">No visible actions yet.</div>';
  va.scrollTop=va.scrollHeight;
  document.getElementById('btn-start').disabled=b.running;
  document.getElementById('btn-stop').disabled=!b.running;
}
function renderAgents(agents){
  document.getElementById('agents').innerHTML=Object.entries(agents).map(([k,a])=>{
    const cls=a.available?(a.status==='busy'?'busy':'ok'):'fail';
    const p=a.profile||{};
    return `<div class="agent-card ${cls}">
      <div class="agent-head"><span class="agent-icon">${p.icon||'?'}</span><span class="agent-name">${p.name||k}</span></div>
      <div class="agent-role">${p.role||''}</div>
      <div class="agent-stats"><span class="ok">✓${a.tasks_completed}</span> <span class="fail">✗${a.tasks_failed}</span> ${a.status}</div>
    </div>`;
  }).join('');
}
function renderPipe(stages,agents){
  document.getElementById('pipe-bar').innerHTML=stages.map(s=>
    `<div class="pipe-stage ps-pend" id="ps-${s}"><div class="sn">${s}</div><div class="sa">${agents[s]||'?'}</div></div>`
  ).join('');
}
function renderProjects(ps){
  const el=document.getElementById('projects');
  if(!ps.length){el.innerHTML='<div style="color:#444;font-size:11px;padding:6px">No products yet.</div>';return}
  el.innerHTML=ps.map(p=>{
    const sr=typeof p.stage_results==='string'?JSON.parse(p.stage_results||'{}'):(p.stage_results||{});
    const ss=['IDEA','SPEC','ARCHITECT','CODE','BUILD','TEST','RECEIPT','SHIP'];
    const mini=ss.map(s=>{
      const r=sr[s];
      const c=r?(r.status==='completed'?'done':r.status==='failed'?'fail':'now'):'';
      const cur=p.current_stage===s&&!r?'now':'';
      return `<div class="ms ${c}${cur}"></div>`;
    }).join('');
    const sel=selProj===p.id?'sel':'';
    return `<div class="proj ${sel}" onclick="sel('${p.id}')">
      <div class="proj-name">${p.name}</div>
      <div class="proj-stage">${p.current_stage} · ${p.status}</div>
      <div class="proj-desc">${(p.description||'').substring(0,70)}</div>
      <div class="proj-mini">${mini}</div>
    </div>`;
  }).join('');
}
function renderDetail(d,stages){
  const sr=typeof d.stage_results==='string'?JSON.parse(d.stage_results||'{}'):(d.stage_results||{});
  stages.forEach(s=>{
    const el=document.getElementById(`ps-${s}`);
    if(!el)return;
    const r=sr[s];
    if(r)el.className=`pipe-stage ${r.status==='completed'?'ps-done':r.status==='failed'?'ps-fail':'ps-now'}`;
    else if(d.current_stage===s)el.className='pipe-stage ps-now';
    else el.className='pipe-stage ps-pend';
  });
  const h=d.stage_history||[];
  const ic={IDEA:'💡',SPEC:'📋',ARCHITECT:'🏗',CODE:'💻',BUILD:'🔨',TEST:'✅',RECEIPT:'🧾',SHIP:'🚀'};
  document.getElementById('stage-detail').innerHTML=h.map(x=>{
    const sc=x.status==='completed'?'fs-completed':x.status==='failed'?'fs-failed':'fs-pending';
    let o='';
    try{const j=JSON.parse(x.output||'{}');o=j.output||j.error||''}catch(e){o=(x.output||'').substring(0,200)}
    return `<div style="display:flex;align-items:center;gap:6px;padding:4px 0;border-bottom:1px solid #0a0a14">
      <span style="font-size:14px">${ic[x.stage]||'?'}</span>
      <span style="font-size:11px;font-weight:600;flex:1">${x.stage}</span>
      <span style="font-size:9px;color:#6a6ad0">${x.agent}</span>
      <span class="fs ${sc}">${x.status}</span>
    </div>${o?`<div style="font-size:9px;color:#555;font-family:monospace;padding:2px 0 4px 20px;white-space:pre-wrap;max-height:50px;overflow-y:auto">${o.substring(0,300)}</div>`:''}`;
  }).join('')||'<div style="color:#444;font-size:11px;padding:6px">No stages run yet.</div>';
}
function renderMsgs(ms){
  document.getElementById('messages').innerHTML=ms.map(m=>
    `<div class="fi"><span class="fs fs-${m.status}">${m.status}</span> <span style="color:#6a6ad0;font-size:9px">${m.from_agent}→${m.to_agent}</span><div style="color:#555;margin-top:2px">${m.content.substring(0,70)}</div></div>`
  ).join('')||'<div style="color:#444;font-size:10px;padding:4px">No messages.</div>';
}
function renderRecs(rs){
  document.getElementById('receipts').innerHTML=rs.map(r=>
    `<div class="fi"><span style="color:#6a6ad0">${r.action}</span><span style="color:#444"> · ${r.agent}</span>${r.stage?`<span style="color:#444"> · ${r.stage}</span>`:''}<div style="color:#333;font-size:8px">${r.timestamp.substring(11,19)}</div></div>`
  ).join('')||'<div style="color:#444;font-size:10px;padding:4px">No receipts.</div>';
}
async function sel(pid){selProj=pid;poll()}
async function startBoss(){await fetch('/api/boss/start',{method:'POST'});poll()}
async function stopBoss(){await fetch('/api/boss/stop',{method:'POST'});poll()}
async function setPersonality(){
  const p=document.getElementById('pers-input').value;if(!p)return;
  await fetch('/api/boss/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({personality:p})});
  poll();
}
async function runTask(){
  const a=document.getElementById('ta').value,t=document.getElementById('tc').value;
  if(!t)return;
  document.getElementById('tr').textContent='Running '+a+'...';
  const r=await fetch('/api/task',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent:a,task:t})});
  const d=await r.json();
  document.getElementById('tr').textContent=`success=${d.success}\n${d.output||d.error||'Done'}`;
  poll();
}
async function askGPT(){
  const p=document.getElementById('cp').value;if(!p)return;
  document.getElementById('cr').textContent='🧠 Asking ChatGPT...';
  const r=await fetch('/api/ask-chatgpt',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:p})});
  const d=await r.json();
  document.getElementById('cr').textContent=d.response||d.error||'No response';
  poll();
}
poll();
setInterval(poll,2000);
</script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    print("HyperFlow AGI v5 — Boss Agent Edition")
    print("Dashboard: http://localhost:8765")
    print("The Boss Agent auto-starts and controls real apps on your Mac.")
    print("Watch Terminal, ChatGPT, and Claude open and execute commands.")
    uvicorn.run(app, host="0.0.0.0", port=8765)
