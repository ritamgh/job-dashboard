from __future__ import annotations
import re
from .contact_search import search_contacts
from .gmail import send_email
from .llm import generate_message
from .models import StartupInput, StartupRecord
from .research import normalize_url, research_startup
from .scoring import weighted_overall
from .storage import (
    add_outreach_contact,
    create_outreach_draft,
    get_outreach_draft,
    get_outreach_session,
    list_outreach_contacts,
    list_outreach_drafts,
    save_outreach_research,
    set_outreach_draft_send_result,
)


def infer_company_from_url(website: str) -> str:
    normalized = normalize_url(website) or website
    host = re.sub(r'^https?://', '', normalized).split('/')[0].removeprefix('www.')
    root = host.split('.')[0]
    return root.replace('-', ' ').replace('_', ' ').title() or host


def _record_from_session(session: dict) -> StartupRecord:
    research = session.get('research') or {}
    overall = weighted_overall(
        int(research.get('ai_native_score') or 0),
        int(research.get('resume_fit_score') or 0),
        int(research.get('hiring_likelihood_score') or 0),
        int(research.get('learning_challenge_score') or 0),
        int(research.get('logistics_score') or 0),
    )
    return StartupRecord(
        id=int(session['id']),
        company=session.get('company') or infer_company_from_url(session['website']),
        website=session.get('website'),
        product_summary=research.get('product_summary'),
        ai_native_score=int(research.get('ai_native_score') or 0),
        interestingness_score=int(research.get('interestingness_score') or 0),
        resume_fit_score=int(research.get('resume_fit_score') or 0),
        hiring_likelihood_score=int(research.get('hiring_likelihood_score') or 0),
        learning_challenge_score=int(research.get('learning_challenge_score') or 0),
        logistics_score=int(research.get('logistics_score') or 0),
        overall_score=overall,
        hiring_status=research.get('hiring_status') or 'Unknown',
        hiring_evidence=research.get('hiring_evidence'),
        remote_india_fit=research.get('remote_india_fit'),
        research_confidence=int(research.get('research_confidence') or 0),
        evidence_urls=research.get('evidence_urls') or [],
        tags=research.get('tags') or [],
    )


def split_subject_body(message: str, fallback_company: str) -> tuple[str, str]:
    lines = message.strip().splitlines()
    if lines and lines[0].lower().startswith('subject:'):
        subject = lines[0].split(':', 1)[1].strip() or f'Building a small AI workflow for {fallback_company}'
        body = '\n'.join(lines[1:]).strip()
        return subject, body
    return f'Building a small AI workflow for {fallback_company}', message.strip()


async def research_session(session_id: int) -> dict:
    session = get_outreach_session(session_id)
    if not session:
        raise KeyError('Outreach session not found')
    company = session.get('company') or infer_company_from_url(session['website'])
    result = await research_startup(StartupInput(company=company, website=session['website']))
    return save_outreach_research(session_id, result)


async def discover_contacts(session_id: int) -> list[dict]:
    session = get_outreach_session(session_id)
    if not session:
        raise KeyError('Outreach session not found')
    company = session.get('company') or infer_company_from_url(session['website'])
    contacts = await search_contacts(company, session['website'])
    for contact in contacts:
        add_outreach_contact(session_id, contact)
    return list_outreach_contacts(session_id)


async def generate_drafts(session_id: int) -> list[dict]:
    session = get_outreach_session(session_id)
    if not session:
        raise KeyError('Outreach session not found')
    record = _record_from_session(session)
    email_message = await generate_message(record, 'email')
    subject, body = split_subject_body(email_message, record.company)
    founder_dm = await generate_message(record, 'founder')
    followup = (
        f'Hi, just following up on my note about {record.company}. '
        'Would it be useful if I sent one concrete idea for a small AI/backend workflow I could build to prove I can help?'
    )
    existing = list_outreach_drafts(session_id)
    if existing:
        return existing
    create_outreach_draft(session_id, {'channel': 'email', 'subject': subject, 'body': body})
    create_outreach_draft(session_id, {'channel': 'linkedin', 'body': founder_dm})
    create_outreach_draft(session_id, {'channel': 'followup', 'subject': f'Following up on {record.company}', 'body': followup})
    return list_outreach_drafts(session_id)


def send_draft(draft_id: int, to: str, subject: str | None, body: str | None, confirm_send: bool) -> dict:
    draft = get_outreach_draft(draft_id)
    if not draft:
        raise KeyError('Outreach draft not found')
    if draft['channel'] != 'email':
        raise ValueError('Only email drafts can be sent')
    if not confirm_send:
        raise ValueError('confirm_send must be true')
    final_subject = (subject or draft.get('edited_subject') or draft.get('subject') or '').strip()
    final_body = (body or draft.get('edited_body') or draft.get('body') or '').strip()
    if not to.strip() or not final_subject or not final_body:
        raise ValueError('Recipient, subject, and body are required')
    set_outreach_draft_send_result(draft_id, 'sending')
    result = send_email(to.strip(), final_subject, final_body)
    set_outreach_draft_send_result(
        draft_id,
        'sent' if result.sent else 'failed',
        gmail_message_id=result.message_id,
        gmail_thread_id=result.thread_id,
        last_error=result.error,
    )
    data = result.as_dict()
    data['draft'] = get_outreach_draft(draft_id)
    return data
