"""
SQLite schema + data classes for the Revenue Oracle.

Tables: artifacts, evidence_packets, claims, receipts, token_manifests,
landing_pages, deployments, revenue_receipts, risk_reports, agent_runs, settings
"""

import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class ArtifactRecord:
    artifact_id: str
    source_type: str
    source_uri_or_path: str
    owner: str
    created_at: float
    source_hash: str
    manifest_hash: str
    status: str = "intake"

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


@dataclass
class EvidencePacket:
    packet_hash: str
    artifact_id: str
    source_hash: str
    manifest_hash: str
    claims: list = field(default_factory=list)
    risk_flags: list = field(default_factory=list)
    license_flags: list = field(default_factory=list)
    provenance_chain: list = field(default_factory=list)
    receipt_list: list = field(default_factory=list)
    reproducibility_notes: str = ""
    limitations: str = ""
    function_graph_hash: str = ""
    created_at: float = 0.0
    revenue_status: str = "proof_of_financeable_structure_only"

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


@dataclass
class MediaAssetRecord:
    """Bonded Machine Media Asset record — bridges broll BMMA into the oracle."""
    media_asset_id: str
    artifact_id: str
    packet_hash: str
    bmma_id: str = ""
    bea_id: str = ""
    question: str = ""
    transcript: str = ""
    claims_json: str = "[]"
    scene_graph_hash: str = ""
    visual_evidence_segments: str = "[]"
    truth_labels: str = "[]"
    rights_labels: str = "[]"
    revenue_ledger_hash: str = ""
    payout_waterfall_hash: str = ""
    quality_grade: float = 0.0
    computed_grade: float = 0.0
    bond_amount_usd: float = 0.0
    bond_required_usd: float = 0.0
    rubric_id: str = ""
    audit_probability: float = 0.0
    producer_id: str = ""
    producer_tier: str = "unproven"
    schema_org_hash: str = ""
    c2pa_manifest_hash: str = ""
    segment_listings_count: int = 0
    segment_listings_available: int = 0
    provenance_hash: str = ""
    receipt_hash: str = ""
    created_at: float = 0.0
    status: str = "draft"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["claims"] = json.loads(d.pop("claims_json"))
        d["visual_evidence_segments"] = json.loads(d.pop("visual_evidence_segments"))
        d["truth_labels"] = json.loads(d.pop("truth_labels"))
        d["rights_labels"] = json.loads(d.pop("rights_labels"))
        return d


@dataclass
class RevenueReceipt:
    receipt_id: str
    buyer_reference: str
    product_type: str
    amount: float
    currency: str
    payment_provider: str
    payment_status: str
    artifact_id: str
    packet_hash: str
    created_at: float

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_uri_or_path TEXT NOT NULL,
    owner TEXT NOT NULL,
    created_at REAL NOT NULL,
    source_hash TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'intake'
);

CREATE TABLE IF NOT EXISTS evidence_packets (
    packet_hash TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    claims TEXT NOT NULL DEFAULT '[]',
    risk_flags TEXT NOT NULL DEFAULT '[]',
    license_flags TEXT NOT NULL DEFAULT '[]',
    provenance_chain TEXT NOT NULL DEFAULT '[]',
    receipt_list TEXT NOT NULL DEFAULT '[]',
    reproducibility_notes TEXT NOT NULL DEFAULT '',
    limitations TEXT NOT NULL DEFAULT '',
    function_graph_hash TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    revenue_status TEXT NOT NULL DEFAULT 'proof_of_financeable_structure_only',
    FOREIGN KEY (artifact_id) REFERENCES artifacts(artifact_id)
);

CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    claim_type TEXT NOT NULL,
    evidence_hash TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'unverified',
    created_at REAL NOT NULL,
    FOREIGN KEY (artifact_id) REFERENCES artifacts(artifact_id)
);

CREATE TABLE IF NOT EXISTS receipts (
    receipt_hash TEXT PRIMARY KEY,
    receipt_type TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    input_hash TEXT NOT NULL DEFAULT '',
    output_hash TEXT NOT NULL DEFAULT '',
    model_name TEXT NOT NULL DEFAULT '',
    model_digest TEXT NOT NULL DEFAULT '',
    packet_hash TEXT NOT NULL DEFAULT '',
    runtime_ms INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    prev_hash TEXT NOT NULL DEFAULT '',
    data TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS token_manifests (
    manifest_id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL,
    packet_hash TEXT NOT NULL,
    token_mode TEXT NOT NULL DEFAULT 'proof_only',
    token_name TEXT NOT NULL DEFAULT '',
    token_symbol TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    mint_address TEXT NOT NULL DEFAULT '',
    tx_hash TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at REAL NOT NULL,
    FOREIGN KEY (artifact_id) REFERENCES artifacts(artifact_id)
);

CREATE TABLE IF NOT EXISTS landing_pages (
    page_id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL,
    packet_hash TEXT NOT NULL,
    html TEXT NOT NULL DEFAULT '',
    page_hash TEXT NOT NULL DEFAULT '',
    deployment_url TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at REAL NOT NULL,
    FOREIGN KEY (artifact_id) REFERENCES artifacts(artifact_id)
);

CREATE TABLE IF NOT EXISTS deployments (
    deployment_id TEXT PRIMARY KEY,
    page_id TEXT NOT NULL,
    target TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    page_hash TEXT NOT NULL DEFAULT '',
    packet_hash TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL,
    FOREIGN KEY (page_id) REFERENCES landing_pages(page_id)
);

CREATE TABLE IF NOT EXISTS revenue_receipts (
    receipt_id TEXT PRIMARY KEY,
    buyer_reference TEXT NOT NULL,
    product_type TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    payment_provider TEXT NOT NULL DEFAULT '',
    payment_status TEXT NOT NULL DEFAULT 'pending',
    artifact_id TEXT NOT NULL,
    packet_hash TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (artifact_id) REFERENCES artifacts(artifact_id)
);

CREATE TABLE IF NOT EXISTS risk_reports (
    report_id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL,
    packet_hash TEXT NOT NULL DEFAULT '',
    risk_score REAL NOT NULL DEFAULT 0.0,
    blockers TEXT NOT NULL DEFAULT '[]',
    token_mode_allowed TEXT NOT NULL DEFAULT 'proof_only',
    asset_status TEXT NOT NULL DEFAULT 'draft',
    summary TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    FOREIGN KEY (artifact_id) REFERENCES artifacts(artifact_id)
);

CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    started_at REAL NOT NULL,
    completed_at REAL NOT NULL DEFAULT 0,
    artifacts_processed INTEGER NOT NULL DEFAULT 0,
    packets_built INTEGER NOT NULL DEFAULT 0,
    pages_generated INTEGER NOT NULL DEFAULT 0,
    receipts_written INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS media_assets (
    media_asset_id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL,
    packet_hash TEXT NOT NULL,
    bmma_id TEXT NOT NULL DEFAULT '',
    bea_id TEXT NOT NULL DEFAULT '',
    question TEXT NOT NULL DEFAULT '',
    transcript TEXT NOT NULL DEFAULT '',
    claims_json TEXT NOT NULL DEFAULT '[]',
    scene_graph_hash TEXT NOT NULL DEFAULT '',
    visual_evidence_segments TEXT NOT NULL DEFAULT '[]',
    truth_labels TEXT NOT NULL DEFAULT '[]',
    rights_labels TEXT NOT NULL DEFAULT '[]',
    revenue_ledger_hash TEXT NOT NULL DEFAULT '',
    payout_waterfall_hash TEXT NOT NULL DEFAULT '',
    quality_grade REAL NOT NULL DEFAULT 0.0,
    computed_grade REAL NOT NULL DEFAULT 0.0,
    bond_amount_usd REAL NOT NULL DEFAULT 0.0,
    bond_required_usd REAL NOT NULL DEFAULT 0.0,
    rubric_id TEXT NOT NULL DEFAULT '',
    audit_probability REAL NOT NULL DEFAULT 0.0,
    producer_id TEXT NOT NULL DEFAULT '',
    producer_tier TEXT NOT NULL DEFAULT 'unproven',
    schema_org_hash TEXT NOT NULL DEFAULT '',
    c2pa_manifest_hash TEXT NOT NULL DEFAULT '',
    segment_listings_count INTEGER NOT NULL DEFAULT 0,
    segment_listings_available INTEGER NOT NULL DEFAULT 0,
    provenance_hash TEXT NOT NULL DEFAULT '',
    receipt_hash TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    FOREIGN KEY (artifact_id) REFERENCES artifacts(artifact_id)
);
"""


class OracleDB:
    """SQLite database for the Revenue Oracle."""

    def __init__(self, db_path: str = "revenue_oracle.db"):
        self.db_path = db_path
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        conn = self._get_conn()
        try:
            conn.executescript(_SCHEMA_SQL)
            conn.commit()
        finally:
            conn.close()

    def insert_artifact(self, rec: ArtifactRecord) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO artifacts
                (artifact_id, source_type, source_uri_or_path, owner, created_at,
                 source_hash, manifest_hash, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (rec.artifact_id, rec.source_type, rec.source_uri_or_path,
                 rec.owner, rec.created_at, rec.source_hash, rec.manifest_hash,
                 rec.status),
            )
            conn.commit()
        finally:
            conn.close()

    def get_artifact(self, artifact_id: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM artifacts WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_artifacts(self, limit: int = 100) -> list:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM artifacts ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def update_artifact_status(self, artifact_id: str, status: str) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE artifacts SET status = ? WHERE artifact_id = ?",
                (status, artifact_id),
            )
            conn.commit()
        finally:
            conn.close()

    def insert_evidence_packet(self, pkt: EvidencePacket) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO evidence_packets
                (packet_hash, artifact_id, source_hash, manifest_hash, claims,
                 risk_flags, license_flags, provenance_chain, receipt_list,
                 reproducibility_notes, limitations, function_graph_hash,
                 created_at, revenue_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (pkt.packet_hash, pkt.artifact_id, pkt.source_hash,
                 pkt.manifest_hash, json.dumps(pkt.claims),
                 json.dumps(pkt.risk_flags), json.dumps(pkt.license_flags),
                 json.dumps(pkt.provenance_chain), json.dumps(pkt.receipt_list),
                 pkt.reproducibility_notes, pkt.limitations,
                 pkt.function_graph_hash, pkt.created_at, pkt.revenue_status),
            )
            conn.commit()
        finally:
            conn.close()

    def get_evidence_packet(self, packet_hash: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM evidence_packets WHERE packet_hash = ?",
                (packet_hash,),
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            for k in ("claims", "risk_flags", "license_flags",
                      "provenance_chain", "receipt_list"):
                d[k] = json.loads(d[k])
            return d
        finally:
            conn.close()

    def insert_receipt(self, receipt_hash: str, receipt_type: str,
                       artifact_id: str, data: dict, input_hash: str = "",
                       output_hash: str = "", model_name: str = "",
                       model_digest: str = "", packet_hash: str = "",
                       runtime_ms: int = 0, prev_hash: str = "") -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO receipts
                (receipt_hash, receipt_type, artifact_id, input_hash, output_hash,
                 model_name, model_digest, packet_hash, runtime_ms, created_at,
                 prev_hash, data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (receipt_hash, receipt_type, artifact_id, input_hash,
                 output_hash, model_name, model_digest, packet_hash,
                 runtime_ms, time.time(), prev_hash, json.dumps(data)),
            )
            conn.commit()
        finally:
            conn.close()

    def get_receipt(self, receipt_hash: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM receipts WHERE receipt_hash = ?",
                (receipt_hash,),
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            d["data"] = json.loads(d["data"])
            return d
        finally:
            conn.close()

    def list_receipts(self, limit: int = 100) -> list:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM receipts ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["data"] = json.loads(d["data"])
                result.append(d)
            return result
        finally:
            conn.close()

    def get_last_receipt_hash(self) -> str:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT receipt_hash FROM receipts ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            return row["receipt_hash"] if row else ""
        finally:
            conn.close()

    def insert_token_manifest(self, manifest_id: str, artifact_id: str,
                              packet_hash: str, token_mode: str,
                              token_name: str, token_symbol: str,
                              metadata_json: str, status: str = "draft",
                              mint_address: str = "", tx_hash: str = "") -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO token_manifests
                (manifest_id, artifact_id, packet_hash, token_mode, token_name,
                 token_symbol, metadata_json, mint_address, tx_hash, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (manifest_id, artifact_id, packet_hash, token_mode,
                 token_name, token_symbol, metadata_json, mint_address,
                 tx_hash, status, time.time()),
            )
            conn.commit()
        finally:
            conn.close()

    def list_token_manifests(self, limit: int = 100) -> list:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM token_manifests ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def insert_landing_page(self, page_id: str, artifact_id: str,
                            packet_hash: str, html: str, page_hash: str,
                            status: str = "draft") -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO landing_pages
                (page_id, artifact_id, packet_hash, html, page_hash,
                 deployment_url, status, created_at)
                VALUES (?, ?, ?, ?, ?, '', ?, ?)""",
                (page_id, artifact_id, packet_hash, html, page_hash,
                 status, time.time()),
            )
            conn.commit()
        finally:
            conn.close()

    def get_landing_page(self, page_id: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM landing_pages WHERE page_id = ?",
                (page_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_landing_pages(self, limit: int = 100) -> list:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM landing_pages ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def insert_deployment(self, deployment_id: str, page_id: str,
                          target: str, url: str, page_hash: str,
                          packet_hash: str, status: str = "pending") -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO deployments
                (deployment_id, page_id, target, url, page_hash, packet_hash,
                 status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (deployment_id, page_id, target, url, page_hash,
                 packet_hash, status, time.time()),
            )
            conn.commit()
        finally:
            conn.close()

    def list_deployments(self, limit: int = 100) -> list:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM deployments ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def insert_revenue_receipt(self, rec: RevenueReceipt) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO revenue_receipts
                (receipt_id, buyer_reference, product_type, amount, currency,
                 payment_provider, payment_status, artifact_id, packet_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (rec.receipt_id, rec.buyer_reference, rec.product_type,
                 rec.amount, rec.currency, rec.payment_provider,
                 rec.payment_status, rec.artifact_id, rec.packet_hash,
                 rec.created_at),
            )
            conn.commit()
        finally:
            conn.close()

    def list_revenue_receipts(self, limit: int = 100) -> list:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM revenue_receipts ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def insert_risk_report(self, report_id: str, artifact_id: str,
                           packet_hash: str, risk_score: float,
                           blockers: list, token_mode_allowed: str,
                           asset_status: str, summary: str) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO risk_reports
                (report_id, artifact_id, packet_hash, risk_score, blockers,
                 token_mode_allowed, asset_status, summary, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (report_id, artifact_id, packet_hash, risk_score,
                 json.dumps(blockers), token_mode_allowed, asset_status,
                 summary, time.time()),
            )
            conn.commit()
        finally:
            conn.close()

    def list_risk_reports(self, limit: int = 100) -> list:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM risk_reports ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["blockers"] = json.loads(d["blockers"])
                result.append(d)
            return result
        finally:
            conn.close()

    def insert_agent_run(self, run_id: str, started_at: float) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO agent_runs
                (run_id, started_at, status) VALUES (?, ?, 'running')""",
                (run_id, started_at),
            )
            conn.commit()
        finally:
            conn.close()

    def complete_agent_run(self, run_id: str, completed_at: float,
                           artifacts_processed: int, packets_built: int,
                           pages_generated: int, receipts_written: int,
                           errors: int) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """UPDATE agent_runs SET
                completed_at = ?, artifacts_processed = ?, packets_built = ?,
                pages_generated = ?, receipts_written = ?, errors = ?,
                status = 'completed'
                WHERE run_id = ?""",
                (completed_at, artifacts_processed, packets_built,
                 pages_generated, receipts_written, errors, run_id),
            )
            conn.commit()
        finally:
            conn.close()

    def list_agent_runs(self, limit: int = 20) -> list:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM agent_runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_setting(self, key: str, default: str = "") -> str:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,),
            ).fetchone()
            return row["value"] if row else default
        finally:
            conn.close()

    def set_setting(self, key: str, value: str) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
            conn.commit()
        finally:
            conn.close()

    def get_pending_artifacts(self) -> list:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM artifacts WHERE status = 'intake' ORDER BY created_at ASC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def insert_media_asset(self, rec: MediaAssetRecord) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO media_assets
                (media_asset_id, artifact_id, packet_hash, bmma_id, bea_id,
                 question, transcript, claims_json, scene_graph_hash,
                 visual_evidence_segments, truth_labels, rights_labels,
                 revenue_ledger_hash, payout_waterfall_hash, quality_grade,
                 computed_grade, bond_amount_usd, bond_required_usd, rubric_id,
                 audit_probability, producer_id, producer_tier, schema_org_hash,
                 c2pa_manifest_hash, segment_listings_count, segment_listings_available,
                 provenance_hash, receipt_hash, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (rec.media_asset_id, rec.artifact_id, rec.packet_hash,
                 rec.bmma_id, rec.bea_id, rec.question, rec.transcript,
                 rec.claims_json, rec.scene_graph_hash,
                 rec.visual_evidence_segments, rec.truth_labels, rec.rights_labels,
                 rec.revenue_ledger_hash, rec.payout_waterfall_hash,
                 rec.quality_grade, rec.computed_grade, rec.bond_amount_usd,
                 rec.bond_required_usd, rec.rubric_id, rec.audit_probability,
                 rec.producer_id, rec.producer_tier, rec.schema_org_hash,
                 rec.c2pa_manifest_hash, rec.segment_listings_count,
                 rec.segment_listings_available, rec.provenance_hash,
                 rec.receipt_hash, rec.created_at, rec.status),
            )
            conn.commit()
        finally:
            conn.close()

    def get_media_asset(self, media_asset_id: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM media_assets WHERE media_asset_id = ?",
                (media_asset_id,),
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            d["claims"] = json.loads(d.pop("claims_json"))
            d["visual_evidence_segments"] = json.loads(d.pop("visual_evidence_segments"))
            d["truth_labels"] = json.loads(d.pop("truth_labels"))
            d["rights_labels"] = json.loads(d.pop("rights_labels"))
            return d
        finally:
            conn.close()

    def list_media_assets(self, limit: int = 100) -> list:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM media_assets ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["claims"] = json.loads(d.pop("claims_json"))
                d["visual_evidence_segments"] = json.loads(d.pop("visual_evidence_segments"))
                d["truth_labels"] = json.loads(d.pop("truth_labels"))
                d["rights_labels"] = json.loads(d.pop("rights_labels"))
                result.append(d)
            return result
        finally:
            conn.close()
