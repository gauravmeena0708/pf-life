"""Phase 2, slice 14 on the running stack: the exempted trust's lifecycle (SOPs on surrender and cancellation, Dec 2023).
Demo Steel Works' trust files its annual audited accounts; Demo Textile Mills surrenders its exemption — the RPFC-I
permits compliance as un-exempted, the past accumulations come to EPFO, the agenda goes RO → ZO → HO (EEC, CBT, the
appropriate Government) and the RO notifies it in the gazette; Demo Chemicals gets a show-cause notice, admits and
relinquishes, and is taken over the same way. Repeatable: a proceeding already closed is only checked."""
import secrets
import time
from datetime import date, timedelta

from tests.e2e.test_journey_a_ecr import call, step_up
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

TEXTILE, CHEMICALS, STEEL = "EST-DEMO-0005", "EST-DEMO-0006", "EST-DEMO-0004"


def step(page, proceeding_id, name, **extra):
    status, r = call(page, "POST", f"/api/v1/office/exempted/proceedings/{proceeding_id}/steps",
                     {"step": name, "note": f"e2e {name}", **extra},
                     {"X-Step-Up-Token": step_up(page, "exemption-step", proceeding_id)})
    assert status == 200, (name, r)
    return r["data"]


def decide(page, est, name, **extra):
    status, r = call(page, "POST", f"/api/v1/ho/exemptions/{est}/decisions", {"decision": name, "note": f"e2e {name}", **extra},
                     {"X-Step-Up-Token": step_up(page, "exemption-decision", est)})
    assert status == 200, (name, r)
    return r["data"]


def drive(persona, proceeding, est, effective, on_permit=None):
    """Take the proceeding from whatever stage it is at to CLOSED (an earlier run may have stopped half-way): the RPFC-I's
    permission (SE-5), the RO's agenda → ZO → HO → EEC → CBT → the appropriate Government → its notification → the RO's
    gazette notification under Para 28(5)."""
    cell, zone, ho = persona("ro-exemption", "/office/exempted"), persona("zo-acc", "/"), persona("ho-exemption", "/ho/exempted-rankings")
    pid, stage, est_checked = proceeding["proceeding_id"], proceeding["stage"], False
    while stage != "CLOSED":
        if stage in ("APPLIED", "RELINQUISHED"):
            stage = step(persona("ro-oic", "/"), pid, "PERMIT_UNEXEMPTED", **({"date": effective} if stage == "RELINQUISHED" else {}))["stage"]
            if on_permit:
                on_permit()
        elif stage == "UNEXEMPTED_COMPLIANCE":
            stage = step(cell, pid, "AGENDA_TO_ZO")["stage"]
        elif stage == "AT_ZO":
            if not est_checked:
                assert call(cell, "POST", f"/api/v1/office/exempted/proceedings/{pid}/steps", {"step": "FORWARD_TO_HO", "note": "not mine"},
                            {"X-Step-Up-Token": step_up(cell, "exemption-step", pid)})[0] == 403      # the zone's step
                est_checked = True
            stage = step(zone, pid, "FORWARD_TO_HO")["stage"]
        elif stage in ("AT_HO", "EEC_RECOMMENDED", "CBT_RATIFIED"):
            stage = decide(ho, est, {"AT_HO": "EEC_RECOMMENDED", "EEC_RECOMMENDED": "CBT_RATIFIED", "CBT_RATIFIED": "SENT_TO_GOVERNMENT"}[stage])["stage"]
        elif stage == "SENT_TO_GOVERNMENT":
            stage = decide(ho, est, "GOVERNMENT_NOTIFIED", reference="S.O. 9999(E) (synthetic)", date=effective)["stage"]
        elif stage == "NOTIFIED":
            stage = step(cell, pid, "GAZETTE_NOTIFY", reference="Para 28(5) notification (synthetic)")["stage"]
        else:
            raise AssertionError(f"unexpected stage {stage}")


def latest(page, kind):
    rows = call(page, "GET", "/api/v1/exempted/me/proceedings")[1]["data"]
    rows = rows if isinstance(rows, list) else rows.get("proceedings", [])
    return next((p for p in rows if p["kind"] == kind and p["stage"] not in ("RETURNED", "DROPPED")), None)


def test_annual_audit(persona):
    trust = persona("exempted-trust", "/exempted")
    body = {"financial_year": "2025-26", "auditor_name": "Demo & Co (synthetic)", "auditor_registration": "FRN000000",
            "opening_corpus_paise": 900000000000, "contributions_paise": 75000000000, "interest_credited_paise": 70000000000,
            "claims_paid_paise": 40000000000, "other_paise": -5000000000, "closing_corpus_paise": 1000000000000,
            "opinion": "QUALIFIED", "observations": "Two members' interest credited late"}
    status, r = call(trust, "POST", "/api/v1/exempted/me/audits", body)
    if status == 409:
        status, r = call(trust, "POST", "/api/v1/exempted/me/audits", {**body, "revised": True})
    assert status == 201, r
    assert r["data"]["due_on"] == "2026-09-30"
    assert call(trust, "POST", "/api/v1/exempted/me/audits", {**body, "closing_corpus_paise": 1, "revised": True})[0] == 422
    cell = persona("ro-exemption", "/office/exempted")
    audits = call(cell, "GET", f"/api/v1/office/exempted/{STEEL}/audits")[1]["data"]
    audits = audits if isinstance(audits, list) else audits.get("audits", [])
    assert any(a["financial_year"] == "2025-26" and "QUALIFIED" in str(a.get("needs_attention")) for a in audits), audits


def test_surrender(persona):
    trust = persona("textile-trust", "/exempted")
    proceeding = latest(trust, "SURRENDER")
    cell = persona("ro-exemption", "/office/exempted")

    def past_accumulations():                                             # Para 28: within 30 days of complying as un-exempted
        profile = call(trust, "GET", "/api/v1/exempted/me/profile")[1]["data"]
        assert profile["status"] == "UNEXEMPTED_COMPLIANCE", profile
        content = "uan,account_link_id,employee_rupees,employer_rupees,pension_rupees\n100000000913,AL-0921,180000,60000,0"
        for _ in range(30):                      # contribution-service learns of the permission by an event; wait for it
            status, r = call(cell, "POST", f"/api/v1/office/exempted/{TEXTILE}/past-accumulation-ingestions",
                             {"transfer_reference": f"PA-TEXTILE-{secrets.token_hex(3)}", "content": content},
                             {"X-Step-Up-Token": step_up(cell, "ingest-past-accumulation", TEXTILE, None, 24000000)})
            if status != 409:
                break
            time.sleep(1)
        assert status == 201, r

    if proceeding is None:
        url = "/api/v1/exempted/me/surrender-requests"
        body = {"surrender_date": (date.today() + timedelta(days=5)).isoformat(), "bot_resolution_ref": "BoT/2026/7 (synthetic)",
                "employer_undertaking": True, "employees_consent": True, "corpus_paise": 250000000000, "members": 1}
        assert call(trust, "POST", url, body, {"X-Step-Up-Token": step_up(trust, "surrender-exemption", TEXTILE)})[0] == 422   # < 30 days
        on = (date.today() + timedelta(days=32)).isoformat()
        status, r = call(trust, "POST", url, {**body, "surrender_date": on}, {"X-Step-Up-Token": step_up(trust, "surrender-exemption", TEXTILE)})
        assert status == 201, r
        proceeding = r["data"]
    on = proceeding["surrender_date"]
    drive(persona, proceeding, TEXTILE, on, past_accumulations)
    profile = call(trust, "GET", "/api/v1/exempted/me/profile")[1]["data"]
    assert profile["status"] == "SURRENDERED" and profile["ended_on"] == on


def test_cancellation_with_relinquishment(persona):
    trust = persona("chemicals-trust", "/exempted")
    proceeding = latest(trust, "CANCELLATION")
    if proceeding is None:
        cell = persona("ro-exemption", "/office/exempted")
        status, r = call(cell, "POST", f"/api/v1/office/exempted/{CHEMICALS}/cancellation-proceedings",
                         {"grounds": [{"code": "CONDITION_25", "text": "Losses in three consecutive years (synthetic)"}], "note": "Form CE-1"},
                         {"X-Step-Up-Token": step_up(cell, "show-cause-exemption", CHEMICALS)})
        assert status == 201, r
        proceeding = r["data"]
        assert proceeding["stage"] == "SHOW_CAUSE_ISSUED" and proceeding["reply_due"]
    pid = proceeding["proceeding_id"]
    if proceeding["stage"] == "SHOW_CAUSE_ISSUED":
        assert call(persona("zo-acc", "/"), "POST", f"/api/v1/office/exempted/proceedings/{pid}/steps", {"step": "PERMIT_UNEXEMPTED", "note": "x"},
                    {"X-Step-Up-Token": "x"})[0] == 403                   # only the RPFC-I permits
        status, r = call(trust, "POST", f"/api/v1/exempted/me/proceedings/{pid}/replies",
                         {"reply": "We admit the losses and relinquish the exemption", "relinquish": True},
                         {"X-Step-Up-Token": step_up(trust, "reply-show-cause", pid)})
        assert status == 200, r
        proceeding = r["data"]
        assert proceeding["stage"] == "RELINQUISHED"
    effective = proceeding["history"][0]["at"][:10]                       # the server's date the show-cause was issued
    drive(persona, proceeding, CHEMICALS, effective)                       # taken over at once: a special surrender
    profile = call(trust, "GET", "/api/v1/exempted/me/profile")[1]["data"]
    assert profile["status"] == "CANCELLED" and profile["ended_on"], profile
    status, r = call(trust, "POST", "/api/v1/exempted/me/returns", {"wage_month": date.today().strftime("%Y-%m")})
    assert status in (400, 409, 422), r                                     # no returns once the exemption has ended
