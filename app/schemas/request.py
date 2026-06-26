from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class TransactionEntry(BaseModel):
    transaction_id: str
    timestamp: Optional[str] = None
    type: Optional[str] = None
    amount: Optional[float] = None
    counterparty: Optional[str] = None
    status: Optional[str] = None


class TicketRequest(BaseModel):
    ticket_id: str
    complaint: str
    language: Optional[str] = None
    channel: Optional[str] = None
    user_type: Optional[str] = None
    campaign_context: Optional[str] = None
    transaction_history: Optional[List[TransactionEntry]] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = None
