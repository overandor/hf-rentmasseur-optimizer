import json, re, time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import requests

RAW = Path("rm_traffic/data/real_bios.jsonl")
OUT = Path("rm_traffic/data/real_bios_with_views.jsonl")
RANKED = Path("rm_traffic/data/real_bios_ranked.txt")

bios = [json.loads(l) for l in RAW.open()]
print(f"Loaded {len(bios)} real bios")

headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

def fetch_views(username):
    if not username:
        return {"visits": 0, "member_since": "", "days_online": 0, "views_per_day": 0}
    try:
        r = requests.get(f"https://rentmasseur.com/{username}", headers=headers, timeout=12)
        if r.status_code != 200:
            return {"visits": 0, "member_since": "", "days_online": 0, "views_per_day": 0}
        member = re.search(r'Member Since:</div><div class="value">([^<]+)</div>', r.text)
        member_since = member.group(1).strip() if member else ""
        visit_values = [int(v) for v in re.findall(r'"visits":(\d+)', r.text) if v != "0"]
        visits = max(visit_values) if visit_values else 0
        days_online = 0
        if member_since:
            try:
                joined = datetime.strptime(member_since, "%b %d, %Y")
                days_online = max(1, (datetime.now() - joined).days)
            except Exception:
                days_online = 0
        views_per_day = visits / days_online if days_online else 0
        return {
            "visits": visits,
            "member_since": member_since,
            "days_online": days_online,
            "views_per_day": views_per_day,
        }
    except Exception:
        return {"visits": 0, "member_since": "", "days_online": 0, "views_per_day": 0}

usernames = [b.get("username") for b in bios]
print(f"Fetching views for {len(usernames)} profiles with 32 workers...")

done = 0
with ThreadPoolExecutor(max_workers=32) as pool:
    results = list(pool.map(fetch_views, usernames))
    view_map = dict(zip(usernames, results))

for b in bios:
    b.update(view_map.get(b.get("username"), {}))

bios.sort(key=lambda x: x.get("views_per_day", 0), reverse=True)

with OUT.open("w") as f:
    for b in bios:
        f.write(json.dumps(b, ensure_ascii=False) + "\n")

with RANKED.open("w") as f:
    for i, b in enumerate(bios, 1):
        desc = (b.get("description") or "").replace("\n", " | ")
        f.write(
            f"#{i} | {b.get('username')} | {b.get('city')} | "
            f"visits={b.get('visits',0)} | days={b.get('days_online',0)} | "
            f"views/day={b.get('views_per_day',0):.2f} | "
            f"rating={b.get('ratingAverage')} | reviews={b.get('reviewsCount')} | "
            f"gold={b.get('isGold')} | available={b.get('isAvailable')}\n"
        )
        f.write(f"HEADLINE: {b.get('headline')}\n")
        f.write(f"DESC: {desc[:1200]}\n")
        f.write(f"SERVICES: {b.get('services')}\n")
        f.write(f"MEMBER SINCE: {b.get('member_since')}\n\n")

print(f"\nDONE: {len(bios)} real bios scored")
print(f"Saved: {OUT}")
print(f"Ranked: {RANKED}")
print(f"\nTop 25:")
for i, b in enumerate(bios[:25], 1):
    print(
        f"#{i:03d} {b.get('username'):<22} "
        f"{b.get('city'):<18} "
        f"v/day={b.get('views_per_day',0):>8.2f} "
        f"visits={b.get('visits',0):>8} "
        f"reviews={b.get('reviewsCount',0):>4} "
        f"headline={b.get('headline')}"
    )
