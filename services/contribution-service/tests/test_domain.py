import copy
from datetime import date
from pathlib import Path

import yaml
import pytest

from app.domain.ecr import FIELDS, parse, split, validate
from app.domain.ledger import build_postings
from app.domain.state import transition

RULES = yaml.safe_load((Path(__file__).resolve().parents[3] / "config/demo-rules.yaml").read_text())
MEMBERS = [
    {"uan": "100000000001", "name": "ASHA DEMO", "date_of_birth": date(1990, 4, 12), "account_link_id": "AL-1", "status": "ACTIVE"},
    {"uan": "100000000004", "name": "DEV DEMO", "date_of_birth": date(1966, 1, 20), "account_link_id": "AL-4", "status": "ACTIVE"},
]


def row(uan="100000000001", name="ASHA DEMO", gross="100000", epf="100000", eps="15000", edli="15000", ee="12000", eps_share="1250", er="10750", ncp="0", refund="0"):
    return [uan, name, gross, epf, eps, edli, ee, eps_share, er, ncp, refund]


def test_txt_parser_and_csv_header():
    content = "#~#".join(row())
    assert parse(content, "ECR_TXT")[0][0]["UAN"] == "100000000001"
    csv_content = ",".join(FIELDS) + "\n" + ",".join(row())
    assert parse(csv_content, "CSV")[0][0]["Member Name"] == "ASHA DEMO"


def test_rounding_and_age_58_example():
    assert split(10000000, 1500000, 60, RULES)["AC10_EPS"] == 0
    assert split(10000000, 1500000, 60, RULES)["AC01_EPF_ER"] == 1200000
    # Born 1966-01-20 is over the illustrative age limit in wage month 2026-08.
    dev = MEMBERS[1]
    content = "#~#".join(row(uan=dev["uan"], name=dev["name"]))
    report = validate(content, "ECR_TXT", "2026-08", MEMBERS, RULES)
    assert any(i["code"] == "E-AGE-EPS" for i in report["issues"])
    corrected = report["corrected_content"].split("#~#")
    assert corrected[0] == "100000000004" and corrected[1] == "DEV DEMO"
    assert corrected[2:6] == ["100000", "100000", "15000", "15000"]


def test_validation_reports_actionable_codes_and_safe_correction():
    malformed = "#~#".join(["100000000001", "ASHA DEMO", "1,000", "2000", "20000", "20000", "1.2", "999", "8", "32", "0"])
    duplicate = "#~#".join(row())
    unknown = "#~#".join(row(uan="999999999999", name="ALIEN"))
    content = "\n".join([malformed, duplicate, duplicate, unknown])
    report = validate(content, "ECR_TXT", "2026-08", MEMBERS, RULES)
    codes = {x["code"] for x in report["issues"]}
    assert {"E-FORMAT-NUMBER", "E-DUPLICATE-UAN", "E-UAN-UNKNOWN", "E-WAGE-ORDER", "E-EPS-CEILING", "E-EPF-EE", "E-EPS-SHARE", "E-DIFF-SHARE", "E-NCP-DAYS"} <= codes
    corrected = report["corrected_content"].splitlines()[0].split("#~#")
    assert corrected[:6] == ["100000000001", "ASHA DEMO", "1,000", "2000", "20000", "20000"]
    assert corrected[9] == "32" and corrected[10] == "0"


def test_field_count_and_zero_wage_codes():
    short = "#~#".join(row()[:-1])
    zero = "#~#".join(row(gross="0", epf="0", eps="0", edli="0", ee="0", eps_share="0", er="0"))
    codes = {i["code"] for i in validate(short + "\n" + zero, "ECR_TXT", "2026-08", MEMBERS, RULES)["issues"]}
    assert {"E-FORMAT-FIELDS", "W-ZERO-WAGES"} <= codes


def test_name_mismatch_zero_missing_normalisation_and_headcount_warnings():
    content = "\ufeff" + "#~#".join(row(name="wrong")) + "  \r\n"
    report = validate(content, "ECR_TXT", "2026-08", MEMBERS, RULES,
                      {"wage_month": "2026-07", "members_then": 5, "total_then_paise": 100, "total_now_paise": 0})
    codes = {i["code"] for i in report["issues"]}
    assert {"W-FORMAT-NORMALISED", "W-MISSING-MEMBER", "W-HEADCOUNT-CHANGE", "E-NAME-MISMATCH"} <= codes


def test_ledger_builder_balances_and_has_member_share_lines():
    postings = build_postings([{"account_link_id": "AL-1", "shares": {"employee": 12000, "employer": 10750}, "AC10_EPS": 1250, "AC21_EDLI": 75, "AC02_ADMIN": 500, "AC22_EDLI_ADMIN": 0}],
                             {"TOTAL": 24575})
    assert sum(x["amount_paise"] for x in postings if x["side"] == "debit") == sum(x["amount_paise"] for x in postings if x["side"] == "credit")
    assert len([x for x in postings if x.get("account_link_id") == "AL-1"]) == 2


def test_state_machine_all_declared_edges_and_forbidden_jumps():
    from app.domain.state import ALLOWED
    for before, afters in ALLOWED.items():
        for after in afters:
            assert transition(before, after) == after
    for before, after in [("DRAFT", "POSTED"), ("APPROVED", "PAYMENT_CONFIRMED"), ("POSTED", "DRAFT")]:
        with pytest.raises(ValueError):
            transition(before, after)
