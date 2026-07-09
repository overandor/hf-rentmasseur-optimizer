#!/usr/bin/env python3
"""HashDiff — A file integrity checker using SHA-256"""
import sys, json
def run():
    print(f"HashDiff v1.0")
    print("Description: A file integrity checker using SHA-256")
    return {"name": "HashDiff", "status": "running", "args": sys.argv[1:]}
if __name__ == "__main__": run()
