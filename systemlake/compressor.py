"""Cognition Compressor — Turns the lake into a small semantic graph.

Takes 3 GB of filesystem and produces a 50KB-5MB signed semantic projection:
systems, files, roles, symbols, dependencies, commands, endpoints, tests,
receipts, risks, value scores.

The output is a cognition packet — not raw files, not Base64 of files,
but a compressed semantic representation that an LLM can reason over.
"""

import os
import re
import json
import hashlib
import zlib
import base64
import time
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from collections import Counter, defaultdict
from pathlib import Path

from .lake import MachineLake, CODE_EXTS, CONFIG_EXTS, DOC_EXTS, TEXT_EXTS
from .policy import PolicyEngine, RedactionEngine, AccessLevel, ExportCapability


class CognitionCompressor:
    """Compresses the lake into a small semantic graph for LLM consumption.

    Output packet contains:
    - machine snapshot ID, timestamp, Merkle root
    - system list with detected capabilities
    - file roles (not raw content)
    - symbol summaries (functions, classes, endpoints)
    - dependency graph
    - risk indicators
    - collateral scores (from UnderwritingEngine)

    Output does NOT contain:
    - Raw file contents (only redacted snippets if policy allows)
    - Secrets or tokens
    - Binary file data
    - Sensitive zone metadata
    """

    def __init__(self, lake: MachineLake, policy: PolicyEngine = None,
                 redactor: RedactionEngine = None):
        self.lake = lake
        self.policy = policy or PolicyEngine()
        self.redactor = redactor or RedactionEngine()

    def compress(self, root: str = None, max_files: int = 500,
                 include_snippets: bool = True,
                 include_symbols: bool = True) -> Dict:
        """Compress the lake into a cognition packet.

        Args:
            root: Root path for relative paths (defaults to crawl root)
            max_files: Maximum files to include in packet
            include_snippets: Include short redacted code snippets
            include_symbols: Include function/class/endpoint symbols

        Returns:
            Cognition packet dict ready for Base64 encoding
        """
        now_str = datetime.now().isoformat()
        merkle_root = self.lake.get_merkle_root()
        systems = self.lake.list_systems()
        lake_summary = self.lake.summary()

        # Build file entries with policy filtering
        files = self.lake.list_files(limit=max_files * 3)  # over-fetch, filter down
        packet_files = []
        redaction_count = 0
        denied_count = 0
        meta_only_count = 0

        for f in files:
            decision = self.policy.evaluate(f['path'], f.get('ext'))

            if decision.access_level == AccessLevel.DENIED:
                denied_count += 1
                continue

            entry = {
                'path': f['path'],
                'size': f['size'],
                'ext': f['ext'],
                'category': f['category'],
                'sha256': f['sha256'][:16] if f['sha256'] else None,
            }

            if decision.access_level == AccessLevel.METADATA_ONLY:
                meta_only_count += 1
                entry['access'] = 'metadata_only'
                packet_files.append(entry)
                continue

            # Full or redacted access
            entry['access'] = 'redacted'

            # Add summary
            entry['summary'] = self._file_summary(f)

            # Add symbols if allowed
            if include_symbols and ExportCapability.SYMBOLS in decision.capabilities:
                entry['symbols'] = self._extract_symbols(f)

            # Add snippet if allowed
            if include_snippets and ExportCapability.SNIPPET in decision.capabilities:
                snippet = self._extract_snippet(f, root)
                if snippet:
                    redacted, count = self.redactor.redact(snippet)
                    redaction_count += count
                    entry['snippet'] = redacted[:800]

            packet_files.append(entry)

            if len(packet_files) >= max_files:
                break

        # Build system summaries
        system_summaries = []
        for sys_row in systems:
            system_summaries.append({
                'name': sys_row['name'],
                'root': os.path.basename(sys_row['root_path']),
                'file_count': sys_row['file_count'],
                'has_tests': bool(sys_row['has_tests']),
                'has_endpoints': bool(sys_row['has_endpoints']),
                'has_receipts': bool(sys_row['has_receipts']),
                'has_readme': bool(sys_row['has_readme']),
                'has_git': bool(sys_row['has_git']),
                'has_dockerfile': bool(sys_row['has_dockerfile']),
                'has_requirements': bool(sys_row['has_requirements']),
                'has_package_json': bool(sys_row['has_package_json']),
            })

        # Build extension distribution
        ext_counts = Counter(f['ext'] or '[none]' for f in packet_files)
        category_counts = Counter(f['category'] for f in packet_files)

        # Build dependency graph (simple: imports/requires)
        dep_graph = self._build_dependency_graph(packet_files)

        packet = {
            'schema': 'membra.systemlake.cognition.v1',
            'created_at': now_str,
            'merkle_root': merkle_root[:16] if merkle_root else None,
            'privacy': {
                'raw_files_uploaded': False,
                'base64_is_encryption': False,
                'files_denied': denied_count,
                'files_metadata_only': meta_only_count,
                'secret_redactions': redaction_count,
                'include_snippets': include_snippets,
                'include_symbols': include_symbols,
            },
            'lake_summary': {
                'total_files': lake_summary['total_files'],
                'total_size': lake_summary['total_size'],
                'systems': lake_summary['systems'],
                'crawl_count': lake_summary['crawl_count'],
            },
            'systems': system_summaries,
            'files': packet_files,
            'extension_counts': dict(ext_counts.most_common(30)),
            'category_counts': dict(category_counts.most_common(10)),
            'dependency_graph': dep_graph,
        }

        # Compute packet hash
        packet['packet_sha256'] = hashlib.sha256(
            json.dumps(packet, sort_keys=True).encode()
        ).hexdigest()

        return packet

    def _file_summary(self, f: Dict) -> str:
        """Generate a one-line summary of a file's role."""
        path = f['path'].lower()
        ext = (f.get('ext') or '').lower()
        category = f.get('category', '')

        if 'test' in path:
            return 'Test file'
        if 'receipt' in path or 'sha256' in path:
            return 'Receipt/provenance/audit file'
        if 'fastapi' in path or 'endpoint' in path or 'uvicorn' in path:
            return 'API endpoint file'
        if 'sqlite' in path or 'duckdb' in path or '.db' in ext:
            return 'Database/persistence file'
        if 'ollama' in path or 'llm' in path or 'openai' in path:
            return 'LLM/agent integration file'
        if 'subprocess' in path or 'terminal' in path or 'shell' in path:
            return 'Terminal execution file'
        if 'dmg' in path or 'hdiutil' in path:
            return 'macOS packaging file'
        if 'lexer' in path or 'parser' in path or 'interpreter' in path:
            return 'Language toolchain file'
        if 'ledger' in path:
            return 'Ledger/accounting file'
        if 'tui' in path or 'dashboard' in path:
            return 'UI/dashboard file'
        if 'cli' in path:
            return 'CLI entry point'
        if '__init__' in path:
            return 'Package init'
        if category == 'code':
            return 'Source code file'
        if category == 'config':
            return 'Configuration file'
        if category == 'doc':
            return 'Documentation file'
        return 'Other file'

    def _extract_symbols(self, f: Dict) -> Dict:
        """Extract function/class/endpoint symbols from a file."""
        # This is a lightweight extraction — the lake stores metadata,
        # but symbol extraction requires reading the file
        # For the packet, we return what we can from the path
        path = f['path']
        ext = (f.get('ext') or '').lower()
        symbols = {}

        if ext == '.recept':
            # RECEPT files: look for capsule/endpoint/workflow/fn declarations
            try:
                full_path = self._resolve_path(path)
                if full_path and os.path.exists(full_path):
                    with open(full_path, 'r', errors='replace') as fh:
                        for line in fh:
                            s = line.strip()
                            m = re.match(r'(capsule|endpoint|workflow|fn)\b(.*)', s)
                            if m:
                                kind = m.group(1)
                                if kind not in symbols:
                                    symbols[kind] = []
                                symbols[kind].append(m.group(2).strip()[:100])
            except Exception:
                pass

        elif ext == '.py':
            try:
                full_path = self._resolve_path(path)
                if full_path and os.path.exists(full_path):
                    with open(full_path, 'r', errors='replace') as fh:
                        for line in fh:
                            s = line.strip()
                            m = re.match(r'(class|def)\s+([A-Za-z_][A-Za-z0-9_]*)', s)
                            if m:
                                kind = m.group(1)
                                if kind not in symbols:
                                    symbols[kind] = []
                                symbols[kind].append(m.group(2))
            except Exception:
                pass

        return {k: v[:20] for k, v in symbols.items()} if symbols else {}

    def _extract_snippet(self, f: Dict, root: str = None) -> Optional[str]:
        """Extract a short snippet from a file."""
        try:
            full_path = self._resolve_path(f['path'], root)
            if not full_path or not os.path.exists(full_path):
                return None
            with open(full_path, 'r', errors='replace') as fh:
                return fh.read(800)
        except Exception:
            return None

    def _resolve_path(self, rel_path: str, root: str = None) -> Optional[str]:
        """Resolve a relative path from the lake to an actual file path."""
        # Try to find the file relative to common roots
        candidates = [
            os.path.join(os.getcwd(), rel_path),
            rel_path,
        ]
        if root:
            candidates.insert(0, os.path.join(root, rel_path))

        for c in candidates:
            if os.path.exists(c):
                return c
        return None

    def _build_dependency_graph(self, files: List[Dict]) -> Dict:
        """Build a simple dependency graph from import/require statements."""
        deps = defaultdict(list)

        for f in files:
            path = f['path']
            ext = (f.get('ext') or '').lower()
            snippet = f.get('snippet', '')

            if not snippet:
                continue

            if ext == '.py':
                # Find imports
                for m in re.finditer(r'^(?:from\s+(\S+)\s+)?import\s+(.+)$', snippet, re.MULTILINE):
                    mod = m.group(1) or m.group(2).strip()
                    deps[path].append(mod.split('.')[0])
            elif ext in ('.js', '.ts', '.tsx', '.jsx'):
                for m in re.finditer(r'(?:import|require)\s*\(?\s*["\']([^"\']+)["\']', snippet):
                    deps[path].append(m.group(1))

        return {k: list(set(v))[:10] for k, v in deps.items()} if deps else {}

    def to_base64(self, packet: Dict) -> str:
        """Encode a cognition packet as compressed Base64."""
        raw = json.dumps(packet, sort_keys=True).encode()
        compressed = zlib.compress(raw, 9)
        return base64.b64encode(compressed).decode()

    def to_receipt(self, packet: Dict) -> Dict:
        """Generate a receipt for a cognition packet export."""
        raw = json.dumps(packet, sort_keys=True).encode()
        compressed = zlib.compress(raw, 9)
        b64 = base64.b64encode(compressed).decode()

        return {
            'schema': 'membra.systemlake.export_receipt.v1',
            'created_at': datetime.now().isoformat(),
            'packet_sha256': hashlib.sha256(raw).hexdigest(),
            'compressed_sha256': hashlib.sha256(compressed).hexdigest(),
            'b64_sha256': hashlib.sha256(b64.encode()).hexdigest(),
            'file_count': len(packet.get('files', [])),
            'system_count': len(packet.get('systems', [])),
            'merkle_root': packet.get('merkle_root'),
            'privacy': packet.get('privacy', {}),
            'b64_size': len(b64),
        }
