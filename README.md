![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)![Jac](https://img.shields.io/badge/Jac-0.8.x-7A1FA2)![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)

# Proposal Template Engine 

A minimal service that leverages **Google Gemini** to transform a client brief into a structured project proposal, complete with estimated costs and a clean Markdown summary. It demonstrates both native Python API calls and advanced **typed LLM calls using Jac (`by llm()`)**.

-----

##  Features & Technologies

| Category | Detail |
| :--- | :--- |
| **LLM** | **Google Gemini** (via `google-generativeai` Python SDK) |
| **API** | **FastAPI** (`/proposals` endpoint) |
| **UI** | Minimal single-page HTML at `/ui` |
| **Storage** | Local JSON file (`data/proposals.json`) |
| **Typed LLM (Optional)** | **Jac** (`jaclang` + `byllm`) for strict, schema-driven LLM output |
| **Currencies** | **USD**, **KES** |

### Demo: What You Get

By inputting the client name, hourly rate, buffer percentage, and a free-form brief, the engine returns:

1.  **Structured Scope:** Deliverables (with estimated hours), Milestones, Assumptions, Out-of-Scope items, and Risks.
2.  **Totals:** Subtotal, buffer, and final costs calculated based on the rate and buffer.
3.  **Summary:** A clean, downloadable **Markdown** file of the full proposal.

-----

##  Project Structure

```bash
.
├─ app.py                  # FastAPI service + simple UI endpoint
├─ engine.jac              # Jac typed LLM engine (optional, used when USE_JAC=1)
├─ static/
│  ├─ ui.html              # Retro minimal UI (served at /ui)
│  └─ index.html           # Optional landing page
├─ data/
│  └─ proposals.json       # Local persistence (created on first save)
├─ requirements.txt
└─ README.md
```

-----

##  Quick Start (Local)

### Requirements

  * **Python 3.12+**
  * A **Google Gemini API key** (Get one here: [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey))

<!-- end list -->

1.  **Clone the repository and set up a Virtual Environment (Venv):**

    ```bash
    git clone https://github.com/<your-username>/proposal-template-engine.git
    cd proposal-template-engine

    python3.12 -m venv .venv
    source .venv/bin/activate
    python -m pip install -U pip
    ```

    *(Windows PowerShell: `.venv\Scripts\Activate.ps1`)*

2.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

    This installs FastAPI, Uvicorn, and the `google-generativeai` client.

3.  **Set environment variables:**

    | OS/Shell | Command |
    | :--- | :--- |
    | **Linux/macOS** | `export GEMINI_API_KEY="YOUR_API_KEY"` |
    | **Windows PowerShell** | `setx GEMINI_API_KEY "YOUR_API_KEY"` |

    *(Optional Model: `export GEMINI_MODEL="gemini-1.5-flash-8b-latest"`)*

4.  **Run the server:**

    ```bash
    uvicorn app:app --host 0.0.0.0 --port 8000
    ```

    Open the UI in your browser: **http://localhost:8000/ui**

-----

##  API Reference

The service is driven by a single **POST** endpoint: `/proposals`.

### Request Body (`POST /proposals`)

| Key | Type | Description |
| :--- | :--- | :--- |
| `client` | `str` | Name of the client/project. |
| `brief` | `str` | Free-form description of the project needs. |
| `rate` | `int/float` | Hourly rate for calculations. |
| `currency` | `str` | **USD** or **KES** only. |
| `buffer` | `float` | Contingency buffer as a decimal (e.g., `0.20` for 20%). |

```json
{
  "client": "Sarah",
  "brief": "We are a growing B2B software company. Redesign our website and integrate it with our CRM.",
  "rate": 52,
  "currency": "USD",
  "buffer": 0.20
}
```

### Response (Truncated)

The response provides structured data for the scope, calculated totals, and a raw Markdown summary.

```json
{
  "ok": true,
  "id": "20250926-095421",
  "engine": "fallback_python",
  "scope": {
    "deliverables": [
      {"title":"New Homepage","description":"...","est_hours":40},
      // ... more deliverables
    ],
    // ... milestones, assumptions, risks
  },
  "totals": {
    "subtotal_hours": 135.0,
    "total": 8424.0,
    "currency": "USD"
  },
  "markdown": "# Proposal Summary for Sarah\n..."
}
```

Results are persisted locally in `data/proposals.json`.

-----

##  Use Typed Jac Engine (Optional)

The service can switch to a **Jac engine** (`engine.jac`) which utilizes `by llm()` functions for **stricter, meaning-typed LLM output**. This eliminates the need for complex prompt engineering in Python.

1.  **Install Jac and byLLM:**

    ```bash
    pip install jaclang byllm
    ```

2.  **Set the Jac LLM environment variables:**
    *Note: The provider prefix (`gemini/`) is required by byLLM/LiteLLM.*

    ```bash
    export JAC_MODEL="gemini/gemini-1.5-flash-8b-latest"
    ```

3.  **Tell the app to use the Jac engine:**

    ```bash
    export USE_JAC=1
    uvicorn app:app --host 0.0.0.0 --port 8000
    ```

    The app will now execute `jac run engine.jac` to call the typed `extract_scope(brief)` function and return its structured JSON.

-----

## Tips & Troubleshooting

| Issue | Solution |
| :--- | :--- |
| **`ModuleNotFoundError: google.generativeai`** | Your venv isn't active or dependencies aren't installed. Run `source .venv/bin/activate` and `pip install -r requirements.txt`. |
| **"UI not found. Missing static/ui.html"** | Make sure you start Uvicorn from the **repo root** (`uvicorn app:app ...`) where `app.py` is located. |
| **Jac/byLLM issues** | **Ensure `GEMINI_API_KEY` is set.** Verify your Jac model name includes the provider prefix, e.g., `gemini/gemini-1.5-flash-8b-latest`. Run `pip install -U jaclang byllm` to upgrade. |
| **Nothing changes after setting env vars** | **You must restart the Uvicorn process** after changing any environment variables (`GEMINI_API_KEY`, `USE_JAC`, etc.). |
| **Results save location** | Results are saved to `data/proposals.json`. You can safely delete this file to reset history. |

### Development Notes

  * **Keep API keys out of Git.** Use environment variables or a `.env` file that is not committed.
  * This project was built for a GenAI course to demonstrate **typed LLM capabilities** via Jac/byLLM.

-----

##  License

**MIT** 