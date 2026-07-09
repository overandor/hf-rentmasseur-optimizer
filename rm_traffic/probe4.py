import requests, re, json

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'application/json',
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

# Exhaustive probe
paths = [
    # Interview variations
    '/api/v1/account/interview',
    '/api/v1/account/interviews',
    '/api/v1/settings/interview',
    '/api/v1/interview',
    '/api/v1/account/dashboard/interview',
    '/api/v1/account/dashboard/interviews',
    '/api/v1/account/feature-interview',
    '/api/v1/account/featureInterview',
    '/api/v1/settings/feature-interview',
    '/api/v1/settings/featureInterview',
    # Blog variations
    '/api/v1/account/blog',
    '/api/v1/account/blogs',
    '/api/v1/account/blog/list',
    '/api/v1/settings/blog',
    '/api/v1/settings/blog/list',
    '/api/v1/blog',
    '/api/v1/blogs',
    '/api/v1/account/dashboard/blog',
    '/api/v1/account/dashboard/blogs',
    # Profile/bio variations
    '/api/v1/account/profile',
    '/api/v1/account/bio',
    '/api/v1/account/about',
    '/api/v1/settings/profile',
    '/api/v1/settings/bio',
    '/api/v1/settings/about',
    '/api/v1/profile',
    '/api/v1/account/dashboard/profile',
    '/api/v1/account/dashboard/bio',
    '/api/v1/account/dashboard/about',
    # Travels
    '/api/v1/account/travels',
    '/api/v1/settings/travels',
    '/api/v1/account/dashboard/travels',
    # Photos
    '/api/v1/account/photos',
    '/api/v1/settings/photos',
    '/api/v1/account/dashboard/photos',
    # Reviews
    '/api/v1/account/reviews',
    '/api/v1/settings/reviews',
    # Membership
    '/api/v1/account/membership',
    '/api/v1/settings/membership',
    '/api/v1/account/dashboard/membership',
    # Sponsor
    '/api/v1/account/sponsor',
    '/api/v1/settings/sponsor',
    '/api/v1/account/dashboard/sponsor',
    # Advertise
    '/api/v1/account/advertise',
    '/api/v1/settings/advertise',
    '/api/v1/account/dashboard/advertise',
    # Certificates
    '/api/v1/account/certificates',
    '/api/v1/settings/certificates',
    # Massages/rates
    '/api/v1/account/massages',
    '/api/v1/settings/massages',
    '/api/v1/account/dashboard/massages',
    '/api/v1/account/services',
    '/api/v1/settings/services',
    '/api/v1/account/rates',
    '/api/v1/settings/rates',
]

for path in paths:
    try:
        r = s.get(f'https://rentmasseur.com{path}', timeout=5)
        if r.status_code != 404:
            body = r.text[:200].replace('\n', ' ')
            print(f'GET {r.status_code} {path:55s} {body}')
    except:
        pass
