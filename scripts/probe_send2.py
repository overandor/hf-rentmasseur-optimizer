#!/usr/bin/env python3
"""Probe deeper for message send endpoint using API client."""
import sys, os, json, requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rm_traffic.api_client import RentMasseurAPI

api = RentMasseurAPI(min_request_interval=0.5)
ok = api.login("karpathianwolf", "os.environ.get("RM_PASSWORD", "")")
if not ok:
    print("Login failed")
    sys.exit(1)
print("Login OK")

# Get mailbox
mail = api.get_mailbox(page=1, folder=1)
emails = mail.get("emails", [])
print(f"Mailbox: {len(emails)} emails")
if not emails:
    sys.exit(0)

e = emails[0]
eid = e.get("id")
uname = e.get("userCard", {}).get("username")
uid = e.get("userCard", {}).get("id")
print(f"First email: id={eid} user={uname} uid={uid}")

# Read full thread
r = api.session.get(f"https://rentmasseur.com/api/v1/mailbox/{eid}", timeout=10)
print(f"\nThread GET: {r.status_code}")
d = r.json()
msgs = d.get("messages", [])
print(f"Messages in thread: {len(msgs)}")
if msgs:
    print(f"Message keys: {list(msgs[0].keys())}")
    print(json.dumps(msgs[0], indent=2, default=str)[:500])

# Probe send endpoints
print(f"\n--- SEND PROBES ---")
send_bodies = [
    {"message": "test", "emailId": eid},
    {"message": "test", "userId": uid},
    {"message": "test", "username": uname},
    {"body": "test", "emailId": eid},
    {"text": "test", "emailId": eid},
    {"message": "test", "emailId": eid, "userId": uid},
]

for p in ["/api/v1/mailbox/reply", "/api/v1/mailbox/send", "/api/v1/mailbox/message", "/api/v1/mailbox", f"/api/v1/mailbox/{eid}/reply", f"/api/v1/mailbox/{eid}/send"]:
    for body in send_bodies:
        try:
            r3 = api.session.post(f"https://rentmasseur.com{p}", json=body, timeout=5)
            if r3.status_code != 404:
                print(f"  POST {p} body={json.dumps(body)}: {r3.status_code} {r3.text[:200]}")
        except Exception as ex:
            pass

# Try PUT
for p in [f"/api/v1/mailbox/{eid}", "/api/v1/mailbox/reply"]:
    try:
        r4 = api.session.put(f"https://rentmasseur.com{p}", json={"message": "test", "emailId": eid}, timeout=5)
        if r4.status_code != 404:
            print(f"  PUT {p}: {r4.status_code} {r4.text[:200]}")
    except:
        pass

print("\nDone.")
