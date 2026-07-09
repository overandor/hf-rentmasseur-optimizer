#!/usr/bin/env python3
import argparse, base64, hashlib, json, mimetypes, os, re, time, zlib
from pathlib import Path
from collections import Counter, defaultdict

EXCLUDE_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".next",
    ".cache", "dist", "build", "target", ".pytest_cache", ".mypy_cache"
}

SECRET_NAME_PATTERNS = [
    r"\.env(\..*)?$", r"id_rsa$", r"id_ed25519$", r"\.pem$", r"\.key$",
    r"credentials.*\.json$", r"token", r"secret", r"private", r"wallet", r"keystore"
]

SECRET_VALUE_PATTERNS = [
    r"sk-[A-Za-z0-9_\-]{20,}",
    r"hf_[A-Za-z0-9]{20,}",
    r"ghp_[A-Za-z0-9]{20,}",
    r"github_pat_[A-Za-z0-9_]{20,}",
    r"AKIA[0-9A-Z]{16}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[^'\"\s]{8,}",
]

TEXT_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".md", ".txt", ".yaml",
    ".yml", ".toml", ".html", ".css", ".sh", ".rs", ".go", ".swift",
    ".sql", ".recept", ".csv"
}

CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".swift", ".sql", ".recept"}

def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def is_secret_name(path):
    s = str(path).lower()
    return any(re.search(p, s) for p in SECRET_NAME_PATTERNS)

def redact(text):
    count = 0
    out = text
    for pat in SECRET_VALUE_PATTERNS:
        out, n = re.subn(pat, "[REDACTED_SECRET]", out)
        count += n
    return out, count

def looks_binary(data):
    return b"\x00" in data[:4096]

def read_text(path, max_bytes=60000):
    try:
        data = path.read_bytes()[:max_bytes]
        if looks_binary(data):
            return None, {"binary": True}
        return data.decode("utf-8", errors="replace"), {"binary": False}
    except Exception as e:
        return None, {"error": str(e)}

def symbols(text, ext):
    out = defaultdict(list)
    for line in text.splitlines()[:2500]:
        s = line.strip()
        if ext == ".py":
            m = re.match(r"(class|def)\s+([A-Za-z_][A-Za-z0-9_]*)", s)
            if m:
                out[m.group(1)].append(m.group(2))
        elif ext in {".js", ".ts", ".tsx", ".jsx"}:
            m = re.match(r"(export\s+)?(async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)", s)
            if m:
                out["function"].append(m.group(3))
            m = re.match(r"(export\s+)?class\s+([A-Za-z_$][A-Za-z0-9_$]*)", s)
            if m:
                out["class"].append(m.group(2))
        elif ext == ".recept":
            m = re.match(r"(capsule|endpoint|workflow|fn)\b(.*)", s)
            if m:
                out[m.group(1)].append(m.group(2).strip()[:140])
    return {k: v[:40] for k, v in out.items()}

def summary(path, text):
    if text is None:
        return "Binary/unreadable file; metadata only."
    low = text.lower()
    name = path.name.lower()
    if name.startswith("readme"):
        return "README / documentation entry point."
    if "fastapi" in low or "uvicorn" in low:
        return "Backend/API endpoint file."
    if "sqlite" in low or "duckdb" in low:
        return "Database/persistence file."
    if "receipt" in low or "sha256" in low:
        return "Receipt/provenance/audit file."
    if "ollama" in low or "llm" in low or "openai" in low:
        return "LLM/agent/model integration file."
    if "subprocess" in low or "terminal" in low or "shell" in low:
        return "Terminal execution/control file."
    if "dmg" in low or "hdiutil" in low:
        return "macOS DMG/build/package file."
    if path.suffix.lower() in CODE_EXTS:
        return "Source code file."
    return "Documentation/config/text file."

def scan(root, max_files=1500, include_snippets=True):
    root = Path(root).expanduser().resolve()
    files = []
    skipped = Counter()
    redactions = 0

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not d.startswith(".git")]
        for fname in filenames:
            if len(files) >= max_files:
                skipped["max_files"] += 1
                continue

            path = Path(dirpath) / fname
            rel = str(path.relative_to(root))

            if is_secret_name(path):
                skipped["secret_name"] += 1
                continue

            try:
                st = path.stat()
            except Exception:
                skipped["stat_error"] += 1
                continue

            ext = path.suffix.lower()
            rec = {
                "path": rel,
                "size": st.st_size,
                "ext": ext,
                "mime": mimetypes.guess_type(path)[0],
                "sha256": None,
                "summary": None,
                "symbols": {},
                "snippet": None,
            }

            try:
                rec["sha256"] = sha256_file(path)
            except Exception as e:
                rec["sha256_error"] = str(e)

            if st.st_size <= 750000 and ext in TEXT_EXTS:
                text, meta = read_text(path)
                if text:
                    text, n = redact(text)
                    redactions += n
                    rec["summary"] = summary(path, text)
                    rec["symbols"] = symbols(text, ext)
                    if include_snippets:
                        rec["snippet"] = text[:1200]
                else:
                    rec["summary"] = summary(path, None)
            else:
                rec["summary"] = "Large, binary, or unsupported file; metadata only."

            files.append(rec)

    ext_counts = Counter(f["ext"] or "[none]" for f in files)
    top_dirs = Counter((Path(f["path"]).parts[0] if len(Path(f["path"]).parts) else ".") for f in files)

    packet = {
        "schema": "qrc.spider.cognition_packet.v1",
        "created_at": now(),
        "root_label": root.name,
        "privacy": {
            "raw_files_uploaded": False,
            "base64_is_encryption": False,
            "secret_name_files_skipped": skipped["secret_name"],
            "secret_value_redactions": redactions,
            "include_snippets": include_snippets,
        },
        "summary": {
            "file_count": len(files),
            "extension_counts": dict(ext_counts.most_common(40)),
            "top_dirs": dict(top_dirs.most_common(25)),
            "skipped": dict(skipped),
        },
        "files": files,
    }

    packet["packet_sha256"] = hashlib.sha256(
        json.dumps(packet, sort_keys=True).encode()
    ).hexdigest()

    return packet

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--out", default="qrc_spider_out")
    ap.add_argument("--no-snippets", action="store_true")
    ap.add_argument("--max-files", type=int, default=1500)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    packet = scan(args.root, max_files=args.max_files, include_snippets=not args.no_snippets)
    raw = json.dumps(packet, indent=2, sort_keys=True).encode()
    compressed = zlib.compress(raw, 9)
    b64 = base64.b64encode(compressed).decode()

    (out / "qrc_packet.json").write_bytes(raw)
    (out / "qrc_packet.b64").write_text(b64)

    receipt = {
        "schema": "qrc.spider.receipt.v1",
        "created_at": now(),
        "packet_sha256": hashlib.sha256(raw).hexdigest(),
        "compressed_sha256": hashlib.sha256(compressed).hexdigest(),
        "b64_sha256": hashlib.sha256(b64.encode()).hexdigest(),
        "file_count": packet["summary"]["file_count"],
        "secret_name_files_skipped": packet["privacy"]["secret_name_files_skipped"],
        "secret_value_redactions": packet["privacy"]["secret_value_redactions"],
    }
    (out / "qrc_receipt.json").write_text(json.dumps(receipt, indent=2))

    print("QRC Spider complete.")
    print("Output:", out.resolve())
    print("Files indexed:", packet["summary"]["file_count"])
    print("Secret files skipped:", packet["privacy"]["secret_name_files_skipped"])
    print("Secret values redacted:", packet["privacy"]["secret_value_redactions"])
    print("Packet SHA-256:", packet["packet_sha256"][:16])
    print("B64 size:", len(b64), "chars")
    print("Paste this file back into ChatGPT:")
    print(out / "qrc_packet.b64")

if __name__ == "__main__":
    main()
