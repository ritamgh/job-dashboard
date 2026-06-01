from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from .importers import startups_from_csv, startups_from_rows
from .llm import generate_message, is_stale_message
from .models import MessageRequest, StartupInput
from .research import research_startup
from .sheet_scraper import scrape_google_sheet
from .storage import apply_research, cancel_research_run, create_research_run, export_csv, get_research_run, get_startup, import_startups, latest_research_run, list_startups, save_message

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

@app.get('/', response_class=HTMLResponse)
def index() -> str:
    return (STATIC_DIR / 'index.html').read_text(encoding='utf-8')

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

@app.get('/api/export.csv')
def export():
    path = export_csv(Path('data/startup-search-export.csv'))
    return FileResponse(path, media_type='text/csv', filename='startup-search-export.csv')
