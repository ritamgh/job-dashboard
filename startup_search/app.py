from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from .company_size import estimate_company_size
from .importers import startups_from_csv, startups_from_rows
from .llm import generate_message, is_stale_message
from .models import MessageRequest, OutreachDraftUpdate, OutreachSendRequest, OutreachSessionCreate, ResearchResult, StartupInput, StartupRecord
from .outreach import discover_contacts, generate_drafts, research_session, send_draft, split_subject_body
from .research import research_startup
from .sheet_scraper import scrape_google_sheet
from .storage import apply_research, cancel_research_run, create_outreach_draft, create_outreach_session, create_research_run, export_csv, get_outreach_session, get_research_run, get_startup, import_startups, latest_research_run, list_outreach_contacts, list_outreach_drafts, list_outreach_sessions, list_startups, save_company_size, save_message, save_outreach_research, update_outreach_draft

app = FastAPI(title='Startup Search Dashboard')
STATIC_DIR = Path(__file__).parent / 'static'
app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')

class RowsPayload(BaseModel):
    rows: list[dict]

class SheetPayload(BaseModel):
    url: str
    max_scrolls: int = 120

class ResearchPayload(BaseModel):
    limit: int = 100
    only_unresearched: bool = True
    max_confidence: int = 6
    start_worker: bool = True


def research_result_from_record(record: StartupRecord) -> ResearchResult:
    return ResearchResult(
        product_summary=record.product_summary or 'Not researched yet.',
        ai_native_score=record.ai_native_score,
        interestingness_score=record.interestingness_score,
        resume_fit_score=record.resume_fit_score,
        hiring_likelihood_score=record.hiring_likelihood_score,
        learning_challenge_score=record.learning_challenge_score,
        logistics_score=record.logistics_score,
        hiring_status=record.hiring_status,
        hiring_evidence=record.hiring_evidence or 'No hiring evidence yet.',
        remote_india_fit=record.remote_india_fit or 'Unknown',
        research_confidence=record.research_confidence,
        evidence_urls=record.evidence_urls,
        tags=record.tags,
    )

@app.get('/', response_class=HTMLResponse)
def index() -> str:
    return (STATIC_DIR / 'index.html').read_text(encoding='utf-8')


@app.get('/outreach', response_class=HTMLResponse)
def outreach_page() -> str:
    return (STATIC_DIR / 'outreach.html').read_text(encoding='utf-8')


@app.get('/api/outreach/sessions')
def outreach_sessions(limit: int = 50):
    return list_outreach_sessions(limit)


@app.post('/api/outreach/sessions')
def create_outreach(payload: OutreachSessionCreate):
    if not payload.website.strip():
        raise HTTPException(400, 'Website is required')
    return create_outreach_session(payload.website.strip(), payload.company.strip() if payload.company else None)


@app.get('/api/outreach/sessions/{session_id}')
def read_outreach(session_id: int):
    session = get_outreach_session(session_id)
    if not session:
        raise HTTPException(404, 'Outreach session not found')
    session['contacts'] = list_outreach_contacts(session_id)
    session['drafts'] = list_outreach_drafts(session_id)
    return session


@app.post('/api/outreach/sessions/{session_id}/research')
async def research_outreach(session_id: int):
    try:
        return await research_session(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post('/api/outreach/sessions/{session_id}/contacts')
async def contacts_outreach(session_id: int):
    try:
        return await discover_contacts(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post('/api/outreach/sessions/{session_id}/drafts')
async def drafts_outreach(session_id: int):
    try:
        return await generate_drafts(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.patch('/api/outreach/drafts/{draft_id}')
def edit_outreach_draft(draft_id: int, payload: OutreachDraftUpdate):
    draft = update_outreach_draft(draft_id, payload.edited_subject, payload.edited_body, payload.contact_id)
    if not draft:
        raise HTTPException(404, 'Outreach draft not found')
    return draft


@app.post('/api/outreach/drafts/{draft_id}/send')
def send_outreach_draft(draft_id: int, payload: OutreachSendRequest):
    try:
        return send_draft(draft_id, payload.to, payload.subject, payload.body, payload.confirm_send)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

@app.get('/api/startups')
def api_startups(limit: int = 5000, q: str | None = None):
    rows = []
    for record in list_startups(limit=limit, query=q):
        data = record.model_dump()
        if is_stale_message(data.get('message_short')):
            data['message_short'] = None
        if is_stale_message(data.get('message_founder')):
            data['message_founder'] = None
        if is_stale_message(data.get('message_email')):
            data['message_email'] = None
        rows.append(data)
    return rows

@app.post('/api/import/csv')
async def import_csv(file: UploadFile = File(...)):
    text = (await file.read()).decode('utf-8-sig', errors='replace')
    ids = import_startups(startups_from_csv(text))
    return {'imported': len(ids), 'ids': ids[:20]}

@app.post('/api/import/rows')
def import_rows(payload: RowsPayload):
    ids = import_startups(startups_from_rows(payload.rows))
    return {'imported': len(ids), 'ids': ids[:20]}

@app.post('/api/import/google-sheet')
async def import_google_sheet(payload: SheetPayload):
    rows = await scrape_google_sheet(payload.url, payload.max_scrolls)
    ids = import_startups(startups_from_rows(rows))
    return {'scraped_rows': len(rows), 'imported': len(ids), 'ids': ids[:20]}

def start_scrapy_worker(run_id: int, limit: int) -> str:
    log_dir = Path('data/crawler_logs')
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f'research-run-{run_id}.log'
    env = os.environ.copy()
    env['PYTHONPATH'] = f"{Path.cwd()}{os.pathsep}{env.get('PYTHONPATH', '')}"
    with log_path.open('ab') as log_file:
        subprocess.Popen(
            [sys.executable, '-m', 'startup_search.crawler.runner', '--run-id', str(run_id), '--limit', str(limit)],
            cwd=Path.cwd(),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return str(log_path)

@app.post('/api/research')
def start_research(payload: ResearchPayload):
    run = create_research_run(payload.limit, payload.only_unresearched, payload.max_confidence)
    log_path = start_scrapy_worker(run['id'], payload.limit) if payload.start_worker and run.get('total', 0) else None
    run = get_research_run(run['id']) or run
    return {'status': 'queued', 'run': run, 'log_path': log_path}


@app.post('/api/research-runs')
def create_run(payload: ResearchPayload):
    run = create_research_run(payload.limit, payload.only_unresearched, payload.max_confidence)
    log_path = start_scrapy_worker(run['id'], payload.limit) if payload.start_worker and run.get('total', 0) else None
    run = get_research_run(run['id']) or run
    return {'run': run, 'log_path': log_path}


@app.get('/api/research-runs/latest')
def latest_run():
    return latest_research_run() or {}


@app.get('/api/research-runs/{run_id}')
def read_run(run_id: int):
    run = get_research_run(run_id)
    if not run:
        raise HTTPException(404, 'Research run not found')
    return run


@app.post('/api/research-runs/{run_id}/cancel')
def cancel_run(run_id: int):
    run = cancel_research_run(run_id)
    if not run:
        raise HTTPException(404, 'Research run not found')
    return run

@app.post('/api/startups/{startup_id}/research')
async def research_one(startup_id: int):
    record = get_startup(startup_id)
    if not record:
        raise HTTPException(404, 'Startup not found')
    result = await research_startup(StartupInput(**record.model_dump(include={'company','website','linkedin','founder_linkedin','twitter','founder_twitter','funding','raw'})))
    apply_research(startup_id, result)
    return get_startup(startup_id).model_dump()

@app.post('/api/startups/{startup_id}/message')
async def message(startup_id: int, request: MessageRequest):
    record = get_startup(startup_id)
    if not record:
        raise HTTPException(404, 'Startup not found')
    existing = {
        'short': record.message_short,
        'founder': record.message_founder,
        'email': record.message_email,
    }[request.style]
    if existing and not request.force and not is_stale_message(existing):
        return {'message': existing, 'cached': True}
    generated = await generate_message(record, request.style)
    save_message(startup_id, request.style, generated)
    return {'message': generated, 'cached': False}


@app.post('/api/startups/{startup_id}/outreach-session')
async def startup_outreach_session(startup_id: int):
    record = get_startup(startup_id)
    if not record:
        raise HTTPException(404, 'Startup not found')
    if not record.website:
        raise HTTPException(400, 'Startup website is required to create an outreach session')
    session = create_outreach_session(record.website, record.company)
    save_outreach_research(session['id'], research_result_from_record(record))
    message_text = record.message_email
    if not message_text or is_stale_message(message_text):
        message_text = await generate_message(record, 'email')
        save_message(startup_id, 'email', message_text)
    subject, body = split_subject_body(message_text, record.company)
    if not list_outreach_drafts(session['id']):
        create_outreach_draft(session['id'], {'channel': 'email', 'subject': subject, 'body': body})
    session = get_outreach_session(session['id']) or session
    session['drafts'] = list_outreach_drafts(session['id'])
    session['contacts'] = list_outreach_contacts(session['id'])
    return session


@app.post('/api/startups/{startup_id}/company-size')
async def company_size(startup_id: int):
    record = get_startup(startup_id)
    if not record:
        raise HTTPException(404, 'Startup not found')
    estimate = await estimate_company_size(record.company, record.website, record.linkedin)
    if not estimate:
        return {'company_size_estimate': None, 'company_size_confidence': 0, 'company_size_source_url': None, 'company_size_source_snippet': None}
    save_company_size(startup_id, estimate)
    return get_startup(startup_id).model_dump()

@app.get('/api/export.csv')
def export():
    path = export_csv(Path('data/startup-search-export.csv'))
    return FileResponse(path, media_type='text/csv', filename='startup-search-export.csv')
