# Phase 2 — plan and progress

Phase 2 is every operation marked **P, phase 2** in `docs/endpoint-catalogue.md` (177 at the start). It is built
in slices, each finishing journeys the POC already demonstrates; a slice is done when its operations are **W**,
its menus in the web app are clickable, and unit, end-to-end and must-deny tests pass on the running stack.

| Slice | Scope | Status |
|---|---|---|
| **P2.1** | Dates of exit (member Mark Exit; employer marks, signatory approves), service history, the member's pending / processed applications, Form 13 transfer (member → present employer → DA → AO; ledger moves the balance), Annexure K | **Done** (28 Sep 2026) |
| **P2.2** | Employer member registration (single, bulk; new UAN or a new member ID under an existing one), Form 11, member KYC (PAN, bank) through mock verifiers and the signatory's approval, KYC bulk with error list, missing details, active-member export, the employee's contribution ledger, UAN card, account readiness | **Done** (28 Sep 2026) |
| **P2.3** | Pension office and pensioner self-service: pension enquiry (8 tabs), updation activities (DA initiates, APFC settles) and tracker, overdue life certificates, suspend / resume (held months released), mock Jeevan Pramaan DLC and signed callback, PPO, slips, bank change, declarations, public pension enquiries behind the demo CAPTCHA | **Done** (29 Sep 2026) |
| **P2.4** | Pension settlement: Form 10D desk by desk (DA Accounts IDS → AO → DA Pension worksheet → APFC Pension → PPO → initial arrear DA → SS → APFC e-sign → dispatch), scheme certificate and its surrender, service aggregation, transfers-in, CPPS monthly run with the mock sponsor bank's paid statement and reconciliation, BRS | **Done** (29 Sep 2026) |
| **P2.5a** | Claim lifecycle and office tools: eligibility preview for one form, documents, withdrawal before a decision, member and office audit trails, the CAD (accounts wing), payment scrolls with return reconciliation, forms filed with a claim, member 360 view (purpose recorded), inoperative accounts | **Done** (29 Sep 2026) |
| **P2.5b** | Death and EDLI claims, beneficiary shares, physical intake at the PRO counter, identity validation (family pension deferred to P2.6) | **Done** (29 Sep 2026) |
| **P2.5c** | Ledger locks, document attestation views, establishment freeze / de-freeze, office Annexure K files and reconciliation | **Done** (29 Sep 2026) |
| **P2.5d** | Claim scrutiny as the CITES manuals set it: the Claim Approval Docket at every level, recommend to approve / reject with the account status, rejection only at the final level (an intermediate "Recommend to Reject" returns to the initiator), Start-Stop Claim, one-time code on every officer action | **Done** (30 Sep 2026) |
| **P2.6a** | Establishment record and changes: KYC through mock registries, bank accounts, exemption, branches (Form 2A), Form 5A, contractors of a principal employer; profile and configuration changes as requests the office decides; OLRE scrutiny (DA Compliance, e-file) and the APFC's coverage decision | **Done** (30 Sep 2026) |
| **P2.6b** | Signatory request / revoke letters, DSC and e-sign registration with the office's approval (Authorized eSign List), the signatory's pending approvals; family pension (Form 10D by a widow / widower or child) | **Done** (30 Sep 2026) |
| **P2.7a** | Returns and payments: arrear and supplementary returns, cancelling an unpaid TRRN, the office rejecting a return before posting or a payment stuck at the bank, the returns dashboard, 14B / 7Q demands on late payment, direct challans (administrative charges; miscellaneous 14B / 7Q) and their knock-off (DA Compliance → SS) | **Done** (30 Sep 2026) |
| **P2.7b** | Office ledger work: receipts outside the challan flow (VDR) allocated to TRRNs or rejected, reversal of a posted journal, recredit of a rejected transfer-in, Appendix E with the CITES manual's four types (DA proposes, APFC approves) | **Done** (30 Sep 2026) |
| **P2.7c** | Member-facing ledger: annual statement, taxable interest split, Form 10C cash withdrawal (pension withdrawal benefit by Table D, paid from EPS) | **Done** (30 Sep 2026) |
| **P2.7d** | Primary member ID: the latest member ID with contributions, over the member's Aadhaar-verified set; claims only against it, whole-balance claims (final settlement, Form 10C, death claims) only when the rest of the set is transferred; Form 13 only into it (checked when filed and when approved) | **Done** (30 Sep 2026) |
| **P2.8a** | Compliance: defaulting establishments (office and public lists), compliance cases, the employer's month-by-month compliance summary, 14B/7Q demands paid directly, VISHWAS settlement of damages (new compliance-service) | **Done** (30 Sep 2026) |
| **P2.8b** | e-Nomination, Know your UAN, exit-date corrections and bulk exits, employer-initiated Joint Declaration, auto-transfer on a change of job, employer attestation of claims, switching a claim's bank account | **Done** (30 Sep 2026) |
| **P2.8c** | Joint option for pension on higher wages (member opts, employer validates wages, dues from the rules); the EDLI section's decision on verified wages; Certificates of Coverage and the international worker's view (new international-service) | **Done** (30 Sep 2026) |
| **P2.8d** | Grievances without a login and their status, reminders, feedback and office transfers; claim status without a login; circulars; the e-Report Card; the approved interest rate recorded by HO F&A (→ a draft rule set); a surrendered trust's past accumulations ingested | **Done** (30 Sep 2026) |
| **P2.8e** | Security incidents with CERT-In reporting (mock); the Concurrent Audit Cell's daily extract, alerts and OIC replies; the NDC Issue Tracker (freeze / de-freeze / login notice); the zonal fraud-risk case list; HR postings that move jurisdiction everywhere; district and employer dashboards; member location mapping | **Done** (30 Sep 2026) |
| **P2.9a** | International workers are members: one member login and menu, with what does not apply to them disabled and explained, from rules in the rule set | **Done** (30 Sep 2026) |
| **P2.9b** | Members of exempted establishments: PF held by the trust (passbook, claims and transfers say so and route correctly), pension and EDLI with EPFO; the trust's Annexure K; a transfer's PF and EPS legs | **Done** (1 Oct 2026) |
| P2.9d | Regulating the trust: the monthly online return (employees, contributions, claims and grievances), the online performance evaluator (six parameters) and the priority matrix (Form CE-6) for the exemption cell | Done |
| **P2.9c** | Member experience: a life-event home page, one consolidated view, plain-language status, nudges, a mobile pass | **Done** (30 Sep 2026; built before P2.9b, which waits for the Exemption Manual) |
| **P2.10a** | Vigilance cases: a CAIU-confirmed risk signal (or a complaint) referred to vigilance; the CVO assigns a preliminary inquiry to a zone (90 days); zonal vigilance reports findings; the CVO decides; restricted, access-logged, the complainant masked | **Done** (30 Sep 2026) |
| **P2.10b** | Preventive vigilance: sensitive posts and 3-year rotation alerts; vigilance clearance for HR postings, promotions and retirement against open cases and penalties | **Done** (1 Oct 2026) |
| **P2.11a** | Inspections and 7A inquiries: the Enforcement Officer's report through DA / SS / circle officer, registration with a diary number, random allocation by size, summons, hearings and daily orders, the employer's replies, the 7A order (ex parte only after due service) raising the demand | Done |
| **P2.11b** | 7B review (after the next-higher officer's view), 7C escaped amounts (within 5 years), ex-parte set-aside, administrative scrutiny of orders; the 14B damages and 7Q interest proceedings | Done (the CBT's waiver for sick companies stays planned) |
| P2.11c | Appeals (7-I) with the 7-O pre-deposit, the legal-case register and court orders, 26B membership disputes, prosecution | Planned |
| P2.11d | Recovery (Recovery Manual, 08/12/2023): recovery certificates (8B–8E), 8F garnishee, attachment, sale, receiver, arrest (records only); HO reports on proceedings and recovery; PMVBRY exclusions from open inquiries | Planned |
| **P2.12h** | Explore pages: the stakeholder chart by EPFO's hierarchy, each lifecycle as a network of stakeholders and steps with how far it is built, and the user manuals published into the portal — all linked from the home page | Done |
| **P2.12a** | Member and tax: Form 16A, the office's TDS computation; UAN allotment and activation (mock Aadhaar face / OTP); inoperative accounts — the public helpdesk search, verification through co-workers, reactivation in the AO / APFC bands | **Done** (1 Oct 2026) |
| **P2.12b** | Employer lifecycle: voluntary coverage, closure, transfer to another office; contractors tagging ECR members to a principal employer and the principal's view of contractor compliance; MCA and Shram Suvidha registration feeds (mock) | **Done** (1 Oct 2026) |
| **P2.12c** | Pension office: deciding a validated higher-pension option and the PF → pension fund transfer after the dues; Special 10D; bank-wise disbursement lists; the actuarial extract | **Done** (1 Oct 2026) |
| **P2.12d** | Oversight: internal audit reports, paras, replies and decisions; DPDP data-principal requests; RTI replies; the CPGRAMS feed (mock) | **Done** (1 Oct 2026) |
| **P2.12e** | Head office reporting: balance sheet, investments, board packs (aggregates), fund-manager position feed (mock) | **Done** (1 Oct 2026) |
| **P2.12f** | The rest: DR replication status and failover drill, training sandboxes, Nidhi Aapke Nikat camp requests, totalisation claims and the foreign agency's CoC check, the composite death claim | **Done** (1 Oct 2026) |
| **P2.12g** | Menu clean-up: screens already built linked from their menus (Composite claim, Know Your Pension Payee Bank, Change Password); every other item without a screen says why — planned (with the slice), awaiting EPFO's definition, or not in the POC | **Done** (1 Oct 2026) |
| P2.13 | Small gaps: disablement pension (EPS para 15); zonal freezing (categories B and C) and zonal ACC decisions above the RO's limits; district office queues; PPO and UAN card issued to DigiLocker (mock) | Planned |
| P2.14 | The exempted trust's lifecycle: annual audit filing and the exemption cell's review; surrender and cancellation (RPFC report → ZO → HO → the Exempted Establishments Committee → the appropriate Government); HO's decision; past accumulations transferred in bulk and reconciled with the receipts | Done (bulk transfer and VDR reconciliation stay planned) |
| P2.15a | PMVBRY (Pradhan Mantri Viksit Bharat Rozgar Yojana): Part A for first timers, Part B for employers adding jobs, the disbursement run and the dashboard — from the scheme guidelines and EPFO's SOP for calculating incentives | Done |
| P2.15b | SMS and e-mail for in-app notices through a mock gateway — preferences and language, essential messages, retries, delivery evidence, the PRO desk's follow-up | Done |
| P2.16 | Gig and platform workers (Code on Social Security, 2020): aggregators registered, a turnover-based contribution return (1–2% of turnover, capped at 5% of payments to the workers, in the rule set), workers linked by e-Shram number to a UAN, reconciliation | Planned — design only until the scheme is notified |
| P2.17 | Insolvency: a watchlist from EPFO's own signals (ECR stopping, defaults, MCA status), IBBI announcements matched to the establishment, claim deadlines, dues frozen (7A; damages and interest kept apart), the resolution plan checked for PF dues in full, liquidation claims outside the estate (IBC s.36(4)(a)(iii)), recovery measured | Planned (links to P2.11) |
| P2.18 | EPF to NPS: the PF leg paid to the member's NPS Tier I (PRAN, KYC match, the trustee bank through the CRA — mock); the EPS leg cannot move — a Scheme Certificate or the withdrawal benefit | Planned (needs PFRDA's circular) |
| P2.19 | Edge cases as tests first, then the fixes: death during a transfer or claim; minor nominee or no nomination; two UANs to merge; court-ordered back wages after exit; 58 in service; a re-employed pensioner; family pension to a dependent parent or a disabled child; attachment orders refused; mergers without a break; a vanished contractor (s.8A); partial payment; exemption cancelled mid-transfer; returned payments after a bank merger; one bank account for many members; identity mismatches; members abroad without Aadhaar; unclaimed balances | Planned |

## P2.9 — plan

**Why.** In P2.8c the international worker was modelled as a separate login with one permission, so
`worker-expat` sees a single page. An international worker is a member — UAN, contributions, passbook, KYC,
nomination, claims — with different rules. And members of exempted establishments have not been modelled at all:
their PF is held by the establishment's trust, which the passbook and claim screens do not reflect.

### P2.9a — international workers as members
- **Identity**: `worker-expat` signs in as `member`; being an international worker is an attribute of the member
  record, already captured on Form 11 (`international_worker`, `country_of_origin`) — plus nationality and whether
  their home scheme issued a Certificate of Coverage (then exempt for the posting). member-service publishes it
  (`MemberRegistered.v1` / a new `MemberInternationalStatusChanged.v1`); claim-service, contribution-service and
  international-service keep a copy. The separate `intl_worker` stakeholder is retired (the activity map's F10.worker
  moves to `member`).
- **Rules, not code** — a new rule-set section `international_workers` (illustrative, validated like the others):
  which claim types are open to an international worker and under what condition (e.g. final settlement only at the
  age of retirement, on permanent incapacity, or on leaving for a country with an agreement that allows it; no
  advances), whether contributions are on full wages (no wage ceiling), and per agreement country what changes.
  Claim eligibility already explains refusals; it gains the reason "not available to international workers …".
- **Contributions**: the ECR accepts wages above the ceiling for international workers (today it is an error for
  EPS/EDLI wages); the validation report says why.
- **Web**: the same member menu; items that do not apply are shown disabled with the reason, not hidden; the
  coverage page stays as *View › International worker coverage*.
- **Agreements**: align the synthetic catalogue with the 20 partner countries and years in `../pf-international`
  (names and years only; terms stay illustrative until curated from the treaty texts).
- **Tests**: claims refused and allowed by rule; ECR above the ceiling; the persona's full menu; must-deny for the
  old one-permission role removed.

### P2.9b — members of exempted establishments
**Sources** (downloaded 1 Oct 2026 from EPFO's exempted-establishments page,
`pmvbry.epfindia.gov.in/exempted-establishments`, to `../manuals/exemption/`): the *Exemption Division Manual*
(4 Dec 2023, 231 pp. — *EM*), the *SOP for Management and Regulation of EPF Exemption* (29 Nov 2023 — *SOP-M*), the
SOPs on grant, cancellation and surrender (4 Dec 2023) and the *Exempted Returns Manual* (*RM*). Page numbers are
the printed ones. What the slice relies on:
- **Kinds of exemption** (EM §1.4, p.15): the whole establishment (s.17(1)(a)), a class of employees (s.17(2) with
  Para 27A), a single employee (Para 27, by the RPFC); also *relaxed* establishments (Para 79). Pension can be exempted
  only under s.17(1C) and EDLI under s.17(2A) (EM pp.10–11) — so by default **PF is with the trust; pension and EDLI
  stay with EPFO**, and the employer still pays EPFO the pension contribution and administrative charges (EM p.164,
  the RPFC's certificate on "pension fund contributions as well as Administrative Charges").
- **What the member is owed** — the conditions of exemption, Para 27AA Appendix A (EM pp.22–23; SOP-M p.6):
  enrolment of every eligible employee (Cond. 3); previous accumulations transferred into the trust (Cond. 4);
  contributions to the trust by the 15th, with 7Q interest when late (Cond. 5); interest at least the statutory
  rate, the employer making good any shortfall (Cond. 7); benefits — contribution rate, interest, advances — not
  less favourable than EPFO's (Cond. 9); claims for withdrawal, advances and transfers settled **within 20 days**
  (Cond. 12, SOP-M p.6; the online evaluator scores settlement **within 10 days**, SOP-M p.17 — the rule set will
  carry one figure, 20, with the other noted); an annual passbook free of cost within six months of the year's end
  and the balance viewable online (Cond. 14–15; SOP-M p.16).
- **Transfers** in and out of the trust are the Board of Trustees' duty (EM p.31; SOP-M p.4); the trust's return
  records *Transfer in* and *Claims including transfer out* (RM Part E, F and W).

**Build**
- **Model** (employer-service owns it; others keep a copy from `EstablishmentExemptionChanged.v1`): an
  establishment's exemption — kind (17(1)(a) / 17(2)+27A / 27 / Para 79 relaxation), schemes exempted (PF; pension
  and EDLI false unless 17(1C) / 17(2A)), the notification or order and its date, the trust's name, status (ACTIVE /
  SURRENDERED / CANCELLED) and dates. Member IDs at such an establishment are *PF with the trust* for that period.
- **Rule set** — a new section `exempted_establishments` (illustrative): which claim types the trust settles (the PF
  ones) and which stay with EPFO (Form 10C / 10D pension, EDLI), `trust_claim_days` 20, interest at least the
  statutory rate.
- **Member view**: the passbook shows the PF of those periods as *held by <trust>*, the pension contributions with
  EPFO, and what the trust owes the member (Cond. 12, 14, 15) in plain words; the claim screen gives PF claims on such
  a member ID the reason "Your PF is with <trust>; the trust settles it within 20 days" and keeps pension and EDLI
  claims with EPFO; the member home's nudge offers to move an old EPFO member ID's balance into the trust (Cond. 4).
- **ECR**: for an exempted establishment the return's PF lines are refused with a reason and only the pension and
  administrative charges are due to EPFO.
- **Each member ID has two accounts**: the PF account (with EPFO, or with the trust while the establishment is
  exempted) and the EPS account (always with EPFO — the trust members are EPS members, Pension Manual §1.3.2; the
  exempted employer pays the pension share to EPFO, Exemption Manual p.164). The EPS account carries the pension
  service (months, breaks) and contributions of that member ID.
- **A transfer has two legs, each with its own status** shown to the member, the employer and the office:
  - *PF leg* — the PF balance and PF service: to or from the trust through Annexure K (the trust answers the office's
    request and submits the amount, `/exempted/me/annexure-k-*`, brought forward from Phase 3; `fo.da_accounts`
    reconciles it); between EPFO member IDs as today.
  - *EPS leg* — the pension service (and its breaks) from the EPS account of the old member ID to the EPS account of
    the new one, both with EPFO.
  - **Unexempted → exempted**: the PF leg goes to the trust; the EPS leg moves the service to the EPS account of the
    member ID linked to the exempted establishment, on approval (it does not depend on the trust).
  - **Exempted → unexempted**: the PF leg comes from the trust; when it is completed (the trust's Annexure K received
    and reconciled), the EPS leg from the exempted member ID's EPS account **starts automatically** — no second request.
    Until then the EPS leg shows *waiting for the PF transfer from the trust*.
  - Statuses per leg: REQUESTED → (PF from a trust: AWAITING_TRUST → ANNEXURE_K_RECEIVED →) COMPLETED, or
    RETURNED with the reason; the EPS leg WAITING_FOR_PF → COMPLETED.
  - This closes the gap the Pension Manual names (p.56): "members get their PF transferred from Trust and fail to get EPS
    service history transferred to EPFO and thus there will be no continuous service".
- **The trust's passbook, fetched on demand — not copied**: the trust holds the PF account (it credits interest and
  settles claims), owes the member a passbook and an online balance (Conditions 14–15), and under the Code's draft rules
  must link its online systems with EPFO's (Exemption Manual p.17). So the trust exposes a small signed passbook API
  (a mock trust service in the POC) and EPFO reads it when the member opens an exempted member ID: the PF part shows
  balance, entries and interest *as reported by <trust>, fetched at <time>*; the EPS part comes from EPFO's own record;
  the two transfer legs show their status. A short cache (minutes) spares the trust repeated calls; if the trust's API is
  unavailable the page shows the last snapshot with its date, or "Contact <trust>" with its details — never blank.
  Office officers read the same (e.g. to check an Annexure K amount). EPFO keeps no copy of the trust's ledger: one
  record holder, no second version to drift, less personal data under the DPDP Act. Data moves in bulk only on a
  transfer (Annexure K) and on surrender or cancellation (the past-accumulation ingestion of P2.8d).
- **Pension service adds up across member IDs**: the pension estimate and the pension claim use the EPS accounts of
  all the member's IDs — the exempted spell included — less breaks without contributions (para 9; breaks from
  Annexure K, nil when it shows none, Pension Manual p.45). Today the estimate counts one joining-to-exit record only
  (`services/pension-service/app/api/routes.py`); that is fixed first, as it is wrong for any member with several
  employers.
- **Tests for the passbook fetch**: the trust's API down (the snapshot or the contact shown), the trust answering only for
  its own members, the member seeing only their own member IDs, the freshness label.
- **Test of the whole path**: a member moves unexempted → exempted → unexempted; the PF moves twice through the trust,
  the EPS service moves twice inside EPFO (the second time on its own once the trust's PF arrives), both statuses are
  visible at each step, and the pension service at the end is the sum of the three spells.
- **Persona and seed**: `exempted-trust` (Board of Trustees' officer, `exempted.trust`) for a seeded exempted
  establishment (17(1)(a), active) with its trust profile (`GET /exempted/me/profile`, the conditions it has
  undertaken); a member there who also has an EPFO member ID with a balance elsewhere.
- **Tests**: claims routed by the rules; the passbook split; the ECR refusal; Annexure K both ways and the
  reconciliation; must-deny (the trust sees only its own members and requests).

### P2.9d — regulating the trust (after b)
- **Monthly online return** (RM; SOP-M p.4): Part C employees (on the rolls, joined, left, excluded, contract,
  international workers), Part D contributions (due, transferred to the Board of Trustees with dates, balance due,
  interest paid for late transfer), and the claims and grievances return (claims received, settled within / beyond
  20 days, pending, with reasons; grievances) — RM pp.8–13. Investments (Part E) and the surcharge on deviations from
  the pattern (SOP-M pp.17–18) are left out.
- **Reconciliation**: the sum of the member balances the trust's passbook API reports against the corpus in its monthly
  return; a difference is flagged for the exemption cell.
- **Online performance evaluator** (SOP-M pp.16–17): six parameters at 100 points each — transfer before the due date,
  investment ≥ 70% of the investible corpus, full remittance to the trust, interest at least EPFO's rate, claims
  settled in time, accounts audited — computed from the returns; the monthly ranking for the exemption cell.
- **Priority matrix** (Form CE-6; SOP-M pp.12–16): *A* — cancellation proceedings by show-cause notice (e.g. no
  return for 3 consecutive months, under 300 of 600 points for 3 consecutive months, PF dues in default, claims not
  settled in time); *B* — rectify, cancellation after 2 consecutive occasions; *C* — advise, cancellation after 3.
  The exemption cell (`fo.exemption`) sees the flags raised from the returns and records the action; the
  cancellation itself (RPFC report → ZO → HO → the Exempted Establishments Committee → CBT → the appropriate
  Government, EM ch. 4) stays a recorded referral.
- **Not planned**: grant of exemption, investments and their pattern, compliance and third-party audits, Board of
  Trustees' meetings — the manual's chapters 2, 6 and 7.

### P2.9c — member experience (after a and b)
- A life-event home page ("I changed jobs", "I'm leaving work", "someone has died", "I need money for …") that
  leads into the existing forms; EPFO's menu stays for familiarity.
- One consolidated view: the balance across the Aadhaar-verified set, the pension estimate, what is pending and the
  next action.
- Plain-language status everywhere (lead with the `next_step` the APIs already return; no internal state codes).
- Nudges: an old member ID with a balance, missing KYC or nomination, an exit not marked.
- A mobile layout pass, checked by the UI tests at phone width.

**Open questions**: whether international workers'
withdrawal conditions should stay illustrative or be taken from a source you can provide.

Operations marked **?** (scope unconfirmed, e.g. *ECR Approval*, *VDR Member Beneficiary*) wait until their
meaning is confirmed.

## P2.10 — plan (vigilance)

**Why.** Interface 18 (Vigilance) is the last one with nothing built: the catalogue has the referral, the case list,
findings and decisions, and the activity map says how work flows (F07.vig_referral → F07.vig_zone → F07.vig_ho), but
no source describes the procedure in detail. The outline below follows the CVC's pattern for complaints and preliminary
inquiries as summarised in `../pf-ideas/divisions/12_vig.md` (Vigilance Complaint Number, 90-day inquiry, first-stage
advice); every period and outcome is illustrative and lives in the rule set.

### P2.10a — vigilance cases (workflow-service)
- **Referral** (`ho.caiu`, `POST /vigilance/referrals`): from a risk signal the CAIU has reviewed as *confirmed*
  (workflow-service keeps a copy from `RiskSignalReviewed.v1`; anything else is refused), from a member's security
  report, or a complaint (source: public, staff, CVC, ministry). Subject: a member, an establishment or an official;
  the office where it arose; the allegation; evidence references (the signal, claims, audit events, office cases); an
  optional complainant, stored but masked for everyone except the CVO. The case gets a Vigilance Complaint Number.
- **CVO** (`ho.cvo`, `POST /vigilance/cases/{id}/decisions`, step-up): *assign a preliminary inquiry* to the zone of
  the office (due in the rule set's `vigilance.pi_days`, 90), *close — no substance*, and after the report: *close*,
  *minor* or *major penalty proceedings*, *refer to the CBI*, *system improvement*, or *return for further inquiry*.
- **Zonal vigilance** (`zo.vigilance`, `POST /vigilance/cases/{id}/findings`, step-up): sees only the cases assigned
  to its zone; reports findings (substantiated / partly / not substantiated, the report, a recommendation, the evidence
  examined); a report after the due date is marked late.
- **Restricted**: only these two roles read cases (`GET /vigilance/cases`, new `GET /vigilance/cases/{id}`); every
  read is written to the audit log; the events (`VigilanceCaseOpened.v1`, `VigilanceFindingsRecorded.v1`,
  `VigilanceDecisionRecorded.v1`) carry identifiers only — no allegation or names — and go to audit only, so nothing
  reaches reporting or the assistant.
- **Persona**: `zo-vigilance` (Zonal Vigilance Directorate, ZO-DEMO-01).
- **Web**: `/vigilance` for the CVO and the zone (list, case, decision and findings forms); *Refer to vigilance* on a
  confirmed signal in the CAIU screen.
- **Tests**: unit (referral only from a confirmed signal, zone restriction, masking, the state machine, late
  findings, reads audited); must-deny (other roles, the other zone); end to end (signal → referral → assignment →
  findings → decision).

### P2.10b — preventive vigilance (after a)
- Sensitive posts (compliance, recovery, cash, administration — in the rule set) and each officer's tenure from the
  postings; alerts at 2½ and 3 years; the list for the annual general transfer.
- Vigilance clearance: HR asks before a posting to a sensitive post, a promotion or retirement; clear unless an
  open case names the officer or a penalty is current.
- Not planned: the Agreed List and doubtful-integrity register (kept with the CBI; too sensitive even as a demo).

## P2.12 — plan (the smaller planned endpoints)

P2.11 (compliance proceedings) and P2.9b / P2.9d (exempted establishments) wait; first the catalogue's smaller
planned endpoints (41, outside compliance and exemption), grouped by who uses them so each slice is one demo story.
The HO reports on proceedings and recovery wait for P2.11. Each slice: the endpoints built (rows move P → W), rules in
the rule set where amounts or periods are involved, unit, must-deny and end-to-end tests, and the web screen.

## P2.13 – P2.15 — plan (gaps found in the ecosystem review)

A review on 1 Oct 2026 (codex and agy asked separately, each claim checked against the repository) found, besides P2.9d
and P2.11 and the integrations that stay mocks in a POC (UIDAI, banks and NPCI, Income Tax, MCA / GSTN, CPPS, Jeevan
Pramaan, UMANG, CSC, B2B payroll, CERT-In):

- **P2.13 — small gaps.** *Disablement pension* (EPS para 15; Pension Manual §2.5 and the claim table p.55): the member
  exits on permanent and total disablement — Form 10D with the medical certificate (100% disability, issued by the
  medical officer), no minimum service, pension from the date of disablement; the activity `F05.disabled_apply` exists,
  nothing handles it. *Zonal freezing* (categories B and C, `F07.freeze_zo`) and *zonal ACC decisions* above an RO's
  limits (`F08.escalate`, `F13.zo`), both marked future in the activity map. *District office* queues (`F06.district`).
  *DigiLocker*: the PPO and the UAN card pushed to the member's DigiLocker (a mock issuer; `F14.digilocker`).
- **P2.14 — the exempted trust's lifecycle** (after P2.9d; sources: the SOPs on surrender and on cancellation, Dec 2023,
  in `../manuals/exemption/`):
  - *Annual audit*: the trust files the annual report with its audited accounts by 30 September (corpus movement that
    must add up, the auditor's opinion and observations); the exemption cell sees late and qualified ones.
  - *Surrender*: the trust applies (SE-1) at least 30 days ahead with the trustees' resolution, the employer's
    undertaking and the employees' consent; the cell returns an incomplete one (7 days); the RPFC-I (`ro-oic`) permits
    compliance as un-exempted (SE-5) from the date — ECRs then carry the EPF share, the trust's returns stop, and the past
    accumulations are due within 30 days (later ones attract 14B / 7Q); the draft agenda goes RO (SE-2) → ZO (SE-3,
    `zo-acc`) → HO (`ho-exemption`: EEC, CBT, the appropriate Government, its notification) → the RO's gazette
    notification under Para 28(5). Each stage shows who acts and by when (the SOPs' timelines).
  - *Cancellation*: the cell issues a show-cause notice (CE-1) on category A flags, Condition 25 or 29, audit findings
    or a complaint; the trust replies in 7 days — the cell drops it, or sends the agenda (CE-2) up the same route; a
    trust that admits and relinquishes is taken over at once as a special surrender.
  - *Every service follows the end date* (`ExemptionStatusChanged.v1`): the ECR, the passbook, transfers, claims and
    the pension's per-spell PF holder.
  - Demo: two new trusts — Demo Textile Mills surrenders (`textile-trust`, member NEHA DEMO), Demo Chemicals' exemption
    is cancelled (`chemicals-trust`); Demo Steel Works keeps its exemption and files its audit.
  - Left planned: *PAST ACCUM BULK TRANSFER* and *PAST ACCUM VDR RECO* (they need the VDR entries, still planned), the
    third-party audit's report, the securities and Special Deposit Scheme transfers, the Para 79 relaxations.
- **P2.15a — PMVBRY (Pradhan Mantri Viksit Bharat Rozgar Yojana)**. Sources, downloaded from pmvbry.epfindia.gov.in to
  `../manuals/pmvbry/`: the scheme guidelines (M/o L&E, 16 Aug 2025, 21 pp.) and EPFO's *SOP for calculating
  incentives* (Nov 2025, 11 pp.). Registration period 1 Aug 2025 – 31 Jul 2027; all figures in the rule set.
  - *Part A — the first timer* (no contributing membership before 1 Aug 2025; UAN by face authentication; gross wage
    up to ₹1 lakh at joining): one completed month's EPF wage, at most ₹15,000, in two instalments — half the average EPF
    wage of 6 continuous completed months (≤ ₹7,500) after 6 ECRs with contributions; the rest of the average of the
    first 12 after 12 ECRs filed within 18 months *and* the financial literacy course. A completed wage month starts
    in the joining month if joined by the 5th, else the next; the EPF wage is the contribution × 100 / 24.
  - *Part B — the employer*: deemed registered; exercises the option with its GSTN and PAN-linked bank account.
    Baseline = the average ECR headcount Aug 2024 – Jul 2025 (20 for a new establishment); threshold 2 additional
    employees under a baseline of 50, else 5; eligibility per month on averages (months 1–6 of crossing: the six;
    7–12: from the first; 13 on: the last 12). Net additional employment = min(headcount − baseline, eligible
    employees — joined in the period, gross ≤ ₹1 lakh, 6 continuous months of contributions; re-joinees need an
    Aadhaar-authenticated UAN). Per employee by the EPF wage slab: ≤ ₹10,000 → 10% (at most ₹1,000), up to ₹20,000 →
    ₹2,000, above → ₹3,000; monthly incentive = the average per eligible employee × net additional; each additional
    "slot" is paid for 24 months (48 in manufacturing) from its first payment, never extended. Paid as a lump sum for
    the first six-month cycle, then monthly, each cycle recomputing the whole and deducting what was paid. Not paid
    while a 7A / 7B / 7C or Para 26-B inquiry, an FIR or an ABRY irregularity stands (from the seed until P2.11 brings
    the inquiries).
  - *Payment*: the FA & CAO's disbursement run (`ho-finance`) — the employee's share by Aadhaar-bridge DBT, held while
    the bank account is not Aadhaar-seeded (accruing), the employer's to the PAN-linked account; within 45 days. The
    dashboard for the CPFC (scheme guidelines 13.1.4): beneficiaries by part, expenditure, pending by age, sectors.
  - *Demo*: Demo Auto Components (manufacturing, baseline 30) with a synthetic ECR history from Aug 2024 — an owner
    (`auto-owner`) and a first timer (`member-ft`, ARJUN DEMO).
  - *Left out*: exempted trusts' ECR without contributions, the fraud SOP of the Executive Committee, the seasonal
    industries' 6-in-12 rule, the savings instrument for the 2nd instalment (not yet notified), grievances' own category.
  - *Wording to confirm with EPFO*: the guidelines say "more than or equal to" baseline + threshold and the SOP says
    "more than"; we follow the guidelines (and the threshold's "at least").
- **P2.15b — notifications**: the notices members already get in the app (`NotificationRequested.v1`, raised by
  claim-, contribution-, grievance-, member- and pension-service) also go by SMS and e-mail, through a mock SMS
  aggregator and mail relay in mock-integrations (signed calls; a bounce, a number that does not exist, the gateway
  down). The member chooses SMS / e-mail and English or Hindi; *essential* messages (money, account security) always
  go by SMS. A worker sends and retries on the rule set's schedule (1, 5, 30 minutes; four attempts), keeping every
  attempt as delivery evidence; a failure reaches the PRO / facilitation desk of the member's office, which can send it
  again once the contact details are right; NDC IS watches the gateway. Demo: ARJUN DEMO's e-mail bounces.
- **Not planned** (needs EPFO first): the seven "?" office functions — VDR Special, VDR member beneficiary, VDR vs ECR
  reconciliation, EO certification, the APFC's ECR approval queue, bank-counter payment — until a domain owner defines
  them; the menus say so.

## P2.16 – P2.19 — plan (gig workers, insolvency, EPF to NPS, edge cases)

Each starts by fetching its official source and summarising it with page references, as was done for the exemption
manual; until then the figures below are from general knowledge and marked so.

- **P2.16 — gig and platform workers.** The Code on Social Security, 2020 defines gig and platform workers and lets the
  central government frame schemes for them; aggregators contribute 1–2% of annual turnover, capped at 5% of what they
  pay those workers; workers register on e-Shram. *To verify*: whether EPFO administers a scheme and what it provides
  (the scheme notifications). Then: aggregator registration, the periodic contribution return with the rate and cap in
  the rule set, workers linked by e-Shram number to a UAN (one worker, many aggregators; a gig worker who is also an
  EPF member elsewhere), reconciliation of contributions with payments, under-declared turnover flagged.
- **P2.17 — insolvency.** PF, pension and gratuity dues owed to workers are outside the liquidation estate (IBC
  s.36(4)(a)(iii)); the moratorium (s.14) stops EPFO's own recovery (8B–8G), so the claim must be early and complete.
  *To verify*: the IBBI regulations' claim forms and deadlines, and how 14B damages and 7Q interest are treated.
  Stages: signals (ECR stopping, defaults building up, MCA status — the mock MCA feed exists) scored into a watchlist;
  IBBI public announcements matched by PAN / CIN with a deadline clock; dues frozen (7A, member-wise, PF / EPS / EDLI,
  damages and interest apart) and the claim filed with proof; the resolution plan checked for PF dues in full; in
  liquidation the claim outside the estate; recovery percentage and time per stage. Edge cases: exited members' dues;
  contractors (s.8A); an exempted establishment's trust at risk; a plan relabelling PF dues; recovery under way when the
  moratorium starts.
- **P2.18 — EPF to NPS.** On the two-leg transfer of P2.9b: the PF leg to the member's NPS Tier I (PRAN, KYC matched,
  paid to the NPS trustee bank through the CRA — mock); the EPS leg cannot move — a Scheme Certificate, or the
  withdrawal benefit when eligible. *To verify*: PFRDA's circular and EPFO's procedure. Edge cases: an open advance or
  claim, a frozen account, unlinked earlier member IDs, 58 or over, a part transfer, an inactive or mismatched PRAN.
- **P2.19 — edge cases.** Written as end-to-end tests first (several may partly work already), then fixed: death during
  a transfer or claim (to the death-claim route); a minor nominee or no nomination; two UANs of one person merged with
  their service; court-ordered back wages after exit (arrear ECR, interest, pension recomputed); 58 while in service
  (EPS to EPF unless deferred pension); a re-employed pensioner (EPF, no new EPS); family pension to a dependent parent or
  for life to a disabled child; an attachment order refused (*to verify*: s.10 of the Act); a merger or demerger without
  a break; a vanished contractor paid by the principal (s.8A); a partial challan's allocation; an exemption cancelled while
  a transfer is in flight; payments returned after a bank merger; one bank account for many members; name or date of
  birth differing across Aadhaar, PAN and the PF record; a member abroad without Aadhaar; unclaimed balances (*to verify*:
  the Senior Citizens' Welfare Fund rule).

## P2.1 — how it is built

- **Processes on the engine** (`config/processes/employer-exit.yaml`, `transfer-form13.yaml`). The engine gained
  generic `account` and `date` form rules, checked against a projection of member accounts in workflow-service
  (whose account, at which establishment, exited, already transferred), and `reads` operations (a member's own case).
  `ProcessTransitioned.v1` now says whether the case ended (`terminal`) and whether the member sees it.
- **Owners**: member-service records exits (`MemberExitMarked.v1`) and keeps the member's applications;
  contribution-service posts the transfer journal (`TransferPosted.v1`) and serves Annexure K; claim-service keeps
  its balances and exit dates from those events.
- **Data**: a UAN can now have several member IDs (contribution-service keys members by member ID). Synthetic
  member D has two: AL-0008 (previous, exit not marked) and AL-0009 (current).

## P2.2 — how it is built

- member-service registers joinees (`MemberRegistered.v1` → contribution, claim, workflow) and runs KYC requests:
  a labelled mock verifier (UIDAI / NSDL / penny-drop) answers first, then the employer's signatory approves with
  step-up (DSC / e-sign). An approved KYC changes the member record and publishes `MemberKycUpdated.v1`
  (claim-service updates the PAN flag that sets the TDS rate).
- Deferred from this slice: UAN activation and self-allotment (a login per new member), exit corrections and
  exit-bulk (exits already need the signatory's approval per member), member location mapping (branches, P2.6),
  employer-initiated Joint Declaration.
- Found: interest for a year in which a member ID's balance was later transferred was credited to the emptied
  member ID. It is now credited to the member ID the money went to, and "already credited" is read from the
  interest postings themselves.

## P2.3 — how it is built

- pension-service owns it all. A pension is credited monthly only while IN_PAYMENT; a lapsed life certificate lets
  the APFC (Pension) suspend it; a new certificate (Jeevan Pramaan, or a physical one recorded as an updation
  activity) resumes it and the held months are credited on that day.
- Updation activities are a small maker-checker inside pension-service (not the engine): the DA (Pension) — new
  persona `ro-da-pension` — initiates, the APFC settles, rejects or sends back; only a settled activity changes the
  pension. A pensioner's bank change is such an activity.
- The gateway now asks the demo CAPTCHA for the four public pension enquiries as well as the TRRN lookup.
- Not modelled: beneficiaries / family pension, commutation, recovery and TDS on pension (the enquiry shows them
  empty), the pension-disbursing bank's own enquiry.

## P2.4 — how it is built

- pension-service holds the Form 10D claim as a small state machine; each step is its own endpoint and role, and
  the officer who took a step cannot check it (the APFC (Pension) both approves the worksheet and e-signs the PPO,
  as in the Pension Manual, with other officers in between). The worksheet uses the pension formula in the rule
  set in force on the date the pension starts; the e-signature is bound (step-up) to the initial arrear amount.
- Dispatching the PPO puts the pension in payment and credits the months since it started (the initial arrear).
- CPPS: a run lists the month's credits; the sponsor bank's paid statement arrives by a signed callback, or — when
  CPPS reconciles before one arrived — the mock bank answers at once (accounts ending 0000 are returned). The
  office's BRS compares its scroll with the bank's debits.
- New personas: `member-e` (retired member), `ro-ss-pension` (SS Pension), `ndc-cpps` (CPPS operator).
- Not built: family pension (Form 10D by claimants), Special 10D, higher-pension options, the legacy bank-wise
  disbursement lists.

## P2.5a — how it is built

- claim-service: a member may withdraw a claim only before an approving officer decides (the work-queue case
  closes); documents are checked (type, magic bytes, 1 MB) and kept with their SHA-256 — a stand-in for the object
  store. The CAD (new persona `ro-fa-accounts`, F&A accounts wing) fixes gross, interest included, TDS and net,
  with the rule and static-data versions; a payment made after it uses its figures. A payment scroll pays every
  approved claim of the office whose debit is posted; its reconciliation lists paid, pending and returned claims.
- member-service: the member 360 view needs a purpose, is limited to the officer's office (a zonal officer sees
  the zone) and is written to the audit log. contribution-service: inoperative accounts (no credit for 36 months).
- Found: the gateway asks for step-up on every POST of an operation marked for it, so a "preview" flag on the
  scroll POST could never work; the preview is its own read-only endpoint (`GET /office/payment-scrolls/ready`).

## P2.5b — how it is built

- Synthetic data: GANESH DEMO (UAN 100000000901, AL-0901) died in service on 15 Jul 2026; nominations LAKSHMI
  DEMO (spouse, 60 %, persona `claimant-a`) and ARJUN DEMO (son, 40 %). New persona `ro-pro-counter` (fo.pro_intake).
- claim-service (`app/api/death_routes.py`): a nominee files Form 20 (PF: the member ID's balance) or Form 5IF
  (EDLI: `edli_benefit` under the rules in force — wages × multiplier, plus a share of the average balance
  capped, between the assured minimum and maximum; synthetic average wages ₹15,000). The claim goes straight to
  review through the normal officer chain; beneficiaries come from the nomination (or a list given with the claim,
  or are added later with no share). The APFC amends a share with a reason (one-time code); payment is refused
  until the shares add up to 100 %; at settlement each beneficiary's paid amount is recorded, net of any share
  settled in the legacy system. The PRO counter inwards paper forms; pension updations go to the pension office.
- `ClaimDecisionRecorded.v1` now carries `fund`: an EDLI claim is debited to AC21_EDLI, not the member's account.
  New event `PhysicalClaimInwarded.v1` (pension-service turns a pension updation into a NEW, PHYSICAL activity);
  `BeneficiaryShareAmended.v1` moved to phase 1.
- member-service: identity validation at the counter matches name and date of birth with the record and keeps the
  KYC status at that moment (audited). An exit marked `DEATH_IN_SERVICE` records the date of death in claim-service.
- Deferred: family pension (Form 10D by a widow / child, P2.6), the composite claim (CCF), a dedicated EDLI
  decision step, and paying each beneficiary to their own bank account (one payment per claim for now).

## P2.5c — how it is built

- workflow-service (`app/api/locks_routes.py`): a claim case, and a Form 13 case (`ledger_lock:` in its YAML), lock
  the member's ledger while open; the lock goes with the case when it finishes. A lock whose owner is gone or has
  expired is orphaned and refuses officers' decisions on that member (`/problems/ledger-locked`) until the OIC
  releases it with a reason and a one-time code (`LockReleased.v1`, now phase 1). Seed: a dead annual-accounts batch
  left one on ESHA DEMO (UAN 100000000005).
- Engine: `produces_document` keeps a signed document on the case (the employer's DSC on Form 13, mock) and
  `requires_viewed` refuses the step until the officer has opened it (`attestation-views`, audited).
- `config/processes/establishment-freeze.yaml`: the zone / OIC / HO freezes an establishment; de-freeze is
  maker-checker (APFC recommends, OIC orders). employer-service now consumes `ProcessTransitioned.v1` and shows the
  freeze to the employer; contribution-service refuses ECR approval and submission while it stands.
- ANNEXURE K FILE / RECO (claim-service, a projection of `TransferPosted.v1`: inward, outward, within the office),
  reconciled against the UAN, the amount and the previous member ID being emptied; ANNEXURE K VDR RECO
  (contribution-service) against the VDR receipt amount. Both with one-time codes.
- Not built: the annual-accounts batch and ECR posting do not take locks yet (only the seeded orphan shows those
  scopes); Annexure K for exempted establishments (`/office/exempted/annexure-k/...`) stays planned.

## P2.5d — how it is built

Source: the CITES user manuals (`../manuals`, reviewed in `docs/reviews/cites-manuals-vs-poc.md`).

- **Claim Approval Docket.** The CAD was an accounts-wing document made after approval; in CITES it is the Claim
  Approval Docket the initiator generates and every verifier and the approver generates again before acting.
  `POST /office/claims/{claimId}/cad` is now open to the scrutinising officers while the claim is under review and
  keeps one version per level; `CADGenerated.v1` carries the officer's role, and the work queue refuses a
  recommendation or decision without a docket of that role made since the last decision (`/problems/docket-required`).
  Payment uses the last docket's figures. The accounts wing views the dockets.
- **Recommendation.** The initiator recommends to approve or to reject and records the account status (Operative /
  Inoperative / Dormant), confirmed with a one-time code like every other officer action.
- **Rejection routing.** Only the final level of the amount's chain rejects. An intermediate level forwards the
  recommendation, or — disagreeing with an approval — recommends rejection, which returns the claim to the
  initiator's worklist; the initiator re-forwards it as "Recommend to Reject". The final level sees Approve / Send
  back after a recommended approval and Reject / Send back after a recommended rejection.
  `CaseDecisionSubmitted.v1` carries the recommendation, and the member's timeline says which was recommended.
- **Start-Stop Claim.** The initiator stops a claim under scrutiny with a reason (it leaves every queue and shows
  under Stopped claims) and restarts it later.
- Kept: a verifier approving within its financial limit is our amount-band chain (the last role for the amount is
  final). Not built from the review: the beneficiary login and uploads, the EDLI three-tab calculation screen and
  officer e-sign of the summary sheet, full data entry at the PRO counter, Form 10C cash, Appendix E.

## P2.6a — how it is built

- employer-service (`app/api/establishment_routes.py`): KYC of the establishment (PAN, GSTIN, TAN, CIN, LIN)
  through a mock registry (a number containing `00000` is "not found"); remittance bank accounts and exemption
  (seeded); branches with sub-codes `<registration no>/001…`, shown in the configuration; Form 5A kept by version,
  signed with a one-time code standing in for DSC / e-sign; a principal employer's contractors with the work order.
- Changes are not edits: `PATCH /employers/me` (address, contact) and configuration changes (establishment type,
  industry) open a change request; the APFC of the establishment's office approves (the record changes) or
  rejects it. One open request of each kind at a time.
- OLRE: a registration verified by the mock registry waits for the DA (Compliance), who views the documents and
  records scrutiny, opening the compliance e-file; then the APFC decides coverage (date and type).
- employer-service now has office postings (seeded) for jurisdiction. New persona `ro-da-compliance`.
- The web pages *Establishment* (employer) and *OLRE and establishment changes* (office) were drafted by codex from
  a written spec and reviewed.

## P2.6b — how it is built

- employer-service (`app/api/signature_routes.py`): the owner registers a signatory's DSC (serial, issuer, validity;
  an expired certificate is refused) or Aadhaar e-sign (mock), with a one-time code; uploads the signed request
  letter (PDF, SHA-256 kept); the APFC approves or rejects it. After a signatory is revoked, the signed revoke letter
  goes to the office; approving it ends the signatory's registration. The *Authorized eSign List* shows all of it.
  Registration is not yet required before a signatory approves (returns, KYC, attestations) — noted for later.
- workflow-service: `GET /employers/me/pending-approvals` lists the engine steps waiting for the establishment's
  signatory (Form 13 attestation, Joint Declarations, operator-marked exits) with the operation to perform.
- pension-service (`app/api/family_routes.py`): the spouse or a child on record (the member's nomination) files
  Form 10D on the member's death; it runs through the same desks as a member's Form 10D, and the worksheet uses
  the family-pension formula in the rules (`pension.family`: 50% of the member's formula pension for the spouse,
  a quarter of that for a child, with minimums; no minimum service). The PPO is issued in the claimant's name.
- Web: the Authorized eSign List on *Establishment*, pending approvals on *Member actions*, the office's DSC /
  e-sign decisions on *OLRE* (drafted by codex, reviewed), and the family-pension section on the claimant page.

## P2.7a — how it is built

- contribution-service: `type=ARREAR | SUPPLEMENTARY` returns need the month's regular return posted; a
  supplementary return may only carry members missing from the posted returns, an arrear return only members in
  them (`E-SUPP-ALREADY-FILED`, `E-ARREAR-NOT-FILED`); warnings about the whole workforce do not apply to them.
- An unpaid TRRN is cancelled by the signatory (one-time code bound to the amount) and the wage month is free
  again; the DA (Accounts) rejects a submitted return before it is paid; Cash rejects a payment stuck at the bank
  (the mock bank's new `STUCK` scenario never answers) and the challan can be paid again.
  `ChallanStatusChanged.v1` tells the mock bank; `ChallanGenerated.v1` makes a direct challan payable.
- Late payment: posting a return paid after the due date (`late_payment.due_day` of the next month) raises a 14B
  damages demand (yearly rate by months of delay) and a 7Q interest demand (yearly rate by days) — new rule section
  `late_payment`, validated and publishable. The employer pays them with a miscellaneous direct challan (posted to
  `DAMAGES_14B` / `INTEREST_7Q`); the DA (Compliance) knocks the demands off against it and the SS approves.
  Administrative charges go by a direct challan too (`AC02_ADMIN`).
- The returns dashboard shows each wage month: the regular return, arrear and supplementary returns, due date,
  paid late or not.

## P2.7b — how it is built

- contribution-service (`app/api/ledger_routes.py`). **Receipts (VDR)**: Cash records a cheque / DD / unmatched
  credit with a one-time code; the DA (Accounts) allocates it to an unpaid TRRN of the same establishment — the
  challan is paid and the return posted by the same code path as an online payment (late-payment demands included)
  and `ChallanStatusChanged.v1` (`SETTLED_OFFLINE`) stops the mock bank from taking an online payment for it — or
  rejects it (a dishonoured cheque). What a VDR entry covers in EPFO is not fully confirmed; this is the reading used.
- **Reversal**: a posted contribution, direct challan or Appendix E journal is reversed by a new reversing
  journal (never edited); a member ID is never taken below zero. **Recredit**: a transfer-in the receiving office
  rejected goes back to the member ID it came from. `LedgerReversed.v1` now carries what was reversed; claim-service
  applies any reversal to balances, workflow and member-service clear "transferred" on a recredit.
- **Appendix E** (CITES manual): *Other* (employee, employer and EPS up or down, balanced by an office adjustment
  account), *interest on returns* (employee and employer only), *1.16% to EPS* (from the employer share, never more
  than it holds), *excess interest debit*; each with the notesheet number, date, remarks and optional PDF. The DA
  proposes, the APFC approves (balances are checked again), then it is posted (`LedgerAdjusted.v1`) and shown in the
  passbook.
- Moved to P2.8: principal-employer tags and exempted past accumulations (their actors have no persona yet).

## P2.7c — how it is built

- **Form 10C cash**: a new claim type `PENSION_WITHDRAWAL` in the rules (form 10C) — two months after leaving,
  under 9½ years of service, once per member ID, never settled automatically. The limit is new rule kind
  `max_from: eps_table_d`: the illustrative Table D factor for the completed years of service × wages at the EPS
  ceiling (`table_d_factor_x100`, validated; the policy editor offers it). It runs through the officer chain with the
  Claim Approval Docket, and `ClaimDecisionRecorded.v1` `fund: EPS` debits the EPS pool (`AC10_EPS`), not the member's
  PF. On a running stack the type reaches members only when a rule set containing it is published (the e2e test
  publishes it through the HO maker-checker flow if needed) — adding a claim type needs no code.
- **Annual statement** (`/members/me/annual-statements/{fy}`): per member ID, the opening balance (with the balance
  brought forward), the year's contributions, withdrawals, transfers, interest and adjustments, and the closing
  balance, employee and employer shares. Interest counts in the year it is earned for.
- **Taxable interest**: interest on the employee's own contributions above `tds.taxable_interest_threshold_paise`
  (illustrative ₹2,50,000 a year) is taxable, at the year's rate on the excess; the rest is not. Shown with the
  working, marked illustrative.
- Not built from the CITES review: "send back to DA for wage corrections" on Form 10C, NCP-day deductions.

## P2.7d — how it is built

Source: the Samadhan Setu tracker (7 of its 35 issue types are about the primary member ID: "Requested member id does
not match with the primary member id", "all services are not transferred to primary member id", "Unable to inward
form 5IF due to incorrect Primary Member ID marked", "Transfer-in Member ID must be primary MemberID") and the office
screens (*Primary UAN*, *Primary Member ID*, "(P)", "Part of AADHAAR verified set").

- Rule (`epfo_persistence.member_ids.primary_member_id`): among the member IDs not transferred out, the latest-joined
  one that has received a contribution; if none has, the latest-joined. It is worked out over the member's
  **Aadhaar-verified set**: every UAN with the same verified Aadhaar (member-service keeps a reference, never the
  number). Seed: BHARAT DEMO's older UAN 100000000903 (AL-0903, ₹50,000 not transferred) is in his set.
- member-service recomputes it when a contribution is posted (a new member ID becomes primary with its first
  contribution), a member ID is registered, a transfer is posted or recredited, and publishes
  `PrimaryMemberIdChanged.v1`; the service history, the member 360 view and the UAN set show it.
- claim-service: a claim on a secondary member ID is refused ("Requested member ID does not match with the primary
  member ID (AL-…)"); a final settlement or Form 10C, and a Form 20 / 5IF death claim, also need every other member ID
  of the set emptied ("All services are not transferred to the primary member ID: AL-… holds ₹…").
- workflow: Form 13's "to" member ID must be primary when filed, and again when the AO approves (the primary may
  have moved; rejecting stays possible).
- Web: "P" against the primary member ID in the service history and the claim screen; the transfer form offers only
  the primary as the target.

## P2.8a — how it is built

- **compliance-service** (new, its own database): the establishments and office postings it needs (seeded), compliance
  cases, VISHWAS applications, and a projection of every 14B/7Q demand from `DemandStateChanged.v1`, which
  contribution-service now publishes whenever a demand is raised, knocked off, waived or paid.
- **Defaulters** (`/office/compliance/defaulters`, reporting-service): establishments with a return month unpaid past
  its due date or an open demand, for the officer's office. `fo.da_compliance` opens a **compliance case** on one
  (`/office/compliance/cases`); APFC and OIC see them. The public list (`/public/defaulting-establishments`) shows
  only the name, office and months in default.
- **Compliance summary** (`/employers/me/compliance-summary`): each wage month — filed, paid, paid late, unpaid —
  with its due date and the demands on it.
- **Paying a demand**: the signatory pays a 14B/7Q demand directly (`/employers/me/demands/{id}/payment-intents`,
  step-up bound to the amount); the payment is journalled (`DEMAND_PAYMENT`) and the demand closed.
- **VISHWAS**: the signatory applies to settle open 14B damages; the APFC approves or rejects (step-up bound to the
  revised amount, which the office list shows). Approval raises one revised demand for
  `vishwas.settlement_share_bp` of the damages (illustrative 30%, in whole rupees) — `DemandRaised.v1` — and
  contribution-service waives the demands it replaces. The rule is in the rule set, so HO can change it.
- Not built: principal-employer tags and contractor compliance (no contractor establishment has a workforce in the
  seed), inspections and 7A proceedings, recovery (attachment, prosecution).

## P2.8b — how it is built

- **e-Nomination** (member-service, `/members/me/nominations`): needs a verified Aadhaar; signed with a mock Aadhaar
  e-sign (the step-up) and replaces the previous nomination, which is kept. Shares add up to 100%; a member with a
  family nominates only family members (EPF Scheme para 61, simplified; a married member has a family); a minor
  needs a guardian. `NominationRegistered.v1` replaces the nominees claim-service's death claims pay (a nominee's
  login and bank details are kept for the same name).
- **Know your UAN** (`/members/uan-lookups`): name, date of birth and the mobile's last four digits, with a mock OTP.
- **Exits** (process engine, `employer_exit`): the operator corrects a marked date of exit (`exit-corrections`) or
  uploads exits in bulk (`exit-bulk-uploads`: one case per valid line, the others reported); the signatory approves
  each in *Member › Approvals*. On approval member-service republishes `MemberExitMarked.v1` with `corrects`. The
  engine gained `bulk:` operations and `subject_from: form:<field>`.
- **Employer-initiated Joint Declaration**: the signatory files it for a member of the establishment with the
  member's consent (mock OTP); it starts at *employer attested* and follows the usual office chain.
- **Employer attestation of claims** (claim-service): a claim on a UAN without a verified Aadhaar waits in
  `PENDING_EMPLOYER_ATTESTATION` for the signatory (`/employers/me/claim-attestations`); attested, it goes on as any
  claim (`ClaimSubmitted.v1` only then); rejected, it ends `REJECTED_BY_EMPLOYER` with the reason.
- **Bank switch** (`PUT /members/me/claims/{id}/bank-details`): until the payment goes to the bank, to another of
  the member's KYC-verified accounts (seeded, then `MemberKycUpdated.v1`). After a return, the re-disbursement
  request still applies.
- **Auto-transfer** (`/members/me/transfers/auto`): an exited member ID of the member's Aadhaar-verified set with a
  balance is offered for transfer into the primary member ID; the member confirms (`AutoTransferConfirmed.v1`) and
  contribution-service posts it as it posts an approved Form 13 (`TransferPosted.v1`). Needs a verified Aadhaar;
  not offered while a claim on that member ID is open.
- Personas: `member-f` (Aadhaar pending) and `member-g` (changed jobs), both synthetic.
- Not built: EPS nomination (Form 2 part II), nominee photographs, a date-of-exit correction after a claim is
  settled (refused in the portal; not checked here), OTP delivery for Know your UAN.

## P2.8c — how it is built

- **Pension on higher wages** (pension-service; rule set section `higher_pension`, illustrative, after the Supreme
  Court's judgment of 4 November 2022): a member in service on 1 September 2014 files the joint option with a
  declaration and consent to move the dues; the employer's signatory uploads the wages month by month, previews the
  dues (the pension share, 8.33%, of the wages above the ceiling in force for each month: ₹5,000 / ₹6,500 / ₹15,000)
  and validates it, the confirmation bound to that amount — or rejects it with a reason.
  `HigherPensionOptionValidated.v1` records the outcome; the office decision, interest on the dues and the PF →
  pension fund transfer stay Phase 3.
- **EDLI decision** (claim-service): once the officer chain admits a Form 5IF claim, it waits in
  `PENDING_EDLI_DECISION`; the EDLI section (`fo.edli`) enters the verified average monthly wages, the benefit is
  worked out again from the rules the claim was filed under, and the approval is bound to that amount (paid from the
  EDLI fund as before). The section can also reject with a reason.
- **international-service** (new, its own database): the agreement catalogue (India's partner countries, illustrative
  terms), Certificates of Coverage for workers posted abroad — the employer applies (country with an agreement, posting
  within its limit, no overlap), uploads the signed PDF, the International Workers cell (`fo.iw`) issues or rejects it,
  the employer downloads the certificate and can extend it within the agreement's extension limit —
  `CertificateOfCoverageIssued.v1`; and the international worker's own view of their coverage.
- Personas: `member-h` (in service since 2011), `worker-expat` (a foreign national employed in India), `iw-officer`,
  `ho-iwu`, `ro-edli`.
- Not built: totalisation claims and the foreign agency's certificate check (Phase 3), CoCs issued to foreign
  nationals by their home scheme (the exemption itself), pensioners' higher-pension options.
- Fixed on the way: the e-nomination notification (P2.8b) named a placeholder the renderer does not supply, so the
  notification failed; a test now renders every template.

## P2.8d — how it is built

- **Without a login** (the gateway's one-use demo question and a rate limit guard each form; the one-time code to
  the mobile is a mock — any six digits except 000000):
  - *Grievance* (`/public/grievances`): a pensioner, an employer or anyone files it; only a hash of the mobile and
    its last four digits are kept; it is routed to the regional office like a member's grievance.
  - *Grievance status* by registration number and mobile: the steps and the resolution, never the grievance text.
  - *Claim status* by claim number and UAN (or the late member's UAN): the steps only — no amounts, names or bank.
  - *Circulars* (intelligence-service): HO Public Relations publishes them; the same number again is a new version
    and the last is kept as superseded. Three synthetic circulars are seeded.
  - *e-Report Card* (reporting-service): the establishment's last 12 wage months due — filed and paid on time,
    late, filed not paid, not filed — with counts and the total remitted; no member data.
- **Grievances**: the member sends a reminder at most once a day while the grievance is open; gives feedback on a
  resolved one (satisfied closes it, otherwise it stays open to a reopen); the regional office transfers a
  grievance to another office (`GrievanceTransferred.v1` moves its work-queue case; a second synthetic office,
  RO-DEMO-02, has no staff).
- **Interest rate** (`PUT /ho/config/interest-rates/{fy}`): HO F&A records the CBT recommendation and the Ministry's
  concurrence; `InterestRateDeclared.v1` makes platform-service prepare a draft rule set with the rate, which ACC
  (HQ) submits and the CPFC publishes as any rule change — crediting still uses only the published rule set.
- **Surrendered trust** (`POST /office/exempted/{estId}/past-accumulation-ingestions`): the exemption cell ingests
  the trust's member ledgers for member IDs of an establishment whose exemption was surrendered or cancelled (the
  seeded Demo Retail Cooperative; KAVITA DEMO and LALIT DEMO), one batch per transfer reference, all lines or none;
  each line is a balanced journal against the trust's transfer (`LedgerAdjusted.v1`, `PAST_ACCUMULATION`), so the
  balances reach the claims projection and can then be transferred.
- Personas: `ho-publicity`, `ro-exemption`.
- Not built: OTP delivery, the maker-checker on trust ingestion (one officer with a one-time code bound to the
  total), trust returns and audits (Phase 3), circulars in the assistant's knowledge base.

## P2.8e — how it is built

- **Security incidents** (audit-service, `ho.security`): recorded with category, severity and detection time; high and
  critical ones, and unauthorised access, data breaches and identity theft whatever their severity, are reportable to
  CERT-In within 6 hours of detection (after CERT-In's directions of 2022, simplified); the report is a mock with an
  acknowledgement number, flagged late when past the window.
- **Concurrent audit** (audit-service): the zone's Concurrent Audit Cell (`zo.rpfc1_audit`) downloads a day's
  functionality extract from the hash-chained audit log — the day's settlements, ledger adjustments and reversals,
  transfers, identity changes, de-freezes and waived demands, each with red flags (high value, bank changed after a
  return, auto-transfer, past-accumulation credit …); raises an alert to a regional office of its zone; the OIC replies
  within 3 days (late replies are marked).
- **NDC Issue Tracker** (platform-service): the OIC raises a freeze, de-freeze or login notice for a UAN with the order
  (PDF, hashed); the IS Division (`ho.is`) executes or rejects it; `IssueTrackerExecuted.v1` is carried out by
  member-service, which owns the account state (`AccountFrozen.v1` / `AccountDefrozen.v1`, or a notice to the member).
- **Fraud-risk committee** (workflow-service, `zo.fraud_committee`): the zone's cases that point to possible fraud —
  claims with an advisory risk signal, member and establishment freezes.
- **Postings** (workflow-service, `ho.hr` anywhere, `fo.admin` within its office): a posting changes the officer's
  office and role; `StaffPostingChanged.v1` updates the copy every service keeps (a shared helper in
  common-persistence), so work queues, the member 360 view, grievances, compliance and the rest follow at once;
  cases assigned to the officer in the old office go back to that office's queue.
- **Dashboards** (reporting-service): the district office's (claims pending and over the service level, payment
  returns, grievances, defaulting establishments) and the employer's (the last three returns, alerts with links).
- **Location mapping** (member-service): the employer maps a serving member to a branch (code, district, pincode).
- Personas: `zo-audit`, `ndc-is`, `zo-fraud`, `do-oic` (HR postings use `hrm-employee`).
- Not built: real CERT-In reporting, Issue Tracker requests for establishments and employer users, vigilance
  referral from the fraud-risk committee (Phase 3), branch lists checked against Form 2A.

## P2.9a — how it is built

- **One login**: `worker-expat` has the `member` role; the `intl_worker` stakeholder has no activities left (F10.worker
  moved to `member`) and is kept in `stakeholders.md` only as a member attribute. member-service stores the status in
  `members.international` (nationality, passport, country of origin), set from the seed and from the employer's Form 11
  (`international_worker` + `country_of_origin`); a change publishes `MemberInternationalStatusChanged.v1`
  {uan, international_worker, nationality}. `GET /members/me` returns `international_worker` and `nationality`.
- **Copies**: claim-service keeps `international_worker`, `nationality` and `date_of_birth` on each account (a new
  member ID under the same UAN inherits the status); contribution-service on `establishment_members`;
  international-service on its worker record. `GET /members/me/international` is now a member endpoint and answers 404
  for a member who is not an international worker.
- **Rules, not code** — rule-set section `international_workers` (illustrative, validated): `no_wage_ceiling`,
  `claim_types` open to them (final settlement only) and `final_settlement_on` (`min_age` 58, or a nationality in
  `agreement_nationalities`). Claim eligibility adds the reason "Not available to international workers …" or the
  age / agreement condition; filing an advance is refused with the same reason.
- **Contributions**: an ECR row above the EPS/EDLI ceiling for an international worker gets the warning
  `W-IW-FULL-WAGES` instead of the error `E-EPS-CEILING`.
- **Agreements**: the synthetic catalogue now lists India's 20 partner countries (names and years; terms illustrative).
- **Web**: the ordinary member menu; *View › International worker coverage* appears when `/members/me` says the member
  is one; the profile shows the status and a one-line note on the rules; the claims page shows the refusals with
  their reasons (disabled, not hidden).
- **Tests**: claim-service `test_international_workers.py`, contribution-service `test_domain.py` (full wages),
  member-service `test_onboarding.py` (Form 11 sets and clears the status, one event per change),
  international-service `test_international.py` (404 for other members, status events), web `P28c.test.tsx`;
  end to end `tests/e2e/test_international_worker_member.py` (the persona's menu, passbook, refusals, an advance
  refused; a domestic member has no coverage page).

## P2.9c — how it is built

- **Member home** (`/member`, now the member's landing page; `MemberHomePage.tsx`): built only from APIs that
  already exist, each loaded on its own so one failing call shows its error in its section and the rest still render.
  *Your savings* — the total across every member ID of the member (claim-service's eligible-types balances joined
  with member-service's service history), each member ID with its status, the total service and the best eligible
  pension scenario. *What is pending* — open claims and pending applications, each led by the API's `next_step` and
  the claim type's plain label. *To do* — nudges. *What do you want to do?* — six life events (changed jobs, need
  money, leaving work, retiring, a death in the family, a wrong record) that lead into the existing forms; EPFO's menu
  stays as it is.
- **Nudges** (`memberHome.ts`, pure and unit-tested): an old member ID with a balance and no transfer; KYC not
  verified (which parts); no current e-Nomination; a member ID with no exit and no contribution for two months while
  a later one exists; contributions not yet in the passbook.
- **Plain language**: the claims list leads with the next step and the claim type's label (the form number in small
  text; no internal codes); applications show their state in words.
- **Phone**: below 620px the menu bar is one *Menu* button (`roleNav.css`) that closes after navigating; life events
  stack in one column; balances are a list, not a table. `tests/e2e/test_member_home.py` checks the home page's
  sections and a nudge, and that every member page fits 360px with no sideways scroll.
- **Hindi**: the member home, life events, nudges, the phone menu and the international-worker screens are translated
  (`i18n/member.en.json` / `member.hi.json`, merged into the resources); the 17 strings left marked `[TODO-translate]`
  since Phase 1 (banner, title, persona menu, interface page) are translated too.
- **Status labels**: one table of plain labels, English and Hindi, for every state and status code the member,
  employer, claimant, pensioner and public screens receive (`statusLabel()`, which the older `stateLabel()` now uses).
- **Not yet**: the office screens keep their codes where no label exists (officers work with them).

## P2.10a — how it is built

- **workflow-service** (`vigilance_routes.py`, migration 0012): `vigilance_cases` (VCN `VIG/<year>/<n>`, source, subject,
  office, zone, allegation, evidence references, complainant, state, PI due date, findings, outcome),
  `vigilance_actions` (the history) and `vigilance_signals` (the CAIU's reviews, from `RiskSignalReviewed.v1`, which
  workflow-service now consumes).
- **States**: `REFERRED` → *assign inquiry* → `PI_ASSIGNED` (zone = the office's zone; due in `vigilance.pi_days`) →
  findings → `PI_REPORTED` → an outcome from `vigilance.outcomes` (`ACTION_ORDERED`, or `CLOSED` when there is no
  substance) or *return for further inquiry* (back to `PI_ASSIGNED` with a new due date). A referral can also be closed
  at once. Decisions and findings need a step-up bound to the case.
- **Referral rules**: the source must be one of `vigilance.sources`; a CAIU signal only when its review was
  *confirmed* (409 otherwise), with the signal added to the evidence; the same signal or report cannot be referred twice.
- **Restriction**: `ho.cvo` reads every case; `zo.vigilance` only its zone's cases once assigned (another zone's case
  answers 404, not 403); every list and case read writes `vigilance.cases.list` / `vigilance.case.read` to the audit log;
  the complainant is `{"masked": true}` for the zone. Events carry identifiers only and go to audit alone.
- **Persona**: `zo-vigilance` (ZO-DEMO-01); `vigilance-investigator` is now labelled *Chief Vigilance Officer*.
- **Web**: `/vigilance` (the list, a linkable case with `?case=`, the CVO's decisions limited to those open, the zone's
  findings form, an *Overdue* mark); *Refer to vigilance* on a confirmed signal in the CAIU screen; the states in the
  shared label table, English and Hindi. Interface 18 is now *Working*, so no interface is left *Planned*.
- **Tests**: workflow-service `test_vigilance.py` (only a confirmed signal, once; the full cycle with a return for
  further inquiry; the history; events without the allegation or names; reads audited; other roles 403, another zone
  404; a late report); web `Vigilance.test.tsx`; end to end `test_vigilance.py` (a staff complaint through to penalty
  proceedings, a benign signal refused, other roles refused).

## P2.10b — how it is built

- **Rule set** (`vigilance`, illustrative): `sensitive_posts` (`fo.da_compliance`, `fo.eo`, `fo.icf`,
  `fo.recovery_officer`, `fo.cash`, `fo.admin` — compliance, recovery, cash and administration),
  `rotation_alert_months` 30, `rotation_limit_months` 36, `clearance_valid_days` 90, `clearance_purposes`, and
  `withholding_outcomes` (penalty proceedings or a CBI reference); validated like the other sections.
- **Tenure**: `office_staff.posted_since` (migration 0013), from the seed (`ro-cashier` since June 2023,
  `ro-da-compliance` since February 2024; others April 2025) and set to the day of every HR posting.
  `GET /vigilance/sensitive-posts` (CVO, HR) lists the officers on sensitive posts with their tenure and
  `WITHIN_TENURE` / `ROTATION_DUE` / `ROTATION_OVERDUE`, and the list for the annual general transfer.
- **Clearance**: HR asks (`POST /vigilance/clearances`: posting to a sensitive post, promotion, retirement, deputation,
  passport NOC). It is withheld while a vigilance case names the officer — open, or ordered with a withholding
  outcome; a case closed with no substance, or one that ended in a system improvement, does not withhold it. HR sees
  cleared / withheld and a neutral reason; only the CVO sees which cases withheld it (`GET /vigilance/clearances`).
  `VigilanceClearanceIssued.v1` goes to audit only.
- **Postings**: `POST /hrm/postings` to a sensitive post needs a current clearance for that purpose (409
  `/problems/vigilance-clearance-needed` or `/problems/vigilance-clearance-withheld`).
- **Web**: the HRM page gains *Vigilance clearance* (form and list) and *Sensitive posts*; the CVO's vigilance page
  gains the rotation list and the clearances with links to the cases; zonal vigilance sees neither.
- **Not built**: the Agreed List and the register of officers of doubtful integrity (kept with the CBI; too sensitive
  even as a demo).
- **Tests**: workflow-service `test_vigilance.py` (rotation, clearance withheld and restored, the posting check and the
  new posting date); web `Vigilance.test.tsx`; end to end `test_vigilance.py::test_sensitive_posts_clearance_and_posting`.

## P2.12a — how it is built

- **Form 16A** (claim-service, `tds_routes.py`): the member's TDS certificate (section 192A) for a financial year from
  the tax stored when each claim was paid — never recomputed — by quarter, with a deterministic certificate number and
  a synthetic deductor TAN; marked illustrative, not for filing.
- **Quarterly TDS statement** (`POST /office/tds/computations`, `fo.da_accounts`): the office's Form 26Q for a quarter
  that has ended — deductees, totals — filed with a deterministic Income Tax mock; one filing per office and quarter
  (`tds_filings`, migration 0015; a second answers 409 with the acknowledgement); `TdsStatementFiled.v1`.
- **UAN allotment** (member-service, `csc_operator` or `member`): mock Aadhaar face authentication
  (`MOCK-FACE-MATCH`); only a hashed Aadhaar reference is kept; an Aadhaar that already has a UAN, or a member asking
  for themselves, gets 409 with the masked UAN; `UanAllotted.v1` carries no Aadhaar or name. New persona `csc-operator`.
- **UAN activation** (`member`): the caller's own UAN with the demo OTP 123456; `activated_at` (migration 0013).
- **Inoperative accounts** — rule-set section `inoperative_accounts` (36 months without a transaction — interest is
  not one, SOP on transaction-less accounts —, 2 co-workers, the AO's band ₹5,00,000):
  - the office list (contribution-service) takes the period from the rule set and shows *verified* / *reactivated*;
    the AO and APFC can read it too;
  - verification through co-workers (member-service, `fo.da_accounts`): at least two members with overlapping
    service at the same establishment confirm the holder; `InoperativeAccountVerified.v1` → contribution-service;
  - reactivation (`fo.ao` within the band, `fo.apfc` above it; step-up bound to the balance) only when verified;
    `AccountReactivated.v1`;
  - the public search (no login, the gateway's demo CAPTCHA and rate limit): name, date of birth and establishment →
    masked matches without a balance; the balance only after the OTP (demo OTP shown) on a 15-minute reference.
  - Seed: MOHAN DEMO (UAN 100000000910, `AL-0913`), left the demo establishment in 2019 with ₹2,00,000; DEV and HARI
    worked there at the time.
- **Web**: Form 16A on *My claims*; *Activate your UAN* on the security page; `/csc` for the CSC operator; the public
  *Inoperative account search*; on the office claim tools the inoperative list with *Verify through co-workers* and
  *Reactivate*, and the quarterly TDS statement.
- **Fixes on the way**: member-service had never read the rule set — its image now carries the baseline rules and
  it keeps published rule sets; two gateway tests used these endpoints as examples of planned ones and now use a
  synthetic planned route.

## P2.12b — how it is built

- **Three more change requests** (employer-service, on the P2.6a change-request flow; signatory with step-up, decided
  by the office's APFC or OIC with step-up):
  - *voluntary coverage* under section 1(4) — rule-set section `voluntary_coverage` (fewer than 20 employees, consent of
    a majority; illustrative); approval sets the coverage type to VOLUNTARY;
  - *closure* (closed on, reason, last wage month) — approval closes the establishment and publishes
    `EstablishmentClosed.v1`; contribution-service then refuses returns for later wage months;
  - *office transfer* — approval moves the establishment and publishes `EstablishmentOfficeTransferred.v1`, which
    contribution-, claim-, member-, workflow- and compliance-service follow so queues and jurisdiction move with it.
- **Contractors**: a contractor establishment's own users tag the workers of a submitted return to a principal
  employer and work order (`principal_employer_tags`; the filing detail now lists its member rows for this);
  `PrincipalEmployerTagged.v1` feeds reporting-service, where the principal's owner sees the contractor's months —
  members, wages, contribution, paid or not. Seed: Demo Engineering Works (EST-DEMO-0002) is the principal, the demo
  establishment its contractor (work order WO/DEW/2026/014); persona `principal-owner`.
- **Registration feeds** (mock, signed like the other callbacks): MCA SPICe+ / AGILE-PRO and Shram Suvidha create an
  establishment and a registration request that the office's OLRE scrutiny picks up; idempotent on CIN / LIN; a PAN
  already registered is refused. Covered by unit tests (the gateway needs a machine token for them).
- **Fixes on the way**: employer-service (and three other services that did not yet read rules) now carry the
  baseline rule set in their images; a Postgres sum returned as a Decimal broke the tag event (the SQLite unit tests
  could not see it); voluntary coverage is 🔐 like every other change request.

## P2.12c — how it is built

- **Higher pension, after the employer** (pension-service): the office lists its options
  (`GET /office/pensions/higher-pension-options`, added for the queues); the APFC (Pension) approves or rejects a
  VALIDATED option (step-up bound to the dues) and the member is told; the DA (Accounts) then asks for the dues to be
  moved (money route: Idempotency-Key, step-up) — `HigherPensionDuesTransferRequested.v1` makes contribution-service
  post one journal (`HIGHER_PENSION_TRANSFER`, keyed on the option): the member's PF debited (employer share first,
  then employee) and the pension fund (AC10) credited; or, if the PF holds less than the dues, nothing is posted.
  `HigherPensionTransferPosted.v1` brings the option to DUES_TRANSFERRED or TRANSFER_FAILED (the member deposits the
  difference through the office). The passbook shows the entry.
- **Special 10D** (`fo.da_pension`): a case for incomplete service, wages, date of birth or exit date, with the
  evidence offered and a checklist of what reconstructs each; one open case per UAN.
- **Disbursement lists** (new persona `ro-pension-disbursement`, `fo.pension_disbursement`): a month's pension payments
  grouped by bank, with totals — the legacy lists until CPPS pays centrally.
- **Actuarial extract** (new persona `ho-actuarial`, `ho.actuarial`): pensioners and higher-pension options with a
  salted pseudonymous id, age, gender, pension start year, monthly pension, service months and status — no name, UAN,
  PPO, bank or Aadhaar — with aggregates by category and age band; the web page downloads it as CSV.
- **Fixes on the way**: the P2.8c test assumed the option stays VALIDATED. (A replayed money request answers with the
  stored data in a fresh envelope — the codebase's convention; codex's test compared the whole envelope and was corrected.)

## P2.12d — how it is built

- **Internal audit** (audit-service; new persona `zo-internal-audit`): the zone's internal audit reports on an office
  of its zone and raises paras (category, observation, amount at risk, references, recommendation; reply due after
  `oversight_periods.para_reply_days`); the OIC sees its office's paras (`GET /audit/internal/paras`, added) and
  replies, asking for a drop if it has complied (late replies marked); the Audit Division (`ho.audit`) drops the para or
  keeps it open with a new due date (step-up).
- **Data-principal requests (DPDP Act)** (audit-service; new persona `ho-dpo`): a member asks for access, correction,
  erasure, a grievance or a nominee (`POST /members/me/privacy-requests`, added, and their list); the data protection
  officer answers within `privacy_response_days` (illustrative) — a refusal or partial answer must state its legal
  basis (e.g. retention under the EPF Scheme); step-up; `PrivacyRequestDecided.v1`.
- **RTI** (grievance-service, the office PRO): an application is registered (`POST /office/rti-requests`, added) only
  with the fee or a BPL card; the reply is due in 30 days (s.7(1), `rti_reply_days`); a refusal names its exemption
  (s.8(1)(d), (e), (g), (j), s.9 or s.11); a transfer under s.6(3) is flagged if made more than five days after receipt;
  late replies are marked; `RtiReplied.v1`.
- **CPGRAMS** (mock, signed like the other callbacks): a CPGRAMS grievance becomes an EPFO grievance routed to the
  office, keeping the CPGRAMS number; idempotent on it. Unit-tested.
- **Web**: `/audit/internal`; the OIC's audit paras next to the concurrent-audit alerts; the Audit Division's
  decisions; *Your personal data (DPDP Act)* on the member's security page; `/privacy` for the DPO; *RTI applications*
  for the PRO.

## P2.12e — how it is built

- **Balance sheet** (contribution-service, which owns the double-entry ledger — the catalogue row moved from
  reporting): every journal line up to the as-of date summed by account; liabilities (members' PF accounts, the pension
  and insurance funds, the administration account, claims and TDS payable, suspense) against assets (balances brought
  forward, the collection and settlement banks), with a *balanced* check. Read-only, for the statutory auditor
  (persona `statutory-auditor`) and HO F&A; each read audited.
- **Fund-manager positions** (reporting-service; mock, signed like the other callbacks): holdings by fund (EPF, EPS,
  EDLI) and asset class at a date, replacing the earlier set for the same manager, fund and date; the seed loads one
  quarter's synthetic positions.
- **Investments** (`ho.investment` — persona `ho-investment` —, FIAC, HO F&A): book and market value, gain and share of
  each fund's corpus by asset class, against the pattern of investment in the rule set (`investment_pattern`, the
  bands summarised in the exemption SOP, Nov 2023, pp.17–18; illustrative), flagged within / below / above.
- **Board packs** (CBT, EC, FIAC members — personas `cbt-member`, `fiac-member` — and the CPFC): aggregates only —
  contributions, claims (days to settle, share within 20 days), grievances, investments, and the pattern flags for
  FIAC — with no names, UANs or establishment ids.
- **Web**: `/ho/finance/balance-sheet`, `/ho/finance/investments`, `/governance/board-packs`, each printable.

## P2.12f — how it is built

- **Disaster-recovery site** (platform-service; persona `ndc-adc`, `tech.adc`): replication status per service
  database — a deterministic simulation, flagged as such — against the rule set's RPO; a failover drill (step-up)
  whose simulated steps add up to an RTO checked against the target. Nothing is failed over.
- **Training sandboxes** (platform-service; persona `pdnasa-trainer`; also ZTI roles): a course, up to 60 trainees,
  the demo personas they practise as, and an expiry from the rule set; the training logins are records only and the
  data is synthetic. Rule-set section `dr_and_training` (illustrative).
- **Nidhi Aapke Nikat camps** (workflow-service; persona `ro-nan`, `fo.nan`): requests taken at a camp of the office
  (grievance, claim help, KYC, inoperative account, pension, UAN help), each with a reference and the next step;
  the seed has one camp.
- **Totalisation claims** (international-service, `ho.iwu`): a benefit claim routed under an agreement that allows
  totalisation, in either direction, with the periods in each country and the months they add up to.
- **Foreign agency** (`ext.foreign_ss`, a new machine client `foreign-agency-demo` in the realm): verifies a
  certificate of coverage by number — status, masked name, country, posting period, issuing office; nothing more.
- **Composite death claim** (`formType=CCF_DEATH`): one submission files the PF (Form 20) and EDLI (Form 5IF)
  claims with a shared reference, each behaving as if filed alone; if either part fails, neither is filed.

With P2.12f every endpoint the catalogue planned outside compliance (P2.11) and the exempted establishments
(P2.9b / P2.9d) is built.

## P2.11b — how it is built

Source: the Compliance Manual — 14B (3.2–3.3), review (2.7), escaped amounts (2.8), ex-parte orders (2.6), scrutiny (2.11).

- **14B / 7Q proceeding**: the DA drafts the notice in a periodic desk review — it covers every open auto-calculated
  14B damages and 7Q interest demand of the establishment not yet noticed (or those named); the SS endorses (T+3), the
  circle officer approves (T+5) and it is filed with a diary number and allotted by size, as a 7A inquiry. The notice
  serves as the summons; hearings as in 7A. The **14B order** levies up to the amount worked out for each demand, with
  reasons for a reduction; the **7Q order** is at the statutory rate and cannot be varied. Each replaces the
  auto-calculated demands with one demand (`DemandRaised.v1`, DAMAGES_14B / INTEREST_7Q).
- **Review (7B)**: the employer applies within 45 days (illustrative — the Scheme sets the time) on new evidence, an
  error apparent or another sufficient reason, or the officer reviews of his own motion; the officer first records the
  view of the officer next above (APFC → RPFC-II → RPFC-I → Zonal ACC). Granted, the parties are given notice and heard
  again; the order passed under review replaces the earlier demand.
- **Set-aside (7A(4))**: on an ex-parte order, within 3 months, for a notice not duly served or a sufficient cause; set
  aside, the demand is withdrawn and the case is heard afresh.
- **7C**: within 5 years of the order, a linked inquiry before the same officer on an omission by the employer or
  information now in possession; its order adds a demand.
- **Scrutiny**: orders listed for the officer next above by the 15th of the following month; observations recorded on
  the standard proforma, optionally directing a 7C. The Zonal ACC scrutinises the RPFC-I's orders (`zo-acc`).
- contribution-service: a 7Q order's demand is kind INTEREST_7Q; an amount of 0 (or `withdraw`) withdraws the demands it
  names (written by agy, reviewed). Screens: on `/office/inquiries` the DA's notice, the approvals, the 14B / 7Q orders,
  review, set-aside and 7C after an order, the scrutiny list; on `/employer/proceedings` the employer's applications
  (written by agy, reviewed).

## P2.12h — how it is built

- **Data**: `docs/tools/build_gate0.py` now also writes each flow and each activity (who does it, what follows, and how
  far it is built — every endpoint working, some, none, outside the POC, on paper, future) into the portal's
  `system-map.generated.json`, and drops the register's Markdown from the stakeholder names. Nothing is maintained by
  hand.
- **Stakeholders** (`/stakeholders`): the governance bodies over Head Office (with the technology and training units),
  the zones, the regional and the district offices; outside EPFO, members, employers and institutions. A role opens
  its demo login, its endpoints and its activities, each linked to its lifecycle.
- **Lifecycles** (`/lifecycles?flow=…`): the flow's activities as an SVG network, left to right by the chain of
  "next" steps (a step nothing leads to sits just before its first successor; a loop is dashed), coloured by how far
  each is built; the steps also as an ordered list; a step opens who does it and what follows, across flows. The
  compliance chain was re-linked in the order the manual sets: DA → SS → circle officer → allocation.
- **User manuals** (`/manuals`): `scripts/publish_manuals.py` copies the newest verified run of `scripts/ui_manuals.py`
  into `apps/web/public/manuals/` (not committed); the page lists each scenario's manuals by role (HTML and Word) and
  the lifecycle case report, or says how to publish them.

## P2.11a — how it is built

Source: EPFO *Compliance Manual* (05/02/2024), chapter 2, downloaded with the *Recovery Manual* and the *Manual for
Inspector-cum-Facilitator* to `../manuals/compliance/`. Time limits in the rule set (`compliance_proceedings`).

- **Inspection** (compliance-service): the circle officer (`ro-apfc`) schedules it for an Enforcement Officer of the
  office (`ro-eo`, new role `fo.eo`; one is picked if none is named); the EO reports the employees found and not
  enrolled, the wages, the findings, the dues estimated and a recommendation (`InspectionReported.v1`). The report goes
  through the file: DA note (T+3), SS note (T+5), the circle officer's decision (T+7) — each step's due date and lateness
  shown.
- **Registration** (`POST /office/compliance/cases`, kind `INQUIRY_7A`, by the SS or DA): a diary number
  `EPR/<office>/<year>/<n>`; the inquiry goes at random to an officer of the rank its size calls for — up to 250
  contributory UANs an APFC, up to 1,000 an RPFC-II (`ro-rpfc2`), above that the RPFC-I (para 2.5.1) — never one barred
  from a sensitive charge nor the inspecting EO; without an inspection, the OIC's approval on credible information is
  recorded (para 2.3.1 iii). The OIC reassigns with a reason (`InquiryRegistered.v1`).
- **Proceedings** (only the allotted officer): summons with the diary number, the virtual-hearing link and the
  e-Proceedings case-status address, served by e-mail and speed post (mock) — `SummonsIssued.v1`; each hearing's daily
  order (who attended, what happened, documents), the next date within 7 days unless a reason is recorded, or the
  hearing concluded — the order then due within 15 *working* days. The employer (`emp-owner`, `/employer/proceedings`)
  sees the summons, the daily orders and the order, and files replies and evidence until the order.
- **The 7A order**: month-wise dues by account (A/c 1 employee and employer, A/c 10, A/c 21, A/c 2) within the
  inquiry's period; ex parte only when the summons was served and the employer was absent at the last hearing (para
  2.6.2); the order text follows the indicative structure (2.12); a one-time code bound to the amount.
  `DemandRaised.v1` (type `DUES_7A`) puts the dues before the employer as a demand; paid directly, contribution-service
  credits each account its share. `InquiryOrderPassed.v1`.
- **Also**: compliance-service now keeps the published rule set (it did not), and `DemandRaised.v1`'s aggregate is
  `demand` for both VISHWAS and 7A. Screens: `/office/inquiries` (EO, DA, SS, circle officer, OIC) and
  `/employer/proceedings`.
- **Left for P2.11b–d**: 7B review, 7C, ex-parte set-aside, administrative scrutiny, 14B / 7Q proceedings, appeals,
  26B, prosecution, recovery; member-wise credit of 7A dues (the POC credits the pooled accounts).

## P2.15b — how it is built

- **One point of entry**: the notices raised by `NotificationRequested.v1` (claims, grievances, transfers, KYC,
  pension, interest…) are rendered by member-service as before; each now also gets an SMS and an e-mail delivery.
- **Preferences and language** (`/members/me/notification-preferences`; the account security page): SMS, e-mail,
  English or Hindi — every template has a Hindi text. *Essential* messages (a claim paid or rejected, a payment
  returned, a transfer, a contact change, account recovery) always go by SMS (rule set `notifications`).
- **The gateway** (mock-integrations): a mock SMS aggregator (sender `EPFOHO`, 160 characters) and mail relay, signed
  calls; an address `@bounce.invalid` bounces, an empty number is invalid, `MOCK_SMS_DOWN` / `MOCK_EMAIL_DOWN` take it
  down. The POC sends to the masked contact details — it has no real ones.
- **The worker** (member-service, every few seconds): delivered; a temporary failure retried after 1, 5 and 30
  minutes, failed after four attempts; a permanent one (bounce, invalid number) failed at once. Every attempt is kept
  — time, HTTP status, gateway reference, error — as delivery evidence; a failure publishes
  `NotificationDeliveryFailed.v1`.
- **Follow-up**: the member sees each channel's outcome under the notice; the PRO / facilitation desk of the
  member's office (`ro-pro`, `/office/notification-deliveries`) sees failures with the evidence and sends one again;
  NDC IS (`ndc-is`) sees all. Demo: ARJUN DEMO's e-mail bounces; `tests/e2e/test_notifications.py`.

## P2.15a — how it is built

- **The ECR, month by month** (contribution-service `pmvbry_ecr_rows`): each employee in a paid ECR with the EPF wage
  worked back from the contributions (× 100 / 24), the gross wage, the joining date and whether a first timer, a
  re-joinee or an old employee; written when a challan is paid, and generated for Demo Auto Components from a compact
  seed (30 employees since 2019, an exit in December 2025, seven joiners from October 2025).
- **The calculation** (`app/domain/pmvbry.py`, pure functions; every number from the rule set's `pmvbry` section):
  the first completed wage month (joined by the 5th or not); Part A's two instalments with what is still missing and
  *ceased* when the first timer leaves before qualifying; Part B's baseline, threshold, crossing month, eligibility on
  averages, eligible employees, net additional employment, the 24 / 48-month "slots" and the cycles (a six-month lump
  sum, then monthly, each recomputing the whole less what was paid). The SOP's worked examples are its unit tests.
- **Screens**: the employer's Part B page with the option (owner only, one-time code), the monthly table and the
  cycles (`/employer/pmvbry`); the member's Part A page with the financial literacy module (`/member/pmvbry`); the HO
  dashboard (`/ho/pmvbry`) and, for the FA & CAO, the run: a preview (`GET …/disbursement-runs/preview`, because the
  gateway asks for the one-time code before the payment route, and the code is bound to the amount), then the payment
  — instalments to an account not Aadhaar-seeded are *held* and paid on a later run; a second run for the same month
  pays nothing new. Events `PmvbryOptionExercised.v1`, `PmvbryIncentiveDisbursed.v1`.
- **Demo and test**: `auto-owner`, `member-ft` (ARJUN DEMO: ₹7,000 + ₹7,000), `ho-finance`, `ho-analyst`;
  `tests/e2e/test_pmvbry.py` (repeatable).

## P2.14 — how it is built

- **Annual audited accounts** (employer-service; `POST /exempted/me/audits`): the year's corpus movement must add up
  (opening + contributions + interest − claims ± other = closing); the auditor and the opinion (qualified or adverse
  needs observations); due by 30 September; a revision supersedes. The exemption cell sees late and qualified ones
  (`GET /office/exempted/{estId}/audits`). `TrustAuditFiled.v1`.
- **One proceeding at a time** per establishment (`exemption_proceedings` with its step history); every view says
  which stage it is at, who acts next and by when (the SOPs' timelines, rule set `exempted_establishments.proceeding_days`),
  and whether that is overdue.
  - *Surrender*: the trust applies (SE-1, a one-time code; the date at least 30 days ahead, the undertaking and the
    consent) → the cell may return it as incomplete → the RPFC-I (`fo.oic`) permits compliance as un-exempted from that
    date (SE-5) → the cell's draft agenda (SE-2) → the Zonal ACC forwards it (SE-3) or remands it → HO Exemption: EEC,
    CBT, sent to the appropriate Government, its notification → the cell's gazette notification (Para 28(5)) → closed.
  - *Cancellation*: the cell's show-cause notice (CE-1) with its grounds (category A flags, Condition 25 or 29, audit
    findings, a complaint) → the trust replies within 7 days, or relinquishes → the cell drops it, or sends the agenda
    (CE-2) — also once the reply is overdue; a relinquished one is taken over at once by the RPFC-I's permission → the
    same route up. A remand goes back to the RO's stage, also after HO has returned it to the zone.
- **The end date travels** (`ExemptionStatusChanged.v1`, consumed by contribution-, claim- and pension-service): each
  copy holds the status and the date from which the establishment complies as un-exempted; every check asks "was the
  exemption in force on that date" — the ECR's EPF share, the passbook, transfers, the trust's claim refusal and the
  pension's per-spell PF holder. From that date the trust's monthly returns stop, the past accumulations are accepted
  (late ones carry the 14B / 7Q note) and the member's passbook says where the PF is until they are credited.
- **Demo**: Demo Textile Mills (`textile-trust`, member NEHA DEMO) surrenders; Demo Chemicals (`chemicals-trust`)
  relinquishes on a show-cause notice; the queue at `/exemption-proceedings` for `ro-exemption`, `ro-oic`, `zo-acc` and
  `ho-exemption`. `tests/e2e/test_exemption_lifecycle.py` resumes a proceeding an earlier run left half-way.
- **Left planned**: *PAST ACCUM BULK TRANSFER* and *PAST ACCUM VDR RECO* (they need the VDR entries), the third-party
  audit's report, the transfer of securities and Special Deposit Scheme funds, Para 79 relaxations.

## P2.9d — how it is built

- **The monthly return** (`POST /exempted/me/returns`, the trust): Part C employees, which must balance (opening + joined
  − left − excluded = contract under the trust + elsewhere + direct exempted + direct unexempted); Part D contributions
  (the due is the two shares; transfers with dates; interest paid for late transfer); claims and grievances (pending
  needs reasons); the interest declared, the investible corpus and the amount invested, whether the accounts were
  audited, and optionally the total of the member balances. One return a month; a revision replaces it and keeps the
  earlier version as *superseded*. The service works out the balance due, the days the last transfer was late (due by
  the 15th of the following month) and the claims pending.
- **The online performance evaluator**, six parts of 100: transfer before the due date (share of the due transferred by
  the 15th), investment (full at 70% of the investible corpus), remittance (share transferred), interest declared
  (full at EPFO's rate for the year), claims settled within 10 days, accounts audited. The rule set holds the due day,
  the 10 days, the 70%, the 300-of-600 floor and the 3 months (`exempted_establishments`).
- **The priority matrix** (Form CE-6): each return raises its flags with the plain consequence — *A* (show-cause for
  cancellation): no return for 3 months running (counted from the trust's first online return), under 300 for 3 months
  running, PF dues in default, claims settled late, interest below EPFO's rate (the employer makes good the shortfall,
  Condition 7); *B* (rectify; cancellation after 2 occasions): the member balances in the return differ from the
  trust's passbook API. `TrustReturnFiled.v1`.
- **The exemption cell** (`ro-exemption`, its office from the postings copy that now also lives in contribution-service):
  the ranking for a month (a missing return scores 0), a trust's returns and flags, and the action on a flag with a
  one-time code — direction to rectify, advice (not for an *A* flag), show-cause notice, referral for cancellation,
  closed as rectified (`TrustFlagActioned.v1`). A revision cannot erase a flag the office has acted on.
- **HO Exemption Division** (new persona `ho-exemption`, `ho.exemption`): the same ranking across all offices, read-only.
- **Seed and test**: Demo Steel Works' returns for June–August 2026 (July paid 7 days late with claims settled late);
  `tests/e2e/test_trust_regulation.py`.

## P2.9b — how it is built

- **The exemption** (employer-service): one record per establishment — kind (s.17(1)(a), s.17(2)+Para 27A, Para 27,
  Para 79), what is exempted (PF; pension and EDLI stay with EPFO unless s.17(1C) / s.17(2A)), the notification, the
  trust, status and dates. The trust (persona `exempted-trust`, `exempted.trust`) sees its profile with the conditions
  it undertook (Appendix A to Para 27AA). Seed: Demo Steel Works (EST-DEMO-0004), PF exempted under s.17(1)(a); a
  signatory for it (`steel-signatory`); the other services keep a copy from the seed. Rule-set section
  `exempted_establishments` (the PF claim types the trust settles, 20 days, the passbook cache).
- **Claims**: on a member ID whose PF is with the trust, the PF claim types are refused with "Your PF for this member ID
  is with <trust>; the trust settles it within 20 days (Condition 12)"; pension and EDLI claims stay with EPFO.
- **ECR**: an exempted establishment's return with an EPF share is refused (E-EXEMPTED-PF): only the pension share and
  the charges come to EPFO.
- **A transfer has two legs** (contribution-service `transfer_legs`, shown to the member — `GET /members/me/transfer-legs`
  — and to the office — `GET /office/transfers/{id}/legs`):
  - *EPFO → trust*: on approval the member ID's balance is debited to `PAYABLE_TO_TRUSTS` (the PF leg *sent to the
    trust*); the EPS leg moves the pension service to the EPS account of the trust member ID inside EPFO.
    *Decided (2 Oct 2026)*: this EPS leg completes when EPFO approves the transfer; it does not wait for the trust to
    acknowledge the PF, since the pension service never leaves EPFO.
  - *trust → EPFO*: on approval the PF leg *waits for the trust*; `TrustTransferRequested.v1` puts an Annexure K request
    in the trust's queue; the trust submits the amount, the service period and the breaks (money route); the DA
    (Accounts) reconciles it with the receipt (`GET /office/exempted/annexure-k`, added, and step-up) —
    `TrustAnnexureKReconciled.v1` credits the member ID (the PF leg *completed*); `TransferPosted.v1` then makes
    pension-service move the EPS service **on its own**, with the breaks the trust reported (`EpsServiceTransferred.v1`
    → the EPS leg *completed*).
- **The trust's passbook, fetched not copied**: the passbook of a trust member ID shows the PF as reported by the
  trust (a signed call to the trust's passbook API — a mock in mock-integrations), with the time fetched, a cache of a
  few minutes, the last snapshot marked stale when the trust does not answer, and the trust's contact when there is no
  snapshot; the EPS part is EPFO's own.
- **Pension**: the estimate's per-member-ID table says who holds the PF of each spell (EPFO or the trust) and where its
  EPS service went; the service adds up across all of them (first step of this slice).
- **Seed and test**: PRIYA DEMO (`member-p`) moves an EPFO member ID into the trust; RAVI DEMO (`member-r`) moves his PF
  out of the trust — `tests/e2e/test_exempted_members.py`. The balance sheet names `PAYABLE_TO_TRUSTS`.
