"""
Token Engine — proof token manifest creation with compliance gates.

Modes (in order of escalation):
  disabled — no token functionality
  proof_only (default) — local manifest only, no chain interaction
  non_transferable_devnet — devnet mint, non-transferable
  non_transferable_mainnet_review_required — mainnet mint, requires compliance
  restricted_reviewed — restricted transfer, reviewed
  public_transferable_blocked_by_default — blocked unless compliance + human + legal

Token metadata must include:
  artifact_id, packet_hash, evidence_uri, receipt_hash,
  token_mode, disclaimer, no_profit_claim
"""

import hashlib
import json
import time
from dataclasses import dataclass, asdict
from typing import Optional

from .risk_engine import RiskEngine, TokenMode, AssetStatus


@dataclass
class TokenManifest:
    manifest_id: str
    artifact_id: str
    packet_hash: str
    token_mode: str
    token_name: str
    token_symbol: str
    metadata_json: str
    mint_address: str
    tx_hash: str
    status: str
    created_at: float
    disclaimer: str = ""
    no_profit_claim: bool = True

    def to_dict(self) -> dict:
        d = asdict(self)
        d["metadata"] = json.loads(self.metadata_json)
        return d


_DISCLAIMER = (
    "This proof token is a receipt carrier, not a security. "
    "It does not represent investment, equity, profit rights, or any "
    "financial instrument. No profit is promised or implied."
)


class TokenEngine:
    """Proof token manifest creation with compliance gates."""

    def __init__(self, db, receipt_ledger=None):
        self.db = db
        self.receipt_ledger = receipt_ledger

    def create_manifest(self, artifact_id: str, packet_hash: str,
                        risk_report: dict,
                        token_name: str = "",
                        token_symbol: str = "",
                        evidence_uri: str = "",
                        receipt_hash: str = "") -> TokenManifest:
        """
        Phase A: Create local proof-token manifest only.

        This does NOT interact with any blockchain. It creates a local
        JSON manifest that can be inspected, verified, and audited.
        """
        token_mode = risk_report.get("token_mode_allowed", TokenMode.PROOF_ONLY.value)

        if token_mode == TokenMode.DISABLED.value:
            raise ValueError("Token mode is disabled for this artifact")

        if not packet_hash:
            raise ValueError("Cannot create token manifest without evidence packet hash")

        manifest_id = hashlib.sha256(
            f"token_manifest:{artifact_id}:{packet_hash}:{time.time()}".encode()
        ).hexdigest()[:16]

        token_name = token_name or f"Proof-{artifact_id[:8]}"
        token_symbol = token_symbol or f"PRF{artifact_id[:4]}".upper()

        metadata = {
            "artifact_id": artifact_id,
            "packet_hash": packet_hash,
            "evidence_uri": evidence_uri,
            "receipt_hash": receipt_hash,
            "token_mode": token_mode,
            "disclaimer": _DISCLAIMER,
            "no_profit_claim": True,
            "created_at": time.time(),
        }

        manifest = TokenManifest(
            manifest_id=manifest_id,
            artifact_id=artifact_id,
            packet_hash=packet_hash,
            token_mode=token_mode,
            token_name=token_name,
            token_symbol=token_symbol,
            metadata_json=json.dumps(metadata, sort_keys=True),
            mint_address="",
            tx_hash="",
            status="manifest_created",
            created_at=time.time(),
            disclaimer=_DISCLAIMER,
            no_profit_claim=True,
        )

        self.db.insert_token_manifest(
            manifest_id=manifest.manifest_id,
            artifact_id=manifest.artifact_id,
            packet_hash=manifest.packet_hash,
            token_mode=manifest.token_mode,
            token_name=manifest.token_name,
            token_symbol=manifest.token_symbol,
            metadata_json=manifest.metadata_json,
            status=manifest.status,
        )

        if self.receipt_ledger:
            self.receipt_ledger.write(
                receipt_type="token_manifest_creation",
                artifact_id=artifact_id,
                data=manifest.to_dict(),
                packet_hash=packet_hash,
            )

        return manifest

    def mint_devnet_nontransferable(self, manifest: TokenManifest,
                                    compliance_approved: bool = False) -> TokenManifest:
        """
        Phase B: Mint devnet non-transferable proof token.

        Requires:
        - token_mode >= non_transferable_devnet
        - compliance_approved for mainnet modes
        - No actual public chain interaction without explicit approval

        This creates a manifest entry with devnet metadata. Actual on-chain
        minting requires an external devnet RPC connection (not performed here).
        """
        if manifest.token_mode == TokenMode.DISABLED.value:
            raise ValueError("Token mode is disabled")
        if manifest.token_mode == TokenMode.PROOF_ONLY.value:
            raise ValueError(
                "Token mode is proof_only — cannot mint devnet token. "
                "Request non_transferable_devnet mode first."
            )

        devnet_metadata = {
            **json.loads(manifest.metadata_json),
            "mint_phase": "devnet_nontransferable",
            "transferable": False,
            "network": "devnet",
            "compliance_approved": compliance_approved,
            "mint_requested_at": time.time(),
        }

        manifest.metadata_json = json.dumps(devnet_metadata, sort_keys=True)
        manifest.status = "devnet_mint_requested"
        manifest.mint_address = ""  # Set by external devnet RPC
        manifest.tx_hash = ""  # Set by external devnet RPC

        self.db.insert_token_manifest(
            manifest_id=manifest.manifest_id,
            artifact_id=manifest.artifact_id,
            packet_hash=manifest.packet_hash,
            token_mode=manifest.token_mode,
            token_name=manifest.token_name,
            token_symbol=manifest.token_symbol,
            metadata_json=manifest.metadata_json,
            status=manifest.status,
            mint_address=manifest.mint_address,
            tx_hash=manifest.tx_hash,
        )

        if self.receipt_ledger:
            self.receipt_ledger.write(
                receipt_type="devnet_mint",
                artifact_id=manifest.artifact_id,
                data=manifest.to_dict(),
                packet_hash=manifest.packet_hash,
            )

        return manifest

    def check_launch_readiness(self, manifest: TokenManifest,
                               compliance_approved: bool = False,
                               human_approved: bool = False,
                               legal_review_completed: bool = False) -> dict:
        """
        Check if a token is ready for mainnet or public launch.

        Returns a dict with: ready, blockers, next_phase
        """
        blockers = []

        if not manifest.packet_hash:
            blockers.append("Missing evidence packet hash")

        if manifest.token_mode == TokenMode.PUBLIC_TRANSFERABLE_BLOCKED_BY_DEFAULT.value:
            if not compliance_approved:
                blockers.append("Compliance approval required for public transferable mode")
            if not human_approved:
                blockers.append("Explicit human approval required for public transferable mode")
            if not legal_review_completed:
                blockers.append("Legal review required — tokenized securities remain securities")

        if manifest.token_mode == TokenMode.NON_TRANSFERABLE_MAINNET_REVIEW_REQUIRED.value:
            if not compliance_approved:
                blockers.append("Compliance approval required for mainnet mode")

        ready = len(blockers) == 0

        next_phase = "blocked"
        if ready:
            if manifest.token_mode == TokenMode.NON_TRANSFERABLE_DEVNET.value:
                next_phase = "devnet_mint_ready"
            elif manifest.token_mode == TokenMode.NON_TRANSFERABLE_MAINNET_REVIEW_REQUIRED.value:
                next_phase = "mainnet_mint_ready"
            elif manifest.token_mode == TokenMode.RESTRICTED_REVIEWED.value:
                next_phase = "restricted_launch_ready"
            elif manifest.token_mode == TokenMode.PUBLIC_TRANSFERABLE_BLOCKED_BY_DEFAULT.value:
                next_phase = "public_launch_ready"

        return {
            "ready": ready,
            "blockers": blockers,
            "next_phase": next_phase,
            "token_mode": manifest.token_mode,
            "manifest_id": manifest.manifest_id,
        }
