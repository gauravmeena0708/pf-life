"""Versioned policy: checks before publishing, rules in force by date, exact version lookup."""
import asyncio
import copy
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from epfo_persistence.policy import (approval_chain, auto_settle_limit, baseline, on_policy_published, policy_metadata,
                                     rules_by_version, rules_on, validate)


def test_baseline_is_valid():
    assert validate(baseline()) == []


@pytest.mark.parametrize("change, message", [
    (lambda d: d["contribution"].update(eps_wage_ceiling_paise=2500050), "whole rupees"),
    (lambda d: d["contribution"].update(eps_rate_bp=1500), "cannot exceed"),
    (lambda d: d["claims"]["approval_bands"][-1].update(upto_paise=999), "no upper limit"),
    (lambda d: d["claims"]["approval_bands"][1].update(upto_paise=10), "must increase"),
    (lambda d: d["claims"]["approval_bands"][0].update(chain=["fo.ss", "fo.ao"]), "start with fo.da_accounts"),
    (lambda d: d["claims"]["approval_bands"][0].update(chain=["fo.da_accounts"]), "at least one approver"),
    (lambda d: d["claims"]["approval_bands"][2].update(chain=["fo.da_accounts", "fo.ss", "fo.cash"]), "fo.apfc or fo.oic"),
    (lambda d: d["claims"]["types"]["ADVANCE_ILLNESS"].update(max_from="salary"), "max_from"),
    (lambda d: d["claims"]["types"]["ADVANCE_ILLNESS"].update(requires_exit_months=2), "both current employment"),
    (lambda d: d["claims"]["types"]["ADVANCE_ILLNESS"].update(approve_everything=True), "unknown fields"),
    (lambda d: [t.update(retired=True) for t in d["claims"]["types"].values()], "stay open"),
    (lambda d: d["grievances"].update(sla_days={"RO": 15}), "RO, ZO and HO"),
])
def test_invalid_documents_are_explained(change, message):
    doc = copy.deepcopy(baseline())
    change(doc)
    assert any(message in p for p in validate(doc)), validate(doc)


def test_per_type_chain_and_auto_limit_override_the_defaults():
    doc = copy.deepcopy(baseline())
    t = doc["claims"]["types"]["FINAL_SETTLEMENT"]
    t["auto_settle_up_to_paise"] = None
    t["approval_bands"] = [{"upto_paise": None, "chain": ["fo.da_accounts", "fo.ao", "fo.apfc"]}]
    assert auto_settle_limit(doc, "FINAL_SETTLEMENT") is None
    assert approval_chain(doc, "FINAL_SETTLEMENT", 100) == ["fo.da_accounts", "fo.ao", "fo.apfc"]
    assert approval_chain(doc, "ADVANCE_ILLNESS", 100) == ["fo.da_accounts", "fo.ss"]
    assert validate(doc) == []


def test_rules_in_force_by_date_and_by_version(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/p.db")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    raised = copy.deepcopy(baseline())
    raised.update(rule_version="demo-rules-2026.2", effective_from="2026-10-01")
    raised["contribution"]["eps_wage_ceiling_paise"] = 2500000

    async def run():
        async with engine.begin() as c:
            await c.run_sync(policy_metadata.create_all)
        async with sessions() as s:
            assert (await rules_on(s, date(2026, 11, 1)))["rule_version"] == "demo-rules-2026.1"   # nothing published yet
        event = {"payload": {"rule_version": "demo-rules-2026.2", "effective_from": "2026-10-01", "document": raised}}
        async with sessions() as s, s.begin():
            await on_policy_published(s, event)
            await on_policy_published(s, event)                                                    # idempotent
        async with sessions() as s:
            september = await rules_on(s, date(2026, 9, 1))
            october = await rules_on(s, date(2026, 10, 1))
            exact = await rules_by_version(s, "demo-rules-2026.1")
        await engine.dispose()
        return september, october, exact
    september, october, exact = asyncio.run(run())
    assert september["contribution"]["eps_wage_ceiling_paise"] == 1500000       # the old rule for old months
    assert october["contribution"]["eps_wage_ceiling_paise"] == 2500000
    assert exact["rule_version"] == "demo-rules-2026.1"


def test_primary_member_id_is_the_latest_joined_with_contributions():
    from epfo_persistence.member_ids import primary_member_id
    ids = [{"account_link_id": "AL-1", "date_of_joining": "2019-04-01", "last_contribution_month": "2025-12", "transferred_to": None},
           {"account_link_id": "AL-2", "date_of_joining": "2026-01-15", "last_contribution_month": "2026-08", "transferred_to": None},
           {"account_link_id": "AL-3", "date_of_joining": "2026-09-01", "last_contribution_month": None, "transferred_to": None}]
    assert primary_member_id(ids) == "AL-2"                         # AL-3 has no contribution yet
    assert primary_member_id([{**ids[2]}]) == "AL-3"                 # nothing contributed anywhere: latest joined
    assert primary_member_id([{**ids[1], "transferred_to": "AL-9"}, ids[0]]) == "AL-1"
    assert primary_member_id([]) is None


def test_the_25000_ceiling_from_17_september_2026_splits_that_month_by_days(tmp_path):
    """P2.26: S.O. 5109(E) — ₹25,000 from 17 Sep 2026. September is one return, at ₹15,000 for 16 days and ₹25,000 for 14."""
    from epfo_persistence.policy import capped_wages, revisions, rules_for_wage_month, validate
    [revision] = revisions()
    doc = revision["document"]
    assert doc["rule_version"] == "demo-rules-2026.2" and doc["effective_from"] == "2026-09-17" and not validate(doc)
    assert doc["contribution"]["eps_wage_ceiling_paise"] == doc["contribution"]["edli_wage_ceiling_paise"] == 2500000
    assert doc["claims"] == baseline()["claims"] and "revisions" not in baseline()          # the rest carried over
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/p.db")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def run():
        async with engine.begin() as c:
            await c.run_sync(policy_metadata.create_all)
        async with sessions() as s, s.begin():
            await on_policy_published(s, {"payload": {"rule_version": doc["rule_version"], "effective_from": doc["effective_from"], "document": doc}})
        async with sessions() as s:
            out = [await rules_for_wage_month(s, m) for m in ("2026-08", "2026-09", "2026-10")]
        await engine.dispose()
        return out
    august, september, october = asyncio.run(run())
    assert august["contribution"]["eps_wage_ceiling_paise"] == 1500000 and "ceiling_periods" not in august["contribution"]
    assert october["contribution"]["eps_wage_ceiling_paise"] == 2500000 and "ceiling_periods" not in october["contribution"]
    c = september["contribution"]
    assert [(p["days"], p["eps_wage_ceiling_paise"]) for p in c["ceiling_periods"]] == [(16, 1500000), (14, 2500000)]
    assert c["eps_wage_ceiling_paise"] == 1966700                      # 15,000 x 16/30 + 25,000 x 14/30, rounded up
    assert capped_wages(2000000, c) == 1733400                         # the FAQ's ₹17,333.33 for wages of ₹20,000
    assert capped_wages(1200000, c) == 1200000                         # under both ceilings: the wages
    assert capped_wages(2000000, october["contribution"]) == 2000000
