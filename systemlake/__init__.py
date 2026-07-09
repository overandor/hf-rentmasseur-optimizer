"""Membra SystemLake Underwriter.

Local-first, policy-gated crawler and underwriting daemon.

Raw files stay local.
Hashes prove existence.
Summaries carry cognition.
Receipts prove execution.
Merkle roots prove state.
Base64 carries snapshots.
Gateway controls exposure.
Underwriter prices the asset.

Architecture:
    MachineLake Daemon → Policy Engine → Redaction Engine
    → Cognition Compressor → Underwriting Engine → AAU → LLM Gateway

Three layers:
    1. Local Machine Lake — crawls system, builds SQLite index, Merkle root
    2. Underwriting Engine + AAU — scores assets, adversarial attribution, collateral
    3. Query Gateway — exposes only policy-approved cognition packets to LLMs

Commands:
    python3 -m systemlake.underwriter /Users/alep \\
      --full-machine-index \\
      --content-roots /Users/alep/Downloads \\
      --deny .ssh,Library/Keychains \\
      --collateralize --sbom --scorecard \\
      --out systemlake_full_underwrite
        → machine_manifest.json, merkle_root.json, systems.json,
          proofbook.jsonl, underwriting_memo.md, collateral_scores.json,
          risk_register.json, focus_packet.json, focus_packet.b64, receipt.json

    python3 -m systemlake.audit /path/to/repo --out out/
        → Same outputs, simpler CLI

    python3 -m systemlake.serve /path/to/repo --audit-dir out/ --port 8787
        → Read-only FastAPI gateway with 20 endpoints

Modules:
    lake.py             — MachineLake: two-pass crawl, SQLite index, Merkle root
    policy.py           — PolicyEngine + RedactionEngine: content-roots, deny list, two-pass
    compressor.py       — CognitionCompressor: semantic graph, Base64 export, receipts
    underwriter.py      — UnderwritingEngine: 10-dimension collateral scoring + haircuts
    aau.py              — AdversarialAttributionUnderwriter: gaming detection, settlement
    audit.py            — Full audit: 13 outputs, two-pass crawl, borrowing base, risk register
    underwriter_cli.py  — Underwriter CLI with --full-machine-index, --sbom, --scorecard
    gateway.py          — FastAPI gateway: 20 read-only endpoints
    serve.py            — Server launcher with audit integration
"""
