# Startup Search Dashboard + Outreach Cockpit

A local research dashboard for turning a large startup spreadsheet into an evidence-backed internship/outreach target list.

I built this for my own AI/ML internship search: import a public startup list, research each company, rank it for fit, estimate team size, generate founder-focused outreach, and send only after manual review.

## Source dataset

The original startup list is a public, view-only Google Sheet:

<https://docs.google.com/spreadsheets/d/1w11kuIGWOVATOad5acQqVWSzELF25xCyP6j3yoBiEUc/edit?gid=0#gid=0>

The app reads it in a read-only way. It does not mutate the sheet.

## What it does

### Startup research dashboard

- Imports 1.5k+ startup rows from the public Google Sheet.
- Preserves and normalizes company name, website, company LinkedIn/X, founder LinkedIn/X, and funding/category fields.
- Scores companies for AI/ML internship fit using a balanced formula:
  - 35% AI-native product depth and innovation
  - 25% resume fit for LangGraph/RAG/CV/FastAPI/LLMOps
  - 20% hiring likelihood
  - 10% learning/challenge
  - 10% remote/India feasibility
- Shows sortable score columns, filters, hiring evidence, source links, tags, and CSV export.
- Generates short LinkedIn DMs, founder DMs, and cold emails on demand.
- Adds a dashboard **Send Email** button that opens a reviewed draft in the Outreach Cockpit. It does not send directly from the table.

### Evidence-backed research

The score is intentionally conservative:

- Sheet/category/social metadata is only a triage signal.
- Sheet-only AI matches are capped at **5/10** and tagged `AI signal unconfirmed`.
- When you click **Research**, **Research next 100**, or **Research all unverified**, the app fetches the company homepage plus common careers URLs.
- A company can rise to **6-10/10** only when its fetched website/careers text confirms AI-native language such as agents, LLMs, RAG, inference, vector search, computer vision, or ML.
- Hiring status works similarly: `Yes` should come from fetched website/careers evidence, not just spreadsheet metadata.

### Scrapy research queue

Batch research uses a durable SQLite queue plus a Scrapy worker.

The dashboard can enqueue:

- **Research next 100**
- **Research all unverified**

The queue tracks pending/running/completed/failed/`needs_browser` rows. Scrapy handles the fast/static path first: homepage, common careers paths, discovered careers links, and linked ATS pages. Thin JavaScript shells are marked `needs_browser` for a later Playwright fallback instead of blocking the run.

Manual worker run:

```bash
python -m startup_search.crawler.runner --run-id <RUN_ID> --limit 100
```

### Outreach Cockpit

The standalone `/outreach` page is for arbitrary company URLs, not just rows from the sheet.

It can:

- Create an outreach session from any company website.
- Research the company.
- Discover visible contact candidates via Serper/Google search.
- Generate editable cold email, LinkedIn DM, and follow-up drafts.
- Let you manually choose or type a recipient.
- Send through a Gmail MCP command only after explicit review and confirmation.

Safety boundary: there is no hidden auto-send. Sending is gated by both the browser confirmation dialog and the API field `confirm_send: true`. If no Gmail MCP command is configured, sending returns a dry-run failure instead of sending anything.

### Contact discovery

Contact discovery is intentionally conservative. It searches for visible public signals and avoids inventing confident emails.

Current query pattern includes:

- `site:<domain> email founder OR careers OR contact`
- `<company> founder email`
- `<company> hiring manager email`
- `<company> LinkedIn founder`
- `<company> contact`

Candidates are scored by whether they have:

- a visible email
- a company-domain email
- a LinkedIn profile
- a source URL on the company domain

Generic emails such as `help@` or `support@` are useful as fallbacks, but founder LinkedIn/founder email is the preferred outreach path.

### Company size estimates

The dashboard includes a **Team size** column with a per-row **Find size** button.

This uses Serper search snippets, especially LinkedIn/Wellfound/company-profile snippets, to produce a sourced estimate such as `11-50 employees` with confidence and a source URL.

Treat this as targeting evidence, not exact headcount. The goal is to prioritize small teams where founder outreach is more likely to work.

## Tech stack

- FastAPI backend
- SQLite local storage with WAL mode
- Static HTML/CSS/JS frontend
- Scrapy for batch static-site research
- Playwright fallback support for Google Sheet/browser scraping
- OpenAI optional for higher-quality message generation
- Serper optional for contact discovery and company-size estimates
- Gmail MCP optional for sending reviewed email drafts

## Setup

Requires Python 3.11+.

```bash
git clone https://github.com/ritamgh/job-mcp.git
cd job-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
python -m uvicorn startup_search.app:app --reload
```

Open:

<http://127.0.0.1:8000>

If you use conda instead:

```bash
conda create -n startup-search python=3.11 -y
conda activate startup-search
pip install -e .
python -m uvicorn startup_search.app:app --reload
```

## Environment variables

All env vars are optional unless you want the corresponding integration.

```bash
# Optional: better research/outreach writing. Without this, local fallback messages are used.
STARTUP_SEARCH_OPENAI_API_KEY=
STARTUP_SEARCH_OPENAI_ANALYSIS_MODEL=gpt-4.1-mini
STARTUP_SEARCH_OPENAI_MESSAGE_MODEL=gpt-4.1-mini

# Optional: required for contact discovery and company-size lookup.
STARTUP_SEARCH_SERPER_API_KEY=
STARTUP_SEARCH_SERPER_ENDPOINT=https://google.serper.dev/search
STARTUP_SEARCH_CONTACT_SEARCH_LIMIT=5

# Optional: required for real Gmail sending.
# Leave blank unless you have a Gmail MCP command configured.
STARTUP_SEARCH_GMAIL_MCP_COMMAND=
```

Do not commit `.env`. It is ignored by git.

## Typical workflow

1. Start the app.
2. Open the dashboard at `/`.
3. Click **Read-only scrape sheet** to import the source sheet, or use the bundled CSV snapshot.
4. Use filters/sort columns to find promising companies.
5. Click **Research** for individual rows or run batch research.
6. Click **Find size** to estimate team size for promising companies.
7. Generate founder DM/email drafts on demand.
8. Click **Send Email** to open a reviewed draft in `/outreach`.
9. Edit the email manually.
10. Send only after explicit confirmation, if Gmail MCP is configured.

## Data and privacy notes

- `data/startup_search.db` is local and ignored.
- `.env` is ignored.
- Runtime logs/caches are ignored.
- The repository includes a CSV snapshot generated from the source sheet for convenience.
- The app is designed for personal/local use, not as a hosted SaaS product.

## Tests

```bash
pytest
```

Current test coverage includes:

- scoring behavior
- Google Sheet parsing helpers
- import normalization
- research queue storage
- outreach session/draft/send safety
- Serper contact parsing
- company-size parsing

## Public repo safety

Before this repo was made public, tracked files and git history were scanned for common API key/token patterns. Secrets should live only in your local `.env`.
