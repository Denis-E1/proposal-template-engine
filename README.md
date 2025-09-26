# Proposal Template Engine

A tiny service that turns a client **brief** into a structured **proposal** (scope, milestones, risks) and a **cost estimate**, plus a clean Markdown summary.

- **Currencies (MVP):** KES, USD
- **Tech:** Jac (by LLM), FastAPI adapter, Railway deploy
- **Storage:** single JSON file (no database for MVP)
- **Branches:** `staging` (work here) → PR → `production`

## Status
Phase 0 — repo & environment bootstrap.

## Product (UX)

**Goal:** Paste a client brief → get a structured proposal (scope, milestones, risks) + a cost estimate and a clean Markdown summary.

**User flow (MVP)**
1. Open **/ui**.
2. Enter: Client name, Hourly rate, Buffer %, Currency (KES or USD).
3. Paste the **brief** and click **Generate Proposal**.
4. See totals + a Markdown summary (copy/download).
5. Proposal is saved to `data/proposals.json` (simple file storage).

**Defaults**
- Hourly rate: `35`
- Buffer %: `0.20` (20%)
- Currencies: `KES`, `USD`

## Data Model (MVP)

**Entities**
- `Client { name, email? }`
- `Brief { text, created_at }`
- `Proposal { title, created_at, rate_per_hour, buffer_pct, currency }`
- `Deliverable { title, description, est_hours }`
- `Milestone { title, due_week, deliverables[] }`
- `Risk { title, mitigation, severity }`
- `Quote { subtotal_hours, rate_per_hour, buffer_pct, subtotal_amount, buffer_amount, total_amount, currency }`

**Enums**
- `Severity { LOW, MEDIUM, HIGH }`
- `Currency { KES, USD }`

**Relations**
- `CLIENT_HAS` (Client → Proposal)
- `PROPOSAL_FROM` (Proposal → Brief)
- `PROPOSAL_HAS` (Proposal → Deliverable/Milestone/Risk/Quote)

## LLM & Types

We bind one global LLM model (Gemini) and use **meaning-typed** functions:

- `extract_scope(brief) -> { deliverables[], milestones[], assumptions[], out_of_scope[], risks[] }  by llm()`
- `summarize_md(scope, quote, currency) -> str  by llm()`

> Numbers are **deterministic** in code:
> - `subtotal_hours = sum(est_hours)`
> - `subtotal_amount = subtotal_hours * rate_per_hour`
> - `buffer_amount = subtotal_amount * buffer_pct`
> - `total_amount = subtotal_amount + buffer_amount`

## API Plan

- `GET /` → health `{ ok: true }`
- `GET /ui` → simple one-page UI
- `POST /proposals`
  - **Body**
    ```json
    {
      "client_name": "Acme Co.",
      "brief": "We need a marketing site with a CMS and blog...",
      "hourly_rate": 35,
      "buffer_pct": 0.2,
      "currency": "USD"
    }
    ```
  - **Response (example)**
    ```json
    {
      "proposal_id": "prop_001",
      "deliverables": [{"title":"Website","description":"...","est_hours":24}],
      "milestones": [{"title":"Design sign-off","due_week":2,"deliverables":["Website"]}],
      "assumptions": ["Client provides brand assets"],
      "out_of_scope": ["Custom CRM"],
      "risks": [{"title":"Scope creep","mitigation":"Change policy","severity":"MEDIUM"}],
      "quote": {
        "subtotal_hours": 24.0,
        "subtotal_amount": 840.0,
        "buffer_amount": 168.0,
        "total_amount": 1008.0,
        "currency": "USD"
      },
      "summary_md": "## Proposal for Acme Co.\n..."
    }
    ```
- `GET /proposals` → list summaries `[ {id, title, total_amount, created_at} ]`
- `GET /proposals/{id}` → full proposal JSON
- `GET /run` → calls `jac run` (grading/completeness helper)

## Persistence (no DB for MVP)

- File: `data/proposals.json` (created on first save)
- Shape: `{ "prop_001": { ...proposal json... }, "prop_002": {...} }`
- In-memory cache mirrors the file; write-through on create/update.
- IDs: `prop_<timestamp>` (e.g., `prop_2025-09-25T12-30-00Z`)

## UI Plan

Single page served at **/ui**:
- Inputs: Client name, Hourly rate, Buffer %, Currency (KES|USD), Brief (textarea)
- Action: **Generate Proposal** (calls `POST /proposals`)
- Output: Totals + tables (Deliverables, Milestones, Risks) + **Markdown preview**
- Buttons: **Copy Markdown**, **Download .md**
- Styling: small inline CSS (no framework)
