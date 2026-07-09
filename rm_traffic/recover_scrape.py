import json, time, re, requests
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from rm_traffic.api_client import RentMasseurAPI
from rm_traffic.bio_scraper import CITIES, extract_bios_from_results

OUT = Path("rm_traffic/data/real_bios_with_views.jsonl")
RANKED = Path("rm_traffic/data/real_bios_ranked.txt")
RAW = Path("rm_traffic/data/real_bios_raw_deep.jsonl")

api = RentMasseurAPI()
api.login("karpathianwolf", "os.environ.get("RM_PASSWORD", "")")

seen = set()
bios = []
print(f"Searching {len(CITIES)} cities serially...")
for city in CITIES:
    city_count = 0
    for page in range(1, 11):
        try:
            results = api.search(city=city, page=page)
            page_bios = extract_bios_from_results(results, city)
            if not page_bios:
                break
            new_count = 0
            for b in page_bios:
                uid = b.get("id") or b.get("username")
                if uid and uid not in seen:
                    seen.add(uid)
                    bios.append(b)
                    new_count += 1
            city_count += len(page_bios)
            print(f"{city} p{page}: {len(page_bios)} bios, {new_count} new, total={len(bios)}")
            if new_count == 0 and page > 1:
                break
            time.sleep(0.25)
        except Exception as e:
            print(f"{city} p{page} ERROR: {e}")
            break

print(f"\nSearch complete: {len(bios)} unique real bios")
RAW.parent.mkdir(parents=True, exist_ok=True)
with RAW.open("w") as f:
    for b in bios:
        f.write(json.dumps(b, ensure_ascii=False) + "\n")

headers = {"User-Agent": "Mozilla/5.0"}

def fetch_views(username):
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

print(f"\nFetching public visit counts for {len(bios)} profiles...")
usernames = [b.get("username") for b in bios if b.get("username")]
with ThreadPoolExecutor(max_workers=32) as pool:
    view_map = dict(zip(usernames, pool.map(fetch_views, usernames)))

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
print(f"Saved full scored data: {OUT}")
print(f"Saved ranked text report: {RANKED}")
print("\nTop 25:")
for i, b in enumerate(bios[:25], 1):
    print(
        f"#{i:03d} {b.get('username'):<22} "
        f"{b.get('city'):<18} "
        f"v/day={b.get('views_per_day',0):>8.2f} "
        f"visits={b.get('visits',0):>8} "
        f"reviews={b.get('reviewsCount',0):>4} "
        f"headline={b.get('headline')}"
    )
