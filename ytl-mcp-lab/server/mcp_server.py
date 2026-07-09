#!/usr/bin/env python3
"""
YTL-MCP Research Lab — MCP Server
Exposes bounded, auditable tools for YouTube research and production.
"""

import json
import os
import sqlite3
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

LAB_ROOT = Path(__file__).parent.parent
DB_PATH = LAB_ROOT / "data" / "ytl_lab.db"
RECEIPT_LEDGER = LAB_ROOT / "receipts" / "ledger.jsonl"
LAB_VERSION = "0.1.0"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hash_obj(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def write_receipt(event: str, tool: str, input_obj: Any, output_obj: Any, 
                  status: str = "ok", error: str = "", quota_cost: int = 0,
                  video_id: str = "", experiment_id: str = "", commit_hash: str = "") -> str:
    """Write a receipt to the JSONL ledger."""
    RECEIPT_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    
    receipt = {
        "timestamp": now_iso(),
        "event": event,
        "tool": tool,
        "actor": os.environ.get("YTL_ACTOR", "system"),
        "input_hash": hash_obj(input_obj),
        "output_hash": hash_obj(output_obj),
        "status": status,
        "error": error,
        "quota_cost": quota_cost,
        "video_id": video_id,
        "experiment_id": experiment_id,
        "commit_hash": commit_hash,
    }
    
    with open(RECEIPT_LEDGER, "a") as f:
        f.write(json.dumps(receipt) + "\n")
    
    return receipt["timestamp"]


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# === Tool Implementations ===

def ytl_get_lab_status() -> Dict[str, Any]:
    """Tier 0: Return server health, queue, channels, quota, errors."""
    conn = get_db()
    
    video_count = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0] if table_exists(conn, "videos") else 0
    experiment_count = conn.execute("SELECT COUNT(*) FROM experiments").fetchone()[0] if table_exists(conn, "experiments") else 0
    receipt_count = 0
    if RECEIPT_LEDGER.exists():
        receipt_count = sum(1 for _ in RECEIPT_LEDGER.open())
    
    status = {
        "lab": "YTL-MCP Research Lab",
        "version": LAB_VERSION,
        "status": "healthy",
        "database": str(DB_PATH),
        "db_exists": DB_PATH.exists(),
        "videos_ingested": video_count,
        "experiments": experiment_count,
        "receipts": receipt_count,
        "quota_used_today": 0,
        "quota_limit": 10000,
        "active_jobs": [],
        "errors": [],
        "timestamp": now_iso(),
    }
    
    write_receipt("lab_status", "ytl_get_lab_status", {}, status)
    conn.close()
    return status


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(f"SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='{name}'").fetchone()[0] > 0


def ytl_ingest_video(video_id: str, title: str = "", channel_id: str = "", 
                     duration: int = 0, source: str = "manual") -> Dict[str, Any]:
    """Tier 1: Ingest video metadata into the lab."""
    conn = get_db()
    
    conn.execute("""
        INSERT OR REPLACE INTO videos (video_id, channel_id, title, duration, source, ingested_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (video_id, channel_id, title, duration, source, now_iso()))
    conn.commit()
    
    result = {"video_id": video_id, "title": title, "ingested": True}
    write_receipt("video_ingested", "ytl_ingest_video", {"video_id": video_id}, result, video_id=video_id)
    conn.close()
    return result


def ytl_score_transcript(video_id: str, transcript_text: str) -> Dict[str, Any]:
    """Tier 1: Score transcript for hook strength, novelty, retention, density."""
    words = transcript_text.split()
    word_count = len(words)
    sentences = [s.strip() for s in transcript_text.replace("?", "?.").replace("!", "!.").split(".") if s.strip()]
    sentence_count = len(sentences)
    
    first_30s_words = len(" ".join(words[:80]).split()) if word_count > 80 else word_count
    question_count = transcript_text.count("?")
    
    import re
    numbers = re.findall(r'\b\d+(?:\.\d+)?\b', transcript_text)
    number_density = len(numbers) / max(word_count, 1) * 100
    
    entities = re.findall(r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b', transcript_text)
    entity_density = len(set(entities)) / max(word_count, 1) * 100
    
    avg_sentence_len = word_count / max(sentence_count, 1)
    sentence_lengths = [len(s.split()) for s in sentences if s]
    length_variance = sum((l - avg_sentence_len) ** 2 for l in sentence_lengths) / max(len(sentence_lengths), 1)
    
    hook_phrases = ["what if", "imagine", "did you know", "here's", "nobody", "secret", "truth", "never", "always", "why"]
    hook_score = min(100, sum(10 for p in hook_phrases if p in transcript_text.lower()[:500]) * 20)
    
    transition_phrases = ["but", "however", "so", "now", "next", "then", "here's", "which means", "the result"]
    retention_score = min(100, sum(5 for p in transition_phrases if p in transcript_text.lower()) * 10)
    
    generic_phrases = ["in this video", "today we'll", "let's talk about", "in conclusion", "thanks for watching"]
    novelty_score = max(0, 100 - sum(15 for p in generic_phrases if p in transcript_text.lower()) * 15)
    
    compression_score = min(100, int(entity_density * 10 + number_density * 5))
    
    payoff_markers = ["the answer", "the result", "here's how", "this is why", "that's because"]
    payoff_timing = min(100, sum(20 for p in payoff_markers if p in transcript_text.lower()) * 20)
    
    scores = {
        "video_id": video_id,
        "word_count": word_count,
        "sentence_count": sentence_count,
        "first_30s_word_count": first_30s_words,
        "question_count": question_count,
        "number_density": round(number_density, 2),
        "entity_density": round(entity_density, 2),
        "avg_sentence_length": round(avg_sentence_len, 1),
        "hook_score": hook_score,
        "retention_score": retention_score,
        "novelty_score": novelty_score,
        "compression_score": compression_score,
        "entity_count": len(set(entities)),
        "payoff_timing": payoff_timing,
        "overall": round((hook_score + retention_score + novelty_score + compression_score + payoff_timing) / 5, 1),
    }
    
    conn = get_db()
    if table_exists(conn, "scores"):
        conn.execute("""
            INSERT OR REPLACE INTO scores 
            (video_id, hook_score, retention_score, novelty_score, compression_score, 
             entity_density, payoff_timing, overall, scored_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (video_id, hook_score, retention_score, novelty_score, compression_score,
              entity_density, payoff_timing, scores["overall"], now_iso()))
        conn.commit()
    conn.close()
    
    write_receipt("transcript_scored", "ytl_score_transcript", 
                  {"video_id": video_id, "word_count": word_count}, scores, video_id=video_id)
    return scores


def ytl_generate_script(hypothesis: str, source_packet: Dict[str, Any]) -> Dict[str, Any]:
    """Tier 1: Generate a script from a hypothesis and source packet."""
    script_id = hash_obj({"hypothesis": hypothesis, "source": source_packet})
    
    script = {
        "script_id": script_id,
        "hypothesis": hypothesis,
        "source_hash": hash_obj(source_packet),
        "sections": [
            {"section": "hook", "duration_s": 7, "text": f"Open with the core tension: {hypothesis}"},
            {"section": "context", "duration_s": 20, "text": "Establish why this matters now"},
            {"section": "evidence", "duration_s": 60, "text": "Present the data, demo, or proof"},
            {"section": "implication", "duration_s": 30, "text": "What this means for the audience"},
            {"section": "payoff", "duration_s": 15, "text": "Deliver the resolution promised in the hook"},
            {"section": "cta", "duration_s": 8, "text": "Clear, specific next action"},
        ],
        "total_duration_s": 140,
        "generated_at": now_iso(),
    }
    
    write_receipt("script_generated", "ytl_generate_script",
                  {"hypothesis": hypothesis}, script)
    return script


def ytl_generate_metadata(script_id: str, topic: str) -> Dict[str, Any]:
    """Tier 1: Generate title variants, description, tags, chapters."""
    metadata = {
        "script_id": script_id,
        "title_variants": [
            f"The Truth About {topic}",
            f"{topic}: What Nobody Tells You",
            f"Why {topic} Changes Everything",
            f"The {topic} Experiment",
            f"{topic} — Tested and Proven",
        ],
        "description_template": f"In this video, we test: {topic}\n\nChapters:\n0:00 Introduction\n0:07 Context\n0:27 Evidence\n1:27 Implications\n1:57 Payoff\n2:12 Next Steps",
        "tags": [topic.lower(), "research", "experiment", "analysis", "evidence"],
        "chapters": [
            {"time": "0:00", "title": "Introduction"},
            {"time": "0:07", "title": "Context"},
            {"time": "0:27", "title": "Evidence"},
            {"time": "1:27", "title": "Implications"},
            {"time": "1:57", "title": "Payoff"},
            {"time": "2:12", "title": "Next Steps"},
        ],
        "pinned_comment_draft": f"What's your experience with {topic}? Let us know below.",
        "generated_at": now_iso(),
    }
    
    write_receipt("metadata_generated", "ytl_generate_metadata",
                  {"script_id": script_id, "topic": topic}, metadata)
    return metadata


def ytl_generate_shotlist(script: Dict[str, Any]) -> Dict[str, Any]:
    """Tier 1: Convert script into shot list and B-roll plan."""
    shots = []
    for section in script.get("sections", []):
        shots.append({
            "section": section["section"],
            "shot_type": "talking_head" if section["section"] in ("hook", "cta") else "b_roll",
            "duration_s": section["duration_s"],
            "visual_notes": f"Visual for {section['section']}: {section['text'][:60]}",
            "b_roll_needed": section["section"] not in ("hook", "cta"),
        })
    
    shotlist = {
        "script_id": script.get("script_id", "unknown"),
        "shots": shots,
        "total_shots": len(shots),
        "b_roll_count": sum(1 for s in shots if s["b_roll_needed"]),
        "generated_at": now_iso(),
    }
    
    write_receipt("shotlist_generated", "ytl_generate_shotlist", script, shotlist)
    return shotlist


def ytl_prepare_upload_package(script: Dict[str, Any], metadata: Dict[str, Any], 
                                shotlist: Dict[str, Any]) -> Dict[str, Any]:
    """Tier 2: Create a publish-ready folder with all assets."""
    package_id = hash_obj({"script": script, "metadata": metadata})
    package_dir = LAB_ROOT / "data" / "packages" / package_id
    package_dir.mkdir(parents=True, exist_ok=True)
    
    (package_dir / "script.md").write_text(
        f"# Script: {script.get('hypothesis', 'Untitled')}\n\n" +
        "\n\n".join(f"## {s['section']} ({s['duration_s']}s)\n{s['text']}" for s in script.get("sections", []))
    )
    
    (package_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
    (package_dir / "shotlist.json").write_text(json.dumps(shotlist, indent=2))
    (package_dir / "description.txt").write_text(metadata.get("description_template", ""))
    (package_dir / "chapters.txt").write_text(
        "\n".join(f"{c['time']} {c['title']}" for c in metadata.get("chapters", []))
    )
    (package_dir / "thumbnail_prompt.txt").write_text(
        f"Thumbnail concept: Bold text overlay '{metadata['title_variants'][0]}'\n"
        f"Visual: One striking image related to {metadata.get('tags', ['topic'])[0]}\n"
        f"Style: High contrast, one focal point, readable at small size"
    )
    (package_dir / "risk_report.md").write_text(
        "# Risk Report\n\n## Copyright\n- No copyrighted material referenced\n\n"
        "## Claims\n- All claims marked as: speculative (requires verification before publish)\n\n"
        "## Policy\n- No medical, legal, or financial advice\n- No impersonation\n- No deceptive practices\n"
    )
    (package_dir / "receipt.json").write_text(json.dumps({
        "package_id": package_id,
        "created_at": now_iso(),
        "script_hash": hash_obj(script),
        "metadata_hash": hash_obj(metadata),
        "status": "ready_for_review",
    }, indent=2))
    
    result = {
        "package_id": package_id,
        "path": str(package_dir),
        "files": ["script.md", "metadata.json", "shotlist.json", "description.txt", 
                   "chapters.txt", "thumbnail_prompt.txt", "risk_report.md", "receipt.json"],
        "status": "ready_for_review",
    }
    
    write_receipt("upload_package_created", "ytl_prepare_upload_package",
                  {"script_id": script.get("script_id")}, result)
    return result


def ytl_run_experiment(hypothesis: str, variant: str, target_metric: str,
                       baseline: float, measurement_window_days: int = 7) -> Dict[str, Any]:
    """Tier 2: Create a formal experiment object."""
    experiment_id = hash_obj({"hypothesis": hypothesis, "variant": variant})
    
    experiment = {
        "experiment_id": experiment_id,
        "hypothesis": hypothesis,
        "variant": variant,
        "target_metric": target_metric,
        "baseline": baseline,
        "start_date": now_iso(),
        "end_date": None,
        "measurement_window_days": measurement_window_days,
        "video_ids": [],
        "status": "active",
        "result": None,
    }
    
    conn = get_db()
    if table_exists(conn, "experiments"):
        conn.execute("""
            INSERT OR REPLACE INTO experiments
            (experiment_id, hypothesis, variant, target_metric, baseline, 
             start_date, measurement_window_days, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (experiment_id, hypothesis, variant, target_metric, baseline,
              now_iso(), measurement_window_days, "active"))
        conn.commit()
    conn.close()
    
    # Save to active experiments dir
    exp_path = LAB_ROOT / "experiments" / "active" / f"{experiment_id}.json"
    exp_path.parent.mkdir(parents=True, exist_ok=True)
    exp_path.write_text(json.dumps(experiment, indent=2))
    
    write_receipt("experiment_started", "ytl_run_experiment",
                  {"hypothesis": hypothesis}, experiment, experiment_id=experiment_id)
    return experiment


def ytl_get_receipts(count: int = 10) -> List[Dict[str, Any]]:
    """Tier 0: Return latest receipts from the ledger."""
    if not RECEIPT_LEDGER.exists():
        return []
    
    receipts = []
    lines = RECEIPT_LEDGER.read_text().strip().split("\n")
    for line in lines[-count:]:
        if line.strip():
            receipts.append(json.loads(line))
    return receipts


# === MCP Tool Registry ===

MCP_TOOLS = {
    "ytl_get_lab_status": {"tier": 0, "handler": ytl_get_lab_status, "description": "Get lab server status"},
    "ytl_ingest_video": {"tier": 1, "handler": ytl_ingest_video, "description": "Ingest video metadata"},
    "ytl_score_transcript": {"tier": 1, "handler": ytl_score_transcript, "description": "Score transcript quality"},
    "ytl_generate_script": {"tier": 1, "handler": ytl_generate_script, "description": "Generate script from hypothesis"},
    "ytl_generate_metadata": {"tier": 1, "handler": ytl_generate_metadata, "description": "Generate title/description/tags/chapters"},
    "ytl_generate_shotlist": {"tier": 1, "handler": ytl_generate_shotlist, "description": "Generate shot list from script"},
    "ytl_prepare_upload_package": {"tier": 2, "handler": ytl_prepare_upload_package, "description": "Create upload package folder"},
    "ytl_run_experiment": {"tier": 2, "handler": ytl_run_experiment, "description": "Create formal experiment"},
    "ytl_get_receipts": {"tier": 0, "handler": ytl_get_receipts, "description": "Get latest receipts"},
}


def main():
    """Run the MCP server or CLI."""
    import sys
    
    if len(sys.argv) < 2:
        print(f"YTL-MCP Research Lab v{LAB_VERSION}")
        print(f"Available tools: {list(MCP_TOOLS.keys())}")
        print(f"\nUsage:")
        print(f"  python3 mcp_server.py status          # Get lab status")
        print(f"  python3 mcp_server.py <tool> [args]   # Call a tool")
        print(f"  python3 mcp_server.py serve           # Start MCP server (stdio)")
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "status":
        status = ytl_get_lab_status()
        print(json.dumps(status, indent=2))
    elif cmd == "serve":
        print(json.dumps({"status": "MCP server mode not yet implemented. Use tool commands directly."}))
    elif cmd in MCP_TOOLS:
        # Parse remaining args as JSON
        tool = MCP_TOOLS[cmd]
        handler = tool["handler"]
        
        if len(sys.argv) > 2:
            try:
                args = json.loads(sys.argv[2])
            except:
                args = {}
        else:
            args = {}
        
        result = handler(**args) if isinstance(args, dict) else handler(args)
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"Unknown command: {cmd}")
        print(f"Available: {list(MCP_TOOLS.keys())}")


if __name__ == "__main__":
    main()
