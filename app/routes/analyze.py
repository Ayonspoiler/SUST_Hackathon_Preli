import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..core.config import settings
from ..schemas.request import TicketRequest
from ..schemas.response import TicketResponse
from ..services.analyzer import analyze_ticket as run_analysis
from ..services.llm_service import build_fallback_response
from ..services.safety_guard import post_filter

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/analyze-ticket")
async def analyze_ticket(req: TicketRequest):
    if not req.complaint or not req.complaint.strip():
        return JSONResponse(
            status_code=422, content={"error": "complaint must not be empty."}
        )

    try:
        result = await asyncio.wait_for(run_analysis(req), timeout=settings.REQUEST_TIMEOUT)
        return TicketResponse(**result).model_dump(mode="json")
    except asyncio.TimeoutError:
        logger.error("Request timed out for ticket %s", req.ticket_id)
        try:
            fallback = build_fallback_response(req)
            cr, na, ag, flags = post_filter(
                fallback["customer_reply"],
                fallback["recommended_next_action"],
                fallback["agent_summary"],
            )
            return TicketResponse(
                ticket_id=req.ticket_id,
                relevant_transaction_id=fallback["relevant_transaction_id"],
                evidence_verdict=fallback["evidence_verdict"],
                case_type=fallback["case_type"],
                severity=fallback["severity"],
                department=fallback["department"],
                agent_summary=ag,
                recommended_next_action=na,
                customer_reply=cr,
                human_review_required=fallback["human_review_required"],
                confidence=fallback.get("confidence"),
                reason_codes=list(dict.fromkeys((fallback.get("reason_codes") or []) + flags)),
            ).model_dump(mode="json")
        except Exception:
            return JSONResponse(status_code=500, content={"error": "Request timed out."})
    except Exception as exc:
        logger.exception("Unhandled error for ticket %s: %s", req.ticket_id, exc)
        return JSONResponse(status_code=500, content={"error": "Internal processing error."})
