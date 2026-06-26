"""Hybrid ticket analyzer: deterministic rules for scored fields, optional LLM for text."""
from typing import Any, Dict

from ..schemas.request import TicketRequest
from .llm_service import build_text_from_reasoning, polish_text_fields_llm
from .reasoning_engine import run_reasoning
from .safety_guard import post_filter, pre_scan, has_unsafe_credential_language


async def analyze_ticket(req: TicketRequest) -> Dict[str, Any]:
    """Run the full investigation pipeline.

    1. Deterministic reasoning (all scored / enum fields) — ~1–5 ms
    2. Safe template text from rules
    3. Optional Gemini polish (text fields only) — bounded timeout
    4. Safety post-filter on all text output
    """
    pre_scan(req.complaint or "")

    reasoning = run_reasoning(req)
    text = build_text_from_reasoning(req, reasoning)

    polished = await polish_text_fields_llm(req, reasoning, text)
    if polished:
        candidate = polished
    else:
        candidate = text

    cr, na, ag, sanitize_flags = post_filter(
        candidate["customer_reply"],
        candidate["recommended_next_action"],
        candidate["agent_summary"],
    )
    if polished and has_unsafe_credential_language(f"{cr} {na} {ag}"):
        cr, na, ag, sanitize_flags = post_filter(
            text["customer_reply"],
            text["recommended_next_action"],
            text["agent_summary"],
        )
        sanitize_flags = list(dict.fromkeys(sanitize_flags + ["reverted_unsafe_polish"]))
    reason_codes = list(
        dict.fromkeys((reasoning.get("reason_codes") or []) + sanitize_flags)
    )

    return {
        "ticket_id": req.ticket_id,
        "relevant_transaction_id": reasoning["relevant_transaction_id"],
        "evidence_verdict": reasoning["evidence_verdict"].value,
        "case_type": reasoning["case_type"].value,
        "severity": reasoning["severity"].value,
        "department": reasoning["department"].value,
        "agent_summary": ag,
        "recommended_next_action": na,
        "customer_reply": cr,
        "human_review_required": reasoning["human_review_required"],
        "confidence": reasoning["confidence"],
        "reason_codes": reason_codes,
    }
