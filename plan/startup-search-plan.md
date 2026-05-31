# Startup Search Dashboard Plan

## Goal
Build a local web dashboard that ingests a public, non-downloadable startup sheet through read-only browser scraping, researches 1.5k+ recently funded startups, ranks them for Ritam Ghosh's AI/ML internship search, and generates LinkedIn outreach messages on demand.

## User profile to optimize for
- 3rd-year B.Tech AI student at SRM University, Chennai.
- Strongest fit: AI/ML, LLM systems, multi-agent workflows, RAG, computer vision, FastAPI/Flask, Docker, LangGraph, LangSmith, vector search.
- Preference: remote-first globally, India onsite/hybrid acceptable.

## Product constraints
- Source sheet is public but cannot be downloaded/copied.
- Scrape rendered rows read-only. Do not mutate the source sheet.
- Scale: 1.5k+ startups.
- Cost mode: frugal two-pass.
- Messages should be generated on demand only for selected companies.

## Scoring formula: Balanced AI Internship Fit Score
- 35% AI-native product depth and innovation.
- 25% role fit to resume: LLM agents/RAG/CV/FastAPI/LLMOps.
- 20% hiring likelihood: active roles, founder hiring signals, recent raise.
- 10% learning/challenge: technical complexity, small team ownership.
- 10% logistics: remote-friendly or India onsite/hybrid.

## Hiring labels
- Yes: current relevant engineering/AI/software roles exist.
- Maybe: recent raise, tiny team, founder hiring posts, always-hiring language, or strong plausible need.
- No: no evidence found.
- Always include evidence/source notes.

## Product direction
Build a local dashboard with:
- Import from scraped sheet rows and optional CSV/JSON fallback.
- Resumable/cached research jobs.
- Company cards/table with filters and sort by fit score.
- Evidence notes and research confidence.
- CSV export.
- On-demand generation buttons for:
  - Short LinkedIn connection request.
  - Concise founder DM.

## Research pipeline
1. Browser scrape rendered sheet into normalized startup rows.
2. Crawl each company website, careers/jobs page, and public social links where available.
3. Pass 1 deterministic extraction/classification for all rows.
4. Pass 2 cheap LLM analysis only for likely AI-native or ambiguous/high-potential companies.
5. Optional better-model message generation only when the user clicks a message button.
6. Cache all fetched pages, analysis results, scores, and generated messages.

## Premise challenge outcome
Do not generate outreach for all 1.5k upfront. Rank first, let the user shortlist, then spend LLM budget only on companies they actually want to contact.

## Phase plan
1. Bootstrap isolated project and conda environment.
2. Implement backend data model, cache, deterministic scoring, and sample import/export.
3. Implement research crawler and LLM abstraction with dry-run/mock mode.
4. Implement dashboard UI with filtering, evidence display, and copy buttons.
5. Implement browser scraping assistant flow once the sheet link is available.
6. Validate with fixture data, unit tests, and a local smoke test.
