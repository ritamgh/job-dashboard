from __future__ import annotations
import re
from dataclasses import dataclass
import httpx
from .config import get_settings


SIZE_RE = re.compile(r'(?P<low>\d{1,3}(?:,\d{3})?)\s*(?:-|–|to)\s*(?P<high>\d{1,3}(?:,\d{3})?)\s+employees?', re.IGNORECASE)
SINGLE_SIZE_RE = re.compile(r'(?P<count>\d{1,3}(?:,\d{3})?)\+?\s+employees?', re.IGNORECASE)


@dataclass
class CompanySizeEstimate:
    estimate: str
    confidence: int
    source_url: str | None = None
    source_snippet: str | None = None

    def as_dict(self) -> dict:
        return {
            'company_size_estimate': self.estimate,
            'company_size_confidence': self.confidence,
            'company_size_source_url': self.source_url,
            'company_size_source_snippet': self.source_snippet,
        }


def company_size_queries(company: str, website: str | None = None, linkedin: str | None = None) -> list[str]:
    queries = [
        f'{company} LinkedIn company employees',
        f'site:linkedin.com/company {company} employees',
        f'{company} Wellfound employees',
        f'{company} team size employees',
    ]
    if linkedin:
        queries.insert(0, f'{linkedin} employees')
    if website:
        queries.append(f'{company} {website} employees')
    return queries


def _clean_number(value: str) -> int:
    return int(value.replace(',', ''))


def _estimate_from_text(text: str, source_url: str | None = None) -> CompanySizeEstimate | None:
    match = SIZE_RE.search(text)
    if match:
        low = _clean_number(match.group('low'))
        high = _clean_number(match.group('high'))
        confidence = 80 if source_url and 'linkedin.com/company' in source_url.lower() else 65
        return CompanySizeEstimate(f'{low}-{high} employees', confidence, source_url, text[:500])
    match = SINGLE_SIZE_RE.search(text)
    if match:
        count = _clean_number(match.group('count'))
        confidence = 60 if source_url and 'linkedin.com/company' in source_url.lower() else 45
        return CompanySizeEstimate(f'{count}+ employees', confidence, source_url, text[:500])
    return None


def parse_company_size_results(payload: dict) -> CompanySizeEstimate | None:
    best: CompanySizeEstimate | None = None
    for item in list(payload.get('organic') or []):
        source_url = str(item.get('link') or '') or None
        text = ' · '.join(str(item.get(key) or '') for key in ('title', 'snippet', 'link'))
        estimate = _estimate_from_text(text, source_url)
        if estimate and (best is None or estimate.confidence > best.confidence):
            best = estimate
    return best


async def estimate_company_size(company: str, website: str | None = None, linkedin: str | None = None) -> dict | None:
    settings = get_settings()
    if not settings.serper_api_key:
        return None
    headers = {'X-API-KEY': settings.serper_api_key, 'Content-Type': 'application/json'}
    best: CompanySizeEstimate | None = None
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        for query in company_size_queries(company, website, linkedin):
            response = await client.post(settings.serper_endpoint, headers=headers, json={'q': query})
            response.raise_for_status()
            estimate = parse_company_size_results(response.json())
            if estimate and (best is None or estimate.confidence > best.confidence):
                best = estimate
            if best and best.confidence >= 80:
                break
    return best.as_dict() if best else None
