import pytest
from fastapi.testclient import TestClient

from startup_search.app import app
from startup_search.company_size import company_size_queries, parse_company_size_results
from startup_search.config import get_settings
from startup_search.models import StartupInput
from startup_search.storage import get_outreach_session, import_startups, list_outreach_drafts


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv('STARTUP_SEARCH_DATABASE_PATH', str(tmp_path / 'test.db'))
    monkeypatch.setenv('STARTUP_SEARCH_FETCH_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.delenv('STARTUP_SEARCH_GMAIL_MCP_COMMAND', raising=False)
    monkeypatch.delenv('STARTUP_SEARCH_SERPER_API_KEY', raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_parse_company_size_results_prefers_linkedin_employee_range():
    payload = {
        'organic': [
            {
                'title': 'Example AI | LinkedIn',
                'link': 'https://www.linkedin.com/company/example-ai',
                'snippet': 'Company size 11-50 employees. Software Development.',
            },
            {
                'title': 'Example AI jobs',
                'link': 'https://example.ai/jobs',
                'snippet': 'We are a small team with 12 employees and growing.',
            },
        ]
    }

    estimate = parse_company_size_results(payload)

    assert estimate.estimate == '11-50 employees'
    assert estimate.confidence >= 80
    assert estimate.source_url == 'https://www.linkedin.com/company/example-ai'


def test_company_size_queries_include_linkedin_and_team_size():
    queries = company_size_queries('Example AI', 'https://example.ai', 'https://linkedin.com/company/example-ai')

    assert queries[0] == 'https://linkedin.com/company/example-ai employees'
    assert any('team size employees' in query for query in queries)


def test_dashboard_outreach_session_creates_reviewable_email_draft():
    startup_id = import_startups([StartupInput(company='Example AI', website='https://example.ai')])[0]
    client = TestClient(app)

    response = client.post(f'/api/startups/{startup_id}/outreach-session')

    assert response.status_code == 200
    payload = response.json()
    session = get_outreach_session(payload['id'])
    drafts = list_outreach_drafts(payload['id'])
    assert session['company'] == 'Example AI'
    assert drafts[0]['channel'] == 'email'
    assert drafts[0]['subject']
    assert drafts[0]['body']
