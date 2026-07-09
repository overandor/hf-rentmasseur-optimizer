#!/usr/bin/env python3
"""Replace landing page with RevenueOps Control Plane UI"""

f = "/Users/alep/Downloads/MEMBRA::SURFACE=BUILD@LIVE/02_AI_Agents/rentmasseur-extension/cpp_os_server.cpp"
c = open(f).read()

old_start = 'static std::string landing_page() {'
old_end = '</script></body></html>)HTML";}'

# Find the block
start_idx = c.find(old_start)
end_idx = c.find(old_end)
if start_idx == -1 or end_idx == -1:
    print("ERROR: could not find landing_page block")
    exit(1)

end_idx += len(old_end)

new_landing = '''static std::string landing_page() {
    return R"HTML(<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>RentMasseur RevenueOps Control Plane</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'SF Mono',Monaco,Consolas,monospace;background:#0a0b14;color:#e0e0e8;padding:20px}
h1{font-size:24px;font-weight:600;letter-spacing:-0.5px}
h2{font-size:13px;text-transform:uppercase;letter-spacing:1px;color:#6b7280;margin-bottom:12px}
.subtitle{color:#6b7280;font-size:13px;margin-top:4px}
.header{padding:24px 0;border-bottom:1px solid #1e2030;margin-bottom:24px}
.header h1{color:#fff}
.status-bar{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}
.tag{padding:4px 10px;border-radius:4px;font-size:11px;font-weight:600}
.tag-green{background:#0d3320;color:#39ff88;border:1px solid #1a5c3a}
.tag-gray{background:#1a1b2e;color:#6b7280;border:1px solid #2a2b3e}
.tag-red{background:#330d0d;color:#ff5370;border:1px solid #5c1a1a}
.tag-yellow{background:#332b0d;color:#ffd166;border:1px solid #5c4a1a}
.tag-black{background:#0d0d0d;color:#444;border:1px solid #222}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px;margin-top:16px}
.panel{background:#11121f;border:1px solid #1e2030;border-radius:8px;padding:20px;min-height:200px}
.panel pre{white-space:pre-wrap;word-break:break-all;font-size:12px;line-height:1.5;color:#9ca3af;max-height:400px;overflow:auto}
.metric-row{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #1a1b2e;font-size:13px}
.metric-label{color:#6b7280}
.metric-value{color:#e0e0e8;font-weight:600}
.metric-zero{color:#444}
.truth{font-size:12px;color:#ff5370;padding:8px;background:#1a0a0a;border-radius:4px;margin-top:8px}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.btn{padding:8px 14px;border-radius:6px;border:1px solid #2a2b3e;background:#161728;color:#9ca3af;text-decoration:none;font-size:12px;cursor:pointer;transition:all 0.15s}
.btn:hover{border-color:#3a3b4e;color:#fff}
.btn-danger{border-color:#3a1a1a;color:#ff5370}
.btn-danger:hover{background:#1a0a0a}
.btn-ok{border-color:#1a3a2a;color:#39ff88}
.btn-ok:hover{background:#0a1a0a}
.footer{margin-top:32px;padding-top:16px;border-top:1px solid #1e2030;color:#444;font-size:11px;text-align:center}
#daily-proof{font-size:12px;line-height:1.8;color:#9ca3af}
.proof-q{color:#6b7280}
.proof-a{color:#e0e0e8}
</style>
</head>
<body>

<div class="header">
  <h1>RentMasseur RevenueOps Control Plane</h1>
  <p class="subtitle">Mission: one paying client per day, or prove exactly why it failed today.</p>
  <div class="status-bar">
    <span class="tag tag-gray" id="tag-health">HEALTH: checking...</span>
    <span class="tag tag-gray" id="tag-metrics">METRICS: checking...</span>
    <span class="tag tag-gray" id="tag-candidates">CANDIDATES: checking...</span>
    <span class="tag tag-gray" id="tag-decision">DECISION: checking...</span>
    <span class="tag tag-black">AVAILABILITY: BLACK_DISABLED</span>
  </div>
</div>

<div class="grid">

  <div class="panel">
    <h2>Mission Control</h2>
    <div class="metric-row"><span class="metric-label">Today target</span><span class="metric-value">1 paid client</span></div>
    <div class="metric-row"><span class="metric-label">Current status</span><span class="metric-value" id="mission-status">loading...</span></div>
    <div class="metric-row"><span class="metric-label">Prospects today</span><span class="metric-value metric-zero" id="prospects-count">0</span></div>
    <div class="metric-row"><span class="metric-label">Leads active</span><span class="metric-value metric-zero" id="leads-active">0</span></div>
    <div class="metric-row"><span class="metric-label">Bookings confirmed</span><span class="metric-value metric-zero" id="bookings-confirmed">0</span></div>
    <div class="metric-row"><span class="metric-label">Revenue verified</span><span class="metric-value metric-zero">$0</span></div>
    <div class="truth" id="mission-truth">No mock success. No simulation labels. Every number must be backed by a receipt.</div>
  </div>

  <div class="panel">
    <h2>Live Metrics</h2>
    <div id="metrics-panel"><pre>loading...</pre></div>
    <div class="actions">
      <a class="btn" href="/api/funnel/daily">Funnel Daily</a>
      <a class="btn" href="/api/leads">Leads</a>
      <a class="btn btn-ok" href="/api/metrics/ingest" onclick="return false">Ingest (POST)</a>
    </div>
  </div>

  <div class="panel">
    <h2>Candidate Queue</h2>
    <div id="candidates-panel"><pre>loading...</pre></div>
    <div class="actions">
      <a class="btn" href="/api/candidates">Refresh</a>
      <a class="btn" href="/api/bios">Bios</a>
    </div>
  </div>

  <div class="panel">
    <h2>Decision Gate</h2>
    <div id="decision-panel"><pre>loading...</pre></div>
    <div class="actions">
      <a class="btn" href="/api/decision/latest">Latest Decision</a>
      <a class="btn btn-danger" href="/api/run/availability">Availability (BLOCKED)</a>
    </div>
  </div>

  <div class="panel">
    <h2>Job Ledger</h2>
    <div id="jobs-panel"><pre>loading...</pre></div>
    <div class="actions">
      <a class="btn" href="/api/jobs">All Jobs</a>
      <a class="btn" href="/api/receipts">Receipts</a>
      <a class="btn" href="/api/audit/files">File Audit</a>
    </div>
  </div>

  <div class="panel">
    <h2>Revenue Proof</h2>
    <div class="metric-row"><span class="metric-label">Verified revenue</span><span class="metric-value metric-zero">$0</span></div>
    <div class="metric-row"><span class="metric-label">Confirmed bookings</span><span class="metric-value metric-zero">0</span></div>
    <div class="metric-row"><span class="metric-label">Target</span><span class="metric-value">1 client/day</span></div>
    <div class="metric-row"><span class="metric-label">Client probability</span><span class="metric-value metric-zero" id="prob">unverified</span></div>
    <div class="truth">No estimates pretending to be money. Only confirmed bookings count.</div>
  </div>

</div>

<div class="grid">
  <div class="panel" style="min-height:auto">
    <h2>Daily Revenue Proof</h2>
    <div id="daily-proof">
      <span class="proof-q">What did the system observe?</span> <span class="proof-a" id="dp-observe">--</span><br>
      <span class="proof-q">How many prospects existed?</span> <span class="proof-a" id="dp-prospects">--</span><br>
      <span class="proof-q">How many were qualified?</span> <span class="proof-a" id="dp-qualified">--</span><br>
      <span class="proof-q">How many clicked?</span> <span class="proof-a" id="dp-clicked">--</span><br>
      <span class="proof-q">How many messaged?</span> <span class="proof-a" id="dp-messaged">--</span><br>
      <span class="proof-q">How many appointments?</span> <span class="proof-a" id="dp-appts">--</span><br>
      <span class="proof-q">How many paid?</span> <span class="proof-a" id="dp-paid">--</span><br>
      <span class="proof-q">Which experiment was live?</span> <span class="proof-a" id="dp-exp">--</span><br>
      <span class="proof-q">What won?</span> <span class="proof-a" id="dp-won">--</span><br>
      <span class="proof-q">What failed?</span> <span class="proof-a" id="dp-failed">--</span><br>
      <span class="proof-q">Tomorrow next best action?</span> <span class="proof-a" id="dp-next">--</span>
    </div>
  </div>
</div>

<div class="grid">
  <div class="panel" style="min-height:auto">
    <h2>CI/CD Control</h2>
    <div class="actions">
      <a class="btn" href="/api/cicd/list">List Workflows</a>
      <a class="btn" href="/api/cicd/runs">Recent Runs</a>
      <a class="btn btn-ok" href="/api/cicd/trigger/deploy-hf-space.yml">Deploy HF</a>
      <a class="btn" href="/api/cicd/trigger/master-rotator.yml">Master Rotator</a>
    </div>
    <pre id="cicd-panel" style="margin-top:12px">loading...</pre>
  </div>
  <div class="panel" style="min-height:auto">
    <h2>System State</h2>
    <pre id="state">loading...</pre>
  </div>
</div>

<div class="footer">
  RentMasseur RevenueOps Control Plane &middot; No receipt, no reality. No metric, no optimization. No lead, no client claim.
</div>

<script>
function setTag(id, text, cls) {
  const el = document.getElementById(id);
  el.textContent = text;
  el.className = 'tag ' + cls;
}

fetch('/api/health').then(r=>r.json()).then(j=>{
  setTag('tag-health', 'HEALTH: ' + (j.status||'?'), j.status==='ok' ? 'tag-green' : 'tag-red');
}).catch(()=>setTag('tag-health','HEALTH: OFFLINE','tag-red'));

fetch('/api/report').then(r=>r.json()).then(j=>{
  state.textContent = JSON.stringify(j, null, 2);
  const hasMetrics = j.status === 'real_data_present';
  setTag('tag-metrics', 'METRICS: ' + (hasMetrics ? 'REAL' : 'NO_DATA'), hasMetrics ? 'tag-green' : 'tag-gray');
  const hasBios = (j.content_counts?.bios || 0) > 0;
  setTag('tag-candidates', 'CANDIDATES: ' + (hasBios ? j.content_counts.bios : 'NONE'), hasBios ? 'tag-green' : 'tag-gray');
  setTag('tag-decision', 'DECISION: ' + (j.latest_decision?.status || 'NONE'), j.latest_decision?.status === 'accepted' ? 'tag-green' : 'tag-gray');
  document.getElementById('mission-status').textContent = j.status || 'unknown';
  document.getElementById('mission-status').className = 'metric-value' + (j.status?.includes('blocked') ? ' metric-zero' : '');
}).catch(e=>state.textContent=String(e));

fetch('/api/funnel/daily').then(r=>r.json()).then(j=>{
  metricsPanel.innerHTML = '';
  const rows = [
    ['Metric entries', j.metric_entries||0],
    ['Profile views', j.profile_views||0],
    ['Contact clicks', j.contact_clicks||0],
    ['Email clicks', j.email_clicks||0],
    ['Phone clicks', j.phone_clicks||0],
    ['Booking requests', j.booking_requests||0],
    ['Confirmed bookings', j.confirmed_bookings||0],
  ];
  rows.forEach(([k,v])=>{
    const d=document.createElement('div');
    d.className='metric-row';
    d.innerHTML='<span class="metric-label">'+k+'</span><span class="metric-value'+(v===0?' metric-zero':'')+'">'+v+'</span>';
    metricsPanel.appendChild(d);
  });
  if((j.metric_entries||0)===0){
    const t=document.createElement('div');
    t.className='truth';
    t.textContent='NO REAL METRICS. Funnel requires first-party data from extension or manual capture.';
    metricsPanel.appendChild(t);
  }
  document.getElementById('prob').textContent = j.client_probability || 'unverified';
}).catch(e=>metricsPanel.innerHTML='<pre>'+String(e)+'</pre>');

fetch('/api/candidates').then(r=>r.json()).then(j=>{
  candidatesPanel.innerHTML='<pre>'+JSON.stringify(j,null,2)+'</pre>';
}).catch(e=>candidatesPanel.innerHTML='<pre>'+String(e)+'</pre>');

fetch('/api/decision/latest').then(r=>r.json()).then(j=>{
  decisionPanel.innerHTML='<pre>'+JSON.stringify(j,null,2)+'</pre>';
}).catch(e=>decisionPanel.innerHTML='<pre>'+String(e)+'</pre>');

fetch('/api/jobs').then(r=>r.json()).then(j=>{
  const count = j.jobs?.length || 0;
  jobsPanel.innerHTML='<pre>Jobs: '+count+'\\n'+JSON.stringify(j.jobs?.slice(-3),null,2)+'</pre>';
}).catch(e=>jobsPanel.innerHTML='<pre>'+String(e)+'</pre>');

fetch('/api/cicd/runs').then(r=>r.json()).then(j=>{
  const runs = j.workflow_runs||[];
  cicdPanel.textContent = runs.slice(0,5).map(r=>r.name+': '+(r.conclusion||r.status)+' ('+r.created_at+')').join('\\n');
}).catch(e=>cicdPanel.textContent=String(e));
</script>
</body></html>)HTML";
}'''

c = c[:start_idx] + new_landing + c[end_idx:]
open(f, 'w').write(c)
print("Landing page replaced with RevenueOps Control Plane")
