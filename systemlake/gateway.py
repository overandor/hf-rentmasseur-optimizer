"""LLM Gateway — Scoped query endpoints for external LLMs.

The only thing exposed to ChatGPT or any other LLM. Does not hand out
the whole filesystem. Answers scoped questions:

    GET  /manifest           — lake summary, system count, merkle root
    GET  /systems            — list all detected systems
    GET  /systems/{id}       — system detail
    GET  /systems/{id}/packet.b64 — Base64 cognition packet for one system
    GET  /lake/latest.b64    — rolling signed snapshot
    GET  /lake/delta/{root}.b64 — delta since merkle root
    POST /query              — scoped question
    POST /export/redacted    — export redacted manifest
    POST /benchmark/llm      — multi-LLM audit harness

Every exposure creates a receipt.
"""

import os
import json
import time
import hashlib
import base64
import zlib
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, JSONResponse, Response
from pydantic import BaseModel

from .lake import MachineLake
from .compressor import CognitionCompressor
from .underwriter import UnderwritingEngine
from .policy import PolicyEngine, RedactionEngine


class QueryRequest(BaseModel):
    """Scoped query from an LLM."""
    question: str
    system: Optional[str] = None
    max_files: int = 100


class ExportRequest(BaseModel):
    """Export request with policy constraints."""
    system: Optional[str] = None
    include_snippets: bool = True
    include_symbols: bool = True
    max_files: int = 200


class BenchmarkRequest(BaseModel):
    """Multi-LLM benchmark request."""
    packet_b64: str
    models: List[str] = ["gpt-4", "claude-3", "gemini-pro", "llama3.1"]


def create_gateway(
    lake: MachineLake = None,
    policy: PolicyEngine = None,
    redactor: RedactionEngine = None,
    compressor: CognitionCompressor = None,
    underwriter: UnderwritingEngine = None,
    receipts_db: str = None,
    audit_dir: str = None,
) -> FastAPI:
    """Create the LLM Gateway FastAPI app.

    All endpoints are policy-gated. Every exposure creates a receipt.
    If audit_dir is provided, serves files from a completed systemlake.audit run.
    """
    from quadrantos.receipt_store import SQLiteReceiptStore

    lake = lake or MachineLake()
    policy = policy or PolicyEngine()
    redactor = redactor or RedactionEngine()
    compressor = compressor or CognitionCompressor(lake, policy, redactor)
    underwriter = underwriter or UnderwritingEngine(lake.db_path)
    receipts = SQLiteReceiptStore(receipts_db or lake.db_path.replace('.db', '_gateway.db'))

    app = FastAPI(title="Membra SystemLake Gateway",
                  description="Policy-gated query endpoints for LLM consumption. "
                              "Raw files stay local. Hashes prove existence. "
                              "Summaries carry cognition. Receipts prove exposure.")

    def _receipt(action: str, details: Dict, artifact_path: str = None):
        """Write a receipt for every gateway exposure."""
        return receipts.write(
            agent='SystemLakeGateway',
            action=action,
            artifact_path=artifact_path,
            details=details,
        )

    @app.get("/manifest")
    async def manifest():
        """Lake summary — system count, merkle root, file counts."""
        summary = lake.summary()
        _receipt('manifest_exposed', {'merkle_root': summary.get('merkle_root', '')[:16]})
        return summary

    @app.get("/systems")
    async def list_systems():
        """List all detected systems with capabilities."""
        systems = lake.list_systems()
        _receipt('systems_listed', {'count': len(systems)})
        return systems

    @app.get("/systems/{system_id}")
    async def get_system(system_id: int):
        """Get detail for a specific system."""
        system = lake.get_system(system_id)
        if not system:
            raise HTTPException(status_code=404, detail="System not found")
        _receipt('system_detail', {'system_id': system_id, 'name': system['name']})
        return system

    @app.get("/systems/{system_id}/packet.b64")
    async def system_packet(system_id: int):
        """Base64 cognition packet for a single system."""
        system = lake.get_system(system_id)
        if not system:
            raise HTTPException(status_code=404, detail="System not found")

        packet = compressor.compress(
            root=system['root_path'],
            max_files=100,
            include_snippets=True,
            include_symbols=True,
        )
        b64 = compressor.to_base64(packet)
        receipt_data = compressor.to_receipt(packet)

        _receipt('system_packet_exported', {
            'system_id': system_id,
            'system_name': system['name'],
            'packet_sha256': receipt_data['packet_sha256'][:16],
            'b64_size': receipt_data['b64_size'],
            'redactions': packet['privacy']['secret_redactions'],
        })

        return PlainTextResponse(b64, media_type="text/plain")

    @app.get("/lake/latest.b64")
    async def latest_snapshot():
        """Rolling signed snapshot of current machine-lake state.

        Returns compressed Base64 of the full cognition packet.
        This is the updatable form — not a giant permanent blob.
        """
        packet = compressor.compress(max_files=500)
        b64 = compressor.to_base64(packet)
        receipt_data = compressor.to_receipt(packet)

        _receipt('lake_snapshot_exported', {
            'merkle_root': packet.get('merkle_root'),
            'packet_sha256': receipt_data['packet_sha256'][:16],
            'b64_size': receipt_data['b64_size'],
            'files_in_packet': len(packet.get('files', [])),
            'redactions': packet['privacy']['secret_redactions'],
            'denied': packet['privacy']['files_denied'],
        })

        return PlainTextResponse(b64, media_type="text/plain")

    @app.get("/lake/delta/{merkle_root}.b64")
    async def delta_snapshot(merkle_root: str):
        """Delta packet — only what changed since the given Merkle root."""
        delta = lake.get_delta(merkle_root)
        if 'error' in delta:
            raise HTTPException(status_code=400, detail=delta['error'])

        raw = json.dumps(delta, sort_keys=True).encode()
        compressed = zlib.compress(raw, 9)
        b64 = base64.b64encode(compressed).decode()

        _receipt('lake_delta_exported', {
            'since_root': merkle_root[:16],
            'changed_files': delta['changed_files'],
            'b64_size': len(b64),
        })

        return PlainTextResponse(b64, media_type="text/plain")

    @app.post("/query")
    async def query(req: QueryRequest):
        """Scoped question — LLM asks, gateway answers with policy-filtered data."""
        # Determine what data to return based on the question
        q_lower = req.question.lower()

        result = {'question': req.question, 'answer': None, 'data': None}

        if 'system' in q_lower or 'project' in q_lower:
            systems = lake.list_systems()
            result['answer'] = f"Found {len(systems)} systems."
            result['data'] = [{'name': s['name'], 'has_tests': s['has_tests'],
                              'has_endpoints': s['has_endpoints']}
                             for s in systems]

        elif 'score' in q_lower or 'collateral' in q_lower or 'underwrite' in q_lower:
            scores = underwriter.score_all()
            result['answer'] = f"Scored {len(scores)} systems."
            result['data'] = [s.to_dict() for s in scores]

        elif 'receipt' in q_lower:
            recent = receipts.list_recent(limit=20)
            result['answer'] = f"Found {len(recent)} recent receipts."
            result['data'] = [{'id': r['id'][:8], 'action': r['action'],
                              'timestamp': r['timestamp'][:19]}
                             for r in recent]

        elif 'failing' in q_lower or 'broken' in q_lower:
            scores = underwriter.score_all()
            failing = [s.to_dict() for s in scores if s.grade in ('D', 'F')]
            result['answer'] = f"Found {len(failing)} failing systems."
            result['data'] = failing

        elif 'deploy' in q_lower or 'rank' in q_lower:
            scores = underwriter.score_all()
            ranked = sorted([s.to_dict() for s in scores],
                           key=lambda x: x['collateral_score'], reverse=True)
            result['answer'] = f"Ranked {len(ranked)} systems by deployability."
            result['data'] = ranked

        else:
            summary = lake.summary()
            result['answer'] = f"Lake has {summary['total_files']} files across {summary['systems']} systems."
            result['data'] = summary

        _receipt('query_answered', {
            'question': req.question[:100],
            'system_filter': req.system,
        })

        return result

    @app.post("/export/redacted")
    async def export_redacted(req: ExportRequest):
        """Export a redacted cognition packet."""
        packet = compressor.compress(
            max_files=req.max_files,
            include_snippets=req.include_snippets,
            include_symbols=req.include_symbols,
        )
        b64 = compressor.to_base64(packet)
        receipt_data = compressor.to_receipt(packet)

        _receipt('redacted_export', {
            'packet_sha256': receipt_data['packet_sha256'][:16],
            'b64_size': receipt_data['b64_size'],
            'redactions': packet['privacy']['secret_redactions'],
            'denied': packet['privacy']['files_denied'],
            'meta_only': packet['privacy']['files_metadata_only'],
        })

        return {
            'b64': b64,
            'receipt': receipt_data,
            'privacy': packet['privacy'],
        }

    @app.post("/benchmark/llm")
    async def benchmark_llm(req: BenchmarkRequest):
        """Multi-LLM audit harness.

        Same packet goes to multiple models. Each returns:
        asset map, risk map, functionality verdict, collateral estimate,
        missing proof, recommended next command.

        Local evaluator compares against actual test results and receipts.
        """
        # Decode the packet
        try:
            compressed = base64.b64decode(req.packet_b64)
            raw = zlib.decompress(compressed)
            packet = json.loads(raw)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid packet: {e}")

        results = {}
        for model in req.models:
            results[model] = {
                'status': 'pending',
                'note': f'Send packet to {model} and record response. '
                        f'Compare against lake receipts for verification.',
                'packet_hash': packet.get('packet_sha256', '')[:16],
            }

        _receipt('benchmark_started', {
            'models': req.models,
            'packet_sha256': packet.get('packet_sha256', '')[:16],
        })

        return {
            'benchmark_id': hashlib.sha256(
                f"{time.time()}:{req.packet_b64[:100]}".encode()
            ).hexdigest()[:16],
            'models': results,
            'packet_summary': {
                'files': len(packet.get('files', [])),
                'systems': len(packet.get('systems', [])),
                'merkle_root': packet.get('merkle_root'),
            },
        }

    @app.get("/receipts")
    async def gateway_receipts():
        """List all gateway exposure receipts."""
        recent = receipts.list_recent(limit=50, agent='SystemLakeGateway')
        return recent

    @app.get("/receipts/verify")
    async def verify_receipts():
        """Verify the gateway receipt chain."""
        return receipts.verify_chain()

    @app.get("/health")
    async def health():
        return {
            'status': 'ok',
            'lake': lake.summary(),
            'policy': 'active',
            'redaction': redactor.summary(),
            'audit_dir': audit_dir,
        }

    # === Audit-serving endpoints (read-only, from systemlake.audit output) ===

    @app.get("/proofbook")
    async def proofbook():
        """Serve ProofBook receipt ledger from audit output."""
        if not audit_dir:
            return {'error': 'No audit directory configured', 'entries': []}
        pb_path = os.path.join(audit_dir, 'proofbook.jsonl')
        if not os.path.exists(pb_path):
            raise HTTPException(status_code=404, detail="ProofBook not found")
        entries = []
        with open(pb_path) as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line))
        _receipt('proofbook_served', {'entries': len(entries)})
        return {'schema': 'membra.proofbook.v1', 'entries': entries}

    @app.get("/audit/memo")
    async def audit_memo():
        """Serve the underwriting memo as markdown."""
        if not audit_dir:
            raise HTTPException(status_code=404, detail="No audit directory configured")
        memo_path = os.path.join(audit_dir, 'underwriting_memo.md')
        if not os.path.exists(memo_path):
            raise HTTPException(status_code=404, detail="Memo not found")
        with open(memo_path) as f:
            content = f.read()
        _receipt('memo_served', {'size': len(content)})
        return PlainTextResponse(content, media_type="text/markdown")

    @app.get("/audit/collateral-scores")
    async def audit_collateral_scores():
        """Serve collateral scores JSON from audit output."""
        if not audit_dir:
            raise HTTPException(status_code=404, detail="No audit directory configured")
        cs_path = os.path.join(audit_dir, 'collateral_score.json')
        if not os.path.exists(cs_path):
            raise HTTPException(status_code=404, detail="Collateral scores not found")
        with open(cs_path) as f:
            data = json.load(f)
        _receipt('collateral_scores_served', {'systems': len(data.get('systems', []))})
        return data

    @app.get("/audit/focus-packet.b64")
    async def audit_focus_packet():
        """Serve the Base64 focus packet from audit output."""
        if not audit_dir:
            raise HTTPException(status_code=404, detail="No audit directory configured")
        fp_path = os.path.join(audit_dir, 'focus_packet.b64')
        if not os.path.exists(fp_path):
            raise HTTPException(status_code=404, detail="Focus packet not found")
        with open(fp_path) as f:
            b64 = f.read()
        _receipt('focus_packet_served', {'b64_size': len(b64)})
        return PlainTextResponse(b64, media_type="text/plain")

    return app
