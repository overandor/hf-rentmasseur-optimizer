#!/usr/bin/env python3
"""PassGen — Password Generator"""
import random, string, sys
def generate(length=16, symbols=True):
    chars = string.ascii_letters + string.digits
    if symbols: chars += "!@#$%^&*"
    return "".join(random.choice(chars) for _ in range(length))
def strength(pw):
    score = sum([len(pw)>=12, any(c.isupper() for c in pw), any(c.isdigit() for c in pw), any(c in "!@#$%^&*" for c in pw)])
    return ["weak","fair","good","strong","very strong"][score]
def run():
    print(f"PassGen v1.0")
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 16
    pw = generate(n)
    print(f"Password: {pw}")
    print(f"Strength: {strength(pw)}")
    return {"name": "PassGen", "status": "running", "password": pw}
if __name__ == "__main__": run()
