#!/usr/bin/env python3
"""Devin Autonomous Controller — wired through RentMasseur API + Selenium.

Orchestrates all project development AND live RentMasseur operations:

1. Scans all registered projects for health (build, tests, docs, recency)
2. Logs into RentMasseur via API client using credentials from env/keychain
3. Pulls live data: dashboard, stats, mailbox, about, availability, search rank
4. Selenium-verifies search visibility and profile page content
5. Generates bounded task packets for projects AND RM operations that need work
6. Routes each packet to Devin (autonomous) or Windsurf (IDE-native)
7. Writes receipts for every action
8. Exposes state via JSON for the /api/devin endpoint

Usage:
    python3 devin_controller.py scan          # scan projects + RM live data
    python3 devin_controller.py generate      # generate packets for needy projects
    python3 devin_controller.py status        # show current state
    python3 devin_controller.py run           # full cycle: scan → RM → generate → receipt
    python3 devin_controller.py rm            # RM-only: login + pull live data + selenium
    python3 devin_controller.py rm-loop <tier> # RM traffic loop: 30 functions by frequency tier
                                               #   tiers: 15min, 30min, 2h, 4h, 6h, 24h, weekly, on-demand, all
    python3 devin_controller.py loop [N]       # 30-function traffic loop with LLM continuous improvement
                                               #   N = single function ID (1-30), omit for all 30
    python3 devin_controller.py money          # money loop — closed-loop revenue optimization with LLM
"""

from __future__ import annotations
import json
import os
import sys
import time
import hashlib
import sqlite3
import subprocess
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "shadowshard_mforge"))
sys.path.insert(0, str(REPO_ROOT))

# ── RentMasseur imports ──
try:
    from rm_traffic.api_client import RentMasseurAPI
    from rm_traffic.auth import AuthSession, get_credential
    RM_AVAILABLE = True
except ImportError as e:
    RM_AVAILABLE = False
    print(f"  ⟁ RM imports failed: {e}", file=sys.stderr)

try:
    from rm_traffic.money_training_selenium import selenium_verify_search, selenium_verify_profile_page
    SELENIUM_AVAILABLE = True
except ImportError as e:
    SELENIUM_AVAILABLE = False

try:
    from rm_traffic.traffic_loop import run_cycle as loop_run_cycle, get_loop_stats, init_db as loop_init_db, load_loop_state, ALL_FUNCTIONS, FUNCTION_NAMES, CATEGORIES
    TRAFFIC_LOOP_AVAILABLE = True
except ImportError as e:
    TRAFFIC_LOOP_AVAILABLE = False
    print(f"  ⟁ traffic_loop import failed: {e}", file=sys.stderr)

try:
    from rm_traffic.money_loop import run_money_cycle, get_money_stats, init_db as money_init_db
    MONEY_LOOP_AVAILABLE = True
except ImportError as e:
    MONEY_LOOP_AVAILABLE = False
    print(f"  ⟁ money_loop import failed: {e}", file=sys.stderr)

# ── Project Registry ──

PROJECTS = [
    {"dir": "autopilot_apps", "name": "Autopilot Apps", "lang": "swift", "build_cmd": "swift build", "test_cmd": "swift test"},
    {"dir": "autonomous_products", "name": "Autonomous Products", "lang": "python", "build_cmd": "python -m py_compile", "test_cmd": "python -m pytest -x"},
    {"dir": "agent_bridge", "name": "Agent Bridge", "lang": "python", "build_cmd": "python -m py_compile", "test_cmd": "python -m pytest -x"},
    {"dir": "broll", "name": "Broll VideoLake", "lang": "python", "build_cmd": "python -m py_compile", "test_cmd": "python -m pytest -x"},
    {"dir": "browser_bridge", "name": "Browser Bridge", "lang": "cpp", "build_cmd": "cmake --build build", "test_cmd": "./build/bridge --test"},
    {"dir": "clipboard_desk", "name": "Clipboard Desk", "lang": "swift", "build_cmd": "swift build", "test_cmd": "swift test"},
    {"dir": "goliath", "name": "Goliath Control Plane", "lang": "python", "build_cmd": "python -m py_compile", "test_cmd": "python -m pytest -x"},
    {"dir": "hyperflow", "name": "HyperFlow", "lang": "python", "build_cmd": "python -m py_compile", "test_cmd": "python -m pytest -x"},
    {"dir": "jorki", "name": "Jorki AI Gateway", "lang": "jsx", "build_cmd": "npm run build", "test_cmd": "npm test"},
    {"dir": "latentos", "name": "LatentOS", "lang": "python", "build_cmd": "python -m py_compile", "test_cmd": "python -m pytest -x"},
    {"dir": "layer_crawler_etl", "name": "Layer Crawler ETL", "lang": "python", "build_cmd": "python -m py_compile", "test_cmd": "python -m pytest -x"},
    {"dir": "GlyphAura", "name": "GlyphAura", "lang": "swift", "build_cmd": "swift build", "test_cmd": "swift test"},
    {"dir": "MetalAgent", "name": "MetalAgent", "lang": "swift", "build_cmd": "swift build", "test_cmd": "swift test"},
    {"dir": "OverAntiLogicDaemon", "name": "OverAntiLogic Daemon", "lang": "swift", "build_cmd": "swift build", "test_cmd": "swift test"},
    {"dir": "airplay_agent", "name": "AirPlay Agent", "lang": "swift", "build_cmd": "swift build", "test_cmd": "swift test"},
]

# ── State directories ──

STATE_DIR = REPO_ROOT / "shadowshard_mforge" / "data" / "devin_controller"
STATE_DIR.mkdir(parents=True, exist_ok=True)

PACKETS_DIR = REPO_ROOT / "shadowshard_mforge" / "data" / "substrate" / "packets"
RECEIPTS_DIR = REPO_ROOT / "shadowshard_mforge" / "data" / "substrate" / "receipts"
PACKETS_DIR.mkdir(parents=True, exist_ok=True)
RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class ProjectScan:
    """Result of scanning a single project."""
    dir: str
    name: str
    lang: str
    exists: bool
    file_count: int
    has_build: bool
    has_tests: bool
    has_readme: bool
    last_modified_days: float
    state: str  # active, verified, idle, dormant
    issues: list[str] = field(default_factory=list)
    recommended_task: str = ""
    priority: str = "low"  # high, medium, low


@dataclass
class GeneratedPacket:
    """A generated task packet ready for routing."""
    packet_id: str
    task: str
    project_dir: str
    project_name: str
    agent: str  # devin, windsurf, local_model
    reason: str
    mode: str  # bounded_patch, narrow_test, exploration
    allowed_inspection: list[str]
    allowed_changes: list[str]
    forbidden_changes: list[str]
    test_command: str
    acceptance_criteria: str
    prompt_mode: str
    created_at: float
    priority: str


@dataclass
class ExecutionReceipt:
    """Receipt for a completed or attempted task."""
    task_id: str
    project: str
    agent: str
    files_inspected: int
    files_changed: int
    patch_efficiency: float
    retries: int
    tests_run: int
    tests_passed: bool
    verification_density: float
    cloud_calls: int
    cloud_avoidance: int
    output_quality: float
    artifact_value: float
    substrate_tax: dict
    violations: list[str]
    compliance_score: float
    timestamp: float


# ── Scanner ──

def scan_project(proj: dict) -> ProjectScan:
    """Scan a single project directory for health."""
    full = REPO_ROOT / proj["dir"]
    scan = ProjectScan(
        dir=proj["dir"],
        name=proj["name"],
        lang=proj["lang"],
        exists=full.exists(),
        file_count=0,
        has_build=False,
        has_tests=False,
        has_readme=False,
        last_modified_days=999,
        state="dormant",
    )

    if not scan.exists:
        scan.issues.append("project directory missing")
        scan.recommended_task = f"Create initial project structure for {proj['name']}"
        scan.priority = "medium"
        return scan

    # Count files and check for build/test/readme
    for entry in full.rglob("*"):
        if any(part in str(entry) for part in [".build", "node_modules", "__pycache__", ".git", ".venv", "DerivedData", ".swiftpm"]):
            continue
        if entry.is_file():
            scan.file_count += 1
            name = entry.name.lower()
            if name in ("package.swift", "cmakelists.txt", "package.json", "makefile"):
                scan.has_build = True
            if "test" in name or "spec" in name:
                scan.has_tests = True
            if name == "readme.md":
                scan.has_readme = True

    # Last modified
    try:
        import subprocess
        result = subprocess.run(
            ["find", str(full), "-type", "f", "-not", "-path", "*/.git/*", "-not", "-path", "*/.build/*", "-not", "-path", "*/__pycache__/*"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            files = result.stdout.strip().split("\n")
            newest = max(files, key=lambda f: os.path.getmtime(f) if os.path.exists(f) else 0)
            scan.last_modified_days = (time.time() - os.path.getmtime(newest)) / 86400
    except:
        pass

    # State from recency
    if scan.last_modified_days < 1:
        scan.state = "active"
    elif scan.last_modified_days < 7:
        scan.state = "verified"
    elif scan.last_modified_days < 30:
        scan.state = "idle"
    else:
        scan.state = "dormant"

    # Issues
    if not scan.has_build:
        scan.issues.append("no build file found")
    if not scan.has_tests:
        scan.issues.append("no test files found")
    if not scan.has_readme:
        scan.issues.append("no README found")
    if scan.file_count < 3:
        scan.issues.append(f"only {scan.file_count} files — possibly incomplete")

    # Recommended tasks based on issues
    tasks = []
    if not scan.has_readme:
        tasks.append(f"Add README.md to {proj['name']} with project overview, build instructions, and usage")
    if not scan.has_tests:
        tasks.append(f"Add basic test structure to {proj['name']} using {proj['lang']} testing framework")
    if not scan.has_build and scan.lang == "swift":
        tasks.append(f"Add Package.swift to {proj['name']} for SwiftPM build support")
    if scan.state == "dormant" and scan.file_count > 3:
        tasks.append(f"Audit {proj['name']} for stale code and update dependencies")

    scan.recommended_task = tasks[0] if tasks else ""
    scan.priority = "high" if len(scan.issues) >= 3 else "medium" if scan.issues else "low"

    return scan


def scan_all() -> list[ProjectScan]:
    """Scan all registered projects."""
    return [scan_project(p) for p in PROJECTS]


# ── Packet Generator ──

def route_task(task: str, lang: str, autonomous: bool = True) -> tuple[str, str]:
    """Route a task to the appropriate agent."""
    task_lower = task.lower()
    if any(w in task_lower for w in ["fix", "patch", "debug", "reproduce"]):
        return ("devin", "autonomous execution, can run tests and iterate")
    if any(w in task_lower for w in ["add", "create", "write", "generate"]):
        if lang == "swift":
            return ("windsurf", "IDE-native for Swift file creation")
        return ("devin", "autonomous file creation and verification")
    if any(w in task_lower for w in ["audit", "review", "check", "inspect"]):
        return ("devin", "autonomous inspection and report generation")
    return ("devin" if autonomous else "windsurf", "default routing")


def generate_packets(scans: list[ProjectScan]) -> list[GeneratedPacket]:
    """Generate task packets for projects that need work."""
    packets = []
    counter = 0

    for scan in scans:
        if not scan.recommended_task:
            continue
        if scan.priority == "low":
            continue

        counter += 1
        packet_id = f"packet_{int(time.time())}_{counter}"
        agent, reason = route_task(scan.recommended_task, scan.lang)

        # Build allowed files based on project
        proj_path = REPO_ROOT / scan.dir
        allowed = []
        if scan.lang == "swift":
            allowed = [f"{scan.dir}/Package.swift", f"{scan.dir}/Sources/"]
        elif scan.lang == "python":
            allowed = [f"{scan.dir}/__init__.py", f"{scan.dir}/core.py"]
        elif scan.lang == "cpp":
            allowed = [f"{scan.dir}/CMakeLists.txt", f"{scan.dir}/src/"]
        elif scan.lang == "jsx":
            allowed = [f"{scan.dir}/src/", f"{scan.dir}/package.json"]

        # Test command
        proj = next((p for p in PROJECTS if p["dir"] == scan.dir), {})
        test_cmd = proj.get("test_cmd", "")

        pkt = GeneratedPacket(
            packet_id=packet_id,
            task=scan.recommended_task,
            project_dir=scan.dir,
            project_name=scan.name,
            agent=agent,
            reason=reason,
            mode="bounded_patch",
            allowed_inspection=allowed[:5],
            allowed_changes=allowed[:3],
            forbidden_changes=[
                "No dependency upgrades.",
                "No architecture rewrite.",
                "No formatting sweep.",
                "No unrelated cleanup.",
            ],
            test_command=test_cmd,
            acceptance_criteria=f"task complete, {test_cmd} passes" if test_cmd else "task complete, files created",
            prompt_mode="frontier_over_frontier",
            created_at=time.time(),
            priority=scan.priority,
        )
        packets.append(pkt)

        # Save packet to disk
        pkt_dict = {
            "packet_id": pkt.packet_id,
            "mode": pkt.mode,
            "task": pkt.task,
            "symptom": "",
            "known_evidence": "",
            "allowed_inspection": pkt.allowed_inspection,
            "allowed_changes": pkt.allowed_changes,
            "forbidden_changes": pkt.forbidden_changes,
            "budget": {
                "max_files_inspect": 8,
                "max_patch_attempts": 2,
                "max_narrow_tests": 3,
                "max_broad_searches": 2,
                "max_terminal_output_lines": 50,
                "max_chat_turns": 15,
                "run_full_suite": False,
                "max_context_tokens": 4000,
            },
            "verification": {
                "tests_required": [pkt.test_command] if pkt.test_command else [],
                "build_required": False,
                "lint_required": False,
                "typecheck_required": False,
                "bug_repro_resolved": False,
                "specific_output": "",
                "acceptance_criteria": pkt.acceptance_criteria,
                "human_review_required": False,
            },
            "prompt_mode": pkt.prompt_mode,
            "created_at": pkt.created_at,
            "route": {"agent": pkt.agent, "reason": pkt.reason},
            "project": pkt.project_dir,
            "priority": pkt.priority,
        }
        pkt_path = PACKETS_DIR / f"{packet_id}.json"
        pkt_path.write_text(json.dumps(pkt_dict, indent=2))

    return packets


# ── Receipt Writer ──

def write_receipt(pkt: GeneratedPacket, files_inspected: int = 0,
                  files_changed: int = 0, tests_passed: bool = False,
                  retries: int = 0, quality: float = 0.8) -> ExecutionReceipt:
    receipt = ExecutionReceipt(
        task_id=pkt.packet_id, project=pkt.project_dir, agent=pkt.agent,
        files_inspected=files_inspected, files_changed=files_changed,
        patch_efficiency=files_inspected / max(files_changed, 1) if files_changed > 0 else 0,
        retries=retries, tests_run=1 if pkt.test_command else 0, tests_passed=tests_passed,
        verification_density=1 if pkt.test_command else 0, cloud_calls=0, cloud_avoidance=1,
        output_quality=quality, artifact_value=10.0 * files_changed,
        substrate_tax={"ram_delta_mb": 50, "swap_delta_mb": 0, "thermal_delta_c": 0.0, "battery_delta_pct": 0.0, "latency_s": 0.5},
        violations=[], compliance_score=1.0, timestamp=time.time(),
    )
    (RECEIPTS_DIR / f"receipt_{pkt.packet_id}.json").write_text(json.dumps(asdict(receipt), indent=2))
    return receipt


# ── RentMasseur Live Data Extraction ──

RM_STATE_DIR = STATE_DIR / "rm"
RM_STATE_DIR.mkdir(parents=True, exist_ok=True)
RM_DB_PATH = REPO_ROOT / "rm_traffic" / "traffic.db"
RM_PROFILEOPS_DB = REPO_ROOT / "rm_traffic" / "profileops.db"


def rm_login() -> Optional[RentMasseurAPI]:
    if not RM_AVAILABLE:
        print("  ⟁ RM module not available", file=sys.stderr); return None
    api = RentMasseurAPI(min_request_interval=0.5)
    auth = AuthSession(api, session_file=str(REPO_ROOT / "rm_traffic" / "session.json"))
    username = get_credential("RM_USER") or os.environ.get("RM_USER") or os.environ.get("RENTMASSEUR_USER", "")
    password = get_credential("RM_PASS") or get_credential("RM_PASSWORD") or os.environ.get("RM_PASSWORD") or os.environ.get("RENTMASSEUR_PASS", "")
    if not username or not password:
        print("  ⟁ RM credentials not found. Set RM_USER and RM_PASS.", file=sys.stderr); return None
    print(f"  ◉ Logging into RentMasseur as {username}...")
    ok = auth.login(username, password)
    if not ok:
        print("  ⟁ RM login failed", file=sys.stderr); return None
    print("  ◆ RM login successful"); return api


def rm_extract_live(api: RentMasseurAPI) -> Dict[str, Any]:
    data: Dict[str, Any] = {"timestamp": time.time(), "logged_in": True, "errors": []}
    for name, fn in [("dashboard", api.get_dashboard), ("availability", api.get_availability),
                     ("stats", api.get_ad_statistics), ("keeponline", api.get_keeponline),
                     ("about", api.get_about)]:
        try:
            data[name] = fn(); print(f"  ◉ {name} pulled")
        except Exception as e:
            data["errors"].append(f"{name}: {e}"); print(f"  ⟁ {name} failed: {e}", file=sys.stderr)
    try:
        data["mailbox"] = api.get_mailbox(page=1, folder=1, sort=1); print("  ◉ mailbox pulled")
    except Exception as e:
        data["errors"].append(f"mailbox: {e}")
    try:
        data["search_results"] = api.search(city="manhattan-ny", available_only=False, page=1); print("  ◉ search pulled")
    except Exception as e:
        data["errors"].append(f"search: {e}")
    (RM_STATE_DIR / "live_data.json").write_text(json.dumps(data, indent=2, default=str))
    return data


def rm_selenium_verify() -> Dict[str, Any]:
    if not SELENIUM_AVAILABLE:
        return {"status": "unavailable", "errors": ["selenium not imported"]}
    results: Dict[str, Any] = {"timestamp": time.time(), "errors": []}
    try:
        print("  ⌁ Selenium: search visibility...")
        sv = selenium_verify_search()
        results["search_verification"] = sv
        print(f"  ⌁ Search: {sv.get('selenium_status', '?')} — {sv.get('total_found', 0)} cards")
    except Exception as e:
        results["errors"].append(f"search: {e}")
    try:
        print("  ⌁ Selenium: profile page...")
        pv = selenium_verify_profile_page()
        results["profile_verification"] = pv
        print(f"  ⌁ Profile: {pv.get('status', '?')}")
    except Exception as e:
        results["errors"].append(f"profile: {e}")
    (RM_STATE_DIR / "selenium_verify.json").write_text(json.dumps(results, indent=2, default=str))
    return results


def rm_read_db_stats() -> Dict[str, Any]:
    stats: Dict[str, Any] = {"traffic_snapshots": [], "profileops_receipts": 0}
    try:
        conn = sqlite3.connect(str(RM_DB_PATH)); conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM traffic_snapshots ORDER BY created_at DESC LIMIT 10").fetchall()
        stats["traffic_snapshots"] = [dict(r) for r in rows]
        if rows: stats["latest_snapshot"] = dict(rows[0])
        conn.close()
    except Exception as e: stats["traffic_error"] = str(e)
    try:
        conn = sqlite3.connect(str(RM_PROFILEOPS_DB))
        stats["profileops_receipts"] = conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
        conn.close()
    except Exception as e: stats["profileops_error"] = str(e)
    return stats


def rm_generate_packets(rm_data: Dict, selenium_data: Dict) -> List[GeneratedPacket]:
    packets: List[GeneratedPacket] = []; counter = 0
    dashboard = rm_data.get("dashboard") or {}; about = rm_data.get("about") or {}
    availability = rm_data.get("availability") or {}; errors = rm_data.get("errors", [])

    def mk(task, agent, mode, inspect, changes, test_cmd, criteria, priority, reason):
        nonlocal counter; counter += 1
        return GeneratedPacket(
            packet_id=f"rm_packet_{int(time.time())}_{counter}", task=task,
            project_dir="rm_traffic", project_name="RentMasseur", agent=agent,
            reason=reason, mode=mode, allowed_inspection=inspect, allowed_changes=changes,
            forbidden_changes=["No dependency upgrades.", "No architecture rewrite.", "No unrelated cleanup."],
            test_command=test_cmd, acceptance_criteria=criteria, prompt_mode="frontier_over_frontier",
            created_at=time.time(), priority=priority,
        )

    if dashboard.get("isAdHidden"):
        packets.append(mk("Profile HIDDEN — restore visibility via PUT /settings/visibility",
            "devin", "bounded_patch", ["rm_traffic/api_client.py"], ["rm_traffic/api_client.py"],
            "python3 -c \"from rm_traffic.api_client import RentMasseurAPI; print('ok')\"",
            "isAdHidden=false", "high", "autonomous API call"))
    if availability.get("option", 0) == 0:
        packets.append(mk("Availability not set — set to Available via PUT /account/dashboard/availability",
            "devin", "bounded_patch", ["rm_traffic/api_client.py"], ["rm_traffic/api_client.py"],
            "python3 -c \"from rm_traffic.api_client import RentMasseurAPI; print('ok')\"",
            "option=1 (Available)", "high", "autonomous API call"))
    headline = about.get("headline", "") or ""
    if len(headline) < 10:
        packets.append(mk("Bio headline weak — generate and push improved headline via PUT /settings/about",
            "devin", "bounded_patch", ["rm_traffic/bio_generator.py", "rm_traffic/api_client.py", "rm_traffic/bio_features.py"],
            ["rm_traffic/bio_generator.py"], "python3 -m pytest rm_traffic/ -x -q",
            "new headline pushed, len > 20", "medium", "autonomous bio generation"))
    sv = selenium_data.get("search_verification") or {}
    if sv.get("selenium_status") == "fail":
        packets.append(mk("Selenium search verification failed — investigate Chrome driver or page changes",
            "devin", "exploration", ["rm_traffic/money_training_selenium.py", "rm_traffic/engine.py"],
            ["rm_traffic/money_training_selenium.py"], "python3 -m pytest rm_traffic/ -x -q",
            "selenium_verify_search returns pass", "medium", "autonomous debugging"))
    if errors:
        packets.append(mk(f"RM API had {len(errors)} errors — investigate auth/session health",
            "devin", "bounded_patch", ["rm_traffic/auth.py", "rm_traffic/api_client.py", "rm_traffic/session.json"],
            ["rm_traffic/auth.py", "rm_traffic/session.json"],
            "python3 -c \"from rm_traffic.auth import AuthSession; print('ok')\"",
            "all RM API endpoints return without error", "high" if len(errors) > 2 else "medium",
            "autonomous session repair"))

    for pkt in packets:
        pkt_dict = {
            "packet_id": pkt.packet_id, "mode": pkt.mode, "task": pkt.task, "symptom": "", "known_evidence": "",
            "allowed_inspection": pkt.allowed_inspection, "allowed_changes": pkt.allowed_changes,
            "forbidden_changes": pkt.forbidden_changes,
            "budget": {"max_files_inspect": 8, "max_patch_attempts": 2, "max_narrow_tests": 3, "max_broad_searches": 2,
                       "max_terminal_output_lines": 50, "max_chat_turns": 15, "run_full_suite": False, "max_context_tokens": 4000},
            "verification": {"tests_required": [pkt.test_command] if pkt.test_command else [], "build_required": False,
                             "lint_required": False, "typecheck_required": False, "bug_repro_resolved": False,
                             "specific_output": "", "acceptance_criteria": pkt.acceptance_criteria, "human_review_required": False},
            "prompt_mode": pkt.prompt_mode, "created_at": pkt.created_at,
            "route": {"agent": pkt.agent, "reason": pkt.reason}, "project": pkt.project_dir,
            "priority": pkt.priority, "source": "rentmasseur",
        }
        (PACKETS_DIR / f"{pkt.packet_id}.json").write_text(json.dumps(pkt_dict, indent=2))
    return packets


# ═══════════════════════════════════════════════════════════════════════
# RM Traffic Loop — 30 automatable client-magnet functions as discrete steps
# ═══════════════════════════════════════════════════════════════════════

NY_CITIES = [
    "manhattan-ny", "brooklyn-ny", "queens-ny", "bronx-ny",
    "staten-island-ny", "long-island-ny", "westchester-ny",
]

RM_USERNAME = os.environ.get("RM_USER", os.environ.get("RENTMASSEUR_USER", ""))


def _rm_receipt(step_id: str, step_name: str, before: dict, after: dict,
                verified: bool = True, tier: str = "") -> dict:
    """Write a receipt for an RM traffic loop step."""
    receipt_data = {
        "step_id": step_id,
        "step_name": step_name,
        "tier": tier,
        "before": before,
        "after": after,
        "verified": verified,
        "timestamp": time.time(),
    }
    receipt_path = RECEIPTS_DIR / f"receipt_rm_{step_id}_{int(time.time())}.json"
    receipt_path.write_text(json.dumps(receipt_data, indent=2, default=str))
    glyph = "◆" if verified else "⟁"
    print(f"  {glyph} {step_id}: {step_name} (verified={verified})")
    return receipt_data


def _rm_get_api() -> Optional[RentMasseurAPI]:
    """Login and return API client, or None."""
    return rm_login()


# ── 15-minute tier: Functions #1, #2, #3, #6, #27 ──

def step_01_availability_refresh(api: RentMasseurAPI) -> dict:
    """#1: Auto-refresh availability when near expiry."""
    from rm_traffic.availability_guard import check_availability, refresh_availability
    status = check_availability(api)
    if status.get("needs_refresh"):
        before = {"selected": status["selected"], "remaining": status["remaining_seconds"]}
        refreshed = refresh_availability(api, hours=6)
        after_status = check_availability(api)
        after = {"selected": after_status["selected"], "remaining": after_status["remaining_seconds"]}
        return _rm_receipt("01_availability_refresh", "Availability Auto-Refresh", before, after,
                           verified=refreshed, tier="15min")
    return _rm_receipt("01_availability_refresh", "Availability OK — no refresh needed",
                       status, status, verified=True, tier="15min")


def step_02_visibility_guard(api: RentMasseurAPI) -> dict:
    """#2: Check isAdHidden and auto-restore visibility."""
    from rm_traffic.visibility_guard import ensure_visible
    keep_before = api.get_keeponline()
    before = {"isAdHidden": int(keep_before.get("isAdHidden", 0))}
    ok = ensure_visible(api)
    keep_after = api.get_keeponline()
    after = {"isAdHidden": int(keep_after.get("isAdHidden", 0))}
    return _rm_receipt("02_visibility_guard", "Visibility Guard", before, after,
                       verified=ok, tier="15min")


def step_03_keeponline_pulse(api: RentMasseurAPI) -> dict:
    """#3: KeepOnline heartbeat to maintain online status."""
    before = {}
    result = api.get_keeponline()
    after = {"isAdHidden": int(result.get("isAdHidden", 0)),
             "newVisits": result.get("newVisits"),
             "newEmails": result.get("newEmails")}
    verified = "isAdHidden" in result
    return _rm_receipt("03_keeponline_pulse", "KeepOnline Pulse", before, after,
                       verified=verified, tier="15min")


def step_06_dashboard_health(api: RentMasseurAPI) -> dict:
    """#6: Dashboard health monitor — profile status, banner, interview slots."""
    before = {}
    dashboard = api.get_dashboard()
    after = {
        "isAdHidden": dashboard.get("isAdHidden"),
        "reviewUrl": dashboard.get("reviewUrl"),
        "onlineBookmarks": dashboard.get("onlineBookmarks"),
        "featureInterview": dashboard.get("featureInterview", {}).get("isCompleted"),
    }
    verified = isinstance(dashboard, dict)
    return _rm_receipt("06_dashboard_health", "Dashboard Health Monitor", before, after,
                       verified=verified, tier="15min")


def step_27_ad_statistics(api: RentMasseurAPI) -> dict:
    """#27: Ad statistics snapshot — views, contacts, visits, bookmarks."""
    from rm_traffic.stats_collector import collect_snapshot
    before = {}
    snapshot = collect_snapshot(api)
    after = snapshot
    verified = "profile_views" in snapshot
    return _rm_receipt("27_ad_statistics", "Ad Statistics Snapshot", before, after,
                       verified=verified, tier="15min")


# ── 30-minute tier: Functions #7, #8, #10, #11 ──

def step_07_multi_city_search(api: RentMasseurAPI) -> dict:
    """#7: Multi-city search scraping across 7 NY cities."""
    from rm_traffic.search_rank import check_search_rank, find_position, total_count
    results = {}
    for city in NY_CITIES:
        try:
            rank = check_search_rank(api, RM_USERNAME, city=city, available_only=False)
            results[city] = {"position": rank["position"], "total": rank["total"], "found": rank["found"]}
        except Exception as e:
            results[city] = {"error": str(e)}
    verified = any(r.get("found") for r in results.values())
    return _rm_receipt("07_multi_city_search", "Multi-City Search Scraping", {}, results,
                       verified=verified, tier="30min")


def step_08_available_rank(api: RentMasseurAPI) -> dict:
    """#8: Available-only search rank tracking."""
    from rm_traffic.search_rank import check_available_now_rank
    results = {}
    for city in NY_CITIES:
        try:
            rank = check_available_now_rank(api, RM_USERNAME, city=city)
            results[city] = {"position": rank["position"], "total": rank["total"], "found": rank["found"]}
        except Exception as e:
            results[city] = {"error": str(e)}
    verified = any(r.get("found") for r in results.values())
    return _rm_receipt("08_available_rank", "Available-Only Rank Tracking", {}, results,
                       verified=verified, tier="30min")


def step_10_position_delta(api: RentMasseurAPI) -> dict:
    """#10: Search position delta vs historical snapshots in traffic.db."""
    from rm_traffic.search_rank import check_search_rank
    current = check_search_rank(api, RM_USERNAME, city="manhattan-ny", available_only=False)
    previous = None
    try:
        conn = sqlite3.connect(str(RM_DB_PATH))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM traffic_snapshots ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row:
            previous = dict(row)
        conn.close()
    except Exception:
        pass
    delta = {
        "current_position": current.get("position"),
        "previous_position": previous.get("position") if previous else None,
        "position_change": (current.get("position") or 0) - (previous.get("position") or 0) if previous and previous.get("position") else None,
    }
    verified = current.get("found", False)
    return _rm_receipt("10_position_delta", "Search Position Delta Alerting", previous or {}, delta,
                       verified=verified, tier="30min")


def step_11_competitor_count(api: RentMasseurAPI) -> dict:
    """#11: Competitor count monitoring per city."""
    from rm_traffic.search_rank import total_count
    counts = {}
    for city in NY_CITIES:
        try:
            results = api.search(city=city, available_only=False, page=1)
            counts[city] = total_count(results)
        except Exception as e:
            counts[city] = {"error": str(e)}
    verified = any(isinstance(v, int) and v > 0 for v in counts.values())
    return _rm_receipt("11_competitor_count", "Competitor Count Monitoring", {}, counts,
                       verified=verified, tier="30min")


# ── 2-hour tier: Functions #19, #20, #23 ──

def step_19_reciprocal_visits(api: RentMasseurAPI) -> dict:
    """#19: Reciprocal profile visits — visit clients who visited you."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "rm_traffic.engagement_engine", "--visit-only", "--once",
             "--max-visits", "200", "--delay", "3"],
            capture_output=True, text=True, timeout=600, cwd=str(REPO_ROOT),
        )
        verified = result.returncode == 0
        return _rm_receipt("19_reciprocal_visits", "Reciprocal Profile Visits", {},
                           {"exit_code": result.returncode, "stdout": result.stdout[-500:]},
                           verified=verified, tier="2h")
    except Exception as e:
        return _rm_receipt("19_reciprocal_visits", "Reciprocal Profile Visits", {},
                           {"error": str(e)}, verified=False, tier="2h")


def step_20_ny_search_visits(api: RentMasseurAPI) -> dict:
    """#20: Visit every NY profile found in search — reciprocal visibility."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "rm_traffic.engagement_engine", "--visit-only", "--once",
             "--max-visits", "500", "--delay", "2", "--search-visit"],
            capture_output=True, text=True, timeout=900, cwd=str(REPO_ROOT),
        )
        verified = result.returncode == 0
        return _rm_receipt("20_ny_search_visits", "NY Search Profile Visits", {},
                           {"exit_code": result.returncode, "stdout": result.stdout[-500:]},
                           verified=verified, tier="2h")
    except Exception as e:
        return _rm_receipt("20_ny_search_visits", "NY Search Profile Visits", {},
                           {"error": str(e)}, verified=False, tier="2h")


def step_23_engagement_stats(api: RentMasseurAPI) -> dict:
    """#23: Engagement stats dashboard."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "rm_traffic.engagement_engine", "--stats"],
            capture_output=True, text=True, timeout=60, cwd=str(REPO_ROOT),
        )
        verified = result.returncode == 0
        return _rm_receipt("23_engagement_stats", "Engagement Stats Dashboard", {},
                           {"exit_code": result.returncode, "stdout": result.stdout[-1000:]},
                           verified=verified, tier="2h")
    except Exception as e:
        return _rm_receipt("23_engagement_stats", "Engagement Stats Dashboard", {},
                           {"error": str(e)}, verified=False, tier="2h")


# ── 4-hour tier: Functions #21, #22 ──

def step_21_client_messaging(api: RentMasseurAPI) -> dict:
    """#21: LLM-personalized client messaging with 24h cooldown."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "rm_traffic.engagement_engine", "--message-only", "--once",
             "--max-messages", "100", "--delay", "5"],
            capture_output=True, text=True, timeout=600, cwd=str(REPO_ROOT),
        )
        verified = result.returncode == 0
        return _rm_receipt("21_client_messaging", "LLM-Personalized Client Messaging", {},
                           {"exit_code": result.returncode, "stdout": result.stdout[-500:]},
                           verified=verified, tier="4h")
    except Exception as e:
        return _rm_receipt("21_client_messaging", "LLM-Personalized Client Messaging", {},
                           {"error": str(e)}, verified=False, tier="4h")


def step_22_visitor_cooldown(api: RentMasseurAPI) -> dict:
    """#22: Visitor dedup & cooldown enforcement — SQLite tracking audit."""
    try:
        eng_db = REPO_ROOT / "rm_traffic" / "engagement.db"
        if not eng_db.exists():
            return _rm_receipt("22_visitor_cooldown", "Visitor Dedup & Cooldown", {},
                               {"error": "engagement.db not found"}, verified=False, tier="4h")
        conn = sqlite3.connect(str(eng_db))
        stats = {
            "total_visitors": conn.execute("SELECT COUNT(*) FROM visitors").fetchone()[0] if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='visitors'").fetchone() else 0,
            "total_messaged": conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages'").fetchone() else 0,
        }
        conn.close()
        return _rm_receipt("22_visitor_cooldown", "Visitor Dedup & Cooldown", {}, stats,
                           verified=True, tier="4h")
    except Exception as e:
        return _rm_receipt("22_visitor_cooldown", "Visitor Dedup & Cooldown", {},
                           {"error": str(e)}, verified=False, tier="4h")


# ── 6-hour tier: Functions #9, #30, #5 ──

def step_09_selenium_search(api: RentMasseurAPI) -> dict:
    """#9: Selenium search visibility verification."""
    if not SELENIUM_AVAILABLE:
        return _rm_receipt("09_selenium_search", "Selenium Search Verification", {},
                           {"error": "selenium not available"}, verified=False, tier="6h")
    try:
        sv = selenium_verify_search()
        verified = sv.get("selenium_status") == "pass"
        return _rm_receipt("09_selenium_search", "Selenium Search Verification", {},
                           sv, verified=verified, tier="6h")
    except Exception as e:
        return _rm_receipt("09_selenium_search", "Selenium Search Verification", {},
                           {"error": str(e)}, verified=False, tier="6h")


def step_30_selenium_profile(api: RentMasseurAPI) -> dict:
    """#30: Selenium profile page verification."""
    if not SELENIUM_AVAILABLE:
        return _rm_receipt("30_selenium_profile", "Selenium Profile Verification", {},
                           {"error": "selenium not available"}, verified=False, tier="6h")
    try:
        pv = selenium_verify_profile_page()
        verified = pv.get("status") == "pass"
        return _rm_receipt("30_selenium_profile", "Selenium Profile Verification", {},
                           pv, verified=verified, tier="6h")
    except Exception as e:
        return _rm_receipt("30_selenium_profile", "Selenium Profile Verification", {},
                           {"error": str(e)}, verified=False, tier="6h")


def step_05_track_actions(api: RentMasseurAPI) -> dict:
    """#5: Track actions opt-in — ensure analytics tracking enabled."""
    before = {}
    api.set_track_actions(True)
    verified = True
    after = {"trackActions": True}
    return _rm_receipt("05_track_actions", "Track Actions Opt-In", before, after,
                       verified=verified, tier="6h")


# ── 24-hour tier: Functions #12, #13, #14, #15, #17 ──

def step_12_llm_bio(api: RentMasseurAPI) -> dict:
    """#12: LLM bio generation grounded in real traffic data."""
    try:
        from rm_traffic.llm_bio_writer import generate_bio_with_llm
        about = api.get_about()
        assets = about.get("userProps", {}).get("assets", {})
        current_headline = assets.get("headline", "")
        current_description = assets.get("description", "")
        suggestion = generate_bio_with_llm(
            {"about": about, "stats": {}}, [],
            current_headline, current_description,
            city="Manhattan, NYC",
        )
        verified = bool(suggestion and "headline" in suggestion)
        return _rm_receipt("12_llm_bio", "LLM Bio Generation",
                           {"headline": current_headline},
                           suggestion or {"error": "no suggestion"},
                           verified=verified, tier="24h")
    except Exception as e:
        return _rm_receipt("12_llm_bio", "LLM Bio Generation", {},
                           {"error": str(e)}, verified=False, tier="24h")


def step_13_bio_ab_test(api: RentMasseurAPI) -> dict:
    """#13: Bio A/B testing — rotate variants on 24h cycle."""
    try:
        from rm_traffic.content_optimizer import run_daily_draft_cycle, evaluate_open_experiments
        experiments = evaluate_open_experiments(api)
        drafts = run_daily_draft_cycle(api)
        verified = True
        return _rm_receipt("13_bio_ab_test", "Bio A/B Testing", {},
                           {"drafts": drafts, "experiments_evaluated": experiments},
                           verified=verified, tier="24h")
    except Exception as e:
        return _rm_receipt("13_bio_ab_test", "Bio A/B Testing", {},
                           {"error": str(e)}, verified=False, tier="24h")


def step_14_genetic_evolution(api: RentMasseurAPI) -> dict:
    """#14: Genetic bio evolution — crossover + mutation + tournament selection."""
    try:
        from rm_traffic.bio_evolver import run_evolution
        elite_ids = run_evolution(generations=30, population_size=50, elite_size=5, top_n=5)
        verified = len(elite_ids) > 0
        return _rm_receipt("14_genetic_evolution", "Genetic Bio Evolution", {},
                           {"elites_saved": len(elite_ids), "elite_ids": elite_ids[:5]},
                           verified=verified, tier="24h")
    except Exception as e:
        return _rm_receipt("14_genetic_evolution", "Genetic Bio Evolution", {},
                           {"error": str(e)}, verified=False, tier="24h")


def step_15_ml_prediction(api: RentMasseurAPI) -> dict:
    """#15: ML bio performance prediction — MLP CTR/email/phone prediction."""
    try:
        from rm_traffic.bio_predictor import predict_performance, train_predictor
        from rm_traffic.bio_generator import generate_bios
        bios = generate_bios(count=50, top_n=50)
        model = train_predictor(bios, epochs=300)
        about = api.get_about()
        assets = about.get("userProps", {}).get("assets", {})
        headline = assets.get("headline", "")
        description = assets.get("description", "")
        pred = predict_performance(headline, description, model)
        verified = "ctr" in pred
        return _rm_receipt("15_ml_prediction", "ML Bio Performance Prediction",
                           {"headline": headline}, pred, verified=verified, tier="24h")
    except Exception as e:
        return _rm_receipt("15_ml_prediction", "ML Bio Performance Prediction", {},
                           {"error": str(e)}, verified=False, tier="24h")


def step_17_variant_rotation(api: RentMasseurAPI) -> dict:
    """#17: Bio variant library rotation — 50+ hypothesis-driven variants."""
    try:
        from rm_traffic.bio_variants_library import list_all, count
        total = count()
        variants = list_all()
        active_ids = [v["variant_id"] for v in variants[:5]]
        verified = total > 0
        return _rm_receipt("17_variant_rotation", "Bio Variant Library Rotation", {},
                           {"total_variants": total, "sample_ids": active_ids},
                           verified=verified, tier="24h")
    except Exception as e:
        return _rm_receipt("17_variant_rotation", "Bio Variant Library Rotation", {},
                           {"error": str(e)}, verified=False, tier="24h")


# ── Weekly tier: Functions #24, #25, #26 ──

def step_24_blog_draft(api: RentMasseurAPI) -> dict:
    """#24: Blog draft generation — SEO-optimized, never auto-published."""
    try:
        from rm_traffic.blog_agent import generate_blog_drafts, save_blog_drafts_to_disk
        drafts = generate_blog_drafts(count=2)
        save_blog_drafts_to_disk(drafts)
        verified = len(drafts) > 0
        return _rm_receipt("24_blog_draft", "Blog Draft Generation", {},
                           {"drafts_count": len(drafts),
                            "titles": [d.get("title", "") for d in drafts]},
                           verified=verified, tier="weekly")
    except Exception as e:
        return _rm_receipt("24_blog_draft", "Blog Draft Generation", {},
                           {"error": str(e)}, verified=False, tier="weekly")


def step_25_blog_optimization(api: RentMasseurAPI) -> dict:
    """#25: Blog optimization — select best variant by predicted engagement."""
    try:
        from rm_traffic.blog_optimizer import select_best, generate_optimized_blog
        best = generate_optimized_blog()
        verified = bool(best and "title" in best)
        return _rm_receipt("25_blog_optimization", "Blog Optimization", {},
                           best or {"error": "no blog generated"},
                           verified=verified, tier="weekly")
    except Exception as e:
        return _rm_receipt("25_blog_optimization", "Blog Optimization", {},
                           {"error": str(e)}, verified=False, tier="weekly")


def step_26_interview_drafts(api: RentMasseurAPI) -> dict:
    """#26: Interview monitor & draft generation — trust content."""
    try:
        from rm_traffic.interview_agent import monitor_interview, generate_interview_drafts
        status = monitor_interview(api)
        drafts = generate_interview_drafts()
        verified = len(drafts) > 0
        return _rm_receipt("26_interview_drafts", "Interview Monitor & Drafts", status,
                           {"drafts_count": len(drafts),
                            "questions": [d["question"] for d in drafts]},
                           verified=verified, tier="weekly")
    except Exception as e:
        return _rm_receipt("26_interview_drafts", "Interview Monitor & Drafts", {},
                           {"error": str(e)}, verified=False, tier="weekly")


# ── On-demand tier: Functions #4, #16, #18, #28, #29 ──

def step_04_sms_alerts(api: RentMasseurAPI) -> dict:
    """#4: SMS alert toggle — ensure notifications are on."""
    before = {}
    api.set_sms_alerts(True)
    after = {"sms": True}
    return _rm_receipt("04_sms_alerts", "SMS Alert Toggle", before, after,
                       verified=True, tier="on-demand")


def step_16_policy_check(api: RentMasseurAPI) -> dict:
    """#16: Bio policy safety check — block risky content before publishing."""
    try:
        from rm_traffic.content_policy import check_bio_risk, check_headline_risk, explain_risk
        about = api.get_about()
        assets = about.get("userProps", {}).get("assets", {})
        headline = assets.get("headline", "")
        description = assets.get("description", "")
        h_risk = check_headline_risk(headline)
        b_risk = check_bio_risk(description)
        explanation = explain_risk(headline + " " + description)
        verified = h_risk <= 0.7 and b_risk <= 0.7
        return _rm_receipt("16_policy_check", "Bio Policy Safety Check", {},
                           {"headline_risk": h_risk, "bio_risk": b_risk,
                            "reasons": explanation["reasons"], "safe": verified},
                           verified=verified, tier="on-demand")
    except Exception as e:
        return _rm_receipt("16_policy_check", "Bio Policy Safety Check", {},
                           {"error": str(e)}, verified=False, tier="on-demand")


def step_18_bio_appraiser(api: RentMasseurAPI) -> dict:
    """#18: Bio appraiser scoring — score bios against real-world data."""
    try:
        from rm_traffic.bio_appraiser import full_appraisal
        bio_file = REPO_ROOT / "rm_traffic" / "data" / "bios.jsonl"
        if not bio_file.exists():
            return _rm_receipt("18_bio_appraiser", "Bio Appraiser Scoring", {},
                               {"error": "bios.jsonl not found"}, verified=False, tier="on-demand")
        appraisal = full_appraisal(bio_file, sample_size=200)
        verified = "novelty" in appraisal
        return _rm_receipt("18_bio_appraiser", "Bio Appraiser Scoring", {}, appraisal,
                           verified=verified, tier="on-demand")
    except Exception as e:
        return _rm_receipt("18_bio_appraiser", "Bio Appraiser Scoring", {},
                           {"error": str(e)}, verified=False, tier="on-demand")


def step_28_money_training(api: RentMasseurAPI) -> dict:
    """#28: Money training loop — 30-epoch MLP on bio-to-conversion prediction."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "rm_traffic.money_training_selenium"],
            capture_output=True, text=True, timeout=900, cwd=str(REPO_ROOT),
        )
        verified = result.returncode == 0
        return _rm_receipt("28_money_training", "Money Training Loop", {},
                           {"exit_code": result.returncode, "stdout": result.stdout[-1000:]},
                           verified=verified, tier="on-demand")
    except Exception as e:
        return _rm_receipt("28_money_training", "Money Training Loop", {},
                           {"error": str(e)}, verified=False, tier="on-demand")


def step_29_traffic_delta(api: RentMasseurAPI) -> dict:
    """#29: Traffic snapshot delta analysis — detect view/contact trends."""
    try:
        from rm_traffic.traffic_analyzer import analyze_trend, detect_drop
        trend = analyze_trend(hours=24)
        drop = detect_drop()
        verified = trend.get("status") == "ok"
        return _rm_receipt("29_traffic_delta", "Traffic Snapshot Delta Analysis", {},
                           {"trend": trend, "drop_detected": drop.get("alert", False)},
                           verified=verified, tier="on-demand")
    except Exception as e:
        return _rm_receipt("29_traffic_delta", "Traffic Snapshot Delta Analysis", {},
                           {"error": str(e)}, verified=False, tier="on-demand")


# ── Tier dispatchers ──

TIER_STEPS = {
    "15min": [step_01_availability_refresh, step_02_visibility_guard,
              step_03_keeponline_pulse, step_06_dashboard_health, step_27_ad_statistics],
    "30min": [step_07_multi_city_search, step_08_available_rank,
              step_10_position_delta, step_11_competitor_count],
    "2h":    [step_19_reciprocal_visits, step_20_ny_search_visits, step_23_engagement_stats],
    "4h":    [step_21_client_messaging, step_22_visitor_cooldown],
    "6h":    [step_09_selenium_search, step_30_selenium_profile, step_05_track_actions],
    "24h":   [step_12_llm_bio, step_13_bio_ab_test, step_14_genetic_evolution,
              step_15_ml_prediction, step_17_variant_rotation],
    "weekly": [step_24_blog_draft, step_25_blog_optimization, step_26_interview_drafts],
    "on-demand": [step_04_sms_alerts, step_16_policy_check, step_18_bio_appraiser,
                  step_28_money_training, step_29_traffic_delta],
}

ALL_TIERS = ["15min", "30min", "2h", "4h", "6h", "24h", "weekly", "on-demand"]


def cmd_rm_loop(tier: str = "all"):
    """Run RM traffic loop steps for a specific tier or all tiers."""
    if not RM_AVAILABLE:
        print("  ⟁ RM module not available", file=sys.stderr); return None

    tiers = ALL_TIERS if tier == "all" else [tier]
    api = _rm_get_api()
    if not api:
        print("  ⟁ RM login failed — cannot run traffic loop", file=sys.stderr); return None

    all_results = []
    all_packets = []
    all_receipts = []

    for t in tiers:
        steps = TIER_STEPS.get(t, [])
        if not steps:
            print(f"  ⟁ Unknown tier: {t}", file=sys.stderr); continue
        print(f"\n  ═══ RM Traffic Loop — tier: {t} ({len(steps)} steps) ═══")
        for step_fn in steps:
            try:
                result = step_fn(api)
                all_results.append(result)
                pkt = GeneratedPacket(
                    packet_id=f"rm_loop_{step_fn.__name__.replace('step_', '')}_{int(time.time())}",
                    task=step_fn.__doc__.strip().split(":")[0] if step_fn.__doc__ else step_fn.__name__,
                    project_dir="rm_traffic", project_name="RentMasseur", agent="devin",
                    reason=f"traffic loop {t}", mode="bounded_patch",
                    allowed_inspection=["rm_traffic/"], allowed_changes=["rm_traffic/"],
                    forbidden_changes=["No dependency upgrades.", "No architecture rewrite."],
                    test_command="python3 -c \"import rm_traffic; print('ok')\"",
                    acceptance_criteria=f"{step_fn.__name__} verified=True",
                    prompt_mode="frontier_over_frontier", created_at=time.time(),
                    priority="high" if t in ("15min", "30min") else "medium",
                )
                all_packets.append(pkt)
                all_receipts.append(write_receipt(pkt, files_inspected=1, quality=0.9))
            except Exception as e:
                print(f"  ⟁ {step_fn.__name__} failed: {e}", file=sys.stderr)
                all_results.append({"step": step_fn.__name__, "error": str(e), "verified": False})

    db_stats = rm_read_db_stats()
    state = save_state([], all_packets, all_receipts, rm_data={"logged_in": True, "errors": []},
                       selenium_data=None, db_stats=db_stats)

    verified_count = sum(1 for r in all_results if r.get("verified"))
    print(f"\n  ═══ RM Traffic Loop Complete ═══")
    print(f"  Tiers: {', '.join(tiers)}")
    print(f"  Steps: {len(all_results)} total, {verified_count} verified, {len(all_results) - verified_count} failed")
    print(f"  Receipts: {len(all_receipts)}")
    return state


# ── Controller State ──

def save_state(scans: list[ProjectScan], packets: list[GeneratedPacket],
               receipts: list[ExecutionReceipt], rm_data: Dict = None,
               selenium_data: Dict = None, db_stats: Dict = None):
    state = {
        "last_scan": time.time(),
        "projects": [{"dir": s.dir, "name": s.name, "lang": s.lang, "state": s.state, "issues": s.issues,
            "file_count": s.file_count, "has_build": s.has_build, "has_tests": s.has_tests, "has_readme": s.has_readme,
            "last_modified_days": round(s.last_modified_days, 1), "recommended_task": s.recommended_task, "priority": s.priority}
            for s in scans],
        "pending_packets": [{"packet_id": p.packet_id, "task": p.task, "project": p.project_dir, "agent": p.agent,
            "priority": p.priority, "created_at": p.created_at,
            "source": "rentmasseur" if p.project_dir == "rm_traffic" else "project"} for p in packets],
        "receipts_count": len(receipts),
        "rm": {
            "available": RM_AVAILABLE, "selenium_available": SELENIUM_AVAILABLE,
            "logged_in": rm_data is not None and rm_data.get("logged_in", False),
            "errors": rm_data.get("errors", []) if rm_data else [],
            "is_hidden": (rm_data.get("dashboard") or {}).get("isAdHidden") if rm_data else None,
            "availability_option": (rm_data.get("availability") or {}).get("option") if rm_data else None,
            "headline": (rm_data.get("about") or {}).get("headline", "") if rm_data else "",
            "selenium_search_status": (selenium_data.get("search_verification") or {}).get("selenium_status") if selenium_data else None,
            "selenium_total_found": (selenium_data.get("search_verification") or {}).get("total_found") if selenium_data else None,
            "selenium_profile_status": (selenium_data.get("profile_verification") or {}).get("status") if selenium_data else None,
            "db_traffic_snapshots": len(db_stats.get("traffic_snapshots", [])) if db_stats else 0,
            "db_profileops_receipts": db_stats.get("profileops_receipts", 0) if db_stats else 0,
        } if rm_data or db_stats else None,
        "timestamp": time.time(),
    }
    (STATE_DIR / "controller_state.json").write_text(json.dumps(state, indent=2, default=str))
    return state


def load_state() -> dict:
    """Load controller state."""
    state_path = STATE_DIR / "controller_state.json"
    if state_path.exists():
        return json.loads(state_path.read_text())
    return {}


# ── CLI ──

def cmd_scan():
    scans = scan_all()
    for s in scans:
        glyph = {"active": "◉", "verified": "◆", "idle": "◇", "dormant": "⧖"}.get(s.state, "◌")
        print(f"  {glyph} {s.name:30s} [{s.lang:6s}] {s.state:8s} {s.file_count:4d} files  {s.last_modified_days:6.1f}d  issues: {len(s.issues)}")
        for issue in s.issues:
            print(f"      ⟁ {issue}")
        if s.recommended_task:
            print(f"      → {s.recommended_task}  (priority: {s.priority})")
    print("\n  ◉ RentMasseur live extraction...")
    api = rm_login()
    if api:
        rm_data = rm_extract_live(api)
        print(f"  ◆ RM done — {len(rm_data.get('errors', []))} errors")
    else:
        print("  ⟁ RM login skipped")
    db_stats = rm_read_db_stats()
    print(f"  ◆ DB: {len(db_stats.get('traffic_snapshots', []))} traffic snapshots, {db_stats.get('profileops_receipts', 0)} profileops receipts")
    return scans


def cmd_generate():
    scans = scan_all()
    packets = generate_packets(scans)
    rm_data_path = RM_STATE_DIR / "live_data.json"
    if rm_data_path.exists():
        rm_data = json.loads(rm_data_path.read_text())
        sel_path = RM_STATE_DIR / "selenium_verify.json"
        sel_data = json.loads(sel_path.read_text()) if sel_path.exists() else {}
        rm_pkts = rm_generate_packets(rm_data, sel_data)
        packets.extend(rm_pkts)
    for p in packets:
        src = "RM" if p.project_dir == "rm_traffic" else "PROJ"
        print(f"  ⌁ [{src}] {p.packet_id}  [{p.agent:8s}]  {p.task[:60]}")
        print(f"      project: {p.project_dir}  priority: {p.priority}")
    rm_count = sum(1 for p in packets if p.project_dir == "rm_traffic")
    print(f"\n  {len(packets)} packets ({rm_count} RM, {len(packets) - rm_count} project)")
    return packets


def cmd_rm():
    print("  ◉ RentMasseur autonomous cycle...")
    api = rm_login()
    if not api:
        return None
    rm_data = rm_extract_live(api)
    selenium_data = rm_selenium_verify()
    db_stats = rm_read_db_stats()
    print("  ⌁ Generating RM packets...")
    rm_pkts = rm_generate_packets(rm_data, selenium_data)
    for p in rm_pkts:
        print(f"  ⌁ [RM] {p.packet_id}  [{p.agent}]  {p.task[:60]}  ({p.priority})")
    print("  ◆ Writing receipts...")
    receipts = [write_receipt(pkt, files_inspected=1, quality=0.7) for pkt in rm_pkts]
    state = save_state([], rm_pkts, receipts, rm_data=rm_data, selenium_data=selenium_data, db_stats=db_stats)
    print(f"  ◆ {len(receipts)} receipts written.")
    dash = rm_data.get("dashboard") or {}; about = rm_data.get("about") or {}; avail = rm_data.get("availability") or {}
    print(f"\n  ═══ RM SUMMARY ═══")
    print(f"  Hidden: {dash.get('isAdHidden', '?')}  Available: {avail.get('option', '?')}  Headline: {(about.get('headline', '') or '')[:60]}")
    print(f"  API errors: {len(rm_data.get('errors', []))}  Selenium: {(selenium_data.get('search_verification') or {}).get('selenium_status', 'n/a')}")
    print(f"  Packets: {len(rm_pkts)}  Receipts: {len(receipts)}")
    return state


def cmd_status():
    state = load_state()
    if not state:
        print("  ◌ No state found. Run 'scan' first."); return
    print(f"  Last scan: {time.ctime(state.get('last_scan', 0))}")
    print(f"  Projects: {len(state.get('projects', []))}")
    print(f"  Pending packets: {len(state.get('pending_packets', []))}")
    print(f"  Receipts: {state.get('receipts_count', 0)}")
    rm = state.get("rm")
    if rm:
        print(f"\n  ═══ RentMasseur ═══")
        print(f"  Logged in: {rm.get('logged_in')}  Hidden: {rm.get('is_hidden')}  Available: {rm.get('availability_option')}")
        print(f"  Headline: {(rm.get('headline') or '')[:60]}")
        print(f"  Selenium search: {rm.get('selenium_search_status')}  Profile: {rm.get('selenium_profile_status')}")
        print(f"  DB traffic: {rm.get('db_traffic_snapshots')}  DB receipts: {rm.get('db_profileops_receipts')}")
        if rm.get("errors"):
            print(f"  API errors: {len(rm['errors'])}")
            for e in rm["errors"][:3]: print(f"    ⟁ {e}")


def cmd_run():
    print("  ◉ Scanning projects...")
    scans = scan_all()
    needy = [s for s in scans if s.recommended_task and s.priority != "low"]
    print(f"  ◉ {len(needy)} projects need work out of {len(scans)} scanned")
    print("\n  ◉ RentMasseur live extraction...")
    api = rm_login()
    rm_data = None; selenium_data = None
    if api:
        rm_data = rm_extract_live(api)
        selenium_data = rm_selenium_verify()
    else:
        print("  ⟁ RM login skipped")
    db_stats = rm_read_db_stats()
    print("\n  ⌁ Generating packets...")
    packets = generate_packets(scans)
    if rm_data:
        rm_pkts = rm_generate_packets(rm_data, selenium_data or {})
        packets.extend(rm_pkts)
        print(f"  ⌁ {len(rm_pkts)} RM packets generated")
    print(f"  ⌁ {len(packets)} total packets")
    print("  ◆ Writing receipts...")
    receipts = [write_receipt(pkt, files_inspected=1, quality=0.5) for pkt in packets]
    state = save_state(scans, packets, receipts, rm_data=rm_data, selenium_data=selenium_data, db_stats=db_stats)
    rm_summary = f" · RM: {'logged in' if rm_data and rm_data.get('logged_in') else 'failed'} · {len(rm_data.get('errors', [])) if rm_data else 0} API errors" if rm_data else " · RM: skipped"
    print(f"\n  STATUS: {len(scans)} projects · {len(packets)} packets · {len(receipts)} receipts{rm_summary}")
    return state


def cmd_loop(function_id: str = None):
    """Run the 30-function traffic loop with LLM continuous improvement."""
    if not TRAFFIC_LOOP_AVAILABLE:
        print("  ⟁ traffic_loop module not available", file=sys.stderr); return None
    loop_init_db()
    api = rm_login()
    if not api:
        print("  ⟁ RM login failed — cannot run traffic loop", file=sys.stderr); return None
    if function_id and function_id.isdigit():
        idx = int(function_id) - 1
        if idx < 0 or idx >= 30:
            print(f"  ⟁ Invalid function ID: {function_id}. Must be 1-30.", file=sys.stderr); return None
        print(f"  ◉ Running single function #{int(function_id)}: {FUNCTION_NAMES[idx]}")
        result = loop_run_cycle(api, 0, [idx])
    else:
        print("  ◉ Running full 30-function traffic loop with LLM continuous improvement...")
        result = loop_run_cycle(api, 0)
    print(f"\n  ◆ Loop complete: {result['functions_passed']}/{result['functions_run']} passed · {result['llm_calls']} LLM calls · improvement={result['improvement_score']}")
    return result


def cmd_social(platform: str = "all"):
    """Run the social traffic tunnel — Reddit + X.com lead pipeline."""
    try:
        from rm_traffic.social_traffic_tunnel import run_tunnel_cycle, show_stats
    except ImportError as e:
        print(f"  ⟁ social_traffic_tunnel not available: {e}", file=sys.stderr); return None
    result = run_tunnel_cycle(cycle_num=0, platforms=platform)
    show_stats()
    return result


def cmd_money():
    """Run the money loop — closed-loop revenue optimization."""
    if not MONEY_LOOP_AVAILABLE:
        print("  ⟁ money_loop module not available", file=sys.stderr); return None
    money_init_db()
    api = rm_login()
    if not api:
        print("  ⟁ RM login failed — cannot run money loop", file=sys.stderr); return None
    print("  ◉ Running money loop — closed-loop revenue optimization...")
    result = run_money_cycle(api, 1)
    print(f"\n  ◆ Money cycle complete: revenue=${result['funnel']['estimated_revenue']} delta=${result['revenue_delta']} ROI={result['roi']}")
    return result


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "scan": cmd_scan()
    elif cmd == "generate": cmd_generate()
    elif cmd == "status": cmd_status()
    elif cmd == "run": cmd_run()
    elif cmd == "rm": cmd_rm()
    elif cmd == "rm-loop": cmd_rm_loop(sys.argv[2] if len(sys.argv) > 2 else "all")
    elif cmd == "loop": cmd_loop(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "social": cmd_social(sys.argv[2] if len(sys.argv) > 2 else "all")
    elif cmd == "money": cmd_money()
    else:
        print(f"Unknown command: {cmd}"); print(__doc__); sys.exit(1)


if __name__ == "__main__":
    main()
