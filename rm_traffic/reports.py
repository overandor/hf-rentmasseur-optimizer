"""
Daily Report Generator — human-readable profile operations report.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from .db import get_latest_traffic_snapshot, get_open_experiments, get_variant_history
from .traffic_analyzer import analyze_trend, conversion_rate
from .search_rank import check_all_search_ranks


def generate_report(username: str, state: Dict, ranks: Dict) -> str:
    """Generate a daily report string."""
    snapshots = get_latest_traffic_snapshot(2)
    current = snapshots[0] if snapshots else {}
    baseline = snapshots[-1] if len(snapshots) > 1 else current
    trend = analyze_trend(hours=24)
    open_exps = get_open_experiments()
    pending = [v for v in get_variant_history("bio", 20) if v["status"] == "pending_approval"]

    keep = state.get("keeponline", {})
    avail = state.get("availability", {})
    about = state.get("about", {})
    assets = about.get("userProps", {}).get("assets", {})
    stats = state.get("stats", {}).get("profileStatistics", {})
    dashboard = state.get("dashboard", {})

    ts = datetime.now(timezone.utc).isoformat()[:19]
    report = f"""
# ProfileOps Report — {ts} UTC

## Account Health
- Visibility: {'Visible' if not keep.get('isAdHidden') else 'HIDDEN'}
- Availability: {avail.get('selected', 'unknown')} ({max(0, int(avail.get('countdown', 0) - __import__('time').time()) // 60)} minutes left)
- Profile: {dashboard.get('profileStatus', 'unknown')}
- Membership: {dashboard.get('membership', 'unknown')}
- Frozen: {bool(keep.get('isFrozen'))}

## Traffic
- Profile views: {current.get('profile_views', 'N/A')}
- Contact clicks: {current.get('contact_clicks', 'N/A')}
- Contact click rate: {conversion_rate(current.get('profile_views') or 0, current.get('contact_clicks') or 0):.2%}
- New visits: {keep.get('newVisits', 'N/A')}
- New emails: {keep.get('newEmails', 'N/A')}
- Online bookmarks: {dashboard.get('onlineBookmarks', 'N/A')}

## 24h Trend
- Status: {trend.get('status', 'N/A')}
- Delta views: {trend.get('comparison', {}).get('delta_views', 'N/A')}
- Delta contacts: {trend.get('comparison', {}).get('delta_clicks', 'N/A')}
- Rate change: {trend.get('comparison', {}).get('rate_delta', 'N/A')}
- Alert: {trend.get('alert', False)}

## Search Presence
- All results: {ranks.get('all', {}).get('position', 'not found')}/{ranks.get('all', {}).get('total', 'N/A')}
- Available Now: {ranks.get('available_now', {}).get('position', 'not found')}/{ranks.get('available_now', {}).get('total', 'N/A')}

## Current Copy
- Headline: {assets.get('headline', 'N/A')}
- Bio length: {len(assets.get('description', ''))} characters

## Pending Actions
- Bio drafts: {len(pending)}
- Open experiments: {len(open_exps)}

## Recommended Next Action
"""
    if not keep.get('isAdHidden'):
        report += "- Profile is visible. Focus on availability + copy optimization.\n"
    else:
        report += "- CRITICAL: Profile is hidden. Fix visibility immediately.\n"

    if avail.get('selected') != 'Available':
        report += "- Availability is off. Turn on when actually available.\n"
    elif max(0, int(avail.get('countdown', 0) - __import__('time').time()) // 60) < 60:
        report += "- Availability expires within 1 hour. Refresh soon.\n"

    if trend.get('alert'):
        report += "- Traffic drop detected. Consider testing a new bio variant.\n"
    elif pending:
        report += f"- {len(pending)} bio draft(s) pending approval.\n"
    else:
        report += "- Traffic stable. Generate a new bio variant to test.\n"

    return report


def save_report(report: str, path: Path = Path("rm_traffic/data/reports")):
    path.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()[:19].replace(":", "-")
    file_path = path / f"report_{ts}.md"
    file_path.write_text(report)
    return file_path


def print_report(username: str, state: Dict, ranks: Dict):
    print(generate_report(username, state, ranks))
