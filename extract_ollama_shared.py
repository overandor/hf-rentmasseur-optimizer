#!/usr/bin/env python3
"""Extract Ollama Web UI shared link chats from Edge LevelDB."""
import os, re, json, base64, urllib.parse
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "chatgpt_exports"
LS_DIR = os.path.expanduser("~/Library/Application Support/Microsoft Edge/Default/Local Storage/leveldb")

# Read 006826.ldb which contains the shared links
fpath = os.path.join(LS_DIR, "006826.ldb")
data = open(fpath, "rb").read()

# Find all share= parameters
results = []
idx = 0
while True:
    idx = data.find(b"share=", idx)
    if idx < 0:
        break
    
    # Extract the base64 string
    start = idx + 6
    end = start
    while end < len(data) and data[end:end+1] not in (b'\x00', b'"', b"'", b' ', b'\n', b'\r', b'\x01', b'\x02', b'\x03', b'\x04', b'\x05'):
        end += 1
    
    encoded = data[start:end].decode("utf-8", errors="ignore")
    
    # URL decode
    decoded_url = urllib.parse.unquote(encoded)
    
    # Add padding
    padding = 4 - len(decoded_url) % 4
    if padding != 4:
        decoded_url += "=" * padding
    
    try:
        decoded_bytes = base64.b64decode(decoded_url)
        text = decoded_bytes.decode("utf-8", errors="ignore")
        obj = json.loads(text)
        if isinstance(obj, dict) and "messages" in obj:
            title = obj.get("title", "?")
            messages = obj.get("messages", [])
            print(f"Shared chat: {title} - {len(messages)} messages")
            results.append(obj)
    except Exception as e:
        pass  # Not valid base64 or not JSON
    
    idx = end

# Also extract from 006824.ldb (the local Ollama Web UI instance)
fpath2 = os.path.join(LS_DIR, "006824.ldb")
data2 = open(fpath2, "rb").read()

# Find threads-v1 data (local Ollama Web UI chats)
idx = data2.find(b"threads-v1")
if idx >= 0:
    # Search forward for JSON array
    for fwd in range(idx, min(idx + 200, len(data2))):
        if data2[fwd:fwd+1] == b"[":
            # Try to find the end of the JSON array
            depth = 0
            in_str = False
            esc = False
            for j in range(fwd, min(fwd + 5000000, len(data2))):
                c = data2[j:j+1]
                if esc:
                    esc = False
                    continue
                if c == b'\\':
                    esc = True
                    continue
                if c == b'"':
                    in_str = not in_str
                    continue
                if in_str:
                    continue
                if c in (b'{', b'['):
                    depth += 1
                elif c in (b'}', b']'):
                    depth -= 1
                    if depth == 0:
                        try:
                            text = data2[fwd:j+1].decode("utf-8", errors="ignore")
                            arr = json.loads(text)
                            if isinstance(arr, list):
                                for item in arr:
                                    if isinstance(item, dict) and "messages" in item:
                                        title = item.get("title", "?")
                                        msgs = item.get("messages", [])
                                        print(f"Local Ollama chat: {title} - {len(msgs)} messages")
                                        results.append(item)
                        except:
                            pass
                        break
            break

# Save all Ollama Web UI chats
if results:
    (OUTPUT_DIR / "ollama_webui_all_chats.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False)
    )
    print(f"\nSaved {len(results)} Ollama Web UI chats to ollama_webui_all_chats.json")
    
    # Save individual markdown files
    for i, chat in enumerate(results):
        title = chat.get("title", "untitled")
        safe = re.sub(r"[^\w\s\-]", "", title).strip()
        safe = re.sub(r"[\s]+", "_", safe) or "untitled"
        md_path = OUTPUT_DIR / f"ollama_{i+1:04d}_{safe[:100]}.md"
        
        lines = [f"# {title}\n", f"Source: Ollama Web UI\n", f"Messages: {len(chat.get('messages', []))}\n", "---\n"]
        for msg in chat.get("messages", []):
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "")
            if isinstance(content, list):
                content = "\n".join(str(c) for c in content)
            lines.append(f"\n## [{role}]\n")
            lines.append(str(content))
            lines.append("")
        
        md_path.write_text("\n".join(lines))
    
    print(f"Saved {len(results)} markdown files (ollama_*.md)")
else:
    print("No Ollama Web UI chats found.")

print("\nDone!")
