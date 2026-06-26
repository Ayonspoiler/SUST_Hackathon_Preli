import re
from typing import List, Optional

# Bangla digit normalization: "২০০০" → "2000"
_BN_DIGITS = {ord(b): a for b, a in zip("০১২৩৪৫৬৭৮৯", "0123456789")}

# Phone number pattern for BD numbers
_PHONE_RE = re.compile(r"(?:\+?880)?0?1[3-9]\d{8}")

INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all instructions",
    "forget your instructions",
    "disregard your",
    "act as ",
    "pretend to be",
    "you are now",
    "system:",
    "<prompt>",
    "</prompt>",
    "override",
    "new instructions",
    "jailbreak",
    "dan mode",
]


def normalize_text(text: str) -> str:
    """Lowercase, normalize Bangla digits, collapse whitespace."""
    t = (text or "").translate(_BN_DIGITS)
    return re.sub(r"\s+", " ", t).strip()


def extract_amounts(norm_text: str) -> List[float]:
    """Extract numeric amounts from complaint text (after phone numbers are masked)."""
    cleaned = _PHONE_RE.sub(" ", norm_text)
    out = []
    for raw in re.findall(r"\d[\d,]*(?:\.\d+)?", cleaned):
        try:
            out.append(float(raw.replace(",", "")))
        except ValueError:
            pass
    return [a for a in out if a >= 1]


def extract_time_hour(text: str) -> Optional[int]:
    """Parse a time mention from complaint text. Returns 24h hour or None."""
    text = text.lower()
    # 12h: "2pm", "2 pm", "2:30pm"
    m = re.search(r"\b(\d{1,2})(?::\d{2})?\s*(am|pm)\b", text)
    if m:
        h = int(m.group(1))
        period = m.group(2)
        if period == "pm" and h != 12:
            h += 12
        elif period == "am" and h == 12:
            h = 0
        return h % 24
    # 24h: "14:08", "14:30"
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
    if m:
        return int(m.group(1)) % 24
    return None


def detect_prompt_injection(text: str) -> bool:
    """Return True if the text contains common prompt injection patterns."""
    lower = (text or "").lower()
    return any(p in lower for p in INJECTION_PATTERNS)
