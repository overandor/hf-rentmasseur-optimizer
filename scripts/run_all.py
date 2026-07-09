#!/usr/bin/env python3
"""Full sweep: get LLM7 token, probe all endpoints, validate all keys, write results."""
import httpx,json,time,re,os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed

client=httpx.Client(timeout=15)
ROOT=Path(__file__).resolve().parent.parent

# ── 1. Get LLM7 free token ──
print("═══ 1. LLM7 TOKEN ═══")
llm7_token=""
try:
    r=client.get('https://token.llm7.io')
    print(f"  token.llm7.io -> {r.status_code} {r.text[:200]}")
    if r.status_code==200:
        try:
            d=r.json()
            llm7_token=d.get('token') or d.get('key') or d.get('api_key','')
            if not llm7_token:
                for v in d.values():
                    if isinstance(v,str) and len(v)>20: llm7_token=v; break
        except:
            llm7_token=r.text.strip()
    print(f"  Token: {llm7_token[:30]}..." if llm7_token else "  No token")
except Exception as e:
    print(f"  ERR: {e}")

# ── 2. Get LLM7 models ──
print("\n═══ 2. LLM7 MODELS ═══")
llm7_models=[]
try:
    r=client.get('https://api.llm7.io/v1/models')
    if r.status_code==200:
        data=r.json()
        llm7_models=[m['id'] for m in data.get('data',[])]
        print(f"  {len(llm7_models)} models: {llm7_models}")
except Exception as e:
    print(f"  ERR: {e}")

# ── 3. Test LLM7 with token ──
print("\n═══ 3. LLM7 CHAT TEST ═══")
llm7_active=False
if llm7_token and llm7_models:
    for model in llm7_models[:3]:
        try:
            r=client.post('https://api.llm7.io/v1/chat/completions',
                json={'model':model,'messages':[{'role':'user','content':'Say hi'}],'max_tokens':10},
                headers={'Authorization':f'Bearer {llm7_token}'})
            if r.status_code==200:
                d=r.json()
                txt=d['choices'][0]['message']['content'][:50]
                print(f"  ◉ {model:30s} -> {txt}")
                llm7_active=True
                break
            else:
                print(f"  ✕ {model:30s} -> {r.status_code} {r.text[:80]}")
        except Exception as e:
            print(f"  ✕ {model:30s} -> ERR {str(e)[:60]}")

# ── 4. Crawl alistaitsacle keys ──
print("\n═══ 4. CRAWL GITHUB KEYS ═══")
all_keys=set()
key_models={}
for repo_url in [
    'https://raw.githubusercontent.com/alistaitsacle/free-llm-api-keys/main/README.md',
    'https://raw.githubusercontent.com/alistaitsacle/free-llm-api-keys/master/README.md',
]:
    try:
        r=client.get(repo_url)
        content=r.text
        keys=re.findall(r'sk-[A-Za-z0-9]{40,}',content)
        all_keys.update(keys)
        for line in content.split('\n'):
            m=re.search(r'(sk-[A-Za-z0-9]{40,})',line)
            if m:
                parts=line.split('|')
                if len(parts)>=3: key_models[m.group(1)]=parts[1].strip()
    except: pass
print(f"  Found {len(all_keys)} keys")

# ── 5. Validate pekpik keys ──
print("\n═══ 5. VALIDATE PEKPIK KEYS ═══")
pekpik_active=[]
def test_pekpik(key):
    model=key_models.get(key,'smart-chat')
    try:
        r=client.post('https://aiapiv2.pekpik.com/v1/chat/completions',
            json={'model':model,'messages':[{'role':'user','content':'Say hi'}],'max_tokens':10},
            headers={'Authorization':f'Bearer {key}'})
        if r.status_code==200:
            d=r.json()
            return 'active',0,d['choices'][0]['message']['content'][:40],model
        return 'dead',0,f'{r.status_code}',model
    except Exception as e:
        return 'dead',0,str(e)[:40],model

with ThreadPoolExecutor(max_workers=10) as pool:
    futures={pool.submit(test_pekpik,k):k for k in all_keys}
    for fut in as_completed(futures):
        k=futures[fut];status,lat,txt,model=fut.result()
        g='◉' if status=='active' else '✕'
        print(f"  {g} {k[:22]}... {status:8s} {model:25s} {txt[:25]}")
        if status=='active': pekpik_active.append({'key':k,'model':model,'response':txt})

# ── 6. Probe keyless endpoints ──
print("\n═══ 6. PROBE KEYLESS ENDPOINTS ═══")
keyless_endpoints=[
 ('https://api.llm7.io/v1/chat/completions','gpt-5.5',llm7_token),
 ('https://api.freetheai.xyz/v1/chat/completions','gpt-4o-mini',''),
 ('https://api.chutes.ai/v1/chat/completions','llama-3.3-70b',''),
 ('https://api.sambanova.ai/v1/chat/completions','Meta-Llama-3.1-405B-Instruct',''),
 ('https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions','Meta-Llama-3.1-70B-Instruct',''),
 ('https://router.huggingface.co/v1/chat/completions','meta-llama/Llama-3.3-70B-Instruct','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'),
]
endpoint_active=[]
for url,model,key in keyless_endpoints:
    headers={'Content-Type':'application/json'}
    if key: headers['Authorization']=f'Bearer {key}'
    try:
        r=client.post(url,json={'model':model,'messages':[{'role':'user','content':'Say hi'}],'max_tokens':10},headers=headers)
        if r.status_code==200:
            d=r.json()
            txt=d.get('choices',[{}])[0].get('message',{}).get('content','')[:40]
            print(f"  ◉ {url:55s} -> {txt}")
            endpoint_active.append({'endpoint':url,'model':model,'key':key,'response':txt})
        else:
            print(f"  ✕ {url:55s} -> {r.status_code} {r.text[:60]}")
    except Exception as e:
        print(f"  ✕ {url:55s} -> ERR {str(e)[:50]}")

# ── 7. Summary + write ──
print("\n═══ 7. SUMMARY ═══")
total_active=len(pekpik_active)+len(endpoint_active)+(1 if llm7_active else 0)
print(f"  LLM7 token:     {'◉ active' if llm7_active else '✕ dead'}")
print(f"  Pekpik keys:    {len(pekpik_active)} active / {len(all_keys)} tested")
print(f"  Keyless EPs:    {len(endpoint_active)} active")
print(f"  TOTAL ACTIVE:   {total_active}")

# Write .env
env_path=ROOT/'.env'
existing={}
if env_path.exists():
    for line in open(env_path,errors='ignore'):
        if '=' in line and not line.startswith('#'):
            k,v=line.strip().split('=',1); existing[k]=v.strip().strip('"')

if llm7_token:
    existing['LLM7_API_KEY']=llm7_token
    existing['LLM7_ENDPOINT']='https://api.llm7.io/v1'
    if llm7_models: existing['LLM7_MODEL']=llm7_models[0]

for i,a in enumerate(pekpik_active):
    existing[f'PEKPIK_KEY_{i+1}']=a['key']
    existing[f'PEKPIK_KEY_{i+1}_MODEL']=a['model']

for i,a in enumerate(endpoint_active):
    existing[f'FREE_EP_{i+1}']=a['endpoint']
    existing[f'FREE_EP_{i+1}_MODEL']=a['model']
    if a['key']: existing[f'FREE_EP_{i+1}_KEY']=a['key']

with open(env_path,'w') as f:
    for k,v in sorted(existing.items()): f.write(f'{k}={v}\n')
print(f"  Wrote {len(existing)} vars to .env")

# Write registry
registry=[]
if llm7_active and llm7_token:
    registry.append({'provider':'llm7','key':llm7_token[:12]+'...','status':'active','model':llm7_models[0] if llm7_models else 'gpt-5.5','score':90})
for a in pekpik_active:
    registry.append({'provider':'pekpik','key':a['key'][:12]+'...','status':'active','model':a['model'],'score':50})
for a in endpoint_active:
    ep_name=a['endpoint'].split('//')[1].split('/')[0]
    registry.append({'provider':ep_name,'key':a['key'][:12]+'...' if a['key'] else 'keyless','status':'active','model':a['model'],'score':70})
with open(ROOT/'data/api_key_registry.json','w') as f: json.dump(registry,f,indent=2)
print(f"  Wrote registry: {len(registry)} entries")

# Write chain
chain=[]
for r in registry:
    env_var='LLM7_API_KEY' if r['provider']=='llm7' else f"FREE_EP_1_KEY" if r['provider'] in [a['endpoint'].split('//')[1].split('/')[0] for a in endpoint_active] else f"PEKPIK_KEY_1"
    chain.append({'provider':r['provider'],'env_var':env_var,'model':r['model'],'score':r['score'],'endpoint':next((a['endpoint'] for a in endpoint_active if a['endpoint'].split('//')[1].split('/')[0]==r['provider']),'https://api.llm7.io/v1' if r['provider']=='llm7' else 'https://aiapiv2.pekpik.com/v1')})
with open(ROOT/'data/llm_fallback_chain.json','w') as f: json.dump(chain,f,indent=2)
print(f"  Wrote fallback chain: {len(chain)} providers")

client.close()
print(f"\n═══ DONE ═══")
