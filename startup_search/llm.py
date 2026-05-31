from __future__ import annotations
from openai import AsyncOpenAI
from .config import get_settings
from .models import StartupRecord

PROFILE = '''Ritam Ghosh is a 3rd-year B.Tech AI student at SRM University with production experience building multi-agent LLM systems using LangGraph, RAG systems, computer vision deployments with YOLO/OpenCV, FastAPI/Flask backends, Docker, LangSmith observability, and vector search.'''


def fallback_message(startup: StartupRecord, style: str) -> str:
    product = startup.product_summary or f'what {startup.company} is building'
    angle = 'LLM agents/RAG/CV systems' if startup.resume_fit_score >= 5 else 'AI engineering and product-building'
    if style == 'short':
        return f"Hi, I’m Ritam, a 3rd-year AI student. {startup.company} caught my eye because of {product[:110]}. I’ve built production LangGraph/RAG and CV systems, and I’d love to connect about possible AI internship work."
    return (
        f"Hi, I’m Ritam, a 3rd-year B.Tech AI student at SRM. I was looking into {startup.company} and found the product interesting: {product[:180]}.\n\n"
        f"My strongest fit is {angle}: I’ve worked on a production multi-agent GenAI copilot with LangGraph, RAG systems, and deployed computer vision pipelines. If your team could use an AI/ML intern who can ship prototypes and backend integrations, I’d love to help.\n\n"
        f"Would you be open to a quick chat or should I send over a short project-fit note?"
    )


async def generate_message(startup: StartupRecord, style: str) -> str:
    settings = get_settings()
    if not settings.openai_api_key:
        return fallback_message(startup, style)
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    length = 'under 280 characters for a LinkedIn connection request' if style == 'short' else '5-7 concise lines for a founder LinkedIn DM'
    prompt = f'''
Write a highly specific cold LinkedIn message, {length}.
Do not invent facts. Use only the company notes and student profile below.
Tone: ambitious, direct, student-founder friendly, not salesy.
Ask for an AI/ML internship or a quick chat.

Student profile: {PROFILE}
Company: {startup.company}
Website: {startup.website}
Product notes: {startup.product_summary}
Scores: AI-native {startup.ai_native_score}/10, resume-fit {startup.resume_fit_score}/10, hiring {startup.hiring_status}
Hiring evidence: {startup.hiring_evidence}
'''.strip()
    response = await client.chat.completions.create(
        model=settings.openai_message_model,
        messages=[{'role': 'system', 'content': 'You write concise, honest founder outreach for internships.'}, {'role': 'user', 'content': prompt}],
        temperature=0.5,
    )
    return response.choices[0].message.content.strip()
