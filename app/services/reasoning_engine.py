"""Deterministic reasoning engine: classify, match transaction, decide verdict, route."""
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..schemas.request import TicketRequest, TransactionEntry
from ..schemas.response import CaseType, Department, EvidenceVerdict, Severity
from ..utils.text_utils import extract_amounts, normalize_text

# --------------------------------------------------------------------------
# Phone helpers
# --------------------------------------------------------------------------
_PHONE_RE = re.compile(r"(?:\+?880)?0?1[3-9]\d{8}")
_SEVERITY_ORDER = [Severity.low, Severity.medium, Severity.high, Severity.critical]
_RECENT_CUES = [
    "today", "aaj", "ajke", "this morning", "just now", "right now",
    "আজ", "আজকে", "এই সকাল", "এইমাত্র",
]
_CAMPAIGN_RECENT_CUTOFF = datetime(2026, 4, 1, tzinfo=timezone.utc)
_IMPLIED_TODAY = datetime(2026, 6, 25, tzinfo=timezone.utc)
_TXN_ID_RE = re.compile(r"\b(TXN-[A-Z0-9]+)\b", re.IGNORECASE)


def _bump(s: Severity) -> Severity:
    i = _SEVERITY_ORDER.index(s)
    return _SEVERITY_ORDER[min(i + 1, len(_SEVERITY_ORDER) - 1)]


def _normalize_phone(p: Optional[str]) -> str:
    digits = re.sub(r"\D", "", p or "")
    return digits[-10:] if len(digits) >= 10 else ""


def _extract_phones(text: str) -> List[str]:
    return [_normalize_phone(m) for m in _PHONE_RE.findall(text)]


def _cp_key(t: TransactionEntry) -> str:
    k = _normalize_phone(t.counterparty)
    return k if k else (t.counterparty or "")


def _amount_match(t: TransactionEntry, amounts: List[float]) -> bool:
    return t.amount is not None and any(abs(t.amount - a) < 0.5 for a in amounts)


def _parse_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _claims_recent(norm: str) -> bool:
    text = norm.lower()
    return any(cue in text for cue in _RECENT_CUES)


def _is_temporally_stale(
    matched: TransactionEntry,
    history: List[TransactionEntry],
    norm: str,
) -> bool:
    """Complaint says 'today' but matched txn is too old to plausibly be the same event."""
    if not _claims_recent(norm):
        return False
    mts = _parse_ts(matched.timestamp)
    if not mts:
        return False
    if mts < _CAMPAIGN_RECENT_CUTOFF:
        return True
    parsed = [_parse_ts(t.timestamp) for t in history]
    valid = [d for d in parsed if d is not None]
    if valid:
        latest = max(valid)
        if (latest - mts).days > 7:
            return True
    if _claims_recent(norm) and mts and len(valid) == 1:
        if mts > _IMPLIED_TODAY + timedelta(days=1):
            return True
    return False


def _extract_explicit_txn_ids(norm: str) -> List[str]:
    return [m.upper() for m in _TXN_ID_RE.findall(norm)]


def _find_explicit_txn(
    history: List[TransactionEntry], norm: str
) -> Optional[TransactionEntry]:
    ids = set(_extract_explicit_txn_ids(norm))
    if not ids:
        return None
    for t in history:
        if t.transaction_id and t.transaction_id.upper() in ids:
            return t
    return None


def _safe_credential_mention(text: str) -> bool:
    """Customer is warning about credentials, not reporting a phishing attack."""
    low = text.lower()
    safe_cues = [
        "should not share", "shouldn't share", "know i should not",
        "know not to share", "will not share", "won't share",
        "did not share", "don't share", "do not share", "never share",
        "not share my", "i know i should not",
    ]
    cred = any(c in low for c in ["otp", "pin", "password", "verification code", "security code"])
    return cred and any(s in low for s in safe_cues)


def _has_credential_signal(text: str) -> bool:
    low = text.lower()
    indirect = [
        "verification code", "security code", "login code", "sms code",
        "code from sms", "share a code", "code sent to my phone",
        "personal information",
    ]
    if any(p in low for p in indirect):
        return True
    return any(c in low for c in [
        "otp", "pin", "password", "passcode", "cvv", "card number",
        "ওটিপি", "পিন", "পাসওয়ার্ড",
    ])


# --------------------------------------------------------------------------
# Keyword maps (English + Banglish + Bangla)
# --------------------------------------------------------------------------
_CRED_MENTIONS = [
    "otp", "pin", "password", "passcode", "cvv", "card number",
    "ওটিপি", "পিন", "পাসওয়ার্ড",
]
_SOCIAL_CUES = [
    "call", "called", "calling", "sms", "message", "asked", "ask for", "asked for",
    "share", "click", "link", "officer", "blocked if", "block if",
    "suspicious", "stranger", "unknown number", "wanted me to",
    "ফোন", "কল", "এসএমএস", "লিংক", "বলছে", "চাইছে", "চেয়েছে", "ব্লক",
]
_STRONG_SCAM = [
    "scam", "phishing", "fishing", "fraud call", "fraud sms", "lottery",
    "won a prize", "you won", "prize", "puroskar",
    "প্রতারণা", "প্রতারক", "লটারি", "পুরস্কার",
]

_WRONG_STRONG = [
    "wrong number", "wrong recipient", "wrong person", "wrong account",
    "mistakenly sent", "sent to wrong", "by mistake", "was a mistake", "bhul number",
    "vul number", "bhul e", "accidentally sent", "accidentally", "sent to a stranger", "stranger",
    "wrong account", "to the wrong",
    "ভুল নম্বর", "ভুল মানুষ", "ভুল করে", "ভুল ব্যক্তি", "ভুলে", "অন্য নম্বর",
]
_SENT_CUES = [
    "sent", "send", "transferred", "transfer", "pathai", "pathaia", "felsi",
    "পাঠিয়েছি", "পাঠালাম", "পাঠাইছি", "পাঠিয়েছে",
]
_NOT_RECEIVED_CUES = [
    "didn't get", "did not get", "didnt get", "didn't receive",
    "did not receive", "not received", "hasn't received",
    "haven't received", "didn't reach", "did not reach",
    "পায়নি", "পাইনি", "পাননি", "পাইনাই", "আসেনি", "আসে নাই", "পৌঁছায়নি",
]

_PAYMENT_FAILED_KW = [
    "failed", "transaction failed", "payment failed",
    "did not go through", "didn't go through", "unsuccessful", "showed failed",
    "ব্যর্থ", "ফেইল", "কেটে নিয়েছে", "টাকা কেটে",
]
_REFUND_KW = [
    "refund", "money back", "return my money", "give back my money", "give me my money back",
    "ferot", "fert", "ferot pai", "ফেরত", "টাকা ফেরত",
]
_DUPLICATE_KW = [
    "twice", "two times", "double", "duplicate", "charged twice", "another",
    "deducted twice", "two payments", "dui bar", "duibar", "double charge", "extra charge",
    "sent it twice",
    "দুইবার", "দুবার", "দুই বার", "ডবল",
]
_SETTLEMENT_KW = [
    "settlement", "settled", "not settled", "settlement delay",
    "payout", "merchant account", "settle", "সেটেলমেন্ট", "সেটেল",
]
_AGENT_KW = [
    "agent", "cash in", "cash-in", "cashin", "agent point",
    "এজেন্ট", "ক্যাশ ইন", "ক্যাশইন", "ক্যাশ-ইন",
]


# --------------------------------------------------------------------------
# Case type classification
# --------------------------------------------------------------------------
def _classify(req: TicketRequest, norm: str) -> Tuple[CaseType, List[str]]:
    text = norm.lower()

    def hits(words: List[str]) -> int:
        return sum(1 for w in words if w.lower() in text)

    # Phishing: scam word OR (credential mention + social engineering cue)
    if not _safe_credential_mention(text):
        if hits(_STRONG_SCAM) > 0 or (
            _has_credential_signal(text) and hits(_SOCIAL_CUES) > 0
        ):
            return CaseType.phishing_or_social_engineering, ["phishing_signal"]
        if _has_credential_signal(text) and any(
            w in text for w in ("gave it", "gave both", "i gave", "shared", "share a code")
        ):
            return CaseType.phishing_or_social_engineering, ["phishing_signal"]

    scores: Dict[CaseType, int] = {ct: 0 for ct in CaseType}
    scores[CaseType.wrong_transfer] = hits(_WRONG_STRONG) * 2
    if hits(_SENT_CUES) > 0 and hits(_NOT_RECEIVED_CUES) > 0:
        scores[CaseType.wrong_transfer] += 2
    scores[CaseType.duplicate_payment] = hits(_DUPLICATE_KW) * 2
    scores[CaseType.merchant_settlement_delay] = hits(_SETTLEMENT_KW) * 2
    scores[CaseType.payment_failed] = hits(_PAYMENT_FAILED_KW) * 2
    scores[CaseType.agent_cash_in_issue] = hits(_AGENT_KW) * 2
    scores[CaseType.refund_request] = hits(_REFUND_KW) * 1

    if req.user_type == "merchant" or req.channel == "merchant_portal":
        scores[CaseType.merchant_settlement_delay] += 1
    if req.user_type == "agent" or req.channel == "field_agent":
        scores[CaseType.agent_cash_in_issue] += 1

    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        return CaseType.other, ["no_clear_signal"]
    top_score = scores[best]
    tied = [ct for ct, sc in scores.items() if sc == top_score and sc > 0]
    if CaseType.duplicate_payment in tied and CaseType.payment_failed in tied:
        return CaseType.duplicate_payment, [CaseType.duplicate_payment.value]
    if CaseType.wrong_transfer in tied and CaseType.duplicate_payment in tied:
        if any(w in text for w in ("mistake", "wrong", "accidentally", "extra", "reverse")):
            return CaseType.wrong_transfer, [CaseType.wrong_transfer.value]
    if CaseType.wrong_transfer in tied and CaseType.refund_request in tied:
        return CaseType.wrong_transfer, [CaseType.wrong_transfer.value]
    if CaseType.payment_failed in tied and CaseType.refund_request in tied:
        if hits(_PAYMENT_FAILED_KW) > 0:
            return CaseType.payment_failed, [CaseType.payment_failed.value]
    return best, [best.value]


# --------------------------------------------------------------------------
# Transaction matching
# --------------------------------------------------------------------------
def _best_match(
    history: List[TransactionEntry],
    amounts: List[float],
    phones: List[str],
    types: set,
) -> Optional[TransactionEntry]:
    best, best_score = None, 0
    for t in history:
        s = 0
        if _amount_match(t, amounts):
            s += 3
        if _normalize_phone(t.counterparty) and _normalize_phone(t.counterparty) in phones:
            s += 3
        if t.type in types:
            s += 1
        if s > best_score:
            best_score, best = s, t
    if best_score >= 1:
        return best
    if len(history) == 1:
        return history[0]
    return None


def _investigate_wrong_transfer(
    history: List[TransactionEntry],
    amounts: List[float],
    phones: List[str],
    norm: str,
) -> Tuple[Optional[TransactionEntry], EvidenceVerdict, List[str]]:
    transfers = [t for t in history if t.type in ("transfer", "payment")]
    amt_cands = [t for t in transfers if _amount_match(t, amounts)]

    if phones:
        ph = [t for t in transfers if _normalize_phone(t.counterparty) in phones]
        candidates = ph or amt_cands
    else:
        candidates = amt_cands

    # De-dup by transaction_id
    seen: set = set()
    distinct: List[TransactionEntry] = []
    for t in candidates:
        if t.transaction_id not in seen:
            seen.add(t.transaction_id)
            distinct.append(t)

    if not distinct:
        if len(history) == 1 and history[0].type in ("transfer", "payment"):
            distinct = [history[0]]
        else:
            return None, EvidenceVerdict.insufficient_data, ["no_match"]

    if len(distinct) >= 2:
        return None, EvidenceVerdict.insufficient_data, ["ambiguous_match"]

    matched = distinct[0]
    if _is_temporally_stale(matched, history, norm):
        return None, EvidenceVerdict.insufficient_data, ["temporal_mismatch", "no_recent_transaction_found"]

    occurrences = sum(1 for t in history if _cp_key(t) == _cp_key(matched))
    status = (matched.status or "").lower()

    if occurrences >= 2:
        return matched, EvidenceVerdict.inconsistent, ["established_recipient_pattern"]
    if status == "completed":
        return matched, EvidenceVerdict.consistent, ["transaction_match"]
    if status in ("failed", "reversed"):
        return matched, EvidenceVerdict.inconsistent, ["not_completed"]
    return matched, EvidenceVerdict.insufficient_data, ["pending"]


def _merchant_hints(norm: str) -> List[str]:
    text = norm.lower()
    hints: List[str] = []
    mapping = {
        "robi": "ROBI",
        "desco": "DESCO",
        "electricity": "DESCO",
        "internet": "ISP",
        "বিদ্যুৎ": "DESCO",
        "রবি": "ROBI",
    }
    for key, token in mapping.items():
        if key in text:
            hints.append(token)
    return hints


def _investigate_payment_failed(
    history: List[TransactionEntry],
    amounts: List[float],
    phones: List[str],
    norm: str,
) -> Tuple[Optional[TransactionEntry], EvidenceVerdict, List[str]]:
    explicit = _find_explicit_txn(history, norm)
    if explicit is not None:
        status = (explicit.status or "").lower() if explicit.status else ""
        if not status:
            return explicit, EvidenceVerdict.insufficient_data, ["null_fields_in_transaction"]
        if status == "failed":
            return explicit, EvidenceVerdict.consistent, ["payment_failed", "transaction_id_mentioned"]
        if status == "completed":
            return explicit, EvidenceVerdict.inconsistent, ["actually_succeeded"]
        return explicit, EvidenceVerdict.insufficient_data, ["pending"]

    hints = _merchant_hints(norm)
    best, best_score = None, -1
    for t in history:
        if t.type not in ("payment", "transfer"):
            continue
        score = 0
        if _amount_match(t, amounts):
            score += 3
        if _normalize_phone(t.counterparty) and _normalize_phone(t.counterparty) in phones:
            score += 3
        cp = (t.counterparty or "").upper()
        for hint in hints:
            if hint in cp:
                score += 5
        if t.type == "payment":
            score += 2
        if (t.status or "").lower() == "failed":
            score += 2
        if score > best_score:
            best_score, best = score, t

    if best is None or best_score < 1:
        if len(history) == 1:
            only = history[0]
            status = (only.status or "").lower() if only.status else ""
            if not status:
                return only, EvidenceVerdict.insufficient_data, ["null_fields_in_transaction"]
        return None, EvidenceVerdict.insufficient_data, ["no_match"]

    status = (best.status or "").lower() if best.status else ""
    if not status:
        return best, EvidenceVerdict.insufficient_data, ["null_fields_in_transaction"]
    if status == "failed":
        return best, EvidenceVerdict.consistent, ["payment_failed"]
    if status == "completed":
        return best, EvidenceVerdict.inconsistent, ["actually_succeeded"]
    return best, EvidenceVerdict.insufficient_data, ["pending"]


def _investigate_duplicate(
    history: List[TransactionEntry], amounts: List[float], phones: List[str]
) -> Tuple[Optional[TransactionEntry], EvidenceVerdict, List[str]]:
    groups: Dict[Any, List[TransactionEntry]] = defaultdict(list)
    for t in history:
        if t.type in ("payment", "transfer"):
            groups[(_cp_key(t), t.amount, t.type)].append(t)

    dup = None
    for k, v in groups.items():
        if len(v) >= 2 and ((not amounts) or k[1] in amounts):
            dup = v
            break
    if dup is None:
        for k, v in groups.items():
            if len(v) >= 2:
                dup = v
                break

    if dup:
        dup_sorted = sorted(dup, key=lambda t: t.timestamp or "")
        return dup_sorted[-1], EvidenceVerdict.consistent, ["duplicate_confirmed"]

    m = _best_match(history, amounts, phones, {"payment", "transfer"})
    if m:
        return m, EvidenceVerdict.inconsistent, ["single_charge_only"]
    return None, EvidenceVerdict.insufficient_data, ["no_match"]


def _investigate(
    req: TicketRequest,
    case_type: CaseType,
    amounts: List[float],
    phones: List[str],
) -> Tuple[Optional[TransactionEntry], EvidenceVerdict, List[str]]:
    history = req.transaction_history or []

    if case_type == CaseType.phishing_or_social_engineering:
        completed = [
            t for t in history
            if t.type in ("transfer", "payment") and (t.status or "").lower() == "completed"
        ]
        if len(completed) >= 2:
            return None, EvidenceVerdict.insufficient_data, [
                "safety_report", "multiple_unauthorized_transfers"
            ]
        m = _find_explicit_txn(history, normalize_text(req.complaint or ""))
        if m is None:
            m = _best_match(history, amounts, phones, {"transfer", "payment"})
        if m:
            return m, EvidenceVerdict.consistent, ["safety_report", "linked_fraud_txn"]
        return None, EvidenceVerdict.insufficient_data, ["safety_report"]

    if not history:
        return None, EvidenceVerdict.insufficient_data, ["no_history"]

    if case_type == CaseType.wrong_transfer:
        return _investigate_wrong_transfer(history, amounts, phones, normalize_text(req.complaint or ""))

    if case_type == CaseType.duplicate_payment:
        return _investigate_duplicate(history, amounts, phones)

    if case_type == CaseType.payment_failed:
        return _investigate_payment_failed(
            history, amounts, phones, normalize_text(req.complaint or "")
        )

    if case_type == CaseType.refund_request:
        m = _best_match(history, amounts, phones, {"payment", "transfer", "refund"})
        if not m:
            return None, EvidenceVerdict.insufficient_data, ["no_match"]
        s = (m.status or "").lower()
        if s == "reversed":
            return m, EvidenceVerdict.inconsistent, ["already_reversed"]
        return m, EvidenceVerdict.consistent, ["underlying_txn_found"]

    if case_type == CaseType.merchant_settlement_delay:
        m = _best_match(history, amounts, phones, {"settlement", "payment"})
        if m and m.type == "settlement":
            s = (m.status or "").lower()
            if s in ("pending", "failed"):
                return m, EvidenceVerdict.consistent, ["settlement_pending"]
            if s == "completed":
                return m, EvidenceVerdict.inconsistent, ["already_settled"]
        return (m, EvidenceVerdict.insufficient_data, ["no_settlement"]) if m \
            else (None, EvidenceVerdict.insufficient_data, ["no_match"])

    if case_type == CaseType.agent_cash_in_issue:
        m = _best_match(history, amounts, phones, {"cash_in"})
        if m and m.type == "cash_in":
            s = (m.status or "").lower()
            if s in ("failed", "pending"):
                return m, EvidenceVerdict.consistent, ["cash_in_not_credited"]
            if s == "completed":
                return m, EvidenceVerdict.inconsistent, ["cash_in_completed"]
        return None, EvidenceVerdict.insufficient_data, ["no_cash_in", "type_mismatch"]

    return None, EvidenceVerdict.insufficient_data, ["no_match"]


# --------------------------------------------------------------------------
# Severity, department, human review
# --------------------------------------------------------------------------
def _assess_severity(
    case_type: CaseType,
    verdict: EvidenceVerdict,
    matched: Optional[TransactionEntry],
    amounts: List[float],
) -> Severity:
    if case_type == CaseType.phishing_or_social_engineering:
        return Severity.critical
    if case_type == CaseType.wrong_transfer:
        sev = Severity.high if verdict == EvidenceVerdict.consistent else Severity.medium
        amt = (matched.amount if matched and matched.amount else None) or (
            max(amounts) if amounts else 0
        )
        if amt and amt >= 50000:
            return Severity.critical
        return sev

    if case_type == CaseType.refund_request:
        if verdict == EvidenceVerdict.inconsistent:
            return Severity.medium
        return Severity.low

    if case_type == CaseType.payment_failed:
        if verdict == EvidenceVerdict.insufficient_data:
            if matched is not None:
                return Severity.high
            return Severity.low
        amt = (matched.amount if matched and matched.amount else None) or (
            max(amounts) if amounts else 0
        )
        if amt and 300 <= amt < 500:
            return Severity.low
        if amt and amt == 500:
            return Severity.medium
        return Severity.high

    if case_type == CaseType.agent_cash_in_issue and verdict == EvidenceVerdict.insufficient_data:
        return Severity.medium

    base = {
        CaseType.duplicate_payment: Severity.high,
        CaseType.merchant_settlement_delay: Severity.medium,
        CaseType.agent_cash_in_issue: Severity.high,
        CaseType.other: Severity.low,
    }.get(case_type, Severity.low)

    amt = (matched.amount if matched and matched.amount else None) or (max(amounts) if amounts else 0)
    if amt and amt >= 50000 and base in (Severity.medium, Severity.high):
        base = _bump(base)
    return base


def _route_department(
    case_type: CaseType, severity: Severity, verdict: EvidenceVerdict
) -> Department:
    if case_type == CaseType.refund_request:
        if verdict == EvidenceVerdict.inconsistent:
            return Department.dispute_resolution
        if severity == Severity.low or verdict == EvidenceVerdict.insufficient_data:
            return Department.customer_support
        return Department.dispute_resolution
    if case_type == CaseType.other:
        return Department.customer_support
    return {
        CaseType.wrong_transfer: Department.dispute_resolution,
        CaseType.payment_failed: Department.payments_ops,
        CaseType.duplicate_payment: Department.payments_ops,
        CaseType.merchant_settlement_delay: Department.merchant_operations,
        CaseType.agent_cash_in_issue: Department.agent_operations,
        CaseType.phishing_or_social_engineering: Department.fraud_risk,
    }[case_type]


def _needs_review(
    case_type: CaseType,
    relevant_id: Optional[str],
    verdict: EvidenceVerdict,
) -> bool:
    if verdict == EvidenceVerdict.inconsistent:
        return True
    if case_type == CaseType.wrong_transfer:
        return relevant_id is not None
    if case_type == CaseType.agent_cash_in_issue:
        return relevant_id is not None
    return case_type in (
        CaseType.duplicate_payment,
        CaseType.phishing_or_social_engineering,
    )


def _confidence(
    case_type: CaseType, verdict: EvidenceVerdict
) -> float:
    base = {
        EvidenceVerdict.consistent: 0.9,
        EvidenceVerdict.inconsistent: 0.75,
        EvidenceVerdict.insufficient_data: 0.62,
    }[verdict]
    if case_type == CaseType.phishing_or_social_engineering:
        base = 0.95
    elif case_type == CaseType.refund_request and verdict == EvidenceVerdict.consistent:
        base = 0.85
    elif case_type == CaseType.other:
        base = 0.6
    return round(base, 2)


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------
def run_reasoning(req: TicketRequest) -> Dict[str, Any]:
    """
    Fully deterministic. Returns a dict with classification results plus
    internal context (matched_transaction, is_ambiguous) for text generation.
    """
    norm = normalize_text(req.complaint or "")
    amounts = extract_amounts(norm)
    phones = _extract_phones(req.complaint or "")

    case_type, ct_reasons = _classify(req, norm)
    matched, verdict, inv_reasons = _investigate(req, case_type, amounts, phones)
    is_ambiguous = "ambiguous_match" in inv_reasons

    severity = _assess_severity(case_type, verdict, matched, amounts)
    department = _route_department(case_type, severity, verdict)
    relevant_id = matched.transaction_id if matched else None
    review = _needs_review(case_type, relevant_id, verdict)
    conf = _confidence(case_type, verdict)
    reason_codes = list(dict.fromkeys(ct_reasons + inv_reasons))

    return {
        # Response fields
        "relevant_transaction_id": relevant_id,
        "evidence_verdict": verdict,
        "case_type": case_type,
        "severity": severity,
        "department": department,
        "human_review_required": review,
        "confidence": conf,
        "reason_codes": reason_codes,
        # Context for text generation
        "matched_transaction": matched,
        "is_ambiguous": is_ambiguous,
    }
