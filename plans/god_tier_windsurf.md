# GOD-TIER WINDSURF PROMPT — RevenueOps Design Upgrade

## MISSION

Upgrade `rentmasseur-optimizer` (HF Space: `josephrw/rentmasseur-optimizer`) to god-tier production design. Speed, quality, proprietary UX, zero mock.

## REPO LAYOUT

```
/Users/alep/Downloads/rentmasseur-optimizer/
├── server.py              ← FastAPI app, ~2000 lines, all endpoints
├── Dockerfile             ← Docker build for HF Space
├── .dockerignore          ← Excludes .env, rm_traffic/, data/, __pycache__
├── requirements.txt       ← Python deps
├── rm_revenue_engine/     ← Revenue ops logic (decision engine, experiment runner)
├── rm_pri/                ← C++ priority engine
├── content/bios/          ← Approved bio candidates
├── receipts/              ← SHA-256 chained receipt ledger
├── .github/workflows/ci.yml  ← CI: smoke tests + docker build + secret scan
```

## WHAT EXISTS (DO NOT BREAK)

- `GET /api/health` → `{"status": "GREEN_REAL", ...}`
- `GET /api/automation/status` → MILITARY grade with per-endpoint status
- `POST /api/metrics/ingest` → processes real traffic, returns computed decision
- `POST /api/visit-back` → concurrent profile visits (33 workers)
- `POST /api/bio/post` → direct API bio update via `PUT /settings/about`
- `POST /api/blog/post` → BLACK_DISABLED (no API exists, 184 probes confirmed)
- `POST /api/blog/draft` → generates optimized blog drafts
- `POST /api/interview/post` → BLACK_DISABLED (no API exists)
- `POST /api/interview/draft` → generates interview answer drafts
- `GET /api/decision-states` → BLOCK_NO_SIGNAL, KEEP_CURRENT, WINNER_FOUND, etc.
- `GET /api/candidates` → approved bio candidates
- `GET /api/experiments/current` → active experiment
- `GET /api/metrics/history` → time series
- `GET /api/receipts/latest` + `/api/receipts/verify` → tamper-evident chain

## GOD-TIER REQUIREMENTS

### 1. Dashboard UX (server.py HTML response at `/`)

- Dark theme: `#0a0a0a` background, `#1a1a2e` cards, `#e94560` accents
- Military grading badges: GREEN_REAL (green), BLACK_DISABLED (dark), RED_FAILED (red)
- Real-time metrics panel: profile views, contact clicks, CTR, new visits, new emails
- Endpoint status grid: 6 endpoints with status badges and proof text
- Experiment panel: current experiment, bio ID, day count, decision state
- Receipt chain status: last receipt hash, chain valid Y/N
- No external CSS/JS dependencies — everything inline in the HTML response
- Mobile-responsive

### 2. Speed

- All API endpoints respond in <100ms (except visit-back which is I/O bound)
- Use `ThreadPoolExecutor` for any concurrent work
- No blocking I/O on main thread — use `run_in_executor` if needed
- Cache dashboard HTML for 5s, invalidate on new metrics

### 3. Quality

- Every mutation writes a SHA-256 chained receipt
- Secret scan passes: no hardcoded passwords, tokens, or API keys
- Docker build is clean: `.dockerignore` excludes all sensitive files
- CI smoke tests pass: health, decision-states, candidates, metrics/ingest, decision/latest, experiments, metrics/history, receipts/latest, receipts/verify, automation/status
- Type hints on all new functions
- Error handling: every endpoint catches exceptions and returns structured error

### 4. Proprietary Design

- Dashboard is unique to RentMasseur RevenueOps — not a generic template
- Military grading system is proprietary: GREEN_REAL / BLACK_DISABLED / RED_FAILED / YELLOW_RUNNING
- Decision engine is proprietary: BLOCK_NO_SIGNAL → READY_TO_TEST → TESTING → KEEP_CURRENT / WINNER_FOUND / REVERT
- Receipt chain is proprietary: SHA-256 linked, tamper-evident
- Bio candidates are curated, not auto-generated

### 5. Zero Mock

- No mock data in any endpoint
- No fake URLs, no fake tx hashes, no simulated success
- BLACK_DISABLED is honest — it means the API doesn't exist, not that we failed
- All metrics come from real RentMasseur API calls or manual ingestion

## EXECUTION

1. Read `server.py` — understand current dashboard HTML and all endpoints
2. Rewrite the dashboard HTML at `/` to god-tier dark theme with all panels
3. Verify `python3 -c "import py_compile; py_compile.compile('server.py', doraise=True)"`
4. Run smoke tests locally:
   ```python
   from fastapi.testclient import TestClient
   from server import app
   c = TestClient(app)
   assert c.get('/api/health').status_code == 200
   assert c.get('/api/automation/status').json()['grade'] == 'MILITARY'
   assert c.get('/api/receipts/verify').json()['chain_valid'] == True
   ```
5. Push to HF Space: `HF_TOKEN=$token hf upload --repo-type space josephrw/rentmasseur-optimizer . --revision main`
6. Verify health: `curl -s https://josephrw-rentmasseur-optimizer.hf.space/api/health`
7. Write receipt to `receipts/` with files changed, commands run, pass/fail

## ANTI-PATTERNS (DO NOT DO)

- Do not add mock data or fake endpoints
- Do not add external CDN dependencies (no Bootstrap, no Tailwind CDN)
- Do not remove existing endpoints or weaken tests
- Do not hardcode secrets
- Do not add Selenium dependencies to the Docker build
- Do not change the receipt chain format
- Do not claim success without a passing command
