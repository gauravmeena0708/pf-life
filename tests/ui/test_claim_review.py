"""Form 31 through actual screens: submit → recommend → return for correction → withdraw.

The return branch exercises an officer decision without paying or depleting the synthetic ledger.
Only the claim created by this test is withdrawn; no existing claims, grants or balances are reset.
"""
import os
import re

from playwright.sync_api import expect

from tests.ui.controls import confirm_dialog, generate_docket, navigate_claims, open_queue_claim, switch_persona


def test_member_submits_and_officers_return_claim_through_ui(ui_pages, recording):
    amount = os.getenv("UI_CLAIM_AMOUNT", "100001")  # above the baseline auto band; DA → AO
    reviewer = os.getenv("UI_REVIEWER", "ro-ao")
    record = recording(
        "claim-review", "Form 31 claim submission and officer scrutiny",
        "Submit a synthetic medical advance and follow a return-for-correction decision.",
        "Member submission, initiator scrutiny and docket generation, reviewing officer decision, member withdrawal.",
        ["The seeded synthetic stack is running with the illustrative baseline claim approval bands.",
         f"Member A has at least ₹{int(amount):,} eligible employee balance and no open medical advance.",
         "Each officer uses a separate authenticated browser session."],
        ["This run exercises return for correction and withdrawal, not final approval or bank payment.",
         "Form 31 eligibility, amounts, approval bands and one-time codes are illustrative.",
         "The captions describe this POC. They do not establish correspondence with official EPFO screens or rules."],
        lifecycle={"case_ids": ["CLM-RETURN-WITHDRAW"], "data": f"Medical advance ₹{amount}; member A; DA → {reviewer}",
                   "expected_outcome": "CANCELLED"},
    )
    member, initiator, officer = ui_pages(), ui_pages(), ui_pages()
    claim_id = None
    withdrawn = False
    try:
        switch_persona(member, "member-a", "/member/passbook", "My passbook", record, "Member")
        navigate_claims(member)
        choice = member.locator("label.claim-type").filter(has_text="Advance for medical treatment")
        expect(choice).to_have_count(1)
        expect(choice.get_by_role("radio")).to_be_enabled()
        choice.get_by_role("radio").check()
        member.get_by_label("Amount (whole rupees)", exact=True).fill(amount)
        expect(member.get_by_role("button", name="Create claim for review", exact=True)).to_be_enabled()
        record.step(member, "Member", "Choose an eligible medical advance",
                    f"Open Online Services → Claim (Form-31, 19, 10C & 10D). Select Advance for medical treatment and enter ₹{int(amount):,}.",
                    "The eligible option is selected and Create claim for review is available.",
                    lambda: expect(member.get_by_role("button", name="Create claim for review", exact=True)).to_be_enabled(),
                    focus=member.get_by_label("Amount (whole rupees)", exact=True))
        member.get_by_role("button", name="Create claim for review", exact=True).click()
        review = member.locator("#claim-review-heading").locator("..")
        expect(review).to_be_visible()
        claim_id = review.locator("code").first.inner_text()
        expect(review).not_to_contain_text("Automatic approval")
        record.step(member, "Member", "Review the claim before submission",
                    "Select Create claim for review. Check the amount, claim reference, officer chain and rule version.",
                    "Review your claim displays a named officer chain and marks the rules ILLUSTRATIVE.",
                    lambda: expect(review).to_contain_text("ILLUSTRATIVE"), focus=review)
        member.get_by_role("button", name="Confirm with one-time code", exact=True).click()
        confirm_dialog(member, record, "Member")
        expect(member).to_have_url(re.compile(r".*/member/claims/" + re.escape(claim_id) + "$"))
        expect(member.locator(".page-header .state-pill")).to_have_text("Under review", timeout=60_000)
        record.step(member, "Member", "Track the submitted claim",
                    "After confirmation, review the claim status, next step and timeline.",
                    "The claim is Under review and the timeline records the submission.",
                    lambda: expect(member.locator(".page-header .state-pill")).to_have_text("Under review"))

        switch_persona(initiator, "do-caseworker", "/office/work-queue", "Work queue", record, "Initiator — DA Accounts")
        open_queue_claim(initiator, claim_id)
        record.step(initiator, "Initiator — DA Accounts", "Open the assigned claim",
                    "In Work queue, find the member's claim reference and select its case link.",
                    "Case details shows this claim, its approval chain and scrutiny controls.",
                    lambda: expect(initiator.locator("#case-summary-heading").locator("..")).to_contain_text(claim_id))
        generate_docket(initiator, record, "Initiator — DA Accounts")
        action = initiator.locator("#case-action-heading").locator("..")
        for label in ("KYC verified", "Bank account verified", "Balance sufficient", "No open grievance or freeze"):
            action.get_by_role("checkbox", name=label, exact=True).check()
        action.get_by_label("Note", exact=True).fill("Synthetic UI exercise: details checked; forward for review.")
        action.get_by_role("radio", name="Recommend to Approve", exact=True).check()
        record.step(initiator, "Initiator — DA Accounts", "Record scrutiny and recommendation",
                    "Record the completed checks and a note. Select Recommend to Approve and confirm the account status.",
                    "The checks and recommendation are selected and the scrutiny note is entered.",
                    lambda: expect(action.get_by_role("radio", name="Recommend to Approve", exact=True)).to_be_checked(), focus=action)
        action.get_by_role("button", name="Submit action", exact=True).click()
        confirm_dialog(initiator, record, "Initiator — DA Accounts")
        expect(initiator.get_by_text("Action recorded. The case and work queue have been refreshed.", exact=True)).to_be_visible()
        record.step(initiator, "Initiator — DA Accounts", "Forward the claim",
                    "Select Submit action and confirm the recommendation using the demo one-time code.",
                    "Action recorded confirms that the case has advanced from the initiator.",
                    lambda: expect(initiator.get_by_text("Action recorded. The case and work queue have been refreshed.", exact=True)).to_be_visible())

        switch_persona(officer, reviewer, "/office/work-queue", "Work queue", record, "Reviewing officer")
        open_queue_claim(officer, claim_id)
        generate_docket(officer, record, "Reviewing officer")
        action = officer.locator("#case-action-heading").locator("..")
        action.get_by_role("radio", name="Send back to first level / initiator", exact=True).check()
        reason = "Please supply supporting evidence (synthetic UI exercise)."
        # React updates the text node of this wrapped textarea; its label text can include the value.
        reason_field = action.get_by_label(re.compile(r"^Reason"))
        reason_field.fill(reason)
        record.step(officer, "Reviewing officer", "Return the claim with a reason",
                    "Review the docket and action history. Select Send back to first level / initiator and enter the reason.",
                    "The return decision is selected and its mandatory reason is recorded in the form.",
                    lambda: expect(reason_field).to_have_value(reason), focus=action)
        action.get_by_role("button", name="Submit action", exact=True).click()
        confirm_dialog(officer, record, "Reviewing officer")
        expect(officer.get_by_text("Action recorded. The case and work queue have been refreshed.", exact=True)).to_be_visible()
        expect(officer.locator("#case-history-heading").locator("..")).to_contain_text(reason)
        expect(officer.locator(".chain-stepper li[aria-current='step']")).to_contain_text("Dealing assistant")
        record.step(officer, "Reviewing officer", "Verify the recorded decision",
                    "Submit and confirm the decision. Review the action history for the return reason.",
                    "The action history contains the return reason and the case has returned to the initiator.",
                    lambda: expect(officer.locator("#case-history-heading").locator("..")).to_contain_text(reason),
                    focus=officer.locator("#case-history-heading"))

        navigate_claims(member, track=True)
        member.get_by_role("link", name=claim_id, exact=True).click()
        expect(member.get_by_role("button", name="Withdraw this claim", exact=True)).to_be_visible()
        record.step(member, "Member", "Open the tracked claim",
                    "Open Online Services → Track Claim Status and select your claim reference.",
                    "The claim detail remains accessible and withdrawal is available before a final approving decision.",
                    lambda: expect(member.get_by_role("button", name="Withdraw this claim", exact=True)).to_be_visible())
        member.get_by_role("button", name="Withdraw this claim", exact=True).click()
        confirm_dialog(member, record, "Member")
        expect(member.locator(".page-header .state-pill")).to_have_text(re.compile("^cancelled$", re.I), timeout=60_000)
        withdrawn = True
        record.step(member, "Member", "Withdraw before final approval",
                    "Select Withdraw this claim and confirm the action with the demo one-time code.",
                    "The claim is Cancelled. No payment is instructed by this workflow.",
                    lambda: expect(member.locator(".page-header .state-pill")).to_have_text(re.compile("^cancelled$", re.I)))
        record.outcome("CANCELLED", lambda: expect(member.locator(".page-header .state-pill")).to_have_text(re.compile("^cancelled$", re.I)))
    except Exception:
        for label, page in (("member", member), ("initiator", initiator), ("officer", officer)):
            record.failure(page, label)
        raise
    finally:
        # Best-effort UI cleanup of this test's claim on failure. Never touch another claim.
        if claim_id and not withdrawn:
            try:
                member.goto(os.getenv("UI_BASE_URL", "http://localhost:5173").rstrip("/") + f"/member/claims/{claim_id}")
                button = member.get_by_role("button", name="Withdraw this claim", exact=True)
                button.wait_for(timeout=5000)
                button.click()
                confirm_dialog(member)
                expect(member.locator(".page-header .state-pill")).to_have_text(re.compile("^cancelled$", re.I), timeout=30_000)
            except Exception as error:
                print(f"UI cleanup could not withdraw this run's claim {claim_id}: {type(error).__name__}")
