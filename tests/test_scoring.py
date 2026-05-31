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
