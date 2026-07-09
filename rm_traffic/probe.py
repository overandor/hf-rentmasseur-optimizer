import requests, re, json

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'application/json,text/plain,*/*',
    'Referer': 'https://rentmasseur.com/settings',
    'Origin': 'https://rentmasseur.com',
})

r = s.get('https://rentmasseur.com/login')
m = re.search(r'csrf["\s:=]+([A-Za-z0-9+/=]{20,})', r.text)
csrf = m.group(1) if m else ''
r = s.post('https://rentmasseur.com/api/v1/login', json={
    'email': 'karpathianwolf', 'password': 'os.environ.get("RM_PASSWORD", "")', 'csrf': csrf, 'remember': True
})
token = r.json().get('accessToken', '')
s.headers['Authorization'] = f'Bearer {token}'
print('Login OK')

# UNHIDE
r = s.put('https://rentmasseur.com/api/v1/settings/visibility', json={'isAdHidden': False})
print('UNHIDE:', r.status_code, r.text[:200])

# Probe endpoints
endpoints = [
    ('GET', '/api/v1/account/interview'),
    ('GET', '/api/v1/account/blog'),
    ('GET', '/api/v1/account/profile'),
    ('GET', '/api/v1/account/bio'),
    ('GET', '/api/v1/account/about'),
    ('GET', '/api/v1/account/travels'),
    ('GET', '/api/v1/account/photos'),
    ('GET', '/api/v1/account/reviews'),
    ('GET', '/api/v1/account/membership'),
    ('GET', '/api/v1/account/sponsor'),
    ('GET', '/api/v1/settings/profile'),
    ('GET', '/api/v1/settings/bio'),
    ('GET', '/api/v1/settings/about'),
    ('GET', '/api/v1/settings/interview'),
    ('GET', '/api/v1/settings/blog'),
    ('GET', '/api/v1/account/dashboard/interview'),
    ('GET', '/api/v1/account/dashboard/blog'),
    ('GET', '/api/v1/account/dashboard/profile'),
    ('GET', '/api/v1/account/dashboard/bio'),
    ('GET', '/api/v1/account/dashboard/about'),
    ('GET', '/api/v1/blog'),
    ('GET', '/api/v1/interview'),
    ('GET', '/api/v1/profile'),
    ('PUT', '/api/v1/settings/profile'),
    ('PUT', '/api/v1/settings/bio'),
    ('PUT', '/api/v1/settings/about'),
    ('PUT', '/api/v1/settings/interview'),
    ('PUT', '/api/v1/settings/blog'),
    ('PUT', '/api/v1/account/profile'),
    ('PUT', '/api/v1/account/interview'),
    ('PUT', '/api/v1/account/blog'),
    ('POST', '/api/v1/account/blog'),
    ('POST', '/api/v1/account/interview'),
    ('POST', '/api/v1/account/profile'),
    ('POST', '/api/v1/blog'),
    ('POST', '/api/v1/interview'),
    ('GET', '/api/v1/account/dashboard/membership'),
    ('GET', '/api/v1/account/dashboard/sponsor'),
    ('GET', '/api/v1/account/dashboard/advertise'),
    ('GET', '/api/v1/account/dashboard/travels'),
    ('GET', '/api/v1/account/dashboard/photos'),
    ('GET', '/api/v1/account/dashboard/reviews'),
    ('GET', '/api/v1/account/dashboard/blog'),
    ('GET', '/api/v1/account/dashboard/interview'),
    ('GET', '/api/v1/account/dashboard/certificates'),
    ('GET', '/api/v1/account/dashboard/massages'),
    ('GET', '/api/v1/account/certificates'),
    ('GET', '/api/v1/account/massages'),
    ('GET', '/api/v1/settings/certificates'),
    ('GET', '/api/v1/settings/massages'),
    ('GET', '/api/v1/settings/travels'),
    ('GET', '/api/v1/settings/reviews'),
    ('GET', '/api/v1/settings/membership'),
    ('GET', '/api/v1/settings/sponsor'),
    ('GET', '/api/v1/settings/advertise'),
]

for method, path in endpoints:
    url = f'https://rentmasseur.com{path}'
    try:
        if method == 'GET':
            r = s.get(url, timeout=5)
        elif method == 'POST':
            r = s.post(url, json={}, timeout=5)
        elif method == 'PUT':
            r = s.put(url, json={}, timeout=5)
        if r.status_code != 404:
            body = r.text[:150].replace('\n', ' ')
            print(f'{method:4s} {r.status_code} {path:55s} {body}')
    except Exception as e:
        print(f'{method:4s} ERR {path:55s} {str(e)[:80]}')
