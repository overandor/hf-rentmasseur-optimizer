#!/usr/bin/env python3
"""Deep scan repos for keys + endpoints."""
import urllib.request,json,re

repos=[
 ('Free-The-Ai/free-ai','https://api.freetheai.xyz/v1'),
 ('open-free-llm-api/awesome-freellm-apis',None),
 ('Arthur-Ficial/apfel',None),
 ('diegosouzapw/OmniRoute',None),
 ('Kame696/kame-api-engine',None),
 ('Devineukaryotic6777/keylessai',None),
 ('xiaopengs/llm-keypool',None),
 ('izaart95-jpg/GLM-Free-API',None),
]
KEY_PATS=[r'gsk_[A-Za-z0-9]{30,}',r'sk-or-[A-Za-z0-9]{30,}',r'sk-[A-Za-z0-9]{40,}',r'AIza[A-Za-z0-9_-]{35}',r'hf_[A-Za-z0-9]{30,}']

for repo,hint_ep in repos:
    for branch in ['main','master']:
        for fname in ['README.md','keys.md','keys.json','.env.example','config.md']:
            url=f'https://raw.githubusercontent.com/{repo}/{branch}/{fname}'
            try:
                req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
                data=urllib.request.urlopen(req,timeout=8).read().decode('utf-8','ignore')
                keys=[]
                for p in KEY_PATS: keys+=re.findall(p,data)
                keys=list(set(keys))
                eps=re.findall(r'https?://[a-zA-Z0-9.-]+/v1',data)
                if keys or eps:
                    print(f'{repo}/{fname} ({branch})')
                    if keys:
                        print(f'  KEYS ({len(keys)}):')
                        for k in keys[:5]: print(f'    {k}')
                    if eps:
                        print(f'  ENDPOINTS:')
                        for e in set(eps): print(f'    {e}')
                    print()
                break
            except: continue
