# Team Reporting Agent (Agntic-reporter)

Educational but practical **Team Daily Reporting Agent**.

Team members submit free-form daily reports. Everything is stored in PostgreSQL.
An **Agentic AI** (tool-calling loop over OpenRouter) answers questions such as:

- «Amin هفته گذشته چه کارهایی انجام داده؟»
- «What did the team work on last week?»
- «Show everything related to Agentic Vulnerability Detection»
- «Which reports support this conclusion?»

The system **never invents** activities or exact progress percentages.
Facts, summaries, and estimates are kept distinct.

---

## Architecture

```
┌─────────────┐
│  Gradio UI  │  Chat · Add Report · History · Weekly
└──────┬──────┘
       │
┌──────▼──────┐     tool schemas      ┌──────────────────┐
│   Agent     │ ◄───────────────────► │  OpenRouter LLM  │
│  (loop)     │                       └──────────────────┘
└──────┬──────┘
       │ tool calls (Python)
       ▼
┌─────────────┐   ┌──────────────┐   ┌─────────────┐
│  Retrieval  │   │ Report Svc   │   │  Web Fetch  │
│  (SQL)      │   │ (parse+gen)  │   │  (httpx)    │
└──────┬──────┘   └──────┬───────┘   └─────────────┘
       │                 │
       └────────┬────────┘
                ▼
        ┌───────────────┐
        │  PostgreSQL   │
        │  reports tbl  │
        └───────────────┘
```

### Tool-calling loop (explicit)

```
User message
    → LLM (with tool schemas)
        → tool_calls? ──yes──→ Python executes tool(s)
              │                      │
             no                 results appended to messages
              │                      │
         Final answer  ←──────── LLM again
```

Tools: `search_reports`, `get_person_activity`, `get_project_activity`,
`get_reports_by_date_range`, `get_report_by_id`, `fetch_url`.

---

## Stack

- Python 3.12 · PostgreSQL 17 · SQLAlchemy 2.x + psycopg 3
- OpenRouter · Gradio · Docker Compose · pytest

---

## Quick start (Docker)

```bash
cp .env.example .env
# set OPENROUTER_API_KEY
docker compose up --build
```

- App: http://localhost:7860
- Postgres: localhost:5434

## Tests

```bash
pip install -r requirements.txt
pytest -v
```

Tests use in-memory SQLite and a mocked LLM (no API key required).

## Environment

```
DATABASE_URL=postgresql+psycopg://report_agent:report_agent_password@localhost:5434/daily_reports
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=openrouter/free
```

Never commit `.env`.

## Design principles

1. Explicit tool loop – no hidden agent framework magic.
2. Raw text is sacred – always stored; generated report is extra.
3. Facts vs inference – progress estimates must be labelled.
4. Retrieval is isolated – easy to later add embeddings in Postgres.
5. No over-engineering – no Redis, Celery, React, vector DB, auth.
