"""
LLM Bio Writer — generates a real bio based on actual profile and traffic analysis.

Uses local Ollama (llama3.2) by default. The prompt includes:
- Current profile data (services, rates, headline, description)
- Last 7 days of views and contact clicks
- Best performing day
- Weaknesses and opportunities
- City/location

Output: a new headline + bio, grounded in real data. No fake claims.
"""

import json
import logging
import time
from typing import Dict, Any, Optional

from rm_traffic.llm_client import LLMClient, generate_with_fallback

log = logging.getLogger("llm_bio")

DEFAULT_MODEL = "llama3.2"


def build_prompt(profile_data: Dict[str, Any], stats_history: list, current_headline: str,
                 current_description: str, city: str = "Manhattan, NYC") -> str:
    """Build a grounded prompt for the LLM bio writer."""

    dash = profile_data.get("dashboard", {})
    stats = profile_data.get("stats", {})
    prof_stats = stats.get("profileStatistics", {}) or {}
    services = dash.get("service", {})
    bookmarks = dash.get("onlineBookmarks", 0)

    # Format services
    services_text = []
    for key, svc in services.items():
        if isinstance(svc, dict) and svc.get("activated"):
            incall = svc.get("price", {}).get("incall", "")
            outcall = svc.get("price", {}).get("outcall", "")
            services_text.append(f"- {svc.get('label', key)}: incall ${incall}, outcall ${outcall}")

    # Format 7-day traffic
    visits = prof_stats.get("visits", [])
    traffic_lines = []
    best_day = None
    best_views = 0
    total_views = 0
    for v in visits:
        if isinstance(v, dict):
            day = v.get("day", "")
            count = v.get("count", 0)
            total_views += count
            traffic_lines.append(f"- {day}: {count} views")
            if count > best_views:
                best_views = count
                best_day = day

    # Recent stats from DB
    recent = stats_history[-3:] if stats_history else []
    recent_lines = []
    for r in recent:
        recent_lines.append(
            f"- {r['ts'][:10]}: {r['views'] or 'N/A'} views, {r['contact_clicks'] or 'N/A'} contact clicks, "
            f"{r['visits'] or 'N/A'} new visits"
        )

    prompt = f"""You are a professional profile copywriter for an independent massage therapist in Manhattan.

Your job: rewrite the headline and bio for this RentMasseur profile based ONLY on the real data below.

Rules:
- Do NOT invent fake credentials, fake reviews, or fake client testimonials.
- Do NOT claim specific results unless they are in the data.
- Keep the tone confident, masculine, direct, and professional.
- Use the location and services from the data.
- Mention the therapist's username "KARPATHIAN WOLF" and the Wolf persona.
- Make the bio 1500-2000 characters.
- The headline should be punchy and memorable, under 80 characters.
- The bio should explain who he is, what he offers, where, and what makes him different.

PROFILE DATA:
Username: Karpathianwolf
Current headline: {current_headline}
Current bio (first 300 chars): {current_description[:300]}
Location: {city}
Services:
{chr(10).join(services_text) if services_text else "- Therapeutic and sensual massage"}

TRAFFIC DATA:
Total profile views: {prof_stats.get('totalPageViews', 'N/A')}
Total contact clicks: {prof_stats.get('totalContactClicks', 'N/A')}
Online bookmarks: {bookmarks}

Last 7 days:
{chr(10).join(traffic_lines) if traffic_lines else "No daily data"}
Best performing day: {best_day} ({best_views} views)

Recent stats:
{chr(10).join(recent_lines) if recent_lines else "No recent data"}

INSIGHTS:
- The profile gets {prof_stats.get('totalPageViews', 0)} lifetime views.
- The best recent day was {best_day} with {best_views} views.
- Keep the profile focused, confident, and trustworthy.

OUTPUT FORMAT:
Return ONLY a JSON object with exactly two keys:
{{"headline": "...", "bio": "..."}}

Do not include any markdown, explanation, or extra text. Just the JSON object.
"""
    return prompt


def parse_llm_output(text: str) -> Optional[Dict[str, str]]:
    """Parse JSON output from LLM. Clean up common formatting issues."""
    if not text:
        return None

    # Find JSON block
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text
        text = text.strip()
        if text.startswith("json"):
            text = text[4:].strip()

    # Find first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    text = text[start:end+1]

    try:
        data = json.loads(text)
        if "headline" in data and "bio" in data:
            return {
                "headline": str(data["headline"]).strip(),
                "bio": str(data["bio"]).strip(),
            }
    except json.JSONDecodeError:
        log.error("Failed to parse LLM output as JSON")
        return None
    return None


def generate_bio_with_llm(profile_data: Dict[str, Any], stats_history: list,
                          current_headline: str, current_description: str,
                          city: str = "Manhattan, NYC", model: str = DEFAULT_MODEL,
                          provider: str = None, max_tokens: int = 1200) -> Optional[Dict[str, str]]:
    """Generate a new bio using the LLM based on real data."""
    prompt = build_prompt(profile_data, stats_history, current_headline, current_description, city)
    log.info("Calling LLM for bio generation...")
    start = time.time()

    if provider:
        client = LLMClient(provider, model)
        response = client.generate(prompt, max_tokens)
    else:
        response = generate_with_fallback(prompt, max_tokens)

    elapsed = time.time() - start
    log.info("LLM response received in %.1fs", elapsed)

    if not response:
        return None

    parsed = parse_llm_output(response)
    if parsed:
        log.info("Generated headline: %s", parsed["headline"])
        return parsed
    else:
        log.error("Could not parse LLM bio output")
        return None


# Fallback: if Ollama is not available, return a template variant
def generate_fallback_bio(current_headline: str = "", current_description: str = "") -> Dict[str, str]:
    from rm_traffic.profileops import suggest_bio
    return suggest_bio(current_headline, current_description)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    # Test
    sample = {
        "dashboard": {
            "onlineBookmarks": 2,
            "service": {
                "therapeutic": {"activated": True, "price": {"incall": 199, "outcall": 269}, "label": "Therapeutic"},
            }
        },
        "stats": {
            "profileStatistics": {
                "totalPageViews": 2808,
                "totalContactClicks": 135,
                "visits": [
                    {"day": "Today", "count": 0, "percent": 0},
                    {"day": "Yesterday", "count": 76, "percent": 85},
                ]
            }
        }
    }
    result = generate_bio_with_llm(sample, [], "Old headline", "Old bio text", "Manhattan, NYC")
    print(json.dumps(result, indent=2) if result else "No result")
