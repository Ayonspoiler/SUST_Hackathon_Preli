# QueueStorm Investigator

Internal support copilot for a digital finance platform (SUST CSE Carnival 2026 — Codex Community Hackathon, Online Preliminary).

Given one customer **complaint** and recent **transaction history**, the service investigates what actually happened, returns structured routing/classification JSON, and drafts safe agent and customer text.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Returns `{"status": "ok"}` (ready within 60s of start) |
| `POST` | `/analyze-ticket` | Full ticket analysis (request/response schema per problem statement) |

## Quick Start

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/macOS

pip install -r requirements.txt
copy .env.example .env           # optional — not required for default mode

uvicorn main:app --host 0.0.0.0 --port 8000
```

Verify:

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/analyze-ticket -H "Content-Type: application/json" -d @sample_input.json
```

Production-style (Docker / VM):

```bash
gunicorn main:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --timeout 60
```

See [RUNBOOK.md](RUNBOOK.md) for Docker, deployment, and validation steps.

## Architecture (Hybrid)

```
POST /analyze-ticket
  → safety pre-scan (injection detection)
  → deterministic rule engine     ← all scored fields (case_type, verdict, txn id, severity, …)
  → safe text templates           ← agent_summary, customer_reply, recommended_next_action
  → optional Gemini text polish   ← OFF by default (ENABLE_LLM_POLISH=false)
  → safety post-filter            ← always runs on all text fields
  → JSON response
```

**Design choice:** Rules decide **facts** (35% evidence-reasoning score). The LLM, when enabled, only rewrites text — never changes enum fields. Default deployment is **fully rule-based** (~5 ms per request, no external API dependency).

### Pipeline modules

| Module | Role |
|--------|------|
| `app/services/reasoning_engine.py` | Classify, match transactions, verdict, severity, department, human review |
| `app/services/analyzer.py` | Orchestrates the full pipeline |
| `app/services/llm_service.py` | Safe templates + optional Gemini polish |
| `app/services/safety_guard.py` | Pre/post safety filters |
| `app/routes/analyze.py` | HTTP handler, timeouts, error responses |

## AI / Model Usage

| Component | Default | Purpose |
|-----------|---------|---------|
| **Rule engine** | Always on | Evidence reasoning, classification, routing — local CPU, deterministic |
| **Gemini 2.5 Flash** | Optional (`ENABLE_LLM_POLISH=true`) | Rewrites the 3 text fields only; 4s timeout; falls back to templates on failure |

No GPU. No model weights in the image. Judging does **not** require an API key when polish is disabled.

### MODELS

| Model | Where it runs | Why |
|-------|---------------|-----|
| **None (rules + templates)** | Local CPU | Primary path. Fast, free, reliable for automated scoring. |
| **gemini-2.5-flash** *(optional)* | Google AI API | Text polish only. `THINKING_BUDGET=0` for low latency. Team supplies own `GEMINI_API_KEY`. |

## Safety Logic

- **Never** asks for PIN, OTP, password, or card number in any output field.
- **Never** confirms refund, reversal, account unblock, or recovery — uses *"any eligible amount will be returned through official channels"*.
- **Never** directs customers to third-party phone numbers or URLs.
- **Prompt injection** in complaints is treated as untrusted data; output is always post-filtered.
- Safe credential mentions (e.g. *"I know I should not share my PIN"*) are not misclassified as phishing.

## Response Schema (summary)

Required fields: `ticket_id`, `relevant_transaction_id`, `evidence_verdict`, `case_type`, `severity`, `department`, `agent_summary`, `recommended_next_action`, `customer_reply`, `human_review_required`.

Optional: `confidence`, `reason_codes`.

Enums must match the problem statement exactly (`wrong_transfer`, `payment_failed`, `consistent`, `fraud_risk`, etc.).

## HTTP Status Codes

| Code | When |
|------|------|
| `200` | Successful analysis |
| `400` | Malformed JSON or missing required fields (`ticket_id`, `complaint`) |
| `422` | Empty or whitespace-only `complaint` |
| `500` | Internal error — no stack traces or secrets in body |

## Environment Variables

Copy `.env.example` to `.env` locally. **Never commit real keys.**

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_LLM_POLISH` | `false` | Set `true` to enable optional Gemini text polish |
| `GEMINI_API_KEY` | *(empty)* | Required only if polish is enabled |
| `MODEL_NAME` | `gemini-2.5-flash` | Gemini model for polish |
| `THINKING_BUDGET` | `0` | Keep `0` for sub-5s latency |
| `LLM_TIMEOUT` | `4.0` | Max seconds for polish call |
| `REQUEST_TIMEOUT` | `6.0` | Max seconds for full `/analyze-ticket` request |

## Performance

- Default (polish off): **~5 ms** average response time, well under the 30s judge timeout and 5s p95 target.
- `/health` is instant — no model loaded at startup.

## Sample Files

| File | Purpose |
|------|---------|
| `sample_input.json` | Example request (matches public sample case shape) |
| `sample_output.json` | Example response from this service |

Validate against the official 10-case pack (download from organizers):

```bash
python tests/test_samples.py SUST_Preli_Sample_Cases.json http://localhost:8000
```

## Assumptions

- Synthetic data only; Bangladesh mobile format for counterparty matching.
- Amounts in BDT; Bangla numerals and comma-separated amounts normalized.
- Multiple valid wordings exist for text fields; judges score key enum/evidence fields.

## Known Limitations

- Keyword/rule maps may miss novel phrasing not seen in training or local testing.
- Template replies are safe and professional but not fully custom per ticket unless polish is enabled.
- Optional Gemini polish adds ~1.5–2s latency and depends on API availability.
- Free-tier hosts may cold-start; keep `/health` warm during the judging window.

## Tech Stack

Python 3.11 · FastAPI · Uvicorn · Gunicorn · Pydantic v2 · python-dotenv · google-genai (optional)

## Submission Checklist

- [ ] Live HTTPS URL with `/health` and `/analyze-ticket` reachable publicly
- [ ] GitHub repo accessible to organizers (`bipulhf` if private)
- [ ] No secrets in repository (only `.env.example`)
- [ ] `ENABLE_LLM_POLISH=false` on production unless you accept latency trade-off
- [ ] README + RUNBOOK reviewed

## License / Data

Hackathon submission. All transaction and complaint data is synthetic. No real customer or payment data.
