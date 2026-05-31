# Startup Search Dashboard

Local dashboard for ranking 1.5k+ recently funded startups for an AI/ML internship search.

## Setup

```bash
conda activate startup-search
python -m uvicorn startup_search.app:app --reload
```

Open <http://127.0.0.1:8000>.

## What it does

- Imports the provided view-only Google Sheet through the public Google Visualization endpoint, with Playwright-rendered scraping as fallback.
- Preserves original sheet columns and normalizes company, website, LinkedIn, Twitter, and funding/category fields.
- Scores companies using the approved Balanced AI Internship Fit formula:
  - 35% AI-native product depth and innovation
  - 25% resume fit for LangGraph/RAG/CV/FastAPI/LLMOps
  - 20% hiring likelihood
  - 10% learning/challenge
  - 10% remote/India feasibility
- Provides filters, sortable score columns, evidence notes, CSV export, and on-demand LinkedIn messages.

## Optional OpenAI key

The app works without an API key using local fallback messages. For higher-quality on-demand messages:

```bash
cp .env.example .env
# edit .env and set STARTUP_SEARCH_OPENAI_API_KEY
```

Messages are generated only when you click a message button, so costs stay low.

## Tests

```bash
conda activate startup-search
pytest
```
