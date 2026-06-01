from __future__ import annotations

import re
from collections import defaultdict
from urllib.parse import urljoin, urlparse

import scrapy
from twisted.python.failure import Failure

from startup_search.config import get_settings
from startup_search.models import StartupInput
from startup_search.research import CAREER_PATHS, normalize_url, text_from_html
from startup_search.scoring import deterministic_research
from startup_search.storage import apply_research, list_research_jobs, record_research_fetch, update_research_job

EXTRA_CAREER_PATHS = ['/work-with-us', '/positions', '/open-roles']
CAREER_LINK_RE = re.compile(r'careers?|jobs?|join|hiring|roles?|positions|work-with-us', re.I)
ATS_HOST_RE = re.compile(r'(lever\.co|greenhouse\.io|ashbyhq\.com|workable\.com|wellfound\.com)', re.I)
JS_SHELL_RE = re.compile(r'enable javascript|requires javascript|please turn on javascript', re.I)


class StartupResearchSpider(scrapy.Spider):
    name = 'startup_research'

    def __init__(self, run_id: int, limit: int = 100, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.run_id = int(run_id)
        self.limit = int(limit)
        self.settings_obj = get_settings()
        self.jobs = list_research_jobs(self.run_id, limit=self.limit)
        self.pages: dict[int, list[dict]] = defaultdict(list)
        self.errors: dict[int, list[str]] = defaultdict(list)
        self.startups: dict[int, StartupInput] = {}
        self.job_startup_ids: dict[int, int] = {}
        self.seen_urls: dict[int, set[str]] = defaultdict(set)
        self.inflight_requests: dict[int, int] = defaultdict(int)
        self.finalized_jobs: set[int] = set()
        self.max_pages_per_job = 8

    def start_requests(self):
        for job in self.jobs:
            job_id = int(job['id'])
            startup_id = int(job['startup_id'])
            startup = StartupInput(
                company=job['company'],
                website=job.get('website'),
                linkedin=job.get('linkedin'),
                twitter=job.get('twitter'),
                founder_twitter=job.get('founder_twitter'),
                funding=job.get('funding'),
                raw=job.get('raw') or {},
            )
            self.startups[job_id] = startup
            self.job_startup_ids[job_id] = startup_id
            update_research_job(job_id, 'running')
            home = normalize_url(startup.website)
            if not home:
                self.errors[job_id].append('No website URL to crawl')
                self.finalize_job(job_id)
                continue
            requests = []
            for url in self.initial_urls(home):
                req = self.make_request(job_id, startup_id, url, source='seed')
                if req is not None:
                    requests.append(req)
            yield from requests

    async def start(self):
        for request in self.start_requests():
            if request is not None:
                yield request

    def initial_urls(self, home: str) -> list[str]:
        parsed = urlparse(home)
        base = f'{parsed.scheme}://{parsed.netloc}'
        urls = [home]
        urls.extend(urljoin(base, path) for path in [*CAREER_PATHS, *EXTRA_CAREER_PATHS])
        return list(dict.fromkeys(urls))[: self.max_pages_per_job]

    def make_request(self, job_id: int, startup_id: int, url: str, source: str):
        normalized = url.split('#', 1)[0]
        if normalized in self.seen_urls[job_id]:
            return None
        if len(self.seen_urls[job_id]) >= self.max_pages_per_job:
            return None
        self.seen_urls[job_id].add(normalized)
        self.inflight_requests[job_id] += 1
        return scrapy.Request(
            normalized,
            callback=self.parse_page,
            errback=self.errback_page,
            dont_filter=True,
            meta={
                'job_id': job_id,
                'startup_id': startup_id,
                'source': source,
                'handle_httpstatus_list': [400, 401, 403, 404, 410, 429, 500, 502, 503],
            },
        )

    def parse_page(self, response: scrapy.http.Response):
        job_id = int(response.meta['job_id'])
        startup_id = int(response.meta['startup_id'])
        content_type = response.headers.get('Content-Type', b'').decode('latin1', errors='ignore')
        text = ''
        if response.status < 400 and 'text/html' in content_type.lower():
            text = text_from_html(response.text)[: self.settings_obj.max_page_chars]
            if text:
                self.pages[job_id].append({'url': response.url, 'text': text, 'status': response.status})
        else:
            self.errors[job_id].append(f'{response.url} returned {response.status}')
        record_research_fetch(
            job_id,
            response.request.url,
            final_url=response.url,
            status_code=response.status,
            content_type=content_type,
            text_chars=len(text),
        )
        new_requests = []
        if response.status < 400 and text and len(self.seen_urls[job_id]) < self.max_pages_per_job:
            for href in self.discover_career_links(response):
                req = self.make_request(job_id, startup_id, href, source='discovered')
                if req is not None:
                    new_requests.append(req)
        self.inflight_requests[job_id] -= 1
        self.finalize_job_if_done(job_id)
        yield from new_requests

    def discover_career_links(self, response: scrapy.http.Response) -> list[str]:
        home_host = urlparse(response.url).netloc.lower().removeprefix('www.')
        links: list[str] = []
        for href in response.css('a::attr(href)').getall():
            if not href:
                continue
            absolute = urljoin(response.url, href).split('#', 1)[0]
            parsed = urlparse(absolute)
            host = parsed.netloc.lower().removeprefix('www.')
            haystack = f'{href} {absolute}'
            if host == home_host and CAREER_LINK_RE.search(haystack):
                links.append(absolute)
            elif ATS_HOST_RE.search(host):
                links.append(absolute)
        return list(dict.fromkeys(links))[:4]

    def errback_page(self, failure: Failure):
        request = failure.request
        job_id = int(request.meta['job_id'])
        error = failure.getErrorMessage()[:300]
        self.errors[job_id].append(f'{request.url}: {error}')
        record_research_fetch(job_id, request.url, error=error)
        self.inflight_requests[job_id] -= 1
        self.finalize_job_if_done(job_id)

    def finalize_job_if_done(self, job_id: int):
        if self.inflight_requests[job_id] <= 0:
            self.finalize_job(job_id)

    def finalize_job(self, job_id: int):
        if job_id in self.finalized_jobs:
            return
        self.finalized_jobs.add(job_id)
        startup_id = self.job_startup_ids.get(job_id)
        startup = self.startups.get(job_id)
        if not startup or startup_id is None:
            update_research_job(job_id, 'failed', 'Job was not initialized')
            return
        pages = self.pages.get(job_id, [])
        combined_text = '\n'.join(page['text'] for page in pages)
        evidence_urls = [page['url'] for page in pages]
        result = None
        if combined_text:
            result = deterministic_research(startup, combined_text, evidence_urls)
            apply_research(startup_id, result)
        if not normalize_url(startup.website):
            update_research_job(job_id, 'failed', 'No website URL to crawl')
            return
        needs_browser = self.needs_browser(combined_text) and (result is None or result.research_confidence < 8)
        if needs_browser:
            update_research_job(job_id, 'needs_browser', self.browser_reason(combined_text), needs_browser=True)
        elif combined_text:
            update_research_job(job_id, 'completed')
        else:
            update_research_job(job_id, 'failed', '; '.join(self.errors.get(job_id, ['No crawlable text found']))[:500])

    def closed(self, reason: str):
        for job in self.jobs:
            self.finalize_job(int(job['id']))

    def needs_browser(self, text: str) -> bool:
        stripped = text.strip()
        return bool(stripped and (len(stripped) < 400 or JS_SHELL_RE.search(stripped)))

    def browser_reason(self, text: str) -> str:
        if JS_SHELL_RE.search(text):
            return 'Static scrape found JavaScript-required shell; needs browser fallback.'
        return 'Static scrape found very little text; needs browser fallback.'
