from startup_search.models import StartupInput, HiringStatus
from startup_search.scoring import deterministic_research, weighted_overall


def test_weighted_overall_matches_plan():
    assert weighted_overall(10, 8, 6, 7, 5) == 79.0


def test_deterministic_research_detects_ai_and_hiring():
    startup = StartupInput(company='AgentOps AI', website='https://example.com')
    text = 'We build AI agents, RAG workflows, vector search, LangGraph automation. Careers: hiring machine learning engineer intern, remote anywhere.'
    result = deterministic_research(startup, text, ['https://example.com/careers'])
    assert result.ai_native_score >= 6
    assert result.resume_fit_score >= 6
    assert result.hiring_status == HiringStatus.yes
    assert result.logistics_score >= 6


def test_sheet_only_ai_signal_is_capped_until_website_confirmation():
    startup = StartupInput(
        company='Maybe AI Co',
        website='https://example.com',
        raw={'Categories': 'Artificial Intelligence, Machine Learning, LLM, Generative AI, AI agents'},
    )
    result = deterministic_research(startup)
    assert result.ai_native_score <= 5
    assert 'AI signal unconfirmed' in result.tags


def test_website_ai_language_confirms_ai_native_score():
    startup = StartupInput(company='Confirmed AI Co', website='https://example.com')
    text = 'We build AI agents powered by LLM workflows, RAG, inference, and vector search for engineering teams.'
    result = deterministic_research(startup, text, ['https://example.com'])
    assert result.ai_native_score >= 6
    assert 'Website-confirmed AI-native' in result.tags
