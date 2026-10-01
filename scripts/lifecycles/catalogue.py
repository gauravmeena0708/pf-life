"""Finite, explicit case inventory. A specification or existing test file is not a passing result.

Amounts and dates describe synthetic baseline examples, never statutory EPFO requirements.
Further policy types can be added without treating this inventory as exhaustive for real EPFO.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def group(family, category, source, rows):
    return [dict(case_id=identifier, family=family, category=category, title=title,
                 data=data, expected=expected, reference=source,
                 prerequisite=prerequisite, integration=integration)
            for identifier, title, data, expected, prerequisite, integration in rows]


CASES = []
CASES += group("Claims", "Input validation", "apps/web/src/features/member/ClaimsPage.tsx", [
    ("CLM-INPUT-EMPTY", "Missing amount", "Amount empty", "Create claim remains disabled; no claim created", "Eligible member A", "working POC"),
    ("CLM-INPUT-ZERO", "Zero amount", "₹0", "Create claim remains disabled; no claim created", "Eligible member A", "working POC"),
    ("CLM-INPUT-NEGATIVE", "Negative amount", "₹-1", "Create claim remains disabled; no claim created", "Eligible member A", "working POC"),
    ("CLM-INPUT-FRACTION", "Fractional rupees", "₹1.5", "Whole-rupee restriction blocks creation", "Eligible member A", "working POC"),
    ("CLM-INPUT-OVER", "Above eligible maximum", "Displayed maximum + ₹1", "Create claim disabled and limit explanation visible", "Eligible member A", "working POC"),
    ("CLM-INPUT-MAX", "Exact eligible maximum", "Displayed maximum", "Creation enabled at the maximum", "Eligible member A with balance", "working POC"),
    ("CLM-INPUT-UNSAFE", "Unsafe integer amount", "₹9007199254740992", "Creation disabled; no rounded monetary command", "Eligible member A", "working POC"),
])
CASES += group("Claims", "Eligibility and identity", "services/claim-service/app/domain/claims.py", [
    ("CLM-ELIG-ACTIVE", "Medical advance while employed", "Active member; positive employee balance", "Medical advance eligible", "Member A", "working POC"),
    ("CLM-ELIG-EXITED", "Medical advance after exit", "Exited member C", "Medical advance disabled; active-employment reason", "Member C has recorded exit", "working POC"),
    ("CLM-ELIG-F19-ACTIVE", "Final settlement before exit", "Active member A; Form 19", "Final settlement disabled; exit reason", "Member A", "working POC"),
    ("CLM-ELIG-F10C-ACTIVE", "Pension withdrawal before exit", "Active member A; Form 10C", "Pension withdrawal disabled; exit reason", "Baseline Form 10C published", "working POC"),
    ("CLM-ELIG-NOBALANCE", "Zero available balance", "Employee and employer balances zero", "No-balance reason; no claim accepted", "Dedicated empty account", "working POC"),
    ("CLM-ELIG-EXIT-BEFORE", "Exit waiting period below boundary", "Exit one day short of two complete months", "Final settlement refused", "Date-controlled fixture", "working POC"),
    ("CLM-ELIG-EXIT-EXACT", "Exit waiting period at boundary", "Exit exactly two complete months ago", "Final settlement eligible if other checks pass", "Date-controlled fixture", "working POC"),
    ("CLM-ELIG-RETIRED", "Retired policy claim type", "Published retired=true", "Type no longer offered for new claims", "Isolated policy fixture", "working POC"),
    ("CLM-ELIG-COOLDOWN", "Repeat benefit before cooldown", "Previously paid Form 10C within configured interval", "Repeat benefit refused with reason", "Prior paid benefit fixture", "working POC"),
    ("CLM-ELIG-SERVICE-MIN", "Minimum service below/at boundary", "5 versus 6 months for Table D", "Below minimum refused; eligible boundary uses configured Table D", "Date-controlled EPS fixture", "working POC"),
    ("CLM-ELIG-SERVICE-MAX", "Maximum EPS service boundary", "113 versus 114 complete months", "Withdrawal allowed below cutoff; pension/certificate explanation beyond", "Date-controlled EPS fixture", "working POC"),
])
CASES += group("Claims", "Account ownership and readiness", "services/claim-service/app/api/routes.py", [
    ("CLM-ID-SECONDARY", "Secondary member ID", "Claim against non-primary account", "Refused with primary member ID explanation", "Member with multiple account links", "working POC"),
    ("CLM-ID-UNTRANSFERRED", "Whole-balance claim with untransferred services", "Form 19/10C with older account balance", "Refused until all services transferred", "Member B linked Aadhaar set", "working POC"),
    ("CLM-ID-OTHER-MEMBER", "Another member's claim", "Member B opens member A claim URL", "Not found; no claim details disclosed", "New claim owned by this run", "working POC"),
    ("CLM-ID-NONMEMBER", "Non-member submits claim", "Employer/office identity on member endpoint", "Permission denied", "Existing must-deny suite", "working POC"),
    ("CLM-ID-KYC-EMPLOYER", "Unverified Aadhaar needs employer attestation", "Member F; no verified Aadhaar", "Waits for employer before office scrutiny", "Member F with eligible balance", "mock identity verification"),
    ("CLM-ID-EMPLOYER-REJECT", "Employer declines attestation", "Pending attestation; reason recorded", "Rejected by employer; reason visible; no payment", "Designated employer claim", "working POC"),
    ("CLM-ID-EMPLOYER-ATTEST", "Employer attests claim", "Pending attestation; authorised signatory", "Office queue receives same claim", "Designated employer claim", "mock signature"),
])
CASES += group("Claims", "Routing boundaries", "config/demo-rules.yaml", [
    ("CLM-ROUTE-AUTO", "Automatic limit inclusive", "Medical advance ₹1,00,000", "Automatic approval shown at inclusive baseline limit", "Member A without risk/freeze", "mock bank at payment"),
    ("CLM-ROUTE-AO", "Just above automatic limit", "Medical advance ₹1,00,001", "DA Accounts → Accounts officer", "Member A; baseline policy", "working POC"),
    ("CLM-ROUTE-AO-MAX", "Accounts officer band inclusive", "Medical advance ₹5,00,000", "DA Accounts → Accounts officer", "Member A; baseline policy", "working POC"),
    ("CLM-ROUTE-APFC", "Above accounts officer band", "Medical advance ₹5,00,001", "DA Accounts → Section supervisor → APFC", "Member A; baseline policy", "working POC"),
    ("CLM-ROUTE-OIC", "Above APFC amount band", "Form 19 ₹25,00,001", "DA Accounts → Accounts officer → OIC", "Member C with sufficient balance", "working POC"),
    ("CLM-ROUTE-SS", "Always-reviewed small Form 10C", "Table D amount ≤ ₹50,000", "DA Accounts → Section supervisor even below auto limit", "Eligible EPS fixture; baseline policy", "working POC"),
    ("CLM-ROUTE-RISK", "Risk signal overrides automatic route", "Small claim with open risk signal", "Officer review; signal does not itself reject", "Isolated security fixture", "working POC"),
    ("CLM-ROUTE-DEFREEZE", "Stricter route after de-freeze", "Previously approved claim frozen then released", "Old approval voided; configured stricter chain restarts", "Isolated freeze fixture", "working POC"),
])
CASES += group("Claims", "Decisions and interruption", "tests/e2e/test_cites_claim_rules.py", [
    ("CLM-DRAFT-WITHDRAW", "Withdraw unconfirmed draft", "Create for review, do not confirm", "Cancelled; balance unchanged", "Member A; own new claim", "working POC"),
    ("CLM-OPEN-DUPLICATE", "Second open claim of same type", "Own draft still open; attempt second medical advance", "Second creation refused; original remains identifiable", "Own draft only", "working POC"),
    ("CLM-STOP-RESTART", "Stop, restart and withdraw", "DA stops with reason, restarts, member withdraws", "Stopped claim leaves active queue; restart restores it; cancelled", "Own reviewed claim; DA role", "working POC"),
    ("CLM-RETURN-WITHDRAW", "Return then member withdrawal", "DA recommends; AO returns with reason", "Case returns to initiator; member cancels; no debit", "Member A; DA and AO", "working POC"),
    ("CLM-RETURN-RESUBMIT", "Return, correct and complete", "DA recommendation → AO return → fresh DA recommendation → approval", "New scrutiny round and dockets; final settlement", "Own new claim; DA/AO/cash", "mock bank"),
    ("CLM-REJECT-AO", "Final rejection on two-level chain", "DA recommends rejection; AO rejects with reason", "Rejected with reason; balance unchanged", "Own new ₹1,00,001 claim", "working POC"),
    ("CLM-REJECT-APFC", "Final rejection on three-level chain", "DA recommends rejection; SS forwards; APFC rejects", "Only final level rejects; no payment/debit", "Own new ₹5,00,001 claim", "working POC"),
    ("CLM-REJECT-INTERMEDIATE", "Intermediate negative view returns to DA", "DA recommends approval; SS recommends rejection", "Returns to initiator rather than final rejection", "Three-level chain fixture", "working POC"),
    ("CLM-DECISION-REASON", "Missing rejection/return reason", "Final decision without reason", "Form or service refuses decision", "Own reviewed claim", "working POC"),
    ("CLM-DECISION-NODOCKET", "Act before own docket exists", "Current officer has not generated CAD", "Submit action disabled", "Every new scrutiny level", "working POC"),
    ("CLM-DECISION-WRONGTURN", "Officer acts out of turn", "Later-level role opens case before handoff", "Action controls unavailable; server denies mutation", "Existing must-deny suite", "working POC"),
    ("CLM-DECISION-MAKER", "Maker tries to approve own recommendation", "Same officer identity on both stages", "Separation of duties enforced", "Isolated role/grant fixture", "working POC"),
    ("CLM-WITHDRAW-LATE", "Withdraw after approving decision", "Approved/paid claim", "Withdrawal unavailable; server refuses", "Own successfully approved claim", "working POC"),
    ("CLM-FROZEN-NEW", "Create/confirm/pay frozen account", "Frozen account at each action", "All affected commands blocked", "Isolated freeze fixture", "working POC"),
])
CASES += group("Claims", "Settlement and bank outcomes", "tests/e2e/test_journey_b_claim.py", [
    ("CLM-SETTLE-AUTO", "Automatic claim to settlement", "Small confirmed medical advance; cash SUCCESS", "Settled; exactly one amount deducted; member notice", "Member A; cash role", "mock bank"),
    ("CLM-SETTLE-REVIEW", "Two-level approval to settlement", "₹1,00,001; DA → AO; cash SUCCESS", "Same claim settled; one debit; payment ID and notice", "Member A; DA/AO/cash", "mock bank"),
    ("CLM-SETTLE-F19", "Form 19 whole-balance settlement", "Member C; entire displayed eligible PF balance", "Applicable chain approves; gross PF balance deducted; tax and net reconcile", "Dedicated member C fixture; consumes its PF balance", "mock bank and illustrative TDS"),
    ("CLM-SETTLE-10C", "Form 10C full Table D benefit", "Member C; entire displayed eligible EPS benefit", "DA and applicable approver; settled from EPS without PF balance deduction", "Dedicated member C fixture; once-per-account benefit", "mock bank and illustrative Table D"),
    ("CLM-PAY-RETURN-REISSUE", "Bank return through correction and reissue", "RETURN → new account → APFC approval → SUCCESS", "Settled; full return/correction/reissue timeline; one net debit", "Member A; DA/AO/APFC/cash", "mock bank and penny-drop"),
    ("CLM-PAY-BAD-BANK", "Penny-drop failure after bank return", "Correction account ends 0000", "Correction refused; claim remains payment returned", "Own returned claim", "mock penny-drop"),
    ("CLM-PAY-BAD-IFSC", "Malformed correction bank details", "Invalid IFSC or account length", "Form/server refuses invalid details", "Own returned claim", "working POC"),
    ("CLM-PAY-REISSUE-REJECT", "APFC refuses corrected bank details", "Redisbursement REJECT with note", "Returns to member correction stage; no second payment", "Own returned claim", "mock bank"),
    ("CLM-PAY-DUPLICATE", "Duplicate payment command/callback", "Repeated idempotency key and signed callback", "One payment, one journal effect", "Existing backend idempotency fixture", "mock bank"),
    ("CLM-PAY-NODEBIT", "Pay before ledger debit posted", "Approved claim; delayed contribution consumer", "Refused until debit exists", "Isolated asynchronous fixture", "mock bank"),
    ("CLM-PAY-SCROLL", "Batch scroll and reconciliation", "Several approved designated claims", "All and only included claims paid; total/reconciliation agrees", "Isolated office queue; no unrelated claims", "mock bank"),
    ("CLM-PAY-NOTICE", "Settlement notification", "Settled own claim reference", "Member notification references same claim and paid outcome", "Successful settlement scenario", "working POC"),
    ("CLM-PAY-BANKSWITCH", "Switch verified bank before payment", "Alternative verified account; current claim version", "Account switch recorded; payment uses selected account", "Member A second bank account", "mock KYC"),
    ("CLM-PAY-LATEBANKSWITCH", "Bank switch after payment sent", "Payment pending/settled", "Switch form unavailable; backend refuses", "Own paid claim", "working POC"),
])
CASES += group("Claims", "Documents, tax and policy", "services/claim-service/tests/test_lifecycle.py", [
    ("CLM-DOC-VALID", "Supporting document upload", "Allowed PDF/JPEG/PNG ≤1 MB", "Document attached to same claim", "Own claim before terminal decision", "working POC"),
    ("CLM-DOC-SIZE", "Oversized supporting document", "Document larger than 1 MB", "Upload refused with explanation", "Own claim", "working POC"),
    ("CLM-DOC-TYPE", "Unsupported document", "Disallowed MIME/file type", "Upload refused", "Own claim", "working POC"),
    ("CLM-DOC-PNG", "PNG supporting document", "Valid PNG", "Document attached to same claim", "Own draft; upload control", "working POC"),
    ("CLM-DOC-JPEG", "JPEG supporting document", "Valid JPEG", "Document attached to same claim", "Own draft; upload control", "working POC"),
    ("CLM-DOC-PDF", "PDF supporting document", "Valid PDF", "Document attached to same claim", "Own draft; upload control", "working POC"),
    ("CLM-DOC-MAX", "Document at size limit", "1,000,000 bytes with valid PNG signature", "Upload accepted at inclusive size limit", "Own draft; synthetic boundary payload", "working POC"),
    ("CLM-DOC-MISMATCH", "File content and MIME disagree", "PDF bytes declared as image/png", "Content/type mismatch refused", "Own draft", "working POC"),
    ("CLM-TAX-BELOW", "Below TDS threshold", "Final settlement just below configured threshold", "No TDS; gross equals net", "Short-service fixture; payment policy", "illustrative tax rules"),
    ("CLM-TAX-PAN", "TDS with verified PAN", "Final settlement at threshold; short service; verified PAN", "Configured PAN rate; gross = tax + net", "Dedicated final-settlement fixture", "illustrative tax rules"),
    ("CLM-TAX-NOPAN", "TDS without verified PAN", "Final settlement; short service; no PAN", "Configured no-PAN rate; gross = tax + net", "Dedicated final-settlement fixture", "illustrative tax rules"),
    ("CLM-TAX-SERVICE", "TDS service exemption boundary", "59 versus 60 complete months", "Exemption starts at configured service boundary", "Date-controlled tax fixture", "illustrative tax rules"),
    ("CLM-TAX-DECLARATION", "Form 15G/15H waiver", "Declaration in payment financial year", "Waiver applied when enabled; recorded basis", "Dedicated tax declaration fixture", "illustrative tax rules"),
    ("CLM-POLICY-FUTURE", "Future policy does not apply early", "Published future effective date", "Current policy remains applied before effective date", "Isolated policy fixture", "working POC"),
    ("CLM-POLICY-PAYDATE", "Payment policy differs from claim policy", "Publish tax change after claim before payment", "Claim snapshot preserved; payment tax uses payment-date policy", "Isolated policy fixture", "illustrative tax rules"),
])

# These are connected lifecycle specifications, not a claim that their UI manuals exist. Each row names the test
# that exercises it (an end-to-end journey where one exists, otherwise the owning service's unit test); the
# family's reference is used only when a row names none.
OTHER_FAMILIES = [
    ("Enrollment", "tests/e2e/test_registration_kyc.py", [
        ("ENR-NEW", "New UAN registration", "New employee and Form 11", "Member ID appears in employer list and member ledger"),
        ("ENR-EXISTING", "Existing UAN, new employment", "Existing UAN at new establishment", "New member ID linked without duplicate identity",
         "services/member-service/tests/test_onboarding.py"),
        ("ENR-BULK", "Mixed bulk registration", "Valid, duplicate and malformed rows", "Valid outcomes and per-row errors reconciled",
         "services/member-service/tests/test_onboarding.py"),
        ("ENR-KYC", "KYC through signatory approval", "Verified, pending and rejected bank/PAN", "Readiness updated only after verification and authorised approval"),
        ("ENR-UAN-LOOKUP", "Know your UAN", "Name, date of birth, mobile last digits; mock OTP", "Matching UAN found; wrong code refused", "tests/e2e/test_member_mobility.py"),
        ("ENR-NOMINATION", "e-Nomination (Form 2)", "Family and minor nominees; shares; unverified Aadhaar", "Signed nomination replaces the last; invalid shares, non-family or unverified Aadhaar refused",
         "tests/e2e/test_member_mobility.py"),
        ("ENR-LOCATION", "Member location mapping", "Serving and exited member IDs", "Branch mapped for a serving member; exited refused",
         "tests/e2e/test_oversight_administration.py"),
        ("ENR-MEMBER-HOME", "Member home and phone layout", "Missing PAN; no nomination; phone width 360px",
         "Savings, pending, nudges and life events shown; every member page fits a phone; menu behind one button",
         "tests/e2e/test_member_home.py"),
    ]),
    ("Contributions", "tests/e2e/test_journey_a_ecr.py", [
        ("ECR-PAID", "ECR to member credit", "Valid monthly return", "TRRN paid, journal posted, member shares/passbook credited"),
        ("ECR-INVALID", "Return validation", "Invalid UAN, wages and totals", "Errors prevent submission; no challan/debit",
         "services/contribution-service/tests/test_ecr_api.py"),
        ("ECR-PENDING", "Submitted but unpaid", "Filed ECR, unpaid challan", "Pending contribution displayed; no false posted credit"),
        ("ECR-MAKER", "Preparer cannot approve own return", "Same maker attempts checker action", "Denied; independent signatory required",
         "services/contribution-service/tests/test_ecr_api.py"),
        ("ECR-DUPLICATE", "Repeated submission", "Same approved filing/idempotency key", "Same TRRN; no duplicate contribution"),
        ("ECR-LATE", "Late payment demands", "Late month payment; 14B/7Q", "Demands raised and subsequent demand payment reconciled",
         "tests/e2e/test_returns_and_demands.py"),
        ("ECR-STUCK", "Stuck bank payment", "Bank STUCK outcome", "Reject stuck payment and controlled retry",
         "services/contribution-service/tests/test_returns.py"),
        ("ECR-SUPPLEMENT", "Arrear and supplementary return", "Same month; eligible supplementary lines", "Additional amounts posted without duplicating original return",
         "tests/e2e/test_returns_and_demands.py"),
        ("ECR-INTEREST-RATE", "Approved interest rate recorded", "CBT recommendation and Ministry concurrence", "Draft rule set prepared; crediting only from the published rule set",
         "tests/e2e/test_public_services.py"),
    ]),
    ("Mobility", "tests/e2e/test_exit_transfer.py", [
        ("MOB-EXIT", "Member records date of exit", "Left job; exit missing", "Exit accepted with conditions; service history updated"),
        ("MOB-EMPLOYER-EXIT", "Employer exit maker/checker", "Operator marks; signatory approves/rejects", "Exit changes only after approval"),
        ("MOB-EXIT-CORRECTION", "Exit correction and bulk exits", "Marked exit corrected; bulk lines valid and invalid", "Correction approved and republished; one case per valid line",
         "tests/e2e/test_member_mobility.py"),
        ("MOB-TRANSFER", "Form 13 to Annexure K", "Source balance; primary destination", "Employer attests; office approves; balances conserve; Annexure K"),
        ("MOB-WRONG-DEST", "Transfer to non-primary destination", "Secondary destination account", "Refused at filing and decision",
         "tests/e2e/test_primary_member_id.py"),
        ("MOB-AUTO", "Auto-transfer on job change", "Verified Aadhaar; pending transfer offer", "Offer confirmed; source moved once to destination",
         "tests/e2e/test_member_mobility.py"),
        ("MOB-JD", "Joint Declaration", "Minor and major identity corrections", "Appropriate employer/office chain; changed master data audited",
         "tests/e2e/test_joint_declaration.py"),
        ("MOB-JD-EMPLOYER", "Employer-initiated Joint Declaration", "Signatory files with member consent", "Starts attested; goes to the office chain",
         "tests/e2e/test_member_mobility.py"),
        ("MOB-COC", "Certificate of Coverage", "Posting to an agreement country; limits; overlap; extension", "Issued by the IW cell; certificate; extension within the limit",
         "tests/e2e/test_higher_pension_international_edli.py"),
        ("MOB-IW-MEMBER", "International worker as a member", "IW versus domestic member; advance versus final settlement; age 58 or an agreement country",
         "Full member menu with the coverage page; advances refused with the IW reason; no coverage page for a domestic member",
         "tests/e2e/test_international_worker_member.py"),
    ]),
    ("Pension", "tests/e2e/test_pension_settlement.py", [
        ("PEN-10D", "Form 10D to PPO", "Retired eligible member", "IDS, worksheet, approvals, signing and dispatch to pension in payment"),
        ("PEN-10C", "EPS lump-sum withdrawal", "Eligible short-service former member", "Table D benefit scrutinised and paid from EPS",
         "tests/e2e/test_pension_withdrawal_statement.py"),
        ("PEN-SCHEME", "Scheme certificate and surrender", "Eligible service without immediate pension", "Certificate issued; surrender included in service aggregation",
         "services/pension-service/tests/test_settlement.py"),
        ("PEN-EARLY", "Early pension and normal-age boundary", "Ages/service at configured boundaries", "Eligibility and illustrative reduction explained",
         "services/pension-service/tests/test_pensions.py"),
        ("PEN-CPPS", "Monthly pension and BRS", "Monthly run with paid and returned items", "Bank statement reconciliation and BRS totals agree"),
        ("PEN-DLC", "Life certificate, suspend and resume", "Overdue versus accepted DLC", "Suspended months held; valid certificate resumes eligible pension",
         "tests/e2e/test_pension_services.py"),
        ("PEN-FAMILY", "Family pension", "Spouse, children and minor beneficiary", "Entitlements and roles verified before PPO/payment",
         "tests/e2e/test_signatures_family_pension.py"),
        ("PEN-HIGHER", "Pension on higher wages (joint option)", "In service on 1 Sep 2014 versus later joiner; wages above the ceiling", "Option validated by the employer; dues from the rules; ineligible member refused",
         "tests/e2e/test_higher_pension_international_edli.py"),
    ]),
    ("Death and EDLI", "tests/e2e/test_death_claims.py", [
        ("DEATH-F20", "Form 20 death settlement", "Deceased member, authorised nominee", "Office approval and beneficiary share payment"),
        ("DEATH-5IF", "EDLI benefit", "Admitted claim; verified average wages", "EDLI section recomputes and sanctions the benefit (bound to the amount); paid from the EDLI fund",
         "tests/e2e/test_higher_pension_international_edli.py"),
        ("DEATH-SHARES", "Beneficiary share correction", "Shares not 100%; minor guardian", "Invalid total refused; authorised correction audited"),
        ("DEATH-NOTNOMINEE", "Unrelated claimant", "No beneficiary entitlement", "No access/submission allowed"),
        ("DEATH-PHYSICAL", "Physical claim at PRO counter", "Paper intake and identity mismatch/match", "Receipt, identity scrutiny and correct office handoff"),
    ]),
    ("Grievance", "tests/e2e/test_journey_c_grievance.py", [
        ("GRV-RESOLVE", "Grievance to closure", "Member linked claim complaint", "Registration, routing, reasoned reply and closure"),
        ("GRV-ESCALATE", "Overdue escalation", "SLA elapsed", "Correct next office receives case; history preserved"),
        ("GRV-REOPEN", "Reopen request", "Within versus outside configured window", "Eligible request reviewed; late request explained",
         "services/grievance-service/tests/test_grievance_api.py"),
        ("GRV-PUBLIC", "Grievance without a login", "Mock OTP; demo question; status by registration number", "Routed to the office; status shows steps, never the text",
         "tests/e2e/test_public_services.py"),
        ("GRV-FOLLOWUP", "Reminder, feedback and office transfer", "Open, resolved and transferred grievances", "One reminder a day; satisfied feedback closes; transfer moves the case",
         "tests/e2e/test_public_services.py"),
    ]),
    ("Compliance", "tests/e2e/test_compliance.py", [
        ("CMP-DEFAULT", "Default to compliance case", "Non-filing and non-payment months", "Office case links periods and evidence"),
        ("CMP-DEMAND", "Demand to paid closure", "14B/7Q demand and direct payment", "Payment journal and demand closure agree"),
        ("CMP-SETTLEMENT", "VISHWAS settlement", "Designated disputed damages", "Decision revises demand; payable/waived totals reconcile"),
        ("CMP-TRUST", "Surrendered trust ingestion", "Trust member ledgers; wrong member ID; repeated reference", "All lines or none; balanced journals; reference used once",
         "tests/e2e/test_public_services.py"),
    ]),
    ("Claims (connected)", "tests/e2e/test_member_mobility.py", [
        ("CLM-ATTEST", "Employer attestation of a claim", "Member without verified Aadhaar", "Claim waits for the signatory; attested goes on, rejected ends with the reason"),
        ("CLM-BANK-SWITCH", "Bank switch before payment", "Second KYC-verified account; unverified account", "Payee switched before payment; unverified refused"),
        ("CLM-PUBLIC-STATUS", "Claim status without a login", "Claim number and UAN; mock OTP", "Progress only; wrong UAN not found", "tests/e2e/test_public_services.py"),
    ]),
    ("Ledger and controls", "tests/e2e/test_ledger_office.py", [
        ("LED-APPENDIX", "Appendix E adjustment", "Four adjustment types; proposal and approval", "Correct shares, journal and audit effect"),
        ("LED-REVERSAL", "Reversal and recredit", "Posted journal versus rejected transfer-in", "Balanced reversal/recredit once; provenance retained",
         "services/contribution-service/tests/test_ledger_work.py"),
        ("LED-VDR", "Offline receipt allocation", "Receipt matched/unmatched to TRRN", "Allocation posts valid return or records rejection"),
        ("LED-FREEZE", "Freeze and de-freeze", "Open claim and locked account", "Affected actions held; controlled release and re-scrutiny",
         "tests/e2e/test_ledger_and_establishment.py"),
        ("LED-ISSUE-TRACKER", "Issue Tracker freeze and notice", "Order raised by the OIC; executed by the IS Division", "Account frozen and de-frozen by member-service; notice delivered",
         "tests/e2e/test_oversight_administration.py"),
        ("OVS-VIGILANCE", "Vigilance case", "Staff complaint; benign signal; CVO, zone and other roles",
         "Referred, inquiry assigned to the zone, findings with the complainant masked, penalty proceedings ordered; benign signal and other roles refused",
         "tests/e2e/test_vigilance.py"),
        ("OVS-PREVENTIVE", "Sensitive posts and vigilance clearance", "Officer overdue for rotation; officer named in a case; posting to the cash section",
         "Rotation list; clearance withheld then given after the case is closed; sensitive posting only with a clearance",
         "tests/e2e/test_vigilance.py"),
    ]),
    ("Oversight and administration", "tests/e2e/test_oversight_administration.py", [
        ("OVS-INCIDENT", "Security incident and CERT-In report", "High severity within and past 6 hours; low severity", "Reportable ones reported (mock) with acknowledgement; late marked"),
        ("OVS-CONCURRENT", "Concurrent audit alert and reply", "Day's flagged decisions; office in and outside the zone", "Alert to the office; OIC replies within 3 days"),
        ("OVS-POSTING", "HR posting", "Officer re-posted and back", "Every service follows the new office"),
        ("OVS-DASHBOARDS", "District and employer dashboards", "Office facts; establishment returns", "Counts and alerts for the caller's scope"),
    ]),
]
for family, reference, rows in OTHER_FAMILIES:
    CASES += [dict(case_id=row[0], family=family, category="Connected process", title=row[1],
                  data=row[2], expected=row[3], reference=row[4] if len(row) > 4 else reference,
                  prerequisite="Designated role/data fixtures; see supporting test and process documentation",
                  integration="synthetic POC; external identity, signatures and bank integrations may be simulated")
              for row in rows]

BY_ID = {case["case_id"]: case for case in CASES}


def validate_catalogue():
    if len(BY_ID) != len(CASES):
        raise ValueError("Duplicate lifecycle case ID")
    for case in CASES:
        if not all(case.values()) or not (ROOT / case["reference"]).is_file():
            raise ValueError(f"Invalid case or missing reference: {case['case_id']}")
    return CASES
