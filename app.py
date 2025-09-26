from __future__ import annotations
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from pathlib import Path
import json, os, re, subprocess, time

BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
STORE = DATA_DIR / "proposals.json"

app = FastAPI(title="Proposal Template Engine", version="0.4.0")

# ---------- tiny store ----------
def read_store() -> dict:
    if STORE.exists():
        return json.loads(STORE.read_text(encoding="utf-8"))
    return {}

def write_store(data: dict) -> None:
    STORE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

# ---------- Jac helpers ----------
ANSI = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

def _strip_ansi(s: str) -> str:
    return ANSI.sub("", s or "")

def _last_json(s: str) -> dict | None:
    s2 = _strip_ansi(s)
    start = s2.rfind("{")
    if start < 0:
        return None
    depth = 0
    for i, ch in enumerate(s2[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s2[start:i+1])
                except Exception:
                    return None
    return None

def _jac_model() -> str:
    raw = (os.environ.get("GEMINI_MODEL") or "gemini-1.5-flash-8b-latest").strip()
    return raw if raw.startswith("gemini/") else f"gemini/{raw}"

def run_jac_extract_scope(brief: str) -> dict | None:
    """Run engine.jac and parse JSON payload."""
    env = os.environ.copy()
    env["BRIEF"] = brief
    env["GEMINI_API_KEY"] = env.get("GEMINI_API_KEY", "")
    env["JAC_MODEL"] = _jac_model()
    env["JAC_COLOR"] = "0"

    cmds = [
        ["jac", "run", "engine.jac", "--no-color"],
        [os.sys.executable, "-m", "jaclang.cli.cli", "run", "engine.jac", "--no-color"],
    ]
    last = None
    for cmd in cmds:
        try:
            p = subprocess.run(
                cmd, cwd=str(BASE_DIR), capture_output=True, text=True, timeout=180
            )
            last = p
            blob = (p.stdout or "") + "\n" + (p.stderr or "")
            js = _last_json(blob)
            if isinstance(js, dict):
                return js
        except Exception:
            continue
    if last:
        print("Jac failed:\nSTDOUT:\n", last.stdout, "\nSTDERR:\n", last.stderr)
    return None

# ---------- fallback if Jac/byLLM not available ----------
def fallback_scope(_: str) -> dict:
    return {
        "deliverables": [
            {"title":"New Homepage","description":"Modern landing page.","est_hours":30},
            {"title":"About Page","description":"Company story & team.","est_hours":20},
            {"title":"Product Pages","description":"Pages per product line.","est_hours":60},
            {"title":"Contact Form","description":"Lead capture form.","est_hours":10},
        ],
        "milestones": [
            {"title":"Design Approved","due_week":2,"deliverables":["New Homepage"]},
            {"title":"Product Pages Complete","due_week":6,"deliverables":["Product Pages"]},
            {"title":"Website Launch","due_week":8,"deliverables":["All"]},
        ],
        "assumptions":[
            "Client provides accurate product information.",
            "All necessary content is available.",
        ],
        "out_of_scope":["CRM integration","E-commerce"],
        "risks":[
            {"title":"Content delays","mitigation":"Agree deadlines with client.","severity":"MEDIUM"},
            {"title":"Tech glitches","mitigation":"Testing & QA plan.","severity":"MEDIUM"},
        ],
        "_source":"fallback_python",
    }

def compute_totals(scope: dict, currency: str, rate: float, buffer: float) -> dict:
    hours = sum(float(d.get("est_hours", 0)) for d in scope.get("deliverables", []))
    subtotal = hours * float(rate)
    buf_amt = subtotal * float(buffer)
    total = subtotal + buf_amt
    cur = currency.upper()

    def fmt(v: float) -> str:
        return f"KES {v:,.0f}" if cur == "KES" else f"USD {v:,.2f}"

    return {
        "subtotal_hours": round(hours, 2),
        "rate": float(rate),
        "subtotal": subtotal,
        "buffer": buf_amt,
        "total": total,
        "currency": cur,
        "fmt": {"subtotal": fmt(subtotal), "buffer": fmt(buf_amt), "total": fmt(total)},
    }

def scope_to_md(client: str, scope: dict, totals: dict) -> str:
    dl, ms, risks = scope.get("deliverables", []), scope.get("milestones", []), scope.get("risks", [])
    lines = []
    lines += [f"# Proposal Summary for {client or 'Client'}", "## Overview",
              "This proposal outlines the project scope derived from the client brief."]
    lines += ["## Deliverables"] + (
        [f"- **{d['title']}** — {d.get('description','')} (_{d.get('est_hours',0)} h_)"
         for d in dl] or ["- No deliverables were defined."]
    )
    lines += ["## Milestones"] + (
        [f"- **{m['title']}** — wk {m.get('due_week','?')}" for m in ms] or ["- No milestones were defined."]
    )
    lines += ["## Risks"] + [f"- **{r['title']}** — {r.get('mitigation','')} ({r.get('severity','')})" for r in risks]
    lines += ["## Cost", f"- Subtotal: {totals['fmt']['subtotal']}",
              f"- Buffer: {totals['fmt']['buffer']}",
              f"- **Total: {totals['fmt']['total']}**"]
    return "\n".join(lines)

# ---------- routes ----------
@app.get("/")
def health():
    return {"ok": True, "service": "proposal-template-engine"}

@app.get("/ui")
def ui():
    for p in [BASE_DIR/"ui.html", BASE_DIR/"static/ui.html", BASE_DIR/"static/index.html"]:
        if p.exists():
            return HTMLResponse(p.read_text(encoding="utf-8"))
    raise HTTPException(status_code=404, detail="UI not found. Put ui.html in project root or static/ui.html")

@app.post("/proposals")
async def create_proposal(req: Request):
    try:
        data = await req.json()
    except Exception:
        form = await req.form()
        data = {k: form.get(k) for k in ["client","currency","hourly_rate","buffer","brief"]}

    client   = (data.get("client") or "").strip()
    currency = (data.get("currency") or "USD").upper()
    rate     = float(data.get("hourly_rate") or 0)
    buffer   = float(data.get("buffer") or 0)
    brief    = (data.get("brief") or "").strip()

    scope = run_jac_extract_scope(brief)
    engine_used = "jac+byllm" if scope else "fallback_python"
    if not scope:
        scope = fallback_scope(brief)

    totals = compute_totals(scope, currency, rate, buffer)
    md = scope_to_md(client, scope, totals)

    store = read_store()
    pid = time.strftime("%Y%m%d-%H%M%S")
    store[pid] = {
        "client": client, "currency": currency, "hourly_rate": rate, "buffer": buffer,
        "brief": brief, "scope": scope, "totals": totals, "markdown": md,
        "engine": engine_used, "model": os.environ.get("GEMINI_MODEL","")
    }
    write_store(store)
    return {"ok": True, "id": pid, "engine": engine_used, "model": os.environ.get("GEMINI_MODEL",""),
            "scope": scope, "totals": totals, "markdown": md}
