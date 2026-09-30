"""Case-driven UI-only lifecycle checks, including explicit negative and settlement outcomes."""
import re
import io

import pytest
from playwright.sync_api import expect
from PIL import Image

from scripts.lifecycles.catalogue import BY_ID
from tests.ui.claim_lifecycle import ClaimJourney, account_section
from tests.ui.controls import BASE_URL, confirm_dialog, navigate_claims, switch_persona

CASE_LINKS = {
    "CLM-SETTLE-AUTO": ["CLM-SETTLE-AUTO", "CLM-ROUTE-AUTO", "CLM-PAY-NOTICE", "CLM-WITHDRAW-LATE"],
    "CLM-SETTLE-REVIEW": ["CLM-SETTLE-REVIEW", "CLM-DECISION-NODOCKET", "CLM-PAY-NOTICE", "CLM-WITHDRAW-LATE"],
    "CLM-PAY-RETURN-REISSUE": ["CLM-PAY-RETURN-REISSUE", "CLM-PAY-BAD-BANK", "CLM-PAY-NOTICE", "CLM-WITHDRAW-LATE"],
    "CLM-RETURN-RESUBMIT": ["CLM-RETURN-RESUBMIT", "CLM-DECISION-REASON", "CLM-PAY-NOTICE", "CLM-WITHDRAW-LATE"],
    "CLM-OPEN-DUPLICATE": ["CLM-OPEN-DUPLICATE", "CLM-DRAFT-WITHDRAW", "CLM-ID-OTHER-MEMBER"],
}
for identifier in ("CLM-DOC-PNG", "CLM-DOC-JPEG", "CLM-DOC-PDF"):
    CASE_LINKS[identifier] = [identifier, "CLM-DOC-VALID"]
CASE_LINKS["CLM-SETTLE-10C"] = ["CLM-SETTLE-10C", "CLM-ROUTE-SS", "PEN-10C"]


def make_record(recording, case_id, outcome):
    case = BY_ID[case_id]
    return recording(case_id.lower(), case["title"], "Follow one synthetic data case across roles and verify its business outcome.",
                     case["expected"], [case["prerequisite"], "Already running seeded synthetic stack; baseline rules; no concurrent financial runs."],
                     ["Synthetic POC rules and money only; external bank, identity and OTP behavior is simulated.",
                      "This case proves only its captured branch and observations. Other cases remain separately unverified."],
                     lifecycle={"case_ids": CASE_LINKS.get(case_id, [case_id]), "data": case["data"], "expected_outcome": outcome})


@pytest.mark.parametrize("case_id,amount,allowed", [
    ("CLM-INPUT-EMPTY", "", False), ("CLM-INPUT-ZERO", "0", False),
    ("CLM-INPUT-NEGATIVE", "-1", False), ("CLM-INPUT-FRACTION", "1.5", False),
    ("CLM-INPUT-OVER", "over", False), ("CLM-INPUT-MAX", "max", True),
    ("CLM-INPUT-UNSAFE", "9007199254740992", False),
])
def test_amount_validation(ui_pages, recording, case_id, amount, allowed):
    outcome = "INPUT_ACCEPTED" if allowed else "INPUT_BLOCKED"
    record = make_record(recording, case_id, outcome)
    journey = ClaimJourney(ui_pages, record)
    choice = account_section(journey.member).locator("label.claim-type").filter(has_text="Advance for medical treatment")
    choice.get_by_role("radio").check()
    field = journey.member.get_by_label("Amount (whole rupees)", exact=True)
    if amount in {"max", "over"}:
        amount = str(int(field.get_attribute("max")) + (amount == "over"))
    field.fill(amount)
    button = journey.member.get_by_role("button", name="Create claim for review", exact=True)
    check = (lambda: expect(button).to_be_enabled()) if allowed else (lambda: expect(button).to_be_disabled())
    journey.capture(journey.member, "Member", "Validate the entered amount", f"Enter {amount or 'an empty amount'} and inspect Create claim for review.",
                    "Creation is enabled at the exact maximum." if allowed else "Creation is disabled; no business command is submitted.", check,
                    stage="Validation", value=outcome, focus=field)
    record.outcome(outcome, check)


@pytest.mark.parametrize("case_id,persona,account,label,reason", [
    ("CLM-ELIG-EXITED", "member-c", "AL-0006", "Advance for medical treatment", "still employed"),
    ("CLM-ELIG-F19-ACTIVE", "member-a", "AL-0001", "Final settlement after leaving employment", "leave employment"),
    ("CLM-ELIG-F10C-ACTIVE", "member-a", "AL-0001", "Pension withdrawal benefit", "leave employment"),
])
def test_ineligible_claim_type(ui_pages, recording, case_id, persona, account, label, reason):
    record = make_record(recording, case_id, "INELIGIBLE")
    journey = ClaimJourney(ui_pages, record, persona, account)
    choice = account_section(journey.member, account).locator("label.claim-type").filter(has_text=label)
    expect(choice.get_by_role("radio")).to_be_disabled()
    journey.capture(journey.member, "Member", "Read the eligibility explanation", f"Find {label} and read why it is unavailable.",
                    f"The option is disabled and explains {reason}.", lambda: expect(choice).to_contain_text(reason),
                    stage="Eligibility", value="INELIGIBLE", focus=choice)
    record.outcome("INELIGIBLE", lambda: expect(choice.get_by_role("radio")).to_be_disabled())


@pytest.mark.parametrize("case_id,amount,persona,account,label,chain", [
    ("CLM-ROUTE-AO", 100001, "member-a", "AL-0001", "Advance for medical treatment", ["Dealing assistant (accounts)", "Accounts officer"]),
    ("CLM-ROUTE-AO-MAX", 500000, "member-a", "AL-0001", "Advance for medical treatment", ["Dealing assistant (accounts)", "Accounts officer"]),
    ("CLM-ROUTE-APFC", 500001, "member-a", "AL-0001", "Advance for medical treatment", ["Dealing assistant (accounts)", "Section supervisor", "Assistant PF commissioner"]),
    ("CLM-ROUTE-OIC", 2500001, "member-c", "AL-0006", "Final settlement after leaving employment", ["Dealing assistant (accounts)", "Accounts officer", "Officer in charge"]),
])
def test_routing_boundaries(ui_pages, recording, case_id, amount, persona, account, label, chain):
    record = make_record(recording, case_id, "CANCELLED")
    journey = ClaimJourney(ui_pages, record, persona, account)
    try:
        journey.create(amount, label, chain)
        journey.withdraw()
        journey.finish("CANCELLED")
    except Exception:
        record.failure(journey.member, "member")
        raise
    finally:
        journey.cleanup()


@pytest.mark.parametrize("case_id,kind,accepted", [
    ("CLM-DOC-PNG", "png", True), ("CLM-DOC-JPEG", "jpeg", True), ("CLM-DOC-PDF", "pdf", True),
    ("CLM-DOC-MAX", "max", True), ("CLM-DOC-SIZE", "over", False),
    ("CLM-DOC-TYPE", "unsupported", False), ("CLM-DOC-MISMATCH", "mismatch", False),
])
def test_supporting_documents(ui_pages, recording, case_id, kind, accepted):
    record = make_record(recording, case_id, "CANCELLED")
    journey = ClaimJourney(ui_pages, record)
    try:
        journey.create(100001)
        journey.member.goto(BASE_URL + "/member/claims/" + journey.claim_id)
        image = io.BytesIO()
        Image.new("RGB", (32, 24), "white").save(image, format="JPEG" if kind == "jpeg" else "PNG")
        buffer = image.getvalue()
        mime = "image/jpeg" if kind == "jpeg" else "image/png"
        if kind in {"pdf", "mismatch"}:
            # Small self-contained PDF fixture, created via Chromium's native PDF printer.
            fixture = ui_pages()
            fixture.set_content("<html><body><p>Synthetic supporting evidence</p></body></html>")
            buffer = fixture.pdf()
            mime = "application/pdf" if kind == "pdf" else "image/png"
        if kind in {"max", "over"}:
            buffer += b"\0" * ((1_000_000 if kind == "max" else 1_000_001) - len(buffer))
        if kind == "unsupported":
            buffer, mime = b"Synthetic unsupported text evidence", "text/plain"
        name = f"synthetic-{kind}.{'jpg' if kind == 'jpeg' else 'pdf' if kind == 'pdf' else 'txt' if kind == 'unsupported' else 'png'}"
        journey.member.locator("input[type=file]").set_input_files({"name": name, "mimeType": mime, "buffer": buffer})
        errors = {"over": "larger than 1 MB", "unsupported": "content_type", "mismatch": "does not match its type"}
        check = (lambda: expect(journey.member.locator("#claim-actions-heading").locator("..")).to_contain_text(name + " uploaded")) if accepted else (lambda: expect(journey.member.get_by_role("alert").first).to_contain_text(errors[kind]))
        journey.capture(journey.member, "Member", "Check the document upload result", f"Select {name} ({len(buffer):,} bytes) in the supporting document control.",
                        "The uploaded document reference is displayed." if accepted else "The invalid document is refused with an error.",
                        check, stage="Document validation", value=f"{kind}: {'ACCEPTED' if accepted else 'REFUSED'}")
        journey.withdraw()
        journey.finish("CANCELLED")
    except Exception:
        record.failure(journey.member, "member")
        raise
    finally:
        journey.cleanup()


@pytest.mark.parametrize("case_id", ["CLM-PAY-BANKSWITCH"])
def test_verified_bank_switch(ui_pages, recording, case_id):
    record = make_record(recording, case_id, "CANCELLED")
    journey = ClaimJourney(ui_pages, record)
    try:
        journey.create(100001)
        journey.confirm()
        bank = journey.member.locator("#bank-switch-heading").locator("..")
        select = bank.get_by_label(re.compile("^Verified bank account"))
        option = select.locator("option").filter(has_text="4321")
        expect(option).to_have_count(1)
        select.select_option(option.get_attribute("value"))
        bank.get_by_role("button", name="Switch bank with one-time code", exact=True).click()
        confirm_dialog(journey.member, record, "Member")
        journey.capture(journey.member, "Member", "Switch to another verified account", "Select the synthetic verified account ending 4321 and confirm the bank switch.",
                        "The claim's current account is ending 4321 and the bank-change notice is displayed.",
                        lambda: expect(bank).to_contain_text("changed to the verified account ending 4321"), stage="Claim bank", value="Verified account ending 4321")
        expect(bank).to_contain_text("Current account: ending 4321")
        journey.withdraw()
        journey.finish("CANCELLED")
    except Exception:
        record.failure(journey.member, "member")
        raise
    finally:
        journey.cleanup()


@pytest.mark.parametrize("case_id", ["CLM-SETTLE-10C", "CLM-SETTLE-F19"])
def test_full_benefit_settlement(ui_pages, recording, case_id):
    """Dedicated member C cases. These consume once-only EPS/PF fixtures; use a fresh isolated stack."""
    eps = case_id == "CLM-SETTLE-10C"
    record = make_record(recording, case_id, "SETTLED")
    journey = ClaimJourney(ui_pages, record, "member-c", "AL-0006")
    label = "Pension withdrawal benefit" if eps else "Final settlement after leaving employment"
    try:
        choice = account_section(journey.member, "AL-0006").locator("label.claim-type").filter(has_text=label)
        expect(choice.get_by_role("radio")).to_be_enabled()
        choice.get_by_role("radio").check()
        amount = int(journey.member.get_by_label("Amount (whole rupees)", exact=True).get_attribute("max"))
        chain = ["Dealing assistant (accounts)", "Section supervisor"] if eps else ["Dealing assistant (accounts)", "Accounts officer", "Officer in charge"]
        journey.create(amount, label, chain)
        journey.confirm()
        journey.recommend()
        if eps:
            journey.decide("ro-ss")
        else:
            journey.decide("ro-ao", "Recommend to Approve (forward)")
            journey.decide("ro-oic")
        journey.track("APPROVED")
        journey.pay()
        summary = journey.member.locator("#claim-summary-heading").locator("..")
        expect(summary).to_contain_text("PAY-")
        if not eps:
            from tests.ui.claim_lifecycle import currency_paise
            def money(label):
                text = summary.locator("dt").filter(has_text=re.compile("^" + re.escape(label) + "$"))\
                              .locator("xpath=following-sibling::dd[1]").inner_text().split("—", 1)[0].strip()
                return 0 if text == "None" else currency_paise(text)
            gross, tax, net = money("Claim amount"), money("Income tax deducted (TDS)"), money("Paid to your bank")
            assert gross == amount * 100 and gross == tax + net and net > 0
            assert tax == gross // 10, "Baseline member C has short service, verified PAN and 10% illustrative TDS"
            journey.record.manifest["lifecycle"].update(gross_paise=gross, tds_paise=tax, net_paise=net)
            journey.record.save()
        journey.finish("SETTLED", debit=0 if eps else amount * 100, notice=True)
    except Exception:
        record.failure(journey.member, "member")
        for persona, page in journey.officers.items():
            record.failure(page, persona)
        raise
    finally:
        journey.cleanup()


@pytest.mark.parametrize("case_id", ["CLM-SETTLE-AUTO", "CLM-SETTLE-REVIEW", "CLM-PAY-RETURN-REISSUE", "CLM-RETURN-RESUBMIT",
                                      "CLM-REJECT-AO", "CLM-REJECT-APFC", "CLM-STOP-RESTART", "CLM-OPEN-DUPLICATE"])
def test_claim_business_outcome(ui_pages, recording, case_id):
    reject = case_id.startswith("CLM-REJECT")
    cancel = case_id in {"CLM-STOP-RESTART", "CLM-OPEN-DUPLICATE"}
    outcome = "REJECTED_WITH_REASON" if reject else "CANCELLED" if cancel else "SETTLED"
    record = make_record(recording, case_id, outcome)
    journey = ClaimJourney(ui_pages, record)
    amount = 100000 if case_id == "CLM-SETTLE-AUTO" else 500001 if case_id == "CLM-REJECT-APFC" else 100001
    try:
        chain = ["Automatic approval"] if case_id == "CLM-SETTLE-AUTO" else ["Dealing assistant (accounts)", "Section supervisor", "Assistant PF commissioner"] if case_id == "CLM-REJECT-APFC" else ["Dealing assistant (accounts)", "Accounts officer"]
        journey.create(amount, chain=chain)
        if case_id == "CLM-OPEN-DUPLICATE":
            other = ui_pages()
            switch_persona(other, "member-b", "/member", "Your PF at a glance", record, "Other member")
            other.goto(BASE_URL + "/member/claims/" + journey.claim_id)
            expect(other.get_by_role("alert").first).to_contain_text(re.compile("not found", re.I))
            expect(other.locator("#claim-summary-heading")).to_have_count(0)
            journey.capture(other, "Other member", "Confirm claim ownership", "Try to open the run-owned claim from the other member's session.",
                            "The claim is not found and its summary is absent.", lambda: expect(other.locator("#claim-summary-heading")).to_have_count(0),
                            stage="Ownership", value="OTHER_MEMBER_DENIED")
            navigate_claims(journey.member)
            # Returning to the same route keeps React's draft-review state. Refresh the actual
            # page to restore the entry form while leaving the first server-side draft open.
            journey.member.reload()
            choice = account_section(journey.member).locator("label.claim-type").filter(has_text="Advance for medical treatment")
            choice.get_by_role("radio").check()
            journey.member.get_by_label("Amount (whole rupees)", exact=True).fill(str(amount))
            journey.member.get_by_role("button", name="Create claim for review", exact=True).click()
            alert = journey.member.get_by_role("alert").first
            journey.capture(journey.member, "Member", "Refuse a second open claim", "Return to Claim services, refresh the form, and attempt a second medical advance while this run's own draft is open.",
                            "A second claim is refused with an open-claim explanation.", lambda: expect(alert).to_contain_text(re.compile("already|open claim", re.I)),
                            stage="Duplicate protection", value="SECOND_OPEN_CLAIM_REFUSED")
            journey.withdraw()
            journey.finish(outcome)
            return
        journey.confirm("AUTO_APPROVED" if case_id == "CLM-SETTLE-AUTO" else "UNDER_REVIEW")
        if case_id == "CLM-STOP-RESTART":
            da = journey.officer("do-caseworker")
            section = da.locator("#stop-heading").locator("..")
            section.get_by_label("Reason (recorded)", exact=True).fill("Wait for supporting evidence (synthetic lifecycle exercise).")
            section.get_by_role("button", name="Stop claim processing", exact=True).click()
            journey.capture(da, "Initiator — DA Accounts", "Stop processing with a reason", "Record why processing must pause and select Stop claim processing.",
                            "Restart claim is offered and the case is stopped.", lambda: expect(da.get_by_role("button", name="Restart claim", exact=True)).to_be_visible(),
                            stage="Office state", value="STOPPED")
            case_url = da.url
            da.goto(BASE_URL + "/office/work-queue")
            expect(da.get_by_role("row").filter(has=da.get_by_text(journey.claim_id, exact=True))).to_have_count(0)
            da.goto(case_url)
            da.get_by_role("button", name="Restart claim", exact=True).click()
            expect(da.get_by_role("button", name="Stop claim processing", exact=True)).to_be_visible()
            journey.capture(da, "Initiator — DA Accounts", "Restart the claim", "After the prerequisite is satisfied, select Restart claim.",
                            "The current initiator action is restored.", lambda: expect(da.get_by_role("button", name="Generate docket", exact=True)).to_be_visible(),
                            stage="Office state", value="IN_REVIEW")
            journey.withdraw()
            journey.finish(outcome)
            return
        if case_id != "CLM-SETTLE-AUTO":
            journey.recommend(rejection=reject)
            if case_id == "CLM-RETURN-RESUBMIT":
                page = journey.decide(decision="Send back to first level / initiator", required_reason_check=True)
                expect(page.locator(".chain-stepper li[aria-current=step]")).to_contain_text("Dealing assistant")
                journey.recommend()
            if case_id == "CLM-REJECT-APFC":
                journey.decide("ro-ss", "Recommend to Reject (forward)")
                journey.decide("ro-apfc", "Reject", required_reason_check=True)
            else:
                journey.decide(decision="Reject" if reject else "Approve", required_reason_check=reject)
            journey.track(outcome if reject else "APPROVED")
        if reject:
            journey.finish(outcome)
            return
        # The approved state must no longer offer member withdrawal.
        expect(journey.member.get_by_role("button", name="Withdraw this claim", exact=True)).to_have_count(0)
        if case_id == "CLM-PAY-RETURN-REISSUE":
            journey.pay("RETURN")
            member = journey.member
            member.get_by_label("IFSC", exact=True).fill("DEMO0000001")
            member.get_by_label("Account number", exact=True).fill("123456780000")
            member.get_by_role("button", name="Send new bank details", exact=True).click()
            journey.capture(member, "Member", "A failed bank check keeps the returned state", "Enter a synthetic account ending 0000 and send the correction.",
                            "The mock bank check refuses the account and correction is not accepted.",
                            lambda: expect(member.get_by_role("alert").first).to_contain_text("could not confirm"), stage="Bank validation", value="PENNY_DROP_FAILED")
            journey.track("PAYMENT_RETURNED")
            member.get_by_label("Account number", exact=True).fill("123456789012")
            member.get_by_role("button", name="Send new bank details", exact=True).click()
            journey.track("CORRECTION_PENDING")
            apfc = journey.officer("ro-apfc")
            action = apfc.locator("#case-action-heading").locator("..")
            action.get_by_role("radio", name="Approve", exact=True).check()
            action.get_by_label(re.compile("^Reason")).fill("Corrected synthetic bank details accepted for re-payment.")
            journey.capture(apfc, "APFC", "Approve the re-payment", "Check the corrected account and approve re-payment without reopening the claim decision.",
                            "The separate re-payment approval action is available.", lambda: expect(action).to_contain_text("claim decision is not reopened"),
                            stage="Re-payment decision", value="APPROVE", focus=action)
            action.get_by_role("button", name="Submit action", exact=True).click()
            confirm_dialog(apfc, record, "APFC")
            journey.track("REISSUE_APPROVED")
            journey.pay(reissue=True)
            timeline = journey.member.locator(".claim-timeline")
            for label in ["Payment returned", "New bank details under approval", "Re-payment approved", "Settled"]:
                expect(timeline).to_contain_text(label)
            expect(timeline).to_contain_text("attempt 2")
        else:
            journey.pay()
        summary = journey.member.locator("#claim-summary-heading").locator("..")
        expect(summary).to_contain_text("PAY-")
        journey.finish(outcome, debit=amount * 100, notice=True)
    except Exception:
        record.failure(journey.member, "member")
        for persona, page in journey.officers.items():
            record.failure(page, persona)
        raise
    finally:
        journey.cleanup()
