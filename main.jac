# Proposal Template Engine — Jac core (Phase 2 scaffold, obj-based)

# 1) Bind a global LLM (Gemini)
import from byllm { Model }
glob llm = Model(model_name="gemini/gemini-2.0-flash", temperature=0.2);

# 2) Enums
enum Severity { LOW, MEDIUM, HIGH }
enum Currency { KES, USD }

# 3) Objects (use `obj` + `has` fields)
obj Deliverable {
    has title: str;
    has description: str;
    has est_hours: float;
}

obj Milestone {
    has title: str;
    has due_week: int;
    has deliverables: list[str];
}

obj Risk {
    has title: str;
    has mitigation: str;
    has severity: Severity;
}

obj ScopeOut {
    has deliverables: list[Deliverable];
    has milestones: list[Milestone];
    has assumptions: list[str];
    has out_of_scope: list[str];
    has risks: list[Risk];
}

# 4) LLM functions (signatures only; implement next phase)
def extract_scope(brief: str) -> ScopeOut by llm();
def summarize_md(scope: ScopeOut, currency: Currency, total_amount: float) -> str by llm();

# 5) Sanity entry
with entry {
    print("Jac OK · LLM bound · Objs ready.");
}
