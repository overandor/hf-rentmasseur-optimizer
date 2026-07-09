import requests, re, json

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json',
    'Referer': 'https://rentmasseur.com/settings', 'Origin': 'https://rentmasseur.com',
})
s.get('https://rentmasseur.com/login')
m = re.search(r'csrf["\s:=]+([A-Za-z0-9+/=]{20,})', s.get('https://rentmasseur.com/login').text)
csrf = m.group(1) if m else ''
r = s.post('https://rentmasseur.com/api/v1/login', json={
    'email': 'karpathianwolf', 'password': 'os.environ.get("RM_PASSWORD", "")', 'csrf': csrf, 'remember': True
})
s.headers['Authorization'] = 'Bearer ' + r.json()['accessToken']
print('Login OK')

# Blogs
for p in ['?page=1', '?username=Karpathianwolf', '/list', '/user']:
    r = s.get(f'https://rentmasseur.com/api/v1/blogs{p}', timeout=5)
    print(f'GET blogs{p}: {r.status_code} {r.text[:200]}')

# POST blog variants
for path in ['/api/v1/blogs', '/api/v1/account/blogs', '/api/v1/settings/blog']:
    r = s.post(f'https://rentmasseur.com{path}', json={'title': 'Test', 'content': 'Test'}, timeout=5)
    print(f'POST {path}: {r.status_code} {r.text[:200]}')

# Interview - try fetching the public profile page which has interview
r = s.get('https://rentmasseur.com/api/v1/account/blogs', timeout=5)
print(f'GET account/blogs: {r.status_code} {r.text[:200]}')

# Rates
r = s.get('https://rentmasseur.com/api/v1/settings/rates')
d = r.json()
print(f'GET rates keys: {list(d.keys())}')
print(json.dumps(d, indent=2, default=str)[:1000])
