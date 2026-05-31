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

## AI score and website confirmation

The AI score is intentionally conservative:

- On import, the sheet/category/social metadata is used only for triage. Sheet-only AI matches are capped at **5/10** and tagged as **AI signal unconfirmed**.
- When you click **Research** or **Research next 100**, the app fetches the company homepage plus common careers URLs (`/careers`, `/jobs`, `/join-us`, `/company/careers`).
- A company only gets the **Website-confirmed AI-native** tag and can rise to **6-10/10** when its own fetched website text contains AI product language such as AI agents, LLMs, generative AI, computer vision, RAG, inference, vector search, or machine learning.
- If the sheet says AI but the website scrape does not confirm it, the score stays capped and the summary says that website confirmation is missing.

Hiring evidence works the same way: a `Yes` hiring label is shown with the matched evidence text and a careers/jobs/homepage link directly below it in the dashboard.

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
