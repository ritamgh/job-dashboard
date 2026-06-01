from startup_search.importers import startups_from_csv, startups_from_rows


def test_csv_import_normalizes_common_columns():
    rows = startups_from_csv('Company,Website,Company LinkedIn,Company Twitter,LinkedIn,Twitter,Funding\nAcme AI,acme.ai,linkedin.com/company/acme,x.com/acme,linkedin.com/in/founder,x.com/founder,Seed\n')
    assert len(rows) == 1
    assert rows[0].company == 'Acme AI'
    assert rows[0].website == 'acme.ai'
    assert rows[0].linkedin == 'linkedin.com/company/acme'
    assert rows[0].twitter == 'x.com/acme'
    assert rows[0].founder_linkedin == 'linkedin.com/in/founder'
    assert rows[0].founder_twitter == 'x.com/founder'


def test_rows_import_falls_back_to_first_value_as_company():
    rows = startups_from_rows([{'Name-ish': 'Mystery AI', 'URL': 'mystery.ai'}])
    assert rows[0].company == 'Mystery AI'
    assert rows[0].website == 'mystery.ai'
