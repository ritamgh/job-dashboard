import pytest
from fastapi.testclient import TestClient

from startup_search.app import app
from startup_search.config import get_settings
from startup_search.contact_search import contact_queries, parse_serper_results
from startup_search.outreach import split_subject_body
from startup_search.storage import create_outreach_draft, create_outreach_session, get_outreach_draft, update_outreach_draft


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv('STARTUP_SEARCH_DATABASE_PATH', str(tmp_path / 'test.db'))
    monkeypatch.setenv('STARTUP_SEARCH_FETCH_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.delenv('STARTUP_SEARCH_GMAIL_MCP_COMMAND', raising=False)
    monkeypatch.delenv('STARTUP_SEARCH_SERPER_API_KEY', raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_outreach_session_and_draft_edit_roundtrip():
    session = create_outreach_session('https://example.com', 'Example')
    draft = create_outreach_draft(session['id'], {'channel': 'email', 'subject': 'Hi', 'body': 'Body'})

    edited = update_outreach_draft(draft['id'], edited_subject='Edited', edited_body='Edited body')

    assert session['website'] == 'https://example.com'
    assert edited['edited_subject'] == 'Edited'
    assert edited['edited_body'] == 'Edited body'


def test_send_requires_explicit_confirmation():
    client = TestClient(app)
    session = create_outreach_session('https://example.com', 'Example')
    draft = create_outreach_draft(session['id'], {'channel': 'email', 'subject': 'Hi', 'body': 'Body'})

    response = client.post(f"/api/outreach/drafts/{draft['id']}/send", json={'to': 'founder@example.com'})

    assert response.status_code == 400
    assert 'confirm_send' in response.json()['detail']
    assert get_outreach_draft(draft['id'])['send_status'] == 'draft'


def test_send_without_gmail_command_is_dry_run_failure_after_confirmation():
    client = TestClient(app)
    session = create_outreach_session('https://example.com', 'Example')
    draft = create_outreach_draft(session['id'], {'channel': 'email', 'subject': 'Hi', 'body': 'Body'})

    response = client.post(
        f"/api/outreach/drafts/{draft['id']}/send",
        json={'to': 'founder@example.com', 'confirm_send': True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['sent'] is False
    assert payload['dry_run'] is True
    assert payload['draft']['send_status'] == 'failed'


def test_parse_serper_results_extracts_email_with_source_confidence():
    payload = {
        'organic': [
            {
                'title': 'Contact Example',
                'link': 'https://example.com/contact',
                'snippet': 'Reach the founder at founder@example.com for hiring questions.',
            }
        ]
    }

    contacts = parse_serper_results(payload, 'https://example.com')

    assert contacts[0].email == 'founder@example.com'
    assert contacts[0].source_url == 'https://example.com/contact'
    assert contacts[0].confidence >= 90


def test_contact_queries_use_company_domain():
    queries = contact_queries('Example AI', 'https://www.example.ai')

    assert queries[0].startswith('site:example.ai')
    assert any('Example AI founder email' == query for query in queries)


def test_split_subject_body_parses_subject_line():
    subject, body = split_subject_body('Subject: Build for Example\n\nHi there', 'Example')

    assert subject == 'Build for Example'
    assert body == 'Hi there'
