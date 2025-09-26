from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from pathlib import Path
import json, os, sys, subprocess, datetime, math
from typing import List, Dict, Any, Literal

# ---- FastAPI app ----
app = FastAPI(title="Proposal Template Engine", version="0.1.0")

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
STORE = DATA_DIR / "proposals.json"

def read_store() -> Dict[str, Any]:
    if STORE.exists():
        return json.loads(STORE.read_text(encoding="utf-8"))
    return {}

def write_store(data: dict):
    STORE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

# ---- health & jac run ----
@app.get("/")
def health():
    return {"ok": True, "service": "proposal-template-engine"}

@app.get("/run")
def run_jac():
    """Call Jac for a simple readiness check."""
    jac_file = str(Path(__file__).parent / "main.jac")
    commands = [
        [sys.executable, "-m", "jaclang.cli.cli", "run", jac_file],
        ["jac", "run", jac_file],
    ]
    last = None
    for cmd in commands:
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode == 0:
            return {"returncode": 0, "stdout": p.stdout, "stderr": p.stderr, "cmd": cmd}
        last = p
    return {"returncode": last.returncode if last else -1, "stdout": last.stdout if last else "", "stderr": last.stderr if last else "no cmd", "tried": commands}

# ---- minimal retro UI ----
@app.get("/ui", response_class=HTMLResponse)
def ui():
    return (Path(__file__).parent / "static" / "ui.html").read_text(encoding="utf-8")

# ---- LLM helpers (Gemini via byllm) ----
def llm_model():
    # byllm reads GEMINI_API_KEY from env (no extra config needed if set)
    from byllm import Model
    # keep light/fast model; you can change to "gemini/gemini-2.0-flash" later
    return Model(model_name="gemini/gemini-1.5-flash", temperature=0.2)

ALLOWED_SEVERITY = {"LOW", "MEDIUM", "HIGH"}

def coerce_severity(s: str) -> str:
    s = (s or "").strip().upper()
    return s if s in ALLOWED_SEVERITY else "MEDIUM"

def ensure_float(x) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0

def llm_extract_scope(brief: str) -> Dict[str, Any]:
    """
    Ask the LLM for a *structured* scope. We instruct it to return JSON that matches
    the Jac 'obj' types you defined (Deliverable, Milestone, Risk).
    """
    m = llm_model()
    system = (
        "You generate software project scopes in STRICT JSON.\n"
        "Return a JSON object with keys: deliverables, milestones, assumptions, out_of_scope, risks.\n"
        "deliverables: array of {title, description, est_hours(float)}.\n"
        "milestones: array of {title, due_week(int), deliverables(array of titles)}.\n"
        "assumptions: array of strings.\n"
        "out_of_scope: array of strings.\n"
        "risks: array of {title, mitigation, severity in [LOW, MEDIUM, HIGH]}.\n"
        "No markdown. No prose. JSON only."
    )
    prompt = f"BRIEF:\n{brief}\n\nProduce the JSON now."
    out = m.complete(system=system, prompt=prompt)

    # Try to parse JSON from output; if it includes code fences, strip them.
    txt = out.strip()
    if txt.startswith("```"):
        # remove ```... fences
        lines = [ln for ln in txt.splitlines() if not ln.strip().startswith("```")]
        txt = "\n".join(lines).strip()

    try:
        data = json.loads(txt)
    except Exception:
        # Very defensive fallback
        data = {
            "deliverables": [],
            "milestones": [],
            "assumptions": [],
            "out_of_scope": [],
            "risks": []
        }

    # Light validation/coercion
    for d in data.get("deliverables", []):
        d["title"] = d.get("title", "").strip()
        d["description"] = d.get("description", "").strip()
        d["est_hours"] = ensure_float(d.get("est_hours"))

    for ml in data.get("milestones", []):
        ml["title"] = ml.get("title", "").strip()
        ml["due_week"] = int(ensure_float(ml.get("due_week")))
        ml["deliverables"] = [str(x).strip() for x in ml.get("deliverables", [])]

    data["assumptions"] = [str(x).strip() for x in data.get("assumptions", [])]
    data["out_of_scope"] = [str(x).strip() for x in data.get("out_of_scope", [])]

    for r in data.get("risks", []):
        r["title"] = r.get("title", "").strip()
        r["mitigation"] = r.get("mitigation", "").strip()
        r["severity"] = coerce_severity(r.get("severity"))

    return data

def llm_summarize_md(scope: Dict[str, Any], currency: str, total_amount: float, client_name: str) -> str:
    m = llm_model()
    currency = currency.upper()
    system = (
        "You are a proposal writer. Return clean, concise MARKDOWN only (no JSON). "
        "Headings, bullet lists, and short sentences."
    )
    deliverables = scope.get("deliverables", [])
    milestones = scope.get("milestones", [])
    assumptions = scope.get("assumptions", [])
    out_of_scope = scope.get("out_of_scope", [])
    risks = scope.get("risks", [])

    summary_seed = {
        "client": client_name,
        "total": f"{currency} {total_amount:,.2f}",
        "deliverables": deliverables,
        "milestones": milestones,
        "assumptions": assumptions,
        "out_of_scope": out_of_scope,
        "risks": risks
    }
    prompt = (
        "Create a client-ready one-page proposal summary in Markdown from this JSON:\n"
        f"{json.dumps(summary_seed, ensure_ascii=False, indent=2)}\n\n"
        "Sections: Overview, Deliverables, Milestones, Assumptions, Out of scope, Risks, Pricing."
    )
    return m.complete(system=system, prompt=prompt).strip()

# ---- API: create proposal (real) ----
@app.post("/proposals")
async def create_proposal(req: Request):
    body = await req.json()
    def g(k, d=None): return body.get(k, d)

    client_name = g("client_name")
    brief = g("brief")
    rate = g("hourly_rate")
    buffer_pct = g("buffer_pct")
    currency = g("currency")

    if not client_name or not brief or currency not in ("KES", "USD"):
        raise HTTPException(status_code=400, detail="Missing required fields or invalid currency (KES|USD).")

    try:
        rate = float(rate)
        buffer_pct = float(buffer_pct)
    except Exception:
        raise HTTPException(status_code=400, detail="hourly_rate and buffer_pct must be numbers.")

    # 1) Ask the LLM for structured scope (deliverables, milestones, risks...)
    scope = llm_extract_scope(brief)

    # 2) Compute totals deterministically
    subtotal_hours = sum(float(d.get("est_hours", 0.0)) for d in scope.get("deliverables", []))
    subtotal_amount = round(subtotal_hours * rate, 2)
    buffer_amount = round(subtotal_amount * buffer_pct, 2)
    total_amount = round(subtotal_amount + buffer_amount, 2)

    # 3) Ask LLM for a concise Markdown summary
    summary_md = llm_summarize_md(scope, currency, total_amount, client_name)

    # 4) Persist proposal
    prop_id = "prop_" + datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    created_at = datetime.datetime.utcnow().isoformat() + "Z"
    proposal = {
        "proposal_id": prop_id,
        "created_at": created_at,
        "client_name": client_name,
        "currency": currency,
        "rate_per_hour": rate,
        "buffer_pct": buffer_pct,
        "brief_len": len(brief),
        "deliverables": scope.get("deliverables", []),
        "milestones": scope.get("milestones", []),
        "assumptions": scope.get("assumptions", []),
        "out_of_scope": scope.get("out_of_scope", []),
        "risks": scope.get("risks", []),
        "quote": {
            "subtotal_hours": subtotal_hours,
            "subtotal_amount": subtotal_amount,
            "buffer_amount": buffer_amount,
            "total_amount": total_amount,
            "currency": currency,
        },
        "summary_md": summary_md,
    }

    store = read_store()
    store[prop_id] = proposal
    write_store(store)
    return proposal

# ---- API: list + get ----
@app.get("/proposals")
def list_proposals():
    store = read_store()
    out = []
    for pid, p in sorted(store.items()):
        out.append({
            "id": pid,
            "created_at": p.get("created_at"),
            "client_name": p.get("client_name"),
            "total_amount": p.get("quote", {}).get("total_amount"),
            "currency": p.get("quote", {}).get("currency"),
        })
    return out

@app.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: str):
    store = read_store()
    if proposal_id not in store:
        raise HTTPException(status_code=404, detail="Not found")
    return store[proposal_id]
