#!/usr/bin/env python3
"""Search GitHub for fresh free API key repos, extract keys, find endpoints."""
import urllib.request,json,re,time

search_urls=[
 'https://api.github.com/search/repositories?q=free+llm+api+key&sort=updated&per_page=10',
 'https://api.github.com/search/repositories?q=free+openai+api&sort=updated&per_page=10',
 'https://api.github.com/search/repositories?q=api+key+pool+llm&sort=updated&per_page=10',
 'https://api.github.com/search/repositories?q=openai+compatible+free&sort=updated&per_page=10',
]

repos=set()
for url in search_urls:
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
        resp=urllib.request.urlopen(req,timeout=10)
        data=json.loads(resp.read())
        for item in data.get('items',[]):
            if 'full_name' in item:
                repos.add(item['full_name'])
                print(f'  REPO: {item["full_name"]:40s} updated={item.get("updated_at","")[:10]} stars={item.get("stargazers_count",0)}')
    except Exception as e:
        print(f'  ERR: {str(e)[:60]}')

print(f'\n{len(repos)} unique repos found\n')

KEY_PATS=[r'gsk_[A-Za-z0-9]{30,}',r'sk-or-[A-Za-z0-9]{30,}',r'sk-[A-Za-z0-9]{40,}',r'AIza[A-Za-z0-9_-]{35}',r'hf_[A-Za-z0-9]{30,}']
all_keys=set()
all_endpoints=set()

for repo in repos:
    for branch in ['main','master']:
        url=f'https://raw.githubusercontent.com/{repo}/{branch}/README.md'
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
            data=urllib.request.urlopen(req,timeout=8).read().decode('utf-8','ignore')
            keys=[]
            for p in KEY_PATS: keys+=re.findall(p,data)
            keys=list(set(keys))
            if keys:
                print(f'  {repo:40s} {len(keys)} keys')
                for k in keys[:3]: print(f'    {k[:40]}...')
                all_keys.update(keys)
            eps=re.findall(r'https?://[a-zA-Z0-9.-]+/v1',data)
            if eps:
                for e in set(eps):
                    print(f'    EP: {e}')
                    all_endpoints.add(e)
            break
        except: continue

print(f'\nTOTAL UNIQUE KEYS: {len(all_keys)}')
print(f'ENDPOINTS FOUND:')
for e in sorted(all_endpoints): print(f'  {e}')
