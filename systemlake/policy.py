"""Policy Engine + Redaction Engine.

Policy Engine: Defines what can be read, summarized, redacted, hashed,
embedded, exported, or served. This is where we prevent accidental leakage.

Redaction Engine: Runs secret scanners before anything leaves the machine.
Any token-looking value gets replaced. Any file with risky name moves
into metadata-only mode.

Safety split: Crawl all locally. Expose selectively.
"""

import os
import re
import hashlib
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field


class AccessLevel(Enum):
    """What level of detail can be exposed for a file."""
    FULL = "full"           # Content + metadata + symbols
    METADATA_ONLY = "meta"  # Hash + size + type, no content
    DENIED = "denied"       # Not even metadata leaves the machine
    REDACTED = "redacted"   # Content with secrets stripped


class ExportCapability(Enum):
    """What operations are permitted on a file."""
    READ = "read"
    HASH = "hash"
    SUMMARIZE = "summarize"
    SYMBOLS = "symbols"
    SNIPPET = "snippet"
    EXPORT = "export"
    EMBED = "embed"


# Sensitive path patterns — denied by default
DENIED_PATTERNS = [
    r'\.ssh/',
    r'Keychains/',
    r'Library/Mail/',
    r'Library/Messages/',
    r'Library/Cookies/',
    r'Library/Safari/',
    r'Library/Application Support/Google/Chrome/',
    r'Library/Application Support/Firefox/',
    r'Library/Group Containers/',
    r'\.env(\.|$)',
    r'passwords/',
    r'wallets/',
    r'keystores/',
    r'secrets/',
    r'id_rsa$',
    r'id_ed25519$',
    r'\.pem$',
    r'\.key$',
    r'credentials.*\.json$',
]

# Metadata-only patterns — hash + size but no content
METADATA_ONLY_PATTERNS = [
    r'\.db$',
    r'\.sqlite$',
    r'\.sqlite3$',
    r'\.duckdb$',
    r'\.dmg$',
    r'\.pkg$',
    r'\.app/',
    r'node_modules/',
    r'\.git/',
    r'__pycache__/',
    r'\.pyc$',
]

# Secret value patterns for redaction
SECRET_VALUE_PATTERNS = [
    (r'sk-[A-Za-z0-9_\-]{20,}', 'openai_key'),
    (r'hf_[A-Za-z0-9]{20,}', 'hf_token'),
    (r'ghp_[A-Za-z0-9]{20,}', 'github_pat'),
    (r'github_pat_[A-Za-z0-9_]{20,}', 'github_fine_grained'),
    (r'AKIA[0-9A-Z]{16}', 'aws_access_key'),
    (r'-----BEGIN [A-Z ]*PRIVATE KEY-----', 'private_key'),
    (r'(?i)(api[_-]?key|secret|token|password|passwd|pwd)\s*[:=]\s*["\']?[^"\'\s]{8,}', 'generic_secret'),
    (r'xox[bpoa]-[A-Za-z0-9-]+', 'slack_token'),
    (r'eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+', 'jwt_token'),
]


@dataclass
class PolicyDecision:
    """Result of a policy check on a file."""
    access_level: AccessLevel
    capabilities: Set[ExportCapability]
    reason: str
    redaction_count: int = 0


class PolicyEngine:
    """Defines what can be read, summarized, exported, or served.

    Default policy:
    - Sensitive paths → DENIED
    - Database/package files → METADATA_ONLY
    - Source code → FULL (with redaction)
    - Everything else → REDACTED (content with secrets stripped)

    Two-pass support:
    - metadata_all: see every reachable file path, size, ext, mtime, hash
    - content pass: only read safe zones (code, docs, configs, tests, manifests)
    """

    # Content-safe extensions — allowed for content reading in underwriting pass
    CONTENT_SAFE_EXTS = {
        '.py', '.js', '.ts', '.tsx', '.jsx', '.rs', '.go', '.swift',
        '.java', '.kt', '.rb', '.php', '.c', '.cpp', '.h', '.hpp',
        '.cs', '.scala', '.clj', '.ex', '.exs', '.erl', '.recept',
        '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
        '.md', '.txt', '.rst', '.sh', '.sql', '.html', '.css', '.csv',
    }

    # Content-safe filenames (case-insensitive)
    CONTENT_SAFE_FILES = {
        'dockerfile', 'makefile', 'license', 'readme.md', 'pyproject.toml',
        'package.json', 'setup.py', 'requirements.txt', 'cargo.toml',
        'go.mod', 'gemfile', '.gitignore', 'docker-compose.yml',
    }

    def __init__(self, content_roots: List[str] = None, deny_paths: List[str] = None):
        self._denied = [re.compile(p, re.IGNORECASE) for p in DENIED_PATTERNS]
        self._meta_only = [re.compile(p, re.IGNORECASE) for p in METADATA_ONLY_PATTERNS]
        self._overrides: Dict[str, AccessLevel] = {}
        self._grants: Dict[str, Set[ExportCapability]] = {}
        self._content_roots = [os.path.expanduser(r) for r in (content_roots or [])]
        self._deny_paths = [os.path.expanduser(d) for d in (deny_paths or [])]

        # Add deny paths as regex patterns
        for dp in self._deny_paths:
            escaped = re.escape(dp)
            self._denied.append(re.compile(escaped, re.IGNORECASE))

    def evaluate(self, path: str, ext: str = None) -> PolicyDecision:
        """Evaluate policy for a file path."""
        low = path.lower()

        # Check denied patterns
        for pat in self._denied:
            if pat.search(low):
                return PolicyDecision(
                    access_level=AccessLevel.DENIED,
                    capabilities=set(),
                    reason='sensitive zone — denied by default',
                )

        # Check metadata-only patterns
        for pat in self._meta_only:
            if pat.search(low):
                return PolicyDecision(
                    access_level=AccessLevel.METADATA_ONLY,
                    capabilities={ExportCapability.HASH},
                    reason='binary/package — metadata only',
                )

        # Check overrides
        for pattern, level in self._overrides.items():
            if re.search(pattern, low):
                if level == AccessLevel.DENIED:
                    return PolicyDecision(level, set(), 'denied by override')
                break

        # Default: full access with redaction for text files
        if ext and ext.lower() in {'.py', '.js', '.ts', '.tsx', '.jsx', '.rs',
                                    '.go', '.swift', '.json', '.yaml', '.yml',
                                    '.toml', '.md', '.txt', '.sh', '.sql', '.recept',
                                    '.html', '.css', '.csv'}:
            return PolicyDecision(
                access_level=AccessLevel.REDACTED,
                capabilities={ExportCapability.READ, ExportCapability.HASH,
                             ExportCapability.SUMMARIZE, ExportCapability.SYMBOLS,
                             ExportCapability.SNIPPET, ExportCapability.EXPORT},
                reason='text file — full access with redaction',
            )

        # Non-text files: metadata only
        return PolicyDecision(
            access_level=AccessLevel.METADATA_ONLY,
            capabilities={ExportCapability.HASH},
            reason='non-text — metadata only',
        )

    def grant(self, path_pattern: str, capabilities: Set[ExportCapability]):
        """Grant specific capabilities for a path pattern."""
        self._grants[path_pattern] = capabilities

    def override(self, path_pattern: str, level: AccessLevel):
        """Override access level for a path pattern."""
        self._overrides[path_pattern] = level

    def can_export(self, path: str) -> bool:
        """Quick check if a file can be exported."""
        decision = self.evaluate(path)
        return ExportCapability.EXPORT in decision.capabilities

    def is_content_safe(self, path: str) -> bool:
        """Check if a file is safe for content reading in underwriting pass.

        A file is content-safe if:
        1. It's not denied
        2. It's within a content-root (if content_roots are set)
        3. It has a content-safe extension or filename
        """
        decision = self.evaluate(path)
        if decision.access_level == AccessLevel.DENIED:
            return False

        # If content_roots are set, file must be within one
        if self._content_roots:
            abs_path = os.path.expanduser(path)
            in_root = any(abs_path.startswith(cr) for cr in self._content_roots)
            if not in_root:
                return False

        ext = os.path.splitext(path)[1].lower()
        filename = os.path.basename(path).lower()

        if ext in self.CONTENT_SAFE_EXTS:
            return True
        if filename in self.CONTENT_SAFE_FILES:
            return True

        return False

    def metadata_decision(self, path: str) -> PolicyDecision:
        """First-pass: metadata only for any file (hash, size, type, mtime).

        Even denied paths get metadata in this pass (path hash only, no content).
        This builds the machine map without exporting raw contents.
        """
        low = path.lower()

        # Check denied — still get path hash but flagged
        for pat in self._denied:
            if pat.search(low):
                return PolicyDecision(
                    access_level=AccessLevel.DENIED,
                    capabilities={ExportCapability.HASH},
                    reason='sensitive zone — metadata hash only, content denied',
                )

        return PolicyDecision(
            access_level=AccessLevel.METADATA_ONLY,
            capabilities={ExportCapability.HASH},
            reason='metadata pass — hash + size + type only',
        )

    def content_decision(self, path: str) -> PolicyDecision:
        """Second-pass: content reading for safe zones only.

        Only reads code, docs, configs, tests, manifests, receipt files.
        Does not raw-read Mail, Messages, browser profiles, keychains,
        wallets, Photos, private keys, .env, or app databases.
        """
        if not self.is_content_safe(path):
            return PolicyDecision(
                access_level=AccessLevel.METADATA_ONLY,
                capabilities={ExportCapability.HASH},
                reason='not content-safe — metadata only',
            )

        return self.evaluate(path)


class RedactionEngine:
    """Runs secret scanners before anything leaves the machine.

    Any token-looking value gets replaced with [REDACTED_SECRET].
    Returns redacted text and count of redactions made.
    """

    def __init__(self):
        self._patterns = [(re.compile(p), label) for p, label in SECRET_VALUE_PATTERNS]
        self._total_redactions = 0
        self._files_redacted = 0

    def redact(self, text: str) -> Tuple[str, int]:
        """Redact secret values from text. Returns (redacted_text, count)."""
        count = 0
        out = text
        for pat, label in self._patterns:
            out, n = pat.subn('[REDACTED_SECRET]', out)
            count += n

        if count > 0:
            self._total_redactions += count
            self._files_redacted += 1

        return out, count

    def scan_file(self, filepath: str, max_bytes: int = 100000) -> Dict:
        """Scan a file for secrets without reading content into output."""
        try:
            with open(filepath, 'r', errors='replace') as f:
                content = f.read(max_bytes)
            _, count = self.redact(content)
            return {
                'path': filepath,
                'secrets_found': count,
                'scanned': True,
            }
        except Exception as e:
            return {
                'path': filepath,
                'secrets_found': 0,
                'scanned': False,
                'error': str(e)[:100],
            }

    def is_safe_name(self, filename: str) -> bool:
        """Check if a filename itself looks like a secret file."""
        low = filename.lower()
        risky = ['token', 'secret', 'private', 'wallet', 'keystore',
                 'credentials', 'password', '.env', '.pem', '.key',
                 'id_rsa', 'id_ed25519']
        return not any(r in low for r in risky)

    def summary(self) -> Dict:
        return {
            'total_redactions': self._total_redactions,
            'files_redacted': self._files_redacted,
            'patterns_active': len(self._patterns),
        }
