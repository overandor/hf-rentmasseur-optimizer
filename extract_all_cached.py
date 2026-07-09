#!/usr/bin/env python3
"""
Extract ChatGPT data from Edge's Local Storage and IndexedDB LevelDB files.
Searches for conversation history, auth tokens, and cached chat data.
"""

import os
import re
import json
import glob
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "chatgpt_exports"
LS_DIR = os.path.expanduser("~/Library/Application Support/Microsoft Edge/Default/Local Storage/leveldb")
IDB_DIR = os.path.expanduser("~/Library/Application Support/Microsoft Edge/Default/IndexedDB/https_chatgpt.com_0.indexeddb.leveldb")


def extract_all_json(data, max_results=50):
    """Find all JSON objects/arrays in raw bytes."""
    results = []
    i = 0
    while i < len(data) and len(results) < max_results:
        if data[i:i+1] in (b'{', b'['):
            depth = 0
            in_string = False
            escape = False
            start = i
            for j in range(i, min(i + 2000000, len(data))):
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
                if c in (b'{', b'['):
                    depth += 1
                elif c in (b'}', b']'):
                    depth -= 1
                    if depth == 0:
                        chunk = data[start:j+1]
                        try:
                            text = chunk.decode('utf-8', errors='ignore')
                            obj = json.loads(text)
                            results.append((start, j+1, obj))
                        except:
                            pass
                        i = j + 1
                        break
            else:
                i += 1
        else:
            i += 1
    return results


def scan_leveldb(directory, label):
    """Scan a LevelDB directory for JSON data."""
    print(f"\n--- Scanning {label}: {directory} ---")
    
    if not os.path.exists(directory):
        print(f"  Directory does not exist!")
        return {}
    
    files = sorted(glob.glob(os.path.join(directory, "*.ldb")) + 
                   glob.glob(os.path.join(directory, "*.log")) +
                   glob.glob(os.path.join(directory, "*.sst")))
    
    print(f"  Found {len(files)} files")
    
    all_data = {}
    
    for fpath in files:
        fname = os.path.basename(fpath)
        try:
            data = open(fpath, "rb").read()
            fsize = len(data)
        except Exception as e:
            print(f"  Error reading {fname}: {e}")
            continue
        
        # Find all JSON objects
        jsons = extract_all_json(data, max_results=100)
        
        for jstart, jend, obj in jsons:
            # Categorize the JSON object
            obj_str = json.dumps(obj)[:200]
            
            # Look for conversation/chat data
            if isinstance(obj, dict):
                # Check for conversation list
                value = obj.get("value", obj)
                if isinstance(value, dict):
                    pages = value.get("pages", [])
                    if isinstance(pages, list):
                        total = sum(len(p.get("items", p.get("conversations", p.get("edges", [])))) 
                                   for p in pages if isinstance(p, dict))
                        if total > 0:
                            key = f"{fname}_page_{jstart}"
                            all_data[key] = obj
                            print(f"  {fname}: conversation list ({total} items)")
                
                # Check for individual conversation
                if "id" in obj and "title" in obj:
                    key = f"{fname}_chat_{jstart}"
                    if key not in all_data:
                        all_data[key] = obj
                        print(f"  {fname}: chat object - {obj.get('title', '?')[:50]}")
                
                # Check for messages
                if "messages" in obj or "message" in obj:
                    key = f"{fname}_msg_{jstart}"
                    all_data[key] = obj
                    msg_count = len(obj.get("messages", obj.get("message", [])))
                    print(f"  {fname}: messages ({msg_count})")
                
                # Check for auth tokens
                if any(k in obj_str.lower() for k in ["token", "auth", "session", "credential"]):
                    key = f"{fname}_auth_{jstart}"
                    all_data[key] = obj
                    print(f"  {fname}: auth-related data")
            
            elif isinstance(obj, list):
                # Check if it's a list of conversations
                if len(obj) > 0 and isinstance(obj[0], dict):
                    if "id" in obj[0] or "title" in obj[0]:
                        key = f"{fname}_list_{jstart}"
                        all_data[key] = obj
                        print(f"  {fname}: chat list ({len(obj)} items)")
    
    return all_data


def extract_chats_from_data(all_data):
    """Extract chat metadata from all collected data."""
    all_chats = []
    all_messages = {}
    
    for key, data in all_data.items():
        if isinstance(data, dict):
            value = data.get("value", data)
            
            # Conversation history pages
            if isinstance(value, dict):
                pages = value.get("pages", [])
                if isinstance(pages, list):
                    for page in pages:
                        if isinstance(page, dict):
                            items = page.get("items", page.get("conversations", page.get("edges", [])))
                            if isinstance(items, list):
                                for item in items:
                                    if isinstance(item, dict):
                                        node = item.get("node", item)
                                        chat_id = node.get("id", "")
                                        title = node.get("title", "untitled")
                                        if chat_id and chat_id not in [c["id"] for c in all_chats]:
                                            all_chats.append({
                                                "id": chat_id,
                                                "title": title,
                                                "create_time": node.get("create_time", node.get("createdAt", "")),
                                                "update_time": node.get("update_time", node.get("updatedAt", "")),
                                            })
            
            # Individual chat with messages
            if "messages" in data:
                chat_id = data.get("id", data.get("conversation_id", key))
                all_messages[chat_id] = data["messages"]
        
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    node = item.get("node", item)
                    chat_id = node.get("id", "")
                    title = node.get("title", "untitled")
                    if chat_id and chat_id not in [c["id"] for c in all_chats]:
                        all_chats.append({
                            "id": chat_id,
                            "title": title,
                            "create_time": node.get("create_time", node.get("createdAt", "")),
                            "update_time": node.get("update_time", node.get("updatedAt", "")),
                        })
    
    return all_chats, all_messages


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("ChatGPT Data Extractor - Local Storage + IndexedDB")
    print("=" * 60)
    
    # Scan Local Storage
    ls_data = scan_leveldb(LS_DIR, "Local Storage")
    
    # Scan IndexedDB
    idb_data = scan_leveldb(IDB_DIR, "IndexedDB")
    
    # Combine all data
    all_data = {**ls_data, **idb_data}
    print(f"\nTotal data entries: {len(all_data)}")
    
    # Extract chats
    all_chats, all_messages = extract_chats_from_data(all_data)
    
    print(f"\nExtracted {len(all_chats)} unique chats:")
    for c in all_chats:
        print(f"  {c['id'][:16]}... {c['title'][:60]}")
    
    print(f"\nExtracted messages for {len(all_messages)} conversations")
    
    # Save chat list
    if all_chats:
        (OUTPUT_DIR / "chats_from_cache.json").write_text(
            json.dumps(all_chats, indent=2, ensure_ascii=False)
        )
    
    # Save all data
    serializable = {}
    for k, v in all_data.items():
        try:
            json.dumps(v)
            serializable[k] = v
        except:
            serializable[k] = str(v)[:1000]
    
    (OUTPUT_DIR / "all_cached_data.json").write_text(
        json.dumps(serializable, indent=2, ensure_ascii=False)
    )
    
    # Save messages
    if all_messages:
        (OUTPUT_DIR / "cached_messages.json").write_text(
            json.dumps(all_messages, indent=2, ensure_ascii=False)
        )
    
    # Save individual chat markdown files
    for i, chat in enumerate(all_chats):
        safe_title = re.sub(r'[^\w\s\-]', '', chat["title"]).strip()
        safe_title = re.sub(r'[\s]+', '_', safe_title) or "untitled"
        md_path = OUTPUT_DIR / f"cache_{i+1:04d}_{safe_title[:100]}.md"
        
        md_lines = [
            f"# {chat['title']}\n",
            f"Chat ID: {chat['id']}\n",
        ]
        if chat.get("create_time"):
            md_lines.append(f"Created: {chat['create_time']}\n")
        if chat.get("update_time"):
            md_lines.append(f"Updated: {chat['update_time']}\n")
        
        # Add messages if we have them
        if chat["id"] in all_messages:
            msgs = all_messages[chat["id"]]
            md_lines.append(f"Messages: {len(msgs)}\n")
            md_lines.append("---\n")
            for msg in msgs:
                if isinstance(msg, dict):
                    role = msg.get("role", msg.get("author", {}).get("role", "unknown"))
                    content = msg.get("content", msg.get("text", str(msg)))
                    if isinstance(content, dict):
                        content = content.get("parts", [str(content)])[0]
                    md_lines.append(f"\n## [{str(role).upper()}]\n")
                    md_lines.append(str(content))
                    md_lines.append("")
        else:
            md_lines.append("---\n")
            md_lines.append("\n(Message content not in cache - need API access for full conversation)\n")
        
        md_path.write_text("\n".join(md_lines))
    
    print(f"\n{'=' * 60}")
    print(f"Extraction complete!")
    print(f"  Chats found: {len(all_chats)}")
    print(f"  Conversations with messages: {len(all_messages)}")
    print(f"  Output: {OUTPUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
