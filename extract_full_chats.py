#!/usr/bin/env python3
"""
Extract full ChatGPT conversations with messages from cached LevelDB data.
The data is in all_cached_data.json under key '006825.ldb_list_559409'.
"""

import json
import re
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "chatgpt_exports"
INPUT_FILE = OUTPUT_DIR / "all_cached_data.json"


def main():
    print("Loading cached data...")
    with open(INPUT_FILE, 'r') as f:
        data = json.load(f)
    
    # Find the chat list with messages
    chat_list = None
    for key, value in data.items():
        if isinstance(value, dict) and 'list' in value:
            lst = value['list']
            if isinstance(lst, list) and len(lst) > 0:
                if isinstance(lst[0], dict) and 'messages' in lst[0]:
                    chat_list = lst
                    print(f"Found chat list in '{key}': {len(lst)} chats")
                    break
        elif isinstance(value, list) and len(value) > 0:
            if isinstance(value[0], dict) and 'messages' in value[0]:
                chat_list = value
                print(f"Found chat list in '{key}': {len(value)} chats")
                break
    
    if not chat_list:
        print("No chat list with messages found!")
        # Try to find any list with chat-like data
        for key, value in data.items():
            if isinstance(value, dict) and 'list' in value:
                lst = value['list']
                if isinstance(lst, list) and len(lst) > 0:
                    if isinstance(lst[0], dict):
                        print(f"  {key}: list of {len(lst)} dicts, keys: {list(lst[0].keys())}")
        return
    
    print(f"\nProcessing {len(chat_list)} chats...")
    
    # Save full JSON
    json_path = OUTPUT_DIR / "full_chats_with_messages.json"
    with open(json_path, 'w') as f:
        json.dump(chat_list, f, indent=2, ensure_ascii=False)
    print(f"Saved JSON: {json_path}")
    
    # Save individual markdown files
    total_messages = 0
    for i, chat in enumerate(chat_list):
        title = chat.get('title', 'untitled')
        chat_id = chat.get('id', '')
        msgs = chat.get('messages', [])
        total_messages += len(msgs)
        
        safe = re.sub(r'[^\w\s\-]', '', title).strip()
        safe = re.sub(r'[\s]+', '_', safe) or 'untitled'
        md_path = OUTPUT_DIR / f"full_{i+1:04d}_{safe[:100]}.md"
        
        lines = [f"# {title}\n", f"Chat ID: {chat_id}\n", f"Messages: {len(msgs)}\n", "---\n"]
        for msg in msgs:
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
        print(f"  [{i+1}/{len(chat_list)}] {title[:50]} - {len(msgs)} msgs")
    
    print(f"\n{'=' * 60}")
    print(f"Extraction complete!")
    print(f"  Total chats: {len(chat_list)}")
    print(f"  Total messages: {total_messages}")
    print(f"  JSON: {json_path}")
    print(f"  Markdown files: {OUTPUT_DIR}/full_*.md")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
