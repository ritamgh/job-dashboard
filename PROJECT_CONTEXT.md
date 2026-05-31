# Project Context

## Purpose
Local research dashboard for ranking 1.5k+ recently funded startups for Ritam Ghosh's AI/ML internship search. The app ingests a public, non-downloadable Google Sheet via read-only extraction, researches company websites/jobs pages, scores AI-native internship fit, and generates LinkedIn outreach messages on demand.

## Key user constraints
- Optimize for balanced fit: interesting AI-native products plus realistic hiring chance.
- User profile: 3rd-year B.Tech AI student with LangGraph agents, RAG, CV deployments, FastAPI/Flask, Docker, LangSmith, vector search.
- Logistics: remote-first globally, India onsite/hybrid acceptable.
- Cost mode: frugal two-pass. Do not generate outreach for all companies upfront.

## Architecture
- Backend: FastAPI app in `startup_search/`.
- Storage: local SQLite database under `data/startup_search.db` by default, plus optional fetch cache.
- Frontend: static HTML/CSS/JS served from `startup_search/static/`.
- Tests: `tests/` run with pytest in the `startup-search` conda environment.

## Main commands
```bash
conda activate startup-search
python -m uvicorn startup_search.app:app --reload
pytest
```

The provided sheet has already been imported locally once. A CSV snapshot exists at `data/startup-search-export.csv`; the SQLite working database is ignored by git at `data/startup_search.db`.

## Important paths
- `plan/startup-search-plan.md`: discovery and execution plan.
- `resume/master_resume 2.pdf`: source resume used for targeting.
- `startup_search/app.py`: FastAPI routes.
- `startup_search/storage.py`: SQLite schema and persistence helpers.
- `startup_search/scoring.py`: deterministic scoring and labels.
- `startup_search/research.py`: crawler/research pipeline.
- `startup_search/llm.py`: OpenAI abstraction and dry-run message generation.
- `startup_search/sheet_scraper.py`: Google Sheet extraction helpers.
- `data/startup-search-export.csv`: latest enriched/exportable CSV snapshot generated from the sheet.

## Gotchas
- The source sheet returned 401 from the CSV export endpoint, but the Google Visualization endpoint works with `headers=0` and returns 1,562 startup rows after skipping founder-continuation rows. `startup_search/sheet_scraper.py` uses this first, then falls back to rendered Playwright extraction.
- Browser bridge setup currently needs manual Firefox extension approval, so app-level Playwright is the reliable scraping path.
- The parent `/home/atom` git repo has unrelated dirty dotfiles. This project is isolated with its own `.git` under `/home/atom/Developer/job-mcp`.
- AI scoring is source-aware: sheet/category signals are triage only, capped at 5/10 and tagged `AI signal unconfirmed`; website/careers fetched text can produce `Website-confirmed AI-native` and 6-10/10.
- Hiring `Yes` should only come from fetched website/careers evidence. Sheet-only rows are `Maybe` with `Hiring unverified`; the UI shows hiring evidence text plus the best careers/jobs/homepage evidence link below the label.
