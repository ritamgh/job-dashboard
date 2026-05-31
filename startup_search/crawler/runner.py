from __future__ import annotations

import argparse
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from .spiders.startup_research_spider import StartupResearchSpider


def run(run_id: int, limit: int = 100) -> None:
    settings = get_project_settings()
    settings.setmodule('startup_search.crawler.settings')
    process = CrawlerProcess(settings)
    process.crawl(StartupResearchSpider, run_id=run_id, limit=limit)
    process.start()


def main() -> None:
    parser = argparse.ArgumentParser(description='Run Scrapy-first startup research worker')
    parser.add_argument('--run-id', type=int, required=True)
    parser.add_argument('--limit', type=int, default=100)
    args = parser.parse_args()
    run(args.run_id, args.limit)


if __name__ == '__main__':
    main()
