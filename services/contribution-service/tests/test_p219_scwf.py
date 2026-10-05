"""P2.19: annual unclaimed-balance transfer and the reclaim window."""
from tests.test_ecr_api import ctx, hdr  # noqa: F401
from tests.test_inoperative import sql


def officer():
    return hdr("accounts-officer", "fo.ao", [], establishment=None)


def test_seven_year_cutoff_transfer_and_reclaim_boundary(ctx):
    client, q = ctx
    sql("UPDATE journals SET occurred_at='2016-08-31 23:59:59' WHERE business_key='OPENING-AL-0002'")
    sql("UPDATE journals SET occurred_at='2016-09-30 23:59:59' WHERE business_key='OPENING-AL-0003'")
    preview = client.get("/api/v1/office/scwf/identifications/2026", headers=officer())
    assert preview.status_code == 200, preview.text
    ids = {r["account_link_id"] for r in preview.json()["data"]["accounts"]}
    assert "AL-0002" in ids and "AL-0003" not in ids
    assert q("SELECT COUNT(*) FROM scwf_transfers") == [(0,)]
    shares_before = q("SELECT share,SUM(CASE WHEN side='credit' THEN amount_paise ELSE -amount_paise END) "
                      "FROM journal_lines WHERE account_code='AC01_EPF' AND account_link_id='AL-0002' GROUP BY share")

    late = client.post("/api/v1/office/scwf/transfers", json={"identification_year": 2026,
                       "transferred_on": "2027-03-02"}, headers=officer())
    assert late.status_code == 422

    sent = client.post("/api/v1/office/scwf/transfers", json={"identification_year": 2026,
                       "transferred_on": "2027-03-01"}, headers=officer())
    assert sent.status_code == 200, sent.text
    row = q("SELECT amount_paise,state FROM scwf_transfers WHERE account_link_id='AL-0002'")[0]
    assert row[0] > 0 and row[1] == "TRANSFERRED"
    assert q("SELECT SUM(CASE WHEN side='credit' THEN amount_paise ELSE -amount_paise END) "
             "FROM journal_lines WHERE account_code='SCWF_PAYABLE'")[0][0] >= row[0]
    again = client.post("/api/v1/office/scwf/transfers", json={"identification_year": 2026,
                        "transferred_on": "2027-03-01"}, headers=officer())
    assert again.status_code == 200
    assert q("SELECT COUNT(*) FROM scwf_transfers WHERE account_link_id='AL-0002'") == [(1,)]
    reclaimed = client.post("/api/v1/office/scwf/transfers/AL-0002/reclaims",
                            json={"claimed_on": "2052-03-01"}, headers=officer())
    assert reclaimed.status_code == 200 and reclaimed.json()["data"]["state"] == "RECLAIMED"
    assert q("SELECT state FROM scwf_transfers WHERE account_link_id='AL-0002'") == [("RECLAIMED",)]
    assert q("SELECT SUM(CASE WHEN side='credit' THEN amount_paise ELSE -amount_paise END) "
             "FROM journal_lines WHERE account_code='AC01_EPF' AND account_link_id='AL-0002'")[0][0] == row[0]
    assert q("SELECT share,SUM(CASE WHEN side='credit' THEN amount_paise ELSE -amount_paise END) "
             "FROM journal_lines WHERE account_code='AC01_EPF' AND account_link_id='AL-0002' GROUP BY share") == shares_before


def test_after_25_years_escheats_without_another_money_movement(ctx):
    client, q = ctx
    sql("UPDATE journals SET occurred_at='2016-08-31' WHERE business_key='OPENING-AL-0002'")
    assert client.post("/api/v1/office/scwf/transfers", json={"identification_year": 2026,
                       "transferred_on": "2027-03-01"}, headers=officer()).status_code == 200
    before = q("SELECT COUNT(*) FROM journals WHERE kind='SCWF_TRANSFER'")[0][0]
    expired = client.post("/api/v1/office/scwf/transfers/AL-0002/reclaims",
                          json={"claimed_on": "2052-03-02"}, headers=officer())
    assert expired.status_code == 200 and expired.json()["data"]["state"] == "ESCHEATED"
    assert q("SELECT state FROM scwf_transfers WHERE account_link_id='AL-0002'") == [("ESCHEATED",)]
    assert q("SELECT COUNT(*) FROM journals WHERE kind='SCWF_TRANSFER'")[0][0] == before


def test_identification_uses_30_september_snapshot(ctx):
    client, _ = ctx
    sql("UPDATE journals SET occurred_at='2016-08-31' WHERE business_key='OPENING-AL-0002'")
    sql("INSERT INTO journals (id,business_key,kind,occurred_at) "
        "VALUES ('future-credit','FUTURE-AL-0002','CONTRIBUTION','2026-10-01')")
    sql("INSERT INTO journal_lines (journal_id,account_code,side,amount_paise) "
        "VALUES ('future-credit','BANK_COLLECTION','debit',100)")
    sql("INSERT INTO journal_lines (journal_id,account_code,side,amount_paise,account_link_id,share) "
        "VALUES ('future-credit','AC01_EPF','credit',100,'AL-0002','employee')")
    response = client.get("/api/v1/office/scwf/identifications/2026", headers=officer())
    assert response.status_code == 200
    assert "AL-0002" in {r["account_link_id"] for r in response.json()["data"]["accounts"]}
