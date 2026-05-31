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
'''

@contextmanager
def connect():
    settings = get_settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
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
