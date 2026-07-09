#!/usr/bin/env python3
"""
Extract ChatGPT conversation history from Edge's Local Storage LevelDB.
ChatGPT caches conversation lists and data in Local Storage.
This script reads the LevelDB files directly without needing plyvel.
"""

import os
import re
import json
import glob
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "chatgpt_exports"
LS_DIR = os.path.expanduser("~/Library/Application Support/Microsoft Edge/Default/Local Storage/leveldb")


def extract_json_from_bytes(data):
    """Find all valid JSON objects/arrays in raw bytes."""
    results = []
    # Try to find JSON by looking for { or [ followed by valid JSON
    for i in range(len(data)):
        if data[i:i+1] in (b'{', b'['):
            # Try to parse JSON starting here
            depth = 0
            in_string = False
            escape = False
            start = i
            for j in range(i, min(i + 500000, len(data))):
                c = data[j:j+1]
                if escape:
                    escape = False
                    continue
                if c == b'\\':
                    escape = True
                    continue
                if c == b'"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if c == b'{' or c == b'[':
                    depth += 1
                elif c == b'}' or c == b']':
                    depth -= 1
                    if depth == 0:
                        chunk = data[start:j+1]
                        try:
                            text = chunk.decode('utf-8', errors='ignore')
                            obj = json.loads(text)
                            results.append((start, obj))
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            pass
                        break
    return results


def extract_keys_from_bytes(data):
    """Find LevelDB keys related to chatgpt.com."""
    keys = []
    # Keys in LevelDB are stored as length-prefixed strings
    # Look for chatgpt.com URL patterns
    pattern = rb'https://chatgpt\.com[^\x00-\x1f]*'
    for match in re.finditer(pattern, data):
        key = match.group().decode('utf-8', errors='ignore')
        keys.append((match.start(), key))
    return keys


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("ChatGPT Local Storage Extractor")
    print("=" * 60)

    all_data = {}
    chat_list = []
    conversations = {}

    files = sorted(glob.glob(os.path.join(LS_DIR, "*.ldb")) + 
                   glob.glob(os.path.join(LS_DIR, "*.log")))
    
    print(f"\nScanning {len(files)} LevelDB files...")

    for fpath in files:
        fname = os.path.basename(fpath)
        try:
            data = open(fpath, "rb").read()
        except Exception as e:
            print(f"  Error reading {fname}: {e}")
            continue

        # Find chatgpt.com keys
        keys = extract_keys_from_bytes(data)
        
        for pos, key in keys:
            # Get data after the key (value follows key in LevelDB)
            key_end = pos + len(key.encode('utf-8'))
            # Look for JSON data near this key
            search_region = data[key_end:key_end + 500000]
            jsons = extract_json_from_bytes(search_region[:10000])  # Limit search
            
            for jpos, obj in jsons:
                if key not in all_data:
                    all_data[key] = obj
                    print(f"  {fname}: {key[:80]}")
                    
                    # Check if this is conversation history
                    if "conversation-history" in key:
                        print(f"    -> Found conversation history!")
                        chat_list.append({"key": key, "data": obj})
                    elif "snorlax" in key:
                        print(f"    -> Found snorlax history!")
                        chat_list.append({"key": key, "data": obj})
                    elif "pinned" in key:
                        print(f"    -> Found pinned items!")
                        all_data["pinned"] = obj

    print(f"\nFound {len(all_data)} unique keys.")

    # Extract chat list from conversation history
    all_chats = []
    
    for entry in chat_list:
        data = entry["data"]
        # Navigate the cached data structure
        # ChatGPT caches: {"value": {"pages": [...]}}
        if isinstance(data, dict):
            value = data.get("value", data)
            if isinstance(value, dict):
                pages = value.get("pages", [])
                if isinstance(pages, list):
                    for page in pages:
                        if isinstance(page, dict):
                            items = page.get("items", page.get("conversations", []))
                            if isinstance(items, list):
                                for item in items:
                                    if isinstance(item, dict):
                                        chat = {
                                            "id": item.get("id", ""),
                                            "title": item.get("title", "untitled"),
                                            "create_time": item.get("create_time"),
                                            "update_time": item.get("update_time"),
                                        }
                                        if chat["id"] and chat["id"] not in [c["id"] for c in all_chats]:
                                            all_chats.append(chat)

    # Also try to extract from raw JSON search
    if not all_chats:
        print("\nTrying direct JSON extraction from all files...")
        for fpath in files:
            fname = os.path.basename(fpath)
            try:
                data = open(fpath, "rb").read()
            except:
                continue
            
            # Search for conversation objects with title and id
            pattern = rb'"id"\s*:\s*"[a-f0-9-]+"\s*,\s*"title"\s*:\s*"[^"]*"'
            for match in re.finditer(pattern, data):
                try:
                    text = match.group().decode('utf-8', errors='ignore')
                    # Parse as partial JSON
                    text = "{" + text + "}"
                    obj = json.loads(text)
                    chat = {
                        "id": obj.get("id", ""),
                        "title": obj.get("title", "untitled"),
                    }
                    if chat["id"] and chat["id"] not in [c["id"] for c in all_chats]:
                        all_chats.append(chat)
                        print(f"  Found chat: {chat['title'][:50]} ({chat['id'][:8]}...)")
                except:
                    pass

    print(f"\nTotal unique chats found: {len(all_chats)}")

    if all_chats:
        # Save chat list
        chat_list_path = OUTPUT_DIR / "chat_list_from_cache.json"
        chat_list_path.write_text(json.dumps(all_chats, indent=2, ensure_ascii=False))
        print(f"Chat list saved to {chat_list_path}")

        # Save all extracted data
        all_data_path = OUTPUT_DIR / "local_storage_data.json"
        # Convert all_data to serializable
        serializable = {}
        for k, v in all_data.items():
            try:
                json.dumps(v)
                serializable[k] = v
            except:
                serializable[k] = str(v)
        all_data_path.write_text(json.dumps(serializable, indent=2, ensure_ascii=False))
        print(f"All Local Storage data saved to {all_data_path}")

        # Save individual chat markdown files
        for i, chat in enumerate(all_chats):
            safe_title = re.sub(r'[^\w\s\-]', '', chat["title"]).strip()
            safe_title = re.sub(r'[\s]+', '_', safe_title) or "untitled"
            md_path = OUTPUT_DIR / f"{i+1:04d}_{safe_title[:100]}.md"
            md_content = f"# {chat['title']}\n\nChat ID: {chat['id']}\n"
            if chat.get("create_time"):
                md_content += f"Created: {chat['create_time']}\n"
            if chat.get("update_time"):
                md_content += f"Updated: {chat['update_time']}\n"
            md_path.write_text(md_content)

        print(f"\n{len(all_chats)} markdown files saved to {OUTPUT_DIR}/")
    else:
        print("\nNo chats found in Local Storage cache.")
        print("The cache may have been cleared or the format has changed.")
        
        # Save whatever we found
        if all_data:
            all_data_path = OUTPUT_DIR / "local_storage_data.json"
            serializable = {}
            for k, v in all_data.items():
                try:
                    json.dumps(v)
                    serializable[k] = v
                except:
                    serializable[k] = str(v)
            all_data_path.write_text(json.dumps(serializable, indent=2, ensure_ascii=False))
            print(f"Partial data saved to {all_data_path}")

    print(f"\n{'=' * 60}")
    print("Extraction complete!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
