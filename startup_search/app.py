from __future__ import annotations
from pathlib import Path
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from .importers import startups_from_csv, startups_from_rows
from .llm import generate_message
from .models import MessageRequest, StartupInput
from .research import research_startup
from .sheet_scraper import scrape_google_sheet
from .storage import apply_research, export_csv, get_startup, import_startups, list_startups, save_message

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

@app.get('/', response_class=HTMLResponse)
def index() -> str:
    return (STATIC_DIR / 'index.html').read_text(encoding='utf-8')

@app.get('/api/startups')
def api_startups(limit: int = 5000, q: str | None = None):
    return [record.model_dump() for record in list_startups(limit=limit, query=q)]

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

async def research_batch(limit: int, only_unresearched: bool, max_confidence: int) -> None:
    records = list_startups(limit=5000)
    if only_unresearched:
        records = [r for r in records if r.research_confidence <= max_confidence]
    for record in records[:limit]:
        result = await research_startup(StartupInput(**record.model_dump(include={'company','website','linkedin','twitter','funding','raw'})))
        apply_research(record.id, result)

@app.post('/api/research')
def start_research(payload: ResearchPayload, background_tasks: BackgroundTasks):
    background_tasks.add_task(research_batch, payload.limit, payload.only_unresearched, payload.max_confidence)
    return {'status': 'queued', 'limit': payload.limit, 'only_unresearched': payload.only_unresearched, 'max_confidence': payload.max_confidence}

@app.post('/api/startups/{startup_id}/research')
async def research_one(startup_id: int):
    record = get_startup(startup_id)
    if not record:
        raise HTTPException(404, 'Startup not found')
    result = await research_startup(StartupInput(**record.model_dump(include={'company','website','linkedin','twitter','funding','raw'})))
    apply_research(startup_id, result)
    return get_startup(startup_id).model_dump()

@app.post('/api/startups/{startup_id}/message')
async def message(startup_id: int, request: MessageRequest):
    record = get_startup(startup_id)
    if not record:
        raise HTTPException(404, 'Startup not found')
    existing = record.message_short if request.style == 'short' else record.message_founder
    if existing and not request.force:
        return {'message': existing, 'cached': True}
    generated = await generate_message(record, request.style)
    save_message(startup_id, request.style, generated)
    return {'message': generated, 'cached': False}

@app.get('/api/export.csv')
def export():
    path = export_csv(Path('data/startup-search-export.csv'))
    return FileResponse(path, media_type='text/csv', filename='startup-search-export.csv')
