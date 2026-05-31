from __future__ import annotations
import re
from dataclasses import dataclass
from .models import HiringStatus, ResearchResult, StartupInput

AI_TERMS = {
    'ai', 'artificial intelligence', 'machine learning', 'ml', 'llm', 'language model',
    'agent', 'agents', 'rag', 'computer vision', 'generative', 'automation', 'copilot',
    'foundation model', 'inference', 'vector', 'embedding', 'voice ai', 'robotics', 'data science'
}
AI_NATIVE_PRODUCT_TERMS = {
    'ai agent', 'ai agents', 'artificial intelligence', 'machine learning', 'llm',
    'language model', 'generative ai', 'computer vision', 'foundation model',
    'voice ai', 'autonomous', 'rag', 'inference', 'vector search'
}
RESUME_TERMS = {
    'llm', 'agent', 'rag', 'langchain', 'langgraph', 'retrieval', 'computer vision', 'yolo',
    'opencv', 'fastapi', 'flask', 'python', 'pytorch', 'vector', 'embedding', 'observability',
    'workflow', 'automation', 'cybersecurity', 'analytics'
}
HIRING_TERMS = {'hiring', 'careers', 'jobs', 'join us', 'open roles', 'we are looking', 'engineer', 'intern'}
REMOTE_TERMS = {'remote', 'distributed', 'anywhere', 'india', 'hybrid'}
CHALLENGE_TERMS = {'infrastructure', 'platform', 'security', 'developer', 'data', 'real-time', 'research', 'scale', 'autonomous'}


def clamp_score(value: int) -> int:
    return max(0, min(10, value))


def term_score(text: str, terms: set[str], base: int = 0) -> int:
    t = text.lower()
    hits = sum(1 for term in terms if term in t)
    return clamp_score(base + hits * 2)


def ai_score_from_sources(sheet_text: str, fetched_text: str) -> tuple[int, bool, str]:
    """Score AI-native fit while distinguishing sheet signals from website proof.

    The source sheet is useful for triage, but its category/social metadata is not
    enough to call a company AI-native. Sheet-only matches are capped at 5/10 and
    labelled as needing website confirmation. A fetched website/careers page can
    raise the score to 6-10 when the company's own copy contains AI product terms.
    """
    sheet_score = term_score(sheet_text, AI_TERMS)
    website_signal_score = term_score(fetched_text, AI_TERMS)
    website_product_score = term_score(fetched_text, AI_NATIVE_PRODUCT_TERMS)
    website_confirmed = bool(fetched_text.strip()) and website_product_score >= 2
    if not fetched_text.strip():
        return min(sheet_score, 5), False, 'Sheet/category AI signal only; click Research to verify on the website.'
    if website_confirmed:
        score = clamp_score(max(website_signal_score, website_product_score + 2) + min(sheet_score, 2))
        return score, True, 'Website text confirms AI-native/product AI language.'
    if sheet_score:
        return min(sheet_score, 5), False, 'Sheet has AI signal, but fetched website text did not clearly confirm AI-native product language.'
    return 0, False, 'No clear AI-native signal found in sheet or fetched website text.'


def weighted_overall(ai: int, resume: int, hiring: int, challenge: int, logistics: int) -> float:
    return round(ai * 3.5 + resume * 2.5 + hiring * 2.0 + challenge * 1.0 + logistics * 1.0, 1)


def infer_hiring_status(text: str, has_jobs_page: bool = False, has_fetched_text: bool = False) -> tuple[HiringStatus, str, int]:
    lower = text.lower()
    if not has_fetched_text:
        return HiringStatus.maybe, 'Not verified yet; click Research to fetch website/careers hiring evidence.', 3
    relevant_role = re.search(r'(ai|ml|machine learning|software|backend|full.stack|data|founding|product).*engineer|intern', lower)
    if has_jobs_page and (relevant_role or any(term in lower for term in ['engineer', 'intern', 'machine learning', 'software'])):
        return HiringStatus.yes, 'Relevant engineering/AI/software hiring language found.', 8
    if relevant_role:
        return HiringStatus.maybe, 'Relevant role language found, but no dedicated careers/jobs page was confirmed.', 5
    if any(term in lower for term in ['hiring', 'join us', 'always looking', 'send us your resume']):
        return HiringStatus.maybe, 'General hiring or always-looking signal found.', 5
    return HiringStatus.no, 'No current relevant hiring evidence found in fetched text.', 1


def deterministic_research(startup: StartupInput, fetched_text: str = '', evidence_urls: list[str] | None = None) -> ResearchResult:
    evidence_urls = evidence_urls or []
    raw_text = ' '.join(str(value) for value in startup.raw.values() if value is not None)
    sheet_text = ' '.join(filter(None, [startup.company, startup.funding, startup.website, raw_text]))
    combined = ' '.join(filter(None, [sheet_text, fetched_text]))
    ai, website_confirmed_ai, ai_evidence = ai_score_from_sources(sheet_text, fetched_text)
    resume = term_score(combined, RESUME_TERMS)
    challenge = term_score(combined, CHALLENGE_TERMS, base=2 if ai >= 4 else 0)
    logistics = term_score(combined, REMOTE_TERMS, base=4 if startup.website else 2)
    status, hiring_evidence, hiring = infer_hiring_status(combined, any('career' in u or 'jobs' in u for u in evidence_urls), bool(fetched_text.strip()))
    interesting = clamp_score(round((ai * 0.65) + (challenge * 0.35)))
    confidence = clamp_score(2 + (3 if fetched_text else 0) + (2 if startup.website else 0) + (1 if evidence_urls else 0))
    summary = summarize_heuristic(startup.company, fetched_text, ai, ai_evidence)
    fetched = bool(fetched_text.strip())
    tags = sorted({tag for tag in ['Website-confirmed AI-native' if website_confirmed_ai and ai >= 6 else '', 'AI signal unconfirmed' if ai and not website_confirmed_ai else '', 'Strong resume fit' if resume >= 6 else '', 'Hiring signal' if fetched and status != HiringStatus.no else '', 'Hiring unverified' if not fetched else '', 'Remote/India signal' if logistics >= 6 else ''] if tag})
    return ResearchResult(
        product_summary=summary,
        ai_native_score=ai,
        interestingness_score=interesting,
        resume_fit_score=resume,
        hiring_likelihood_score=hiring,
        learning_challenge_score=challenge,
        logistics_score=logistics,
        hiring_status=status,
        hiring_evidence=hiring_evidence,
        remote_india_fit='Remote/India-friendly signals found.' if logistics >= 6 else 'No clear remote/India signal found yet.',
        research_confidence=confidence,
        evidence_urls=evidence_urls,
        tags=tags,
    )


def summarize_heuristic(company: str, text: str, ai_score: int, ai_evidence: str = '') -> str:
    clean = re.sub(r'\s+', ' ', text).strip()
    if clean:
        first = clean[:260].strip()
        suffix = '...' if len(clean) > 260 else ''
        return f'{company}: {first}{suffix} AI check: {ai_evidence}'
    if ai_score:
        return f'{company} appears to have AI-related sheet/category signals, but needs website research for confirmation.'
    return f'{company} needs research to determine whether the core product is AI-native.'
