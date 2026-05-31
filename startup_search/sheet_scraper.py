from __future__ import annotations
import json
import re
import urllib.parse
import urllib.request
from typing import Any

SHEET_ID_RE = re.compile(r'/spreadsheets/d/([a-zA-Z0-9-_]+)')


def sheet_id_from_url(url: str) -> str | None:
    match = SHEET_ID_RE.search(url)
    return match.group(1) if match else None


def gid_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if 'gid' in query and query['gid']:
        return query['gid'][0]
    fragment = urllib.parse.parse_qs(parsed.fragment)
    if 'gid' in fragment and fragment['gid']:
        return fragment['gid'][0]
    return '0'


def scrape_google_sheet_gviz(url: str) -> list[dict[str, Any]]:
    """Read a public Google Sheet through the Visualization API.

    This often works for view-only sheets even when export/copy/download are
    disabled. `headers=0` preserves the title row and real header row so we can
    infer columns ourselves.
    """
    sheet_id = sheet_id_from_url(url)
    if not sheet_id:
        raise ValueError('Could not find Google Sheet id in URL')
    gid = gid_from_url(url)
    endpoint = f'https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:json&gid={gid}&headers=0'
    request = urllib.request.Request(endpoint, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read().decode('utf-8', errors='replace')
    data = json.loads(payload[payload.index('{'): payload.rindex('}') + 1])
    raw_rows = []
    for row in data.get('table', {}).get('rows', []):
        raw_rows.append([(cell or {}).get('v') for cell in row.get('c', [])])
    header_index = next((i for i, row in enumerate(raw_rows) if any(str(cell).strip().lower() == 'company name' for cell in row if cell is not None)), None)
    if header_index is None:
        header_index = 0
    headers = [str(cell).strip() if cell is not None and str(cell).strip() else f'column_{idx + 1}' for idx, cell in enumerate(raw_rows[header_index])]
    output: list[dict[str, Any]] = []
    for raw in raw_rows[header_index + 1:]:
        item = {headers[idx]: (raw[idx] if idx < len(raw) else '') for idx in range(len(headers))}
        if any(str(v).strip() for v in item.values()):
            output.append(item)
    return output


async def scrape_google_sheet(url: str, max_scrolls: int = 120) -> list[dict[str, Any]]:
    try:
        rows = scrape_google_sheet_gviz(url)
        if rows:
            return rows
    except Exception:
        pass
    return await scrape_google_sheet_rendered(url, max_scrolls=max_scrolls)


async def scrape_google_sheet_rendered(url: str, max_scrolls: int = 120) -> list[dict[str, Any]]:
    """Extract visible/rendered Google Sheet cells with Playwright.

    This is read-only and scrolls the grid to collect rows. It is intentionally
    conservative: it only reads DOM text and never clicks editing controls.
    """
    from playwright.async_api import async_playwright

    rows: dict[int, dict[int, str]] = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1600, 'height': 1000})
        await page.goto(url, wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(5000)
        for _ in range(max_scrolls):
            cells = await page.locator('[role="gridcell"]').evaluate_all('''els => els.map(el => ({
                row: Number(el.getAttribute('data-row') || el.getAttribute('aria-rowindex') || 0),
                col: Number(el.getAttribute('data-col') || el.getAttribute('aria-colindex') || 0),
                text: el.innerText || el.textContent || ''
            }))''')
            for cell in cells:
                row = int(cell.get('row') or 0)
                col = int(cell.get('col') or 0)
                text = str(cell.get('text') or '').strip()
                if row and col and text:
                    rows.setdefault(row, {})[col] = text
            await page.mouse.wheel(0, 900)
            await page.wait_for_timeout(250)
        await browser.close()
    if not rows:
        return []
    sorted_rows = [rows[i] for i in sorted(rows)]
    header_cells = sorted_rows[0]
    headers = [header_cells.get(c, f'column_{c}') for c in sorted(header_cells)]
    output: list[dict[str, Any]] = []
    for row in sorted_rows[1:]:
        item: dict[str, Any] = {}
        for idx, col in enumerate(sorted(header_cells)):
            item[headers[idx]] = row.get(col, '')
        if any(str(v).strip() for v in item.values()):
            output.append(item)
    return output
