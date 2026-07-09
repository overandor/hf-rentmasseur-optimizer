
#!/usr/bin/env python3
"""Probe free/keyless LLM endpoints."""
import urllib.request,json,time

endpoints=[
 ('https://api.freetheai.xyz/v1/chat/completions','gpt-4o-mini',''),
 ('https://api.llm7.io/v1/chat/completions','gpt-4o-mini',''),
 ('https://api.chutes.ai/v1/chat/completions','llama-3.3-70b',''),
 ('https://api.aionlabs.ai/v1/chat/completions','llama-3.3-70b',''),
 ('https://api.sambanova.ai/v1/chat/completions','Meta-Llama-3.1-405B-Instruct',''),
 ('https://api.cerebras.ai/v1/chat/completions','llama-3.3-70b',''),
 ('https://router.huggingface.co/v1/chat/completions','meta-llama/Llama-3.3-70B-Instruct','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'),
 ('https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions','llama-3.3-70b',''),
 ('https://inference.api.nscale.com/v1/chat/completions','llama-3.3-70b',''),
 ('https://api-inference.modelscope.cn/v1/chat/completions','llama-3.3-70b',''),
 ('https://api.studio.nebius.com/v1/chat/completions','llama-3.3-70b',''),
 ('https://api.siliconflow.cn/v1/chat/completions','deepseek-ai/DeepSeek-V3',''),
 ('https://ai.sumopod.com/v1/chat/completions','llama-3.3-70b',''),
 ('https://api.deepinfra.com/v1/chat/completions','meta-llama/Llama-3.3-70B-Instruct-Turbo',''),
]

for url,model,key in endpoints:
    body=json.dumps({'model':model,'messages':[{'role':'user','content':'Say hi'}],'max_tokens':10}).encode()
    headers={'Content-Type':'application/json'}
    if key: headers['Authorization']=f'Bearer {key}'
    t0=time.time()
    try:
        req=urllib.request.Request(url,data=body,headers=headers,method='POST')
        resp=urllib.request.urlopen(req,timeout=12)
        dt=int((time.time()-t0)*1000)
        d=json.loads(resp.read())
        txt=d.get('choices',[{}])[0].get('message',{}).get('content','')[:40]
        print(f'OK  {url:55s} {dt:5d}ms {txt}')
    except urllib.error.HTTPError as e:
        dt=int((time.time()-t0)*1000)
        err=e.read().decode()[:80]
        print(f'{e.code:3d} {url:55s} {dt:5d}ms {err}')
    except Exception as e:
        print(f'ERR {url:55s} {str(e)[:60]}')
