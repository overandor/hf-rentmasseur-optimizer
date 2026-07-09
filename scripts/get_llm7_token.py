#!/usr/bin/env python3
"""Get a free LLM7 token and test it."""
import urllib.request,json,time

url='https://token.llm7.io'
try:
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
    resp=urllib.request.urlopen(req,timeout=10)
    data=resp.read().decode()
    print(f'Status: {resp.status}')
    print(f'Body: {data[:500]}')
except urllib.error.HTTPError as e:
    print(f'{e.code}: {e.read().decode()[:300]}')
except Exception as e:
    print(f'ERR: {e}')

# Try POST
print('--- POST ---')
try:
    body=json.dumps({}).encode()
    req=urllib.request.Request(url,data=body,headers={'User-Agent':'Mozilla/5.0','Content-Type':'application/json'},method='POST')
    resp=urllib.request.urlopen(req,timeout=10)
    print(f'Status: {resp.status} Body: {resp.read().decode()[:500]}')
except urllib.error.HTTPError as e:
    print(f'{e.code}: {e.read().decode()[:300]}')
except Exception as e:
    print(f'ERR: {e}')

# Try subpaths
for path in ['/register','/signup','/free','/api-key','/keys']:
    try:
        u=f'https://token.llm7.io{path}'
        req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
        resp=urllib.request.urlopen(req,timeout=8)
        print(f'{path}: {resp.status} {resp.read().decode()[:200]}')
    except urllib.error.HTTPError as e:
        print(f'{path}: {e.code} {e.read().decode()[:100]}')
    except Exception as e:
        print(f'{path}: ERR {str(e)[:60]}')
