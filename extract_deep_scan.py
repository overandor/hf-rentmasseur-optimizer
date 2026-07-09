#!/usr/bin/env python3
"""
Deep scan of all LevelDB files for any ChatGPT conversation data.
Searches for all JSON objects containing 'id' and 'messages' or 'title' fields.
Also searches for conversation IDs we found earlier but don't have messages for.
"""

import os
import re
import json
import glob
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "chatgpt_exports"
LS_DIR = os.path.expanduser("~/Library/Application Support/Microsoft Edge/Default/Local Storage/leveldb")
IDB_DIR = os.path.expanduser("~/Library/Application Support/Microsoft Edge/Default/IndexedDB/https_chatgpt.com_0.indexeddb.leveldb")

# Chat IDs we found earlier but don't have messages for
MISSING_IDS = [
    "3632942d", "a31a6101", "f5de2332", "8494f606", "6a38684d",
    "7b44b80a", "d8746e2e", "3f08a1c8",
]


def extract_json_objects(data, max_results=200):
    """Find all JSON objects in raw bytes, more aggressively."""
    results = []
    i = 0
    while i < len(data) and len(results) < max_results:
        if data[i:i+1] in (b'{', b'['):
            depth = 0
            in_string = False
            escape = False
            start = i
            for j in range(i, min(i + 5000000, len(data))):
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


def main():
    print("=" * 60)
    print("Deep LevelDB Scanner for ChatGPT Data")
    print("=" * 60)
    
    all_conversations = {}
    all_chat_metadata = {}
    
    # Scan both Local Storage and IndexedDB
    for directory, label in [(LS_DIR, "Local Storage"), (IDB_DIR, "IndexedDB")]:
        if not os.path.exists(directory):
            print(f"\n{label}: directory not found")
            continue
        
        files = sorted(glob.glob(os.path.join(directory, "*.ldb")) + 
                       glob.glob(os.path.join(directory, "*.log")) +
                       glob.glob(os.path.join(directory, "*.sst")))
        
        print(f"\n{label}: {len(files)} files")
        
        for fpath in files:
            fname = os.path.basename(fpath)
            try:
                data = open(fpath, "rb").read()
            except:
                continue
            
            # Search for conversation IDs
            for mid in MISSING_IDS:
                if mid.encode() in data:
                    print(f"  {fname}: Found missing ID '{mid}'!")
                    # Try to extract JSON around it
                    idx = data.find(mid.encode())
                    # Search backwards for opening brace
                    for back in range(idx, max(0, idx - 500), -1):
                        if data[back:back+1] == b'{':
                            # Try to parse from here
                            jsons = extract_json_objects(data[back:back+500000], max_results=5)
                            for _, _, obj in jsons:
                                if isinstance(obj, dict):
                                    obj_str = json.dumps(obj)[:500]
                                    if mid in obj_str:
                                        if 'messages' in obj:
                                            chat_id = obj.get('id', mid)
                                            all_conversations[chat_id] = obj
                                            print(f"    -> Found conversation with {len(obj['messages'])} messages!")
                                        elif 'title' in obj:
                                            all_chat_metadata[obj.get('id', mid)] = obj
                                            print(f"    -> Found metadata: {obj.get('title', '?')[:50]}")
                            break
            
            # Also extract all JSON objects and look for chat data
            jsons = extract_json_objects(data, max_results=300)
            for _, _, obj in jsons:
                if isinstance(obj, dict):
                    # Check for conversation with messages
                    if 'messages' in obj and 'id' in obj:
                        chat_id = obj.get('id', '')
                        if chat_id and chat_id not in all_conversations:
                            all_conversations[chat_id] = obj
                            print(f"  {fname}: conversation '{obj.get('title', '?')[:50]}' - {len(obj['messages'])} msgs")
                    
                    # Check for conversation list
                    if 'value' in obj and isinstance(obj['value'], dict):
                        value = obj['value']
                        if 'pages' in value and isinstance(value['pages'], list):
                            for page in value['pages']:
                                if isinstance(page, dict):
                                    items = page.get('items', page.get('conversations', page.get('edges', [])))
                                    if isinstance(items, list):
                                        for item in items:
                                            if isinstance(item, dict):
                                                node = item.get('node', item)
                                                cid = node.get('id', '')
                                                if cid and cid not in all_chat_metadata:
                                                    all_chat_metadata[cid] = node
                
                elif isinstance(obj, list):
                    for item in obj:
                        if isinstance(item, dict):
                            if 'messages' in item and 'id' in item:
                                cid = item.get('id', '')
                                if cid and cid not in all_conversations:
                                    all_conversations[cid] = item
                                    print(f"  {fname}: conversation '{item.get('title', '?')[:50]}' - {len(item['messages'])} msgs")
                            elif 'id' in item and 'title' in item:
                                cid = item.get('id', '')
                                if cid and cid not in all_chat_metadata:
                                    all_chat_metadata[cid] = item
    
    print(f"\n{'=' * 60}")
    print(f"Results:")
    print(f"  Conversations with messages: {len(all_conversations)}")
    print(f"  Chat metadata (title only): {len(all_chat_metadata)}")
    
    # Combine: use conversations with messages, add metadata for the rest
    all_chats = []
    
    for cid, conv in all_conversations.items():
        all_chats.append({
            'id': cid,
            'title': conv.get('title', 'untitled'),
            'messages': conv.get('messages', []),
            'message_count': len(conv.get('messages', [])),
            'has_content': True,
        })
    
    for cid, meta in all_chat_metadata.items():
        if cid not in all_conversations:
            all_chats.append({
                'id': cid,
                'title': meta.get('title', 'untitled'),
                'messages': [],
                'message_count': 0,
                'has_content': False,
            })
    
    print(f"  Total unique chats: {len(all_chats)}")
    
    # Save everything
    # Full JSON
    json_path = OUTPUT_DIR / "all_chats_complete.json"
    with open(json_path, 'w') as f:
        json.dump(all_chats, f, indent=2, ensure_ascii=False)
    print(f"\n  JSON: {json_path}")
    
    # Individual markdown files
    for i, chat in enumerate(all_chats):
        title = chat['title']
        safe = re.sub(r'[^\w\s\-]', '', title).strip()
        safe = re.sub(r'[\s]+', '_', safe) or 'untitled'
        md_path = OUTPUT_DIR / f"complete_{i+1:04d}_{safe[:100]}.md"
        
        lines = [f"# {title}\n", f"Chat ID: {chat['id']}\n", f"Messages: {chat['message_count']}\n"]
        if not chat['has_content']:
            lines.append("(Message content not available in cache)\n")
        lines.append("---\n")
        
        for msg in chat['messages']:
            role = msg.get('role', 'unknown').upper()
            content = msg.get('content', '')
            if isinstance(content, list):
                content = '\n'.join(str(c) for c in content)
            elif isinstance(content, dict):
                content = json.dumps(content, indent=2)
            lines.append(f"\n## [{role}]\n")
            lines.append(str(content))
            lines.append('')
        
        md_path.write_text('\n'.join(lines))
    
    print(f"  Markdown files: {OUTPUT_DIR}/complete_*.md")
    print(f"\n{'=' * 60}")


if __name__ == "__main__":
    main()
