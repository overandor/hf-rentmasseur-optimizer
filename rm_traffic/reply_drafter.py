"""
LLM Reply Drafter — template-first reply drafting for client messages.

Template is canonical. LLM is optional polish only (local, 8s timeout).
Uses local-only providers for private client text:
  template canonical → local Ollama/Transformers optional polish → template retained if invalid.
No Groq. No OpenRouter. No cloud fallback.

Drafts replies, does NOT auto-send. Human approval required for first contact.
Ready-for-fast-approval only for repeat/opt-in clients with valid templates.

Reply structure (always):
  - availability
  - location / incall-outcall boundary
  - rate clarity
  - session length
  - professional tone
  - one next-step question
  - no spammy pressure
  - no weird sexual escalation
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .intent_engine import classify, IntentResult

# Local-only LLM imports — NO cloud providers for private client text
try:
    from .llm_client import LLMClient
    _HAS_LLM = True
except ImportError:
    _HAS_LLM = False

log = logging.getLogger("reply_drafter")

# Reply classes
REPLY_BOOKING_NOW = "booking_now_reply"
REPLY_PRICE_QUESTION = "price_question_reply"
REPLY_LOCATION_QUESTION = "location_question_reply"
REPLY_REPEAT_CLIENT = "repeat_client_reply"
REPLY_INQUIRY = "inquiry_reply"
REPLY_FOLLOW_UP = "follow_up_reply"
REPLY_CLOSE_LOOP = "close_loop_reply"
REPLY_AVAILABILITY_QUESTION = "availability_reply"
REPLY_HIGH_VALUE_REPEAT = "high_value_repeat_reply"
REPLY_NONE = "none"

# Risk levels
RISK_SAFE = "safe"
RISK_REVIEW = "review"
RISK_BLOCKED = "blocked"


@dataclass
class DraftReply:
    username: str = ""
    intent_class: str = ""
    confidence: float = 0.0
    booking_probability: float = 0.0
    reply_text: str = ""
    reply_class: str = ""
    risk_level: str = RISK_SAFE
    needs_human_approval: bool = True
    reason: str = ""
    suggested_time_slots: List[str] = field(default_factory=list)
    error: str = ""


def _build_polish_prompt(template_text: str, message: str, intent: IntentResult, context: Dict) -> str:
    """Build LLM prompt for polishing an existing template draft.
    The model rewrites the template for clarity — it does NOT generate from scratch."""
    username = context.get("username", "")
    is_repeat = intent.classification in ("repeat_client", "high_value_repeat")

    prompt = f"""Rewrite this existing draft only for clarity. Do not add facts. Do not change rates, location, session length, phone, or availability. Return one reply only.

Existing draft:
"{template_text}"

Client message: "{message[:300]}"
Client username: {username}
Intent: {intent.classification}
Is repeat client: {is_repeat}

Rules:
- Rewrite the existing draft for clarity and warmth only
- Do NOT add new facts, rates, locations, or availability not in the existing draft
- Do NOT change the rate, location, session length, or phone number
- Keep it under 80 words
- End with exactly ONE next-step question
- Professional tone, first person singular (I/my, not we/us/our)
- No sexual language, no innuendo
- Return only the rewritten reply text, nothing else

Rewritten reply:"""

    return prompt


def _clean_llm_output(text: str) -> str:
    """Clean LLM output — remove quotes, markdown, extra whitespace."""
    if not text:
        return ""
    text = text.strip()
    # Remove surrounding quotes
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    # Remove markdown
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    # Remove any "Reply:" prefix
    text = re.sub(r'^(Reply|Response|Message):\s*', '', text, flags=re.IGNORECASE)
    # Normalize whitespace
    text = ' '.join(text.split())
    return text.strip()


def _template_fallback(intent: IntentResult, context: Dict) -> str:
    """Fixed template fallback when LLM is unavailable."""
    rate = context.get("rate", "$200")
    phone = context.get("phone", "")
    cls = intent.classification

    if cls == "booking_now":
        return (
            f"Yes — I'm available today. I have openings at 7:30 or 9 PM. "
            f"Manhattan incall, {rate} for 60 min. "
            f"Which time works for you? Text {phone} to confirm."
        )

    if cls == "price_question":
        return (
            f"Rate is {rate} for 60 min, $280 for 90 min, $360 for 120 min. "
            f"Manhattan incall. What duration and time work for you? "
            f"Text {phone} to book."
        )

    if cls == "availability_question":
        return (
            f"I'm available today and this week. "
            f"Manhattan incall, {rate} for 60 min. "
            f"What day and time work for you? Text {phone} to schedule."
        )

    if cls == "location_question":
        return (
            f"I'm based in Manhattan — private incall space. "
            f"Outcall available within Manhattan for additional travel fee. "
            f"Rate is {rate}. Text {phone} for faster booking."
        )

    if cls in ("repeat_client", "high_value_repeat"):
        return (
            f"Great to hear from you again! "
            f"I have openings today. Same location in Manhattan. "
            f"Text {phone} to confirm your time."
        )

    if cls == "ghosted_lead":
        return (
            f"Hi — following up. I'm available this week if you'd like to book. "
            f"Manhattan incall, {rate} for 60 min. "
            f"Text {phone} to schedule."
        )

    return (
        f"Hi! Thanks for your interest. "
        f"I offer deep tissue and sports recovery massage in Manhattan. "
        f"Rate is {rate} for 60 min. "
        f"What questions can I answer? Text {phone} for faster response."
    )


def _determine_reply_class(intent: IntentResult) -> str:
    """Map intent classification to reply class."""
    mapping = {
        "booking_now": REPLY_BOOKING_NOW,
        "price_question": REPLY_PRICE_QUESTION,
        "availability_question": REPLY_AVAILABILITY_QUESTION,
        "location_question": REPLY_LOCATION_QUESTION,
        "repeat_client": REPLY_REPEAT_CLIENT,
        "high_value_repeat": REPLY_HIGH_VALUE_REPEAT,
        "ghosted_lead": REPLY_FOLLOW_UP,
        "do_not_contact": REPLY_NONE,
        "spam": REPLY_NONE,
        "unknown": REPLY_INQUIRY,
    }
    return mapping.get(intent.classification, REPLY_INQUIRY)


def _determine_risk(intent: IntentResult, is_first_contact: bool = True) -> str:
    """Determine risk level for the reply."""
    if intent.classification in ("do_not_contact", "spam"):
        return RISK_BLOCKED
    if "unsafe" in (intent.risk_flags or []):
        return RISK_BLOCKED
    if "opt_out" in (intent.risk_flags or []):
        return RISK_BLOCKED
    if is_first_contact:
        return RISK_REVIEW
    return RISK_SAFE


def validate_reply_text(text: str, context: Dict = None) -> Tuple[bool, str]:
    """Validate reply text against quality and safety rules.
    Returns (is_valid, reason)."""
    if not text or not text.strip():
        return False, "empty_text"

    if context is None:
        context = {}

    text_lower = text.lower()
    word_count = len(text.split())

    # ─── Reject: bad pronouns (first person plural = wrong voice) ───
    if re.search(r'\b(we|us|our)\b', text_lower):
        return False, "first_person_plural_detected"

    # ─── Reject: "app" reference ───
    if re.search(r'\bapp\b', text_lower):
        return False, "app_reference_detected"

    # ─── Reject: known bad phrases ───
    bad_phrases = ["sorry to hear", "reaching out to us", "last-minute app",
                   "thank you for reaching out"]
    if any(p in text_lower for p in bad_phrases):
        return False, f"bad_phrase_detected"

    # ─── Reject: sexual/innuendo terms ───
    sexual_kw = ["sexual", "erotic", "sensual", "nude", "naked", "happy ending",
                 "full service", "extras", "menu", "gfe", "bb", "bareback"]
    if any(kw in text_lower for kw in sexual_kw):
        return False, "sexual_innuendo_detected"

    # ─── Reject: phone number when not allowed ───
    allow_phone = os.environ.get("ALLOW_PHONE_IN_DRAFT", "false").lower() == "true"
    if not allow_phone:
        phone_in_context = context.get("phone", "")
        # Check for raw phone numbers (not the word "text")
        if re.search(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', text):
            return False, "raw_phone_in_draft_not_allowed"
        if phone_in_context and phone_in_context in text and not allow_phone:
            return False, "phone_in_draft_not_allowed"

    # ─── Reject: over 80 words ───
    if word_count > 80:
        return False, f"too_many_words ({word_count})"

    # ─── Reject: no question mark (no next-step question) ───
    if "?" not in text:
        return False, "no_next_step_question"

    # ─── Reject: multiple questions (rule is one next-step question) ───
    question_count = text.count("?")
    if question_count > 2:  # allow up to 2 for compound questions like "What time and duration?"
        return False, f"too_many_questions ({question_count})"

    # ─── Reject: missing rate (for booking/price/location intents) ───
    rate = context.get("rate", "$200")
    intent_class = context.get("intent_class", "")
    if intent_class in ("booking_now", "price_question", "location_question", "availability_question"):
        if rate and rate not in text:
            return False, "missing_rate"

    # ─── Reject: missing location ───
    location = context.get("location", "Manhattan")
    if location and location.lower() not in text_lower and "manhattan" not in text_lower:
        return False, "missing_location"

    # ─── Reject: missing session length ───
    if intent_class in ("booking_now", "price_question"):
        if not re.search(r'\b(60|90|120)\s*min', text_lower) and "min" not in text_lower:
            return False, "missing_session_length"

    return True, "valid"


def _try_local_llm_polish(template_text: str, message: str, intent: IntentResult,
                            context: Dict, timeout_seconds: int = 8) -> Optional[str]:
    """Try local-only LLM (Ollama or Transformers.js) for light polish.
    Rewrites the existing template — does NOT generate from scratch.
    NO cloud providers. Returns None if unavailable or too slow."""
    if not _HAS_LLM:
        return None

    import threading

    prompt = _build_polish_prompt(template_text, message, intent, context)

    result = [None]
    def _call():
        try:
            # Try Ollama only (local), then Transformers.js (local)
            # NO Groq, NO OpenRouter — private client text stays local
            for provider, model in [("ollama", "llama3.2"), ("transformers", None)]:
                try:
                    client = LLMClient(provider=provider, model=model)
                    resp = client.generate(prompt, max_tokens=150)
                    if resp and len(resp) > 20:
                        result[0] = resp
                        return
                except Exception:
                    continue
        except Exception:
            return

    t = threading.Thread(target=_call, daemon=True)
    t.start()
    t.join(timeout=timeout_seconds)

    if t.is_alive():
        log.info(f"  ⟁ Local LLM timed out ({timeout_seconds}s) — using template")
        return None

    return result[0]


def draft_reply(message: str, context: Dict = None) -> DraftReply:
    """
    Generate a template-first draft reply for a client message.

    Template is canonical. LLM is optional polish only (local, 8s timeout).
    No cloud providers ever called on private client text.
    All first-contact drafts are approval-gated.

    Args:
        message: The client's message text
        context: Dict with username, is_premium, rate, phone, location, is_first_contact

    Returns:
        DraftReply with reply_text, risk_level, needs_human_approval
    """
    if context is None:
        context = {}

    # Classify intent
    intent = classify(message, context.get("username", ""))

    # Build draft
    draft = DraftReply(
        username=context.get("username", ""),
        intent_class=intent.classification,
        confidence=intent.confidence,
        booking_probability=intent.booking_probability,
        reply_class=_determine_reply_class(intent),
        risk_level=_determine_risk(intent, context.get("is_first_contact", True)),
        reason=f"Intent: {intent.classification} (conf={intent.confidence:.2f})",
    )

    # Blocked — no reply
    if draft.risk_level == RISK_BLOCKED:
        draft.reply_text = ""
        draft.needs_human_approval = False
        draft.reason = f"BLOCKED: {intent.classification} with risk flags {intent.risk_flags}"
        return draft

    # ─── Template first (canonical) ───
    draft.reply_text = _template_fallback(intent, context)
    draft.reason += " | template-canonical"
    log.info(f"  ◉ Template reply for {draft.username}: {draft.reply_text[:80]}...")

    # ─── Optional local LLM polish (8s timeout, no cloud) ───
    polished = _try_local_llm_polish(draft.reply_text, message, intent, context, timeout_seconds=8)
    if polished:
        cleaned = _clean_llm_output(polished)
        # Validate polished output against strict quality rules
        validation_context = {**context, "intent_class": intent.classification}
        is_valid, reject_reason = validate_reply_text(cleaned, validation_context)
        if is_valid:
            draft.reply_text = cleaned
            draft.reason += " | llm-polished"
            log.info(f"  ◉ Polished reply for {draft.username}: {draft.reply_text[:80]}...")
        else:
            draft.reason += f" | llm-polish-rejected:{reject_reason}"
            log.info(f"  ⟁ LLM polish rejected ({reject_reason}) — keeping template")

    # Approval gate — all first contact needs approval
    is_repeat = intent.classification in ("repeat_client", "high_value_repeat")
    if is_repeat and not context.get("is_first_contact", True):
        draft.needs_human_approval = False
    else:
        draft.needs_human_approval = True

    # Suggested time slots for booking intent
    if intent.classification in ("booking_now", "high_value_repeat"):
        draft.suggested_time_slots = ["7:30 PM", "9:00 PM", "Tomorrow 12:00 PM"]

    return draft


def draft_mailbox_replies(emails: List[Dict], context: Dict = None) -> List[DraftReply]:
    """
    Generate draft replies for all mailbox conversations.

    Args:
        emails: List of email dicts from api.get_mailbox()
        context: Base context (rate, phone, location)

    Returns:
        List of DraftReply objects
    """
    if context is None:
        context = {}

    drafts = []
    for email in emails:
        uc = email.get("userCard", {})
        msg = email.get("lastMessage", "")
        username = uc.get("username", "")

        email_context = {
            **context,
            "username": username,
            "is_premium": bool(uc.get("isPremium", 0)),
            "is_first_contact": not bool(email.get("lastMessage", "")),
        }

        draft = draft_reply(msg, email_context)
        drafts.append(draft)

    return drafts


def format_drafts_summary(drafts: List[DraftReply]) -> str:
    """Format drafts for display."""
    lines = [f"\n{'='*60}", f"  REPLY DRAFT QUEUE — {len(drafts)} drafts", f"{'='*60}\n"]

    for d in drafts:
        if d.risk_level == RISK_BLOCKED:
            lines.append(f"  🚫 {d.username} [{d.intent_class}] — BLOCKED")
            lines.append(f"     {d.reason}")
            continue

        approval = "🔒 approval" if d.needs_human_approval else "⚡ ready_for_fast_approval"
        lines.append(f"  ◉ {d.username} [{d.intent_class}] conf={d.confidence:.2f} {approval}")
        lines.append(f"    Reply: \"{d.reply_text[:120]}\"")
        if d.suggested_time_slots:
            lines.append(f"    Slots: {', '.join(d.suggested_time_slots)}")
        lines.append("")

    return "\n".join(lines)
