"""P2.19: amalgamation retains service and passes dues to the transferee."""
from tests.test_ecr_api import ctx, hdr  # noqa: F401
from tests.test_inoperative import sql


def test_amalgamation_continues_service_and_dues(ctx):
    client, q = ctx
    sql("INSERT INTO demands (demand_id,establishment_id,kind,trrn,wage_month,amount_paise,days_late,"
        "working,rule_version,state) VALUES ('MERGER-DUE','EST-DEMO-0001','INTEREST_7Q','TRRN0000000000001',"
        "'2026-08',12500,3,'[]','test','OPEN')")
    original = q("SELECT date_of_joining,date_of_exit FROM establishment_members WHERE account_link_id='AL-0001'")[0]
    office = hdr("office", "fo.apfc", [], establishment=None)
    response = client.post("/api/v1/office/establishments/mergers",
                           json={"from_establishment_id": "EST-DEMO-0001", "to_establishment_id": "EST-DEMO-0002",
                                 "effective_on": "2026-09-01"}, headers=office)
    assert response.status_code == 200, response.text
    assert q("SELECT establishment_id,date_of_joining,date_of_exit FROM establishment_members "
             "WHERE account_link_id='AL-0001'") == [("EST-DEMO-0002", *original)]
    assert q("SELECT COUNT(*) FROM transfer_postings") == [(0,)]
    dues = client.get("/api/v1/employers/me/demands", headers=hdr("new-owner", "employer.owner", [],
                      establishment="EST-DEMO-0002"))
    assert dues.status_code == 200 and "MERGER-DUE" in str(dues.json()["data"])
    assert client.post("/api/v1/office/establishments/mergers",
                       json={"from_establishment_id": "EST-DEMO-0001", "to_establishment_id": "EST-DEMO-0002",
                             "effective_on": "2026-09-01"}, headers=office).status_code == 200
    assert q("SELECT COUNT(*) FROM establishment_mergers") == [(1,)]
