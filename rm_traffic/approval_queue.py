"""
Approval Queue — formal interface for content drafts awaiting approval.
"""

from .db import (
    get_conn,
    upsert_content_variant,
    set_variant_status,
    get_variant_history,
    get_active_variant,
    now_iso,
)


def submit_draft(variant_id: str, kind: str, headline: str, description: str,
                 title: str = "", body: str = "", hypothesis: str = "") -> str:
    """Submit a draft to the approval queue."""
    upsert_content_variant(variant_id, kind, headline, description, title, body,
                         status="pending_approval", hypothesis=hypothesis)
    return variant_id


def approve_draft(variant_id: str) -> bool:
    """Mark a draft as approved."""
    set_variant_status(variant_id, "approved")
    return True


def reject_draft(variant_id: str) -> bool:
    """Reject a draft."""
    set_variant_status(variant_id, "rejected")
    return True


def list_pending(kind: str = None) -> list:
    """List pending drafts."""
    conn = get_conn()
    if kind:
        rows = conn.execute(
            "SELECT * FROM content_variants WHERE kind=? AND status='pending_approval' ORDER BY created_at DESC",
            (kind,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM content_variants WHERE status='pending_approval' ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_approved(kind: str = None) -> list:
    """List approved drafts."""
    conn = get_conn()
    if kind:
        rows = conn.execute(
            "SELECT * FROM content_variants WHERE kind=? AND status='approved' ORDER BY created_at DESC",
            (kind,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM content_variants WHERE status='approved' ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
