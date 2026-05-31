from startup_search.config import get_settings
from startup_search.models import StartupInput
from startup_search.storage import (
    apply_research,
    create_research_run,
    get_research_run,
    import_startups,
    list_research_jobs,
    record_research_fetch,
    update_research_job,
)
from startup_search.scoring import deterministic_research


def configure_temp_db(monkeypatch, tmp_path):
    monkeypatch.setenv('STARTUP_SEARCH_DATABASE_PATH', str(tmp_path / 'startup_search.db'))
    monkeypatch.setenv('STARTUP_SEARCH_FETCH_CACHE_DIR', str(tmp_path / 'fetch_cache'))
    get_settings.cache_clear()


def test_research_run_queues_unverified_rows(monkeypatch, tmp_path):
    configure_temp_db(monkeypatch, tmp_path)
    ids = import_startups([
        StartupInput(company='Unverified AI', website='https://example.com', raw={'Categories': 'AI agents'}),
        StartupInput(company='Verified AI', website='https://verified.example'),
    ])
    apply_research(ids[1], deterministic_research(
        StartupInput(company='Verified AI', website='https://verified.example'),
        'We build AI agents and are hiring machine learning engineers.',
        ['https://verified.example/careers'],
    ))

    run = create_research_run(limit=10, only_unresearched=True, max_confidence=6)
    jobs = list_research_jobs(run['id'])

    assert run['total'] == 1
    assert jobs[0]['company'] == 'Unverified AI'


def test_research_job_status_counts_and_fetches(monkeypatch, tmp_path):
    configure_temp_db(monkeypatch, tmp_path)
    [startup_id] = import_startups([StartupInput(company='Thin JS Co', website='https://example.com')])
    run = create_research_run(limit=1)
    job = list_research_jobs(run['id'])[0]

    update_research_job(job['id'], 'running')
    record_research_fetch(job['id'], 'https://example.com', final_url='https://example.com', status_code=200, content_type='text/html', text_chars=100)
    update_research_job(job['id'], 'needs_browser', 'Static scrape found very little text; needs browser fallback.', needs_browser=True)
    refreshed = get_research_run(run['id'])

    assert refreshed['running'] == 0
    assert refreshed['needs_browser'] == 1
    assert refreshed['pending'] == 0
    assert refreshed['recent_errors'][0]['company'] == 'Thin JS Co'
