import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..core.config import settings
from ..schemas.request import TicketRequest
from ..schemas.response import TicketResponse
from ..services.llm_service import generate_text_fields
from ..services.reasoning_engine import run_reasoning
from ..services.safety_guard import post_filter, pre_scan

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/analyze-ticket")
async def analyze_ticket(req: TicketRequest):
    if not req.complaint or not req.complaint.strip():
        return JSONResponse(
            status_code=422, content={"error": "complaint must not be empty."}
        )

    async def _pipeline():
        pre_scan(req.complaint)
        reasoning = run_reasoning(req)
        text_fields = await generate_text_fields(req, reasoning)
        cr, na, ag, sanitize_flags = post_filter(
            text_fields["customer_reply"],
            text_fields["recommended_next_action"],
            text_fields["agent_summary"],
        )
        reasoning["reason_codes"] = list(
            dict.fromkeys(reasoning["reason_codes"] + sanitize_flags)
        )
        return TicketResponse(
            ticket_id=req.ticket_id,
            relevant_transaction_id=reasoning["relevant_transaction_id"],
            evidence_verdict=reasoning["evidence_verdict"].value,
            case_type=reasoning["case_type"].value,
            severity=reasoning["severity"].value,
            department=reasoning["department"].value,
            agent_summary=ag,
            recommended_next_action=na,
            customer_reply=cr,
            human_review_required=reasoning["human_review_required"],
            confidence=reasoning["confidence"],
            reason_codes=reasoning["reason_codes"],
        )

    try:
        result = await asyncio.wait_for(_pipeline(), timeout=settings.REQUEST_TIMEOUT)
        return result.model_dump(mode="json")
    except asyncio.TimeoutError:
        logger.error("Request timed out for ticket %s", req.ticket_id)
        return JSONResponse(status_code=500, content={"error": "Request timed out."})
    except Exception as exc:
        logger.exception("Unhandled error for ticket %s: %s", req.ticket_id, exc)
        return JSONResponse(status_code=500, content={"error": "Internal processing error."})
