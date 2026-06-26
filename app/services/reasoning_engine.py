"""Deterministic reasoning engine: classify, match transaction, decide verdict, route."""
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from ..schemas.request import TicketRequest, TransactionEntry
from ..schemas.response import CaseType, Department, EvidenceVerdict, Severity
from ..utils.text_utils import extract_amounts, normalize_text

# --------------------------------------------------------------------------
# Phone helpers
# --------------------------------------------------------------------------
_PHONE_RE = re.compile(r"(?:\+?880)?0?1[3-9]\d{8}")
_SEVERITY_ORDER = [Severity.low, Severity.medium, Severity.high, Severity.critical]


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


def _cp_score(counterparty: Optional[str], norm_text: str) -> int:
    """Return bonus score if any meaningful token from counterparty appears in complaint."""
    if not counterparty or not norm_text:
        return 0
    parts = re.split(r"[-_/\s]", counterparty.lower())
    for part in parts:
        if len(part) >= 4 and part in norm_text.lower():
            return 2
    return 0


# --------------------------------------------------------------------------
# Keyword maps (English + Banglish + Bangla)
# --------------------------------------------------------------------------
_CRED_MENTIONS = [
    "otp", "pin", "password", "passcode", "cvv", "card number",
    "ওটিপি", "পিন", "পাসওয়ার্ড",
]
_SOCIAL_CUES = [
    "call", "called", "calling", "sms", "message", "asked", "ask for",
    "share", "click", "link", "officer", "blocked if", "block if",
    "suspicious", "unknown number", "impersonat",
    "ফোন", "কল", "এসএমএস", "লিংক", "বলছে", "চাইছে", "চেয়েছে", "ব্লক",
]
_STRONG_SCAM = [
    "scam", "phishing", "fishing", "fraud call", "fraud sms", "lottery",
    "won a prize", "you won", "prize", "puroskar",
    "প্রতারণা", "প্রতারক", "লটারি", "পুরস্কার",
]

_WRONG_STRONG = [
    # English
    "wrong number", "wrong recipient", "wrong person", "wrong account",
    "wrong bkash", "wrong mobile",
    "mistakenly sent", "mistakenly transferred",
    "sent to wrong", "transferred to wrong", "sent by mistake",
    "sent to the wrong", "transferred to the wrong",
    "by mistake", "accidentally sent", "accidentally transferred",
    "to a stranger", "to an unknown", "to wrong person",
    "to unknown person", "to unknown number",
    # Banglish
    "bhul number", "vul number", "bhul e", "bhul nambor",
    "vul nambor", "galti te", "wrong e pathiye",
    # Bangla
    "ভুল নম্বর", "ভুল মানুষ", "ভুল করে", "ভুল ব্যক্তি",
    "ভুলে", "অন্য নম্বর", "অচেনা", "ভুল মানুষে",
    "ভুল একাউন্ট", "অন্য ব্যক্তি",
]
_SENT_CUES = [
    "sent", "send", "transferred", "transfer", "pathai", "diye diyechi",
    "পাঠিয়েছি", "পাঠালাম", "পাঠাইছি", "পাঠিয়েছে",
    "পাঠিয়ে দিয়েছি", "পাঠিয়ে দিলাম", "দিয়েছি",
]
_NOT_RECEIVED_CUES = [
    "didn't get", "did not get", "didnt get", "didn't receive",
    "did not receive", "not received", "hasn't received",
    "haven't received", "didn't reach", "did not reach",
    "she did not receive", "he did not receive", "they did not receive",
    "পায়নি", "পাইনি", "পাননি", "পাইনাই", "আসেনি", "আসে নাই", "পৌঁছায়নি",
]

_PAYMENT_FAILED_KW = [
    "failed", "transaction failed", "payment failed",
    "did not go through", "didn't go through", "unsuccessful", "showed failed",
    "could not", "couldn't", "not successful", "rejected",
    "balance deducted", "deducted", "money deducted",
    "ব্যর্থ", "ফেইল", "কেটে নিয়েছে", "টাকা কেটে", "হয়নি",
]
_REFUND_KW = [
    "refund", "money back", "return my money", "give back my money",
    "get it back", "ferot", "fert", "ফেরত", "টাকা ফেরত",
]
_DUPLICATE_KW = [
    "twice", "two times", "double", "duplicate", "charged twice",
    "deducted twice", "two payments", "dui bar", "duibar", "double charge",
    "same payment", "charged again", "billed twice",
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

    # Phishing: explicit scam word OR (credential mention + social engineering cue)
    if hits(_STRONG_SCAM) > 0 or (hits(_CRED_MENTIONS) > 0 and hits(_SOCIAL_CUES) > 0):
        return CaseType.phishing_or_social_engineering, ["phishing_signal"]

    scores: Dict[CaseType, int] = {ct: 0 for ct in CaseType}

    # Wrong transfer — strong keywords score 2 each
    scores[CaseType.wrong_transfer] = hits(_WRONG_STRONG) * 2
    # sent + not-received is also a strong wrong-transfer signal
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
    return best, [best.value]


# --------------------------------------------------------------------------
# Transaction matching
# --------------------------------------------------------------------------
def _best_match(
    history: List[TransactionEntry],
    amounts: List[float],
    phones: List[str],
    types: set,
    norm_text: str = "",
    prefer_status: str = "",
) -> Optional[TransactionEntry]:
    """
    Score each transaction and return the best match.
    Scoring:
      +3  amount matches complaint
      +3  counterparty phone matches a phone in complaint
      +1  transaction type is in expected types set
      +2  counterparty keyword appears in complaint text
      +1  transaction status matches prefer_status (tiebreaker)
    Falls back to the single history entry only when there is at least
    one signal (amount or phone) linking it to the complaint.
    """
    best, best_score = None, 0
    for t in history:
        s = 0
        if _amount_match(t, amounts):
            s += 3
        if _normalize_phone(t.counterparty) and _normalize_phone(t.counterparty) in phones:
            s += 3
        if t.type in types:
            s += 1
        s += _cp_score(t.counterparty, norm_text)
        if prefer_status and (t.status or "").lower() == prefer_status:
            s += 1
        if s > best_score:
            best_score, best = s, t

    if best_score >= 1:
        return best
    # Fallback: single entry only when there is a signal to link it
    if len(history) == 1 and (amounts or phones):
        return history[0]
    return None


# --------------------------------------------------------------------------
# Investigation helpers
# --------------------------------------------------------------------------
def _investigate_wrong_transfer(
    history: List[TransactionEntry],
    amounts: List[float],
    phones: List[str],
    norm_text: str,
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
        # Only use single-entry fallback when there is a signal linking it
        if len(history) == 1 and history[0].type in ("transfer", "payment") and (amounts or phones):
            distinct = [history[0]]
        else:
            return None, EvidenceVerdict.insufficient_data, ["no_match"]

    if len(distinct) >= 2:
        # Try counterparty keyword to break the tie
        scored = [(t, _cp_score(t.counterparty, norm_text)) for t in distinct]
        top_score = max(s for _, s in scored)
        if top_score > 0:
            top = [t for t, s in scored if s == top_score]
            if len(top) == 1:
                distinct = top
            else:
                return None, EvidenceVerdict.insufficient_data, ["ambiguous_match"]
        else:
            return None, EvidenceVerdict.insufficient_data, ["ambiguous_match"]

    matched = distinct[0]
    occurrences = sum(1 for t in history if _cp_key(t) == _cp_key(matched))
    status = (matched.status or "").lower()

    if occurrences >= 2:
        return matched, EvidenceVerdict.inconsistent, ["established_recipient_pattern"]
    if status == "completed":
        return matched, EvidenceVerdict.consistent, ["transaction_match"]
    if status in ("failed", "reversed"):
        return matched, EvidenceVerdict.inconsistent, ["not_completed"]
    return matched, EvidenceVerdict.insufficient_data, ["pending"]


def _investigate_duplicate(
    history: List[TransactionEntry],
    amounts: List[float],
    phones: List[str],
    norm_text: str,
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

    m = _best_match(history, amounts, phones, {"payment", "transfer"}, norm_text)
    if m:
        return m, EvidenceVerdict.inconsistent, ["single_charge_only"]
    return None, EvidenceVerdict.insufficient_data, ["no_match"]


def _investigate(
    req: TicketRequest,
    case_type: CaseType,
    amounts: List[float],
    phones: List[str],
    norm_text: str,
) -> Tuple[Optional[TransactionEntry], EvidenceVerdict, List[str]]:
    history = req.transaction_history or []

    if case_type == CaseType.phishing_or_social_engineering:
        if not history:
            return None, EvidenceVerdict.insufficient_data, ["safety_report"]
        # Look for a matching transaction — e.g., an unauthorized transfer that followed OTP theft
        m = _best_match(history, amounts, phones, {"transfer", "payment"}, norm_text)
        if m:
            return m, EvidenceVerdict.consistent, ["linked_transaction_found"]
        return None, EvidenceVerdict.insufficient_data, ["safety_report"]

    if not history:
        return None, EvidenceVerdict.insufficient_data, ["no_history"]

    if case_type == CaseType.wrong_transfer:
        return _investigate_wrong_transfer(history, amounts, phones, norm_text)

    if case_type == CaseType.duplicate_payment:
        return _investigate_duplicate(history, amounts, phones, norm_text)

    if case_type == CaseType.payment_failed:
        m = _best_match(
            history, amounts, phones, {"payment", "transfer"},
            norm_text, prefer_status="failed",
        )
        if not m:
            return None, EvidenceVerdict.insufficient_data, ["no_match"]
        s = (m.status or "").lower()
        if s == "failed":
            return m, EvidenceVerdict.consistent, ["payment_failed"]
        if s == "completed":
            return m, EvidenceVerdict.inconsistent, ["actually_succeeded"]
        return m, EvidenceVerdict.insufficient_data, ["pending"]

    if case_type == CaseType.refund_request:
        m = _best_match(history, amounts, phones, {"payment", "transfer", "refund"}, norm_text)
        if not m:
            return None, EvidenceVerdict.insufficient_data, ["no_match"]
        s = (m.status or "").lower()
        if s == "reversed":
            # Refund may have already been processed
            return m, EvidenceVerdict.inconsistent, ["already_reversed"]
        return m, EvidenceVerdict.consistent, ["underlying_txn_found"]

    if case_type == CaseType.merchant_settlement_delay:
        m = _best_match(history, amounts, phones, {"settlement", "payment"}, norm_text)
        if m and m.type == "settlement":
            s = (m.status or "").lower()
            if s in ("pending", "failed"):
                return m, EvidenceVerdict.consistent, ["settlement_pending"]
            if s == "completed":
                return m, EvidenceVerdict.inconsistent, ["already_settled"]
        return (m, EvidenceVerdict.insufficient_data, ["no_settlement"]) if m \
            else (None, EvidenceVerdict.insufficient_data, ["no_match"])

    if case_type == CaseType.agent_cash_in_issue:
        m = _best_match(history, amounts, phones, {"cash_in"}, norm_text)
        if m and m.type == "cash_in":
            s = (m.status or "").lower()
            if s in ("failed", "pending"):
                return m, EvidenceVerdict.consistent, ["cash_in_not_credited"]
            if s == "completed":
                return m, EvidenceVerdict.inconsistent, ["cash_in_completed"]
        # Found a transaction but it's the wrong type (e.g., a transfer instead of cash_in)
        if m:
            return None, EvidenceVerdict.insufficient_data, ["type_mismatch"]
        return None, EvidenceVerdict.insufficient_data, ["no_match"]

    return None, EvidenceVerdict.insufficient_data, ["no_match"]


# --------------------------------------------------------------------------
# Severity, department, human review
# --------------------------------------------------------------------------
def _amount_tier(amt: float) -> Severity:
    """Map a BDT amount to a base severity tier."""
    if amt >= 50000:
        return Severity.critical
    if amt >= 2000:
        return Severity.high
    if amt >= 500:
        return Severity.medium
    return Severity.low


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
        amt = (matched.amount if matched else None) or (max(amounts) if amounts else 0)
        if amt and amt >= 50000:
            sev = Severity.critical
        return sev

    amt = (matched.amount if matched else None) or (max(amounts) if amounts else 0)

    if case_type == CaseType.payment_failed:
        base = _amount_tier(amt) if amt else Severity.low
        return base

    if case_type == CaseType.refund_request:
        if not amt:
            return Severity.low
        if amt >= 50000:
            return Severity.critical
        if amt >= 10000:
            return Severity.high
        if amt >= 500:
            return Severity.medium
        return Severity.low

    if case_type == CaseType.duplicate_payment:
        base = Severity.high
        if amt and amt >= 50000:
            base = Severity.critical
        return base

    if case_type == CaseType.merchant_settlement_delay:
        # Inconsistent means platform says settled but merchant disagrees — escalate
        if verdict == EvidenceVerdict.inconsistent:
            return Severity.high
        return Severity.medium

    if case_type == CaseType.agent_cash_in_issue:
        # Only high when we have confirmed evidence of the issue
        if verdict == EvidenceVerdict.consistent:
            return Severity.high
        return Severity.medium

    return Severity.low  # CaseType.other and fallback


def _route_department(
    case_type: CaseType, severity: Severity, verdict: EvidenceVerdict
) -> Department:
    if case_type == CaseType.refund_request:
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
    # Contradictory evidence always needs a human to reconcile
    if verdict == EvidenceVerdict.inconsistent:
        return True

    # Phishing is always a human-escalation case
    if case_type == CaseType.phishing_or_social_engineering:
        return True

    # Duplicate payments need verification before any reversal
    if case_type == CaseType.duplicate_payment:
        return True

    # Wrong transfers and cash-in issues: only when a transaction is identified
    if case_type in (CaseType.wrong_transfer, CaseType.agent_cash_in_issue):
        return relevant_id is not None

    # Refund requests need review when a transaction is linked
    if case_type == CaseType.refund_request and relevant_id is not None:
        return True

    return False


def _confidence(
    case_type: CaseType, verdict: EvidenceVerdict
) -> float:
    base = {
        EvidenceVerdict.consistent: 0.9,
        EvidenceVerdict.inconsistent: 0.75,
        EvidenceVerdict.insufficient_data: 0.62,
    }[verdict]
    if case_type == CaseType.phishing_or_social_engineering:
        base = max(base, 0.92)
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
    matched, verdict, inv_reasons = _investigate(req, case_type, amounts, phones, norm)
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
