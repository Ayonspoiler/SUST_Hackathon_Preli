# QueueStorm Investigator

Internal support copilot for a digital finance platform. Reads a customer complaint
**plus** the customer's recent transaction history, decides what actually happened,
routes the case to the right department, and drafts a safe reply.

Built for **SUST CSE Carnival 2026 — Codex Community Hackathon**, Online Preliminary.

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Returns `{"status": "ok"}` — ready within 60s of start |
| `POST` | `/analyze-ticket` | Structured analysis (see schema below) |

## Tech Stack

Python 3.11 · FastAPI · Uvicorn · Gunicorn · Pydantic v2 · python-dotenv

Optional: Anthropic SDK (for LLM reply polishing — not required for full scoring)

## AI Approach

A deterministic **rule-based investigator** is the core:

1. **Classify** `case_type` from complaint keywords (English + Banglish + Bangla) plus
   `user_type` / `channel` hints. Phishing detection requires an explicit scam keyword
   *or* a credential mention (OTP/PIN) paired with a social-engineering cue — so benign
   mentions like "I forgot my PIN" are not misrouted.

2. **Match** the relevant transaction by amount (Bangla numerals normalised), counterparty
   phone, and transaction type.

3. **Decide** `evidence_verdict`:
   - `consistent` — the matched transaction supports the complaint.
   - `inconsistent` — data contradicts the complaint (e.g. "wrong transfer" to a
     counterparty the customer has paid repeatedly; a "failed" payment that actually
     completed).
   - `insufficient_data` — empty history, no match, or ≥2 plausible transactions where
     guessing would risk the wrong dispute.

4. **Route** to department and **assess** severity deterministically.

5. **Escalate** for human review on disputes, fraud, and ambiguous cases.

6. **Generate** `agent_summary`, `recommended_next_action`, and a language-aware
   `customer_reply` from safe templates, then run every text field through the safety
   sanitizer. Optionally polish text via LLM if `ANTHROPIC_API_KEY` is set.

This service is a copilot, not an autonomous decision-maker: it never confirms a refund
it cannot authorise and escalates ambiguous/high-risk cases.

## Safety Logic

- Never asks for PIN/OTP/password/card — enforced by safe templates **and** a
  sentence-level sanitiser that distinguishes a request ("share your OTP") from a
  warning ("do **not** share your OTP").
- Never confirms a refund/reversal/unblock; uses
  *"any eligible amount will be returned through official channels."*
- Never directs customers to third parties or raw URLs — only official channels.
- Prompt injection: the complaint is treated purely as **data** (keyword scan), never
  executed. The sanitiser runs on every output field including any LLM output.

## Evidence Reasoning — Validated

The engine reproduces all 10 public sample cases on the scored key fields
(`relevant_transaction_id`, `evidence_verdict`, `case_type`, `department`, `severity`,
`human_review_required`). Run `python tests/test_samples.py` to reproduce.

## MODELS

| Model | Where | Why |
|---|---|---|
| **None (rule-based core)** | Local CPU | Deterministic, free, sub-ms per request. Scores the 35% evidence-reasoning category without any API dependency. |
| **claude-haiku-4-5-20251001** *(optional)* | Anthropic API | Used only to polish `agent_summary` / `customer_reply` text. Call is time-bounded (20s) and falls back to templates on any error, so judging never depends on it. Cost: pay-per-token on own key. |

## Performance

No model loaded at startup → `/health` is instant. Rule-based reasoning is well under
the 30s limit. Bad input returns 400/422/500 and never crashes the process.

## HTTP Status Codes

| Code | Meaning |
|---|---|
| 200 | Valid analysis |
| 400 | Malformed JSON / missing required fields |
| 422 | Valid schema but empty `complaint` |
| 500 | Internal error — no stack traces, no secrets |

## Assumptions

- Bangladeshi mobile-number format for counterparty matching.
- Amounts in BDT; complaint amounts parsed via regex (Bangla numerals supported).
- "Other valid responses exist" — we match the key fields plus a safe reply, per the spec.

## Known Limitations

- Keyword classification can miss unusual phrasings; keyword maps are easy to extend.
- Free-tier hosting may cold-start; keep `/health` warm during the judging window.

## Run

See [RUNBOOK.md](RUNBOOK.md).
