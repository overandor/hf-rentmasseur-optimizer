#!/usr/bin/env python3
"""
ChatGPT Mac App Chat Extractor
Reads conversation data from the ChatGPT Mac app's WebKit IndexedDB.

The ChatGPT Mac app is a WebKit/Electron hybrid that stores conversation
data in IndexedDB. We read the SQLite backing store directly.
"""

import json
import os
import sqlite3
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional

# The ChatGPT app's WebKit data directory
WEBKIT_BASE = Path.home() / "Library" / "WebKit" / "com.openai.chat"
IDB_GLOB = "**/IndexedDB.sqlite3"
OUTPUT_DIR = Path(__file__).parent / "chatgpt_exports"


def find_idb_files() -> List[Path]:
    """Find all IndexedDB SQLite files in the ChatGPT WebKit directory."""
    if not WEBKIT_BASE.exists():
        return []
    return list(WEBKIT_BASE.glob(IDB_GLOB))


def read_idb_without_collation(db_path: Path) -> Dict[str, Any]:
    """Read IndexedDB SQLite file, bypassing the IDBKEY collation.
    
    We do this by opening the database with a custom collation registered
    as a no-op, so SQLite can parse the schema and read the data.
    """
    conn = sqlite3.connect(str(db_path))
    
    # Register a no-op collation for IDBKEY
    conn.create_collation("IDBKEY", lambda a, b: -1 if a < b else (1 if a > b else 0))
    
    result = {"db_path": str(db_path), "stores": {}, "records": []}
    
    try:
        # Get object stores
        stores = conn.execute("SELECT id, name FROM ObjectStoreInfo").fetchall()
        result["stores"] = {str(sid): name for sid, name in stores}
        
        # Get records from each store
        for store_id, store_name in stores:
            try:
                rows = conn.execute(
                    "SELECT key, value FROM Records WHERE objectStoreID = ?",
                    (store_id,)
                ).fetchall()
                
                for key, value in rows:
                    record = {
                        "store": store_name,
                        "key": decode_key(key),
                        "value": decode_value(value),
                    }
                    result["records"].append(record)
            except Exception as e:
                result["records"].append({
                    "store": store_name,
                    "error": str(e),
                })
    except Exception as e:
        result["error"] = str(e)
    finally:
        conn.close()
    
    return result


def decode_key(key: Any) -> str:
    """Decode an IndexedDB key (could be text or binary)."""
    if isinstance(key, str):
        return key
    if isinstance(key, bytes):
        # Try to decode as UTF-8 first
        try:
            return key.decode("utf-8")
        except:
            # WebKit encodes IDB keys in a binary format
            return decode_idb_key(key)
    return str(key)


def decode_idb_key(data: bytes) -> str:
    """Decode WebKit's binary IndexedDB key format.
    
    Format: type byte followed by value
    - 0x00: null
    - 0x01: number (8 bytes, double)
    - 0x02: date (8 bytes, double)
    - 0x03: string (4 bytes length + UTF-16BE)
    - 0x04: array
    - 0x05: binary (4 bytes length + data)
    """
    if not data:
        return ""
    
    try:
        pos = 0
        return _decode_key_part(data, pos)[0]
    except:
        return data.hex()[:100]


def _decode_key_part(data: bytes, pos: int) -> tuple:
    """Decode one key part, return (value, next_pos)."""
    if pos >= len(data):
        return ("", pos)
    
    key_type = data[pos]
    pos += 1
    
    if key_type == 0x00:  # null
        return (None, pos)
    elif key_type == 0x01:  # number
        val = struct.unpack(">d", data[pos:pos+8])[0]
        return (val, pos + 8)
    elif key_type == 0x02:  # date
        val = struct.unpack(">d", data[pos:pos+8])[0]
        return (val, pos + 8)
    elif key_type == 0x03:  # string
        length = struct.unpack(">I", data[pos:pos+4])[0]
        pos += 4
        val = data[pos:pos+length*2].decode("utf-16-be")
        return (val, pos + length * 2)
    elif key_type == 0x04:  # array
        items = []
        # Read until we hit the end or a terminator
        while pos < len(data):
            val, pos = _decode_key_part(data, pos)
            if val is None and pos >= len(data):
                break
            items.append(val)
        return (items, pos)
    elif key_type == 0x05:  # binary
        length = struct.unpack(">I", data[pos:pos+4])[0]
        pos += 4
        val = data[pos:pos+length]
        return (f"<binary:{length}b>", pos + length)
    
    return (f"<unknown:0x{key_type:02x}>", pos)


def decode_value(value: Any) -> Any:
    """Decode an IndexedDB value (WebKit serializes as JSON-like binary)."""
    if isinstance(value, str):
        # Try to parse as JSON
        try:
            return json.loads(value)
        except:
            return value
    if isinstance(value, bytes):
        # WebKit stores values as serialized binary blobs
        # Try UTF-8 first
        try:
            text = value.decode("utf-8")
            try:
                return json.loads(text)
            except:
                return text
        except:
            # Try to find JSON within the binary
            return decode_webkit_value(value)
    return value


def decode_webkit_value(data: bytes) -> Any:
    """Decode WebKit's IndexedDB value serialization.
    
    WebKit uses a custom serialization format. We try to extract
    readable strings and JSON from it.
    """
    # Strategy 1: Look for JSON-like patterns in the binary
    try:
        text = data.decode("utf-8", errors="ignore")
        # Find JSON objects
        for i in range(len(text)):
            if text[i] == '{':
                # Try to parse from here
                depth = 0
                for j in range(i, len(text)):
                    if text[j] == '{':
                        depth += 1
                    elif text[j] == '}':
                        depth -= 1
                        if depth == 0:
                            try:
                                obj = json.loads(text[i:j+1])
                                return obj
                            except:
                                pass
                            break
    except:
        pass
    
    # Strategy 2: Extract all readable strings
    strings = []
    current = []
    for byte in data:
        if 32 <= byte < 127:
            current.append(chr(byte))
        else:
            if len(current) > 10:
                strings.append("".join(current))
            current = []
    if len(current) > 10:
        strings.append("".join(current))
    
    return {"_type": "binary", "_size": len(data), "_strings": strings[:50]}


def extract_chats() -> Dict[str, Any]:
    """Main extraction function."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    idb_files = find_idb_files()
    if not idb_files:
        return {"error": "No IndexedDB files found for ChatGPT app"}
    
    all_results = {"files": [], "chats": [], "total_records": 0}
    
    for db_path in idb_files:
        result = read_idb_without_collation(db_path)
        all_results["files"].append({
            "path": str(db_path),
            "stores": result["stores"],
            "record_count": len(result["records"]),
        })
        all_results["total_records"] += len(result["records"])
        
        # Extract chat-like records
        for record in result["records"]:
            if record.get("store") == "conversations":
                value = record.get("value")
                if isinstance(value, dict):
                    chat = {
                        "key": record.get("key"),
                        "title": value.get("title", ""),
                        "id": value.get("id", record.get("key")),
                        "created": value.get("createdAt", value.get("created", "")),
                        "updated": value.get("updatedAt", value.get("updated", "")),
                        "message_count": len(value.get("messages", [])) if "messages" in value else None,
                    }
                    all_results["chats"].append(chat)
                elif isinstance(value, str) and len(value) > 20:
                    all_results["chats"].append({
                        "key": record.get("key"),
                        "raw_text": value[:200],
                    })
    
    return all_results


def main():
    print("=" * 60)
    print("ChatGPT Mac App — Chat Extractor")
    print("=" * 60)
    
    idb_files = find_idb_files()
    print(f"\nFound {len(idb_files)} IndexedDB file(s):")
    for f in idb_files:
        print(f"  {f}")
    
    if not idb_files:
        print("\nNo ChatGPT IndexedDB found. Is the app installed and has been used?")
        return
    
    print(f"\nExtracting chats...")
    results = extract_chats()
    
    print(f"\nFiles scanned: {len(results.get('files', []))}")
    for f in results.get("files", []):
        print(f"  {f['path']}")
        print(f"    Stores: {f['stores']}")
        print(f"    Records: {f['record_count']}")
    
    print(f"\nTotal records: {results.get('total_records', 0)}")
    print(f"Chats found: {len(results.get('chats', []))}")
    
    # Save results
    output = OUTPUT_DIR / "mac_app_chats.json"
    output.write_text(json.dumps(results, indent=2, default=str, ensure_ascii=False))
    print(f"\nSaved to: {output}")
    
    # Print chat titles
    chats = results.get("chats", [])
    if chats:
        print(f"\n{'=' * 60}")
        print(f"Chat List ({len(chats)} chats)")
        print(f"{'=' * 60}")
        for i, chat in enumerate(chats[:50]):
            title = chat.get("title", chat.get("raw_text", "untitled")[:60])
            msg_count = chat.get("message_count", "?")
            print(f"  [{i+1}] {title} ({msg_count} msgs)")
    else:
        print("\nNo structured chats found — data may be in binary format.")
        print("Raw records saved to JSON for inspection.")
    
    # Also check LocalStorage for conversation metadata
    ls_path = WEBKIT_BASE / "WebsiteData"
    ls_files = list(ls_path.glob("**/localstorage.sqlite3"))
    if ls_files:
        print(f"\n{'=' * 60}")
        print(f"LocalStorage ({len(ls_files)} file(s))")
        print(f"{'=' * 60}")
        for ls in ls_files:
            try:
                conn = sqlite3.connect(str(ls))
                rows = conn.execute("SELECT key, value FROM ItemTable").fetchall()
                for key, value in rows:
                    if "chat" in key.lower() or "conv" in key.lower() or "history" in key.lower():
                        val_str = value.decode("utf-8", errors="ignore")[:200] if isinstance(value, bytes) else str(value)[:200]
                        print(f"  {key}: {val_str}")
                conn.close()
            except Exception as e:
                print(f"  Error reading {ls}: {e}")


if __name__ == "__main__":
    main()
