"""
Scrape real bios from RentMasseur search results.
Uses the verified POST /api/v1/search endpoint.
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List

from .api_client import RentMasseurAPI

log = logging.getLogger("profileops.scraper")

CITIES = [
    # NY
    "manhattan-ny", "brooklyn-ny", "queens-ny", "bronx-ny", "staten-island-ny",
    "long-island-ny", "rochester-ny", "buffalo-ny", "albany-ny", "syracuse-ny",
    # NJ
    "jersey-city-nj", "hoboken-nj", "newark-nj", "atlantic-city-nj", "princeton-nj",
    # MA
    "boston-ma", "cambridge-ma", "provincetown-ma", "springfield-ma", "worcester-ma",
    # PA
    "philadelphia-pa", "pittsburgh-pa", "allentown-pa",
    # IL
    "chicago-il", "springfield-il",
    # CA
    "los-angeles-ca", "san-francisco-ca", "san-diego-ca", "sacramento-ca",
    "san-jose-ca", "oakland-ca", "long-beach-ca", "fresno-ca", "palm-springs-ca",
    "palm-desert-ca", "west-hollywood-ca", "berkeley-ca", "pasadena-ca",
    # FL
    "miami-fl", "fort-lauderdale-fl", "orlando-fl", "tampa-fl", "jacksonville-fl",
    "key-west-fl", "st-petersburg-fl", "naples-fl", "west-palm-beach-fl",
    # GA
    "atlanta-ga", "savannah-ga",
    # TX
    "dallas-tx", "houston-tx", "austin-tx", "san-antonio-tx", "fort-worth-tx",
    # DC
    "washington-dc",
    # WA
    "seattle-wa", "tacoma-wa", "spokane-wa",
    # NV
    "las-vegas-nv", "reno-nv",
    # CO
    "denver-co", "boulder-co", "aspen-co", "colorado-springs-co",
    # AZ
    "phoenix-az", "tucson-az", "scottsdale-az",
    # OR
    "portland-or", "eugene-or",
    # OH
    "columbus-oh", "cleveland-oh", "cincinnati-oh",
    # MI
    "detroit-mi", "grand-rapids-mi",
    # MN
    "minneapolis-mn", "saint-paul-mn",
    # MO
    "st-louis-mo", "kansas-city-mo",
    # TN
    "nashville-tn", "memphis-tn",
    # NC
    "charlotte-nc", "raleigh-nc", "asheville-nc",
    # SC
    "charleston-sc", "columbia-sc",
    # LA
    "new-orleans-la", "baton-rouge-la",
    # IN
    "indianapolis-in",
    # WI
    "milwaukee-wi", "madison-wi",
    # CT
    "hartford-ct", "new-haven-ct",
    # RI
    "providence-ri",
    # MD
    "baltimore-md",
    # VA
    "richmond-va", "norfolk-va",
    # KY
    "louisville-ky",
    # NM
    "albuquerque-nm", "santa-fe-nm",
    # UT
    "salt-lake-city-ut",
    # ID
    "boise-id",
    # OK
    "oklahoma-city-ok", "tulsa-ok",
    # KS
    "wichita-ks",
    # NE
    "omaha-ne",
    # IA
    "des-moines-ia",
    # AR
    "little-rock-ar",
    # MS
    "jackson-ms",
    # AL
    "birmingham-al",
    # ME
    "portland-me",
    # NH
    "manchester-nh",
    # VT
    "burlington-vt",
    # DE
    "wilmington-de",
    # HI
    "honolulu-hi",
    # AK
    "anchorage-ak",
    # Canada
    "toronto-on", "montreal-qc", "vancouver-bc", "ottawa-on",
    # UK
    "london", "manchester",
    # Other
    "providence-ri", "buffalo-ny",
]

OUTPUT_PATH = Path(__file__).parent / "data" / "real_bios.jsonl"


def search_city(api: RentMasseurAPI, city: str, page: int = 1) -> Dict:
    """Search a city and return results."""
    return api.search(city=city, page=page)


def extract_bios_from_results(results: Dict, city: str = "") -> List[Dict]:
    """Extract bio data from search results."""
    bios = []
    users = results.get("users", [])
    if isinstance(users, dict):
        users = users.get("list", users.get("data", []))
    for user in users:
        if not isinstance(user, dict):
            continue
        headline = user.get("headline", "")
        description = user.get("description", "")
        if not description and not headline:
            continue
        card = user.get("userCard", {})
        bios.append({
            "id": card.get("userId", ""),
            "username": card.get("username", ""),
            "city": city or card.get("searchCity", card.get("location", "")),
            "headline": headline,
            "description": description,
            "isAvailable": card.get("status", {}).get("available", 0),
            "isGold": card.get("isGold", 0),
            "ratingAverage": user.get("ratingAverage", ""),
            "reviewsCount": user.get("reviewsCount", 0),
            "isCertified": user.get("isCertified", 0),
            "services": user.get("services", []),
            "distance": user.get("distance", 0),
            "travels": user.get("travels", []),
        })
    return bios


def scrape_all_cities(api: RentMasseurAPI, max_pages: int = 10, delay: float = 0.8) -> List[Dict]:
    """Scrape bios from all cities, deep paging."""
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
                        all_bios.append(bio)
                        new_count += 1
                log.info("  %s p%d: %d bios (%d new, total %d)", city, page, len(bios), new_count, len(all_bios))
                if new_count == 0:
                    break
                time.sleep(delay)
            except Exception as e:
                log.error("  Error on %s page %d: %s", city, page, e)
                break

    log.info("Scraped %d unique bios from %d cities", len(all_bios), len(CITIES))
    return all_bios


def save_bios(bios: List[Dict], path: Path = OUTPUT_PATH):
    """Save bios to JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for bio in bios:
            f.write(json.dumps(bio, default=str) + "\n")
    log.info("Saved %d bios to %s", len(bios), path)


def rank_by_engagement(bios: List[Dict]) -> List[Dict]:
    """Rank bios by engagement proxy: reviews * rating."""
    def score(b):
        try:
            rating = float(b.get("ratingAverage", 0) or 0)
        except (ValueError, TypeError):
            rating = 0
        reviews = b.get("reviewsCount", 0) or 0
        return rating * reviews
    return sorted(bios, key=score, reverse=True)


def save_ranked_report(bios: List[Dict], path: Path = None):
    """Save a ranked report of all bios by engagement."""
    if path is None:
        path = Path(__file__).parent / "data" / "real_bios_ranked.txt"
    ranked = rank_by_engagement(bios)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for i, b in enumerate(ranked):
            try:
                rating = float(b.get("ratingAverage", 0) or 0)
            except (ValueError, TypeError):
                rating = 0
            reviews = b.get("reviewsCount", 0) or 0
            engagement = rating * reviews
            f.write(f"#{i+1} | {b['username']} | {b['city']} | ⭐{rating} | {reviews} reviews | engagement={engagement}\n")
            f.write(f"  Headline: {b['headline']}\n")
            desc = b['description'].replace('\n', ' | ')[:500]
            f.write(f"  Desc: {desc}\n")
            f.write(f"  Services: {b.get('services', [])}\n")
            f.write(f"  Gold: {b.get('isGold', 0)} | Avail: {b.get('isAvailable', 0)} | Certified: {b.get('isCertified', 0)}\n")
            f.write("\n")
    log.info("Ranked report saved to %s", path)
    return path


def scrape_and_save(api: RentMasseurAPI, max_pages: int = 10, delay: float = 0.8) -> int:
    """Full scrape pipeline with ranking."""
    bios = scrape_all_cities(api, max_pages=max_pages, delay=delay)
    save_bios(bios)
    save_ranked_report(bios)
    return len(bios)
