from __future__ import annotations
import csv
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable
from .config import get_settings
from .models import ResearchResult, StartupInput, StartupRecord
from .scoring import deterministic_research, weighted_overall

SCHEMA = '''
CREATE TABLE IF NOT EXISTS startups (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company TEXT NOT NULL,
  website TEXT,
  linkedin TEXT,
  twitter TEXT,
  funding TEXT,
  raw_json TEXT NOT NULL DEFAULT '{}',
  product_summary TEXT,
  ai_native_score INTEGER NOT NULL DEFAULT 0,
  interestingness_score INTEGER NOT NULL DEFAULT 0,
  resume_fit_score INTEGER NOT NULL DEFAULT 0,
  hiring_likelihood_score INTEGER NOT NULL DEFAULT 0,
  learning_challenge_score INTEGER NOT NULL DEFAULT 0,
  logistics_score INTEGER NOT NULL DEFAULT 0,
  overall_score REAL NOT NULL DEFAULT 0,
  hiring_status TEXT NOT NULL DEFAULT 'Unknown',
  hiring_evidence TEXT,
  remote_india_fit TEXT,
  research_confidence INTEGER NOT NULL DEFAULT 0,
  evidence_urls_json TEXT NOT NULL DEFAULT '[]',
  tags_json TEXT NOT NULL DEFAULT '[]',
  message_short TEXT,
  message_founder TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_startups_company_website ON startups(company, COALESCE(website, ''));

CREATE TABLE IF NOT EXISTS research_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  status TEXT NOT NULL DEFAULT 'pending',
  total INTEGER NOT NULL DEFAULT 0,
  completed INTEGER NOT NULL DEFAULT 0,
  failed INTEGER NOT NULL DEFAULT 0,
  needs_browser INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS research_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  startup_id INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  needs_browser INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(run_id, startup_id)
);
CREATE INDEX IF NOT EXISTS idx_research_jobs_run_status ON research_jobs(run_id, status, id);

CREATE TABLE IF NOT EXISTS research_fetches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id INTEGER NOT NULL,
  url TEXT NOT NULL,
  final_url TEXT,
  status_code INTEGER,
  content_type TEXT,
  text_chars INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_research_fetches_job ON research_fetches(job_id);
'''

@contextmanager
def connect():
    settings = get_settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=5000')
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_record(row: sqlite3.Row) -> StartupRecord:
    data = dict(row)
    data['raw'] = json.loads(data.pop('raw_json') or '{}')
    data['evidence_urls'] = json.loads(data.pop('evidence_urls_json') or '[]')
    data['tags'] = json.loads(data.pop('tags_json') or '[]')
    data.pop('created_at', None)
    data.pop('updated_at', None)
    return StartupRecord(**data)


def upsert_startup(startup: StartupInput) -> int:
    with connect() as conn:
        existing = conn.execute('SELECT id FROM startups WHERE company=? AND COALESCE(website, "")=COALESCE(?, "")', (startup.company, startup.website)).fetchone()
        if existing:
            conn.execute('''UPDATE startups SET linkedin=?, twitter=?, funding=?, raw_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=?''',
                         (startup.linkedin, startup.twitter, startup.funding, json.dumps(startup.raw), existing['id']))
            return int(existing['id'])
        cur = conn.execute('''INSERT INTO startups(company, website, linkedin, twitter, funding, raw_json) VALUES(?,?,?,?,?,?)''',
                           (startup.company, startup.website, startup.linkedin, startup.twitter, startup.funding, json.dumps(startup.raw)))
        return int(cur.lastrowid)


def import_startups(startups: Iterable[StartupInput]) -> list[int]:
    ids: list[int] = []
    for startup in startups:
        if not startup.company.strip():
            continue
        startup_id = upsert_startup(startup)
        apply_research(startup_id, deterministic_research(startup))
        ids.append(startup_id)
    return ids


def list_startups(limit: int = 5000, query: str | None = None) -> list[StartupRecord]:
    with connect() as conn:
        if query:
            rows = conn.execute('SELECT * FROM startups WHERE company LIKE ? OR product_summary LIKE ? ORDER BY overall_score DESC, id ASC LIMIT ?', (f'%{query}%', f'%{query}%', limit)).fetchall()
        else:
            rows = conn.execute('SELECT * FROM startups ORDER BY overall_score DESC, id ASC LIMIT ?', (limit,)).fetchall()
        return [row_to_record(r) for r in rows]


def get_startup(startup_id: int) -> StartupRecord | None:
    with connect() as conn:
        row = conn.execute('SELECT * FROM startups WHERE id=?', (startup_id,)).fetchone()
        return row_to_record(row) if row else None


def apply_research(startup_id: int, result: ResearchResult) -> None:
    overall = weighted_overall(result.ai_native_score, result.resume_fit_score, result.hiring_likelihood_score, result.learning_challenge_score, result.logistics_score)
    with connect() as conn:
        conn.execute('''UPDATE startups SET product_summary=?, ai_native_score=?, interestingness_score=?, resume_fit_score=?, hiring_likelihood_score=?, learning_challenge_score=?, logistics_score=?, overall_score=?, hiring_status=?, hiring_evidence=?, remote_india_fit=?, research_confidence=?, evidence_urls_json=?, tags_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=?''',
            (result.product_summary, result.ai_native_score, result.interestingness_score, result.resume_fit_score, result.hiring_likelihood_score, result.learning_challenge_score, result.logistics_score, overall, result.hiring_status.value, result.hiring_evidence, result.remote_india_fit, result.research_confidence, json.dumps(result.evidence_urls), json.dumps(result.tags), startup_id))


def save_message(startup_id: int, style: str, message: str) -> None:
    column = 'message_short' if style == 'short' else 'message_founder'
    with connect() as conn:
        conn.execute(f'UPDATE startups SET {column}=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', (message, startup_id))


def export_csv(path: Path) -> Path:
    records = list_startups()
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ['id','company','website','linkedin','twitter','funding','product_summary','overall_score','ai_native_score','interestingness_score','resume_fit_score','hiring_likelihood_score','learning_challenge_score','logistics_score','hiring_status','hiring_evidence','remote_india_fit','research_confidence','tags','evidence_urls','message_short','message_founder']
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in records:
            d = r.model_dump()
            d['tags'] = '; '.join(r.tags)
            d['evidence_urls'] = '; '.join(r.evidence_urls)
            writer.writerow({field: d.get(field) for field in fields})
    return path


def _refresh_run_counts(conn: sqlite3.Connection, run_id: int) -> None:
    counts = {row['status']: row['count'] for row in conn.execute('SELECT status, COUNT(*) AS count FROM research_jobs WHERE run_id=? GROUP BY status', (run_id,)).fetchall()}
    total = sum(counts.values())
    completed = counts.get('completed', 0)
    failed = counts.get('failed', 0)
    needs_browser = counts.get('needs_browser', 0)
    running = counts.get('running', 0)
    pending = counts.get('pending', 0)
    status = 'running' if running else ('pending' if pending else 'completed')
    if failed and not pending and not running:
        status = 'completed_with_failures'
    conn.execute('''UPDATE research_runs SET status=?, total=?, completed=?, failed=?, needs_browser=?, updated_at=CURRENT_TIMESTAMP WHERE id=?''',
                 (status, total, completed, failed, needs_browser, run_id))


def create_research_run(limit: int = 100, only_unresearched: bool = True, max_confidence: int = 6) -> dict:
    with connect() as conn:
        cur = conn.execute('INSERT INTO research_runs(status) VALUES(?)', ('pending',))
        run_id = int(cur.lastrowid)
        sql = 'SELECT id FROM startups'
        params: list[object] = []
        if only_unresearched:
            sql += ' WHERE research_confidence <= ?'
            params.append(max_confidence)
        sql += ' ORDER BY overall_score DESC, id ASC LIMIT ?'
        params.append(limit)
        startup_ids = [int(row['id']) for row in conn.execute(sql, params).fetchall()]
        for startup_id in startup_ids:
            conn.execute('INSERT OR IGNORE INTO research_jobs(run_id, startup_id) VALUES(?, ?)', (run_id, startup_id))
        _refresh_run_counts(conn, run_id)
        return get_research_run(run_id, conn=conn) or {'id': run_id, 'total': 0}


def get_research_run(run_id: int, conn: sqlite3.Connection | None = None) -> dict | None:
    owns_conn = conn is None
    if owns_conn:
        ctx = connect()
        conn = ctx.__enter__()
    try:
        row = conn.execute('SELECT * FROM research_runs WHERE id=?', (run_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        counts = {r['status']: r['count'] for r in conn.execute('SELECT status, COUNT(*) AS count FROM research_jobs WHERE run_id=? GROUP BY status', (run_id,)).fetchall()}
        data['total'] = sum(counts.values())
        data['completed'] = counts.get('completed', 0)
        data['failed'] = counts.get('failed', 0)
        data['needs_browser'] = counts.get('needs_browser', 0)
        data['pending'] = counts.get('pending', 0)
        data['running'] = counts.get('running', 0)
        if data['status'] != 'cancelled':
            data['status'] = 'running' if data['running'] else ('pending' if data['pending'] else 'completed')
            if data['failed'] and not data['pending'] and not data['running']:
                data['status'] = 'completed_with_failures'
        data['recent_errors'] = [dict(r) for r in conn.execute('''SELECT j.id AS job_id, j.startup_id, s.company, j.status, j.last_error
            FROM research_jobs j JOIN startups s ON s.id=j.startup_id
            WHERE j.run_id=? AND j.last_error IS NOT NULL
            ORDER BY j.updated_at DESC LIMIT 8''', (run_id,)).fetchall()]
        return data
    finally:
        if owns_conn:
            ctx.__exit__(None, None, None)


def latest_research_run() -> dict | None:
    with connect() as conn:
        row = conn.execute('SELECT id FROM research_runs ORDER BY id DESC LIMIT 1').fetchone()
        return get_research_run(int(row['id']), conn=conn) if row else None


def list_research_jobs(run_id: int, status: str = 'pending', limit: int = 100) -> list[dict]:
    with connect() as conn:
        rows = conn.execute('''SELECT j.*, s.company, s.website, s.linkedin, s.twitter, s.funding, s.raw_json
            FROM research_jobs j JOIN startups s ON s.id=j.startup_id
            WHERE j.run_id=? AND j.status=?
            ORDER BY j.id ASC LIMIT ?''', (run_id, status, limit)).fetchall()
        jobs = []
        for row in rows:
            data = dict(row)
            data['raw'] = json.loads(data.pop('raw_json') or '{}')
            jobs.append(data)
        return jobs


def update_research_job(job_id: int, status: str, last_error: str | None = None, needs_browser: bool = False) -> None:
    with connect() as conn:
        row = conn.execute('SELECT run_id, attempts FROM research_jobs WHERE id=?', (job_id,)).fetchone()
        if not row:
            return
        attempts = int(row['attempts']) + (1 if status == 'running' else 0)
        conn.execute('''UPDATE research_jobs SET status=?, attempts=?, last_error=?, needs_browser=?, updated_at=CURRENT_TIMESTAMP WHERE id=?''',
                     (status, attempts, last_error, 1 if needs_browser else 0, job_id))
        _refresh_run_counts(conn, int(row['run_id']))


def record_research_fetch(job_id: int, url: str, final_url: str | None = None, status_code: int | None = None, content_type: str | None = None, text_chars: int = 0, error: str | None = None) -> None:
    with connect() as conn:
        conn.execute('''INSERT INTO research_fetches(job_id, url, final_url, status_code, content_type, text_chars, error) VALUES(?, ?, ?, ?, ?, ?, ?)''',
                     (job_id, url, final_url, status_code, content_type, text_chars, error))


def cancel_research_run(run_id: int) -> dict | None:
    with connect() as conn:
        conn.execute('''UPDATE research_jobs SET status='skipped', updated_at=CURRENT_TIMESTAMP WHERE run_id=? AND status IN ('pending', 'running')''', (run_id,))
        conn.execute('UPDATE research_runs SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', ('cancelled', run_id))
        _refresh_run_counts(conn, run_id)
        conn.execute('UPDATE research_runs SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', ('cancelled', run_id))
        return get_research_run(run_id, conn=conn)
