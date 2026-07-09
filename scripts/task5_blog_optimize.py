#!/usr/bin/env python3
"""Task 5: Blog optimization. Independent process.
Generates optimized blog drafts, scores them, saves for review."""
import json, time, os, sys

def main():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from rm_traffic.blog_agent import generate_blog_drafts, save_blog_drafts_to_disk
    from rm_traffic.blog_optimizer import score_blog

    count = int(os.getenv("BLOG_COUNT", "3"))
    print(f"[task5] Generating {count} optimized blog drafts...")
    drafts = generate_blog_drafts(count=count)

    # Score each draft
    for d in drafts:
        s = score_blog(d["title"], d["body"])
        d["score"] = s
        print(f"[task5] {d['title'][:50]}: local_seo={s['local_seo']:.2f} marketing={s['marketing']:.2f} risk={s['risk']:.2f}")

    save_blog_drafts_to_disk(drafts)

    result = {
        "status": "GREEN_REAL",
        "count": len(drafts),
        "drafts": [{"title": d["title"], "body_len": len(d["body"]), "score": d["score"],
                     "hypothesis": d.get("hypothesis", "")} for d in drafts],
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with open("data/task5_blog_optimize.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"[task5] Done: {len(drafts)} drafts generated and scored")

if __name__ == "__main__":
    main()
