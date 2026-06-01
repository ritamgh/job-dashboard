from __future__ import annotations
import re
from openai import AsyncOpenAI
from .config import get_settings
from .models import StartupRecord

PROFILE = '''Ritam Ghosh builds agentic workflows, multi-agent systems, and RAG/CV products. He is currently a 4th-year AI student looking for an internship where he can prove himself by building something useful first. His experience includes LangGraph, RAG systems, YOLO/OpenCV computer vision deployments, FastAPI/Flask backends, Docker, LangSmith observability, and vector search.'''

NAV_PHRASES = (
    'how it works', 'product', 'products', 'pricing', 'blog', 'docs', 'documentation',
    'careers', 'customers', 'contact', 'login', 'sign in', 'sign up', 'book a demo',
)

STALE_MESSAGE_PHRASES = (
    '[name]',
    '[founder]',
    'b.tech ai student at srm',
    'found the product interesting',
    'my strongest fit',
    'caught my eye',
    'possible ai internship work',
    'internship/' 'project work',
    'short project-fit note',
)


def is_stale_message(message: str | None) -> bool:
    if not message:
        return False
    lowered = message.lower()
    return any(phrase in lowered for phrase in STALE_MESSAGE_PHRASES)


def clean_generated_message(message: str) -> str:
    message = message.strip()
    message = re.sub(r'^hi\s+\[[^\]]+\]\s*[\u2014\u2013-]\s*', 'Hi, ', message, flags=re.IGNORECASE)
    message = re.sub(r'^hi\s+\[[^\]]+\][,!]?\s*', 'Hi, ', message, flags=re.IGNORECASE)
    message = re.sub(r'\s*[\u2014\u2013]\s*', ', ', message)
    message = re.sub(r'\s+--\s+', ', ', message)
    message = re.sub(r' *, *', ', ', message)
    message = re.sub(r' {2,}', ' ', message)
    message = re.sub(r' +\n', '\n', message)
    return message.strip()


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


def observation_angle(startup: StartupRecord) -> str:
    detail = company_angle(startup)
    if detail.startswith(('build ', 'deploy ', 'create ', 'turn ', 'make ', 'help ')):
        return f'the push to {detail}'
    return detail


def has_clear_ai_fit(startup: StartupRecord) -> bool:
    return startup.ai_native_score >= 6 and startup.resume_fit_score >= 6


def help_offer(startup: StartupRecord) -> str:
    tags = ' '.join(startup.tags).lower()
    summary = (startup.product_summary or '').lower()
    context = f'{tags} {summary}'
    if 'developer' in context or 'workflow' in context or 'agent' in context:
        return 'build a small agent/RAG workflow, integration, or example that shows how developers could use the product'
    if 'rag' in context or 'search' in context or 'knowledge' in context:
        return 'prototype a small RAG workflow, eval harness, or retrieval demo around one real use case'
    if 'vision' in context or 'video' in context or 'image' in context or 'computer vision' in context:
        return 'prototype a lightweight CV pipeline or demo around one real product use case'
    if has_clear_ai_fit(startup):
        return 'turn one AI use case into a working workflow/demo instead of just talking about fit'
    return 'take a shot at a lightweight AI/backend workflow or prototype to prove I can help'


def closing_ask(startup: StartupRecord) -> str:
    if has_clear_ai_fit(startup):
        return 'Could I send one concrete idea, or is there something specific you’d like me to build to prove I can help?'
    return 'If there’s a small AI/backend workflow you’ve wanted to test, could I take a shot at building it to prove I can help?'


def researched_context(startup: StartupRecord) -> str:
    lines = [
        f'Company: {startup.company}',
        f'Website: {startup.website or "Unknown"}',
        f'Fit classification: {"strong" if has_clear_ai_fit(startup) else "weak/unclear"}',
        f'Best product/problem detail: {clean_company_note(startup, 260) or "No researched product detail available"}',
        f'Raw researched summary: {startup.product_summary or "None"}',
        f'Tags/signals: {", ".join(startup.tags) if startup.tags else "None"}',
        f'Hiring status: {startup.hiring_status}',
        f'Hiring evidence: {startup.hiring_evidence or "None"}',
        f'Remote/India fit: {startup.remote_india_fit or "Unknown"}',
        f'Evidence URLs: {", ".join(startup.evidence_urls[:4]) if startup.evidence_urls else "None"}',
        f'Suggested value-first offer: {help_offer(startup)}',
        f'Suggested closing ask: {closing_ask(startup)}',
        f'Scores: AI-native {startup.ai_native_score}/10, resume-fit {startup.resume_fit_score}/10, interestingness {startup.interestingness_score}/10, learning challenge {startup.learning_challenge_score}/10',
    ]
    return '\n'.join(lines)


def fallback_message(startup: StartupRecord, style: str) -> str:
    product = observation_angle(startup)
    offer = help_offer(startup)
    ask = closing_ask(startup)
    if style == 'short':
        if has_clear_ai_fit(startup):
            return (
                f"Hi, I’m Ritam. I build agentic workflows, multi-agent systems, and RAG/CV products, and {startup.company}'s work around {product} felt relevant to that. "
                "Could I send one concrete idea, or is there something specific you’d like me to build to prove I can help?"
            )
        return (
            "Hi, I’m Ritam. I build agentic workflows, multi-agent systems, and RAG/CV products, and I’m trying to earn opportunities by building small useful things first. "
            "If there’s a lightweight AI/backend prototype you’ve wanted to test, I’d be happy to build it to prove I can help."
        )
    if style == 'email':
        return (
            f"Subject: Building a small AI workflow for {startup.company}\n\n"
            "Hi,\n\n"
            f"I’m Ritam. I build agentic workflows, multi-agent systems, and RAG/CV products, and I was looking at {startup.company}'s work around {product}.\n\n"
            "I’m a 4th-year AI student looking for an internship, but I’d rather prove I can help by building first. "
            f"For your team, I could {offer}.\n\n"
            "If there’s something specific you’d like me to build to prove I can help, send me the problem and I’ll prototype a small version. "
            f"Otherwise, {ask}"
        )
    return (
        f"Hi, I’m Ritam. I build agentic workflows, multi-agent systems, and RAG/CV products. I was looking at {startup.company} and noticed {product}.\n\n"
        f"I’m currently a 4th-year AI student looking for an internship, but I’d rather prove fit by building something useful first. For your team, I could {offer}.\n\n"
        f"{ask}"
    )


async def generate_message(startup: StartupRecord, style: str) -> str:
    settings = get_settings()
    if not settings.openai_api_key:
        return fallback_message(startup, style)
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    if style == 'short':
        length = 'under 280 characters for a LinkedIn connection request'
        style_rules = 'Write exactly 2 sentences. No line breaks. Make it fit a connection request. Open with "I’m Ritam" plus what he builds. End by asking to send one specific useful idea or asking what small thing they would like him to build to prove he can help, not by asking for an internship directly.'
    elif style == 'email':
        length = 'a cold email with a subject line and 4 short paragraphs'
        style_rules = 'Write a cold email. Start with "Subject:" on its own line, then the email body. Paragraph 1 introduces Ritam and one natural company-specific observation. Paragraph 2 says he is a 4th-year AI student looking for an internship, but frames credibility around building first. Paragraph 3 offers a concrete build. Paragraph 4 asks what they would like him to build to prove he can help.'
    else:
        length = '5-7 concise lines for a founder LinkedIn DM'
        style_rules = 'Write 3 short paragraphs with line breaks. Paragraph 1 introduces Ritam as a builder and makes one natural company-specific observation. Paragraph 2 mentions he is a 4th-year AI student looking for an internship, but frames credibility around building something useful first. Paragraph 3 asks what small thing they would like him to build to prove he can help, or asks permission to send one concrete idea.'
    prompt = f'''
Write a highly specific cold outreach message, {length}.
Do not invent facts. Use only the company notes and student profile below.
Tone: human, ambitious, direct, student-founder friendly, not salesy.
Goal: value-first outreach. The message should feel like "I noticed what you're building and can help with a small concrete AI workflow/demo/integration," not "student asking for a job."
{style_rules}

Quality rules:
- Do not mention SRM University unless the user explicitly asks for it later.
- Do not use long dashes. Use commas or periods instead.
- Do not pair internship with project work. Say "internship" only.
- Do not use placeholders like [Name], [Founder], or {{first_name}}. Start with "Hi," if no founder name is available.
- Do not lead with year/student status in founder DMs. If education appears, keep it secondary.
- Introduce Ritam as someone who builds agentic workflows, multi-agent systems, and RAG/CV products.
- Do not use phrases like "found the product interesting", "my strongest fit", "caught my eye", "passionate about", or "possible AI internship work".
- Do not paste a product description after a generic compliment.
- Do not ask directly for an internship in the first line.
- Do not say "caught my eye because of" followed by a raw page title or copied snippet.
- Do not repeat the company name/title/nav text.
- Lead with a natural observation about the specific product/problem the company appears to work on.
- Connect that detail to one concrete contribution Ritam could make: example workflow, agent/RAG demo, integration, eval harness, docs/template, backend prototype, or CV pipeline.
- If company fit is strong, ask to send one concrete idea or ask what they would like Ritam to build to prove he can help.
- If company fit is weak or unclear, do not fake relevance. Ask whether there is a small AI/backend workflow Ritam could build to prove he can help.
- Sound like a thoughtful individual DM, not a template.
- If the research is thin, be honest and phrase it as "I was looking at..." rather than pretending deep knowledge.
- Make the ask lightweight: "Would it be useful if I sent one specific idea?" or "Open to a quick chat?"

Student profile: {PROFILE}
Researched company context:
{researched_context(startup)}
'''.strip()
    response = await client.chat.completions.create(
        model=settings.openai_message_model,
        messages=[{'role': 'system', 'content': 'You write concise, value-first founder outreach for a student builder earning internship/project opportunities by offering to build something useful first.'}, {'role': 'user', 'content': prompt}],
        temperature=0.5,
    )
    return clean_generated_message(response.choices[0].message.content or '')
