#!/usr/bin/env python3
"""
Final comprehensive extractor: scan all LevelDB files for ALL chat data
from ChatGPT AND Ollama Web UI, plus any other chat services.
Extracts full conversations with messages.
"""

import os
import re
import json
import glob
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "chatgpt_exports"
LS_DIR = os.path.expanduser("~/Library/Application Support/Microsoft Edge/Default/Local Storage/leveldb")
IDB_DIR = os.path.expanduser("~/Library/Application Support/Microsoft Edge/Default/IndexedDB")


def extract_json_from_position(data, start):
    """Try to extract a JSON object starting at position `start` in data."""
    if start >= len(data):
        return None
    if data[start:start+1] not in (b'{', b'['):
        return None
    depth = 0
    in_string = False
    escape = False
    for j in range(start, min(start + 5000000, len(data))):
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
                    return json.loads(text)
                except:
                    return None
    return None


def scan_for_chats(data, fname, source_label):
    """Scan raw bytes for chat conversation patterns."""
    chats = []
    
    # Pattern 1: "id":"<uuid>","title":"<text>","messages":[
    # This matches the Ollama Web UI format
    pattern1 = rb'"id"\s*:\s*"([a-f0-9\-]{36})"\s*,\s*"title"\s*:\s*"([^"]{0,200})"\s*,\s*"messages"\s*:\s*\['
    for match in re.finditer(pattern1, data):
        chat_id = match.group(1).decode()
        title = match.group(2).decode('utf-8', errors='ignore')
        # Find the start of the JSON object (search backwards for '{')
        for back in range(match.start(), max(0, match.start() - 500), -1):
            if data[back:back+1] == b'{':
                obj = extract_json_from_position(data, back)
                if obj and isinstance(obj, dict) and 'messages' in obj:
                    chats.append({
                        'source': source_label,
                        'id': obj.get('id', chat_id),
                        'title': obj.get('title', title),
                        'messages': obj.get('messages', []),
                        'url': obj.get('url', ''),
                        'file': fname,
                    })
                    break
    
    # Pattern 2: "id":"<uuid>","title":"<text>","preview"
    # This matches conversation list entries (metadata only)
    pattern2 = rb'"id"\s*:\s*"([a-f0-9\-]{36})"\s*,\s*"title"\s*:\s*"([^"]{0,200})"\s*,\s*"preview"'
    for match in re.finditer(pattern2, data):
        chat_id = match.group(1).decode()
        title = match.group(2).decode('utf-8', errors='ignore')
        # Check if we already have this chat with messages
        if chat_id not in [c['id'] for c in chats]:
            # Try to find full conversation nearby
            for back in range(match.start(), max(0, match.start() - 500), -1):
                if data[back:back+1] == b'{':
                    obj = extract_json_from_position(data, back)
                    if obj and isinstance(obj, dict):
                        if 'messages' in obj:
                            chats.append({
                                'source': source_label,
                                'id': obj.get('id', chat_id),
                                'title': obj.get('title', title),
                                'messages': obj.get('messages', []),
                                'url': obj.get('url', ''),
                                'file': fname,
                            })
                            break
                        elif 'url' in obj:
                            # Metadata only (shared link)
                            chats.append({
                                'source': source_label,
                                'id': chat_id,
                                'title': title,
                                'messages': [],
                                'url': obj.get('url', ''),
                                'file': fname,
                                'metadata_only': True,
                            })
                            break
    
    # Pattern 3: ChatGPT conversation history pages
    # {"value":{"pages":[{"items":[...]}]}}
    pattern3 = rb'"pages"\s*:\s*\['
    for match in re.finditer(pattern3, data):
        for back in range(match.start(), max(0, match.start() - 2000), -1):
            if data[back:back+1] == b'{':
                obj = extract_json_from_position(data, back)
                if obj and isinstance(obj, dict):
                    value = obj.get('value', obj)
                    if isinstance(value, dict):
                        pages = value.get('pages', [])
                        if isinstance(pages, list):
                            for page in pages:
                                if isinstance(page, dict):
                                    items = page.get('items', page.get('conversations', page.get('edges', [])))
                                    if isinstance(items, list):
                                        for item in items:
                                            if isinstance(item, dict):
                                                node = item.get('node', item)
                                                cid = node.get('id', '')
                                                title = node.get('title', 'untitled')
                                                if cid and cid not in [c['id'] for c in chats]:
                                                    chats.append({
                                                        'source': 'chatgpt',
                                                        'id': cid,
                                                        'title': title,
                                                        'messages': [],
                                                        'file': fname,
                                                        'metadata_only': True,
                                                        'create_time': node.get('create_time', ''),
                                                        'update_time': node.get('update_time', ''),
                                                    })
                break
    
    return chats


def main():
    print("=" * 60)
    print("Final Comprehensive Chat Extractor")
    print("=" * 60)
    
    all_chats = []
    seen_ids = set()
    
    # Scan Local Storage
    print("\n--- Local Storage ---")
    files = sorted(glob.glob(os.path.join(LS_DIR, "*.ldb")) + glob.glob(os.path.join(LS_DIR, "*.log")))
    for fpath in files:
        fname = os.path.basename(fpath)
        try:
            data = open(fpath, "rb").read()
        except:
            continue
        
        # Detect source by content
        if b'chatgpt.com' in data:
            chats = scan_for_chats(data, fname, 'chatgpt')
        elif b'ollama-web-ui' in data or b'127.0.0.1' in data:
            chats = scan_for_chats(data, fname, 'ollama-web-ui')
        else:
            chats = scan_for_chats(data, fname, 'unknown')
        
        for chat in chats:
            if chat['id'] not in seen_ids:
                seen_ids.add(chat['id'])
                all_chats.append(chat)
                msg_count = len(chat.get('messages', []))
                source = chat.get('source', '?')
                has_msgs = f"{msg_count} msgs" if msg_count > 0 else "metadata only"
                print(f"  {fname}: [{source}] {chat['title'][:50]} - {has_msgs}")
    
    # Scan IndexedDB for ChatGPT
    print("\n--- IndexedDB ---")
    idb_chatgpt = os.path.join(IDB_DIR, "https_chatgpt.com_0.indexeddb.leveldb")
    if os.path.exists(idb_chatgpt):
        files = sorted(glob.glob(os.path.join(idb_chatgpt, "*.ldb")) + glob.glob(os.path.join(idb_chatgpt, "*.log")))
        for fpath in files:
            fname = os.path.basename(fpath)
            try:
                data = open(fpath, "rb").read()
            except:
                continue
            chats = scan_for_chats(data, fname, 'chatgpt-idb')
            for chat in chats:
                if chat['id'] not in seen_ids:
                    seen_ids.add(chat['id'])
                    all_chats.append(chat)
                    print(f"  {fname}: [chatgpt-idb] {chat['title'][:50]} - {len(chat.get('messages', []))} msgs")
    
    # Also check for other IndexedDB entries
    if os.path.exists(IDB_DIR):
        for entry in os.listdir(IDB_DIR):
            if 'chatgpt' in entry.lower() or 'openai' in entry.lower():
                continue  # Already scanned
            if entry.startswith('https_') or entry.startswith('http_'):
                idb_path = os.path.join(IDB_DIR, entry, "leveldb") if os.path.isdir(os.path.join(IDB_DIR, entry)) else os.path.join(IDB_DIR, entry)
                if os.path.exists(idb_path) and os.path.isdir(idb_path):
                    files = glob.glob(os.path.join(idb_path, "*.ldb")) + glob.glob(os.path.join(idb_path, "*.log"))
                    for fpath in files:
                        fname = os.path.basename(fpath)
                        try:
                            data = open(fpath, "rb").read()
                        except:
                            continue
                        if b'"messages"' in data and b'"id"' in data:
                            source = entry.replace('https_', '').replace('http_', '').replace('_0.indexeddb.leveldb', '')
                            chats = scan_for_chats(data, fname, source)
                            for chat in chats:
                                if chat['id'] not in seen_ids:
                                    seen_ids.add(chat['id'])
                                    all_chats.append(chat)
                                    print(f"  {fname}: [{source}] {chat['title'][:50]} - {len(chat.get('messages', []))} msgs")
    
    # Deduplicate and merge (some chats appear in multiple files)
    # For chats with messages, prefer the version with more messages
    merged = {}
    for chat in all_chats:
        cid = chat['id']
        if cid in merged:
            existing = merged[cid]
            if len(chat.get('messages', [])) > len(existing.get('messages', [])):
                merged[cid] = chat
        else:
            merged[cid] = chat
    
    all_chats = list(merged.values())
    
    # Sort by source then title
    all_chats.sort(key=lambda c: (c.get('source', ''), c.get('title', '')))
    
    print(f"\n{'=' * 60}")
    print(f"Total unique chats: {len(all_chats)}")
    
    # Stats
    with_messages = sum(1 for c in all_chats if len(c.get('messages', [])) > 0)
    metadata_only = sum(1 for c in all_chats if len(c.get('messages', [])) == 0)
    total_messages = sum(len(c.get('messages', [])) for c in all_chats)
    
    by_source = {}
    for c in all_chats:
        src = c.get('source', 'unknown')
        if src not in by_source:
            by_source[src] = {'total': 0, 'with_messages': 0, 'messages': 0}
        by_source[src]['total'] += 1
        if len(c.get('messages', [])) > 0:
            by_source[src]['with_messages'] += 1
            by_source[src]['messages'] += len(c['messages'])
    
    print(f"  With messages: {with_messages}")
    print(f"  Metadata only: {metadata_only}")
    print(f"  Total messages: {total_messages}")
    print(f"\n  By source:")
    for src, stats in by_source.items():
        print(f"    {src}: {stats['total']} chats, {stats['with_messages']} with messages, {stats['messages']} total messages")
    
    # Save complete JSON
    json_path = OUTPUT_DIR / "ALL_chats_final.json"
    with open(json_path, 'w') as f:
        json.dump(all_chats, f, indent=2, ensure_ascii=False)
    print(f"\n  JSON: {json_path} ({os.path.getsize(json_path)} bytes)")
    
    # Save individual markdown files organized by source
    for i, chat in enumerate(all_chats):
        title = chat.get('title', 'untitled')
        source = chat.get('source', 'unknown')
        safe_source = re.sub(r'[^\w]', '_', source)
        safe_title = re.sub(r'[^\w\s\-]', '', title).strip()
        safe_title = re.sub(r'[\s]+', '_', safe_title) or 'untitled'
        
        md_path = OUTPUT_DIR / f"FINAL_{safe_source}_{i+1:04d}_{safe_title[:80]}.md"
        
        lines = [
            f"# {title}\n",
            f"Source: {source}\n",
            f"Chat ID: {chat.get('id', '')}\n",
        ]
        if chat.get('url'):
            lines.append(f"URL: {chat['url']}\n")
        if chat.get('create_time'):
            lines.append(f"Created: {chat['create_time']}\n")
        if chat.get('update_time'):
            lines.append(f"Updated: {chat['update_time']}\n")
        
        msgs = chat.get('messages', [])
        lines.append(f"Messages: {len(msgs)}\n")
        
        if chat.get('metadata_only'):
            lines.append("(Message content not available in cache - metadata only)\n")
        
        lines.append("---\n")
        
        for msg in msgs:
            role = msg.get('role', 'unknown').upper()
            content = msg.get('content', msg.get('text', ''))
            if isinstance(content, list):
                content = '\n'.join(str(c) for c in content)
            elif isinstance(content, dict):
                content = json.dumps(content, indent=2)
            lines.append(f"\n## [{role}]\n")
            lines.append(str(content))
            lines.append('')
        
        md_path.write_text('\n'.join(lines))
    
    print(f"  Markdown files: {OUTPUT_DIR}/FINAL_*.md")
    
    # Create summary file
    summary = {
        'total_chats': len(all_chats),
        'with_messages': with_messages,
        'metadata_only': metadata_only,
        'total_messages': total_messages,
        'by_source': by_source,
        'chats': [{'title': c.get('title', '?'), 'source': c.get('source', '?'), 'messages': len(c.get('messages', [])), 'id': c.get('id', '')} for c in all_chats],
    }
    summary_path = OUTPUT_DIR / "extraction_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"  Summary: {summary_path}")
    
    print(f"\n{'=' * 60}")
    print("Extraction complete!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
