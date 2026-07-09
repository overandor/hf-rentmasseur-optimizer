import json

bios = [json.loads(l) for l in open("rm_traffic/data/real_bios_with_views.jsonl")]
bios.sort(key=lambda b: b.get("views_per_day", 0), reverse=True)

print("=" * 80)
print("TOP 15 BIOS BY VIEWS/DAY")
print("=" * 80)
for i, b in enumerate(bios[:15]):
    r = float(b.get("ratingAverage", 0) or 0)
    vpd = b.get("views_per_day", 0)
    print(f"\n#{i+1} {b['username']} | {b['city']} | {vpd:.1f} v/day | {b['visits']} visits | R={r} Rev={b['reviewsCount']}")
    print(f"  HEADLINE: {b['headline']}")
    print(f"  SINCE: {b['member_since']} ({b['days_online']} days)")
    print(f"  SERVICES: {b.get('services', [])}")
    desc = b["description"].replace("\n", " ")
    print(f"  DESC: {desc[:500]}")

print("\n" + "=" * 80)
print("BOTTOM 5")
print("=" * 80)
for i, b in enumerate(bios[-5:]):
    r = float(b.get("ratingAverage", 0) or 0)
    vpd = b.get("views_per_day", 0)
    rank = len(bios) - 4 + i
    print(f"\n#{rank} {b['username']} | {vpd:.1f} v/day | {b['visits']} visits | R={r} Rev={b['reviewsCount']}")
    print(f"  HEADLINE: {b['headline']}")
    desc = b["description"].replace("\n", " ")
    print(f"  DESC: {desc[:300]}")

# Pattern analysis
print("\n" + "=" * 80)
print("PATTERN ANALYSIS")
print("=" * 80)

top10 = bios[:10]
bot10 = bios[-10:]

def avg(lst):
    return sum(lst) / len(lst) if lst else 0

# Headline length
hl_top = avg([len(b["headline"]) for b in top10])
hl_bot = avg([len(b["headline"]) for b in bot10])
print(f"Avg headline length: TOP={hl_top:.0f} chars vs BOT={hl_bot:.0f} chars")

# Description length
dl_top = avg([len(b["description"]) for b in top10])
dl_bot = avg([len(b["description"]) for b in bot10])
print(f"Avg desc length: TOP={dl_top:.0f} chars vs BOT={dl_bot:.0f} chars")

# Emoji usage
import re
emoji_top = avg([len(re.findall(r'[\U0001F000-\U0001FFFF]|[\u2600-\u27BF]', b["description"])) for b in top10])
emoji_bot = avg([len(re.findall(r'[\U0001F000-\U0001FFFF]|[\u2600-\u27BF]', b["description"])) for b in bot10])
print(f"Avg emoji count: TOP={emoji_top:.1f} vs BOT={emoji_bot:.1f}")

# Price mentions
price_top = sum([1 for b in top10 if re.search(r'\$\d+', b["description"])])
price_bot = sum([1 for b in bot10 if re.search(r'\$\d+', b["description"])])
print(f"Mentions price: TOP={price_top}/10 vs BOT={price_bot}/10")

# "Available now" / urgency
urg_top = sum([1 for b in top10 if re.search(r'available|now|today|text|call', b["description"], re.I)])
urg_bot = sum([1 for b in bot10 if re.search(r'available|now|today|text|call', b["description"], re.I)])
print(f"Urgency/CTA: TOP={urg_top}/10 vs BOT={urg_bot}/10")

# Services count
svc_top = avg([len(b.get("services") or []) for b in top10])
svc_bot = avg([len(b.get("services") or []) for b in bot10])
print(f"Avg services listed: TOP={svc_top:.1f} vs BOT={svc_bot:.1f}")

# Certified
cert_top = sum([1 for b in top10 if b.get("isCertified")])
cert_bot = sum([1 for b in bot10 if b.get("isCertified")])
print(f"Certified: TOP={cert_top}/10 vs BOT={cert_bot}/10")

# Gold
gold_top = sum([1 for b in top10 if b.get("isGold")])
gold_bot = sum([1 for b in bot10 if b.get("isGold")])
print(f"Gold: TOP={gold_top}/10 vs BOT={gold_bot}/10")

# Days online
days_top = avg([b.get("days_online", 0) for b in top10])
days_bot = avg([b.get("days_online", 0) for b in bot10])
print(f"Avg days online: TOP={days_top:.0f} vs BOT={days_bot:.0f}")
