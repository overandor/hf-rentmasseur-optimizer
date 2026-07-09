"""
BlurHash64 — Adjustable-Fidelity Glyph Encodings
=================================================
Fidelity ladder from opaque hash (L0) to full transport (L9).

Levels:
  L0: null glyph — no information
  L1: presence — file exists
  L2: type — file class (python, pdf, image, etc.)
  L3: metadata — size, ext, timestamps, mime
  L4: feature — imports, functions, deps, entities, schema
  L5: sketch — lossy summary, preview, semantic description
  L6: receipt — hash commitments, provenance, proof claims
  L7: partial-body — selected chunks, redacted fragments
  L8: encrypted-body — full body, key-gated
  L9: full transport — Base64, fully reconstructable

Separates: Identity, Resemblance, Recoverability, Executability
"""

import os
import json
import time
import hashlib
import base64
import struct
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def merkle_commitment(data: bytes, chunk_size: int = 4096) -> dict:
    chunks = [data[i:i+chunk_size] for i in range(0, len(data), chunk_size)]
    if not chunks:
        chunks = [b""]
    leaf_hashes = [sha256(c) for c in chunks]
    tree = list(leaf_hashes)
    while len(tree) > 1:
        next_level = []
        for i in range(0, len(tree) - 1, 2):
            next_level.append(sha256((tree[i] + tree[i+1]).encode()))
        if len(tree) % 2 == 1:
            next_level.append(tree[-1])
        tree = next_level
    return {
        "root": tree[0] if tree else sha256(b""),
        "leaf_count": len(leaf_hashes),
        "leaf_hashes": leaf_hashes[:16],
    }


def blur_hash64(data: bytes) -> str:
    """Non-reversible fidelity label. SHA-512 truncated to 64 chars base64."""
    h = hashlib.sha512(data).digest()
    return base64.b64encode(h[:48]).decode()[:64]


def detect_file_class(filename: str, content: str) -> str:
    ext = Path(filename).suffix.lower()
    head = content[:1000] if content else ""
    class_map = {
        ".py": "python_source", ".js": "javascript_source", ".ts": "typescript_source",
        ".swift": "swift_source", ".cpp": "cpp_source", ".c": "c_source",
        ".rs": "rust_source", ".go": "go_source", ".java": "java_source",
        ".rb": "ruby_source", ".sh": "shell_script", ".sql": "sql_query",
        ".json": "json_data", ".yaml": "yaml_config", ".yml": "yaml_config",
        ".xml": "xml_data", ".csv": "csv_dataset", ".tsv": "tsv_dataset",
        ".md": "markdown_document", ".txt": "text_document",
        ".pdf": "pdf_document", ".png": "image_png", ".jpg": "image_jpeg",
        ".jpeg": "image_jpeg", ".gif": "image_gif", ".svg": "image_svg",
        ".html": "html_document", ".css": "css_stylesheet",
        ".zip": "archive_zip", ".tar": "archive_tar", ".gz": "archive_gzip",
        ".db": "sqlite_database", ".sqlite": "sqlite_database",
        ".parquet": "parquet_dataset", ".arrow": "arrow_dataset",
    }
    if ext in class_map:
        return class_map[ext]
    if "def " in head or "import " in head:
        return "python_source"
    if "function " in head or "const " in head:
        return "javascript_source"
    if "SELECT" in head.upper():
        return "sql_query"
    if head.strip().startswith("{") or head.strip().startswith("["):
        return "json_data"
    if "<html" in head.lower() or "<!DOCTYPE" in head:
        return "html_document"
    return "text"


def extract_features(content: str, file_class: str) -> dict:
    """Extract semantic features from text content."""
    features = {
        "imports": [], "functions": [], "classes": [],
        "entities": [], "dependencies": [],
        "line_count": 0, "word_count": 0,
        "has_tests": False, "has_secrets": False,
    }
    if not content:
        return features

    lines = content.split("\n")
    features["line_count"] = len(lines)
    features["word_count"] = len(content.split())

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from ") and " import" in stripped:
            features["imports"].append(stripped[:80])
        if stripped.startswith("def "):
            fname = stripped.split("(")[0].replace("def ", "")
            features["functions"].append(fname[:60])
        if stripped.startswith("class "):
            cname = stripped.split("(")[0].split(":")[0].replace("class ", "")
            features["classes"].append(cname[:60])
        if "require(" in stripped or stripped.startswith("const ") and "require" in stripped:
            features["dependencies"].append(stripped[:80])
        if any(s in stripped.lower() for s in ["password", "secret", "api_key", "token", "credential"]):
            if "=" in stripped and not stripped.startswith("#") and not stripped.startswith("//"):
                features["has_secrets"] = True
        if "test" in stripped.lower() and ("def " in stripped or "func " in stripped or "func(" in stripped):
            features["has_tests"] = True

    features["imports"] = features["imports"][:20]
    features["functions"] = features["functions"][:30]
    features["classes"] = features["classes"][:10]
    features["dependencies"] = features["dependencies"][:15]
    return features


def check_executable(file_class: str, fidelity_level: int) -> bool:
    """Determine if a glyph at this fidelity level crosses the execution threshold."""
    if fidelity_level < 7:
        return False
    if file_class in ("python_source", "javascript_source", "shell_script", "cpp_source", "c_source",
                      "swift_source", "rust_source", "go_source", "java_source", "ruby_source"):
        return fidelity_level >= 9
    return False


def compute_lambda_friction(features: dict, metadata: dict) -> dict:
    """Compute lambda friction score — transferability resistance."""
    components = {
        "local_path_dependency": 0.0,
        "secret_dependency": 0.0,
        "runtime_drift": 0.0,
        "documentation_gap": 0.0,
        "test_gap": 0.0,
        "missing_deps": 0.0,
    }

    if features.get("has_secrets"):
        components["secret_dependency"] = 0.30
    if not features.get("has_tests"):
        components["test_gap"] = 0.15
    if not features.get("imports") and features.get("line_count", 0) > 50:
        components["documentation_gap"] = 0.10
    if features.get("line_count", 0) > 1000:
        components["runtime_drift"] = 0.10
    if features.get("dependencies") and not features.get("imports"):
        components["missing_deps"] = 0.15

    total = sum(components.values())
    transferability = 1.0 / (1.0 + total) if total > 0 else 1.0

    return {
        "components": components,
        "lambda_total": round(total, 4),
        "transferability": round(transferability, 4),
        "interpretation": "low_friction" if total < 0.2 else "medium_friction" if total < 0.4 else "high_friction",
    }


@dataclass
class Glyph:
    """A BlurHash64 glyph — adjustable-fidelity file representation."""
    glyph_id: str = ""
    filename: str = ""
    fidelity_level: int = 0
    file_class: str = "unknown"
    identity: dict = field(default_factory=dict)
    resemblance: dict = field(default_factory=dict)
    recoverability: dict = field(default_factory=dict)
    executability: dict = field(default_factory=dict)
    payload: dict = field(default_factory=dict)
    lambda_friction: dict = field(default_factory=dict)
    created_at: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)

    @property
    def is_recoverable(self) -> bool:
        return self.fidelity_level >= 8

    @property
    def is_executable(self) -> bool:
        return self.executability.get("crosses_threshold", False)

    @property
    def has_resemblance(self) -> bool:
        return self.fidelity_level >= 4


class BlurHash64Encoder:
    """Encodes files into adjustable-fidelity glyphs."""

    def __init__(self):
        self.glyphs: dict[str, Glyph] = {}

    def encode(self, content: str | bytes, filename: str = "", fidelity: int = 6) -> Glyph:
        """Encode a file into a glyph at the specified fidelity level (0-9)."""
        if isinstance(content, bytes):
            data = content
            text = content.decode("utf-8", errors="replace")
        else:
            data = content.encode()
            text = content

        glyph_id = hashlib.sha256(data).hexdigest()[:12]
        file_class = detect_file_class(filename, text)
        merkle = merkle_commitment(data)
        blur = blur_hash64(data)
        features = extract_features(text, file_class)
        metadata = {
            "filename": filename,
            "size_bytes": len(data),
            "size_human": _human_size(len(data)),
            "extension": Path(filename).suffix.lower(),
            "mime_type": _mime_type(filename),
            "file_class": file_class,
        }
        lambda_info = compute_lambda_friction(features, metadata)

        glyph = Glyph(
            glyph_id=glyph_id,
            filename=filename,
            fidelity_level=fidelity,
            file_class=file_class,
            identity={"sha256": sha256(data), "merkle_root": merkle["root"], "blur_hash64": blur},
            resemblance={},
            recoverability={},
            executability={"crosses_threshold": check_executable(file_class, fidelity)},
            payload={},
            lambda_friction=lambda_info,
            created_at=time.time(),
        )

        if fidelity >= 1:
            glyph.payload["exists"] = True
        if fidelity >= 2:
            glyph.payload["file_class"] = file_class
            glyph.resemblance["class"] = file_class
        if fidelity >= 3:
            glyph.payload["metadata"] = metadata
            glyph.resemblance["size"] = metadata["size_human"]
        if fidelity >= 4:
            glyph.payload["features"] = features
            glyph.resemblance["features"] = {
                "imports": features["imports"][:5],
                "functions": features["functions"][:5],
                "classes": features["classes"][:3],
                "line_count": features["line_count"],
            }
        if fidelity >= 5:
            preview = text[:500] + "..." if len(text) > 500 else text
            glyph.payload["sketch"] = {
                "preview": preview,
                "summary": f"{file_class} with {features['line_count']} lines, {len(features['functions'])} functions",
                "word_count": features["word_count"],
            }
            glyph.resemblance["sketch"] = preview[:200]
        if fidelity >= 6:
            glyph.payload["receipt"] = {
                "hash": sha256(data),
                "merkle_root": merkle["root"],
                "merkle_leaves": merkle["leaf_count"],
                "provenance": {"encoded_at": time.time(), "encoder": "BlurHash64/1.0"},
                "proof_claims": ["artifact_existed", "hash_bound", "merkle_root_valid"],
                "lambda_score": lambda_info["lambda_total"],
                "transferability": lambda_info["transferability"],
            }
        if fidelity >= 7:
            chunk_size = 4096
            chunks = [data[i:i+chunk_size] for i in range(0, len(data), chunk_size)]
            glyph.payload["partial_body"] = {
                "chunk_count": len(chunks),
                "chunks": [base64.b64encode(c).decode() for c in chunks[:3]],
                "chunk_hashes": [sha256(c) for c in chunks],
                "redacted": len(chunks) > 3,
            }
            glyph.recoverability["partial"] = True
        if fidelity >= 8:
            key = hashlib.sha256((glyph_id + str(time.time())).encode()).digest()[:32]
            encrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
            glyph.payload["encrypted_body"] = {
                "ciphertext": base64.b64encode(encrypted).decode(),
                "key_hash": sha256(key),
                "algorithm": "XOR-256",
                "note": "Key not included. External authorization required.",
            }
            glyph.recoverability["full_body"] = True
            glyph.recoverability["key_gated"] = True
        if fidelity >= 9:
            glyph.payload["full_body"] = base64.b64encode(data).decode()
            glyph.recoverability["full_body"] = True
            glyph.recoverability["key_gated"] = False
            glyph.recoverability["format"] = "base64"

        self.glyphs[glyph_id] = glyph
        return glyph

    def decode(self, glyph: Glyph, key: bytes = None) -> Optional[bytes]:
        """Attempt to recover the original file from a glyph."""
        if glyph.fidelity_level >= 9 and "full_body" in glyph.payload:
            return base64.b64decode(glyph.payload["full_body"])
        if glyph.fidelity_level >= 8 and "encrypted_body" in glyph.payload and key:
            encrypted = base64.b64decode(glyph.payload["encrypted_body"]["ciphertext"])
            return bytes(b ^ key[i % len(key)] for i, b in enumerate(encrypted))
        if glyph.fidelity_level >= 7 and "partial_body" in glyph.payload:
            chunks = [base64.b64decode(c) for c in glyph.payload["partial_body"]["chunks"]]
            return b"".join(chunks)
        return None

    def ladder(self, content: str | bytes, filename: str = "") -> list[dict]:
        """Generate all 10 fidelity levels for a file."""
        results = []
        for level in range(10):
            g = self.encode(content, filename, fidelity=level)
            results.append({
                "level": level,
                "glyph_id": g.glyph_id,
                "recoverable": g.is_recoverable,
                "executable": g.is_executable,
                "has_resemblance": g.has_resemblance,
                "payload_keys": list(g.payload.keys()),
                "lambda": g.lambda_friction["lambda_total"],
                "transferability": g.lambda_friction["transferability"],
            })
        return results


def _human_size(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _mime_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return {
        ".py": "text/x-python", ".js": "text/javascript", ".ts": "text/typescript",
        ".swift": "text/swift", ".cpp": "text/x-c++", ".c": "text/x-c",
        ".json": "application/json", ".xml": "application/xml", ".csv": "text/csv",
        ".md": "text/markdown", ".txt": "text/plain", ".html": "text/html",
        ".css": "text/css", ".pdf": "application/pdf", ".png": "image/png",
        ".jpg": "image/jpeg", ".zip": "application/zip", ".db": "application/x-sqlite3",
    }.get(ext, "application/octet-stream")
