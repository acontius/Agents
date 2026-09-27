# Team Reporting Agent (Agntic-reporter)

Educational team reporting agent: store daily reports in PostgreSQL, generate
**English Markdown** daily / weekly / monthly reports with **Jalali dates**,
and answer questions via a real OpenRouter **tool-calling** agent.

## Features

| Area | Behavior |
|------|----------|
| **Add Report** | Select Jalali date from dropdown; English `#daily` Markdown generated |
| **Reports** | Daily / Weekly / Monthly via period dropdowns (no typed dates) |
| **Weekly table** | Sat–Thu board columns + Goal + Final % (evidence-based only) |
| **History** | Jalali labels; no database IDs; session-safe ORM serialization |
| **Chat** | Gradio messages format + real agent tool loop |

## Report formats

**Daily** — `#daily # username` with Jalali date, entered/done times, English actions.

**Weekly** — narrative sections (Assigned / Completed / In Progress / Next Week /
Blockers / Suggestions) plus board table:

`Person | Saturday | Sunday | Monday | Tuesday | Wednesday | Thursday | Goal | Final %`

Week number is computed in Python (Iranian work week: Saturday–Thursday).
**Final %** comes only from an explicit percentage in the **previous** week’s
reports; otherwise `N/A`.

**Monthly** — same narrative idea for the Jalali month + summary table.

## Stack

Python 3.12 · PostgreSQL · SQLAlchemy 2 · Gradio · OpenRouter · Docker Compose

## Quick start

```bash
cp .env.example .env   # set OPENROUTER_API_KEY
docker compose up -d --build
# UI: http://localhost:7860
```

```bash
pytest -q
python -m compileall app tests
```

## Architecture

```
User → Gradio → Agent (tool loop) → PostgreSQL / URL fetch → LLM → answer
                 Reports UI → aggregation (Python dates + LLM summary)
```

Jalali conversion: `app/jalali.py` (no external calendar dependency).
Gregorian dates remain the database source of truth.
