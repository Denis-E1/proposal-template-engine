from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from pathlib import Path
import json, os, sys, subprocess, datetime
from typing import Dict, Any

app = FastAPI(title="Proposal Template Engine", version="0.2.0")

# ---------------- storage ----------------
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
STORE = DATA_DIR / "proposals.json"

def read_store() -> Dict[str, Any]:
    if STORE.exists():
        return json.loads(STORE.read_text(encoding="utf-8"))
    return {}

def write_store(data: dict):
    STORE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

# ---------------- health & jac sanity ----------------
@app.get("/")
def health():
    return {"ok": True, "service": "proposal-template-engine"}

@app.get("/run")
def run_jac():
    """Optional sanity: execute main.jac in a subprocess.
    Note: this may print plugin-related warnings if byllm is installed."""
    jac_file = str(Path(__file__).parent / "main.jac")
    commands = [
        [sys.executable, "-m", "jaclang.cli.cli", "run", jac_file],  # python -m jaclang ...
        ["jac", "run", jac_file],                                    # or jac run
    ]
    last = None
    for cmd in commands:
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode == 0:
            return {"returncode": 0, "stdout": p.stdout, "stderr": p.stderr, "cmd": cmd}
        last = p
    return {
        "returncode": last.returncode if last else -1,
        "stdout": last.stdout if last else "",
        "stderr": last.stderr if last else "no cmd",
        "tried": commands,
    }

# ---------------- retro UI ----------------
@app.get("/ui", response_class=HTMLResponse)
def ui():
    return (Path(__file__).parent / "static" / "ui.html").read_text(encoding="utf-8")

# ---------------- Gemini (official client) ----------------
def gemini_model():
    import google.generativeai as genai
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in environment.")
    genai.configure(api_key=api_key)
    model_name = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash-8b-latest")
    return genai.GenerativeModel(model_name)


def _json_from_text(txt: str) -> Dict[str, Any]:
    """Extract a JSON object from model text (handles ``` fences)."""
    t = (txt or "").strip()
    if t.startswith("```"):
        lines = [ln for ln in t.splitlines() if not ln.strip().startswith("```")]
        t = "\n".join(lines).strip()
    if "{" in t and "}" in t:
        t = t[t.index("{"): t.rindex("}") + 1]
    try:
        return json.loads(t)
    except Exception:
        return {}

ALLOWED_SEVERITY = {"LOW", "MEDIUM", "HIGH"}

def coerce_severity(s: str) -> str:
    s = (s or "").strip().upper()
    return s if s in ALLOWED_SEVERITY else "MEDIUM"

def as_float(x) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0

def llm_extract_scope(brief: str) -> Dict[str, Any]:
    """Ask the model for STRICT JSON matching our object shapes."""
    m = gemini_model()
    system = (
        "You generate software project scopes. Return STRICT JSON ONLY.\n"
        "Object with keys:\n"
        "  deliverables: [{title, description, est_hours(float)}]\n"
        "  milestones:   [{title, due_week(int), deliverables([titles])}]\n"
        "  assumptions:  [str]\n"
        "  out_of_scope: [str]\n"
        "  risks:        [{title, mitigation, severity in [LOW, MEDIUM, HIGH]}]\n"
        "No prose, no markdown."
    )
    prompt = f"BRIEF:\n{brief}\n\nProduce the JSON now."
    resp = m.generate_content([system, prompt])
    data = _json_from_text(getattr(resp, "text", "") or "") or {
        "deliverables": [],
        "milestones": [],
        "assumptions": [],
        "out_of_scope": [],
        "risks": [],
    }

    # light validation/coercion
    for d in data.get("deliverables", []):
        d["title"] = str(d.get("title", "")).strip()
        d["description"] = str(d.get("description", "")).strip()
        d["est_hours"] = as_float(d.get("est_hours"))

    for ml in data.get("milestones", []):
        ml["title"] = str(ml.get("title", "")).strip()
        ml["due_week"] = int(as_float(ml.get("due_week")))
        ml["deliverables"] = [str(x).strip() for x in ml.get("deliverables", [])]

    data["assumptions"] = [str(x).strip() for x in data.get("assumptions", [])]
    data["out_of_scope"] = [str(x).strip() for x in data.get("out_of_scope", [])]

    for r in data.get("risks", []):
        r["title"] = str(r.get("title", "")).strip()
        r["mitigation"] = str(r.get("mitigation", "")).strip()
        r["severity"] = coerce_severity(r.get("severity"))

    return data

def llm_summarize_md(scope: Dict[str, Any], currency: str, total_amount: float, client_name: str) -> str:
    m = gemini_model()
    currency = (currency or "USD").upper()
    seed = {
        "client": client_name,
        "total": f"{currency} {total_amount:,.2f}",
        "deliverables": scope.get("deliverables", []),
        "milestones": scope.get("milestones", []),
        "assumptions": scope.get("assumptions", []),
        "out_of_scope": scope.get("out_of_scope", []),
        "risks": scope.get("risks", []),
    }
    system = (
        "Return a succinct client-ready SUMMARY in MARKDOWN only. "
        "Use headings and bullet lists. No JSON."
    )
    prompt = (
        "Create a one-page proposal summary (Markdown) from this JSON:\n"
        f"{json.dumps(seed, ensure_ascii=False, indent=2)}\n\n"
        "Sections: Overview, Deliverables, Milestones, Assumptions, Out of scope, Risks, Pricing."
    )
    resp = m.generate_content([system, prompt])
    return (getattr(resp, "text", "") or "").strip()

# ---------------- API: create/list/get ----------------
@app.post("/proposals")
async def create_proposal(req: Request):
    body = await req.json()
    def g(k, d=None): return body.get(k, d)

    client_name = g("client_name")
    brief = g("brief")
    rate = g("hourly_rate")
    buffer_pct = g("buffer_pct")
    currency = (g("currency") or "").upper()

    if not client_name or not brief or currency not in ("KES", "USD"):
        raise HTTPException(status_code=400, detail="Missing required fields or invalid currency (KES|USD).")

    try:
        rate = float(rate)
        buffer_pct = float(buffer_pct)
    except Exception:
        raise HTTPException(status_code=400, detail="hourly_rate and buffer_pct must be numbers.")

    # 1) LLM scope
    scope = llm_extract_scope(brief)

    # 2) Deterministic totals
    subtotal_hours = sum(as_float(d.get("est_hours")) for d in scope.get("deliverables", []))
    subtotal_amount = round(subtotal_hours * rate, 2)
    buffer_amount = round(subtotal_amount * buffer_pct, 2)
    total_amount = round(subtotal_amount + buffer_amount, 2)

    # 3) Markdown summary
    summary_md = llm_summarize_md(scope, currency, total_amount, client_name)

    # 4) Persist
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
