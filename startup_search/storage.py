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
  founder_linkedin TEXT,
  twitter TEXT,
  founder_twitter TEXT,
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
  company_size_estimate TEXT,
  company_size_confidence INTEGER NOT NULL DEFAULT 0,
  company_size_source_url TEXT,
  company_size_source_snippet TEXT,
  message_short TEXT,
  message_founder TEXT,
  message_email TEXT,
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

CREATE TABLE IF NOT EXISTS outreach_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company TEXT,
  website TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',
  research_json TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_outreach_sessions_updated ON outreach_sessions(updated_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS outreach_contacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL,
  name TEXT,
  role TEXT,
  email TEXT,
  linkedin_url TEXT,
  confidence INTEGER NOT NULL DEFAULT 0,
  source_url TEXT,
  source_snippet TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_outreach_contacts_unique ON outreach_contacts(session_id, COALESCE(email, ''), COALESCE(linkedin_url, ''));
CREATE INDEX IF NOT EXISTS idx_outreach_contacts_session ON outreach_contacts(session_id, confidence DESC);

CREATE TABLE IF NOT EXISTS outreach_drafts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL,
  contact_id INTEGER,
  channel TEXT NOT NULL,
  subject TEXT,
  body TEXT NOT NULL,
  edited_subject TEXT,
  edited_body TEXT,
  send_status TEXT NOT NULL DEFAULT 'draft',
  sent_at TEXT,
  gmail_message_id TEXT,
  gmail_thread_id TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_outreach_drafts_session ON outreach_drafts(session_id, id);
'''


def infer_founder_linkedin(raw: dict, company_linkedin: str | None = None) -> str | None:
    keys = ['Founder LinkedIn', 'Founder Linkedin', 'Founders LinkedIn', 'Founders Linkedin', 'Linkedin', 'LinkedIn', 'LinkedIn URL', 'Linkedin URL']
    for key in keys:
        val = raw.get(key)
        if val is not None and str(val).strip():
            link = str(val).strip()
            if company_linkedin and link == company_linkedin:
                continue
            return link
    return None


def infer_founder_twitter(raw: dict, company_twitter: str | None = None) -> str | None:
    keys = ['Founder X', 'Founder Twitter', 'Founders X', 'Founders Twitter', 'Twitter', 'X', 'X/Twitter']
    for key in keys:
        val = raw.get(key)
        if val is not None and str(val).strip():
            link = str(val).strip()
            if company_twitter and link == company_twitter:
                continue
            return link
    return None


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    columns = {row['name'] for row in conn.execute('PRAGMA table_info(startups)').fetchall()}
    if 'founder_linkedin' not in columns:
        conn.execute('ALTER TABLE startups ADD COLUMN founder_linkedin TEXT')
    if 'founder_twitter' not in columns:
        conn.execute('ALTER TABLE startups ADD COLUMN founder_twitter TEXT')
    if 'message_email' not in columns:
        conn.execute('ALTER TABLE startups ADD COLUMN message_email TEXT')
    if 'company_size_estimate' not in columns:
        conn.execute('ALTER TABLE startups ADD COLUMN company_size_estimate TEXT')
    if 'company_size_confidence' not in columns:
        conn.execute('ALTER TABLE startups ADD COLUMN company_size_confidence INTEGER NOT NULL DEFAULT 0')
    if 'company_size_source_url' not in columns:
        conn.execute('ALTER TABLE startups ADD COLUMN company_size_source_url TEXT')
    if 'company_size_source_snippet' not in columns:
        conn.execute('ALTER TABLE startups ADD COLUMN company_size_source_snippet TEXT')

@contextmanager
def connect():
    settings = get_settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=5000')
    try:
        ensure_schema(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_record(row: sqlite3.Row) -> StartupRecord:
    data = dict(row)
    data['raw'] = json.loads(data.pop('raw_json') or '{}')
    data['founder_linkedin'] = data.get('founder_linkedin') or infer_founder_linkedin(data['raw'], data.get('linkedin'))
    data['founder_twitter'] = data.get('founder_twitter') or infer_founder_twitter(data['raw'], data.get('twitter'))
    data['evidence_urls'] = json.loads(data.pop('evidence_urls_json') or '[]')
    data['tags'] = json.loads(data.pop('tags_json') or '[]')
    data.pop('created_at', None)
    data.pop('updated_at', None)
    return StartupRecord(**data)


def upsert_startup(startup: StartupInput) -> int:
    with connect() as conn:
        existing = conn.execute('SELECT id FROM startups WHERE company=? AND COALESCE(website, "")=COALESCE(?, "")', (startup.company, startup.website)).fetchone()
        if existing:
            conn.execute('''UPDATE startups SET linkedin=?, founder_linkedin=?, twitter=?, founder_twitter=?, funding=?, raw_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=?''',
                         (startup.linkedin, startup.founder_linkedin or infer_founder_linkedin(startup.raw, startup.linkedin), startup.twitter, startup.founder_twitter or infer_founder_twitter(startup.raw, startup.twitter), startup.funding, json.dumps(startup.raw), existing['id']))
            return int(existing['id'])
        cur = conn.execute('''INSERT INTO startups(company, website, linkedin, founder_linkedin, twitter, founder_twitter, funding, raw_json) VALUES(?,?,?,?,?,?,?,?)''',
                           (startup.company, startup.website, startup.linkedin, startup.founder_linkedin or infer_founder_linkedin(startup.raw, startup.linkedin), startup.twitter, startup.founder_twitter or infer_founder_twitter(startup.raw, startup.twitter), startup.funding, json.dumps(startup.raw)))
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
    column = {'short': 'message_short', 'founder': 'message_founder', 'email': 'message_email'}[style]
    with connect() as conn:
        conn.execute(f'UPDATE startups SET {column}=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', (message, startup_id))


def save_company_size(startup_id: int, estimate: dict) -> None:
    with connect() as conn:
        conn.execute('''UPDATE startups SET company_size_estimate=?, company_size_confidence=?, company_size_source_url=?, company_size_source_snippet=?, updated_at=CURRENT_TIMESTAMP WHERE id=?''',
            (estimate.get('company_size_estimate'), int(estimate.get('company_size_confidence') or 0), estimate.get('company_size_source_url'), estimate.get('company_size_source_snippet'), startup_id))


def export_csv(path: Path) -> Path:
    records = list_startups()
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ['id','company','website','linkedin','founder_linkedin','twitter','founder_twitter','funding','product_summary','overall_score','ai_native_score','interestingness_score','resume_fit_score','hiring_likelihood_score','learning_challenge_score','logistics_score','hiring_status','hiring_evidence','remote_india_fit','research_confidence','company_size_estimate','company_size_confidence','company_size_source_url','company_size_source_snippet','tags','evidence_urls','message_short','message_founder','message_email']
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
        rows = conn.execute('''SELECT j.*, s.company, s.website, s.linkedin, s.twitter, s.founder_twitter, s.funding, s.raw_json
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


def _json_or_none(value: str | None) -> dict | None:
    return json.loads(value) if value else None


def _session_from_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data['research'] = _json_or_none(data.pop('research_json'))
    return data


def create_outreach_session(website: str, company: str | None = None) -> dict:
    with connect() as conn:
        cur = conn.execute('INSERT INTO outreach_sessions(company, website) VALUES(?, ?)', (company, website))
        row = conn.execute('SELECT * FROM outreach_sessions WHERE id=?', (int(cur.lastrowid),)).fetchone()
        return _session_from_row(row)


def get_outreach_session(session_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute('SELECT * FROM outreach_sessions WHERE id=?', (session_id,)).fetchone()
        return _session_from_row(row) if row else None


def list_outreach_sessions(limit: int = 50) -> list[dict]:
    with connect() as conn:
        rows = conn.execute('SELECT * FROM outreach_sessions ORDER BY updated_at DESC, id DESC LIMIT ?', (limit,)).fetchall()
        return [_session_from_row(row) for row in rows]


def save_outreach_research(session_id: int, result: ResearchResult) -> dict:
    payload = result.model_dump(mode='json')
    with connect() as conn:
        conn.execute("UPDATE outreach_sessions SET status='researched', research_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (json.dumps(payload), session_id))
        row = conn.execute('SELECT * FROM outreach_sessions WHERE id=?', (session_id,)).fetchone()
        return _session_from_row(row)


def add_outreach_contact(session_id: int, contact: dict) -> dict:
    with connect() as conn:
        conn.execute('''INSERT OR IGNORE INTO outreach_contacts(session_id, name, role, email, linkedin_url, confidence, source_url, source_snippet) VALUES(?, ?, ?, ?, ?, ?, ?, ?)''',
                     (session_id, contact.get('name'), contact.get('role'), contact.get('email'), contact.get('linkedin_url'), int(contact.get('confidence') or 0), contact.get('source_url'), contact.get('source_snippet')))
        row = conn.execute('''SELECT * FROM outreach_contacts WHERE session_id=? AND COALESCE(email, '')=COALESCE(?, '') AND COALESCE(linkedin_url, '')=COALESCE(?, '') ORDER BY confidence DESC LIMIT 1''',
                           (session_id, contact.get('email'), contact.get('linkedin_url'))).fetchone()
        return dict(row) if row else {}


def list_outreach_contacts(session_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute('SELECT * FROM outreach_contacts WHERE session_id=? ORDER BY confidence DESC, id ASC', (session_id,)).fetchall()
        return [dict(row) for row in rows]


def create_outreach_draft(session_id: int, draft: dict) -> dict:
    with connect() as conn:
        cur = conn.execute('''INSERT INTO outreach_drafts(session_id, contact_id, channel, subject, body) VALUES(?, ?, ?, ?, ?)''',
                           (session_id, draft.get('contact_id'), draft['channel'], draft.get('subject'), draft['body']))
        conn.execute('UPDATE outreach_sessions SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', ('generated', session_id))
        row = conn.execute('SELECT * FROM outreach_drafts WHERE id=?', (int(cur.lastrowid),)).fetchone()
        return dict(row)


def get_outreach_draft(draft_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute('SELECT * FROM outreach_drafts WHERE id=?', (draft_id,)).fetchone()
        return dict(row) if row else None


def list_outreach_drafts(session_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute('SELECT * FROM outreach_drafts WHERE session_id=? ORDER BY id ASC', (session_id,)).fetchall()
        return [dict(row) for row in rows]


def update_outreach_draft(draft_id: int, edited_subject: str | None = None, edited_body: str | None = None, contact_id: int | None = None) -> dict | None:
    with connect() as conn:
        current = conn.execute('SELECT * FROM outreach_drafts WHERE id=?', (draft_id,)).fetchone()
        if not current:
            return None
        conn.execute('''UPDATE outreach_drafts SET edited_subject=?, edited_body=?, contact_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?''',
                     (edited_subject, edited_body, contact_id, draft_id))
        row = conn.execute('SELECT * FROM outreach_drafts WHERE id=?', (draft_id,)).fetchone()
        return dict(row)


def set_outreach_draft_send_result(draft_id: int, status: str, gmail_message_id: str | None = None, gmail_thread_id: str | None = None, last_error: str | None = None) -> None:
    with connect() as conn:
        conn.execute('''UPDATE outreach_drafts SET send_status=?, sent_at=CASE WHEN ?='sent' THEN CURRENT_TIMESTAMP ELSE sent_at END, gmail_message_id=?, gmail_thread_id=?, last_error=?, updated_at=CURRENT_TIMESTAMP WHERE id=?''',
                     (status, status, gmail_message_id, gmail_thread_id, last_error, draft_id))
        row = conn.execute('SELECT session_id FROM outreach_drafts WHERE id=?', (draft_id,)).fetchone()
        if row and status == 'sent':
            conn.execute('UPDATE outreach_sessions SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', ('sent', int(row['session_id'])))
