"""
Interview Monitor — stable trust content. Draft only, manual approval.

Confirmed: featureInterview status in dashboard.
Not confirmed: interview edit endpoint.

Policy: never auto-edit approved interview. Only draft improvements.
"""

import logging
import time
from typing import Dict

from .db import write_receipt, upsert_content_variant
from .content_policy import check_bio_risk
from .api_client import RentMasseurAPI

log = logging.getLogger("profileops.interview")

INTERVIEW_ANSWER_DRAFTS = {
    "about_you": """I am a professional bodyworker based in Manhattan. My sessions are pressure-forward, focused on real relief for people who train hard, sit long hours, or carry stress in their body. I believe in clear communication, clean space, and practical results.""",
    "your_style": """My style is direct and deliberate. I find the tension, apply sustained pressure, and work through the layers that contribute to tightness. Deep tissue, sports recovery, and targeted neck/shoulder work are the main focus areas.""",
    "why_clients": """Clients come to me when they need more than a light massage. They want real pressure, a calm environment, and a therapist who listens. Many are desk workers, athletes, or travelers dealing with accumulated stiffness.""",
    "boundaries": """I keep things professional. I work with the body as a whole, focus on therapeutic goals, and maintain clear boundaries. I expect the same respect in return.""",
}


def get_interview_status(dashboard: Dict) -> Dict:
    """Extract interview status from dashboard."""
    interview = dashboard.get("featureInterview", {})
    return {
        "is_completed": int(interview.get("isCompleted", 0)),
        "is_pending_approved": int(interview.get("isPendingApproved", 0)),
        "approved": int(interview.get("isApproved", 0)) if "isApproved" in interview else None,
        "raw": interview,
    }


def monitor_interview(api: RentMasseurAPI) -> Dict:
    """Check interview status and write receipt."""
    dashboard = api.get_dashboard()
    status = get_interview_status(dashboard)
    write_receipt("interview_monitor_v1", "monitor_interview", {}, status, verified=True)
    log.info("Interview status: completed=%s pending=%s", status["is_completed"], status["is_pending_approved"])
    return status


def generate_interview_drafts() -> list:
    """Generate improved interview answer drafts."""
    drafts = []
    for key, text in INTERVIEW_ANSWER_DRAFTS.items():
        risk = check_bio_risk(text)
        if risk > 0.7:
            continue
        variant_id = f"interview_{key}_{int(time.time())}"
        upsert_content_variant(
            variant_id, "interview",
            title=key, body=text,
            hypothesis="Professional interview answer draft.",
            status="draft"
        )
        write_receipt(
            "interview_draft_created_v1",
            "generate_interview_draft",
            {},
            {"variant_id": variant_id, "question": key, "risk": risk},
            verified=True,
        )
        drafts.append({"variant_id": variant_id, "question": key, "body": text, "risk": risk})
        log.info("Interview draft created: %s", key)
    return drafts
