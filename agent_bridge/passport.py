"""Passport rendering + Groq LLM integration for Agent Bridge."""
import json, os, urllib.request, urllib.error
from typing import Any, Dict, List, Optional

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"]

_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;padding:20px;max-width:960px;margin:0 auto}
h1{font-size:1.6rem;margin-bottom:4px}h2{font-size:1.1rem;margin:28px 0 12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em}
.subtitle{color:#64748b;font-size:.85rem;margin-bottom:20px}
.passport-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:24px}
.stamp{font-size:.7rem;font-weight:700;padding:4px 12px;border-radius:9999px;text-transform:uppercase}
.field-grid{display:grid;grid-template-columns:180px 1fr;background:#1e293b;border-radius:10px;overflow:hidden}
.field-label{padding:12px 16px;font-size:.75rem;color:#64748b;text-transform:uppercase;border-bottom:1px solid #334155}
.field-value{padding:12px 16px;font-size:.85rem;border-bottom:1px solid #334155;word-break:break-word}
.field-value code{background:#334155;padding:2px 6px;border-radius:4px;font-size:.8rem}
.badge{display:inline-block;padding:2px 10px;border-radius:9999px;font-size:.7rem;font-weight:600;color:#fff}
.response-card{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:16px;margin-bottom:12px}
.response-header{display:flex;justify-content:space-between;margin-bottom:8px}
.response-sender{font-weight:600;color:#4a9eff}.response-time{color:#64748b;font-size:.75rem}
.response-content{font-size:.85rem;line-height:1.5;white-space:pre-wrap}
.response-meta{margin-top:8px;font-size:.7rem;color:#64748b}
.step-list{list-style:none}.step-item{padding:12px 16px;border-left:3px solid #334155;margin-bottom:8px;background:#1e293b;border-radius:0 8px 8px 0}
.step-item.current{border-left-color:#4a9eff}.step-item.done{border-left-color:#22c55e;opacity:.6}
.step-num{font-size:.7rem;color:#64748b}.step-agent{font-weight:600}.step-action{color:#94a3b8;font-size:.85rem}
.back-link{margin-bottom:20px}.back-link a{color:#4a9eff;text-decoration:none;font-size:.85rem}
.back-link a:hover{text-decoration:underline}
.actions{margin-top:20px;display:flex;gap:12px;flex-wrap:wrap}
.actions a{background:#334155;padding:8px 16px;border-radius:8px;color:#e2e8f0;text-decoration:none;font-size:.8rem}
.actions a:hover{background:#475569}
.timeline{position:relative;padding-left:24px}.timeline::before{content:'';position:absolute;left:8px;top:0;bottom:0;width:2px;background:#334155}
.timeline-item{position:relative;padding:8px 0 8px 16px;font-size:.8rem}
.timeline-item::before{content:'';position:absolute;left:-20px;top:12px;width:10px;height:10px;border-radius:50%;background:#4a9eff}
.timeline-item.done::before{background:#22c55e}.timeline-item.failed::before{background:#ef4444}
.timeline-time{color:#64748b;font-size:.7rem}
.empty-state{color:#64748b;text-align:center;padding:24px;font-size:.85rem}
.prompt-box{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:16px;margin:12px 0;font-size:.85rem;line-height:1.6;white-space:pre-wrap}
.context-box{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:12px 16px;margin:8px 0;font-size:.8rem;color:#94a3b8}
.llm-box{background:#1a1a2e;border:1px solid #6c5ce7;border-radius:10px;padding:16px;margin:12px 0;font-size:.85rem;line-height:1.6;white-space:pre-wrap}
.llm-label{font-size:.7rem;color:#6c5ce7;text-transform:uppercase;margin-bottom:8px;font-weight:700}
"""


def _ft(v):
    if not v: return '<span style="color:#64748b">—</span>'
    return str(v)[:19].replace("T", " ")


def _fm(v):
    if not v or v == "{}": return '<span style="color:#64748b">—</span>'
    try:
        d = json.loads(v) if isinstance(v, str) else v
        return f'<pre style="font-size:.75rem;color:#94a3b8;white-space:pre-wrap">{json.dumps(d,indent=2)}</pre>'
    except: return f'<code>{v}</code>'


def render_task_passport(task: Dict, responses: List, workflow: Optional[Dict], llm_analysis: str = "") -> str:
    tid = task.get("id", "?")
    status = task.get("status", "?")
    direction = task.get("direction", "?")
    sc = {"pending": "#f59e0b", "claimed": "#4a9eff", "completed": "#22c55e", "failed": "#ef4444"}.get(status, "#999")
    dc = "#4a9eff" if direction == "to_chatgpt" else "#f59e0b"

    rcards = []
    if not responses:
        rcards.append('<div class="empty-state">No responses yet — waiting for agent reply.</div>')
    for r in responses:
        s_col = "#4a9eff" if r.get("sender") == "chatgpt" else "#22c55e"
        rcards.append(f'''<div class="response-card"><div class="response-header">
        <span class="response-sender" style="color:{s_col}">{r.get('sender','?')}</span>
        <span class="response-time">{_ft(r.get("created_at"))}</span></div>
        <div class="response-content">{r.get("content","")}</div>
        <div class="response-meta">ID: {r.get("id","?")} | Status: {r.get("status","?")} | Read: {_ft(r.get("read_at"))}</div></div>''')

    wf_html = ""
    if workflow:
        wid = workflow.get("workflow_id", "?")
        steps = workflow.get("steps", [])
        cur = workflow.get("current_step", 0)
        ws = workflow.get("status", "?")
        wsc = "#22c55e" if ws == "completed" else "#4a9eff" if ws == "active" else "#999"
        si = []
        for i, s in enumerate(steps):
            cls = "done" if i < cur else "current" if i == cur else ""
            si.append(f'<li class="step-item {cls}"><span class="step-num">Step {i}</span> — <span class="step-agent">{s.get("agent","?")}</span>: <span class="step-action">{s.get("action","?")}</span></li>')
        wf_html = f'''<h2>Linked Workflow</h2><div class="field-grid">
        <div class="field-label">Workflow ID</div><div class="field-value"><a href="/workflows/{wid}/passport"><code>{wid}</code></a></div>
        <div class="field-label">Name</div><div class="field-value">{workflow.get("name","?")}</div>
        <div class="field-label">Progress</div><div class="field-value">Step {cur}/{len(steps)}</div>
        <div class="field-label">Status</div><div class="field-value"><span class="badge" style="background:{wsc}">{ws}</span></div></div>
        <h2>Workflow Steps</h2><ul class="step-list">{"".join(si)}</ul>'''

    tl = [f'<div class="timeline-item done"><div class="timeline-time">{_ft(task.get("created_at"))}</div>Task created by {task.get("sender","?")}</div>']
    if task.get("claimed_at"):
        tl.append(f'<div class="timeline-item done"><div class="timeline-time">{_ft(task.get("claimed_at"))}</div>Claimed by {task.get("claimed_by","?")}</div>')
    if status == "completed":
        tl.append(f'<div class="timeline-item done"><div class="timeline-time">{_ft(task.get("updated_at"))}</div>Task completed</div>')
    elif status == "failed":
        tl.append(f'<div class="timeline-item failed"><div class="timeline-time">{_ft(task.get("updated_at"))}</div>Task failed</div>')
    for r in responses:
        tl.append(f'<div class="timeline-item"><div class="timeline-time">{_ft(r.get("created_at"))}</div>Response from {r.get("sender","?")}</div>')

    llm_html = ""
    if llm_analysis:
        llm_html = f'<h2>LLM Analysis (Groq)</h2><div class="llm-box"><div class="llm-label">Groq AI Insight</div>{llm_analysis}</div>'

    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Task Passport — {tid[:20]}</title><style>{_CSS}</style></head><body>
<div class="back-link"><a href="/">&larr; Back to Dashboard</a></div>
<div class="passport-header"><div><h1>Task Passport</h1><div class="subtitle"><code>{tid}</code></div></div>
<div style="display:flex;gap:8px;flex-direction:column;align-items:flex-end">
<span class="stamp" style="background:{sc}">{status}</span><span class="stamp" style="background:{dc}">{direction}</span></div></div>

<h2>Identity</h2><div class="field-grid">
<div class="field-label">Task ID</div><div class="field-value"><code>{tid}</code></div>
<div class="field-label">Direction</div><div class="field-value"><span class="badge" style="background:{dc}">{direction}</span></div>
<div class="field-label">Sender</div><div class="field-value">{task.get("sender","?")}</div>
<div class="field-label">Status</div><div class="field-value"><span class="badge" style="background:{sc}">{status}</span></div>
<div class="field-label">Priority</div><div class="field-value">{task.get("priority","?")}</div>
<div class="field-label">Created</div><div class="field-value">{_ft(task.get("created_at"))}</div>
<div class="field-label">Claimed By</div><div class="field-value">{task.get("claimed_by") or '<span style="color:#64748b">—</span>'}</div>
<div class="field-label">Claimed At</div><div class="field-value">{_ft(task.get("claimed_at"))}</div>
<div class="field-label">Updated</div><div class="field-value">{_ft(task.get("updated_at"))}</div>
<div class="field-label">Workflow</div><div class="field-value">{task.get("workflow_id") or '<span style="color:#64748b">—</span>'}</div>
<div class="field-label">Step Index</div><div class="field-value">{task.get("step_index",0)}</div>
</div>

<h2>Prompt</h2><div class="prompt-box">{task.get("prompt","")}</div>

{"<h2>Context</h2><div class=\"context-box\">" + task.get("context","") + "</div>" if task.get("context") else ""}

<h2>Responses ({len(responses)})</h2>{"".join(rcards)}

{wf_html}

<h2>Timeline</h2><div class="timeline">{"".join(tl)}</div>

{llm_html}

<div class="actions">
<a href="/tasks/{tid}">JSON API</a>
<a href="/tasks/{tid}/analyze">Analyze with Groq</a>
<a href="/">Dashboard</a>
<a href="/docs">API Docs</a>
</div></body></html>'''


def render_workflow_passport(wf: Dict) -> str:
    wid = wf.get("workflow_id", "?")
    steps = wf.get("steps", [])
    cur = wf.get("current_step", 0)
    ws = wf.get("status", "?")
    wsc = "#22c55e" if ws == "completed" else "#4a9eff" if ws == "active" else "#999"
    ctx = wf.get("context", {})

    si = []
    for i, s in enumerate(steps):
        cls = "done" if i < cur else "current" if i == cur else ""
        si.append(f'<li class="step-item {cls}"><span class="step-num">Step {i}</span> — <span class="step-agent">{s.get("agent","?")}</span>: <span class="step-action">{s.get("action","?")}</span></li>')

    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Workflow Passport — {wid[:24]}</title><style>{_CSS}</style></head><body>
<div class="back-link"><a href="/">&larr; Back to Dashboard</a></div>
<div class="passport-header"><div><h1>Workflow Passport</h1><div class="subtitle"><code>{wid}</code></div></div>
<span class="stamp" style="background:{wsc}">{ws}</span></div>

<h2>Identity</h2><div class="field-grid">
<div class="field-label">Workflow ID</div><div class="field-value"><code>{wid}</code></div>
<div class="field-label">Name</div><div class="field-value">{wf.get("name","?")}</div>
<div class="field-label">Status</div><div class="field-value"><span class="badge" style="background:{wsc}">{ws}</span></div>
<div class="field-label">Progress</div><div class="field-value">Step {cur}/{len(steps)}</div>
<div class="field-label">Created</div><div class="field-value">{_ft(wf.get("created_at"))}</div>
<div class="field-label">Updated</div><div class="field-value">{_ft(wf.get("updated_at"))}</div>
</div>

<h2>Steps ({len(steps)})</h2><ul class="step-list">{"".join(si)}</ul>

{"<h2>Context</h2><div class=\"context-box\"><pre style=\"font-size:.8rem\">" + json.dumps(ctx, indent=2) + "</pre></div>" if ctx else ""}

<div class="actions">
<a href="/workflows/{wid}">JSON API</a>
<a href="/workflows/{wid}/advance">Advance Step</a>
<a href="/">Dashboard</a>
</div></body></html>'''


# === Groq LLM Integration ===

def groq_chat(prompt: str, system: str = "", model: str = "llama-3.3-70b-versatile", timeout: int = 30) -> Dict[str, Any]:
    """Send a chat completion to Groq API. Returns response dict."""
    if not GROQ_API_KEY:
        return {"error": "GROQ_API_KEY not set", "hint": "export GROQ_API_KEY=gsk_... or set in .env"}
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body = json.dumps({"model": model, "messages": messages, "temperature": 0.7, "max_tokens": 4096}).encode()
    req = urllib.request.Request(GROQ_URL, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {GROQ_API_KEY}")
    req.add_header("User-Agent", "AgentBridge/0.2.0")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            content = data["choices"][0]["message"]["content"]
            return {
                "success": True,
                "response": content,
                "model": data.get("model", model),
                "usage": data.get("usage", {}),
                "created": data.get("created", 0),
            }
    except urllib.error.HTTPError as e:
        err_body = e.read().decode() if e.fp else ""
        return {"success": False, "error": f"HTTP {e.code}", "detail": err_body[:500]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def groq_analyze_task(task: Dict, responses: List) -> str:
    """Use Groq to analyze a task and its responses. Returns HTML-safe analysis text."""
    prompt = f"""Analyze this agent bridge task and its responses. Provide:
1. Summary of what was requested
2. Assessment of the response quality
3. Any issues or gaps
4. Recommended next steps

Task:
- ID: {task.get('id','?')}
- Direction: {task.get('direction','?')}
- Sender: {task.get('sender','?')}
- Status: {task.get('status','?')}
- Prompt: {task.get('prompt','?')}

Responses ({len(responses)}):
"""
    for r in responses:
        prompt += f"\n[{r.get('sender','?')}]: {r.get('content','')[:500]}"
    if not responses:
        prompt += "\n(no responses yet)"

    result = groq_chat(prompt, system="You are an AI agent bridge analyzer. Be concise and actionable.")
    if result.get("success"):
        return result["response"].replace("<", "&lt;").replace(">", "&gt;")
    return f"Analysis failed: {result.get('error', 'unknown')}"
