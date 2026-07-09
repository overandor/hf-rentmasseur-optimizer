#!/usr/bin/env python3
"""TodoCLI — CLI Todo Manager"""
import json, sys, os
from pathlib import Path
DB = Path.home() / ".todocli.json"
def load():
    if DB.exists(): return json.loads(DB.read_text())
    return []
def save(todos): DB.write_text(json.dumps(todos, indent=2))
def add(text):
    todos = load()
    todos.append({"id": len(todos)+1, "text": text, "done": False})
    save(todos)
    print(f"Added: #{len(todos)} {text}")
def lst():
    todos = load()
    if not todos: print("No todos."); return
    for t in todos:
        print(f"[{'✓' if t['done'] else ' '}] #{t['id']} {t['text']}")
def done(tid):
    todos = load()
    for t in todos:
        if t["id"] == tid: t["done"] = True
    save(todos)
def run():
    print(f"TodoCLI v1.0")
    if len(sys.argv) < 2: lst(); return
    cmd = sys.argv[1]
    if cmd == "add": add(" ".join(sys.argv[2:]))
    elif cmd == "list": lst()
    elif cmd == "done": done(int(sys.argv[2]))
    return {"name": "TodoCLI", "status": "running", "todos": len(load())}
if __name__ == "__main__": run()
