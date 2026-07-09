"""MachineLake Daemon — Filesystem crawler with SQLite index and Merkle root.

Runs every N minutes. Walks the filesystem. Builds a SQLite index.
Computes SHA-256 hashes. Detects deltas. Maintains a Merkle root
for the current machine state.

The lake stays local. Nothing leaves the machine through this layer.
"""

import os
import sqlite3
import hashlib
import time
import json
import threading
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict


# Directories that are always excluded from crawling
EXCLUDE_DIRS = {
    '.git', 'node_modules', '.venv', 'venv', '__pycache__', '.next',
    '.cache', 'dist', 'build', 'target', '.pytest_cache', '.mypy_cache',
    '.Trash', '.Spotlight-V100', '.DocumentRevisions-V100',
    '.fseventsd', '.TemporaryItems', '.vol',
    'Library', 'Photos', 'Music', 'Movies', 'Pictures',
    'Caches', 'Containers', 'Group Containers',
    '.npm', '.cargo', '.rustup', '.docker', '.colima',
    '.orbstack', '.lima', '.gradle', '.m2', '.ivy2',
    '.windsurf', '.vscode', '.cursor', '.qwen',
}

# Sensitive zones — metadata only, never content
SENSITIVE_DIRS = {
    '.ssh', 'Keychains', 'Library/Mail', 'Library/Messages',
    'Library/Cookies', 'Library/Safari', 'Library/Application Support/Google/Chrome',
    'Library/Application Support/Firefox', 'Library/Group Containers',
    '.env', 'passwords', 'wallets', 'keystores', 'secrets',
}

# File extensions that indicate code
CODE_EXTS = {'.py', '.js', '.ts', '.tsx', '.jsx', '.rs', '.go', '.swift',
             '.java', '.kt', '.rb', '.php', '.c', '.cpp', '.h', '.hpp',
             '.cs', '.scala', '.clj', '.ex', '.exs', '.erl', '.recept'}

# File extensions that indicate config
CONFIG_EXTS = {'.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf', '.env'}

# File extensions that indicate docs
DOC_EXTS = {'.md', '.txt', '.rst', '.pdf', '.docx', '.rtf'}

# Text file extensions for content reading
TEXT_EXTS = CODE_EXTS | CONFIG_EXTS | DOC_EXTS | {'.sh', '.sql', '.html', '.css', '.csv'}


class MachineLake:
    """Local filesystem lake with SQLite index and Merkle root.

    Crawls the filesystem, stores metadata in SQLite, computes SHA-256 hashes,
    detects deltas between crawls, and maintains a Merkle root for state verification.

    The lake never exposes raw files. All exposure goes through the Gateway.
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT NOT NULL UNIQUE,
        filename TEXT,
        ext TEXT,
        mime TEXT,
        size INTEGER,
        sha256 TEXT,
        modified REAL,
        category TEXT,
        is_sensitive INTEGER DEFAULT 0,
        is_code INTEGER DEFAULT 0,
        is_config INTEGER DEFAULT 0,
        is_test INTEGER DEFAULT 0,
        is_doc INTEGER DEFAULT 0,
        first_seen TEXT,
        last_seen TEXT,
        deleted INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS crawls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT,
        finished_at TEXT,
        root TEXT,
        file_count INTEGER,
        total_size INTEGER,
        merkle_root TEXT,
        new_files INTEGER,
        changed_files INTEGER,
        deleted_files INTEGER,
        duration_ms INTEGER
    );

    CREATE TABLE IF NOT EXISTS systems (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        root_path TEXT NOT NULL,
        detected_type TEXT,
        file_count INTEGER DEFAULT 0,
        has_tests INTEGER DEFAULT 0,
        has_endpoints INTEGER DEFAULT 0,
        has_receipts INTEGER DEFAULT 0,
        has_readme INTEGER DEFAULT 0,
        has_git INTEGER DEFAULT 0,
        has_dockerfile INTEGER DEFAULT 0,
        has_requirements INTEGER DEFAULT 0,
        has_package_json INTEGER DEFAULT 0,
        has_setup_py INTEGER DEFAULT 0,
        has_makefile INTEGER DEFAULT 0,
        first_seen TEXT,
        last_seen TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);
    CREATE INDEX IF NOT EXISTS idx_files_sha ON files(sha256);
    CREATE INDEX IF NOT EXISTS idx_files_category ON files(category);
    CREATE INDEX IF NOT EXISTS idx_systems_name ON systems(name);
    """

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.path.expanduser(
            '~/Library/Application Support/Membra/systemlake.db')
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._lock = threading.Lock()
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript(self.SCHEMA)
        conn.commit()

    def _sha256_file(self, path: str) -> Optional[str]:
        try:
            h = hashlib.sha256()
            with open(path, 'rb') as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return None

    def _sha256_metadata(self, path: str, size: int, mtime: float) -> str:
        """Fast hash of path + size + mtime — no file content read."""
        h = hashlib.sha256()
        h.update(path.encode())
        h.update(str(size).encode())
        h.update(str(int(mtime)).encode())
        return h.hexdigest()

    def _sha256_bytes(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _is_sensitive(self, path: str) -> bool:
        low = path.lower()
        for s in SENSITIVE_DIRS:
            if s.lower() in low:
                return True
        return False

    def _classify(self, ext: str, filename: str) -> str:
        ext = ext.lower()
        fn = filename.lower()

        if 'test' in fn or fn.startswith('test_') or fn.endswith('_test.py'):
            return 'test'
        if ext in CODE_EXTS:
            return 'code'
        if ext in CONFIG_EXTS:
            return 'config'
        if ext in DOC_EXTS:
            return 'doc'
        if ext in ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico'):
            return 'image'
        if ext in ('.db', '.sqlite', '.sqlite3', '.duckdb'):
            return 'database'
        if ext in ('.dmg', '.pkg', '.app'):
            return 'package'
        if fn in ('dockerfile', 'makefile', 'license', 'readme.md'):
            return 'meta'
        return 'other'

    def crawl(self, root: str, max_files: int = 50000,
             metadata_only: bool = False,
             content_roots: List[str] = None,
             deny_paths: List[str] = None) -> Dict:
        """Crawl a root directory and update the lake index.

        Two-pass crawl:
        1. metadata_only=True: hash + size + type for every reachable file
        2. metadata_only=False: content analysis for safe zones only

        Returns crawl statistics including Merkle root.
        """
        root = os.path.expanduser(root)
        start = time.time()
        started_at = datetime.now().isoformat()
        now_str = started_at

        new_files = 0
        changed_files = 0
        deleted_files = 0
        file_count = 0
        total_size = 0
        file_hashes: List[Tuple[str, str]] = []

        # Get existing paths for deletion detection
        conn = self._get_conn()
        existing = set()
        for row in conn.execute('SELECT path FROM files WHERE deleted = 0'):
            existing.add(row['path'])

        seen = set()

        # Build policy if content_roots or deny_paths provided
        from .policy import PolicyEngine, AccessLevel
        policy = None
        if content_roots or deny_paths:
            policy = PolicyEngine(content_roots=content_roots, deny_paths=deny_paths)

        for dirpath, dirnames, filenames in os.walk(root):
            # Stop if we've hit max_files
            if file_count >= max_files:
                dirnames.clear()
                continue

            # Filter excluded dirs
            dirnames[:] = [d for d in dirnames
                          if d not in EXCLUDE_DIRS and not d.startswith('.git')]

            # Filter denied paths from descent
            if policy and deny_paths:
                dirnames[:] = [d for d in dirnames
                              if not any(os.path.join(dirpath, d).startswith(dp)
                                        for dp in deny_paths)]

            for fname in filenames:
                if file_count >= max_files:
                    dirnames.clear()
                    break

                fpath = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(fpath, root)
                seen.add(rel_path)

                try:
                    st = os.stat(fpath)
                except Exception:
                    continue

                ext = os.path.splitext(fname)[1]
                sensitive = self._is_sensitive(fpath)
                category = self._classify(ext, fname)

                # Compute hash
                # In metadata_only pass, use fast path+size+mtime hash (no content read)
                # In content pass, hash actual file content for safe files
                sha = None
                if metadata_only:
                    sha = self._sha256_metadata(fpath, st.st_size, st.st_mtime)
                elif not sensitive and st.st_size < 10_000_000:
                    sha = self._sha256_file(fpath)

                # In content pass, check policy for content safety
                if not metadata_only and policy:
                    content_decision = policy.content_decision(fpath)
                    if content_decision.access_level == AccessLevel.DENIED:
                        sensitive = True  # upgrade to sensitive if denied by policy

                is_code = 1 if ext in CODE_EXTS else 0
                is_config = 1 if ext in CONFIG_EXTS else 0
                is_test = 1 if 'test' in fname.lower() else 0
                is_doc = 1 if ext in DOC_EXTS else 0

                # Check if file exists in DB
                prev = conn.execute(
                    'SELECT sha256, size, first_seen FROM files WHERE path = ? AND deleted = 0',
                    (rel_path,)
                ).fetchone()

                if prev is None:
                    new_files += 1
                elif prev['sha256'] != sha or prev['size'] != st.st_size:
                    changed_files += 1

                first_seen = prev['first_seen'] if prev else now_str

                conn.execute("""
                    INSERT OR REPLACE INTO files
                    (path, filename, ext, mime, size, sha256, modified,
                     category, is_sensitive, is_code, is_config, is_test, is_doc,
                     first_seen, last_seen, deleted)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """, (
                    rel_path, fname, ext,
                    mimetypes.guess_type(fpath)[0],
                    st.st_size, sha, st.st_mtime,
                    category, sensitive, is_code, is_config, is_test, is_doc,
                    first_seen,
                    now_str,
                ))

                file_count += 1
                total_size += st.st_size

                if sha:
                    file_hashes.append((rel_path, sha))

        # Detect deleted files
        deleted = existing - seen
        for d in deleted:
            conn.execute('UPDATE files SET deleted = 1 WHERE path = ?', (d,))
            deleted_files += 1

        # Compute Merkle root
        file_hashes.sort()
        merkle_root = self._compute_merkle_root(file_hashes)

        # Detect systems (project directories)
        self._detect_systems(root, conn, now_str)

        duration_ms = int((time.time() - start) * 1000)
        finished_at = datetime.now().isoformat()

        conn.execute("""
            INSERT INTO crawls
            (started_at, finished_at, root, file_count, total_size,
             merkle_root, new_files, changed_files, deleted_files, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (started_at, finished_at, root, file_count, total_size,
              merkle_root, new_files, changed_files, deleted_files, duration_ms))
        conn.commit()

        return {
            'root': root,
            'file_count': file_count,
            'total_size': total_size,
            'new_files': new_files,
            'changed_files': changed_files,
            'deleted_files': deleted_files,
            'merkle_root': merkle_root,
            'duration_ms': duration_ms,
            'started_at': started_at,
            'finished_at': finished_at,
        }

    def _compute_merkle_root(self, file_hashes: List[Tuple[str, str]]) -> str:
        """Compute Merkle root from file path + hash pairs.

        Builds a Merkle tree where leaves are hash(path + sha256).
        Root proves the complete state of the lake.
        """
        if not file_hashes:
            return self._sha256_bytes(b'EMPTY')

        # Build leaf hashes
        leaves = []
        for path, sha in file_hashes:
            leaf = self._sha256_bytes(f"{path}:{sha}".encode())
            leaves.append(leaf)

        # Build tree
        while len(leaves) > 1:
            next_level = []
            for i in range(0, len(leaves), 2):
                if i + 1 < len(leaves):
                    combined = self._sha256_bytes(
                        (leaves[i] + leaves[i + 1]).encode())
                else:
                    combined = leaves[i]
                next_level.append(combined)
            leaves = next_level

        return leaves[0]

    # Markers that alone justify system detection
    STRONG_MARKERS = {'has_git', 'has_dockerfile', 'has_requirements',
                      'has_setup_py', 'has_makefile'}

    def _is_junk_system(self, dirpath: str, dirname: str, markers_found: set) -> bool:
        """Filter out non-project directories that happen to have marker files."""
        path_lower = dirpath.lower()
        # Skip if inside an extensions directory
        if '/extensions/' in path_lower or '/extension/' in path_lower:
            return True
        # Skip version-numbered package dirs (e.g. ms-python.python-2026.4.0-universal)
        if any(c.isdigit() for c in dirname) and '-' in dirname and len(dirname) > 10:
            return True
        # Skip dirs with only README but no code, no git, no build files
        if markers_found == {'has_readme'}:
            return True
        # Skip dirs with only package.json but inside node_modules or vendor
        if markers_found == {'has_package_json'} and ('node_modules' in path_lower or 'vendor' in path_lower):
            return True
        return False

    def _detect_systems(self, root: str, conn, now_str: str, max_dirs: int = 500):
        """Detect project/system directories by marker files.

        Filters out junk directories (IDE extensions, package caches, vendor blobs)
        and requires at least 2 markers or 1 strong marker for a system to be registered.
        """
        root_path = Path(root)

        markers = {
            'requirements.txt': 'has_requirements',
            'package.json': 'has_package_json',
            'setup.py': 'has_setup_py',
            'Makefile': 'has_makefile',
            'Dockerfile': 'has_dockerfile',
            '.git': 'has_git',
            'README.md': 'has_readme',
        }

        systems = {}
        dirs_visited = 0

        for dirpath, dirnames, filenames in os.walk(root):
            dirs_visited += 1
            if dirs_visited > max_dirs:
                break

            # Check for .git BEFORE filtering it from dirnames
            has_git_dir = '.git' in dirnames

            dirnames[:] = [d for d in dirnames
                          if d not in EXCLUDE_DIRS and not d.startswith('.git')]

            dir_files = set(filenames + dirnames)
            if has_git_dir:
                dir_files.add('.git')
            markers_found = set()
            for m, col in markers.items():
                if m in dir_files:
                    markers_found.add(col)

            if not markers_found:
                continue

            dirname = os.path.basename(dirpath) or 'root'

            # Filter junk systems
            if self._is_junk_system(dirpath, dirname, markers_found):
                continue

            # Require at least 2 markers, or 1 strong marker, or git+code
            has_code = any(f.endswith(('.py', '.js', '.ts', '.go', '.rs', '.java'))
                          for f in filenames)
            if len(markers_found) < 2 and not (markers_found & self.STRONG_MARKERS):
                if not (markers_found == {'has_git'} and has_code):
                    continue

            sys_name = dirname
            if sys_name not in systems:
                systems[sys_name] = {
                    'root_path': dirpath,
                    'file_count': 0,
                    'has_tests': 0,
                    'has_endpoints': 0,
                    'has_receipts': 0,
                }

            sys_info = systems[sys_name]
            sys_info['file_count'] += len(filenames)

            for col in markers_found:
                sys_info[col] = 1

            # Check for tests
            if any('test' in f.lower() for f in filenames):
                sys_info['has_tests'] = 1

            # Check for endpoints by filename pattern only (no content read)
            endpoint_files = {'app.py', 'server.py', 'main.py', 'server.js', 'index.js'}
            if endpoint_files & set(filenames):
                sys_info['has_endpoints'] = 1

            # Check for receipts by filename pattern only
            if any('receipt' in f.lower() for f in filenames):
                sys_info['has_receipts'] = 1

        # Upsert systems
        for name, info in systems.items():
            existing = conn.execute(
                'SELECT id FROM systems WHERE name = ? AND root_path = ?',
                (name, info['root_path'])
            ).fetchone()

            if existing:
                conn.execute("""
                    UPDATE systems SET
                        file_count = ?, has_tests = ?, has_endpoints = ?,
                        has_receipts = ?, has_readme = ?, has_git = ?,
                        has_dockerfile = ?, has_requirements = ?,
                        has_package_json = ?, has_setup_py = ?, has_makefile = ?,
                        last_seen = ?
                    WHERE id = ?
                """, (
                    info['file_count'], info['has_tests'], info['has_endpoints'],
                    info['has_receipts'], info.get('has_readme', 0),
                    info.get('has_git', 0), info.get('has_dockerfile', 0),
                    info.get('has_requirements', 0), info.get('has_package_json', 0),
                    info.get('has_setup_py', 0), info.get('has_makefile', 0),
                    now_str, existing['id']
                ))
            else:
                conn.execute("""
                    INSERT INTO systems
                    (name, root_path, detected_type, file_count, has_tests,
                     has_endpoints, has_receipts, has_readme, has_git,
                     has_dockerfile, has_requirements, has_package_json,
                     has_setup_py, has_makefile, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    name, info['root_path'], 'auto', info['file_count'],
                    info['has_tests'], info['has_endpoints'], info['has_receipts'],
                    info.get('has_readme', 0), info.get('has_git', 0),
                    info.get('has_dockerfile', 0), info.get('has_requirements', 0),
                    info.get('has_package_json', 0), info.get('has_setup_py', 0),
                    info.get('has_makefile', 0), now_str, now_str
                ))

    def get_merkle_root(self) -> Optional[str]:
        """Get the latest Merkle root."""
        conn = self._get_conn()
        row = conn.execute(
            'SELECT merkle_root FROM crawls ORDER BY id DESC LIMIT 1'
        ).fetchone()
        return row['merkle_root'] if row else None

    def get_delta(self, since_merkle_root: str) -> Dict:
        """Get changes since a given Merkle root."""
        conn = self._get_conn()
        # Find the crawl with that root
        baseline = conn.execute(
            'SELECT id, finished_at FROM crawls WHERE merkle_root = ?',
            (since_merkle_root,)
        ).fetchone()

        if not baseline:
            return {'error': 'unknown merkle root', 'requested': since_merkle_root[:16]}

        # Get files changed since baseline
        changed = conn.execute("""
            SELECT path, sha256, size, category, deleted
            FROM files
            WHERE last_seen > ? OR deleted = 1
            ORDER BY path
        """, (baseline['finished_at'],)).fetchall()

        return {
            'since_root': since_merkle_root[:16],
            'baseline_crawl': baseline['id'],
            'changed_files': len(changed),
            'files': [{'path': r['path'], 'sha256': r['sha256'],
                       'size': r['size'], 'category': r['category'],
                       'deleted': bool(r['deleted'])}
                      for r in changed],
        }

    def list_systems(self) -> List[Dict]:
        """List all detected systems."""
        conn = self._get_conn()
        rows = conn.execute('SELECT * FROM systems ORDER BY name').fetchall()
        return [dict(r) for r in rows]

    def get_system(self, system_id: int) -> Optional[Dict]:
        """Get a system by ID."""
        conn = self._get_conn()
        row = conn.execute('SELECT * FROM systems WHERE id = ?', (system_id,)).fetchone()
        return dict(row) if row else None

    def list_files(self, system_name: str = None, category: str = None,
                   limit: int = 100) -> List[Dict]:
        """List files with optional filters."""
        conn = self._get_conn()
        query = 'SELECT * FROM files WHERE deleted = 0'
        params = []
        if category:
            query += ' AND category = ?'
            params.append(category)
        if system_name:
            query += ' AND path LIKE ?'
            params.append(f'{system_name}/%')
        query += ' ORDER BY path LIMIT ?'
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def summary(self) -> Dict:
        """Get lake summary statistics."""
        conn = self._get_conn()
        total = conn.execute(
            'SELECT COUNT(*) as c FROM files WHERE deleted = 0').fetchone()['c']
        total_size = conn.execute(
            'SELECT COALESCE(SUM(size), 0) as s FROM files WHERE deleted = 0'
        ).fetchone()['s']

        by_category = {}
        for row in conn.execute(
            'SELECT category, COUNT(*) as c FROM files WHERE deleted = 0 GROUP BY category'
        ):
            by_category[row['category']] = row['c']

        systems = conn.execute('SELECT COUNT(*) as c FROM systems').fetchone()['c']
        crawls = conn.execute('SELECT COUNT(*) as c FROM crawls').fetchone()['c']

        latest = conn.execute(
            'SELECT * FROM crawls ORDER BY id DESC LIMIT 1'
        ).fetchone()

        return {
            'total_files': total,
            'total_size': total_size,
            'by_category': by_category,
            'systems': systems,
            'crawl_count': crawls,
            'latest_crawl': dict(latest) if latest else None,
            'merkle_root': self.get_merkle_root(),
        }
