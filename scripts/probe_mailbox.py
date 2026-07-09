#!/usr/bin/env python3
"""Probe RentMasseur mailbox API to discover message structure and send endpoints."""
import requests, re, json

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://rentmasseur.com/settings',
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

# 1. Read mailbox
r = s.get('https://rentmasseur.com/api/v1/mailbox?page=1&folder=1&sort=1', timeout=10)
d = r.json()
emails = d.get('emails', [])
print(f'\nMailbox: {len(emails)} emails')
if not emails:
    print('No emails found. Exiting.')
    exit(0)

e = emails[0]
eid = e.get('id', '')
uname = e.get('userCard', {}).get('username', '')
print(f'\nFirst email structure:')
print(json.dumps(e, indent=2, default=str)[:2000])

# 2. Probe read/thread endpoints
print(f'\n--- READ ENDPOINTS (email_id={eid}, username={uname}) ---')
for p in [
    f'/api/v1/mailbox/{eid}',
    f'/api/v1/mailbox/email/{eid}',
    f'/api/v1/mailbox/thread/{uname}',
    f'/api/v1/mailbox/conversation/{uname}',
    f'/api/v1/mailbox/{eid}/thread',
    f'/api/v1/mailbox/{eid}/messages',
]:
    try:
        r2 = s.get(f'https://rentmasseur.com{p}', timeout=5)
        status = r2.status_code
        body = r2.text[:300]
        if status != 404:
            print(f'  GET {p}: {status} {body}')
    except Exception as ex:
        print(f'  GET {p}: ERROR {ex}')

# 3. Probe send/reply endpoints
print(f'\n--- SEND ENDPOINTS ---')
send_body = {'username': uname, 'message': 'test probe', 'body': 'test probe', 'text': 'test probe', 'emailId': eid, 'recipient': uname}
for p in [
    '/api/v1/mailbox/send',
    '/api/v1/mailbox/reply',
    '/api/v1/mailbox',
    '/api/v1/mailbox/message',
    '/api/v1/message/send',
    '/api/v1/messages',
    '/api/v1/messages/send',
    '/api/v1/mailbox/reply/' + str(eid),
    '/api/v1/mailbox/' + str(eid) + '/reply',
]:
    try:
        r3 = s.post(f'https://rentmasseur.com{p}', json=send_body, timeout=5)
        status = r3.status_code
        body = r3.text[:300]
        if status != 404:
            print(f'  POST {p}: {status} {body}')
    except Exception as ex:
        print(f'  POST {p}: ERROR {ex}')

# 4. Check mailbox folders
print(f'\n--- MAILBOX FOLDERS ---')
for folder in range(1, 6):
    r4 = s.get(f'https://rentmasseur.com/api/v1/mailbox?page=1&folder={folder}&sort=1', timeout=5)
    d4 = r4.json()
    count = len(d4.get('emails', []))
    if count > 0:
        print(f'  folder={folder}: {count} emails')
        for em in d4.get('emails', [])[:3]:
            print(f'    from={em.get("userCard",{}).get("username","")} subject={em.get("subject","")[:40]} body={em.get("body","")[:80]}')

print('\nDone.')
