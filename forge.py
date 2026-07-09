#!/usr/bin/env python3
"""
Forge — CLI dispatcher for the Reality Compiler ecosystem.

Commands route to dedicated modules:
  compile/build/test  → glyphlang + overlang
  run                 → overlang
  jorki               → jorki
  glyphlock           → glyphlock
  audio               → audioglyph
  ziptoapp            → ziptoapp
  rc                  → reality_compiler
  pulse               → clientpulse
"""

import sys
import os
import json
import time
import hashlib
from pathlib import Path

from glyphlang import (
    GLYPH_TOKENS, OPERATORS, OPERATOR_RATIO,
    compile_glyph,
)
from overlang import (
    compile_over, parse_over, OverRuntime,
)


# =============================================================================
# Build tool commands
# =============================================================================

PROJECT_STRUCTURE = {
    "src/": ".glyph and .over source files",
    "build/": "Compiled artifacts (JSON)",
    "test/": "Test vectors",
    "receipts/": "Signed receipts with SHA256",
    "snapshots/": "Policy snapshots",
}


def cmd_init():
    """Initialize project structure."""
    print("GlyphForge — Initializing project")
    print(f"  Operator ratio: {len(OPERATORS)}/{len(GLYPH_TOKENS)} = {OPERATOR_RATIO:.1%}")
    print()

    for dirname, desc in PROJECT_STRUCTURE.items():
        path = Path(dirname)
        path.mkdir(exist_ok=True)
        print(f"  ✓ {dirname} — {desc}")

    example_glyph = Path("src/example.glyph")
    if not example_glyph.exists():
        example_glyph.write_text(
            "▷ HashVerify\n"
            "  ◇ → H\n"
            "  H ⊙ R\n"
            "  R ≡ ◎\n"
            "  ⊙̂ H\n"
            "◀\n"
        )
        print("  ✓ src/example.glyph — example glyph program")

    example_over = Path("src/example.over")
    if not example_over.exists():
        example_over.write_text(
            "# OverLanguage workflow: verify and pay\n"
            "workflow: VerifyPay\n"
            "intent: verify artifact hash and issue payment receipt\n"
            "step 1: index file → local_index\n"
            "step 2: compute hash → merkle_root\n"
            "step 3: verify hash ≡ canonical → verified\n"
            "step 4: issue receipt → signed_receipt\n"
            "artifact: signed_receipt\n"
            "receipt: SHA256 chained from step 1 to step 4\n"
            "value: verified artifact with payment proof\n"
        )
        print("  ✓ src/example.over — example workflow")

    config = Path("forge.json")
    if not config.exists():
        config.write_text(json.dumps({
            "compiler": "glyphforge",
            "version": "1.0.0",
            "operator_ratio": round(OPERATOR_RATIO, 4),
            "sources": {"glyph": "src/*.glyph", "over": "src/*.over"},
            "output": "build/",
            "receipts": "receipts/",
        }, indent=2))
        print("  ✓ forge.json — project config")

    print()
    print("Project initialized. Run: python3 forge.py build")


def cmd_compile(filepath: str):
    """Compile a single .glyph or .over file."""
    path = Path(filepath)
    if not path.exists():
        print(f"Error: {filepath} not found")
        sys.exit(1)

    source = path.read_text()
    ext = path.suffix

    if ext == ".glyph":
        print(f"Compiling {filepath} (.glyph)")
        artifact = compile_glyph(source, filename=path.name)
        print(f"  Glyphs: {artifact['glyph_count']}")
        print(f"  Operators: {artifact['operator_count']} ({artifact['operator_ratio']:.1%})")
        print(f"  Nodes: {artifact['node_count']}")
        print(f"  Compile time: {artifact['compile_time_ms']}ms")
        print(f"  SHA256: {artifact['sha256'][:16]}...")
    elif ext == ".over":
        print(f"Compiling {filepath} (.over)")
        artifact = compile_over(source, filename=path.name)
        print(f"  Workflow: {artifact['workflow_name']}")
        print(f"  Intent: {artifact['intent']}")
        print(f"  Steps: {artifact['step_count']}")
        print(f"  Receipts: {len(artifact['receipt_chain'])}")
        print(f"  Merkle root: {artifact['merkle_root'][:16]}...")
        print(f"  SHA256: {artifact['sha256'][:16]}...")
    else:
        print(f"Error: unknown file type {ext}")
        sys.exit(1)

    build_dir = Path("build")
    build_dir.mkdir(exist_ok=True)
    out_name = path.stem + ".json"
    out_path = build_dir / out_name
    out_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False))
    print(f"  Output: {out_path}")

    return artifact


def cmd_build():
    """Compile all sources in src/."""
    print("GlyphForge — Building all sources")
    print(f"  Operator ratio: {len(OPERATORS)}/{len(GLYPH_TOKENS)} = {OPERATOR_RATIO:.1%}")
    print()

    src_dir = Path("src")
    if not src_dir.exists():
        print("Error: src/ directory not found. Run: python3 forge.py init")
        sys.exit(1)

    glyph_files = sorted(src_dir.glob("*.glyph"))
    over_files = sorted(src_dir.glob("*.over"))
    all_files = glyph_files + over_files

    if not all_files:
        print("No .glyph or .over files found in src/")
        sys.exit(1)

    artifacts = []
    for f in all_files:
        source = f.read_text()
        ext = f.suffix
        if ext == ".glyph":
            artifact = compile_glyph(source, filename=f.name)
        else:
            artifact = compile_over(source, filename=f.name)
        artifacts.append(artifact)
        print(f"  ✓ {f.name} → build/{f.stem}.json  (SHA256: {artifact['sha256'][:12]}...)")

    build_dir = Path("build")
    manifest = {
        "build_time": time.time(),
        "file_count": len(all_files),
        "glyph_files": len(glyph_files),
        "over_files": len(over_files),
        "operator_ratio": round(OPERATOR_RATIO, 4),
        "artifacts": [
            {"file": a["source_file"], "sha256": a["sha256"], "type": a["type"]}
            for a in artifacts
        ],
    }
    manifest_str = json.dumps(manifest, sort_keys=True)
    manifest["sha256"] = hashlib.sha256(manifest_str.encode()).hexdigest()
    (build_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    print()
    print(f"Built {len(all_files)} files. Manifest: build/manifest.json")
    print(f"Build SHA256: {manifest['sha256'][:16]}...")


def cmd_test():
    """Run all test vectors in test/."""
    print("GlyphForge — Running tests")
    print()

    test_dir = Path("test")
    if not test_dir.exists():
        print("No test/ directory. Creating with default tests...")
        test_dir.mkdir(exist_ok=True)
        (test_dir / "test_hash.glyph").write_text(
            "▷ HashTest\n  ◇ → H\n  H ⊙ R\n  R ≡ ◎\n  ⊙̂ H\n◀\n"
        )
        (test_dir / "test_pay.glyph").write_text(
            "▷ PayTest\n  ◇ → $\n  $ Æ R\n  R → ◎\n  ¤ $\n◀\n"
        )
        (test_dir / "test_verify.over").write_text(
            "workflow: TestVerify\n"
            "intent: test verification workflow\n"
            "step 1: hash file → file_hash\n"
            "step 2: check hash → result\n"
            "artifact: result\n"
            "value: test passes if hash verified\n"
        )

    tests = sorted(test_dir.glob("*.glyph")) + sorted(test_dir.glob("*.over"))
    passed = 0
    failed = 0

    for t in tests:
        source = t.read_text()
        ext = t.suffix
        try:
            if ext == ".glyph":
                artifact = compile_glyph(source, filename=t.name)
                assert artifact["glyph_count"] > 0, "no glyphs found"
                assert artifact["sha256"], "no checksum"
            else:
                artifact = compile_over(source, filename=t.name)
                assert artifact["step_count"] > 0, "no steps"
                assert artifact["merkle_root"], "no merkle root"
            print(f"  ✓ {t.name} — PASSED")
            passed += 1
        except Exception as e:
            print(f"  ✕ {t.name} — FAILED: {e}")
            failed += 1

    print()
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")


def cmd_snapshot():
    """Emit JSON policy snapshot with SHA256."""
    print("GlyphForge — Emitting policy snapshot")
    print()

    build_dir = Path("build")
    if not build_dir.exists():
        print("Error: no build/ directory. Run: python3 forge.py build first.")
        sys.exit(1)

    manifest_path = build_dir / "manifest.json"
    if not manifest_path.exists():
        print("Error: no build manifest. Run: python3 forge.py build first.")
        sys.exit(1)

    manifest = json.loads(manifest_path.read_text())

    snapshot = {
        "snapshot_time": time.time(),
        "build_sha256": manifest.get("sha256", ""),
        "file_count": manifest.get("file_count", 0),
        "operator_ratio": manifest.get("operator_ratio", 0),
        "artifacts": manifest.get("artifacts", []),
        "policy": {
            "mode": "production",
            "supervisor": "shared",
            "models": ["PCA", "KMeans", "SVM", "RandomForest", "GradientBoosting", "XGBoost"],
            "dry_run": False,
        },
    }

    snapshot_str = json.dumps(snapshot, sort_keys=True)
    snapshot["sha256"] = hashlib.sha256(snapshot_str.encode()).hexdigest()

    snap_dir = Path("snapshots")
    snap_dir.mkdir(exist_ok=True)
    snap_name = f"snapshot_{int(time.time())}.json"
    snap_path = snap_dir / snap_name
    snap_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False))

    print(f"  Snapshot: {snap_path}")
    print(f"  SHA256: {snapshot['sha256']}")
    print(f"  Files: {snapshot['file_count']}")
    print(f"  Operator ratio: {snapshot['operator_ratio']:.1%}")
    print(f"  Policy: {snapshot['policy']['mode']} / {snapshot['policy']['supervisor']} supervisor")


def cmd_verify(receipt_path: str):
    """Verify a receipt or artifact checksum."""
    print(f"GlyphForge — Verifying {receipt_path}")
    print()

    path = Path(receipt_path)
    if not path.exists():
        print(f"Error: {receipt_path} not found")
        sys.exit(1)

    data = json.loads(path.read_text())
    stored_hash = data.pop("sha256", None)

    if not stored_hash:
        print("Error: no sha256 field found")
        sys.exit(1)

    recomputed = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    if recomputed == stored_hash:
        print(f"  ✓ VALID — SHA256 matches")
        print(f"  Stored:     {stored_hash}")
        print(f"  Recomputed: {recomputed}")
        print(f"  Type: {data.get('type', 'unknown')}")
        if "merkle_root" in data:
            print(f"  Merkle root: {data['merkle_root'][:16]}...")
        if "receipt_chain" in data:
            print(f"  Receipt chain: {len(data['receipt_chain'])} entries")
    else:
        print(f"  ✕ INVALID — SHA256 mismatch!")
        print(f"  Stored:     {stored_hash}")
        print(f"  Recomputed: {recomputed}")


def cmd_clean():
    """Remove build artifacts."""
    print("GlyphForge — Cleaning build artifacts")
    for dirname in ["build", "snapshots"]:
        d = Path(dirname)
        if d.exists():
            for f in d.glob("*.json"):
                f.unlink()
            print(f"  ✓ Cleaned {dirname}/")


# =============================================================================
# Module delegation wrappers
# =============================================================================

def cmd_run(filepath: str, args: list[str] | None = None):
    """Execute a .over workflow with real file I/O."""
    from overlang import cmd_run as _cmd_run
    _cmd_run(filepath, args)


def cmd_jorki(args: list[str] | None = None):
    """JORKI file gateway CLI."""
    from jorki import cmd_jorki as _cmd_jorki
    _cmd_jorki(args)


def cmd_glyphlock(args: list[str] | None = None):
    """GlyphLock time-gated codec CLI."""
    from glyphlock import cmd_glyphlock as _cmd_glyphlock
    _cmd_glyphlock(args)


def cmd_audio(args: list[str] | None = None):
    """AudioGlyph codec CLI."""
    from audioglyph import cmd_audio as _cmd_audio
    _cmd_audio(args)


def cmd_ziptoapp(args: list[str] | None = None):
    """ZipToApp CLI: render a .zip into a macOS .app bundle."""
    from ziptoapp import cmd_ziptoapp as _cmd_ziptoapp
    _cmd_ziptoapp(args)


def cmd_reality_compiler(args: list[str] | None = None):
    """Reality Compiler CLI — compile production events into LambdaReceipts."""
    import reality_compiler
    sys.argv = ["reality_compiler.py"] + (args or [])
    reality_compiler.cli()


def cmd_clientpulse(args: list[str] | None = None):
    """ClientPulse OS CLI — hourly evidence engine for profile conversion."""
    import clientpulse
    sys.argv = ["clientpulse.py"] + (args or [])
    clientpulse.cli()


def cmd_proofwallet(args: list[str] | None = None):
    """ProofWallet CLI — life proof wallet. Never lose the proof."""
    import proofwallet
    sys.argv = ["proofwallet.py"] + (args or [])
    proofwallet.main()


# =============================================================================
# Main dispatcher
# =============================================================================

def main():
    if len(sys.argv) < 2:
        print("Forge — CLI dispatcher for the Reality Compiler ecosystem")
        print(f"  Glyph operators: {len(OPERATORS)}/{len(GLYPH_TOKENS)} = {OPERATOR_RATIO:.1%}")
        print()
        print("Commands:")
        print("  python3 forge.py init                    Initialize project")
        print("  python3 forge.py compile <file>          Compile .glyph or .over")
        print("  python3 forge.py build                   Build all sources in src/")
        print("  python3 forge.py test                    Run test vectors")
        print("  python3 forge.py snapshot                Emit policy snapshot + SHA256")
        print("  python3 forge.py verify <receipt.json>   Verify checksum")
        print("  python3 forge.py clean                   Remove build artifacts")
        print("  python3 forge.py run <file.over>         Execute .over workflow with real I/O")
        print("  python3 forge.py jorki <sub> [args]      JORKI file gateway CLI")
        print("  python3 forge.py glyphlock <sub> [args]  GlyphLock time-gated codec CLI")
        print("  python3 forge.py audio <sub> [args]      AudioGlyph codec CLI")
        print("  python3 forge.py ziptoapp <zip> [name]   Render zip into .app bundle")
        print("  python3 forge.py rc <sub> [args]         Reality Compiler CLI")
        print("  python3 forge.py pulse <sub> [args]      ClientPulse OS CLI")
        print("  python3 forge.py proofwallet <sub> [args] ProofWallet CLI")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "init":
        cmd_init()
    elif cmd == "compile":
        if len(sys.argv) < 3:
            print("Usage: python3 forge.py compile <file.glyph|file.over>")
            sys.exit(1)
        cmd_compile(sys.argv[2])
    elif cmd == "build":
        cmd_build()
    elif cmd == "test":
        cmd_test()
    elif cmd == "snapshot":
        cmd_snapshot()
    elif cmd == "verify":
        if len(sys.argv) < 3:
            print("Usage: python3 forge.py verify <receipt.json>")
            sys.exit(1)
        cmd_verify(sys.argv[2])
    elif cmd == "clean":
        cmd_clean()
    elif cmd == "run":
        if len(sys.argv) < 3:
            print("Usage: python3 forge.py run <file.over> [--key=value ...]")
            sys.exit(1)
        cmd_run(sys.argv[2], sys.argv[3:])
    elif cmd == "jorki":
        cmd_jorki(sys.argv[2:])
    elif cmd == "glyphlock":
        cmd_glyphlock(sys.argv[2:])
    elif cmd == "audio":
        cmd_audio(sys.argv[2:])
    elif cmd == "ziptoapp":
        cmd_ziptoapp(sys.argv[2:])
    elif cmd == "rc":
        cmd_reality_compiler(sys.argv[2:])
    elif cmd == "pulse":
        cmd_clientpulse(sys.argv[2:])
    elif cmd == "proofwallet":
        cmd_proofwallet(sys.argv[2:])
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
