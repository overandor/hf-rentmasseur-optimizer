#!/usr/bin/env python3
"""
AGI ETL Pipeline — Extract, Transform, Load powered by Groq LLM.

Extract:   Pull data from git, ChatGPT responses, test results, code files
Transform: Groq LLM processes, analyzes, summarizes, classifies
Load:      Store enriched results back to bridge queue + SQLite + dashboard

Usage:
    python3 -m agent_bridge.etl_pipeline                    # Run continuous
    python3 -m agent_bridge.etl_pipeline --once              # One ETL cycle
    python3 -m agent_bridge.etl_pipeline --source git        # Only git source
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .passport import groq_chat

BRIDGE_URL = "http://127.0.0.1:8766"

LOG_DIR = Path(__file__).parent / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "etl_pipeline.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("etl_pipeline")

REPO_ROOT = Path(__file__).parent.parent


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _api(method, path, data=None, base=BRIDGE_URL):
    url = f"{base}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "AgentBridge-ETL/0.1.0")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


# === EXTRACT ===

def extract_git_commits(limit: int = 5) -> List[Dict]:
    """Extract recent git commits as structured data."""
    try:
        result = subprocess.run(
            ["git", "log", f"-{limit}", "--pretty=format:{json.dumps({'hash': '%H', 'author': '%an', 'email': '%ae', 'date': '%ai', 'message': '%s'})}"],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=10
        )
        commits = []
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                try:
                    commits.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        logger.info(f"EXTRACT git: {len(commits)} commits")
        return commits
    except Exception as e:
        logger.error(f"EXTRACT git failed: {e}")
        return []


def extract_code_files(pattern: str = "*.py", limit: int = 10) -> List[Dict]:
    """Extract code files with metadata."""
    files = []
    for py in sorted(REPO_ROOT.rglob(pattern))[:limit]:
        if "__pycache__" in str(py) or ".git" in str(py):
            continue
        try:
            content = py.read_text()[:5000]
            lines = content.count("\n")
            files.append({
                "path": str(py.relative_to(REPO_ROOT)),
                "lines": lines,
                "size_bytes": py.stat().st_size,
                "content_preview": content[:500],
                "modified": datetime.fromtimestamp(py.stat().st_mtime).isoformat(),
            })
        except Exception:
            pass
    logger.info(f"EXTRACT code: {len(files)} files")
    return files


def extract_bridge_tasks() -> List[Dict]:
    """Extract pending + recently completed tasks from bridge."""
    pending = _api("GET", "/tasks/pending").get("tasks", [])
    stats = _api("GET", "/stats")
    logger.info(f"EXTRACT bridge: {len(pending)} pending tasks, stats={json.dumps(stats)}")
    return pending


def extract_test_results() -> Dict:
    """Extract test results by running pytest."""
    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", "test_agent_bridge.py", "--tb=short", "-q"],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=60
        )
        output = result.stdout + result.stderr
        passed = output.count(" passed")
        failed = output.count(" failed")
        errors = output.count(" error")
        data = {
            "exit_code": result.returncode,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "output_preview": output[:1000],
            "timestamp": now_iso(),
        }
        logger.info(f"EXTRACT tests: {passed} passed, {failed} failed, {errors} errors")
        return data
    except Exception as e:
        logger.error(f"EXTRACT tests failed: {e}")
        return {"error": str(e)}


def extract_chatgpt_responses() -> List[Dict]:
    """Extract unread ChatGPT responses from bridge."""
    unread = _api("GET", "/responses/unread").get("responses", [])
    logger.info(f"EXTRACT chatgpt: {len(unread)} unread responses")
    return unread


# === TRANSFORM (Groq-powered) ===

def transform_summarize(data: str, context: str = "") -> str:
    """Use Groq to summarize arbitrary text data."""
    result = groq_chat(
        f"Summarize this data concisely. Context: {context}\n\nData:\n{data[:3000]}",
        system="You are an ETL transform agent. Be concise, structured, and actionable.",
        model="llama-3.3-70b-versatile"
    )
    return result.get("response", f"Transform failed: {result.get('error')}")


def transform_classify_severity(text: str) -> Dict:
    """Use Groq to classify severity of issues in text."""
    result = groq_chat(
        f"Classify the severity of issues in this text. Return JSON with fields: severity (critical/high/medium/low), category (bug/security/performance/style/other), summary.\n\nText:\n{text[:2000]}",
        system="You are a severity classifier. Respond ONLY with valid JSON.",
        model="llama-3.1-8b-instant"
    )
    resp = result.get("response", "{}")
    try:
        return json.loads(resp)
    except json.JSONDecodeError:
        return {"severity": "unknown", "category": "unknown", "summary": resp[:200]}


def transform_code_analysis(code: str, filename: str = "") -> str:
    """Use Groq to analyze code quality."""
    result = groq_chat(
        f"Analyze this code file: {filename}\n\nCode:\n{code[:3000]}\n\nProvide: quality score (1-10), issues found, suggested improvements.",
        system="You are a code quality analyzer. Be specific and concise.",
        model="llama-3.3-70b-versatile"
    )
    return result.get("response", f"Analysis failed: {result.get('error')}")


def transform_commit_analysis(commits: List[Dict]) -> str:
    """Use Groq to analyze git commit history."""
    commit_text = "\n".join(f"- {c['hash'][:8]} by {c['author']}: {c['message']}" for c in commits)
    result = groq_chat(
        f"Analyze this git commit history. Identify: patterns, risk areas, velocity, and recommendations.\n\nCommits:\n{commit_text}",
        system="You are a devops analyzer. Be concise.",
        model="llama-3.3-70b-versatile"
    )
    return result.get("response", f"Analysis failed: {result.get('error')}")


def transform_test_analysis(test_results: Dict) -> str:
    """Use Groq to analyze test results."""
    result = groq_chat(
        f"Analyze these test results. Assess health, identify failures, suggest fixes.\n\nResults:\n{json.dumps(test_results, indent=2)[:2000]}",
        system="You are a test analyst. Be concise and actionable.",
        model="llama-3.1-8b-instant"
    )
    return result.get("response", f"Analysis failed: {result.get('error')}")


# === LOAD ===

def load_to_bridge(key: str, value: Any, source: str = "etl") -> Dict:
    """Load transformed data back to bridge as a task for review."""
    result = _api("POST", "/tasks", {
        "direction": "to_chatgpt",
        "sender": f"etl_pipeline",
        "prompt": f"[ETL:{key}]\n\n{value if isinstance(value, str) else json.dumps(value, indent=2)}",
        "context": f"ETL pipeline output from source: {source}",
        "priority": 7,
    })
    logger.info(f"LOAD bridge: {key} -> task {result.get('id', '?')}")
    return result


def load_etl_record(record: Dict) -> str:
    """Load ETL record to SQLite-backed storage via bridge stats endpoint."""
    etl_log = Path(__file__).parent / "data" / "etl_records.jsonl"
    etl_log.parent.mkdir(parents=True, exist_ok=True)
    with open(etl_log, "a") as f:
        f.write(json.dumps(record) + "\n")
    logger.info(f"LOAD record: {record['cycle_id']} -> {etl_log}")
    return str(etl_log)


# === PIPELINE ORCHESTRATION ===

def run_etl_cycle(sources: List[str] = None) -> Dict:
    """Run one full ETL cycle: Extract → Transform → Load."""
    sources = sources or ["git", "code", "bridge", "tests", "chatgpt"]
    cycle_id = f"etl_{int(time.time())}"
    started = time.time()
    logger.info(f"=== ETL CYCLE {cycle_id} START ===")

    results = {"cycle_id": cycle_id, "started": now_iso(), "stages": {}}

    # EXTRACT
    extracted = {}
    if "git" in sources:
        extracted["git_commits"] = extract_git_commits()
    if "code" in sources:
        extracted["code_files"] = extract_code_files()
    if "bridge" in sources:
        extracted["bridge_tasks"] = extract_bridge_tasks()
    if "tests" in sources:
        extracted["test_results"] = extract_test_results()
    if "chatgpt" in sources:
        extracted["chatgpt_responses"] = extract_chatgpt_responses()

    results["stages"]["extract"] = {k: len(v) if isinstance(v, list) else 1 for k, v in extracted.items()}

    # TRANSFORM
    transformed = {}

    if extracted.get("git_commits"):
        transformed["commit_analysis"] = transform_commit_analysis(extracted["git_commits"])

    if extracted.get("code_files"):
        top_file = extracted["code_files"][0]
        transformed["code_analysis"] = transform_code_analysis(top_file["content_preview"], top_file["path"])

    if extracted.get("test_results"):
        transformed["test_analysis"] = transform_test_analysis(extracted["test_results"])

    if extracted.get("chatgpt_responses"):
        combined = "\n".join(r.get("content", "")[:200] for r in extracted["chatgpt_responses"][:5])
        transformed["chatgpt_summary"] = transform_summarize(combined, "ChatGPT responses from bridge")

    if extracted.get("bridge_tasks"):
        task_summary = "\n".join(f"- {t['direction']}: {t['prompt'][:80]}" for t in extracted["bridge_tasks"][:10])
        transformed["queue_summary"] = transform_summarize(task_summary, "Bridge task queue")

    results["stages"]["transform"] = {k: len(v) for k, v in transformed.items()}

    # LOAD
    loaded = {}
    for key, value in transformed.items():
        load_to_bridge(key, value, source=cycle_id)
        loaded[key] = True

    # Load ETL record
    elapsed = round(time.time() - started, 2)
    record = {
        "cycle_id": cycle_id,
        "timestamp": now_iso(),
        "elapsed_s": elapsed,
        "sources": sources,
        "extracted": results["stages"]["extract"],
        "transformed": results["stages"]["transform"],
        "loaded": list(loaded.keys()),
    }
    load_etl_record(record)

    results["elapsed_s"] = elapsed
    results["completed"] = now_iso()
    logger.info(f"=== ETL CYCLE {cycle_id} DONE ({elapsed}s) ===")
    return results


def run_continuous(interval: float = 60, sources: List[str] = None, bridge_url: str = BRIDGE_URL):
    """Run ETL pipeline continuously."""
    logger.info(f"AGI ETL Pipeline starting (interval={interval}s)")
    logger.info(f"Sources: {sources or 'all'}")
    logger.info(f"Bridge: {BRIDGE_URL}")

    # Health check
    health = _api("GET", "/health")
    if "error" in health:
        logger.error(f"Cannot reach bridge: {health['error']}")
        return
    logger.info(f"Bridge healthy: {health.get('status')}")

    while True:
        try:
            results = run_etl_cycle(sources)
            logger.info(f"Cycle complete: {results['elapsed_s']}s, {len(results.get('loaded', []))} records loaded")
        except Exception as e:
            logger.error(f"ETL cycle error: {e}")

        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="AGI ETL Pipeline — Extract, Transform, Load with Groq LLM")
    parser.add_argument("--bridge-url", default=BRIDGE_URL)
    parser.add_argument("--interval", type=float, default=60, help="Seconds between ETL cycles")
    parser.add_argument("--once", action="store_true", help="Run one ETL cycle then exit")
    parser.add_argument("--source", nargs="*", default=None, help="Sources: git code bridge tests chatgpt")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.once:
        results = run_etl_cycle(args.source)
        print(json.dumps(results, indent=2))
    else:
        run_continuous(args.interval, args.source, args.bridge_url)


if __name__ == "__main__":
    main()
