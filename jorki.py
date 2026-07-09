"""
JORKI — Private file-access substrate.

CLI: index, query, search, chunk, revoke — all through .over workflows.
"""

import sys
from pathlib import Path
from overlang import OverRuntime, parse_over


def cmd_jorki(args: list[str] | None = None):
    """JORKI CLI: index, query, search, chunk, revoke - all through .over workflows."""
    if not args:
        print("JORKI - AI File Gateway (via .over workflows)")
        print()
        print("Usage:")
        print("  python3 forge.py jorki index <file>           Index a file")
        print("  python3 forge.py jorki search <file_id> <q>    Search indexed file")
        print("  python3 forge.py jorki chunk <file_id> <idx>   Get chunk by index")
        print("  python3 forge.py jorki sql <file_id> <sql>     SQL query on index")
        print("  python3 forge.py jorki meta <file_id>          Get file metadata")
        print("  python3 forge.py jorki summary <file_id>       Get file summary")
        print("  python3 forge.py jorki revoke <file_id>        Revoke access")
        print("  python3 forge.py jorki list                    List all indexed files")
        print("  python3 forge.py jorki verify <file_id>        Verify integrity")
        sys.exit(0)

    sub = args[0]
    rt = OverRuntime()

    if sub == "index":
        if len(args) < 2:
            print("Usage: jorki index <file>")
            sys.exit(1)
        filepath = args[1]
        if not os.path.exists(filepath):
            print(f"Error: {filepath} not found")
            sys.exit(1)
        result = rt._index_file(filepath)
        file_id = result["file_id"]
        rt.registry[file_id] = {
            "filename": result["filename"], "merkle_root": result["merkle_root"],
            "indexed_at": time.time(), "status": "active", "index_path": result["index_path"],
        }
        rt._save_registry()
        print(f"JORKI - File indexed")
        print(f"  File ID:    {file_id}")
        print(f"  Filename:   {result['filename']}")
        print(f"  Size:       {result['size_human']} ({result['size_bytes']} bytes)")
        print(f"  Lines:      {result['total_lines']}")
        print(f"  Words:      {result['total_words']}")
        print(f"  Chunks:     {result['total_chunks']}")
        print(f"  Symbols:    {result['total_symbols']}")
        print(f"  Merkle:     {result['merkle_root'][:24]}...")
        print(f"  Index:      {result['index_size_bytes']} bytes ({result['index_ratio']}% of original)")
        print(f"  Time:       {result['index_time_ms']}ms")
        print(f"  Query URL:  jorki://query/{file_id}")

    elif sub == "search":
        if len(args) < 3:
            print("Usage: jorki search <file_id> <query>")
            sys.exit(1)
        result = rt._search(args[1], args[2])
        print(f"JORKI - Search: '{args[2]}' in {args[1]}")
        print(f"  Total matches: {result.get('total_matches', 0)}")
        for c in result.get("chunks", [])[:5]:
            print(f"    chunk {c['idx']} (lines {c['lines']}): {c['preview'][:60]}...")
        for s in result.get("symbols", [])[:5]:
            print(f"    symbol line {s['line']}: {s['name']} ({s['type']})")
        for w in result.get("words", [])[:5]:
            print(f"    word: {w['word']} (count={w['count']})")

    elif sub == "chunk":
        if len(args) < 3:
            print("Usage: jorki chunk <file_id> <chunk_idx>")
            sys.exit(1)
        result = rt._get_chunk(args[1], int(args[2]))
        print(f"JORKI - Chunk {args[2]} from {args[1]}")
        if "error" in result:
            print(f"  Error: {result['error']}")
        else:
            print(f"  Type:   {result['boundary_type']}")
            print(f"  Lines:  {result['line_start']}-{result['line_end']} ({result['line_count']} lines)")
            print(f"  Preview:")
            print(f"    {result['preview'][:200]}")

    elif sub == "sql":
        if len(args) < 3:
            print("Usage: jorki sql <file_id> <sql>")
            sys.exit(1)
        result = rt._sql_query(args[1], " ".join(args[2:]))
        print(f"JORKI - SQL query on {args[1]}")
        if "error" in result:
            print(f"  Error: {result['error']}")
        else:
            print(f"  Columns: {result['columns']}")
            print(f"  Rows: {result['row_count']}")
            for row in result['rows'][:10]:
                print(f"    {row}")

    elif sub == "meta":
        if len(args) < 2:
            print("Usage: jorki meta <file_id>")
            sys.exit(1)
        result = rt._get_meta(args[1])
        print(f"JORKI - Metadata for {args[1]}")
        for k, v in result.get("meta", {}).items():
            print(f"  {k}: {v}")

    elif sub == "summary":
        if len(args) < 2:
            print("Usage: jorki summary <file_id>")
            sys.exit(1)
        result = rt._get_summary(args[1])
        print(f"JORKI - Summary for {args[1]}")
        print(f"  Chunks: {result.get('total_chunks', 0)}")
        for c in result.get("chunks", [])[:5]:
            print(f"    chunk {c['idx']}: {c['type']} lines {c['lines']}")
        print(f"  Symbols: {result.get('total_symbols', 0)}")
        for s in result.get("symbols", [])[:5]:
            print(f"    line {s['line']}: {s['name']} ({s['type']})")

    elif sub == "revoke":
        if len(args) < 2:
            print("Usage: jorki revoke <file_id>")
            sys.exit(1)
        file_id = args[1]
        if file_id in rt.registry:
            rt.registry[file_id]["status"] = "revoked"
            rt.registry[file_id]["revoked_at"] = time.time()
            rt._save_registry()
            print(f"JORKI - Access revoked for {file_id}")
            print(f"  Status: revoked")
        else:
            print(f"Error: {file_id} not in registry")

    elif sub == "list":
        print(f"JORKI - Indexed files ({len(rt.registry)} total)")
        for fid, info in rt.registry.items():
            status = info.get("status", "unknown")
            print(f"  {fid}  {info.get('filename', '?'):30s}  {status:10s}  {info.get('indexed_at', 0):.0f}")

    elif sub == "verify":
        if len(args) < 2:
            print("Usage: jorki verify <file_id>")
            sys.exit(1)
        file_id = args[1]
        entry = rt.registry.get(file_id, {})
        if not entry:
            print(f"Error: {file_id} not in registry")
            sys.exit(1)
        idx_path = Path(entry.get("index_path", ""))
        if idx_path.exists():
            conn = sqlite3.connect(str(idx_path))
            row = conn.execute("SELECT value FROM file_meta WHERE key='merkle_root'").fetchone()
            conn.close()
            stored = row[0] if row else ""
            if stored == entry.get("merkle_root", ""):
                print(f"JORKI - Verified {file_id}")
                print(f"  Merkle root: {stored[:24]}...")
                print(f"  Status: {entry.get('status', 'unknown')}")
                print(f"  Integrity: VALID")
            else:
                print(f"JORKI - INVALID {file_id}")
                print(f"  Stored:     {stored[:24]}...")
                print(f"  Registry:   {entry.get('merkle_root', '')[:24]}...")
        else:
            print(f"Error: index file missing for {file_id}")

    else:
        print(f"Unknown jorki subcommand: {sub}")
        sys.exit(1)

