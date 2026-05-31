from __future__ import annotations
import csv
from io import StringIO
from typing import Any
from .models import StartupInput

COMPANY_KEYS = ['company', 'company name', 'name', 'startup']
WEBSITE_KEYS = ['website', 'site', 'url', 'company website']
LINKEDIN_KEYS = ['company linkedin', 'linkedin', 'linkedin url']
TWITTER_KEYS = ['company twitter', 'twitter', 'x', 'x/twitter']
FUNDING_KEYS = ['funding', 'round', 'amount', 'raise', 'funding round']


def pick(row: dict[str, Any], keys: list[str]) -> str | None:
    lower = {str(k).strip().lower(): v for k, v in row.items()}
    for key in keys:
        val = lower.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return None


def normalize_row(row: dict[str, Any]) -> StartupInput | None:
    company = pick(row, COMPANY_KEYS)
    lower_keys = {str(k).strip().lower() for k in row.keys()}
    has_company_column = any(key in lower_keys for key in COMPANY_KEYS)
    if has_company_column and not company:
        return None
    if not company:
        values = [str(v).strip() for v in row.values() if v is not None and str(v).strip()]
        company = values[0] if values else None
    if not company:
        return None
    return StartupInput(
        company=company,
        website=pick(row, WEBSITE_KEYS),
        linkedin=pick(row, LINKEDIN_KEYS),
        twitter=pick(row, TWITTER_KEYS),
        funding=pick(row, FUNDING_KEYS),
        raw={str(k): v for k, v in row.items()},
    )


def startups_from_csv(text: str) -> list[StartupInput]:
    reader = csv.DictReader(StringIO(text))
    return [s for row in reader if (s := normalize_row(row))]


def startups_from_rows(rows: list[dict[str, Any]]) -> list[StartupInput]:
    return [s for row in rows if (s := normalize_row(row))]
