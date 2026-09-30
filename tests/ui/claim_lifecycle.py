"""Visible controls for one owned synthetic claim; no API shortcuts or stack resets."""
import re
import time
from decimal import Decimal

from playwright.sync_api import expect

from tests.ui.controls import BASE_URL, confirm_dialog, generate_docket, navigate_claims, open_queue_claim, switch_persona

LABELS = {"AWAITING_CONFIRMATION": "Awaiting confirmation", "UNDER_REVIEW": "Under review", "RECOMMENDED": "Recommended",
          "APPROVED": "Approved", "AUTO_APPROVED": "Automatically approved", "SETTLED": "Settled",
          "PAYMENT_RETURNED": "Payment returned", "CORRECTION_PENDING": "New bank details under approval",
          "REISSUE_APPROVED": "Re-payment approved", "REJECTED_WITH_REASON": "Rejected with reason", "CANCELLED": "cancelled"}
ROLES = {"do-caseworker": "Initiator — DA Accounts", "ro-ao": "Accounts officer", "ro-ss": "Section supervisor",
         "ro-apfc": "APFC", "ro-oic": "Officer in charge", "ro-cashier": "Cash section"}


def currency_paise(text):
    return int(Decimal(text.replace("₹", "").replace(",", "").strip()) * 100)


def account_section(page, account="AL-0001"):
    return page.locator("section.claim-account").filter(has=page.locator(f"#account-{account}"))


class ClaimJourney:
    def __init__(self, pages, record, persona="member-a", account="AL-0001"):
        self.pages, self.record, self.account = pages, record, account
        self.member = pages()
        self.officers = {}
        self.claim_id = None
        self.done = False
        switch_persona(self.member, persona, "/member/passbook", "My passbook", record, "Member")
        navigate_claims(self.member)
        metrics = account_section(self.member, account).locator(".metrics strong")
        expect(metrics).to_have_count(3)
        self.opening_balance = currency_paise(metrics.nth(2).inner_text())
        self.record.manifest["lifecycle"].update(account=account, opening_balance_paise=self.opening_balance)
        self.record.save()

    def capture(self, page, role, title, instruction, expected, check, stage=None, value=None, focus=None):
        self.record.step(page, role, title, instruction, expected, check, focus=focus)
        if stage:
            self.record.observe(stage, value, check)

    def create(self, amount, claim_label="Advance for medical treatment", chain=None):
        choice = account_section(self.member, self.account).locator("label.claim-type").filter(has_text=claim_label)
        expect(choice).to_have_count(1)
        expect(choice.get_by_role("radio")).to_be_enabled()
        choice.get_by_role("radio").check()
        self.member.get_by_label("Amount (whole rupees)", exact=True).fill(str(amount))
        button = self.member.get_by_role("button", name="Create claim for review", exact=True)
        self.capture(self.member, "Member", "Choose the claim and amount",
                     f"Select {claim_label} against {self.account} and enter ₹{amount:,}.",
                     "The claim is eligible and the entered amount can be reviewed.", lambda: expect(button).to_be_enabled(),
                     stage="Input", value=f"{claim_label}; {amount * 100} paise")
        button.click()
        review = self.member.locator("#claim-review-heading").locator("..")
        expect(review).to_be_visible()
        self.claim_id = review.locator("code").first.inner_text()
        self.record.manifest["lifecycle"].update(claim_id=self.claim_id, amount_paise=amount * 100)
        self.record.save()
        if chain is not None:
            expect(review.locator("ol li")).to_have_text(chain)
        self.capture(self.member, "Member", "Review the routing and reference", "Check the claim reference, amount, route and rule version.",
                     "The route and ILLUSTRATIVE rule version match this case.", lambda: expect(review).to_contain_text("ILLUSTRATIVE"),
                     stage="Routing", value=" → ".join(chain) if chain else review.locator("ol").inner_text(), focus=review)

    def confirm(self, state="UNDER_REVIEW"):
        self.member.get_by_role("button", name="Confirm with one-time code", exact=True).click()
        confirm_dialog(self.member, self.record, "Member")
        self.track(state, "Confirm and follow the claim")

    def track(self, state, title="Track the same claim"):
        if not self.member.url.endswith("/member/claims/" + self.claim_id):
            self.member.goto(BASE_URL + "/member/claims/" + self.claim_id)
        pill = self.member.locator(".page-header .state-pill")
        check = lambda: expect(pill).to_have_text(re.compile("^" + re.escape(LABELS[state]) + "$", re.I), timeout=60_000)
        self.capture(self.member, "Member", title, "Open the claim reference and inspect its current status and timeline.",
                     f"This claim is {LABELS[state]}.", check, stage="Claim state", value=state)
        return self.member

    def officer(self, persona):
        if persona not in self.officers:
            page = self.pages()
            switch_persona(page, persona, "/office/work-queue", "Work queue", self.record, ROLES[persona])
            self.officers[persona] = page
        else:
            page = self.officers[persona]
            page.goto(BASE_URL + "/office/work-queue")
        open_queue_claim(page, self.claim_id)
        return page

    def recommend(self, rejection=False):
        page = self.officer("do-caseworker")
        role = ROLES["do-caseworker"]
        generate_docket(page, self.record, role)
        action = page.locator("#case-action-heading").locator("..")
        for label in ("KYC verified", "Bank account verified", "Balance sufficient", "No open grievance or freeze"):
            action.get_by_role("checkbox", name=label, exact=True).check()
        note = "Synthetic lifecycle exercise: " + ("evidence does not support approval." if rejection else "evidence checked and corrected if required.")
        action.get_by_label("Note", exact=True).fill(note)
        option = "Recommend to Reject" if rejection else "Recommend to Approve"
        radio = action.get_by_role("radio", name=option, exact=True)
        radio.check()
        self.capture(page, role, "Record scrutiny and recommendation", f"Complete the checks, record a note and choose {option}.",
                     f"The recorded recommendation is {option}.", lambda: expect(radio).to_be_checked(), stage="Recommendation", value=option, focus=action)
        action.get_by_role("button", name="Submit action", exact=True).click()
        confirm_dialog(page, self.record, role)
        expect(page.get_by_text("Action recorded. The case and work queue have been refreshed.", exact=True)).to_be_visible()
        self.track("RECOMMENDED")

    def decide(self, persona="ro-ao", decision="Approve", reason="Synthetic lifecycle exercise: decision evidence checked.", required_reason_check=False):
        page = self.officer(persona)
        role = ROLES[persona]
        generate_docket(page, self.record, role)
        action = page.locator("#case-action-heading").locator("..")
        radio = action.get_by_role("radio", name=decision, exact=True)
        radio.check()
        field = action.get_by_label(re.compile(r"^Reason"))
        if required_reason_check:
            expect(field).to_have_attribute("required", "")
            expect(field).to_have_value("")
            self.capture(page, role, "A reason is required", "Choose return or rejection and inspect the empty mandatory reason field.",
                         "The form requires a reason before the decision can be submitted.",
                         lambda: expect(field).to_have_attribute("required", ""), stage="Validation", value="Reason is mandatory", focus=action)
        field.fill(reason)
        self.capture(page, role, "Record the officer decision", f"Select {decision}, record the reason, and review the claim docket.",
                     "The selected action and reason are ready for confirmation.", lambda: expect(radio).to_be_checked(), stage="Decision", value=f"{role}: {decision}", focus=action)
        action.get_by_role("button", name="Submit action", exact=True).click()
        confirm_dialog(page, self.record, role)
        expect(page.get_by_text("Action recorded. The case and work queue have been refreshed.", exact=True)).to_be_visible()
        expect(page.locator("#case-history-heading").locator("..")).to_contain_text(reason)
        return page

    def pay(self, scenario="SUCCESS", reissue=False):
        page = self.officer("ro-cashier")
        action = page.locator("#case-action-heading").locator("..")
        expect(action).to_contain_text("No funds move")
        scenario_field = action.get_by_label(re.compile("^Demo payment scenario"))
        scenario_field.select_option(scenario)
        self.capture(page, "Cash section", "Reissue payment" if reissue else "Instruct payment",
                     f"Check the owned claim reference and select the {'bank-return' if scenario == 'RETURN' else 'successful-payment'} simulation.",
                     "The action explicitly identifies the bank simulation; no real funds move.",
                     lambda: expect(scenario_field).to_have_value(scenario),
                     stage="Bank simulation", value=scenario, focus=action)
        action.get_by_role("button", name="Submit action", exact=True).click()
        confirm_dialog(page, self.record, "Cash section")
        expect(page.get_by_text("Action recorded. The case and work queue have been refreshed.", exact=True)).to_be_visible()
        self.track("SETTLED" if scenario == "SUCCESS" else "PAYMENT_RETURNED")

    def withdraw(self):
        self.member.goto(BASE_URL + "/member/claims/" + self.claim_id)
        self.member.get_by_role("button", name="Withdraw this claim", exact=True).click()
        confirm_dialog(self.member, self.record, "Member")
        self.track("CANCELLED", "Withdraw the owned claim")
        self.done = True

    def balance(self, expected):
        navigate_claims(self.member)
        metrics = account_section(self.member, self.account).locator(".metrics strong")
        # The UI's ledger projection is asynchronous. Reload the visible page until it converges.
        end = time.monotonic() + 40
        while True:
            expect(metrics).to_have_count(3)
            actual = currency_paise(metrics.nth(2).inner_text())
            if actual == expected or time.monotonic() >= end:
                break
            self.member.wait_for_timeout(500)
            self.member.reload()
        assert actual == expected, f"Expected total balance {expected} paise, observed {actual}; concurrent money changes invalidate this run"
        def check_balance():
            assert currency_paise(metrics.nth(2).inner_text()) == expected
        self.capture(self.member, "Member", "Verify the ledger balance", "Open Claim services and compare the displayed account balance with the opening balance.",
                     f"The visible account total is {expected} paise.",
                     check_balance,
                     stage="Balance", value=f"Opening {self.opening_balance}; observed {actual}; change {actual - self.opening_balance} paise")
        # The numerical assertion above is the monetary check; it is not inferred from claim status.
        self.record.manifest["lifecycle"]["closing_balance_paise"] = actual
        self.record.save()

    def notification(self):
        self.member.goto(BASE_URL + "/member/profile")
        notice = self.member.locator(".notice-list li").filter(has_text=self.claim_id).filter(has_text="paid")
        expect(notice.first).to_be_visible(timeout=60_000)
        self.capture(self.member, "Member", "Verify the settlement notice", "Open Profile & notices and locate the notice for the same claim reference.",
                     "The member notice confirms this claim's paid outcome.", lambda: expect(notice.first).to_be_visible(),
                     stage="Notification", value=f"Settlement notice for {self.claim_id}", focus=notice.first)

    def finish(self, outcome, debit=0, notice=False):
        self.done = True
        self.balance(self.opening_balance - debit)
        if notice:
            self.notification()
        self.track(outcome, "Verify the final business outcome")
        self.record.outcome(outcome, lambda: expect(self.member.locator(".page-header .state-pill")).to_have_text(
            re.compile("^" + re.escape(LABELS[outcome]) + "$", re.I)))

    def cleanup(self):
        if self.claim_id and not self.done:
            try:
                self.member.goto(BASE_URL + "/member/claims/" + self.claim_id)
                button = self.member.get_by_role("button", name="Withdraw this claim", exact=True)
                button.wait_for(timeout=3000)
                button.click()
                confirm_dialog(self.member)
                expect(self.member.locator(".page-header .state-pill")).to_have_text(re.compile("cancelled", re.I))
            except Exception:
                print(f"Cleanup could not withdraw this run's claim {self.claim_id}; inspect retained evidence. No other claim was touched.")
