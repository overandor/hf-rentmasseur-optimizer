#!/usr/bin/env python3
"""Validate all discovered keys against the correct pekpik endpoint."""
import urllib.request,json,time,re
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path

url='https://raw.githubusercontent.com/alistaitsacle/free-llm-api-keys/main/README.md'
req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
content=urllib.request.urlopen(req,timeout=15).read().decode('utf-8','ignore')
keys=list(set(re.findall(r'sk-[A-Za-z0-9]{40,}',content)))
print(f'Extracted {len(keys)} keys')

lines=content.split('\n')
key_models={}
for line in lines:
    m=re.search(r'(sk-[A-Za-z0-9]{40,})',line)
    if m:
        key=m.group(1); parts=line.split('|')
        if len(parts)>=3: key_models[key]=parts[1].strip()

EP='https://aiapiv2.pekpik.com/v1/chat/completions'

def validate(key):
    model=key_models.get(key,'smart-chat')
    body=json.dumps({'model':model,'messages':[{'role':'user','content':'Say hi'}],'max_tokens':10}).encode()
    t0=time.time()
    try:
        r=urllib.request.Request(EP,data=body,headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'},method='POST')
        resp=urllib.request.urlopen(r,timeout=15); dt=int((time.time()-t0)*1000)
        d=json.loads(resp.read()); txt=d.get('choices',[{}])[0].get('message',{}).get('content','')[:40]
        return 'active',dt,txt,model
    except urllib.error.HTTPError as e:
        dt=int((time.time()-t0)*1000)
        if e.code==429: return 'rate_limited',dt,'429',model
        if e.code in (401,403): return 'expired',dt,str(e.code),model
        return 'invalid',dt,str(e.code),model
    except Exception as e: return 'invalid',0,str(e)[:40],model

active=[]
with ThreadPoolExecutor(max_workers=12) as pool:
    futures={pool.submit(validate,k):k for k in keys}
    for fut in as_completed(futures):
        k=futures[fut];status,lat,txt,model=fut.result()
        g={'active':'OK','expired':'EXP','rate_limited':'RL'}.get(status,'BAD')
        print(f'{g:3s} {k[:20]}... {lat:5d}ms {model:25s} {txt[:25]}')
        if status=='active': active.append({'key':k,'latency':lat,'model':model})

print(f'\n{len(keys)} tested | {len(active)} active')
if active:
    active.sort(key=lambda x:x['latency'])
    env=Path('.env'); ex={}
    if env.exists():
        for l in open(env,errors='ignore'):
            if '=' in l and not l.startswith('#'): k,v=l.strip().split('=',1);ex[k]=v.strip()
    ex['PEKPIK_API_KEY']=active[0]['key']
    ex['PEKPIK_ENDPOINT']='https://aiapiv2.pekpik.com/v1'
    ex['PEKPIK_MODEL']=active[0]['model']
    for i,a in enumerate(active):
        ex[f'FREE_KEY_{i+1}']=a['key']
        ex[f'FREE_KEY_{i+1}_MODEL']=a['model']
    with open(env,'w') as f:
        for k,v in sorted(ex.items()): f.write(f'{k}={v}\n')
    reg=[{'provider':'pekpik','key':a['key'][:12]+'...','status':'active','latency_ms':a['latency'],'model':a['model'],'score':round(max(0,100-min(a['latency'],2000)/20),1)} for a in active]
    chain=[{'provider':'pekpik','env_var':f'FREE_KEY_{i+1}','model':a['model'],'score':round(max(0,100-min(a['latency'],2000)/20),1),'latency_ms':a['latency']} for i,a in enumerate(active)]
    with open('data/api_key_registry.json','w') as f: json.dump(reg,f,indent=2)
    with open('data/llm_fallback_chain.json','w') as f: json.dump(chain,f,indent=2)
    print(f'Wrote {len(active)} keys to .env + registry + chain')
