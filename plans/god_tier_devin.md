# GOD-TIER DEVIN PROMPT — RevenueOps Speed & Quality Upgrade

## MISSION

Maximize concurrency and speed across all 6 RevenueOps tasks. Each task is a separate script with its own session. All fire simultaneously. No mock. No fake. Military-grade throughput.

## REPO LAYOUT

```
/Users/alep/Downloads/windsurf-smoke/
├── scripts/
│   ├── task1_visit_back.py       ← Selenium, tiny Chrome @0,0
│   ├── task2_blog_post.py        ← Selenium, tiny Chrome @420,0
│   ├── task3_interview_post.py   ← Selenium, tiny Chrome @840,0
│   ├── task4_bio_push.py         ← Direct API (no browser)
│   ├── task5_blog_optimize.py    ← Local computation (no browser)
│   ├── task6_metrics_ingest.py   ← Direct API → HF Space
│   └── launch_all.py             ← Fires all 6 as subprocess.Popen
├── rm_traffic/
│   ├── api_client.py             ← RentMasseurAPI: login, get_mailbox, set_about, etc.
│   ├── blog_agent.py             ← Blog draft generation
│   ├── blog_optimizer.py         ← Blog scoring (local_seo, marketing, risk)
│   └── interview_agent.py        ← Interview draft generation
├── data/                         ← Task output JSON files
├── .github/workflows/ci.yml      ← CI: compile, secret scan, HF health, military grading
```

## WHAT EXISTS (DO NOT BREAK)

- `task4_bio_push.py` — works, pushes bio via `PUT /settings/about`, writes receipt
- `task5_blog_optimize.py` — works, generates 3 scored blog drafts
- `task6_metrics_ingest.py` — works, fetches dashboard stats, posts to HF Space
- `task1_visit_back.py` — Selenium-based, needs Chrome (works locally, not in CI)
- `task2_blog_post.py` — Selenium-based, brute-forces blog editor form
- `task3_interview_post.py` — Selenium-based, brute-forces interview editor form
- `launch_all.py` — fires all 6 via `subprocess.Popen`, collects results

## GOD-TIER SPEED REQUIREMENTS

### 1. Process Isolation

- Each task runs as a separate OS process via `subprocess.Popen`
- Each Selenium task uses its own Chrome profile dir (`/tmp/rm_task1`, `/tmp/rm_task2`, `/tmp/rm_task3`)
- Each API task creates its own `RentMasseurAPI` instance with independent login
- No shared state between tasks
- `launch_all.py` must launch all 6 PIDs within 1 second

### 2. Concurrency Within Tasks

- `task1_visit_back.py`: 33 concurrent workers via `ThreadPoolExecutor`
- `task2_blog_post.py`: single browser (form submission is sequential)
- `task3_interview_post.py`: single browser (form submission is sequential)
- `task4_bio_push.py`: single API call (fastest possible)
- `task5_blog_optimize.py`: parallel draft generation if possible
- `task6_metrics_ingest.py`: parallel API calls for dashboard + stats + keeponline

### 3. Latency Targets

| Task | Target | Method |
|------|--------|--------|
| task1 visit-back | <3s for 48 profiles | 33 concurrent HTTP GET |
| task2 blog-post | <30s | Selenium form fill + network capture |
| task3 interview-post | <30s | Selenium form fill + network capture |
| task4 bio-push | <1s | Single PUT /settings/about |
| task5 blog-optimize | <5s | Local computation, no I/O |
| task6 metrics-ingest | <2s | Parallel API calls + HF POST |

### 4. Receipt & Evidence

- Every task writes a JSON file to `data/taskN_*.json` with:
  - `status`: GREEN_REAL / RED_FAILED / BLACK_DISABLED
  - `ts`: ISO timestamp
  - Task-specific fields (visited count, bio headline, draft titles, metrics packet)
- `launch_all.py` writes `data/launch_all_summary.json` with:
  - `total_tasks`, `succeeded`, `failed`, `elapsed`, per-task results

### 5. Error Handling

- Each task catches its own exceptions and exits with code 1
- `launch_all.py` captures stdout/stderr per task, reports failures
- No task crash should affect another task
- Selenium tasks must `driver.quit()` in a `finally` block

## EXECUTION

1. Read all 6 scripts in `scripts/` — understand current state
2. Fix any import issues (each script must have `sys.path.insert(0, parent_dir)`)
3. Verify each script compiles: `python3 -m py_compile scripts/task*.py`
4. Test tasks 4, 5, 6 individually (they don't need Chrome):
   ```bash
   python3 scripts/task4_bio_push.py
   python3 scripts/task5_blog_optimize.py
   python3 scripts/task6_metrics_ingest.py
   ```
5. Test `launch_all.py`:
   ```bash
   python3 scripts/launch_all.py --wait
   ```
6. Verify `data/launch_all_summary.json` has `succeeded >= 3` (tasks 4, 5, 6)
7. Write receipt to `receipts/` with files changed, commands run, pass/fail

## ANTI-PATTERNS (DO NOT DO)

- Do not run tasks in a single process or thread — they must be separate processes
- Do not share Chrome profiles between tasks
- Do not share API sessions between tasks
- Do not add mock data or fake success
- Do not block `launch_all.py` on any single task — all must launch simultaneously
- Do not use `ProcessPoolExecutor` — it corrupts subprocess environment on macOS
- Do not claim success without `data/launch_all_summary.json` showing real results
