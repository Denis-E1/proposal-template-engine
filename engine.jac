# Jac LLM engine (typed) — produces a ScopeOut JSON for the Python app

# Import via Python interop (works across Jac versions)
py import os;
py import json;
py import byllm;

# LLM model (reads env JAC_MODEL if set, else defaults)
glob llm = byllm.Model(model_name=os.getenv("JAC_MODEL", "gemini/gemini-1.5-flash-8b-latest"));

# Typed enums & objects
enum Severity { LOW, MEDIUM, HIGH }

obj Deliverable { has title: str; has description: str; has est_hours: float; }
obj Milestone   { has title: str; has due_week: int; has deliverables: list[str]; }
obj Risk        { has title: str; has mitigation: str; has severity: Severity; }

obj ScopeOut {
    has deliverables: list[Deliverable];
    has milestones: list[Milestone];
    has assumptions: list[str];
    has out_of_scope: list[str];
    has risks: list[Risk];
}

# Typed LLM function (Jac will call llm.invoke under the hood)
def extract_scope(brief: str) -> ScopeOut by llm();

# Semantic spec for the LLM (no prompt engineering in code)
sem extract_scope = """
You are a project analyst. From the client brief, produce:
- 3-8 Deliverables (title, 1-sentence description, est_hours float 5..200)
- 3-6 Milestones (title, due_week 1..16, deliverables [titles])
- 3-8 Assumptions (list[str])
- 2-6 Out-of-scope items (list[str])
- 2-5 Risks (title, mitigation, severity in {LOW, MEDIUM, HIGH})
Return exactly a ScopeOut instance.
""";

# Convert the typed object to JSON for the Python app to parse
def to_json(scope: ScopeOut) -> str {
    let d = {
        "deliverables": [ {"title": x.title, "description": x.description, "est_hours": x.est_hours} for x in scope.deliverables ],
        "milestones":   [ {"title": m.title, "due_week": m.due_week, "deliverables": m.deliverables} for m in scope.milestones ],
        "assumptions": scope.assumptions,
        "out_of_scope": scope.out_of_scope,
        "risks":        [ {"title": r.title, "mitigation": r.mitigation, "severity": f"{r.severity}"} for r in scope.risks ],
        "_source": "jac+byllm",
    };
    return json.dumps(d);
}

# Entry — Python app sets BRIEF env; we print JSON to stdout
with entry {
    let brief = os.getenv("BRIEF", "");
    if brief == "" {
        print("# engine ready — set BRIEF env when running from the app.");
    } else {
        let s = extract_scope(brief=brief);
        print(to_json(scope=s));
    }
}
