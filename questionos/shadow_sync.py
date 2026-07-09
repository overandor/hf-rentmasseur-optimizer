"""QuestionOS Shadow Sync — Export/Import snapshots for cloud VM.

Architecture:
- Mac runs heavy local compute when present
- Before shutdown: export QuestionOS snapshot (repos, state, datasets, receipts, endpoints)
- Cloud Ubuntu VM imports snapshot and serves approved endpoints
- On return: Mac pulls back new receipts, usage logs, dataset deltas

The shadow is not a full clone of the Mac. It's a functional clone of work state.
"""

import os
import json
import tarfile
import hashlib
import subprocess
from datetime import datetime
from typing import Dict, List, Optional


class ShadowSync:
    """Handles export/import of QuestionOS state for shadow VM deployment.

    The snapshot contains:
    - Compressed datasets (question residues)
    - Receipt ledger
    - Question/Execution/Cost-Avoidance ledgers
    - Endpoint definitions (FastAPI apps)
    - SQLite/DuckDB state
    - Secrets policy (never actual secrets)
    - Docker image hash (if containerized)

    The snapshot does NOT contain:
    - Raw API keys, tokens, or credentials
    - Full repo clones (only approved repo list)
    - System-level configuration
    """

    def __init__(self, base_dir: str = None):
        self.base_dir = base_dir or os.path.join(os.getcwd(), 'questionos')
        self.snapshots_dir = os.path.join(self.base_dir, 'snapshots')
        os.makedirs(self.snapshots_dir, exist_ok=True)

    def export_snapshot(self, label: str = None) -> Dict:
        """Export current QuestionOS state as a portable snapshot.

        Returns metadata about the snapshot including path and manifest.
        """
        timestamp = datetime.now().isoformat()
        snapshot_name = f"snapshot_{timestamp.replace(':', '-').replace('.', '_')}"
        if label:
            snapshot_name += f"_{label}"
        snapshot_dir = os.path.join(self.snapshots_dir, snapshot_name)
        os.makedirs(snapshot_dir, exist_ok=True)

        manifest = {
            'snapshot_id': snapshot_name,
            'created_at': timestamp,
            'label': label or 'unnamed',
            'components': {},
            'secrets_policy': 'no_secrets_included',
            'compatible_runtime': 'ubuntu-22.04+',
        }

        # 1. Copy ledgers
        ledgers_src = os.path.join(self.base_dir, 'ledgers')
        ledgers_dst = os.path.join(snapshot_dir, 'ledgers')
        if os.path.exists(ledgers_src):
            self._copy_dir(ledgers_src, ledgers_dst)
            manifest['components']['ledgers'] = self._dir_info(ledgers_dst)

        # 2. Copy datasets (compressed question residues)
        datasets_src = os.path.join(self.base_dir, 'datasets')
        datasets_dst = os.path.join(snapshot_dir, 'datasets')
        if os.path.exists(datasets_src):
            self._copy_dir(datasets_src, datasets_dst)
            manifest['components']['datasets'] = self._dir_info(datasets_dst)

        # 3. Copy receipts
        receipts_src = os.path.join(self.base_dir, 'receipts')
        receipts_dst = os.path.join(snapshot_dir, 'receipts')
        if os.path.exists(receipts_src):
            self._copy_dir(receipts_src, receipts_dst)
            manifest['components']['receipts'] = self._dir_info(receipts_dst)

        # 4. Copy session states (not raw questions unless access_policy allows)
        sessions_src = os.path.join(self.base_dir, 'sessions')
        sessions_dst = os.path.join(snapshot_dir, 'sessions')
        if os.path.exists(sessions_src):
            self._copy_dir(sessions_src, sessions_dst)
            manifest['components']['sessions'] = self._dir_info(sessions_dst)

        # 5. Collect endpoint definitions
        endpoints = self._collect_endpoints()
        if endpoints:
            endpoints_path = os.path.join(snapshot_dir, 'endpoints.json')
            with open(endpoints_path, 'w') as f:
                json.dump(endpoints, f, indent=2)
            manifest['components']['endpoints'] = {'count': len(endpoints), 'file': 'endpoints.json'}

        # 6. Write secrets policy (never actual secrets)
        policy = {
            'policy': 'no_secrets_included',
            'note': 'Cloud VM must use its own environment variables for credentials.',
            'required_env_vars': self._detect_required_env_vars(),
        }
        policy_path = os.path.join(snapshot_dir, 'secrets_policy.json')
        with open(policy_path, 'w') as f:
            json.dump(policy, f, indent=2)
        manifest['secrets_policy'] = policy

        # 7. Compute snapshot hash
        manifest_path = os.path.join(snapshot_dir, 'manifest.json')
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)

        snapshot_hash = self._hash_dir(snapshot_dir)
        manifest['snapshot_hash'] = snapshot_hash
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)

        # 8. Create tarball for transfer
        tarball_path = os.path.join(self.snapshots_dir, f"{snapshot_name}.tar.gz")
        with tarfile.open(tarball_path, 'w:gz') as tar:
            tar.add(snapshot_dir, arcname=snapshot_name)

        manifest['tarball_path'] = tarball_path
        manifest['tarball_size'] = os.path.getsize(tarball_path)

        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)

        return manifest

    def import_snapshot(self, snapshot_path: str) -> Dict:
        """Import a snapshot from a tarball or directory.

        Merges new receipts, usage logs, and dataset deltas from the shadow VM.
        """
        if snapshot_path.endswith('.tar.gz'):
            extract_dir = os.path.join(self.snapshots_dir, 'importing')
            os.makedirs(extract_dir, exist_ok=True)
            with tarfile.open(snapshot_path, 'r:gz') as tar:
                tar.extractall(extract_dir)
            snapshot_name = os.listdir(extract_dir)[0]
            snapshot_dir = os.path.join(extract_dir, snapshot_name)
        else:
            snapshot_dir = snapshot_path

        manifest_path = os.path.join(snapshot_dir, 'manifest.json')
        if not os.path.exists(manifest_path):
            return {'imported': False, 'error': 'no manifest found'}

        with open(manifest_path) as f:
            manifest = json.load(f)

        # Verify hash
        expected_hash = manifest.get('snapshot_hash')
        actual_hash = self._hash_dir(snapshot_dir, exclude=['manifest.json'])
        if expected_hash and actual_hash != expected_hash:
            return {'imported': False, 'error': 'hash mismatch', 
                    'expected': expected_hash[:16], 'actual': actual_hash[:16]}

        imported = {}

        # Merge ledgers (append new entries)
        ledgers_src = os.path.join(snapshot_dir, 'ledgers')
        if os.path.exists(ledgers_src):
            ledgers_dst = os.path.join(self.base_dir, 'ledgers')
            merged = self._merge_ledgers(ledgers_src, ledgers_dst)
            imported['ledgers'] = merged

        # Merge datasets
        datasets_src = os.path.join(snapshot_dir, 'datasets')
        if os.path.exists(datasets_src):
            datasets_dst = os.path.join(self.base_dir, 'datasets')
            merged = self._merge_dirs(datasets_src, datasets_dst)
            imported['datasets'] = merged

        # Merge receipts
        receipts_src = os.path.join(snapshot_dir, 'receipts')
        if os.path.exists(receipts_src):
            receipts_dst = os.path.join(self.base_dir, 'receipts')
            merged = self._merge_dirs(receipts_src, receipts_dst)
            imported['receipts'] = merged

        # Clean up extracted dir
        if snapshot_path.endswith('.tar.gz'):
            import shutil
            shutil.rmtree(extract_dir, ignore_errors=True)

        return {
            'imported': True,
            'snapshot': manifest.get('snapshot_id'),
            'components': imported,
            'verified': True,
        }

    def _copy_dir(self, src: str, dst: str):
        """Copy directory contents."""
        import shutil
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)

    def _merge_dirs(self, src: str, dst: str) -> Dict:
        """Merge src into dst, adding files that don't exist."""
        os.makedirs(dst, exist_ok=True)
        added = 0
        skipped = 0
        for item in os.listdir(src):
            src_path = os.path.join(src, item)
            dst_path = os.path.join(dst, item)
            if not os.path.exists(dst_path):
                import shutil
                if os.path.isdir(src_path):
                    shutil.copytree(src_path, dst_path)
                else:
                    shutil.copy2(src_path, dst_path)
                added += 1
            else:
                skipped += 1
        return {'added': added, 'skipped': skipped}

    def _merge_ledgers(self, src: str, dst: str) -> Dict:
        """Merge ledger JSON files, appending new entries."""
        os.makedirs(dst, exist_ok=True)
        merged = {}
        for ledger_file in os.listdir(src):
            if not ledger_file.endswith('.json'):
                continue
            src_path = os.path.join(src, ledger_file)
            dst_path = os.path.join(dst, ledger_file)

            if not os.path.exists(dst_path):
                import shutil
                shutil.copy2(src_path, dst_path)
                merged[ledger_file] = 'copied'
                continue

            with open(src_path) as f:
                src_data = json.load(f)
            with open(dst_path) as f:
                dst_data = json.load(f)

            if isinstance(src_data, list) and isinstance(dst_data, list):
                existing_ids = {e.get('entry_id') or e.get('question_id') or e.get('receipt_id') 
                               for e in dst_data if isinstance(e, dict)}
                new_entries = [e for e in src_data 
                              if (e.get('entry_id') or e.get('question_id') or e.get('receipt_id')) not in existing_ids]
                dst_data.extend(new_entries)
                with open(dst_path, 'w') as f:
                    json.dump(dst_data, f, indent=2)
                merged[ledger_file] = f'added {len(new_entries)} entries'
            else:
                merged[ledger_file] = 'skipped (non-list format)'

        return merged

    def _collect_endpoints(self) -> List[Dict]:
        """Collect endpoint definitions from sessions."""
        endpoints = []
        sessions_dir = os.path.join(self.base_dir, 'sessions')
        if not os.path.exists(sessions_dir):
            return endpoints

        for session_id in os.listdir(sessions_dir):
            state_path = os.path.join(sessions_dir, session_id, 'state.json')
            if os.path.exists(state_path):
                with open(state_path) as f:
                    state = json.load(f)
                if state.get('endpoint_url'):
                    serve_path = os.path.join(sessions_dir, session_id, 'serve.py')
                    endpoints.append({
                        'session_id': session_id,
                        'url': state['endpoint_url'],
                        'intent': state.get('intent_class'),
                        'project': state.get('project'),
                        'serve_script': os.path.basename(serve_path) if os.path.exists(serve_path) else None,
                    })
        return endpoints

    def _detect_required_env_vars(self) -> List[str]:
        """Detect environment variables referenced in session files."""
        env_vars = set()
        sessions_dir = os.path.join(self.base_dir, 'sessions')
        if not os.path.exists(sessions_dir):
            return []

        for session_id in os.listdir(sessions_dir):
            session_dir = os.path.join(sessions_dir, session_id)
            for fname in os.listdir(session_dir):
                if fname.endswith('.py') or fname.endswith('.sh'):
                    fpath = os.path.join(session_dir, fname)
                    try:
                        with open(fpath) as f:
                            content = f.read()
                        import re
                        matches = re.findall(r'os\.environ\.get\(["\'](\w+)["\']', content)
                        matches += re.findall(r'\$\{(\w+)\}', content)
                        env_vars.update(matches)
                    except Exception:
                        pass

        return sorted(list(env_vars))

    def _dir_info(self, path: str) -> Dict:
        """Get directory info."""
        total_size = 0
        file_count = 0
        for root, dirs, files in os.walk(path):
            for f in files:
                fp = os.path.join(root, f)
                total_size += os.path.getsize(fp)
                file_count += 1
        return {'files': file_count, 'size_bytes': total_size}

    def _hash_dir(self, dir_path: str, exclude: List[str] = None) -> str:
        """Compute SHA-256 hash of a directory's contents."""
        exclude = exclude or []
        h = hashlib.sha256()
        for root, dirs, files in os.walk(dir_path):
            dirs.sort()
            files.sort()
            for f in files:
                if f in exclude:
                    continue
                fpath = os.path.join(root, f)
                relpath = os.path.relpath(fpath, dir_path)
                h.update(relpath.encode())
                with open(fpath, 'rb') as fh:
                    h.update(fh.read())
        return h.hexdigest()

    def list_snapshots(self) -> List[Dict]:
        """List available snapshots."""
        snapshots = []
        if not os.path.exists(self.snapshots_dir):
            return snapshots

        for item in sorted(os.listdir(self.snapshots_dir), reverse=True):
            if item.endswith('.tar.gz'):
                manifest_name = item.replace('.tar.gz', '')
                manifest_path = os.path.join(self.snapshots_dir, manifest_name, 'manifest.json')
                if os.path.exists(manifest_path):
                    with open(manifest_path) as f:
                        m = json.load(f)
                    snapshots.append({
                        'name': manifest_name,
                        'label': m.get('label'),
                        'created': m.get('created_at', '?')[:19],
                        'size': os.path.getsize(os.path.join(self.snapshots_dir, item)),
                        'hash': m.get('snapshot_hash', '?')[:16],
                    })
        return snapshots
