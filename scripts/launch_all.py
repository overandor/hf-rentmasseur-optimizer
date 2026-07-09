#!/usr/bin/env python3
"""Launch all 6 tasks simultaneously — 6 independent processes.
Each task runs in its own process with its own session/connection.
Tasks 1-3 use separate Chrome profiles (tiny windows).
Tasks 4-6 use direct API (no browser needed).

Usage:
    python3 scripts/launch_all.py           # fire all 6 at once
    python3 scripts/launch_all.py --wait    # wait for all to finish
"""
import subprocess, sys, os, time, json
from concurrent.futures import ProcessPoolExecutor, as_completed

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPTS_DIR), "data")
os.makedirs(DATA_DIR, exist_ok=True)

TASKS = [
    ("task1_visit_back", os.path.join(SCRIPTS_DIR, "task1_visit_back.py")),
    ("task2_blog_post", os.path.join(SCRIPTS_DIR, "task2_blog_post.py")),
    ("task3_interview_post", os.path.join(SCRIPTS_DIR, "task3_interview_post.py")),
    ("task4_bio_push", os.path.join(SCRIPTS_DIR, "task4_bio_push.py")),
    ("task5_blog_optimize", os.path.join(SCRIPTS_DIR, "task5_blog_optimize.py")),
    ("task6_metrics_ingest", os.path.join(SCRIPTS_DIR, "task6_metrics_ingest.py")),
]

def main():
    wait = "--wait" in sys.argv
    print(f"Launching {len(TASKS)} tasks simultaneously...")
    print(f"  task1: visit-back (Selenium, tiny window @0,0)")
    print(f"  task2: blog-post (Selenium, tiny window @420,0)")
    print(f"  task3: interview-post (Selenium, tiny window @840,0)")
    print(f"  task4: bio-push (direct API)")
    print(f"  task5: blog-optimize (local computation)")
    print(f"  task6: metrics-ingest (direct API -> HF Space)")
    print()

    cwd = os.path.dirname(os.path.dirname(SCRIPTS_DIR))
    t0 = time.time()

    # Launch all 6 as truly independent processes
    procs = []
    for name, script in TASKS:
        p = subprocess.Popen(
            [sys.executable, script],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=cwd,
        )
        procs.append((name, p))
        print(f"  [{name}] PID {p.pid} launched")

    print(f"\nAll {len(procs)} processes launched. Waiting...")

    results = []
    for name, p in procs:
        stdout, stderr = p.communicate(timeout=300)
        elapsed_one = time.time() - t0
        rc = p.returncode
        stdout_s = stdout.decode()[-2000:]
        stderr_s = stderr.decode()[-500:]
        status = "OK" if rc == 0 else f"EXIT {rc}"
        print(f"  [{name}] {status} in {elapsed_one:.1f}s")
        if rc != 0:
            print(f"    stderr: {stderr_s[:200]}")
        results.append({"task": name, "exit_code": rc, "elapsed": round(elapsed_one, 1),
                        "stdout": stdout_s, "stderr": stderr_s})

    elapsed = time.time() - t0
    print(f"\nAll {len(results)} tasks completed in {elapsed:.1f}s")

    summary = {
        "total_tasks": len(results),
        "succeeded": sum(1 for r in results if r["exit_code"] == 0),
        "failed": sum(1 for r in results if r["exit_code"] != 0),
        "elapsed": round(elapsed, 1),
        "results": results,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with open(os.path.join(DATA_DIR, "launch_all_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Summary: {summary['succeeded']}/{summary['total_tasks']} succeeded")

if __name__ == "__main__":
    main()
