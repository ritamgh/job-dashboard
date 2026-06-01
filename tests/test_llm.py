from startup_search.llm import clean_company_note, fallback_message, researched_context
from startup_search.models import HiringStatus, StartupRecord


def make_startup(**overrides):
    data = {
        'id': 1,
        'company': 'Trigger.dev',
        'website': 'https://trigger.dev',
        'product_summary': 'Trigger.dev: Trigger.dev | Build and deploy fully-managed AI agents and workflows. How it works Product Pricing Docs',
        'ai_native_score': 8,
        'interestingness_score': 8,
        'resume_fit_score': 8,
        'hiring_likelihood_score': 6,
        'learning_challenge_score': 8,
        'logistics_score': 7,
        'overall_score': 77.0,
        'hiring_status': HiringStatus.maybe,
        'hiring_evidence': 'Careers page mentions engineering roles and remote-friendly team.',
        'remote_india_fit': 'Remote-friendly signals found.',
        'research_confidence': 7,
        'evidence_urls': ['https://trigger.dev', 'https://trigger.dev/careers'],
        'tags': ['Website-confirmed AI-native', 'AI agents', 'Developer tooling'],
    }
    data.update(overrides)
    return StartupRecord(**data)


def test_clean_company_note_removes_raw_title_and_nav_text():
    note = clean_company_note(make_startup())

    assert note == 'Build and deploy fully-managed AI agents and workflows'
    assert 'How it works' not in note
    assert 'Product Pricing' not in note
    assert not note.startswith('Trigger.dev')


def test_fallback_message_uses_specific_researched_detail():
    message = fallback_message(make_startup(), 'founder')

    assert 'fully-managed AI agents and workflows' in message
    assert 'How it works' not in message
    assert 'Product Pricing' not in message
    assert 'possible AI internship work' not in message


def test_researched_context_includes_crawler_evidence_for_prompt():
    context = researched_context(make_startup())

    assert 'Best product/problem detail: Build and deploy fully-managed AI agents and workflows' in context
    assert 'Tags/signals: Website-confirmed AI-native, AI agents, Developer tooling' in context
    assert 'Evidence URLs: https://trigger.dev, https://trigger.dev/careers' in context
