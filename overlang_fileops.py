"""
OverLang File Ops — Real file indexing, search, and retrieval functions.

All functions are standalone and take explicit params (no class state).
SQLite indexes stored under index_dir/{file_id}.idx.
"""

import time
import hashlib
import sqlite3
import re
from pathlib import Path
from typing import Any


def index_file(filepath: str, index_dir: Path) -> dict:
    """Real file indexing: SHA256, line count, word freq, chunks, SQLite index."""
    start = time.time()
    path = Path(filepath)
    content = path.read_bytes()
    size = len(content)
    merkle_root = hashlib.sha256(content).hexdigest()
    file_id = merkle_root[:12]

    text = content.decode("utf-8", errors="replace")
    lines = text.split("\n")
    line_count = len(lines)
    words = re.findall(r"\b\w+\b", text)
    word_freq: dict[str, int] = {}
    for w in words:
        word_freq[w] = word_freq.get(w, 0) + 1
    top_words = sorted(word_freq.items(), key=lambda x: -x[1])[:20]

    chunks = []
    current_chunk = []
    chunk_start = 0
    for i, line in enumerate(lines):
        current_chunk.append(line)
        is_boundary = (
            (line.strip() == "" and len(current_chunk) > 5)
            or line.strip().startswith("def ")
            or line.strip().startswith("class ")
            or line.strip().startswith("func ")
            or line.strip().startswith("▷")
            or line.strip().startswith("workflow:")
        )
        if is_boundary and len(current_chunk) >= 3:
            chunks.append({
                "idx": len(chunks), "line_start": chunk_start, "line_end": i,
                "boundary_type": "function" if line.strip().startswith(("def ", "class ", "func ")) else "paragraph",
                "preview": "\n".join(current_chunk[:3])[:200], "line_count": len(current_chunk),
            })
            current_chunk = []
            chunk_start = i + 1
    if current_chunk:
        chunks.append({
            "idx": len(chunks), "line_start": chunk_start, "line_end": line_count - 1,
            "boundary_type": "final", "preview": "\n".join(current_chunk[:3])[:200], "line_count": len(current_chunk),
        })

    symbols = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        for prefix in ["def ", "class ", "func ", "async def "]:
            if stripped.startswith(prefix):
                name = stripped[len(prefix):].split("(")[0].split(":")[0].strip()
                symbols.append({"line": i + 1, "name": name, "type": prefix.strip()})

    idx_path = index_dir / f"{file_id}.idx"
    conn = sqlite3.connect(str(idx_path))
    conn.execute("CREATE TABLE IF NOT EXISTS file_meta (key TEXT, value TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS chunks (idx INTEGER, line_start INTEGER, line_end INTEGER, boundary_type TEXT, preview TEXT, line_count INTEGER)")
    conn.execute("CREATE TABLE IF NOT EXISTS word_freq (word TEXT, count INTEGER)")
    conn.execute("CREATE TABLE IF NOT EXISTS symbols (line INTEGER, name TEXT, type TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS capabilities (id INTEGER, name TEXT)")

    meta = {"filename": path.name, "size_bytes": str(size), "total_lines": str(line_count), "total_words": str(len(words)), "merkle_root": merkle_root, "total_chunks": str(len(chunks)), "total_symbols": str(len(symbols))}
    for k, v in meta.items():
        conn.execute("INSERT INTO file_meta VALUES (?,?)", (k, v))
    for c in chunks:
        conn.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?)", (c["idx"], c["line_start"], c["line_end"], c["boundary_type"], c["preview"], c["line_count"]))
    for w, cnt in top_words:
        conn.execute("INSERT INTO word_freq VALUES (?,?)", (w, cnt))
    for s in symbols:
        conn.execute("INSERT INTO symbols VALUES (?,?,?)", (s["line"], s["name"], s["type"]))
    caps = [(i, name) for i, name in enumerate(["sql", "nosql", "search", "chunk", "summary", "meta", "mcp", "word_freq", "symbols", "chunks", "merkle", "sha256", "capabilities", "revocation"])]
    conn.executemany("INSERT INTO capabilities VALUES (?,?)", caps)
    conn.commit()
    conn.close()

    elapsed = round((time.time() - start) * 1000, 2)
    index_size = idx_path.stat().st_size

    return {
        "file_id": file_id, "filename": path.name, "size_bytes": size,
        "size_human": f"{size/1024:.1f}KB" if size < 1048576 else f"{size/1048576:.1f}MB",
        "total_lines": line_count, "total_words": len(words),
        "total_chunks": len(chunks), "total_symbols": len(symbols),
        "merkle_root": merkle_root, "index_path": str(idx_path),
        "index_size_bytes": index_size, "index_ratio": round(index_size / max(size, 1) * 100, 1),
        "index_time_ms": elapsed, "capabilities": 14,
    }


def compute_hash(filepath: str) -> str:
    content = Path(filepath).read_bytes()
    return hashlib.sha256(content).hexdigest()


def search_index(file_id: str, query: str, index_dir: Path) -> dict:
    idx_path = index_dir / f"{file_id}.idx"
    if not idx_path.exists():
        return {"error": f"Index not found for {file_id}"}
    conn = sqlite3.connect(str(idx_path))
    chunk_results = conn.execute("SELECT idx, line_start, line_end, preview FROM chunks WHERE preview LIKE ?", (f"%{query}%",)).fetchall()
    sym_results = conn.execute("SELECT line, name, type FROM symbols WHERE name LIKE ?", (f"%{query}%",)).fetchall()
    word_results = conn.execute("SELECT word, count FROM word_freq WHERE word LIKE ? ORDER BY count DESC LIMIT 10", (f"%{query}%",)).fetchall()
    conn.close()
    total = len(chunk_results) + len(sym_results) + len(word_results)
    return {
        "file_id": file_id, "query": query, "total_matches": total,
        "chunks": [{"idx": r[0], "lines": f"{r[1]}-{r[2]}", "preview": r[3][:80]} for r in chunk_results],
        "symbols": [{"line": r[0], "name": r[1], "type": r[2]} for r in sym_results],
        "words": [{"word": r[0], "count": r[1]} for r in word_results],
    }


def sql_query(file_id: str, sql: str, index_dir: Path) -> dict:
    if not sql.strip().upper().startswith("SELECT"):
        return {"error": "Only SELECT statements allowed"}
    for kw in ["INSERT", "UPDATE", "DELETE", "DROP", "ATTACH", "PRAGMA", "CREATE", "ALTER"]:
        if kw in sql.upper():
            return {"error": f"{kw} not allowed"}
    idx_path = index_dir / f"{file_id}.idx"
    if not idx_path.exists():
        return {"error": f"Index not found for {file_id}"}
    conn = sqlite3.connect(str(idx_path))
    try:
        cursor = conn.execute(sql)
        columns = [d[0] for d in cursor.description] if cursor.description else []
        rows = cursor.fetchmany(1000)
        conn.close()
        return {"file_id": file_id, "sql": sql, "columns": columns, "rows": rows, "row_count": len(rows)}
    except Exception as e:
        conn.close()
        return {"error": str(e)}


def get_chunk(file_id: str, chunk_idx: int, index_dir: Path) -> dict:
    idx_path = index_dir / f"{file_id}.idx"
    if not idx_path.exists():
        return {"error": f"Index not found for {file_id}"}
    conn = sqlite3.connect(str(idx_path))
    row = conn.execute("SELECT idx, line_start, line_end, boundary_type, preview, line_count FROM chunks WHERE idx = ?", (chunk_idx,)).fetchone()
    conn.close()
    if not row:
        return {"error": f"Chunk {chunk_idx} not found"}
    return {"idx": row[0], "line_start": row[1], "line_end": row[2], "boundary_type": row[3], "preview": row[4], "line_count": row[5]}


def get_meta(file_id: str, index_dir: Path) -> dict:
    idx_path = index_dir / f"{file_id}.idx"
    if not idx_path.exists():
        return {"error": f"Index not found for {file_id}"}
    conn = sqlite3.connect(str(idx_path))
    rows = conn.execute("SELECT key, value FROM file_meta").fetchall()
    conn.close()
    return {"file_id": file_id, "meta": {r[0]: r[1] for r in rows}}


def get_summary(file_id: str, index_dir: Path) -> dict:
    idx_path = index_dir / f"{file_id}.idx"
    if not idx_path.exists():
        return {"error": f"Index not found for {file_id}"}
    conn = sqlite3.connect(str(idx_path))
    chunks = conn.execute("SELECT idx, boundary_type, line_start, line_end FROM chunks LIMIT 20").fetchall()
    symbols = conn.execute("SELECT line, name, type FROM symbols LIMIT 20").fetchall()
    conn.close()
    return {
        "file_id": file_id, "total_chunks": len(chunks),
        "chunks": [{"idx": r[0], "type": r[1], "lines": f"{r[2]}-{r[3]}"} for r in chunks],
        "total_symbols": len(symbols),
        "symbols": [{"line": r[0], "name": r[1], "type": r[2]} for r in symbols],
    }
