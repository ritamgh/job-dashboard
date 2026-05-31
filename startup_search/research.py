from __future__ import annotations
import hashlib
import re
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup
from .config import get_settings
from .models import ResearchResult, StartupInput
from .scoring import deterministic_research

CAREER_PATHS = ['/careers', '/jobs', '/join-us', '/company/careers']
HEADERS = {'User-Agent': 'StartupSearchBot/0.1 (+local research dashboard)'}


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    if not re.match(r'^https?://', url):
        url = 'https://' + url
    return url


def text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, 'html.parser')
    for node in soup(['script', 'style', 'noscript', 'svg']):
        node.decompose()
    return re.sub(r'\s+', ' ', soup.get_text(' ', strip=True)).strip()


async def fetch_url(client: httpx.AsyncClient, url: str) -> tuple[str, str] | None:
    settings = get_settings()
    cache_key = hashlib.sha256(url.encode()).hexdigest() + '.txt'
    cache_path = settings.fetch_cache_dir / cache_key
    if cache_path.exists():
        return url, cache_path.read_text(encoding='utf-8', errors='ignore')
    try:
        resp = await client.get(url, follow_redirects=True)
        if resp.status_code >= 400 or 'text/html' not in resp.headers.get('content-type', ''):
            return None
        text = text_from_html(resp.text)[: settings.max_page_chars]
        cache_path.write_text(text, encoding='utf-8')
        return str(resp.url), text
    except Exception:
        return None


def career_urls(home_url: str) -> list[str]:
    parsed = urlparse(home_url)
    base = f'{parsed.scheme}://{parsed.netloc}'
    return [urljoin(base, path) for path in CAREER_PATHS]


async def research_startup(startup: StartupInput) -> ResearchResult:
    settings = get_settings()
    evidence: list[str] = []
    texts: list[str] = []
    home = normalize_url(startup.website)
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, headers=HEADERS) as client:
        urls = [home] if home else []
        urls.extend(career_urls(home) if home else [])
        for url in urls:
            if not url:
                continue
            result = await fetch_url(client, url)
            if result:
                final_url, text = result
                evidence.append(final_url)
                texts.append(text)
    return deterministic_research(startup, '\n'.join(texts), evidence)
