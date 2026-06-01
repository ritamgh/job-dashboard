from startup_search.importers import startups_from_csv, startups_from_rows


def test_csv_import_normalizes_common_columns():
    rows = startups_from_csv('Company,Website,Company LinkedIn,LinkedIn,Funding\nAcme AI,acme.ai,linkedin.com/company/acme,linkedin.com/in/founder,Seed\n')
    assert len(rows) == 1
    assert rows[0].company == 'Acme AI'
    assert rows[0].website == 'acme.ai'
    assert rows[0].linkedin == 'linkedin.com/company/acme'
    assert rows[0].founder_linkedin == 'linkedin.com/in/founder'


def test_rows_import_falls_back_to_first_value_as_company():
    rows = startups_from_rows([{'Name-ish': 'Mystery AI', 'URL': 'mystery.ai'}])
    assert rows[0].company == 'Mystery AI'
    assert rows[0].website == 'mystery.ai'
