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

# Search our blog posts across pages
found = False
for page in range(1, 20):
    r = s.get(f'https://rentmasseur.com/api/v1/blogs?page={page}', timeout=5)
    d = r.json()
    blogs = d.get('blogs', [])
    if not blogs:
        break
    for b in blogs:
        uname = b.get('userCard', {}).get('username', '')
        if 'karpathian' in uname.lower() or 'wolf' in uname.lower():
            print(f'FOUND blog p{page}: {json.dumps(b, default=str)[:500]}')
            found = True
    if found:
        break

if not found:
    print('No blog posts found in first 19 pages')

# Try creating a blog post
print('\n--- CREATE BLOG ---')
for method in ['POST', 'PUT']:
    for path in ['/api/v1/blogs', '/api/v1/account/blog', '/api/v1/settings/blog']:
        r = s.request(method, f'https://rentmasseur.com{path}',
                      json={'title': 'Test', 'content': 'Test', 'categoryId': 1}, timeout=5)
        if r.status_code != 404:
            print(f'{method} {path}: {r.status_code} {r.text[:200]}')

# GET account/blog
r = s.get('https://rentmasseur.com/api/v1/account/blog', timeout=5)
print(f'GET account/blog: {r.status_code} {r.text[:200]}')

# Try blog with user filter
r = s.get('https://rentmasseur.com/api/v1/blogs?page=1&user=Karpathianwolf', timeout=5)
print(f'GET blogs?user=: {r.status_code} {r.text[:200]}')

# Try /api/v1/blog/{id} pattern
r = s.get('https://rentmasseur.com/api/v1/blog/1', timeout=5)
print(f'GET blog/1: {r.status_code} {r.text[:200]}')

# Try /api/v1/blog/create
r = s.post('https://rentmasseur.com/api/v1/blog/create', json={'title': 'T', 'content': 'C'}, timeout=5)
print(f'POST blog/create: {r.status_code} {r.text[:200]}')

# Try /api/v1/account/blog/create
r = s.post('https://rentmasseur.com/api/v1/account/blog/create', json={'title': 'T', 'content': 'C'}, timeout=5)
print(f'POST account/blog/create: {r.status_code} {r.text[:200]}')
