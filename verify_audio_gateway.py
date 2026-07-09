#!/usr/bin/env python3
"""
Verify all JORKI Audio Gateway endpoints end-to-end.
Tests: upload → meta → fingerprint → transcript-shadow → speakers → search → chunk → glyph → ladder → receipt → claim → escrow → reveal → settle
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

BASE = "http://localhost:7861"
AUDIO_FILE = os.path.join(os.path.dirname(__file__), "audio_cascade", "workspace", "raw_audio.wav")
RESULTS = []


def test(name, method, path, data=None, expected_keys=None):
    url = BASE + path
    try:
        if method == "GET":
            req = urllib.request.Request(url, method="GET")
        else:
            body = json.dumps(data).encode() if data else b""
            req = urllib.request.Request(url, data=body, method="POST")
            req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=30) as resp:
            r = json.loads(resp.read().decode())
            ok = True
            if expected_keys:
                for k in expected_keys:
                    if k not in r:
                        ok = False
                        RESULTS.append(("FAIL", name, f"missing key: {k}"))
                        return
            if ok:
                RESULTS.append(("PASS", name, ""))
                return r
    except urllib.error.HTTPError as e:
        err = e.read().decode()[:200]
        RESULTS.append(("FAIL", name, f"HTTP {e.code}: {err}"))
    except Exception as e:
        RESULTS.append(("FAIL", name, str(e)[:200]))
    return None


def main():
    if not os.path.exists(AUDIO_FILE):
        print(f"Audio file not found: {AUDIO_FILE}")
        sys.exit(1)

    print("JORKI AUDIO GATEWAY — FULL VERIFICATION")
    print("=" * 60)

    # Health
    test("health", "GET", "/audio/health", expected_keys=["status"])

    # Upload (multipart — use curl)
    print("\n  Uploading audio...")
    r = subprocess.run(
        ["curl", "-s", "-X", "POST", f"{BASE}/audio/upload",
         "-F", f"file=@{AUDIO_FILE}"],
        capture_output=True, text=True, timeout=30
    )
    if r.returncode == 0 and r.stdout:
        resp = json.loads(r.stdout)
        audio_id = resp.get("audio_id")
        if audio_id:
            RESULTS.append(("PASS", "upload", f"audio_id={audio_id}"))
        else:
            RESULTS.append(("FAIL", "upload", r.stdout[:200]))
            sys.exit(1)
    else:
        RESULTS.append(("FAIL", "upload", "curl failed"))
        sys.exit(1)

    print(f"  audio_id: {audio_id}")

    # Meta
    test("meta", "GET", f"/audio/meta/{audio_id}", expected_keys=["sha256", "duration_seconds"])

    # Fingerprint
    test("fingerprint", "GET", f"/audio/fingerprint/{audio_id}", expected_keys=["fingerprint_hash", "band_energies"])

    # Transcript shadow
    test("transcript-shadow", "GET", f"/audio/transcript-shadow/{audio_id}", expected_keys=["transcript_hash"])

    # Speakers
    test("speakers", "GET", f"/audio/speakers/{audio_id}", expected_keys=["speaker_count"])

    # Search
    test("search", "GET", f"/audio/search/{audio_id}?q=test", expected_keys=["total_matches"])

    # Chunk
    test("chunk", "GET", f"/audio/chunk/{audio_id}/1.0", expected_keys=["chunk_hash"])

    # Glyph
    test("glyph", "GET", f"/audio/glyph/{audio_id}?level=6", expected_keys=["AUDIOGLYPH:v1"])

    # Ladder
    test("ladder", "GET", f"/audio/ladder/{audio_id}", expected_keys=["ladder"])

    # Receipt
    test("receipt", "GET", f"/audio/receipt/{audio_id}", expected_keys=["receipt_hash"])

    # List
    test("list", "GET", "/audio/list", expected_keys=["sessions"])

    # AFC Claim flow
    claim_resp = test("claim/create", "POST", "/audio/claim/create",
                      data={"audio_id": audio_id, "seller_id": "seller1", "claim_text": "This recording contains a test tone", "bond_amount": 100.0},
                      expected_keys=["claim_id"])
    claim_id = claim_resp.get("claim_id") if claim_resp else None

    if claim_id:
        test("claim/escrow", "POST", f"/audio/claim/{claim_id}/escrow",
             data={"buyer_id": "buyer1", "payment": 100.0},
             expected_keys=["status"])

        test("claim/reveal", "POST", f"/audio/claim/{claim_id}/reveal",
             expected_keys=["status"])

        settle_resp = test("claim/settle", "POST", f"/audio/claim/{claim_id}/settle",
                           data=[],
                           expected_keys=["result"])

    # Results
    print("\n" + "=" * 60)
    passed = sum(1 for r in RESULTS if r[0] == "PASS")
    failed = sum(1 for r in RESULTS if r[0] == "FAIL")
    print(f"\n  RESULTS: {passed}/{len(RESULTS)} passed, {failed} failed\n")
    print(f"  {'STATUS':<8} {'TEST':<25} {'DETAIL'}")
    print(f"  {'─'*8} {'─'*25} {'─'*30}")
    for status, name, detail in RESULTS:
        icon = "✅" if status == "PASS" else "❌"
        print(f"  {icon} {status:<6} {name:<25} {detail[:50]}")
    print()
    if failed > 0:
        sys.exit(1)
    else:
        print("  ALL TESTS PASSED ✅")


if __name__ == "__main__":
    main()
