"""
Intent Engine — classifies inbound messages using local Ollama.

Classifies each message into:
  booking_now       — asking for time/date/session today or tomorrow
  price_question    — asking about rates
  availability_question — asking when available
  location_question — asking about incall/outcall/area
  repeat_client     — references prior sessions
  ghosted_lead      — reappearing after silence
  high_value_repeat — repeat client with booking language
  do_not_contact    — STOP / opt-out / unsafe
  spam              — promotional, irrelevant
  unknown           — can't classify

Falls back to keyword-based classification if Ollama is not running.
"""

import json
import logging
import os
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Dict, List, Optional

log = logging.getLogger("intent_engine")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:latest")

# Keyword fallback
BOOKING_KW = ["book", "appointment", "schedule", "session", "available", "today", "tonight", "tomorrow", "when can", "how soon", "fit me in"]
PRICE_KW = ["price", "rate", "cost", "how much", "fee", "charge", "donation", "pricing"]
AVAIL_KW = ["available", "when are you", "what time", "open", "slots", "free"]
LOCATION_KW = ["where", "location", "incall", "outcall", "hotel", "address", "area", "neighborhood", "come to", "travel to"]
REPEAT_KW = ["again", "last time", "saw you before", "was here before", "repeat", "second time", "regular", "missed you", "been a while"]
STOP_KW = ["stop", "unsubscribe", "remove", "do not text", "don't text", "not interested", "wrong number", "stop texting", "opt out", "don't contact", "do not contact", "take me off", "no more"]
SPAM_KW = ["promo", "discount", "offer", "deal", "click here", "visit my", "check out my", "follow me", "subscribe", "free", "bonus"]
UNSAFE_KW = ["raw", "bb", "bareback", "unsafe", "no condom", "bare"]


@dataclass
class IntentResult:
    classification: str = "unknown"
    confidence: float = 0.0
    booking_probability: float = 0.0
    suggested_reply_class: str = ""
    risk_flags: List[str] = None

    def __post_init__(self):
        if self.risk_flags is None:
            self.risk_flags = []


def keyword_classify(message: str) -> IntentResult:
    """Fast keyword-based classification — always available."""
    text = (message or "").lower().strip()

    if not text:
        return IntentResult(classification="unknown", confidence=0.0)

    # Check stop/unsafe first
    if any(kw in text for kw in STOP_KW):
        return IntentResult(
            classification="do_not_contact",
            confidence=0.95,
            suggested_reply_class="",
            risk_flags=["opt_out"],
        )

    if any(kw in text for kw in UNSAFE_KW):
        return IntentResult(
            classification="do_not_contact",
            confidence=0.95,
            risk_flags=["unsafe"],
        )

    if any(kw in text for kw in SPAM_KW):
        return IntentResult(
            classification="spam",
            confidence=0.8,
            risk_flags=["spam"],
        )

    is_repeat = any(kw in text for kw in REPEAT_KW)
    is_booking = any(kw in text for kw in BOOKING_KW)
    is_price = any(kw in text for kw in PRICE_KW)
    is_location = any(kw in text for kw in LOCATION_KW)
    is_avail = any(kw in text for kw in AVAIL_KW)

    if is_repeat and is_booking:
        return IntentResult(
            classification="high_value_repeat",
            confidence=0.85,
            booking_probability=0.9,
            suggested_reply_class="repeat_client_reply",
        )

    if is_booking:
        return IntentResult(
            classification="booking_now",
            confidence=0.8,
            booking_probability=0.8,
            suggested_reply_class="booking_now_reply",
        )

    if is_price:
        return IntentResult(
            classification="price_question",
            confidence=0.75,
            booking_probability=0.5,
            suggested_reply_class="price_question_reply",
        )

    if is_avail:
        return IntentResult(
            classification="availability_question",
            confidence=0.7,
            booking_probability=0.5,
            suggested_reply_class="booking_now_reply",
        )

    if is_location:
        return IntentResult(
            classification="location_question",
            confidence=0.7,
            booking_probability=0.4,
            suggested_reply_class="location_question_reply",
        )

    if is_repeat:
        return IntentResult(
            classification="repeat_client",
            confidence=0.7,
            booking_probability=0.6,
            suggested_reply_class="repeat_client_reply",
        )

    if text:
        return IntentResult(
            classification="unknown",
            confidence=0.3,
            booking_probability=0.2,
            suggested_reply_class="inquiry_reply",
        )

    return IntentResult(classification="unknown", confidence=0.0)


def ollama_classify(message: str, context: str = "") -> Optional[IntentResult]:
    """Use local Ollama for richer classification. Returns None if unavailable."""
    prompt = f"""Analyze this massage client message. Respond ONLY with JSON.

Message: "{message[:500]}"
Context: {context[:200]}

JSON format:
{{"classification":"booking_now|price_question|availability_question|location_question|repeat_client|high_value_repeat|ghosted_lead|do_not_contact|spam|unknown","confidence":0.0,"booking_probability":0.0,"suggested_reply_class":"booking_now_reply|price_question_reply|location_question_reply|repeat_client_reply|inquiry_reply|none","risk_flags":[]}}
"""

    try:
        body = json.dumps({
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1},
        }).encode()

        req = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
        req.timeout = 30

        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            text = data.get("response", "").strip()

            # Strip markdown fences
            if text.startswith("```"):
                text = text[3:]
                if "\n" in text:
                    text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            # Extract JSON
            if "{" in text and "}" in text:
                start = text.index("{")
                end = text.rindex("}") + 1
                text = text[start:end]

            parsed = json.loads(text)
            return IntentResult(
                classification=parsed.get("classification", "unknown"),
                confidence=float(parsed.get("confidence", 0)),
                booking_probability=float(parsed.get("booking_probability", 0)),
                suggested_reply_class=parsed.get("suggested_reply_class", ""),
                risk_flags=parsed.get("risk_flags", []),
            )
    except Exception as e:
        log.debug(f"Ollama unavailable: {e}")
        return None


def classify(message: str, context: str = "") -> IntentResult:
    """
    Classify a message. Tries Ollama first, falls back to keywords.
    """
    # Try Ollama
    result = ollama_classify(message, context)
    if result and result.confidence > 0:
        return result

    # Fallback to keywords
    return keyword_classify(message)


def classify_mailbox(emails: List[Dict]) -> List[Dict]:
    """
    Classify all mailbox conversations.
    Returns list of {username, classification, confidence, booking_probability, ...}
    """
    results = []
    for email in emails:
        uc = email.get("userCard", {})
        msg = email.get("lastMessage", "")
        username = uc.get("username", "")

        result = classify(msg, context=f"User: {username}")

        results.append({
            "username": username,
            "is_premium": bool(uc.get("isPremium", 0)),
            "unread": bool(email.get("unread", 0)),
            "classification": result.classification,
            "confidence": result.confidence,
            "booking_probability": result.booking_probability,
            "suggested_reply_class": result.suggested_reply_class,
            "risk_flags": result.risk_flags,
        })

    return results
