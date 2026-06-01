from __future__ import annotations
import re
from dataclasses import dataclass
from urllib.parse import urlparse
import httpx
from .config import get_settings

EMAIL_RE = re.compile(r'(?<![\w.+-])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})(?![\w.+-])', re.IGNORECASE)
LINKEDIN_RE = re.compile(r'https?://(?:[\w-]+\.)?linkedin\.com/in/[^\s)"\']+', re.IGNORECASE)


@dataclass
class ContactCandidate:
    name: str | None = None
    role: str | None = None
    email: str | None = None
    linkedin_url: str | None = None
    confidence: int = 0
    source_url: str | None = None
    source_snippet: str | None = None

    def as_dict(self) -> dict:
        return {
            'name': self.name,
            'role': self.role,
            'email': self.email,
            'linkedin_url': self.linkedin_url,
            'confidence': self.confidence,
            'source_url': self.source_url,
            'source_snippet': self.source_snippet,
        }


def company_domain(website: str) -> str:
    parsed = urlparse(website if website.startswith(('http://', 'https://')) else f'https://{website}')
    host = parsed.netloc.lower().removeprefix('www.')
    return host


def contact_queries(company: str, website: str) -> list[str]:
    domain = company_domain(website)
    return [
        f'site:{domain} email founder OR careers OR contact',
        f'{company} founder email',
        f'{company} hiring manager email',
        f'{company} LinkedIn founder',
        f'{company} contact',
    ]


def _confidence(email: str | None, linkedin_url: str | None, source_url: str | None, domain: str) -> int:
    score = 35
    if email:
        score += 25
        if email.lower().endswith('@' + domain):
            score += 30
        elif domain and domain.split('.')[0] in email.lower():
            score += 10
    if linkedin_url:
        score += 15
    if source_url and domain in source_url.lower():
        score += 15
    return max(0, min(score, 100))


def parse_serper_results(payload: dict, website: str) -> list[ContactCandidate]:
    domain = company_domain(website)
    candidates: dict[tuple[str | None, str | None], ContactCandidate] = {}
    results = list(payload.get('organic') or []) + list(payload.get('peopleAlsoAsk') or [])
    for item in results:
        snippet = str(item.get('snippet') or item.get('title') or '')
        link = str(item.get('link') or '') or None
        text = ' '.join(str(item.get(k) or '') for k in ('title', 'snippet', 'link'))
        emails = EMAIL_RE.findall(text)
        linkedins = LINKEDIN_RE.findall(text)
        if not emails and not linkedins:
            continue
        for email in emails or [None]:
            linkedin = linkedins[0] if linkedins else None
            key = (email.lower() if email else None, linkedin)
            confidence = _confidence(email, linkedin, link, domain)
            existing = candidates.get(key)
            candidate = ContactCandidate(
                email=email,
                linkedin_url=linkedin,
                confidence=confidence,
                source_url=link,
                source_snippet=snippet[:500] if snippet else None,
            )
            if existing is None or candidate.confidence > existing.confidence:
                candidates[key] = candidate
    return sorted(candidates.values(), key=lambda c: c.confidence, reverse=True)


async def search_contacts(company: str, website: str) -> list[dict]:
    settings = get_settings()
    if not settings.serper_api_key:
        return []
    headers = {'X-API-KEY': settings.serper_api_key, 'Content-Type': 'application/json'}
    found: dict[tuple[str | None, str | None], ContactCandidate] = {}
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        for query in contact_queries(company, website):
            response = await client.post(settings.serper_endpoint, headers=headers, json={'q': query})
            response.raise_for_status()
            for candidate in parse_serper_results(response.json(), website):
                key = (candidate.email.lower() if candidate.email else None, candidate.linkedin_url)
                if key not in found or candidate.confidence > found[key].confidence:
                    found[key] = candidate
            if len(found) >= settings.contact_search_limit:
                break
    return [c.as_dict() for c in sorted(found.values(), key=lambda c: c.confidence, reverse=True)[: settings.contact_search_limit]]
