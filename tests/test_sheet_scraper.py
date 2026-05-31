from startup_search.sheet_scraper import gid_from_url, sheet_id_from_url


def test_sheet_id_and_gid_from_url():
    url = 'https://docs.google.com/spreadsheets/d/abc123_DEF/edit?gid=42#gid=42'
    assert sheet_id_from_url(url) == 'abc123_DEF'
    assert gid_from_url(url) == '42'
