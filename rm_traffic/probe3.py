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

# Probe interview endpoints
print('\n--- INTERVIEW ---')
for path in ['/api/v1/settings/interview', '/api/v1/account/dashboard/interview', '/api/v1/account/interview']:
    r = s.get(f'https://rentmasseur.com{path}', timeout=5)
    if r.status_code != 404:
        print(f'GET {r.status_code} {path}: {r.text[:500]}')

# Probe blog endpoints
print('\n--- BLOG ---')
for path in ['/api/v1/settings/blog', '/api/v1/account/dashboard/blog', '/api/v1/account/blog', '/api/v1/blog']:
    r = s.get(f'https://rentmasseur.com{path}', timeout=5)
    if r.status_code != 404:
        print(f'GET {r.status_code} {path}: {r.text[:500]}')

# Try PUT interview with sample data
print('\n--- PUT INTERVIEW ---')
r = s.put('https://rentmasseur.com/api/v1/settings/interview', json={
    'interview': 'test answer'
})
print(f'PUT interview: {r.status_code} {r.text[:300]}')

# Try PUT blog
print('\n--- PUT/POST BLOG ---')
r = s.post('https://rentmasseur.com/api/v1/settings/blog', json={
    'title': 'test', 'content': 'test'
})
print(f'POST blog: {r.status_code} {r.text[:300]}')
r = s.put('https://rentmasseur.com/api/v1/settings/blog', json={
    'title': 'test', 'content': 'test'
})
print(f'PUT blog: {r.status_code} {r.text[:300]}')
