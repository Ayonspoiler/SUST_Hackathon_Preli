from enum import Enum
from typing import List, Optional
from pydantic import BaseModel


class CaseType(str, Enum):
    wrong_transfer = "wrong_transfer"
    payment_failed = "payment_failed"
    refund_request = "refund_request"
    duplicate_payment = "duplicate_payment"
    merchant_settlement_delay = "merchant_settlement_delay"
    agent_cash_in_issue = "agent_cash_in_issue"
    phishing_or_social_engineering = "phishing_or_social_engineering"
    other = "other"


class Department(str, Enum):
    customer_support = "customer_support"
    dispute_resolution = "dispute_resolution"
    payments_ops = "payments_ops"
    merchant_operations = "merchant_operations"
    agent_operations = "agent_operations"
    fraud_risk = "fraud_risk"


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class EvidenceVerdict(str, Enum):
    consistent = "consistent"
    inconsistent = "inconsistent"
    insufficient_data = "insufficient_data"


class TicketResponse(BaseModel):
    ticket_id: str
    relevant_transaction_id: Optional[str]
    evidence_verdict: str
    case_type: str
    severity: str
    department: str
    agent_summary: str
    recommended_next_action: str
    customer_reply: str
    human_review_required: bool
    confidence: Optional[float] = None
    reason_codes: Optional[List[str]] = None


class LLMTextPolish(BaseModel):
    """Text-only polish output — scored fields come from the rule engine."""

    agent_summary: str
    recommended_next_action: str
    customer_reply: str


class LLMAnalysis(BaseModel):
    """Structured output schema the LLM must return.

    `ticket_id` is intentionally excluded — the service echoes the request value
    itself to guarantee an exact match. Enum-typed fields force the model to emit
    only allowed values, protecting the schema/enum score.
    """

    relevant_transaction_id: Optional[str]
    evidence_verdict: EvidenceVerdict
    case_type: CaseType
    severity: Severity
    department: Department
    agent_summary: str
    recommended_next_action: str
    customer_reply: str
    human_review_required: bool
    confidence: float
    reason_codes: List[str]
