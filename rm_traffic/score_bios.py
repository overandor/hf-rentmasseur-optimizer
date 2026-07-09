import json, re, requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

h = {"User-Agent": "Mozilla/5.0"}

def fv(u):
    try:
        r = requests.get(f"https://rentmasseur.com/{u}", headers=h, timeout=10)
        if r.status_code != 200:
            return 0, "", 0
        m = re.search(r'Member Since:</div><div class="value">([^<]+)</div>', r.text)
        ms = m.group(1).strip() if m else ""
        vs = [int(v) for v in re.findall(r'"visits":(\d+)', r.text) if v != "0"]
        v = max(vs) if vs else 0
        d = 0
        if ms:
            try:
                d = max(1, (datetime.now() - datetime.strptime(ms, "%b %d, %Y")).days)
            except:
                pass
        return v, ms, d
    except:
        return 0, "", 0

bios = [json.loads(l) for l in open("rm_traffic/data/real_bios.jsonl")]
us = [b["username"] for b in bios]
print(f"Fetching {len(us)} profiles...")
res = dict(zip(us, ThreadPoolExecutor(max_workers=10).map(fv, us)))

for b in bios:
    v, ms, d = res.get(b["username"], (0, "", 0))
    b["visits"] = v
    b["member_since"] = ms
    b["days_online"] = d
    b["views_per_day"] = v / d if d > 0 else 0

# Save with views
out = Path("rm_traffic/data/real_bios_with_views.jsonl")
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, "w") as f:
    for b in bios:
        f.write(json.dumps(b, default=str) + "\n")

# Rank
bios.sort(key=lambda b: b.get("views_per_day", 0), reverse=True)

print(f"\n{'#':>3} {'Username':<18} {'City':<14} {'Visits':>7} {'Days':>5} {'V/Day':>7} {'R':>2} {'Rev':>3}")
print("-" * 70)
for i, b in enumerate(bios):
    r = float(b.get("ratingAverage", 0) or 0)
    print(f"{i+1:>3} {b['username']:<18} {b['city']:<14} {b['visits']:>7} {b['days_online']:>5} {b['views_per_day']:>7.1f} {r:>2} {b.get('reviewsCount',0):>3}")

# Save ranked report
ranked_path = Path("rm_traffic/data/real_bios_ranked.txt")
with open(ranked_path, "w") as f:
    for i, b in enumerate(bios):
        r = float(b.get("ratingAverage", 0) or 0)
        vpd = b.get("views_per_day", 0)
        f.write(f"#{i+1} | {b['username']} | {b['city']} | visits={b['visits']} | days={b['days_online']} | views/day={vpd:.1f} | rating={r} | reviews={b.get('reviewsCount',0)}\n")
        f.write(f"  Headline: {b['headline']}\n")
        desc = b["description"].replace("\n", " | ")[:500]
        f.write(f"  Desc: {desc}\n")
        f.write(f"  Services: {b.get('services', [])}\n")
        f.write(f"  Member since: {b.get('member_since', 'N/A')}\n")
        f.write(f"  Gold: {b.get('isGold', 0)} | Avail: {b.get('isAvailable', 0)} | Certified: {b.get('isCertified', 0)}\n\n")

print(f"\nSaved to {out} and {ranked_path}")
