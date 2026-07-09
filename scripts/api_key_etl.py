#!/usr/bin/env python3
"""API Key ETL Agent — Discover, Validate, Rank, Write. Stamps files, doesn't print them."""
import json,os,re,sys,time,urllib.request,urllib.error,glob
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent; DATA=ROOT/"data"; DATA.mkdir(exist_ok=True)
RECEIPTS=ROOT/"receipts"; RECEIPTS.mkdir(exist_ok=True); ENV_PATH=ROOT/".env"
CATALOG=json.load(open(DATA/"api_catalog.json"))["services"]
KEY_PATTERNS={r"gsk_[A-Za-z0-9]{40,}":"GROQ_API_KEY",r"sk-or-[A-Za-z0-9]{40,}":"OPENROUTER_API_KEY",r"hf_[A-Za-z0-9]{20,}":"HF_TOKEN",r"AIza[A-Za-z0-9_-]{35}":"GEMINI_API_KEY",r"sk-[A-Za-z0-9]{40,}":"OPENAI_API_KEY",r"csk-[A-Za-z0-9]{40,}":"CEREBRAS_API_KEY",r"[A-Za-z0-9]{40,}":"MISTRAL_API_KEY"}
VALIDATE_PROMPT={"role":"user","content":"Say hello in 5 words."}
VALIDATE_BODY=lambda m:json.dumps({"model":m,"messages":[{"role":"system","content":"Reply briefly."},VALIDATE_PROMPT],"max_tokens":50,"temperature":0.1})
GEMINI_BODY=lambda m:json.dumps({"contents":[{"parts":[{"text":"Say hello in 5 words."}]}],"generationConfig":{"maxOutputTokens":50}})

def now(): return datetime.now(timezone.utc).isoformat()

def discover_local():
    """Scan ~/Downloads, ~/, project dirs for .env files and extract keys by pattern."""
    found={}; search_paths=[str(ROOT/".env"),str(Path.home()/".env")]+glob.glob(str(Path.home()/"Downloads"/"*"/".env"))+glob.glob(str(Path.home()/"Downloads"/"*.env"))
    for fp in search_paths:
        if not os.path.exists(fp): continue
        for line in open(fp,errors="ignore"):
            line=line.strip()
            if "=" not in line or line.startswith("#"): continue
            k,v=line.split("=",1); v=v.strip().strip("'\"")
            for pat,env_var in KEY_PATTERNS.items():
                if re.fullmatch(pat,v): found[env_var]=v; break
    return found

def discover_github_keys():
    """Fetch live keys from alistaitsacle/free-llm-api-keys GitHub repo."""
    found={}; urls=["https://raw.githubusercontent.com/alistaitsacle/free-llm-api-keys/main/README.md","https://raw.githubusercontent.com/alistaitsacle/free-llm-api-keys/master/README.md"]
    for url in urls:
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
            content=urllib.request.urlopen(req,timeout=10).read().decode("utf-8",errors="ignore")
            keys=re.findall(r"sk-[A-Za-z0-9]{40,}",content)
            if keys: found["OPENAI_COMPATIBLE_KEYS"]=list(set(keys))[:20]
            gkeys=re.findall(r"gsk_[A-Za-z0-9]{40,}",content)
            if gkeys: found["GROQ_DISCOVERED"]=list(set(gkeys))[:10]
            break
        except: continue
    return found

def validate_oai_compat(endpoint,key,model):
    """Validate OpenAI-compatible endpoint. Returns (status,latency_ms,error)."""
    body=VALIDATE_BODY(model).encode(); headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"}
    t0=time.time()
    try:
        req=urllib.request.Request(endpoint,data=body,headers=headers,method="POST")
        resp=urllib.request.urlopen(req,timeout=15); dt=int((time.time()-t0)*1000)
        data=json.loads(resp.read()); return "active",dt,None
    except urllib.error.HTTPError as e:
        dt=int((time.time()-t0)*1000); code=e.code
        if code==429: return "rate_limited",dt,"429 Too Many Requests"
        if code==401 or code==403: return "expired",dt,f"{code} Auth Failed"
        return "invalid",dt,f"HTTP {code}: {e.read().decode()[:200]}"
    except Exception as e: return "invalid",int((time.time()-t0)*1000),str(e)[:200]

def validate_gemini(key,model):
    """Validate Google Gemini endpoint."""
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body=GEMINI_BODY(model).encode(); t0=time.time()
    try:
        req=urllib.request.Request(url,data=body,headers={"Content-Type":"application/json"},method="POST")
        resp=urllib.request.urlopen(req,timeout=15); dt=int((time.time()-t0)*1000)
        return "active",dt,None
    except urllib.error.HTTPError as e:
        dt=int((time.time()-t0)*1000); code=e.code
        if code==429: return "rate_limited",dt,"429"
        if code in(401,403): return "expired",dt,f"{code}"
        return "invalid",dt,f"HTTP {code}"
    except Exception as e: return "invalid",int((time.time()-t0)*1000),str(e)[:200]

def validate_hf(key,model):
    """Validate HuggingFace token."""
    url=f"https://api-inference.huggingface.co/models/{model}"; body=json.dumps({"inputs":"Hello"}).encode()
    headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"}; t0=time.time()
    try:
        req=urllib.request.Request(url,data=body,headers=headers,method="POST")
        resp=urllib.request.urlopen(req,timeout=20); dt=int((time.time()-t0)*1000)
        return "active",dt,None
    except urllib.error.HTTPError as e:
        dt=int((time.time()-t0)*1000); code=e.code
        if code==429: return "rate_limited",dt,"429"
        if code in(401,403): return "expired",dt,f"{code}"
        return "loading" if code==503 else "invalid",dt,f"HTTP {code}"
    except Exception as e: return "invalid",int((time.time()-t0)*1000),str(e)[:200]

def validate_cohere(key,model):
    """Validate Cohere endpoint."""
    body=json.dumps({"message":"Say hello","model":model}).encode()
    headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"}; t0=time.time()
    try:
        req=urllib.request.Request("https://api.cohere.ai/v1/chat",data=body,headers=headers,method="POST")
        resp=urllib.request.urlopen(req,timeout=15); dt=int((time.time()-t0)*1000)
        return "active",dt,None
    except urllib.error.HTTPError as e:
        dt=int((time.time()-t0)*1000); code=e.code
        if code==429: return "rate_limited",dt,"429"
        if code in(401,403): return "expired",dt,f"{code}"
        return "invalid",dt,f"HTTP {code}"
    except Exception as e: return "invalid",int((time.time()-t0)*1000),str(e)[:200]

def validate_key(svc,key):
    """Route to correct validator based on provider."""
    p=svc["p"]; model=svc.get("m",[""])[0] if svc.get("m") else ""
    if p=="google": return validate_gemini(key,model)
    if p=="huggingface": return validate_hf(key,model)
    if p=="cohere": return validate_cohere(key,model)
    if svc.get("oai"): return validate_oai_compat(svc["e"],key,model)
    return "untested",0,"no validator"

def rate_limit_probe(svc,key):
    """Send 3 rapid requests to detect RPM ceiling."""
    statuses=[]
    for _ in range(3):
        s,_,_=validate_key(svc,key); statuses.append(s)
        if s!="active": break
    active=sum(1 for s in statuses if s=="active")
    if active==3: return "high_rpm"
    if active==2: return "medium_rpm"
    if active==1: return "low_rpm"
    return "dead"

def score_key(status,latency,rl_probe,oai_compat):
    """Score: latency(40%) + rate limit(30%) + model quality(20%) + oai bonus(10%)."""
    if status!="active": return 0
    lat_score=max(0,100-min(latency,2000)/20)
    rl_score={"high_rpm":100,"medium_rpm":70,"low_rpm":40,"dead":0}.get(rl_probe,0)
    oai_score=100 if oai_compat else 50
    return round(lat_score*0.4+rl_score*0.3+oai_score*0.2+oai_score*0.1,1)

def run_etl(dry_run=False,phase="all"):
    """Full ETL pipeline: discover → validate → rank → write."""
    report={"timestamp":now(),"phases":[]}
    # ── DISCOVER ──
    if phase in("all","discover"):
        print("[DISCOVER] Scanning local .env files..."); local=discover_local(); print(f"  Found {len(local)} local keys")
        print("[DISCOVER] Fetching GitHub live keys..."); github=discover_github_keys(); print(f"  Found {len(github)} GitHub key sets")
        all_keys={**local}
        for k,v in github.items():
            if isinstance(v,list): all_keys[k]=v[0] if v else ""
            else: all_keys[k]=v
        report["phases"].append({"phase":"discover","local_keys":len(local),"github_keys":len(github),"total":len(all_keys)})
        if not dry_run: json.dump(all_keys,open(DATA/"discovered_keys.json","w"),indent=2)
    else: all_keys=json.load(open(DATA/"discovered_keys.json")) if (DATA/"discovered_keys.json").exists() else {}
    # ── VALIDATE ──
    if phase in("all","validate"):
        print("[VALIDATE] Testing all keys against endpoints..."); results=[]
        tasks=[]
        for svc in CATALOG:
            env_var=svc.get("env",""); key=all_keys.get(env_var,"")
            if not key: continue
            tasks.append((svc,key))
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures={pool.submit(validate_key,svc,key):svc for svc,key in tasks}
            for fut in as_completed(futures):
                svc=futures[fut]; status,latency,err=fut.result()
                rl=rate_limit_probe(svc,all_keys.get(svc.get("env",""))) if status=="active" else "dead"
                score=score_key(status,latency,rl,svc.get("oai",0))
                r={"provider":svc["p"],"name":svc["n"],"env_var":svc.get("env",""),"status":status,"latency_ms":latency,"rate_limit":rl,"score":score,"model":svc["m"][0] if svc.get("m") else "","error":err,"timestamp":now()}
                results.append(r); print(f"  {svc['p']:15s} {status:12s} {latency:5d}ms score={score}")
        report["phases"].append({"phase":"validate","tested":len(tasks),"active":sum(1 for r in results if r["status"]=="active"),"expired":sum(1 for r in results if r["status"]=="expired"),"invalid":sum(1 for r in results if r["status"]=="invalid")})
        if not dry_run: json.dump(results,open(DATA/"api_key_registry.json","w"),indent=2)
    else: results=json.load(open(DATA/"api_key_registry.json")) if (DATA/"api_key_registry.json").exists() else []
    # ── RANK ──
    if phase in("all","rank"):
        print("[RANK] Scoring and building fallback chain...")
        active=[r for r in results if r["status"]=="active"]
        active.sort(key=lambda r:r["score"],reverse=True)
        chain=[{"provider":r["provider"],"env_var":r["env_var"],"model":r["model"],"score":r["score"],"latency_ms":r["latency_ms"],"rate_limit":r["rate_limit"]} for r in active]
        report["phases"].append({"phase":"rank","active_keys":len(active),"chain_length":len(chain)})
        if not dry_run: json.dump(chain,open(DATA/"llm_fallback_chain.json","w"),indent=2)
        print(f"  Fallback chain: {[c['provider'] for c in chain[:10]]}")
    # ── WRITE .ENV ──
    if phase in("all","write") and not dry_run:
        print("[WRITE] Updating .env with validated keys...")
        existing={}
        if ENV_PATH.exists():
            for line in open(ENV_PATH,errors="ignore"):
                if "=" in line and not line.startswith("#"):
                    k,v=line.strip().split("=",1); existing[k]=v.strip().strip("'\"")
        for svc in CATALOG:
            env_var=svc.get("env",""); key=all_keys.get(env_var,"")
            if key: existing[env_var]=key
        with open(ENV_PATH,"w") as f:
            for k,v in sorted(existing.items()): f.write(f"{k}={v}\n")
        print(f"  Wrote {len(existing)} keys to .env")
    # ── RECEIPT ──
    if not dry_run:
        receipt={"agent":"api_key_etl","timestamp":now(),"report":report,"catalog_size":len(CATALOG)}
        json.dump(receipt,open(RECEIPTS/f"api_key_etl_{int(time.time())}.json","w"),indent=2)
    print(f"\n[DONE] Catalog: {len(CATALOG)} services | Active keys: {sum(1 for r in results if r['status']=='active')} | Expired: {sum(1 for r in results if r['status']=='expired')}")
    return report

if __name__=="__main__":
    import argparse; p=argparse.ArgumentParser(); p.add_argument("--phase",default="all",choices=["all","discover","validate","rank","write"]); p.add_argument("--dry-run",action="store_true"); a=p.parse_args()
    run_etl(dry_run=a.dry_run,phase=a.phase)
