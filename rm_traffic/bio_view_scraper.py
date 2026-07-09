"""
Scrape real bios with view counts and member-since dates.
Calculates views/day for ranking.
"""

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import requests

from .api_client import RentMasseurAPI
from .bio_scraper import CITIES, extract_bios_from_results, search_city

log = logging.getLogger("profileops.view_scraper")

OUTPUT_PATH = Path(__file__).parent / "data" / "real_bios_with_views.jsonl"
RANKED_PATH = Path(__file__).parent / "data" / "real_bios_ranked.txt"

WEB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}


def parse_member_since(text: str) -> str:
    """Extract Member Since date from profile page HTML."""
    match = re.search(r'Member Since:</div><div class="value">([^<]+)</div>', text)
    return match.group(1).strip() if match else ""


def parse_visits(text: str) -> int:
    """Extract visits count from profile page HTML."""
    matches = re.findall(r'"visits":(\d+)', text)
    # Filter out 0 (own profile stat), take the max
    vals = [int(v) for v in matches if v != "0"]
    return max(vals) if vals else 0


def days_since(date_str: str) -> int:
    """Calculate days since a date string like 'Mar 25, 2014'."""
    if not date_str:
        return 0
    try:
        d = datetime.strptime(date_str, "%b %d, %Y")
        return max(1, (datetime.now(timezone.utc).replace(tzinfo=None) - d).days)
    except ValueError:
        return 0


def fetch_profile_views(username: str, delay: float = 0.3) -> Dict:
    """Fetch view count and member-since from web profile page."""
    try:
        url = f"https://rentmasseur.com/{username}"
        r = requests.get(url, headers=WEB_HEADERS, timeout=15)
        if r.status_code != 200:
            return {"visits": 0, "member_since": "", "days_online": 0}
        member_since = parse_member_since(r.text)
        visits = parse_visits(r.text)
        days = days_since(member_since)
        time.sleep(delay)
        return {"visits": visits, "member_since": member_since, "days_online": days}
    except Exception as e:
        log.error("Error fetching %s: %s", username, e)
        return {"visits": 0, "member_since": "", "days_online": 0}


def scrape_with_views(api: RentMasseurAPI, max_pages: int = 10, delay: float = 0.5,
                      fetch_views: bool = True) -> List[Dict]:
    """Scrape all bios and fetch view counts."""
    all_bios = []
    seen_ids = set()

    for city in CITIES:
        log.info("Scraping %s...", city)
        for page in range(1, max_pages + 1):
            try:
                results = search_city(api, city, page)
                bios = extract_bios_from_results(results, city)
                if not bios:
                    break
                new_count = 0
                for bio in bios:
                    if bio["id"] and bio["id"] not in seen_ids:
                        seen_ids.add(bio["id"])
                        if fetch_views and bio["username"]:
                            views = fetch_profile_views(bio["username"], delay=0.3)
                            bio["visits"] = views["visits"]
                            bio["member_since"] = views["member_since"]
                            bio["days_online"] = views["days_online"]
                            bio["views_per_day"] = (
                                views["visits"] / views["days_online"]
                                if views["days_online"] > 0 else 0
                            )
                        else:
                            bio["visits"] = 0
                            bio["member_since"] = ""
                            bio["days_online"] = 0
                            bio["views_per_day"] = 0
                        all_bios.append(bio)
                        new_count += 1
                log.info("  %s p%d: %d bios (%d new, total %d)", city, page, len(bios), new_count, len(all_bios))
                if new_count == 0:
                    break
                time.sleep(delay)
            except Exception as e:
                log.error("  Error on %s page %d: %s", city, page, e)
                break

    log.info("Scraped %d unique bios", len(all_bios))
    return all_bios


def rank_by_views_per_day(bios: List[Dict]) -> List[Dict]:
    """Rank bios by views per day online."""
    return sorted(bios, key=lambda b: b.get("views_per_day", 0), reverse=True)


def save_ranked_report(bios: List[Dict], path: Path = RANKED_PATH):
    """Save ranked report sorted by views/day."""
    ranked = rank_by_views_per_day(bios)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for i, b in enumerate(ranked):
            try:
                rating = float(b.get("ratingAverage", 0) or 0)
            except (ValueError, TypeError):
                rating = 0
            reviews = b.get("reviewsCount", 0) or 0
            visits = b.get("visits", 0)
            days = b.get("days_online", 0)
            vpd = b.get("views_per_day", 0)
            f.write(f"#{i+1} | {b['username']} | {b['city']} | visits={visits} | days={days} | views/day={vpd:.1f} | ⭐{rating} | {reviews} reviews\n")
            f.write(f"  Headline: {b['headline']}\n")
            desc = b["description"].replace("\n", " | ")[:500]
            f.write(f"  Desc: {desc}\n")
            f.write(f"  Services: {b.get('services', [])}\n")
            f.write(f"  Member since: {b.get('member_since', 'N/A')}\n")
            f.write(f"  Gold: {b.get('isGold', 0)} | Avail: {b.get('isAvailable', 0)} | Certified: {b.get('isCertified', 0)}\n")
            f.write("\n")
    log.info("Ranked report saved to %s", path)
    return path


def save_bios(bios: List[Dict], path: Path = OUTPUT_PATH):
    """Save bios to JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for bio in bios:
            f.write(json.dumps(bio, default=str) + "\n")
    log.info("Saved %d bios to %s", len(bios), path)


def scrape_all_with_views(api: RentMasseurAPI, max_pages: int = 10, delay: float = 0.5) -> int:
    """Full scrape with view counts and ranking."""
    bios = scrape_with_views(api, max_pages=max_pages, delay=delay, fetch_views=True)
    save_bios(bios)
    save_ranked_report(bios)
    return len(bios)
