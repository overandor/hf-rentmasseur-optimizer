#!/usr/bin/env python3
"""Run all: test LLM7 anonymous, probe endpoints, crawl keys, validate, write results."""
import json,time,re,os
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
import urllib.request,urllib.error

def post_json(url,body,headers=None,timeout=15):
    h=headers or {}
    h['Content-Type']='application/json'
    data=json.dumps(body).encode()
    req=urllib.request.Request(url,data=data,headers=h,method='POST')
    return urllib.request.urlopen(req,timeout=timeout)

def get_json(url,headers=None,timeout=15):
    h=headers or {}
    h['User-Agent']='Mozilla/5.0'
    req=urllib.request.Request(url,headers=h)
    return urllib.request.urlopen(req,timeout=timeout)

# ── 1. LLM7 anonymous (api_key="unused") ──
print("═══ 1. LLM7 ANONYMOUS ═══")
llm7_models=['default','fast','gpt-5.5','gpt-5.4-mini','deepseek-v4-flash','gemini-3.5-flash','grok-420-fast']
llm7_active=[]
for model in llm7_models:
    t0=time.time()
    try:
        resp=post_json('https://api.llm7.io/v1/chat/completions',
            {'model':model,'messages':[{'role':'user','content':'Say hello in 5 words'}],'max_tokens':20},
            {'Authorization':'Bearer unused'})
        dt=int((time.time()-t0)*1000)
        d=json.loads(resp.read())
        txt=d['choices'][0]['message']['content'][:60]
        print(f"  ◉ {model:25s} {dt:5d}ms -> {txt}")
        llm7_active.append({'model':model,'latency':dt,'response':txt})
    except urllib.error.HTTPError as e:
        dt=int((time.time()-t0)*1000)
        print(f"  ✕ {model:25s} {dt:5d}ms -> {e.code} {e.read().decode()[:60]}")
    except Exception as e:
        print(f"  ✕ {model:25s} -> ERR {str(e)[:50]}")

# ── 2. Crawl GitHub keys ──
print("\n═══ 2. CRAWL GITHUB ═══")
all_keys=set()
key_models={}
try:
    resp=get_json('https://raw.githubusercontent.com/alistaitsacle/free-llm-api-keys/main/README.md')
    content=resp.read().decode('utf-8','ignore')
    all_keys=set(re.findall(r'sk-[A-Za-z0-9]{40,}',content))
    for line in content.split('\n'):
        m=re.search(r'(sk-[A-Za-z0-9]{40,})',line)
        if m:
            parts=line.split('|')
            if len(parts)>=3: key_models[m.group(1)]=parts[1].strip()
except Exception as e:
    print(f"  ERR: {e}")
print(f"  Found {len(all_keys)} keys")

# ── 3. Validate pekpik keys ──
print("\n═══ 3. VALIDATE PEKPIK ═══")
pekpik_active=[]
for key in all_keys:
    model=key_models.get(key,'smart-chat')
    t0=time.time()
    try:
        resp=post_json('https://aiapiv2.pekpik.com/v1/chat/completions',
            {'model':model,'messages':[{'role':'user','content':'Say hi'}],'max_tokens':10},
            {'Authorization':f'Bearer {key}'})
        dt=int((time.time()-t0)*1000)
        d=json.loads(resp.read())
        txt=d['choices'][0]['message']['content'][:40]
        print(f"  ◉ {key[:22]}... {dt:5d}ms {model:25s} -> {txt}")
        pekpik_active.append({'key':key,'model':model,'latency':dt,'response':txt})
    except urllib.error.HTTPError as e:
        pass
    except Exception as e:
        pass
print(f"  {len(pekpik_active)} active / {len(all_keys)} tested")

# ── 4. Probe other endpoints ──
print("\n═══ 4. PROBE ENDPOINTS ═══")
endpoints=[
 ('https://api.freetheai.xyz/v1/chat/completions','gpt-4o-mini',''),
 ('https://api.chutes.ai/v1/chat/completions','llama-3.3-70b',''),
 ('https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions','Meta-Llama-3.1-70B-Instruct',''),
 ('https://router.huggingface.co/v1/chat/completions','meta-llama/Llama-3.3-70B-Instruct','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'),
 ('https://api.groq.com/openai/v1/chat/completions','llama-3.3-70b-versatile','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'),
 ('https://api.mistral.ai/v1/chat/completions','mistral-small-latest','4521f0c56e39b374cb4df235ab69c27f548e59c24ffb67b6b7a38f968a6d23b3'),
]
ep_active=[]
for url,model,key in endpoints:
    headers={}
    if key: headers['Authorization']=f'Bearer {key}'
    t0=time.time()
    try:
        resp=post_json(url,{'model':model,'messages':[{'role':'user','content':'Say hi'}],'max_tokens':10},headers)
        dt=int((time.time()-t0)*1000)
        d=json.loads(resp.read())
        txt=d.get('choices',[{}])[0].get('message',{}).get('content','')[:40]
        print(f"  ◉ {url:55s} {dt:5d}ms -> {txt}")
        ep_active.append({'endpoint':url,'model':model,'key':key,'latency':dt,'response':txt})
    except urllib.error.HTTPError as e:
        dt=int((time.time()-t0)*1000)
        print(f"  ✕ {url:55s} {dt:5d}ms -> {e.code}")
    except Exception as e:
        print(f"  ✕ {url:55s} -> ERR {str(e)[:50]}")

# ── 5. Summary + write ──
print("\n═══ 5. SUMMARY ═══")
total=len(llm7_active)+len(pekpik_active)+len(ep_active)
print(f"  LLM7 (anonymous): {len(llm7_active)} models active")
print(f"  Pekpik keys:      {len(pekpik_active)} active / {len(all_keys)} tested")
print(f"  Other endpoints:  {len(ep_active)} active")
print(f"  TOTAL ACTIVE:     {total}")

# Write .env
env=ROOT/'.env'; ex={}
if env.exists():
    for l in open(env,errors='ignore'):
        if '=' in l and not l.startswith('#'): k,v=l.strip().split('=',1);ex[k]=v.strip().strip('"')
if llm7_active:
    ex['LLM7_API_KEY']='unused'
    ex['LLM7_ENDPOINT']='https://api.llm7.io/v1'
    ex['LLM7_MODEL']=llm7_active[0]['model']
for i,a in enumerate(pekpik_active):
    ex[f'PEKPIK_KEY_{i+1}']=a['key']
    ex[f'PEKPIK_KEY_{i+1}_MODEL']=a['model']
for i,a in enumerate(ep_active):
    name=a['endpoint'].split('//')[1].split('/')[0].replace('.','_').upper()
    ex[f'EP_{i+1}_URL']=a['endpoint']
    ex[f'EP_{i+1}_MODEL']=a['model']
    if a['key']: ex[f'EP_{i+1}_KEY']=a['key']
with open(env,'w') as f:
    for k,v in sorted(ex.items()): f.write(f'{k}={v}\n')
print(f"  Wrote {len(ex)} vars to .env")

# Write registry
reg=[]
for m in llm7_active:
    reg.append({'provider':'llm7','key':'unused','status':'active','model':m['model'],'latency_ms':m['latency'],'score':round(max(0,100-min(m['latency'],2000)/20),1),'response':m['response'][:60]})
for a in pekpik_active:
    reg.append({'provider':'pekpik','key':a['key'][:12]+'...','status':'active','model':a['model'],'latency_ms':a['latency'],'score':round(max(0,100-min(a['latency'],2000)/20),1)})
for a in ep_active:
    name=a['endpoint'].split('//')[1].split('/')[0]
    reg.append({'provider':name,'key':a['key'][:12]+'...' if a['key'] else 'keyless','status':'active','model':a['model'],'latency_ms':a['latency'],'score':round(max(0,100-min(a['latency'],2000)/20),1)})
with open(ROOT/'data/api_key_registry.json','w') as f: json.dump(reg,f,indent=2)
print(f"  Wrote registry: {len(reg)} entries")

# Write chain
chain=[]
for r in reg:
    if r['provider']=='llm7': ev='LLM7_API_KEY'
    elif r['provider']=='pekpik': ev='PEKPIK_KEY_1'
    else: ev='EP_1_KEY'
    ep='https://api.llm7.io/v1' if r['provider']=='llm7' else 'https://aiapiv2.pekpik.com/v1' if r['provider']=='pekpik' else ''
    chain.append({'provider':r['provider'],'env_var':ev,'model':r['model'],'score':r['score'],'latency_ms':r.get('latency_ms',0),'endpoint':ep})
with open(ROOT/'data/llm_fallback_chain.json','w') as f: json.dump(chain,f,indent=2)
print(f"  Wrote chain: {len(chain)} providers")
print("\n═══ DONE ═══")
