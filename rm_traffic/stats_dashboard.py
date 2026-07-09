"""
Stats Dashboard — generate a simple HTML stats page for the ProfileOps engine.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from .db import get_conn
from .traffic_analyzer import conversion_rate, analyze_trend


def _get_latest_state():
    conn = get_conn()
    snap = conn.execute("SELECT * FROM traffic_snapshots ORDER BY created_at DESC LIMIT 1").fetchone()
    conn.close()
    return dict(snap) if snap else {}


def _get_experiment_count():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
    open_ = conn.execute("SELECT COUNT(*) FROM experiments WHERE ended_at IS NULL").fetchone()[0]
    conn.close()
    return {"total": total, "open": open_}


def _get_draft_count():
    conn = get_conn()
    bio = conn.execute("SELECT COUNT(*) FROM content_variants WHERE kind='bio' AND status='draft'").fetchone()[0]
    blog = conn.execute("SELECT COUNT(*) FROM content_variants WHERE kind='blog' AND status='draft'").fetchone()[0]
    interview = conn.execute("SELECT COUNT(*) FROM content_variants WHERE kind='interview' AND status='draft'").fetchone()[0]
    conn.close()
    return {"bio": bio, "blog": blog, "interview": interview}


def _get_receipt_count():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
    verified = conn.execute("SELECT COUNT(*) FROM receipts WHERE verified=1").fetchone()[0]
    conn.close()
    return {"total": total, "verified": verified}


def _get_recent_receipts(limit: int = 10):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM receipts ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def generate_html(state: dict = None, output_path: Path = None) -> Path:
    if state is None:
        state = _get_latest_state()
    trend = analyze_trend(hours=24)
    experiments = _get_experiment_count()
    drafts = _get_draft_count()
    receipts = _get_receipt_count()
    recent = _get_recent_receipts(10)

    views = state.get("profile_views") or 0
    contacts = state.get("contact_clicks") or 0
    rate = conversion_rate(views, contacts)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RM ProfileOps Stats Dashboard</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; background: #f5f5f7; color: #1d1d1f; }}
        h1 {{ font-size: 32px; margin-bottom: 8px; }}
        .timestamp {{ color: #86868b; font-size: 14px; margin-bottom: 24px; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }}
        .card {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .card h2 {{ font-size: 14px; color: #86868b; margin: 0 0 8px 0; text-transform: uppercase; letter-spacing: 0.5px; }}
        .card .value {{ font-size: 32px; font-weight: 600; margin: 0; }}
        .card .sub {{ font-size: 14px; color: #86868b; margin-top: 4px; }}
        .section {{ background: white; border-radius: 12px; padding: 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .section h2 {{ font-size: 18px; margin-top: 0; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
        th, td {{ text-align: left; padding: 10px; border-bottom: 1px solid #eee; }}
        th {{ color: #86868b; font-weight: 500; }}
        .ok {{ color: #34c759; }}
        .warn {{ color: #ff9500; }}
        .bad {{ color: #ff3b30; }}
    </style>
</head>
<body>
    <h1>RM ProfileOps Stats Dashboard</h1>
    <div class="timestamp">Generated: {datetime.now(timezone.utc).isoformat()} UTC</div>

    <div class="grid">
        <div class="card">
            <h2>Profile Views</h2>
            <p class="value">{views}</p>
        </div>
        <div class="card">
            <h2>Contact Clicks</h2>
            <p class="value">{contacts}</p>
        </div>
        <div class="card">
            <h2>Contact Rate</h2>
            <p class="value">{rate:.2%}</p>
        </div>
        <div class="card">
            <h2>Receipts</h2>
            <p class="value">{receipts['total']}</p>
            <p class="sub">{receipts['verified']} verified</p>
        </div>
        <div class="card">
            <h2>Experiments</h2>
            <p class="value">{experiments['total']}</p>
            <p class="sub">{experiments['open']} open</p>
        </div>
        <div class="card">
            <h2>Drafts</h2>
            <p class="value">{drafts['bio'] + drafts['blog'] + drafts['interview']}</p>
            <p class="sub">bio {drafts['bio']} | blog {drafts['blog']} | interview {drafts['interview']}</p>
        </div>
    </div>

    <div class="section">
        <h2>24h Trend</h2>
        <p><strong>Status:</strong> {trend.get('status', 'N/A')}</p>
        <p><strong>Delta views:</strong> {trend.get('comparison', {}).get('delta_views', 'N/A')}</p>
        <p><strong>Delta contacts:</strong> {trend.get('comparison', {}).get('delta_clicks', 'N/A')}</p>
        <p><strong>Rate change:</strong> {trend.get('comparison', {}).get('rate_delta', 'N/A')}</p>
        <p><strong>Alert:</strong> <span class="{'bad' if trend.get('alert') else 'ok'}">{'YES' if trend.get('alert') else 'NO'}</span></p>
    </div>

    <div class="section">
        <h2>Recent Receipts</h2>
        <table>
            <tr><th>Time</th><th>Action</th><th>Verified</th></tr>
            {''.join(f'<tr><td>{r["created_at"]}</td><td>{r["action"]}</td><td class="{"ok" if r["verified"] else "bad"}">{"YES" if r["verified"] else "NO"}</td></tr>' for r in recent)}
        </table>
    </div>
</body>
</html>
"""

    output_path = output_path or Path(__file__).parent / "data" / "dashboard" / "index.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html)
    return output_path


def generate_dashboard() -> Path:
    return generate_html()
