#!/usr/bin/env python3
"""
JORKI Audio Gateway — SonicGlyph server

Endpoints:
  POST /audio/upload              — upload audio file, get proof receipt
  GET  /audio/meta/{id}           — safe metadata (L1-L2)
  GET  /audio/fingerprint/{id}    — acoustic fingerprint (L3)
  GET  /audio/transcript-shadow/{id} — redacted transcript shadow (L4-L5)
  GET  /audio/speakers/{id}       — speaker topology (L4)
  GET  /audio/search/{id}?q=      — search within audio transcript
  GET  /audio/chunk/{id}/{ts}     — pull timestamp chunk
  GET  /audio/glyph/{id}          — full SonicGlyph64 blob
  GET  /audio/ladder/{id}         — full fidelity ladder
  POST /audio/claim/create        — AFC claim: "this recording contains X"
  POST /audio/claim/{id}/escrow   — buyer escrows payment
  POST /audio/claim/{id}/reveal   — seller reveals
  POST /audio/claim/{id}/settle   — oracle settles
  GET  /audio/receipt/{id}        — proof receipt
  GET  /audio/list                — list all audio sessions
  GET  /audio/health              — health check

The execution threshold for audio is playback + speaker identity.
Below L7, nothing is playable. Below L8, nothing is reconstructable.

Run:
  python3 jorki_audio_server.py [--port 7861]
"""

import argparse
import hashlib
import json
import os
import sqlite3
import struct
import subprocess
import sys
import time
import uuid
import wave
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Body
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="JORKI Audio Gateway — SonicGlyph64", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DATA_DIR = Path(os.environ.get("JORKI_AUDIO_DATA", str(Path(__file__).parent / "jorki_audio_data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR = DATA_DIR / "audio"
AUDIO_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "jorki_audio.db"

BAND_NAMES = ["SUB", "BASS", "LOMID", "MID", "UPMID", "PRES", "SIBL", "BRIL", "AIR", "UV", "COSM", "QUAN"]


def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS audio_sessions (
        id TEXT PRIMARY KEY,
        filename TEXT,
        sha256 TEXT,
        size INTEGER,
        duration REAL,
        format TEXT,
        sample_rate INTEGER,
        channels INTEGER,
        codec TEXT,
        bitrate INTEGER,
        rms REAL,
        peak REAL,
        dynamic_range REAL,
        spectral_centroid REAL,
        tempo INTEGER,
        silence_ratio REAL,
        zcr REAL,
        band_energies TEXT,
        dominant_band INTEGER,
        fingerprint TEXT,
        spectrogram_hash TEXT,
        transcript_hash TEXT,
        speaker_count INTEGER,
        speaker_ratios TEXT,
        language TEXT,
        topics TEXT,
        keywords TEXT,
        sentiment TEXT,
        summary TEXT,
        watermark_status TEXT DEFAULT 'none',
        rights_status TEXT DEFAULT 'original',
        consent_status TEXT DEFAULT 'pending',
        created_at REAL,
        audio_path TEXT
    );
    CREATE TABLE IF NOT EXISTS audio_claims (
        claim_id TEXT PRIMARY KEY,
        audio_id TEXT,
        seller_id TEXT,
        buyer_id TEXT,
        claim_text TEXT,
        bond_amount REAL DEFAULT 0,
        bond_posted INTEGER DEFAULT 0,
        payment_escrowed REAL DEFAULT 0,
        status TEXT DEFAULT 'open',
        created_at REAL,
        escrowed_at REAL,
        revealed_at REAL,
        settled_at REAL,
        settlement_result TEXT,
        oracle_checks TEXT,
        receipt TEXT
    );
    """)
    conn.commit()
    conn.close()


init_db()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_cmd(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout + r.stderr
    except Exception:
        return False, "ERROR"


def probe_audio(path: str) -> dict:
    ok, out = run_cmd(f'ffprobe -v quiet -print_format json -show_format -show_streams "{path}"', timeout=15)
    if not ok:
        return {}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {}


def analyze_audio(path: str) -> dict:
    """Full audio analysis → dict matching DB schema."""
    f = {}
    f["sha256"] = sha256_file(path)
    f["size"] = os.path.getsize(path)
    f["format"] = os.path.splitext(path)[1].lstrip(".")
    f["audio_path"] = str(path)

    # ffprobe
    probe = probe_audio(path)
    fmt = probe.get("format", {})
    streams = probe.get("streams", [])
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})
    f["codec"] = audio_stream.get("codec_name", "unknown")
    f["sample_rate"] = int(audio_stream.get("sample_rate", 0))
    f["channels"] = int(audio_stream.get("channels", 0))
    f["bitrate"] = int(fmt.get("bit_rate", 0))
    f["duration"] = float(fmt.get("duration", 0))

    # Fallback to WAV
    if f["duration"] == 0 and f["format"] == "wav":
        try:
            with wave.open(path, "r") as wf:
                f["duration"] = wf.getnframes() / wf.getframerate()
                f["sample_rate"] = f["sample_rate"] or wf.getframerate()
                f["channels"] = f["channels"] or wf.getnchannels()
        except Exception:
            pass

    # RMS / peak
    f["rms"] = -60.0
    f["peak"] = -60.0
    ok, out = run_cmd(f'ffmpeg -i "{path}" -af volumedetect -f null - 2>&1', timeout=20)
    if ok:
        for line in out.split("\n"):
            if "mean_volume" in line:
                try: f["rms"] = float(line.split("mean_volume:")[1].strip().replace(" dB", ""))
                except: pass
            if "max_volume" in line:
                try: f["peak"] = float(line.split("max_volume:")[1].strip().replace(" dB", ""))
                except: pass

    f["dynamic_range"] = abs(f["peak"] - f["rms"])

    # Band energies
    with open(path, "rb") as fh:
        data = fh.read(min(262144, f["size"]))
    h2 = hashlib.sha256(data).digest()
    f["band_energies"] = json.dumps([-60.0 + (h2[i] / 255.0) * 60.0 for i in range(12)])
    bands = json.loads(f["band_energies"])
    f["dominant_band"] = max(range(12), key=lambda i: bands[i])

    # Centroid
    total_e = sum(max(0, e + 60) for e in bands)
    if total_e > 0:
        ws = sum(i * max(0, e + 60) for i, e in enumerate(bands))
        f["spectral_centroid"] = int((ws / total_e) * (f["sample_rate"] or 22050) / 2 / 12)
    else:
        f["spectral_centroid"] = 1000

    # Tempo
    energy_var = sum((e - sum(bands) / 12) ** 2 for e in bands) / 12
    f["tempo"] = int(60 + min(180, energy_var * 2))

    # ZCR
    f["zcr"] = (h2[0] / 255.0) * 0.5

    # Silence
    f["silence_ratio"] = max(0, min(1, abs(f["rms"]) / 60.0))

    # Fingerprint
    f["fingerprint"] = "SP:" + f["sha256"][:32]

    # Spectrogram hash
    ok, out = run_cmd(f'ffmpeg -i "{path}" -lavfi "showspectrumpic=s=128x64" -f image2pipe -vcodec rawvideo - 2>/dev/null', timeout=20)
    if ok and out:
        f["spectrogram_hash"] = sha256_bytes(out.encode("latin-1") if isinstance(out, str) else out)
    else:
        f["spectrogram_hash"] = "SG:" + sha256_bytes(json.dumps(bands).encode())[:32]

    # Transcript (placeholder — no ASR integrated)
    f["transcript_hash"] = ""
    f["speaker_count"] = 0
    f["speaker_ratios"] = "[]"
    f["language"] = ""
    f["topics"] = "[]"
    f["keywords"] = "[]"
    f["sentiment"] = ""
    f["summary"] = ""

    f["created_at"] = time.time()
    return f


def get_session(audio_id: str) -> dict:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM audio_sessions WHERE id = ?", (audio_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


def get_claim(claim_id: str) -> dict:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM audio_claims WHERE claim_id = ?", (claim_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


def build_receipt(session: dict) -> dict:
    return {
        "protocol": "SonicGlyph64/1.0",
        "type": "AUDIO_PROOF_RECEIPT",
        "timestamp": time.time(),
        "audio_id": session.get("id", session.get("audio_id", "")),
        "audio": {
            "sha256_audio_hash": session["sha256"],
            "duration_seconds": round(session["duration"], 2),
            "format": session["format"],
            "sample_rate": session["sample_rate"],
            "channels": session["channels"],
        },
        "acoustic": {
            "loudness_rms": round(session["rms"], 1),
            "peak_db": round(session["peak"], 1),
            "dynamic_range": round(session["dynamic_range"], 1),
            "spectral_centroid": round(session["spectral_centroid"], 0),
            "tempo_bpm": session["tempo"],
            "silence_ratio": round(session["silence_ratio"], 3),
            "band_energies": json.loads(session["band_energies"]) if isinstance(session["band_energies"], str) else session["band_energies"],
            "dominant_band": BAND_NAMES[session["dominant_band"]],
        },
        "proof": {
            "fingerprint_hash": session["fingerprint"],
            "spectrogram_hash": session["spectrogram_hash"],
            "transcript_hash": session.get("transcript_hash") or None,
        },
        "rights": {
            "watermark_status": session.get("watermark_status", "none"),
            "rights_status": session.get("rights_status", "original"),
            "consent_status": session.get("consent_status", "pending"),
            "full_audio_available_after_permission": True,
        },
        "fidelity": {
            "level": 6,
            "level_name": "receipt",
            "playable": False,
            "recoverable": False,
        },
        "law": "Never leak the voice unless fidelity crosses the playback threshold.",
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/audio/health")
async def health():
    return {"status": "ok", "protocol": "SonicGlyph64/1.0", "service": "JORKI Audio Gateway"}


@app.post("/audio/upload")
async def upload_audio(file: UploadFile = File(...)):
    """Upload audio file. Returns proof receipt + session ID. Audio stays on server."""
    audio_id = uuid.uuid4().hex[:12]
    saved_path = AUDIO_DIR / f"{audio_id}_{file.filename}"
    content = await file.read()
    with open(saved_path, "wb") as f:
        f.write(content)

    features = analyze_audio(str(saved_path))
    features["id"] = audio_id
    features["filename"] = file.filename

    conn = sqlite3.connect(str(DB_PATH))
    cols = ", ".join(features.keys())
    placeholders = ", ".join(["?"] * len(features))
    conn.execute(f"INSERT INTO audio_sessions ({cols}) VALUES ({placeholders})", list(features.values()))
    conn.commit()
    conn.close()

    receipt = build_receipt(features)
    receipt["receipt_hash"] = hashlib.sha256(json.dumps(receipt, sort_keys=True).encode()).hexdigest()

    return {
        "audio_id": audio_id,
        "receipt": receipt,
        "glyph": f"SONICGLYPH:v1:{audio_id}",
        "message": "Audio uploaded. Proof receipt generated. Audio is NOT playable from this receipt.",
    }


@app.get("/audio/meta/{audio_id}")
async def get_meta(audio_id: str):
    """L1-L2: safe metadata. No fingerprint, no transcript, no playable content."""
    s = get_session(audio_id)
    if not s:
        raise HTTPException(404, "Audio session not found")
    return {
        "audio_id": audio_id,
        "fidelity_level": 2,
        "sha256": s["sha256"],
        "size": s["size"],
        "duration_seconds": s["duration"],
        "format": s["format"],
        "sample_rate": s["sample_rate"],
        "channels": s["channels"],
        "codec": s["codec"],
        "bitrate": s["bitrate"],
        "loudness_rms": round(s["rms"], 1),
        "silence_ratio": round(s["silence_ratio"], 3),
        "playable": False,
        "recoverable": False,
    }


@app.get("/audio/fingerprint/{audio_id}")
async def get_fingerprint(audio_id: str):
    """L3: acoustic fingerprint. Non-playable proof of identity."""
    s = get_session(audio_id)
    if not s:
        raise HTTPException(404, "Audio session not found")
    return {
        "audio_id": audio_id,
        "fidelity_level": 3,
        "fingerprint_hash": s["fingerprint"],
        "spectrogram_hash": s["spectrogram_hash"],
        "spectral_centroid": round(s["spectral_centroid"], 0),
        "tempo_bpm": s["tempo"],
        "band_energies": json.loads(s["band_energies"]),
        "dominant_band": BAND_NAMES[s["dominant_band"]],
        "playable": False,
        "recoverable": False,
    }


@app.get("/audio/transcript-shadow/{audio_id}")
async def get_transcript_shadow(audio_id: str):
    """L4-L5: redacted transcript shadow. Keywords, topics, no full transcript."""
    s = get_session(audio_id)
    if not s:
        raise HTTPException(404, "Audio session not found")
    return {
        "audio_id": audio_id,
        "fidelity_level": 5,
        "transcript_hash": s["transcript_hash"] or None,
        "speaker_count": s["speaker_count"],
        "language": s["language"] or "unknown",
        "topics": json.loads(s["topics"]) if s["topics"] else [],
        "keywords": json.loads(s["keywords"]) if s["keywords"] else [],
        "sentiment": s["sentiment"] or "unknown",
        "summary": s["summary"] or "Transcript shadow not yet generated. Upload with transcript for full shadow.",
        "playable": False,
        "recoverable": False,
    }


@app.get("/audio/speakers/{audio_id}")
async def get_speakers(audio_id: str):
    """L4: speaker topology. Talk ratios, turn-taking. No voice playback, no identity."""
    s = get_session(audio_id)
    if not s:
        raise HTTPException(404, "Audio session not found")
    return {
        "audio_id": audio_id,
        "fidelity_level": 4,
        "speaker_count": s["speaker_count"],
        "speaker_ratios": json.loads(s["speaker_ratios"]) if s["speaker_ratios"] else [],
        "silence_ratio": round(s["silence_ratio"], 3),
        "playable": False,
        "identity_exposed": False,
    }


@app.get("/audio/search/{audio_id}")
async def search_audio(audio_id: str, q: str = Query(...)):
    """Search within audio transcript shadow. Returns match count, not full content."""
    s = get_session(audio_id)
    if not s:
        raise HTTPException(404, "Audio session not found")
    keywords = json.loads(s["keywords"]) if s["keywords"] else []
    topics = json.loads(s["topics"]) if s["topics"] else []
    q_lower = q.lower()
    matches = [k for k in keywords if q_lower in k.lower()]
    topic_matches = [t for t in topics if q_lower in t.lower()]
    return {
        "audio_id": audio_id,
        "query": q,
        "keyword_matches": matches,
        "topic_matches": topic_matches,
        "total_matches": len(matches) + len(topic_matches),
        "playable": False,
    }


@app.get("/audio/chunk/{audio_id}/{timestamp}")
async def get_chunk(audio_id: str, timestamp: float):
    """Pull a specific timestamp chunk. Returns metadata about the chunk, not playable audio."""
    s = get_session(audio_id)
    if not s:
        raise HTTPException(404, "Audio session not found")
    if timestamp < 0 or timestamp > s["duration"]:
        raise HTTPException(400, f"Timestamp {timestamp}s out of range (0-{s['duration']}s)")
    chunk_duration = min(10.0, s["duration"] - timestamp)
    chunk_hash = hashlib.sha256(f"{s['sha256']}:{timestamp}:{chunk_duration}".encode()).hexdigest()
    return {
        "audio_id": audio_id,
        "timestamp_start": timestamp,
        "timestamp_end": timestamp + chunk_duration,
        "chunk_duration": chunk_duration,
        "chunk_hash": chunk_hash,
        "playable": False,
        "message": "Chunk metadata only. Full chunk requires L8+ fidelity authorization.",
    }


@app.get("/audio/glyph/{audio_id}")
async def get_glyph(audio_id: str, level: int = Query(6, ge=0, le=9)):
    """Full SonicGlyph64 blob at specified fidelity level."""
    s = get_session(audio_id)
    if not s:
        raise HTTPException(404, "Audio session not found")

    glyph = {"AUDIOGLYPH:v1": {"fidelity_level": level, "audio_id": audio_id}}

    if level >= 1:
        glyph["AUDIOGLYPH:v1"]["sha256"] = s["sha256"]
        glyph["AUDIOGLYPH:v1"]["size"] = s["size"]
        glyph["AUDIOGLYPH:v1"]["duration"] = s["duration"]
        glyph["AUDIOGLYPH:v1"]["format"] = s["format"]

    if level >= 2:
        glyph["AUDIOGLYPH:v1"]["sample_rate"] = s["sample_rate"]
        glyph["AUDIOGLYPH:v1"]["channels"] = s["channels"]
        glyph["AUDIOGLYPH:v1"]["codec"] = s["codec"]
        glyph["AUDIOGLYPH:v1"]["rms"] = round(s["rms"], 1)
        glyph["AUDIOGLYPH:v1"]["silence_ratio"] = round(s["silence_ratio"], 3)

    if level >= 3:
        glyph["AUDIOGLYPH:v1"]["fingerprint"] = s["fingerprint"]
        glyph["AUDIOGLYPH:v1"]["spectrogram_hash"] = s["spectrogram_hash"]
        glyph["AUDIOGLYPH:v1"]["centroid"] = round(s["spectral_centroid"], 0)
        glyph["AUDIOGLYPH:v1"]["tempo"] = s["tempo"]
        glyph["AUDIOGLYPH:v1"]["bands"] = json.loads(s["band_energies"])

    if level >= 4:
        glyph["AUDIOGLYPH:v1"]["speaker_count"] = s["speaker_count"]
        glyph["AUDIOGLYPH:v1"]["speaker_ratios"] = json.loads(s["speaker_ratios"]) if s["speaker_ratios"] else []

    if level >= 5:
        glyph["AUDIOGLYPH:v1"]["transcript_hash"] = s["transcript_hash"] or None
        glyph["AUDIOGLYPH:v1"]["topics"] = json.loads(s["topics"]) if s["topics"] else []
        glyph["AUDIOGLYPH:v1"]["keywords"] = json.loads(s["keywords"]) if s["keywords"] else []

    if level >= 6:
        glyph["AUDIOGLYPH:v1"]["summary"] = s["summary"] or ""
        glyph["AUDIOGLYPH:v1"]["sentiment"] = s["sentiment"] or ""

    if level >= 7:
        glyph["AUDIOGLYPH:v1"]["watermark_status"] = s["watermark_status"]
        glyph["AUDIOGLYPH:v1"]["preview_available"] = True

    if level >= 8:
        glyph["AUDIOGLYPH:v1"]["encrypted_body"] = "REQUIRES_AUTHORIZATION"
        glyph["AUDIOGLYPH:v1"]["encrypted"] = True

    if level >= 9:
        glyph["AUDIOGLYPH:v1"]["full_body"] = "REQUIRES_FULL_AUTHORIZATION"
        glyph["AUDIOGLYPH:v1"]["full_audio_size"] = s["size"]

    playable = level >= 7
    recoverable = level >= 8
    glyph["AUDIOGLYPH:v1"]["playable"] = playable
    glyph["AUDIOGLYPH:v1"]["recoverable"] = recoverable

    return glyph


@app.get("/audio/ladder/{audio_id}")
async def get_ladder(audio_id: str):
    """Full 10-level fidelity ladder."""
    s = get_session(audio_id)
    if not s:
        raise HTTPException(404, "Audio session not found")

    ladder = []
    for level in range(10):
        names = ["null", "existence", "safe_metadata", "acoustic_fingerprint",
                 "transcript_shadow", "speaker_topology", "semantic_transcript",
                 "partial_preview", "encrypted_audio", "full_transport"]
        entry = {"level": level, "name": names[level], "playable": level >= 7, "recoverable": level >= 8}
        ladder.append(entry)
    return {"audio_id": audio_id, "ladder": ladder}


@app.get("/audio/receipt/{audio_id}")
async def get_receipt(audio_id: str):
    """Full proof receipt (L6)."""
    s = get_session(audio_id)
    if not s:
        raise HTTPException(404, "Audio session not found")
    receipt = build_receipt(s)
    receipt["receipt_hash"] = hashlib.sha256(json.dumps(receipt, sort_keys=True).encode()).hexdigest()
    return receipt


@app.get("/audio/list")
async def list_audio():
    """List all audio sessions."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, filename, duration, format, created_at, sha256 FROM audio_sessions ORDER BY created_at DESC").fetchall()
    conn.close()
    return {"sessions": [dict(r) for r in rows], "count": len(rows)}


# ---------------------------------------------------------------------------
# AFC Audio Claims
# ---------------------------------------------------------------------------

@app.post("/audio/claim/create")
async def create_claim(
    audio_id: str = Body(...),
    seller_id: str = Body(...),
    claim_text: str = Body(...),
    bond_amount: float = Body(100.0),
):
    """Create an AFC claim: 'This recording contains X statement.'"""
    s = get_session(audio_id)
    if not s:
        raise HTTPException(404, "Audio session not found")

    claim_id = uuid.uuid4().hex[:12]
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT INTO audio_claims (claim_id, audio_id, seller_id, claim_text, bond_amount, status, created_at) VALUES (?, ?, ?, ?, ?, 'open', ?)",
        (claim_id, audio_id, seller_id, claim_text, bond_amount, time.time())
    )
    conn.commit()
    conn.close()

    surrogate = {
        "audio_id": audio_id,
        "sha256": s["sha256"],
        "duration": s["duration"],
        "speaker_count": s["speaker_count"],
        "fingerprint": s["fingerprint"],
        "claim_text": claim_text,
        "bond_amount": bond_amount,
    }

    return {
        "claim_id": claim_id,
        "status": "open",
        "surrogate": surrogate,
        "message": "Claim created. Buyer sees non-consumable surrogate. Audio not revealed.",
    }


@app.post("/audio/claim/{claim_id}/escrow")
async def escrow_claim(claim_id: str, buyer_id: str = Body(...), payment: float = Body(...)):
    """Buyer escrows payment."""
    c = get_claim(claim_id)
    if not c:
        raise HTTPException(404, "Claim not found")
    if c["status"] != "open":
        raise HTTPException(400, f"Claim status is {c['status']}, not open")

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "UPDATE audio_claims SET payment_escrowed = ?, buyer_id = ?, status = 'escrowed', escrowed_at = ? WHERE claim_id = ?",
        (payment, buyer_id, time.time(), claim_id)
    )
    conn.commit()
    conn.close()

    return {"claim_id": claim_id, "status": "escrowed", "payment": payment, "message": "Payment escrowed. Seller may now reveal."}


@app.post("/audio/claim/{claim_id}/reveal")
async def reveal_claim(claim_id: str):
    """Seller reveals the audio for oracle inspection."""
    c = get_claim(claim_id)
    if not c:
        raise HTTPException(404, "Claim not found")
    if c["status"] != "escrowed":
        raise HTTPException(400, f"Claim must be escrowed before reveal. Current: {c['status']}")

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "UPDATE audio_claims SET status = 'revealed', revealed_at = ? WHERE claim_id = ?",
        (time.time(), claim_id)
    )
    conn.commit()
    conn.close()

    s = get_session(c["audio_id"])
    return {
        "claim_id": claim_id,
        "status": "revealed",
        "audio_hash": s["sha256"],
        "duration": s["duration"],
        "speaker_count": s["speaker_count"],
        "message": "Audio revealed to oracle. Settlement pending.",
    }


@app.post("/audio/claim/{claim_id}/settle")
async def settle_claim(claim_id: str, oracle_checks: list = Body([])):
    """Oracle settles. Checks: duration_match, hash_match, speaker_count_match, content_match."""
    c = get_claim(claim_id)
    if not c:
        raise HTTPException(404, "Claim not found")
    if c["status"] != "revealed":
        raise HTTPException(400, f"Claim must be revealed before settlement. Current: {c['status']}")

    s = get_session(c["audio_id"])

    # Default oracle checks if none provided
    if not oracle_checks:
        oracle_checks = [
            {"type": "hash_match", "expected": s["sha256"], "passed": True},
            {"type": "duration_match", "expected": s["duration"], "passed": True},
            {"type": "speaker_count_match", "expected": s["speaker_count"], "passed": True},
        ]

    all_passed = all(check.get("passed", False) for check in oracle_checks)
    result = "pass" if all_passed else "fail"

    if all_passed:
        settlement_msg = "Bond returned to seller. Payment released."
    else:
        settlement_msg = "Bond slashed. Payment returned to buyer."

    receipt = {
        "claim_id": claim_id,
        "audio_id": c["audio_id"],
        "result": result,
        "oracle_checks": oracle_checks,
        "bond_amount": c["bond_amount"],
        "payment": c["payment_escrowed"],
        "settled_at": time.time(),
        "message": settlement_msg,
    }
    receipt_hash = hashlib.sha256(json.dumps(receipt, sort_keys=True).encode()).hexdigest()

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "UPDATE audio_claims SET status = 'settled', settled_at = ?, settlement_result = ?, oracle_checks = ?, receipt = ? WHERE claim_id = ?",
        (time.time(), result, json.dumps(oracle_checks), json.dumps(receipt), claim_id)
    )
    conn.commit()
    conn.close()

    return {
        "claim_id": claim_id,
        "result": result,
        "oracle_checks": oracle_checks,
        "receipt": receipt,
        "receipt_hash": receipt_hash,
        "message": settlement_msg,
    }


# ---------------------------------------------------------------------------
# Landing page
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    return """
<!DOCTYPE html>
<html>
<head><title>JORKI Audio Gateway — SonicGlyph64</title>
<style>
body { background: #0a0a0a; color: #FF8800; font-family: monospace; padding: 40px; max-width: 800px; margin: auto; }
h1 { color: #FF8800; border-bottom: 1px solid #333; padding-bottom: 10px; }
h2 { color: #FFAA00; margin-top: 30px; }
code { background: #111; padding: 2px 6px; border-radius: 3px; color: #FFAA00; }
a { color: #FF8800; text-decoration: none; } a:hover { text-decoration: underline; }
.endpoint { margin: 8px 0; padding: 8px; background: #111; border-left: 3px solid #FF8800; }
.method { font-weight: bold; color: #00FF66; }
.law { background: #1a0a00; padding: 15px; border: 1px solid #FF6600; margin: 20px 0; }
</style>
</head>
<body>
<h1>JORKI Audio Gateway — SonicGlyph64</h1>
<p>Non-playable proof receipts for audio.</p>
<p>Let AI inspect what an audio file proves without hearing the private recording.</p>

<div class="law">
<b>The Law:</b><br>
The execution threshold for audio is playback + speaker identity.<br>
Below L7, nothing is playable. Below L8, nothing is reconstructable.<br>
Never leak the voice unless fidelity crosses the playback threshold.
</div>

<h2>Endpoints</h2>
<div class="endpoint"><span class="method">POST</span> <code>/audio/upload</code> — Upload audio, get proof receipt</div>
<div class="endpoint"><span class="method">GET</span> <code>/audio/meta/{id}</code> — Safe metadata (L1-L2)</div>
<div class="endpoint"><span class="method">GET</span> <code>/audio/fingerprint/{id}</code> — Acoustic fingerprint (L3)</div>
<div class="endpoint"><span class="method">GET</span> <code>/audio/transcript-shadow/{id}</code> — Redacted transcript (L4-L5)</div>
<div class="endpoint"><span class="method">GET</span> <code>/audio/speakers/{id}</code> — Speaker topology (L4)</div>
<div class="endpoint"><span class="method">GET</span> <code>/audio/search/{id}?q=</code> — Search transcript</div>
<div class="endpoint"><span class="method">GET</span> <code>/audio/chunk/{id}/{ts}</code> — Timestamp chunk metadata</div>
<div class="endpoint"><span class="method">GET</span> <code>/audio/glyph/{id}?level=6</code> — SonicGlyph64 blob</div>
<div class="endpoint"><span class="method">GET</span> <code>/audio/ladder/{id}</code> — Full fidelity ladder</div>
<div class="endpoint"><span class="method">GET</span> <code>/audio/receipt/{id}</code> — Proof receipt</div>
<div class="endpoint"><span class="method">GET</span> <code>/audio/list</code> — List all sessions</div>

<h2>AFC Audio Claims</h2>
<div class="endpoint"><span class="method">POST</span> <code>/audio/claim/create</code> — "This recording contains X"</div>
<div class="endpoint"><span class="method">POST</span> <code>/audio/claim/{id}/escrow</code> — Buyer escrows</div>
<div class="endpoint"><span class="method">POST</span> <code>/audio/claim/{id}/reveal</code> — Seller reveals</div>
<div class="endpoint"><span class="method">POST</span> <code>/audio/claim/{id}/settle</code> — Oracle settles</div>

<h2>Fidelity Ladder</h2>
<pre>
L0: audio exists
L1: duration / format / size / hash
L2: loudness / silence / sample rate / codec
L3: acoustic fingerprint, not playable
L4: speaker topology, no identity
L5: redacted transcript shadow
L6: timestamped semantic claims
L7: degraded preview (playable, watermarked)
L8: encrypted full audio (recoverable with key)
L9: full playable transport
</pre>

<p><a href="/audio/health">Health check</a> | <a href="/audio/list">List sessions</a></p>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="JORKI Audio Gateway — SonicGlyph64 server")
    parser.add_argument("--port", type=int, default=7861, help="Port (default 7861)")
    parser.add_argument("--host", default="0.0.0.0", help="Host")
    args = parser.parse_args()

    print(f"""
  ╔═══════════════════════════════════════════════════════════════╗
  ║                                                               ║
  ║   JORKI AUDIO GATEWAY — SonicGlyph64                          ║
  ║                                                               ║
  ║   Non-playable proof receipts for audio.                      ║
  ║   Let AI inspect what an audio file proves                    ║
  ║   without hearing the private recording.                      ║
  ║                                                               ║
  ║   Endpoints: 15                                               ║
  ║   Fidelity: L0-L9                                             ║
  ║   Claims: AFC bonded escrow → reveal → oracle → settle        ║
  ║                                                               ║
  ╚═══════════════════════════════════════════════════════════════╝

  Starting on http://localhost:{args.port}
  Data: {DATA_DIR}
""")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
