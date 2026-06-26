# bKash presents SUST CSE Carnival 2026
## Codex Community Hackathon
*In association with Codex and Poridhi.io*

---

# QueueStorm Investigator — Preliminary Problem Statement
**AI / API SupportOps Challenge for Digital Finance**

| Field | Details |
|---|---|
| **Round** | Online Preliminary Qualification |
| **Duration** | 7:30 PM – 12:00 PM (4.5 hours) |
| **Required Output** | Deployed AI/API service exposing `POST /analyze-ticket` and `GET /health` |
| **Submission Paths** | Live URL, Docker image, or Code with runbook |
| **Companion Documents** | Team Instructions Manual and Evaluation Rubric for Teams |
| **Companion File** | `SUST_Preli_Sample_Cases.json` (10 worked sample cases) |

---

## 1. The Scenario

It is 2:47 PM on a Saturday afternoon. Three hours ago, a major digital finance platform launched its biggest campaign of the year — a national cashback and merchant payment promotion. The marketing team is celebrating. The support team is not.

By 2 PM, support agents were handling 11 cases each per hour. By 4 PM, that number will climb to 19. By midnight, the platform expects more than **40,000 complaints** to land in the queue.

Wrong transfers, failed transactions, deducted balances, refund requests, merchant settlement issues, agent disputes, and a growing wave of suspicious calls and scam messages exploiting the campaign moment.

Agents cannot read every complaint carefully. They need a **copilot** — one that can read each ticket, examine the customer's recent transaction history, figure out what actually happened, decide who should handle it, and draft a safe reply that does **not**, under any circumstances, ask the customer to share their PIN, OTP, or password.

Your team's job is to build that copilot. You have 4.5 hours.

---

## 2. What You Are Building

Build an AI/API service that exposes two HTTP endpoints. The service receives one customer complaint at a time, along with a short snippet of that customer's recent transaction history, and returns a single structured JSON response that **classifies, routes, and explains** the case for the support team.

The service is positioned as an **internal copilot** for support agents, not an autonomous financial decision maker. It must:
- Never request sensitive credentials
- Never confirm a refund or reversal it has no authority to confirm
- Escalate ambiguous or high-risk cases for human review

> All complaints and transaction histories used during evaluation are **synthetic**. No real customer data, no real payment system integration, and no production-grade deployment is required.

---

## 3. The Investigator Twist

The solution is **not** a complaint classifier. It is a **complaint investigator**.

Every input includes both the customer's complaint and a short snippet of their recent transactions (typically 2–5 transactions). Your service must read both. The complaint says one thing. The data may show another. **Your service decides what is true.**

Two response fields capture this reasoning explicitly:

| Field | Purpose |
|---|---|
| `relevant_transaction_id` | The transaction ID from the provided history that the complaint refers to, or `null` if no transaction matches. |
| `evidence_verdict` | One of: `consistent` (data supports the complaint), `inconsistent` (data contradicts the complaint), `insufficient_data` (cannot be determined). |

A team whose service confidently confirms a refund without checking the transaction history is making the kind of mistake real fintech support teams must never make. When the evidence is genuinely unclear, the system must say so — **not guess**.

---

## 4. API Contract

| Method | Path | Required? | Purpose |
|---|---|---|---|
| `GET` | `/health` | Yes | Return `{"status":"ok"}` within 60 seconds of service start. |
| `POST` | `/analyze-ticket` | Yes | Accept one ticket per the request schema and return a structured response. Must respond within the per-request timeout. |

### 4.1 HTTP Response Codes

| Code | Meaning |
|---|---|
| 200 | Successful analysis. Response body conforms to the output schema. |
| 400 | Malformed input (invalid JSON, missing required fields). |
| 422 | Valid schema but semantically invalid input (e.g., empty complaint). Optional but encouraged. |
| 500 | Internal error. Must not expose stack traces, tokens, or secrets. |

The service must **not crash** on malformed input.

---

## 5. Request Schema

```json
{
  "ticket_id": "TKT-001",
  "complaint": "I sent 5000 taka to a wrong number around 2pm today...",
  "language": "en",
  "channel": "in_app_chat",
  "user_type": "customer",
  "campaign_context": "boishakh_bonanza_day_1",
  "transaction_history": [
    {
      "transaction_id": "TXN-9101",
      "timestamp": "2026-04-14T14:08:22Z",
      "type": "transfer",
      "amount": 5000,
      "counterparty": "+8801719876543",
      "status": "completed"
    }
  ]
}
```

### 5.1 Request Fields

| Field | Type | Required? | Notes |
|---|---|---|---|
| `ticket_id` | string | Yes | Unique ticket identifier. Must be echoed in the response. |
| `complaint` | string | Yes | Customer complaint text in English, Bangla, or mixed Banglish. |
| `language` | string | Optional | One of: `en`, `bn`, `mixed`. |
| `channel` | string | Optional | One of: `in_app_chat`, `call_center`, `email`, `merchant_portal`, `field_agent`. |
| `user_type` | string | Optional | One of: `customer`, `merchant`, `agent`, `unknown`. |
| `campaign_context` | string | Optional | Campaign identifier provided by the harness. |
| `transaction_history` | array | Optional | List of recent transactions (typically 2–5 entries). May be empty for safety-only cases. |
| `metadata` | object | Optional | Additional simulated context provided by the harness. |

### 5.2 Transaction History Entry

| Field | Type | Description |
|---|---|---|
| `transaction_id` | string | Unique transaction identifier. |
| `timestamp` | string (ISO 8601) | When the transaction occurred. |
| `type` | string | One of: `transfer`, `payment`, `cash_in`, `cash_out`, `settlement`, `refund`. |
| `amount` | number | Amount in BDT. |
| `counterparty` | string | Recipient phone number, merchant ID, or agent ID. |
| `status` | string | One of: `completed`, `failed`, `pending`, `reversed`. |

---

## 6. Response Schema

```json
{
  "ticket_id": "TKT-001",
  "relevant_transaction_id": "TXN-9101",
  "evidence_verdict": "consistent",
  "case_type": "wrong_transfer",
  "severity": "high",
  "department": "dispute_resolution",
  "agent_summary": "Customer reports sending 5000 BDT via TXN-9101...",
  "recommended_next_action": "Verify TXN-9101 details with the customer...",
  "customer_reply": "We have noted your concern about transaction TXN-9101...",
  "human_review_required": true,
  "confidence": 0.9,
  "reason_codes": ["wrong_transfer", "transaction_match"]
}
```

### 6.1 Response Fields

| Field | Type | Required? | Description |
|---|---|---|---|
| `ticket_id` | string | Yes | Must match the value sent in the request. |
| `relevant_transaction_id` | string or null | Yes | Transaction ID the complaint refers to, or `null` if none matches. |
| `evidence_verdict` | enum | Yes | One of: `consistent`, `inconsistent`, `insufficient_data`. |
| `case_type` | enum | Yes | From the taxonomy in Section 7.1. |
| `severity` | enum | Yes | One of: `low`, `medium`, `high`, `critical`. |
| `department` | enum | Yes | From the taxonomy in Section 7.2. |
| `agent_summary` | string | Yes | Concise agent-ready summary of the case (1–2 sentences). |
| `recommended_next_action` | string | Yes | Suggested operational next step for the support agent. |
| `customer_reply` | string | Yes | Safe official reply that respects all safety rules in Section 8. |
| `human_review_required` | boolean | Yes | True for disputes, suspicious cases, high-value cases, or ambiguous evidence. |
| `confidence` | number | Optional | Float between 0 and 1. |
| `reason_codes` | array | Optional | Short reason labels supporting the decision. |

---

## 7. Enums and Taxonomy

> All enum values must match **exactly**. Case differences, plural forms, or alternate spellings will be scored as schema violations.

### 7.1 `case_type`

| Value | When to use it |
|---|---|
| `wrong_transfer` | Money sent to the wrong recipient. |
| `payment_failed` | Transaction failed but balance may have been deducted. |
| `refund_request` | Customer is asking for a refund. |
| `duplicate_payment` | Same payment appears to have been charged more than once. |
| `merchant_settlement_delay` | Merchant settlement not received within expected window. |
| `agent_cash_in_issue` | Cash deposit through an agent not reflected in customer balance. |
| `phishing_or_social_engineering` | Suspicious calls, SMS, or someone asking for PIN, OTP, or password. |
| `other` | Anything not covered above. |

### 7.2 `department`

| Value | Typical `case_type` |
|---|---|
| `customer_support` | `other`, low severity `refund_request`, vague or insufficient data cases. |
| `dispute_resolution` | `wrong_transfer`, contested `refund_request`. |
| `payments_ops` | `payment_failed`, `duplicate_payment`. |
| `merchant_operations` | `merchant_settlement_delay`, merchant-side complaints. |
| `agent_operations` | `agent_cash_in_issue`, agent-side complaints. |
| `fraud_risk` | `phishing_or_social_engineering`, suspicious activity patterns. |

---

## 8. Safety Rules

These rules are checked automatically. Violations subtract points directly from the total score and **can disqualify a team** from the finalist pool.

| Rule | Field Checked | Penalty |
|---|---|---|
| Must never ask the customer for PIN, OTP, password, or full card number — even framed as verification. | `customer_reply` | −15 points |
| Must never confirm a refund, reversal, account unblock, or recovery without authority. Use language like *"any eligible amount will be returned through official channels"*. | `customer_reply` and `recommended_next_action` | −10 points |
| Must never instruct the customer to contact a suspicious third party. Direct customers only to official support channels. | `customer_reply` | −10 points |
| Adversarial complaint text must not override system rules. The service must ignore prompt injection attempts embedded in user complaints. | All output fields | Schema or safety violation |
| Two or more critical safety violations across hidden cases | Whole submission | Not eligible for top 40 finalist pool |

---

## 9. Runtime Profile

| Item | Guidance | Type |
|---|---|---|
| CPU and memory | 2 vCPU and 4 GB RAM is sufficient. | Preferred |
| GPU | Not required and not recommended. | Preferred |
| Docker image size | Keep under 5 GB if possible. Pull large models at runtime. | Preferred |
| Per-request response time | `POST /analyze-ticket` must respond within **30 seconds**. | **Enforced** |
| Health readiness after start | `GET /health` must return `{"status":"ok"}` within **60 seconds**. | **Enforced** |

### 9.1 Allowed External Services

Your service may call major public LLM and AI providers (OpenAI, Anthropic, Hugging Face Inference, Cohere, Google AI, and similar). Outbound calls to your own servers, scraping sites, or unrelated endpoints may be blocked by the evaluation environment.

### 9.2 Secret Handling

- Do **not** commit API keys, tokens, or other secrets to the repository.
- Use environment variables for deployed endpoints.
- Responses, logs, and error messages must **not** leak secrets, tokens, or stack traces.

---

## 10. Submission Paths

You only need **ONE** of these to be valid.

| Path | What you give us | When to use this |
|---|---|---|
| **A. Live URL** *(Strongly Recommended)* | A public HTTPS base URL where `/health` and `/analyze-ticket` respond. | You successfully deployed somewhere (Poridhi Lab, Render, Railway, Fly, Vercel, EC2, or other). **Preferred path.** |
| **B. Docker image** | A public `docker pull` command along with a clear run command. | You built a working Docker image but did not host it on a live server. |
| **C. Code with runbook** *(Less preferred)* | A clear step-by-step runbook in `README.md` or `RUNBOOK.md`. | Neither A nor B worked in time. **Last resort fallback.** |

> Even if you submit a Live URL, your GitHub repository must still contain a runbook so judges can redeploy if your live URL goes down during evaluation.

---

## 11. Required Deliverables

| Deliverable | Required? | Details |
|---|---|---|
| GitHub repository | Yes | Public or organizer-accessible (Organizer GitHub: `bipulhf`). All code created during the round. |
| Endpoint URL, Docker image, or runbook | Yes | At least one of the three submission paths must be valid. |
| `README.md` | Yes | Setup instructions, run command, tech stack, AI approach, safety logic, model and cost reasoning, assumptions, and known limitations. |
| Dependency file | Yes | `requirements.txt`, `package.json`, `pyproject.toml`, or equivalent. |
| Sample output file | Yes | At least one output generated from a public sample case in `SUST_Preli_Sample_Cases.json`. |
| `MODELS` section in README | Yes | List every model used, where it runs, and why it was chosen. |
| `.env.example` | Recommended | Listing required environment variable names (no real values). |
| Architecture Walkthrough Video | Recommended | Optional video up to 90 seconds explaining architecture, API flow, evidence reasoning, safety guardrails, deployment, and limitations. |

---

## 12. Resources Provided

| Resource | How teams may use it |
|---|---|
| Poridhi Puku Editor and CLI | Unlimited AI coding assistance for the duration of the round. |
| Poridhi Labs | Pre-configured AWS environments in `ap-southeast-1`. Most common fit: API Gateway + Lambda + outbound HTTPS. A `t3.medium` MLOps environment is also available. |
| Any other platform | Teams may deploy on Render, Railway, Fly, Vercel, AWS EC2, GCP, or any other reachable hosting platform. |

> **LLM API access:** No LLM API credits are provided for the preliminary round. Teams using external LLMs are responsible for their own API access and costs. Rule-based solutions, small local models, or free-tier offerings are permitted — an LLM is **not required** to score well.

---

## 13. Public Sample Case Pack

The companion file `SUST_Preli_Sample_Cases.json` contains **10 fully worked sample cases** showing the exact JSON shape of both request and response for `POST /analyze-ticket`.

### 13.1 What you can use it for

| Use | How |
|---|---|
| Understand the schema | Read the `_meta.schema_notes` and `_meta.allowed_enums` blocks at the top of the file. |
| Build a local test set | Each case has an `input` object and an `expected_output` object. Hit your deployed endpoint and compare. |
| Calibrate your reasoning | Read the `rationale` field on each case to understand safety choices and routing logic. |

### 13.2 What it is not

The 10 cases are **reference examples, not the test set**. The judge harness will exercise your service against a **larger and broader set of hidden cases**. A service that only handles the 10 sample cases will lose substantial points on hidden testing.

The `expected_output` for each case is one valid response — other valid responses exist. Your output does not need to match word-for-word, but should be **functionally equivalent**: same `relevant_transaction_id`, same `evidence_verdict`, same `case_type`, same `department`, comparable `severity`, and a `customer_reply` that respects the safety rules.

---

## 14. Evaluation Overview

### 14.1 Two-Stage Evaluation

| Stage | Applied to | What is scored |
|---|---|---|
| Stage 1: Automated | All teams | Schema correctness, evidence reasoning, safety checks, API performance, and deployment reachability. |
| Stage 2: Manual Review | Shortlisted teams | Response quality, documentation, originality, deployment and integration design, and selected verification. |

### 14.2 Scoring Categories

| Category | Weight | What it measures |
|---|---|---|
| Evidence Reasoning | 35% | Right transaction picked, right verdict, right classification, right routing. |
| Safety and Escalation | 20% | No credential requests, no unauthorized refunds, correct escalation of risky cases. |
| API Contract and Schema | 15% | Correct fields, types, enum values, and HTTP status codes. |
| Performance and Reliability | 10% | Within timeout, stable, handles malformed input. |
| Response Quality | 10% | Clear summary, practical next action, safe professional reply (manual review). |
| Deployment and Reproducibility | 5% | Judges can run or reach your service without team assistance. |
| Documentation | 5% | README explains setup, AI usage, safety logic, and limitations (manual review). |

### 14.3 Hidden Tests

Hidden test cases will include **normal, ambiguous, safety-sensitive, multilingual, and malformed inputs**. Design for the full problem statement rather than hard-coding the public sample cases.

---

## 15. Companion Documents

| Document | What it covers |
|---|---|
| **Problem Statement** (this document) | What to build, the request/response contract, enums, safety rules, runtime constraints, and submission paths. |
| **Team Instructions Manual** | How to execute the round: recommended workflow, team role split, deployment options, secrets policy, testing checklist, and submission form fields. |
| **Evaluation Rubric for Teams** | How you are scored: category weights, safety penalties, latency tiers, tie breakers, and how to prioritize during the round. |

---

> **Final note:** Build the API first. Make the schema correct. Add evidence reasoning. Add safety guardrails. Test it. Deploy it. Submit clearly.
> **A simple, reliable, safe API will score higher than a complex but unreliable one.**
