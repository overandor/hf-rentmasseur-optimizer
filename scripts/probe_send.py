#!/usr/bin/env python3
"""Probe deeper for message send endpoint."""
import requests, re, json

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://rentmasseur.com/settings/mailbox',
    'Origin': 'https://rentmasseur.com',
})
s.get('https://rentmasseur.com/login')
m = re.search(r'csrf["\s:=]+([A-Za-z0-9+/=]{20,})', s.get('https://rentmasseur.com/login').text)
csrf = m.group(1) if m else ''
r = s.post('https://rentmasseur.com/api/v1/login', json={
    'email': 'karpathianwolf', 'password': 'os.environ.get("RM_PASSWORD", "")', 'csrf': csrf, 'remember': True
})
s.headers['Authorization'] = 'Bearer ' + r.json()['accessToken']
print('Login OK')

# Get full thread to understand message structure
r = s.get('https://rentmasseur.com/api/v1/mailbox/47126391', timeout=10)
d = r.json()
print(f'\nThread keys: {list(d.keys())}')
msgs = d.get('messages', [])
print(f'Messages: {len(msgs)}')
if msgs:
    print(f'First message keys: {list(msgs[0].keys())}')
    print(json.dumps(msgs[0], indent=2, default=str)[:800])
profile = d.get('profileData', {})
print(f'\nProfile data: {json.dumps(profile, indent=2)[:300]}')

# Now try sending with various body structures
eid = 47126391
uname = 'Brooklynkm'
uid = 160758

print(f'\n--- SEND PROBES ---')
bodies = [
    {'message': 'test', 'emailId': eid},
    {'message': 'test', 'userId': uid},
    {'message': 'test', 'username': uname},
    {'body': 'test', 'emailId': eid},
    {'text': 'test', 'emailId': eid},
    {'message': 'test', 'emailId': eid, 'userId': uid},
    {'message': 'test', 'emailId': eid, 'username': uname},
]

for p in ['/api/v1/mailbox/reply', '/api/v1/mailbox/send', '/api/v1/mailbox/message', '/api/v1/mailbox']:
    for body in bodies:
        try:
            r3 = s.post(f'https://rentmasseur.com{p}', json=body, timeout=5)
            if r3.status_code != 404:
                print(f'  POST {p} body={json.dumps(body)}: {r3.status_code} {r3.text[:200]}')
        except:
            pass

# Try PUT on mailbox (some APIs use PUT for reply)
for p in [f'/api/v1/mailbox/{eid}', '/api/v1/mailbox/reply']:
    try:
        r4 = s.put(f'https://rentmasseur.com{p}', json={'message': 'test', 'emailId': eid}, timeout=5)
        if r4.status_code != 404:
            print(f'  PUT {p}: {r4.status_code} {r4.text[:200]}')
    except:
        pass

print('\nDone.')
