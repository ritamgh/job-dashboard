from startup_search.llm import clean_company_note, clean_generated_message, closing_ask, fallback_message, help_offer, is_stale_message, researched_context
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

    assert message.startswith('Hi, I’m Ritam. I build agentic workflows')
    assert 'fully-managed AI agents and workflows' in message
    assert 'How it works' not in message
    assert 'Product Pricing' not in message
    assert 'possible AI internship work' not in message
    assert 'SRM' not in message
    assert 'found the product interesting' not in message.lower()
    assert 'strongest fit' not in message.lower()
    assert '4th-year AI student' in message
    assert 'one concrete idea' in message
    assert 'internship/' 'project work' not in message
    assert '\u2014' not in message


def test_strong_fit_offer_asks_to_send_a_concrete_idea():
    startup = make_startup()

    assert 'agent/RAG workflow' in help_offer(startup)
    assert closing_ask(startup) == 'Could I send one concrete idea, or is there something specific you’d like me to build to prove I can help?'


def test_weak_fit_does_not_fake_relevance_and_asks_to_prototype():
    startup = make_startup(
        company='OpsCo',
        product_summary='OpsCo helps finance teams manage vendor approvals and spend controls.',
        ai_native_score=2,
        resume_fit_score=3,
        tags=['SaaS', 'Finance'],
    )
    message = fallback_message(startup, 'founder')

    assert 'agent/RAG workflow' not in help_offer(startup)
    assert 'small AI/backend workflow' in closing_ask(startup)
    assert 'could I take a shot at building it to prove I can help' in message
    assert 'I build agentic workflows, multi-agent systems, and RAG/CV products' in message


def test_researched_context_includes_crawler_evidence_for_prompt():
    context = researched_context(make_startup())

    assert 'Fit classification: strong' in context
    assert 'Best product/problem detail: Build and deploy fully-managed AI agents and workflows' in context
    assert 'Tags/signals: Website-confirmed AI-native, AI agents, Developer tooling' in context
    assert 'Evidence URLs: https://trigger.dev, https://trigger.dev/careers' in context
    assert 'Suggested value-first offer: build a small agent/RAG workflow' in context
    assert 'Suggested closing ask: Could I send one concrete idea' in context


def test_old_template_messages_are_marked_stale():
    old = 'Hi, I’m Ritam, a 4th-year B.Tech AI student at SRM. I found the product interesting. My strongest fit is LLM agents/RAG/CV systems.'
    fresh = fallback_message(make_startup(), 'founder')

    assert is_stale_message(old)
    assert is_stale_message('Hi [Name] \u2014 I’m Ritam, a builder.')
    assert is_stale_message('I’m looking for internship/' 'project work.')
    assert not is_stale_message(fresh)


def test_generated_message_cleanup_removes_name_placeholder():
    cleaned = clean_generated_message('Hi [Name] \u2014 I’m Ritam, and I build agentic workflows.')

    assert cleaned == 'Hi, I’m Ritam, and I build agentic workflows.'
    assert '[Name]' not in cleaned
    assert '\u2014' not in cleaned


def test_fallback_email_has_subject_and_build_to_prove_value_ask():
    message = fallback_message(make_startup(), 'email')

    assert message.startswith('Subject:')
    assert 'looking for an internship' in message
    assert 'internship/' 'project work' not in message
    assert 'something specific you’d like me to build to prove I can help' in message
    assert '\u2014' not in message
