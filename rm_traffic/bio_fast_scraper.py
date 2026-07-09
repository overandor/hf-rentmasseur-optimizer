"""
Ultra-fast parallel bio scraper — concurrent city search + concurrent profile view fetch.
"""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import requests

from .api_client import RentMasseurAPI
from .bio_scraper import CITIES, extract_bios_from_results

log = logging.getLogger("profileops.fast_scraper")

OUTPUT_PATH = Path(__file__).parent / "data" / "real_bios_with_views.jsonl"
RANKED_PATH = Path(__file__).parent / "data" / "real_bios_ranked.txt"

WEB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}


def parse_member_since(text: str) -> str:
    match = re.search(r'Member Since:</div><div class="value">([^<]+)</div>', text)
    return match.group(1).strip() if match else ""


def parse_visits(text: str) -> int:
    matches = re.findall(r'"visits":(\d+)', text)
    vals = [int(v) for v in matches if v != "0"]
    return max(vals) if vals else 0


def days_since(date_str: str) -> int:
    if not date_str:
        return 0
    try:
        d = datetime.strptime(date_str, "%b %d, %Y")
        return max(1, (datetime.now(timezone.utc).replace(tzinfo=None) - d).days)
    except ValueError:
        return 0


def fetch_profile_views(username: str) -> Dict:
    try:
        r = requests.get(f"https://rentmasseur.com/{username}", headers=WEB_HEADERS, timeout=10)
        if r.status_code != 200:
            return {"visits": 0, "member_since": "", "days_online": 0}
        member_since = parse_member_since(r.text)
        visits = parse_visits(r.text)
        days = days_since(member_since)
        return {"visits": visits, "member_since": member_since, "days_online": days}
    except Exception:
        return {"visits": 0, "member_since": "", "days_online": 0}


def fetch_views_batch(usernames: List[str], workers: int = 50) -> Dict[str, Dict]:
    """Fetch profile views for many usernames in parallel."""
    results = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_profile_views, u): u for u in usernames}
        for future in as_completed(futures):
            username = futures[future]
            results[username] = future.result()
    return results


def search_city_pages(api: RentMasseurAPI, city: str, max_pages: int) -> List[Dict]:
    """Search all pages of a city."""
    bios = []
    for page in range(1, max_pages + 1):
        try:
            results = api.search(city=city, page=page)
            page_bios = extract_bios_from_results(results, city)
            if not page_bios:
                break
            bios.extend(page_bios)
        except Exception as e:
            log.error("  %s p%d: %s", city, page, e)
            break
    return bios


def scrape_fast(api: RentMasseurAPI, max_pages: int = 10, view_workers: int = 50) -> List[Dict]:
    """Scrape all cities in parallel, then fetch all views in parallel."""
    # Phase 1: Search all cities in parallel
    log.info("Phase 1: Searching %d cities in parallel...", len(CITIES))
    all_bios = []
    seen_ids = set()

    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(search_city_pages, api, city, max_pages): city for city in CITIES}
        for future in as_completed(futures):
            city = futures[future]
            try:
                city_bios = future.result()
                for bio in city_bios:
                    if bio["id"] and bio["id"] not in seen_ids:
                        seen_ids.add(bio["id"])
                        all_bios.append(bio)
                log.info("  %s: %d bios (total %d)", city, len(city_bios), len(all_bios))
            except Exception as e:
                log.error("  %s: %s", city, e)

    log.info("Phase 1 done: %d unique bios", len(all_bios))

    # Phase 2: Fetch all profile views in parallel
    usernames = [b["username"] for b in all_bios if b["username"]]
    log.info("Phase 2: Fetching views for %d profiles with %d workers...", len(usernames), view_workers)
    view_data = fetch_views_batch(usernames, workers=view_workers)

    for bio in all_bios:
        v = view_data.get(bio["username"], {})
        bio["visits"] = v.get("visits", 0)
        bio["member_since"] = v.get("member_since", "")
        bio["days_online"] = v.get("days_online", 0)
        bio["views_per_day"] = bio["visits"] / bio["days_online"] if bio["days_online"] > 0 else 0

    log.info("Phase 2 done")
    return all_bios


def rank_by_views_per_day(bios: List[Dict]) -> List[Dict]:
    return sorted(bios, key=lambda b: b.get("views_per_day", 0), reverse=True)


def save_bios(bios: List[Dict], path: Path = OUTPUT_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for bio in bios:
            f.write(json.dumps(bio, default=str) + "\n")
    log.info("Saved %d bios to %s", len(bios), path)


def save_ranked_report(bios: List[Dict], path: Path = RANKED_PATH):
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


def scrape_all_fast(api: RentMasseurAPI, max_pages: int = 10, view_workers: int = 50) -> int:
    start = time.time()
    bios = scrape_fast(api, max_pages=max_pages, view_workers=view_workers)
    save_bios(bios)
    save_ranked_report(bios)
    elapsed = time.time() - start
    log.info("Done: %d bios in %.1fs", len(bios), elapsed)
    return len(bios)
