from __future__ import annotations
import re
from openai import AsyncOpenAI
from .config import get_settings
from .models import StartupRecord

PROFILE = '''Ritam Ghosh is a 3rd-year B.Tech AI student at SRM University with production experience building multi-agent LLM systems using LangGraph, RAG systems, computer vision deployments with YOLO/OpenCV, FastAPI/Flask backends, Docker, LangSmith observability, and vector search.'''

NAV_PHRASES = (
    'how it works', 'product', 'products', 'pricing', 'blog', 'docs', 'documentation',
    'careers', 'customers', 'contact', 'login', 'sign in', 'sign up', 'book a demo',
)


def clean_company_note(startup: StartupRecord, max_chars: int = 140) -> str:
    """Turn scraped page/title text into one usable company-specific detail."""
    text = startup.product_summary or ''
    if not text:
        return ''

    text = re.sub(r'\s+', ' ', text).strip(' .|:-')
    company = re.escape(startup.company)
    text = re.sub(rf'^(?:{company}\s*[:|\-]\s*)+', '', text, flags=re.IGNORECASE)
    text = re.sub(rf'\b{company}\b\s*[:|\-]?\s*', '', text, count=2, flags=re.IGNORECASE)

    chunks = re.split(r'[.!?]\s+|\s+[|•]\s+', text)
    cleaned: list[str] = []
    for chunk in chunks:
        chunk = chunk.strip(' .|:-')
        if not chunk:
            continue
        lowered = chunk.lower()
        if lowered in NAV_PHRASES:
            continue
        if any(lowered == phrase or lowered.startswith(f'{phrase} ') for phrase in NAV_PHRASES):
            continue
        cleaned.append(chunk)

    detail = cleaned[0] if cleaned else text
    detail = re.sub(r'\b(?:' + '|'.join(re.escape(p) for p in NAV_PHRASES) + r')\b.*$', '', detail, flags=re.IGNORECASE).strip(' .|:-')
    if len(detail) > max_chars:
        detail = detail[:max_chars].rsplit(' ', 1)[0].strip(' ,.;:')
    return detail


def company_angle(startup: StartupRecord) -> str:
    detail = clean_company_note(startup)
    if detail:
        return detail[0].lower() + detail[1:]
    if startup.tags:
        return ', '.join(startup.tags[:2]).lower()
    return 'the product you are building'


def researched_context(startup: StartupRecord) -> str:
    lines = [
        f'Company: {startup.company}',
        f'Website: {startup.website or "Unknown"}',
        f'Best product/problem detail: {clean_company_note(startup, 260) or "No researched product detail available"}',
        f'Raw researched summary: {startup.product_summary or "None"}',
        f'Tags/signals: {", ".join(startup.tags) if startup.tags else "None"}',
        f'Hiring status: {startup.hiring_status}',
        f'Hiring evidence: {startup.hiring_evidence or "None"}',
        f'Remote/India fit: {startup.remote_india_fit or "Unknown"}',
        f'Evidence URLs: {", ".join(startup.evidence_urls[:4]) if startup.evidence_urls else "None"}',
        f'Scores: AI-native {startup.ai_native_score}/10, resume-fit {startup.resume_fit_score}/10, interestingness {startup.interestingness_score}/10, learning challenge {startup.learning_challenge_score}/10',
    ]
    return '\n'.join(lines)


def fallback_message(startup: StartupRecord, style: str) -> str:
    product = company_angle(startup)
    angle = 'LLM agents/RAG/CV systems' if startup.resume_fit_score >= 5 else 'AI engineering and product-building'
    if style == 'short':
        return (
            f"Hi, I’m Ritam, a 3rd-year AI student. {startup.company} stood out because it’s working on {product}. "
            "I’ve built LangGraph/RAG and CV systems, and I’d love to connect if an AI intern could help."
        )
    return (
        f"Hi, I’m Ritam, a 3rd-year B.Tech AI student at SRM. I was looking into {startup.company} and the part that caught me was {product}.\n\n"
        f"That maps closely to problems I’ve worked on with {angle}: multi-agent GenAI workflows, RAG pipelines, CV deployments, backend APIs, and observability.\n\n"
        "If there’s room for an AI/ML intern who can prototype fast and turn messy AI ideas into working systems, I’d love to help. "
        "Would you be open to a quick chat?"
    )


async def generate_message(startup: StartupRecord, style: str) -> str:
    settings = get_settings()
    if not settings.openai_api_key:
        return fallback_message(startup, style)
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    length = 'under 280 characters for a LinkedIn connection request' if style == 'short' else '5-7 concise lines for a founder LinkedIn DM'
    style_rules = (
        'Write exactly 2 sentences. No line breaks. Make it fit a connection request.'
        if style == 'short'
        else 'Write 3 short paragraphs with line breaks. Paragraph 1 proves company research, paragraph 2 maps Ritam to their likely needs, paragraph 3 asks for a quick chat.'
    )
    prompt = f'''
Write a highly specific cold LinkedIn message, {length}.
Do not invent facts. Use only the company notes and student profile below.
Tone: human, ambitious, direct, student-founder friendly, not salesy.
Ask for an AI/ML internship or a quick chat.
{style_rules}

Quality rules:
- Do not say "caught my eye because of" followed by a raw page title or copied snippet.
- Do not repeat the company name/title/nav text.
- Lead with the specific product/problem the company appears to work on.
- Connect that detail to Ritam's LangGraph/RAG/CV/backend experience in one concrete way.
- Sound like a thoughtful individual DM, not a template.
- If the research is thin, be honest and phrase it as "I was looking at..." rather than pretending deep knowledge.
- Avoid generic phrases like "possible AI internship work", "I found the product interesting", and "I would love to connect" unless tied to a concrete contribution.

Student profile: {PROFILE}
Researched company context:
{researched_context(startup)}
'''.strip()
    response = await client.chat.completions.create(
        model=settings.openai_message_model,
        messages=[{'role': 'system', 'content': 'You write concise, honest founder outreach for internships.'}, {'role': 'user', 'content': prompt}],
        temperature=0.5,
    )
    return response.choices[0].message.content.strip()
