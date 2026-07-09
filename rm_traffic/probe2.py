import requests, re, json

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'application/json',
    'Referer': 'https://rentmasseur.com/settings',
    'Origin': 'https://rentmasseur.com',
})

r = s.get('https://rentmasseur.com/login')
m = re.search(r'csrf["\s:=]+([A-Za-z0-9+/=]{20,})', r.text)
csrf = m.group(1) if m else ''
r = s.post('https://rentmasseur.com/api/v1/login', json={
    'email': 'karpathianwolf', 'password': 'os.environ.get("RM_PASSWORD", "")', 'csrf': csrf, 'remember': True
})
s.headers['Authorization'] = 'Bearer ' + r.json()['accessToken']
print('Login OK')

r = s.get('https://rentmasseur.com/api/v1/settings/about')
d = r.json()
h = d['userProps']['assets']['headline']
desc = d['userProps']['assets']['description']

# Try different payload structures
payloads = [
    {'headline': h, 'description': desc},
    {'assets': {'headline': h, 'description': desc}},
    {'userProps': {'assets': {'headline': h, 'description': desc}}},
    {'headline': h, 'description': desc, 'isTextUnderReview': 0},
]

for i, p in enumerate(payloads):
    r2 = s.put('https://rentmasseur.com/api/v1/settings/about', json=p)
    print(f'PUT #{i} keys={list(p.keys())}: {r2.status_code} {r2.text[:150]}')
    if r2.status_code == 200:
        print('SUCCESS')
        break

# Also try POST
r3 = s.post('https://rentmasseur.com/api/v1/settings/about', json={'headline': h, 'description': desc})
print(f'POST: {r3.status_code} {r3.text[:150]}')

# Try PATCH
r4 = s.patch('https://rentmasseur.com/api/v1/settings/about', json={'headline': h, 'description': desc})
print(f'PATCH: {r4.status_code} {r4.text[:150]}')
