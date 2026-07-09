"""
Agent Loop — continuous scan/intake/packet/classify/risk/page/receipt loop.

Loop:
1. Scan intake queue for new artifacts
2. For each new artifact:
   a. Build evidence packet
   b. Ask Ollama to summarize and classify (if available)
   c. Run risk engine
   d. Generate landing page
   e. Create proof receipt
   f. Optionally create proof-token manifest
   g. Write all events to ledger
3. Sleep and repeat
"""

import hashlib
import time
from typing import Optional

from .schema import OracleDB, ArtifactRecord
from .receipt_ledger import ReceiptLedger
from .ollama_client import OllamaClient
from .evidence_packet import EvidencePacketBuilder
from .risk_engine import RiskEngine, TokenMode
from .landing_page import LandingPageGenerator
from .token_engine import TokenEngine
from .bmma_builder import BMMABuilder


class AgentLoop:
    """Continuous agent loop for the Revenue Oracle."""

    def __init__(self, db: OracleDB,
                 ollama: OllamaClient = None,
                 ollama_enabled: bool = True,
                 create_tokens: bool = False,
                 poll_interval: float = 5.0):
        self.db = db
        self.ollama = ollama or OllamaClient()
        self.ollama_enabled = ollama_enabled
        self.create_tokens = create_tokens
        self.poll_interval = poll_interval

        self.receipt_ledger = ReceiptLedger(db)
        self.packet_builder = EvidencePacketBuilder(db)
        self.risk_engine = RiskEngine(db)
        self.page_generator = LandingPageGenerator(db)
        self.token_engine = TokenEngine(db, self.receipt_ledger)
        self.bmma_builder = BMMABuilder(db, self.receipt_ledger)

        self._running = False

    def process_artifact(self, artifact: dict) -> dict:
        """
        Process a single artifact through the full pipeline.

        Returns a dict with all outputs.
        """
        artifact_id = artifact["artifact_id"]
        results = {"artifact_id": artifact_id, "steps": []}

        # Step 1: Build evidence packet
        packet = self.packet_builder.build_packet(
            artifact=ArtifactRecord(
                artifact_id=artifact["artifact_id"],
                source_type=artifact["source_type"],
                source_uri_or_path=artifact["source_uri_or_path"],
                owner=artifact["owner"],
                created_at=artifact["created_at"],
                source_hash=artifact["source_hash"],
                manifest_hash=artifact["manifest_hash"],
            ),
        )
        self.receipt_ledger.write(
            receipt_type="packet_creation",
            artifact_id=artifact_id,
            data={"packet_hash": packet.packet_hash},
            output_hash=packet.packet_hash,
            packet_hash=packet.packet_hash,
        )
        results["packet_hash"] = packet.packet_hash
        results["steps"].append("packet_built")

        # Step 2: Ollama classification (if available)
        ollama_analysis = None
        if self.ollama_enabled and self.ollama.is_available():
            try:
                ollama_analysis = self.ollama.classify_artifact(artifact)
                self.receipt_ledger.write(
                    receipt_type="ollama_analysis",
                    artifact_id=artifact_id,
                    data=ollama_analysis,
                    model_name=ollama_analysis.get("model", ""),
                    packet_hash=packet.packet_hash,
                    runtime_ms=ollama_analysis.get("runtime_ms", 0),
                )
                results["ollama_analysis"] = ollama_analysis
                results["steps"].append("ollama_classified")
            except Exception as e:
                results["ollama_error"] = str(e)
                results["steps"].append("ollama_failed")
        elif self.ollama_enabled:
            results["ollama_error"] = "Ollama not available — skipping classification"
            results["steps"].append("ollama_skipped")

        # Rebuild packet with Ollama analysis if available
        if ollama_analysis:
            packet = self.packet_builder.build_packet(
                artifact=ArtifactRecord(
                    artifact_id=artifact["artifact_id"],
                    source_type=artifact["source_type"],
                    source_uri_or_path=artifact["source_uri_or_path"],
                    owner=artifact["owner"],
                    created_at=artifact["created_at"],
                    source_hash=artifact["source_hash"],
                    manifest_hash=artifact["manifest_hash"],
                ),
                ollama_analysis=ollama_analysis,
            )

        # Step 3: Risk evaluation
        packet_data = packet.to_dict()
        risk_report = self.risk_engine.evaluate(
            artifact_id=artifact_id,
            packet_hash=packet.packet_hash,
            packet_data=packet_data,
        )
        self.receipt_ledger.write(
            receipt_type="risk_report",
            artifact_id=artifact_id,
            data=risk_report,
            packet_hash=packet.packet_hash,
        )
        results["risk_report"] = risk_report
        results["steps"].append("risk_evaluated")

        # Step 3b: Build BMMA (Bonded Machine Media Asset)
        try:
            bmma_result = self.bmma_builder.build_bmma(
                artifact=artifact,
                packet=packet_data,
                question=artifact.get("question", ""),
                claims=packet_data.get("claims", []),
                machine_scores=ollama_analysis.get("machine_scores") if ollama_analysis else None,
            )
            results["bmma"] = bmma_result.to_dict()
            results["steps"].append("bmma_built")
        except Exception as e:
            results["bmma_error"] = str(e)
            results["steps"].append("bmma_skipped")

        # Step 4: Generate landing page
        page = self.page_generator.generate(
            artifact=artifact,
            packet=packet_data,
            risk_report=risk_report,
        )
        self.receipt_ledger.write(
            receipt_type="landing_page_generation",
            artifact_id=artifact_id,
            data={"page_id": page.page_id, "page_hash": page.page_hash},
            output_hash=page.page_hash,
            packet_hash=packet.packet_hash,
        )
        results["page_id"] = page.page_id
        results["steps"].append("page_generated")

        # Step 5: Optionally create proof-token manifest
        if self.create_tokens and risk_report["token_mode_allowed"] != TokenMode.DISABLED.value:
            try:
                manifest = self.token_engine.create_manifest(
                    artifact_id=artifact_id,
                    packet_hash=packet.packet_hash,
                    risk_report=risk_report,
                )
                results["manifest_id"] = manifest.manifest_id
                results["steps"].append("token_manifest_created")
            except Exception as e:
                results["token_error"] = str(e)
                results["steps"].append("token_manifest_skipped")

        # Step 6: Update artifact status
        self.db.update_artifact_status(artifact_id, risk_report["asset_status"])
        results["asset_status"] = risk_report["asset_status"]
        results["steps"].append("status_updated")

        return results

    def run_once(self) -> dict:
        """Process all pending artifacts once."""
        run_id = hashlib.sha256(
            f"run:{time.time()}".encode()
        ).hexdigest()[:16]
        started_at = time.time()
        self.db.insert_agent_run(run_id, started_at)

        pending = self.db.get_pending_artifacts()
        results = []
        errors = 0
        packets_built = 0
        pages_generated = 0
        receipts_before = len(self.receipt_ledger.list_all(limit=10000))

        for artifact in pending:
            try:
                result = self.process_artifact(artifact)
                results.append(result)
                packets_built += 1
                pages_generated += 1
            except Exception as e:
                errors += 1
                results.append({"artifact_id": artifact["artifact_id"], "error": str(e)})

        receipts_after = len(self.receipt_ledger.list_all(limit=10000))
        receipts_written = receipts_after - receipts_before

        self.db.complete_agent_run(
            run_id=run_id,
            completed_at=time.time(),
            artifacts_processed=len(pending),
            packets_built=packets_built,
            pages_generated=pages_generated,
            receipts_written=receipts_written,
            errors=errors,
        )

        return {
            "run_id": run_id,
            "artifacts_processed": len(pending),
            "packets_built": packets_built,
            "pages_generated": pages_generated,
            "receipts_written": receipts_written,
            "errors": errors,
            "results": results,
        }

    def run_forever(self) -> None:
        """Run the agent loop continuously."""
        self._running = True
        while self._running:
            try:
                self.run_once()
            except Exception:
                pass
            time.sleep(self.poll_interval)

    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
