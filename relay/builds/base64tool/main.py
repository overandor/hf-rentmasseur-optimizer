#!/usr/bin/env python3
"""Base64Tool — Base64 Tool"""
import base64, sys
def encode(text): return base64.b64encode(text.encode()).decode()
def decode(b64): return base64.b64decode(b64.encode()).decode()
def run():
    print(f"Base64Tool v1.0")
    return {"name": "Base64Tool", "status": "running"}
if __name__ == "__main__": run()
