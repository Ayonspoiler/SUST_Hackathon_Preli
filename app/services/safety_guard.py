"""Safety guard: pre-scan for injection, post-filter unsafe LLM output."""
import logging
import re
from typing import List, Tuple

from ..utils.text_utils import detect_prompt_injection

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Credential safety
# --------------------------------------------------------------------------
_CRED_WORDS = [
    "otp", "pin", "password", "passcode", "cvv", "card number", "card no",
    "ওটিপি", "পিন", "পাসওয়ার্ড",
]
_REQUEST_VERBS = [
    "share", "send", "provide", "give", "tell", "enter", "type",
    "confirm your", "what is your", "what's your",
]
_NEG_CUES = [
    "not", "never", "don't", "do not", "dont", "won't", "without", "avoid",
    "kindly do not", "not to share", "na ", "না", "কখনো", "শেয়ার করবেন না",
]

# --------------------------------------------------------------------------
# Refund / reversal confirmation patterns
# --------------------------------------------------------------------------
_REFUND_PATTERNS = [
    r"\bwe (will|have|are going to|are) refund(ed|ing)?\b",
    r"\brefund (has been|is|will be) (processed|completed|issued|done|given)\b",
    r"\bwe (will|have) revers(e|ed)\b",
    r"\bwe (will|have) return(ed)? your money\b",
    r"\byour (money|amount|refund) (has been|is) (refunded|returned|processed)\b",
    r"\byour account (is|has been) (now )?(unblocked|unlocked|restored)\b",
]
_SAFE_REFUND = "any eligible amount will be returned through official channels"

# --------------------------------------------------------------------------
# Third-party direction patterns
# --------------------------------------------------------------------------
_THIRD_PARTY_PATTERNS = [
    r"https?://\S+",
    r"\bcall (this|that|the following) number\b",
    r"\bcontact (this|that) (agent|person|number|link)\b",
]
_SAFE_CHANNEL = "please use only our official support app or verified helpline"

_SAFE_PIN_EN = "Please do not share your PIN or OTP with anyone."
_SAFE_PIN_BN = "অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না।"

_SENT_SPLIT = re.compile(r"(?<=[.!?।])\s+")


def _standardize_pin_warnings(text: str) -> Tuple[str, bool]:
    """Rewrite any PIN/OTP mention in customer-facing text to the approved warning."""
    if not re.search(r"\b(pin|otp|password|পিন|ওটিপি)\b", text, re.IGNORECASE):
        return text, False

    kept: List[str] = []
    for sentence in _SENT_SPLIT.split(text):
        if re.search(r"\b(pin|otp|password|পিন|ওটিপি)\b", sentence, re.IGNORECASE):
            continue
        if sentence.strip():
            kept.append(sentence.strip())

    body = " ".join(kept).strip()
    if body and body[-1] not in ".!?।":
        body += "."
    warning = _SAFE_PIN_BN if re.search(r"[\u0980-\u09FF]", text) else _SAFE_PIN_EN
    merged = f"{body} {warning}".strip() if body else warning
    return merged, merged != text


def _sanitize_credentials(text: str) -> Tuple[str, bool]:
    changed = False
    parts = []
    for sentence in _SENT_SPLIT.split(text):
        low = sentence.lower()
        if any(c in low for c in _CRED_WORDS):
            has_neg = any(n in low for n in _NEG_CUES)
            has_req = any(v in low for v in _REQUEST_VERBS)
            if has_req and not has_neg:
                sentence = (
                    "For your security, please verify your identity only "
                    "through our official secure support channels."
                )
                changed = True
        parts.append(sentence)
    return " ".join(parts), changed


def _strip_credential_sentences(text: str) -> Tuple[str, bool]:
    """Remove agent-facing sentences that mention sharing PIN/OTP."""
    kept: List[str] = []
    changed = False
    for sentence in _SENT_SPLIT.split(text):
        low = sentence.lower()
        if re.search(r"\b(pin|otp|password|পিন|ওটিপি)\b", low) and re.search(
            r"share|provide|send|give|advise", low
        ):
            changed = True
            continue
        if sentence.strip():
            kept.append(sentence.strip())
    return " ".join(kept).strip(), changed


def _sanitize_text(text: str, *, customer_facing: bool = False) -> Tuple[str, List[str]]:
    flags: List[str] = []
    t, cred_changed = _sanitize_credentials(text)
    if cred_changed:
        flags.append("stripped_credential_request")
    if customer_facing:
        t, pin_changed = _standardize_pin_warnings(t)
        if pin_changed:
            flags.append("standardized_pin_warning")
    else:
        t, stripped = _strip_credential_sentences(t)
        if stripped:
            flags.append("stripped_admin_credential_sentence")
    for pat in _REFUND_PATTERNS:
        if re.search(pat, t, re.IGNORECASE):
            flags.append("softened_refund_language")
            t = re.sub(pat, _SAFE_REFUND, t, flags=re.IGNORECASE)
    for pat in _THIRD_PARTY_PATTERNS:
        if re.search(pat, t, re.IGNORECASE):
            flags.append("removed_third_party_direction")
            t = re.sub(pat, _SAFE_CHANNEL, t, flags=re.IGNORECASE)
    return t, list(dict.fromkeys(flags))


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
def pre_scan(complaint: str) -> None:
    """Detect prompt injection in the complaint; log a warning if found."""
    if detect_prompt_injection(complaint):
        logger.warning("Prompt injection pattern detected in complaint (treating as data).")


def has_unsafe_credential_language(text: str) -> bool:
    """Detect credential-request phrasing that must not appear in customer-facing output."""
    combined = (text or "").lower()
    for sentence in _SENT_SPLIT.split(combined):
        if any(n in sentence for n in _NEG_CUES):
            continue
        if re.search(
            r"(please )?(share|provide|send|give|tell|enter) (us )?(your )?(pin|otp|password)",
            sentence,
        ):
            return True
    return False


def post_filter(
    customer_reply: str,
    recommended_next_action: str,
    agent_summary: str,
) -> Tuple[str, str, str, List[str]]:
    """
    Sanitize the three text fields.
    Returns (customer_reply, recommended_next_action, agent_summary, combined_flags).
    """
    cr, f1 = _sanitize_text(customer_reply, customer_facing=True)
    na, f2 = _sanitize_text(recommended_next_action)
    ag, f3 = _sanitize_text(agent_summary)
    all_flags = list(dict.fromkeys(f1 + f2 + f3))
    return cr, na, ag, all_flags
