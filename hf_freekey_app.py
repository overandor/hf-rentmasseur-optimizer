#!/usr/bin/env python3
"""FreeKey Agent — HuggingFace Space app that crawls, retrieves, validates, and serves free LLM API keys.
Deploy to HF Spaces. Auto-discovers keys from GitHub repos, validates them, serves via OpenAI-compatible proxy."""
import json,os,re,sys,time,glob,urllib.request,urllib.error,subprocess
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse,JSONResponse
from pydantic import BaseModel

DATA=Path(os.environ.get("FREEKEY_DATA_DIR",str(Path(__file__).resolve().parent/"data"))); DATA.mkdir(exist_ok=True)
CATALOG_PATH=DATA/"api_catalog.json"; REGISTRY_PATH=DATA/"api_key_registry.json"
CHAIN_PATH=DATA/"llm_fallback_chain.json"; DISCOVERED_PATH=DATA/"discovered_keys.json"

SOURCES=[
 "https://raw.githubusercontent.com/alistaitsacle/free-llm-api-keys/main/README.md",
 "https://raw.githubusercontent.com/alistaitsacle/free-llm-api-keys/master/README.md",
 "https://raw.githubusercontent.com/cheahjs/free-llm-api-resources/main/README.md",
]
KEY_RE=[r"gsk_[A-Za-z0-9]{40,}",r"sk-or-[A-Za-z0-9]{40,}",r"sk-[A-Za-z0-9]{40,}",r"hf_[A-Za-z0-9]{20,}",r"AIza[A-Za-z0-9_-]{35}"]
PROVIDERS={
 "groq":{"endpoint":"https://api.groq.com/openai/v1/chat/completions","model":"llama-3.3-70b-versatile","oai":True},
 "openrouter":{"endpoint":"https://openrouter.ai/api/v1/chat/completions","model":"meta-llama/llama-3.3-70b-instruct:free","oai":True},
 "openai_compat":{"endpoint":"https://api.llm7.io/v1/chat/completions","model":"gpt-4o-mini","oai":True},
 "cerebras":{"endpoint":"https://api.cerebras.ai/v1/chat/completions","model":"llama-3.3-70b","oai":True},
 "mistral":{"endpoint":"https://api.mistral.ai/v1/chat/completions","model":"mistral-small-latest","oai":True},
 "together":{"endpoint":"https://api.together.xyz/v1/chat/completions","model":"meta-llama/Llama-3.3-70B-Instruct-Turbo","oai":True},
 "fireworks":{"endpoint":"https://api.fireworks.ai/inference/v1/chat/completions","model":"accounts/fireworks/models/llama-v3p3-70b-instruct","oai":True},
 "deepseek":{"endpoint":"https://api.deepseek.com/v1/chat/completions","model":"deepseek-chat","oai":True},
 "sambanova":{"endpoint":"https://api.sambanova.ai/v1/chat/completions","model":"Meta-Llama-3.1-405B-Instruct","oai":True},
 "siliconflow":{"endpoint":"https://api.siliconflow.cn/v1/chat/completions","model":"deepseek-ai/DeepSeek-V3","oai":True},
 "nvidia":{"endpoint":"https://integrate.api.nvidia.com/v1/chat/completions","model":"meta/llama-3.3-70b-instruct","oai":True},
 "hyperbolic":{"endpoint":"https://api.hyperbolic.xyz/v1/chat/completions","model":"meta-llama/llama-3.3-70b-instruct","oai":True},
 "novita":{"endpoint":"https://api.novita.ai/v3/openai/chat/completions","model":"meta-llama/llama-3.3-70b-instruct","oai":True},
}
GEMINI_URL="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
HF_URL="https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3"

app=FastAPI(title="FreeKey Agent",version="1.0.0")
_USAGE={"total":0,"per_provider":{},"fallbacks":0,"last_crawl":None}

def now(): return datetime.now(timezone.utc).isoformat()

def crawl_github():
 """Crawl GitHub repos for free API keys."""
 found={"groq":[],"openrouter":[],"openai_compat":[],"hf":[],"gemini":[]}
 for url in SOURCES:
  try:
   req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
   content=urllib.request.urlopen(req,timeout=10).read().decode("utf-8","ignore")
   for pat in KEY_RE:
    keys=list(set(re.findall(pat,content)))
    if re.match(r"gsk_",pat): found["groq"]+=keys
    elif re.match(r"sk-or-",pat): found["openrouter"]+=keys
    elif re.match(r"sk-",pat): found["openai_compat"]+=keys
    elif re.match(r"hf_",pat): found["hf"]+=keys
    elif re.match(r"AIza",pat): found["gemini"]+=keys
  except: continue
 # Dedupe
 for k in found: found[k]=list(set(found[k]))[:20]
 return found

def discover_local():
 """Scan for .env files in common locations."""
 found={}
 for fp in [str(Path.home()/".env")]+glob.glob(str(Path.home()/"Downloads"/"**"/".env"),recursive=True)+glob.glob(str(Path("/data"/"*.env"))):
  if not os.path.exists(fp): continue
  for line in open(fp,errors="ignore"):
   if "=" not in line or line.startswith("#"): continue
   k,v=line.strip().split("=",1); v=v.strip().strip("'\"")
   for pat in KEY_RE:
    if re.fullmatch(pat,v): found[k]=v; break
 return found

def validate_oai(endpoint,key,model):
 body=json.dumps({"model":model,"messages":[{"role":"user","content":"Say hi"}],"max_tokens":10}).encode()
 headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"}
 t0=time.time()
 try:
  req=urllib.request.Request(endpoint,data=body,headers=headers,method="POST")
  resp=urllib.request.urlopen(req,timeout=15); dt=int((time.time()-t0)*1000)
  data=json.loads(resp.read()); txt=data["choices"][0]["message"]["content"][:50]
  return "active",dt,txt
 except urllib.error.HTTPError as e:
  dt=int((time.time()-t0)*1000); code=e.code
  if code==429: return "rate_limited",dt,"429"
  if code in(401,403): return "expired",dt,f"{code}"
  return "invalid",dt,f"{code}"
 except Exception as e: return "invalid",int((time.time()-t0)*1000),str(e)[:80]

def validate_gemini(key):
 url=f"{GEMINI_URL}?key={key}"
 body=json.dumps({"contents":[{"parts":[{"text":"Say hi"}]}],"generationConfig":{"maxOutputTokens":10}}).encode()
 t0=time.time()
 try:
  req=urllib.request.Request(url,data=body,headers={"Content-Type":"application/json"},method="POST")
  resp=urllib.request.urlopen(req,timeout=15); dt=int((time.time()-t0)*1000)
  data=json.loads(resp.read()); txt=data["candidates"][0]["content"]["parts"][0]["text"][:50]
  return "active",dt,txt
 except urllib.error.HTTPError as e:
  dt=int((time.time()-t0)*1000); code=e.code
  if code==429: return "rate_limited",dt,"429"
  if code in(401,403): return "expired",dt,f"{code}"
  return "invalid",dt,f"{code}"
 except Exception as e: return "invalid",int((time.time()-t0)*1000),str(e)[:80]

def validate_hf(key):
 body=json.dumps({"inputs":"Say hi"}).encode()
 headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"}
 t0=time.time()
 try:
  req=urllib.request.Request(HF_URL,data=body,headers=headers,method="POST")
  resp=urllib.request.urlopen(req,timeout=20); dt=int((time.time()-t0)*1000)
  data=json.loads(resp.read()); txt=str(data[0].get("generated_text",""))[:50]
  return "active",dt,txt
 except urllib.error.HTTPError as e:
  dt=int((time.time()-t0)*1000); code=e.code
  if code==429: return "rate_limited",dt,"429"
  if code in(401,403): return "expired",dt,f"{code}"
  if code==503: return "loading",dt,"model loading"
  return "invalid",dt,f"{code}"
 except Exception as e: return "invalid",int((time.time()-t0)*1000),str(e)[:80]

def validate_all(discovered):
 """Validate all discovered keys in parallel. Returns list of results."""
 results=[]; tasks=[]
 # Build task list
 for prov,keys in discovered.items():
  if not isinstance(keys,list): continue
  for key in keys:
   if prov=="gemini": tasks.append(("gemini",key,validate_gemini,key))
   elif prov=="hf": tasks.append(("hf",key,validate_hf,key))
   elif prov in PROVIDERS:
    pinfo=PROVIDERS[prov]; tasks.append((prov,key,validate_oai,pinfo["endpoint"],key,pinfo["model"]))
 # Run in parallel
 with ThreadPoolExecutor(max_workers=15) as pool:
  futures={}
  for t in tasks:
   if t[0]=="gemini": futures[pool.submit(validate_gemini,t[1])]=t
   elif t[0]=="hf": futures[pool.submit(validate_hf,t[1])]=t
   else: futures[pool.submit(validate_oai,t[3],t[4],t[5])]=t
  for fut in as_completed(futures):
   t=futures[fut]; prov=t[0]; key=t[1]
   status,latency,txt=fut.result()
   score=max(0,100-min(latency,2000)/20) if status=="active" else 0
   results.append({"provider":prov,"key":key[:12]+"...","status":status,"latency_ms":latency,"score":round(score,1),"response":txt,"timestamp":now()})
 results.sort(key=lambda r:r["score"],reverse=True)
 return results

def build_chain(results):
 """Build fallback chain from active keys."""
 active=[r for r in results if r["status"]=="active"]
 active.sort(key=lambda r:r["score"],reverse=True)
 chain=[]
 for r in active:
  prov=r["provider"]; pinfo=PROVIDERS.get(prov,{"endpoint":"","model":""})
  chain.append({"provider":prov,"endpoint":pinfo.get("endpoint",""),"model":pinfo.get("model",""),"score":r["score"],"latency_ms":r["latency_ms"],"key_prefix":r["key"]})
 return chain

def save_json(path,data):
 with open(path,"w") as f: json.dump(data,f,indent=2)

def load_json(path):
 if path.exists():
  with open(path) as f: return json.load(f)
 return {} if "catalog" in str(path) else [] if "chain" in str(path) or "registry" in str(path) else {}

def run_crawl():
 """Full crawl: discover → validate → rank → save."""
 t0=time.time()
 print("[CRAWL] Discovering keys from GitHub...")
 github=crawl_github()
 print(f"[CRAWL] GitHub: {sum(len(v) for v in github.values())} keys found")
 local=discover_local()
 print(f"[CRAWL] Local: {len(local)} keys found")
 # Merge: local env vars override
 discovered=dict(github)
 for k,v in local.items():
  kl=k.lower()
  if "groq" in kl: discovered.setdefault("groq",[]).append(v)
  elif "openrouter" in kl: discovered.setdefault("openrouter",[]).append(v)
  elif "hf" in kl or "hugging" in kl: discovered.setdefault("hf",[]).append(v)
  elif "gemini" in kl or "google" in kl: discovered.setdefault("gemini",[]).append(v)
  elif "mistral" in kl: discovered.setdefault("mistral",[]).append(v)
 save_json(DISCOVERED_PATH,discovered)
 print("[CRAWL] Validating all keys in parallel...")
 results=validate_all(discovered)
 save_json(REGISTRY_PATH,results)
 print(f"[CRAWL] Validated: {len(results)} keys, {sum(1 for r in results if r['status']=='active')} active")
 chain=build_chain(results)
 save_json(CHAIN_PATH,chain)
 print(f"[CRAWL] Fallback chain: {len(chain)} providers")
 _USAGE["last_crawl"]=now()
 elapsed=time.time()-t0
 print(f"[CRAWL] Done in {elapsed:.1f}s")
 return {"discovered":sum(len(v) for v in discovered.values()),"validated":len(results),"active":sum(1 for r in results if r["status"]=="active"),"chain_length":len(chain),"elapsed_s":round(elapsed,1)}

# ═══ ENDPOINTS ═══

@app.get("/")
async def root():
 return HTMLResponse("""<!DOCTYPE html><html><head><meta charset=utf-8><title>FreeKey Agent</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{background:#0a0a0a;color:#e5e5e5;font-family:monospace;padding:2rem}h1{color:#f97316;margin-bottom:1rem}.card{background:#111;border:1px solid #333;border-radius:8px;padding:1rem;margin-bottom:1rem}.glyph{font-size:1.5rem}.active{color:#10b981}.expired{color:#ef4444}.rate_limited{color:#f59e0b}.invalid{color:#71717a}table{width:100%;border-collapse:collapse}td,th{padding:6px 12px;text-align:left;border-bottom:1px solid #222}th{color:#888;font-size:12px;text-transform:uppercase}.btn{background:#f97316;color:#000;border:none;padding:8px 16px;border-radius:4px;cursor:pointer;font-family:monospace;font-weight:bold}a{color:#f97316}</style>
</head><body><h1>◉ FreeKey Agent</h1><p style=color:#888;margin-bottom:1rem>Autonomous API key discovery, validation & serving</p>
<div class=card><h3 style=color:#888;font-size:12px>ENDPOINTS</h3><table><tr><th>Method</th><th>Path</th><th>Description</th></tr>
<tr><td>GET</td><td><a href=/crawl>/crawl</a></td><td>Crawl GitHub + local for free keys</td></tr>
<tr><td>GET</td><td><a href=/keys>/keys</a></td><td>All validated keys with status</td></tr>
<tr><td>GET</td><td><a href=/chain>/chain</a></td><td>Ranked fallback chain</td></tr>
<tr><td>GET</td><td><a href=/health>/health</a></td><td>Live provider status board</td></tr>
<tr><td>GET</td><td><a href=/usage>/usage</a></td><td>Request tracking</td></tr>
<tr><td>POST</td><td>/chat</td><td>OpenAI-compatible proxy (auto-routes to best key)</td></tr>
<tr><td>POST</td><td>/v1/chat/completions</td><td>Drop-in OpenAI replacement</td></tr>
</table></div>
<div class=card><button class=btn onclick="fetch('/crawl').then(r=>r.json()).then(d=>{alert('Crawled: '+d.active+' active keys found')})">⚡ CRAWL NOW</button></div>
<div class=card><h3 style=color:#888;font-size:12px>STATUS</h3><div id=status>Loading...</div></div>
<script>fetch('/health').then(r=>r.json()).then(d=>{document.getElementById('status').innerHTML='<table>'+d.providers.map(p=>'<tr><td class='+p.status+'>'+p.glyph+'</td><td>'+p.provider+'</td><td>'+p.status+'</td><td>'+p.latency_ms+'ms</td><td>score:'+p.score+'</td></tr>').join('')+'</table>'})</script>
</body></html>""")

@app.get("/crawl")
async def crawl():
 """Trigger full crawl: discover → validate → rank → save."""
 result=run_crawl()
 return result

@app.get("/keys")
async def keys():
 """All validated keys with status."""
 r=load_json(REGISTRY_PATH)
 return {"keys":r,"total":len(r),"active":sum(1 for x in r if x.get("status")=="active")}

@app.get("/chain")
async def chain():
 """Ranked fallback chain."""
 return {"chain":load_json(CHAIN_PATH)}

@app.get("/health")
async def health():
 """Live provider status board."""
 r=load_json(REGISTRY_PATH)
 GLYPH={"active":"◉","expired":"⟁","rate_limited":"⧖","invalid":"✕","loading":"◌","untested":"◌"}
 providers=[]
 for x in r:
  s=x.get("status","unknown")
  providers.append({"provider":x["provider"],"status":s,"glyph":GLYPH.get(s,"◌"),"latency_ms":x.get("latency_ms",0),"score":x.get("score",0)})
 return {"providers":providers,"summary":{"active":sum(1 for p in providers if p["status"]=="active"),"total":len(providers)},"last_crawl":_USAGE.get("last_crawl")}

@app.get("/usage")
async def usage():
 return _USAGE

class ChatRequest(BaseModel):
 model:str="auto"; messages:list=[]; prompt:str=""; max_tokens:int=500; temperature:float=0.3

def _do_chat(messages,model,max_tokens,temperature):
 """Try each provider in chain until one works."""
 chain=load_json(CHAIN_PATH)
 if not chain: return {"error":"No active keys. GET /crawl first."}
 errors=[]
 for entry in chain:
  prov=entry["provider"]; endpoint=entry["endpoint"]; use_model=model if model!="auto" else entry["model"]
  # Get full key from discovered
  discovered=load_json(DISCOVERED_PATH)
  keys_list=discovered.get(prov,[])
  if not isinstance(keys_list,list): keys_list=[keys_list]
  if not keys_list: continue
  key=keys_list[0]
  if not key: continue
  try:
   body=json.dumps({"model":use_model,"messages":messages,"max_tokens":max_tokens,"temperature":temperature}).encode()
   headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"}
   req=urllib.request.Request(endpoint,data=body,headers=headers,method="POST")
   resp=urllib.request.urlopen(req,timeout=20)
   data=json.loads(resp.read())
   _USAGE["total"]+=1
   _USAGE["per_provider"][prov]=_USAGE["per_provider"].get(prov,0)+1
   return {"provider":prov,"model":use_model,"response":data["choices"][0]["message"]["content"],"usage":_USAGE}
  except Exception as e:
   errors.append({"provider":prov,"error":str(e)[:100]}); continue
 _USAGE["fallbacks"]+=1
 return {"error":"All providers failed","errors":errors}

@app.post("/chat")
async def chat(req:ChatRequest):
 """OpenAI-compatible proxy. Auto-routes to best available key."""
 msgs=req.messages if req.messages else [{"role":"user","content":req.prompt}]
 return _do_chat(msgs,req.model,req.max_tokens,req.temperature)

@app.post("/v1/chat/completions")
async def openai_compat(req:ChatRequest):
 """Drop-in OpenAI replacement endpoint."""
 msgs=req.messages if req.messages else [{"role":"user","content":req.prompt}]
 result=_do_chat(msgs,req.model,req.max_tokens,req.temperature)
 if "error" in result: return JSONResponse(status_code=503,content=result)
 # Return in OpenAI format
 return {"id":f"freekey-{int(time.time())}","object":"chat.completion","model":result["model"],"choices":[{"index":0,"message":{"role":"assistant","content":result["response"]},"finish_reason":"stop"}],"provider":result["provider"]}

@app.on_event("startup")
async def startup():
 """Auto-crawl on startup."""
 print("[STARTUP] Auto-crawling for free API keys...")
 try: run_crawl()
 except Exception as e: print(f"[STARTUP] Crawl failed: {e}")

if __name__=="__main__":
 import uvicorn; uvicorn.run(app,host="0.0.0.0",port=7860)
