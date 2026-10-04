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
| **P2.11c** | Appeals (7-I) with the 7-O pre-deposit, the legal-case register and court orders, 26B membership disputes, prosecution | Done |
| **P2.11d** | Recovery (Recovery Manual, 08/12/2023): recovery certificates (8B–8E), 8F garnishee, attachment, sale, receiver, arrest (records only); HO reports on proceedings and recovery; PMVBRY exclusions from open inquiries | Done |
| **P2.12h** | Explore pages: the stakeholder chart by EPFO's hierarchy, each lifecycle as a network of stakeholders and steps with how far it is built, and the user manuals published into the portal — all linked from the home page | Done |
| **P2.12a** | Member and tax: Form 16A, the office's TDS computation; UAN allotment and activation (mock Aadhaar face / OTP); inoperative accounts — the public helpdesk search, verification through co-workers, reactivation in the AO / APFC bands | **Done** (1 Oct 2026) |
| **P2.12b** | Employer lifecycle: voluntary coverage, closure, transfer to another office; contractors tagging ECR members to a principal employer and the principal's view of contractor compliance; MCA and Shram Suvidha registration feeds (mock) | **Done** (1 Oct 2026) |
| **P2.12c** | Pension office: deciding a validated higher-pension option and the PF → pension fund transfer after the dues; Special 10D; bank-wise disbursement lists; the actuarial extract | **Done** (1 Oct 2026) |
| **P2.12d** | Oversight: internal audit reports, paras, replies and decisions; DPDP data-principal requests; RTI replies; the CPGRAMS feed (mock) | **Done** (1 Oct 2026) |
| **P2.12e** | Head office reporting: balance sheet, investments, board packs (aggregates), fund-manager position feed (mock) | **Done** (1 Oct 2026) |
| **P2.12f** | The rest: DR replication status and failover drill, training sandboxes, Nidhi Aapke Nikat camp requests, totalisation claims and the foreign agency's CoC check, the composite death claim | **Done** (1 Oct 2026) |
| **P2.12g** | Menu clean-up: screens already built linked from their menus (Composite claim, Know Your Pension Payee Bank, Change Password); every other item without a screen says why — planned (with the slice), awaiting EPFO's definition, or not in the POC | **Done** (1 Oct 2026) |
| P2.25 | Sources checked: the *to verify* rule values, and the Code on Social Security — which turned up the 2026 Schemes and the ₹25,000 ceiling (findings below) | Done (findings) |
| P2.26 | The Code's transition. **a**: ₹25,000 wage ceiling from 17 Sep 2026 (a second rule-set version; September split by days in one ECR; pension membership flagged; Form 10C at the ceiling of the exit date); VISHWAS, 2026's real terms; instalments by the circulars (powers, guarantee, Head Office beyond 36, withdrawn on default). **b**: EEC, 2026. **c**: the 2026 Schemes' withdrawal, EPS withdrawal-benefit and EDLI rules (needs the gazette text) | a, b: Done; c: Planned |
| P2.27 | Contracts and copies: every event checked against its contract in every unit test; a cross-service consistency check of the facts services copy, run after the end-to-end suite in CI | Done |
| P2.13 | Small gaps: disablement pension (EPS para 15); zonal freezing (categories B and C) and zonal ACC decisions above the RO's limits; district office queues; PPO and UAN card issued to DigiLocker (mock) | Done (a: disablement pension; b: zone and Head Office decide instalments beyond a region's power — zonal freezing and grievance escalation were already built); district queues dropped; DigiLocker moved to P2.21 |
| P2.14 | The exempted trust's lifecycle: annual audit filing and the exemption cell's review; surrender and cancellation (RPFC report → ZO → HO → the Exempted Establishments Committee → the appropriate Government); HO's decision; past accumulations transferred in bulk and reconciled with the receipts | Done |
| P2.15a | PMVBRY (Pradhan Mantri Viksit Bharat Rozgar Yojana): Part A for first timers, Part B for employers adding jobs, the disbursement run and the dashboard — from the scheme guidelines and EPFO's SOP for calculating incentives | Done |
| P2.15b | SMS and e-mail for in-app notices through a mock gateway — preferences and language, essential messages, retries, delivery evidence, the PRO desk's follow-up | Done |
| P2.16 | Gig and platform workers (Code on Social Security, 2020): aggregators registered, a turnover-based contribution return (1–2% of turnover, capped at 5% of payments to the workers, in the rule set), workers linked by e-Shram number to a UAN, reconciliation | Planned — design only until the scheme is notified |
| P2.17 | Insolvency: a watchlist from EPFO's own signals (ECR stopping, defaults, MCA status), IBBI announcements matched to the establishment, claim deadlines, dues frozen (7A; damages and interest kept apart), the resolution plan checked for PF dues in full, liquidation claims outside the estate (IBC s.36(4)(a)(iii)), recovery measured | Planned (links to P2.11) |
| P2.18 | EPF to NPS: the PF leg paid to the member's NPS Tier I (PRAN, KYC match, the trustee bank through the CRA — mock); the EPS leg cannot move — a Scheme Certificate or the withdrawal benefit | Planned (needs PFRDA's circular) |
| P2.19 | Edge cases as tests first, then the fixes: death during a transfer or claim; minor nominee or no nomination; two UANs to merge; court-ordered back wages after exit; 58 in service; a re-employed pensioner; family pension to a dependent parent or a disabled child; attachment orders refused; mergers without a break; a vanished contractor (s.8A); partial payment; exemption cancelled mid-transfer; returned payments after a bank merger; one bank account for many members; identity mismatches; members abroad without Aadhaar; unclaimed balances | a (money at risk: death, short cheque, re-employed pensioner, child pension to 25, back wages): Done; c (erroneous EPS contributions rectified, circular WSU/2025/E-961539 of 19 Dec 2025): Done; the rest planned |
| P2.20 | Navigation and findability: side or top menu (per user, by role), menu search (Ctrl+K), the empty menu headings wired to existing screens; a text-size control (to 150%) for senior citizens; later task-based member and employer menus with the legacy ones behind a toggle | Done (task-based menus later) |
| P2.21 | Data held, not asked: pre-filled claims, automatic transfer when a new member ID appears, the pension case opened at 58 and on death, settlement by default for low risk with sampled audits | a (transfer unasked; claims and pension offered filled in): Done; b (death from the civil registry, claims offered to the nominee, sampled audit of automatic settlements, DigiLocker): Done |
| P2.22 | Real-time contributions: a per-pay-run contribution API and a conformance sandbox for payroll vendors (the ECR kept as a format); a due-date option to model contributions paid with wages | Done (pay runs adding up into the ECR, the sandbox, employer-authorised providers; the payday due date dropped) |
| P2.23 | Retirement view: one forecast across PF and pension with VPF what-if and replacement rate; every rejection saying what fixes it | a (retirement view, VPF what-if): Done; b (every rejection and refusal saying what fixes it): Done |
| P2.24 | Trust and governance: authorised representatives (guardian, agent) with consented scope; published service standards with live performance; an independent review tier; rule-change simulation; interest-sustainability model | Planned |
| P2.28 | Production UX foundations: task-based journeys (one task per page, check-your-answers, a confirmation with a reference, a receipt with a QR to verify it); plain language with no internal codes and complete Hindi; forms that check as you type and list errors at the top; officers' queues with sorting, filters, deadlines, bulk actions and the documents beside the decision; risk-based step-up; a component library on UX4G and GIGW 3.0; WCAG 2.1 AA verified (axe in CI, screen reader, 400% zoom); phone layouts and per-page code; loading, empty and error states; usability sessions and privacy-safe analytics. First: the member's claim, KYC and transfer journeys | a (the claim journey, the first shared components): Done; b (changing the bank account): Done; c (the transfer): Done; d–f (the work queue, the case page, axe checks): Done; g (phone tables), h (a receipt anyone can check): Done; next: risk-based step-up; the old claim form retired once the UI suites use the journey |
| P2.29 | A README for the repository (there is none): says up front that this is a vibe-coded app — written by AI coding agents (Claude Code, Codex, agy) at a person's direction, not hand-written or reviewed as production code — and a synthetic demonstration, not an EPFO system; what it covers (the stakeholders, journeys and the official sources it follows), how to run it (`make up`, `make migrate`, `make seed`, the personas), how it is tested, and a map of `docs/`. With a nod to the name: it should have been *pf-vibe* | Done |
| P2.30 | Order-safe copies: every service's copy of another's facts kept by the event's time (or a version), so events about one record applied in either order — the consumer handles up to ten at once and re-queues a failed one — never leave an older state; a test per copy delivering them out of order. Found when compliance-service kept a withdrawn 7A demand OPEN (fixed there) | Planned |

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

## P2.25 — findings (2 October 2026)

**The values marked *to verify*:**
- *7B review: 45 days* — confirmed: an application in Form 9 within 45 days of the 7A order (Compliance Manual 2.7.6).
- *Appeal: 60 + 60 days* — confirmed: EPF Appellate Tribunal (Procedure) Rules, 1997, rule 7(2); the extension is
  capped, so nothing is condoned after 120 days.
- *Pre-deposit: 75%* — confirmed: s.7-O; the Tribunal may waive or reduce it for reasons recorded.
- *72 instalments* — confirmed as the outer limit, with conditions the POC does not enforce (Recovery Manual, circulars
  of 11.4.2012, 11.02.2014, 7.4.2006). Up to 36 is the norm. Beyond 36 only for unexempted establishments, with no
  second facility after a default, and a revolving bank guarantee for six instalments. Each instalment is paid with that
  month's 7Q interest and current dues. A default withdraws the facility without notice. More than 36 instalments or
  over ₹50 lakh goes to Head Office. Who grants, by arrears: the RPFC-II in charge of an SRO up to ₹10 lakh, the RPFC-I up
  to ₹25 lakh, the zone's ACC up to ₹50 lakh, the CPFC above. **Gap:** the POC lets the OIC grant up to 72 for any
  amount.

**What the check found besides** (official: PIB releases 2310973 of 16 Sep 2026, 2313829 of 23 Sep 2026 and 2285666 of
17 Jul 2026; secondary: KPMG's flash of 2 Jul 2026, BDO's alert, an FAQ on the ceiling circulating among employers —
the official texts of the Schemes and the gazette notification were not reachable, and are to be read before the
figures marked *secondary* are relied on):
- **The Code has applied to provident funds since 21 November 2025**, and on **29 June 2026** the Ministry notified the
  **EPF Scheme, 2026** (G.S.R. 525(E)), the **EDLI Scheme, 2026** (526(E)) and the **EPS, 2026** (527(E)). They supersede
  the 1952, 1976 and 1995 Schemes: the POC's citations of their paragraphs are now history. *Wages* is s.2(88) of the
  Code: basic, DA and retaining allowance, with excluded components above half of the remuneration counted back.
- **The wage ceiling is ₹25,000 from 17 September 2026** (S.O. 5109(E); official). Mandatory EPF, EPS and EDLI cover
  reaches employees with wages up to ₹25,000. The maximum EPS share rises from ₹1,250 to ₹2,083 (official). *Secondary
  (the FAQ):* September 2026 is one ECR, split by days at the old and new ceilings. Employees in the ₹15,000–25,000 band
  are enrolled from 17 September by the employer, without an application, and EPF-only members in the band join EPS
  from that date. The Government's 1.16% stays on ₹15,000. Part A of PMVBRY stays capped at ₹15,000, and the EDLI maximum
  stays at ₹7 lakh. **Gap:** the POC's ceiling is ₹15,000, and its rule sets change only at the start of a wage month.
- **VISHWAS, 2026** (official): damages for defaults before 14 June 2024 are recalculated at 0.25% a month (up to two
  months), 0.50% (two to under four) and 1% (four or more). All 7Q interest must be paid first, further appeal is given
  up, fraud is excluded, and applications go online with a DSC or e-sign, from 29 June to 28 December 2026. **Gap:**
  the POC settles at a flat 30%.
- **EEC, 2026** (*secondary*): employers may enrol employees who joined between 1 April 2009 and 31 March 2026 and were
  left out, until 31 October 2026. **AMNESTY, 2026**: unrecognised PF trusts may regularise. This is the menu item
  *EEC-2026/VISHWAS*.
- **Other changes in the 2026 Schemes** (*secondary*):
  - partial withdrawal after 12 months of membership, keeping 25% of the contributions;
  - final settlement 12 months after leaving (the POC: 2);
  - the EPS withdrawal benefit 36 months after the last contribution (the POC: 2);
  - EDLI with a base benefit of ₹50,000–1 lakh without 12 months' service, and ₹2.5–7 lakh with it;
  - a late fee of ₹500 a day for returns;
  - Forms X, XI and XII for contractors;
  - 9.49% to EPS for members on higher wages.

## Pending items reviewed (2 October 2026)

Each pending item weighed for value, cost and whether its source is in hand; the order that follows.

- **Unblocked, do next.** P2.14's bulk transfer and VDR reconciliation waited for VDR entries, which exist now. P2.13's
  disablement pension (EPS para 15) and zonal freezing / escalation complete rules the POC already enforces. P2.19,
  ranked by money at risk: death during a transfer or claim, a partial challan's allocation, a re-employed pensioner,
  family pension for a disabled child, back wages after exit first; UAN merge, bank merger and unclaimed balances later.
  *58 in service* already works (the ECR split stops EPS at 58). P2.23 reads data the system has.
- **Rescoped.** P2.21 extends what exists (auto-settlement below a limit, auto-transfer) rather than building it; the
  pension case opened on death needs a mock civil-registry feed; DigiLocker (from P2.13) joins it. P2.22 keeps per-pay-run
  submissions that add up into the ECR (one record of what was paid) and drops the payday due date (a foreign policy, not
  India's). P2.24 keeps service standards (from EPFO's Citizen's Charter), rule-change simulation on balances and
  authorised representatives; drops an independent review tier (EPFO has none) and interest sustainability (needs
  investment data, out of scope). P2.17 keeps the watchlist, the claim against its deadline and recovery stopped by the
  moratorium (like a court's stay, P2.11d); drops checking resolution plans (legal judgement).
- **Held for the source.** P2.16 (who administers the gig workers' fund) and P2.18 (PFRDA's circular). P2.13's district
  office queues dropped (district offices facilitate; they do not decide cases).
- **Added.** P2.25: the values marked *to verify*, and the Code on Social Security's definition of wages, which would
  change the contribution base more than anything in P2.16–P2.24. A cross-service consistency checker and event
  contract tests in CI get a slice of their own (P2.14's status column showed why).
- **Order.** P2.25 → P2.26 (the Code's transition: money is wrong until it is done) → the P2.14 leftovers → P2.13 core → P2.19 (money at risk) → consistency checks → P2.21 → P2.23 →
  P2.22 (adapter) → P2.24 and P2.17 (trimmed); P2.16 and P2.18 wait.

## P2.20 – P2.24 — plan (what a mature social-security system does)

A comparison with systems abroad (Australia's Single Touch Payroll, SuperStream and stapled funds; the UK's Real Time
Information, State Pension forecast and Pensions Dashboards; Singapore's CPF; the US Social Security statement; Estonia's
and the Netherlands' once-only and proactive services — from general knowledge, to be checked before a slice relies on
a detail) shows the gap is less in screens than in how the system works: real-time, data already held, proactive,
explained. The slices: P2.20 navigation (side / top, search); P2.21 pre-filled and proactive claims; P2.22 per-pay-run
contributions; P2.23 a retirement forecast and decisions that say how to fix them; P2.24 representatives, service
standards, independent review, rule simulation. Alongside: a cross-service consistency checker, event contract tests and
accessibility checks in CI.

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

## P2.11d — how it is built

Source: the EPFO *Recovery Manual* (08/12/2023): general procedures (1.5), attachment and sale (2–4), receiver (5), arrest
and detention (6), s.8F, the instalment circulars.

- **The certificate (s.8B)**: on a passed order whose dues are still unpaid after the 15 days it allows, the officer who
  passed it (or the RPFC-I) certifies them to the office's Recovery Officer (new persona `ro-recovery`). One open
  certificate per order.
- **Execution** (`/office/recovery`): the demand notice EPFCP-1 (15 days to pay); then attachment of movable or immovable
  property, debts or shares — earlier only with the reasons recorded (the defaulter is likely to conceal or remove it);
  sale at or above the reserve price, the proceeds realised; a receiver; arrest — a notice to show cause (EPFCP-25) and a
  hearing before a detention order, which needs one of the Manual's grounds (dishonest transfer; the means to pay and a
  refusal); a warrant for not appearing; release. All are records: no property, warrant or prison is real. The RPFC-I
  grants instalments (at most 72, *illustrative*), during which coercive steps wait; a court's stay on the order halts
  them too (P2.11c's register).
- **Section 8F**: the officer directs a bank or a debtor of the employer to pay EPFO; what it pays is realised against
  the certificate.
- **Into the ledger**: every realisation is `RecoveryRealised.v1`; contribution-service applies it to the certificate's
  demands (part-payments tracked in `realised_paise`, a DUES_7A share split across A/c 1, 10, 21 and 2 in the order's
  proportions), one journal per reference, the demand PAID when fully realised (written by agy; the duplicate consumer
  route it added was removed, and the demands are locked while a realisation is applied — three arriving together had
  each read the same balance).
- **PMVBRY**: Part B is withheld from an establishment while a 7A / 7C / 26B inquiry is pending or an order's dues are
  unpaid (guidelines 6.2.3), from `InquiryRegistered.v1` / `InquiryOrderPassed.v1` and the demand's state — no longer a
  seeded reason. Seed: Demo Engineering Works' 7A order of June 2026, unpaid.
- **HO reports** (`/ho/compliance-reports`, `ho-compliance`, `ho-recovery`; moved from reporting-service to
  compliance-service, which holds the data): inquiries by section and stage, pending by office, orders overdue,
  disposal and days to order, legal cases; certificates, certified / realised / outstanding, realised by mode, stayed,
  in instalments, older than a year. The employer sees its recovery certificates on `/employer/proceedings`.

## P2.11c — how it is built

Sources: the Compliance Manual (ch. 4 — 26B; ch. 5 — prosecution; 2.9 — remanded cases) and the Act for appeals (s.7-I,
s.7-O). The appeal period (60 days, 60 more condonable) and the 75% pre-deposit are in the rule set marked *to verify*.

- **26B membership disputes** (`/office/compliance/membership-disputes`, the SS, one-time code): the trigger (an
  employee's or a union's complaint, an inspector's observation, a 7A inquiry) and the employees in dispute; allotted
  to an RPFC-II or above whatever the size; notice and hearings as for 7A; the order decides each employee — a member
  from a date, or not eligible — and raises no demand (non-compliance leads to a 7A inquiry, para 4.6.3).
- **Appeals** (Legal Cell, new persona `ro-legal`, role `fo.legal`): an appeal under s.7-I against a 7A / 7B / 7C / 14B
  order (7Q interest is not appealable there) goes on the register — within the period or with delay condonation; it
  bars a 7B review (s.7B(1)). The s.7-O pre-deposit (75% of the amount) is recorded once per reference; the Tribunal's
  reduction or waiver lowers the share; the appeal is heard only when it is met.
- **The legal register** (`/office/legal`): appeals, writs, NCLT matters, prosecutions in court, with every order. An
  order's effect: an interim stay (recovery held) or its vacation; *allowed* — the demand withdrawn and the case closed
  on appeal; *partly allowed* — the demand replaced by the amount left; *remanded* — the order withdrawn and the case
  heard again by an officer one level higher (para 2.9); conviction or acquittal for a prosecution.
- **Prosecution**: the circle officer's show-cause notice (at least 7 working days; for unpaid dues only after a 7A
  order whose dues stay unpaid 15 days on — para 5.2.2 iii); the employer replies (`/employer/proceedings`); the RPFC
  (OIC) sanctions after the reply or once its time has run; the Enforcement Officer — an Inspector, s.14AC — files the
  complaint within 7 days, which enters the legal register; or the circle officer drops it when the default is set right.
- Events: `LegalCaseRegistered.v1`, `LegalOrderRecorded.v1`, `ProsecutionStepTaken.v1`. The Legal Cell's screen was
  written by agy and reviewed; the rest here.

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

## P2.20 — how it is built

- **Side or top.** The same menu definitions (`src/data/navigation.ts`) draw either the bar across the top or a tree
  down the side. Office, zone, head office and other staff roles get the side menu by default (their bar wrapped onto
  two lines); members, employers and the public keep the top bar. Each user can switch in the header; the choice is
  kept in the browser (`navLayout.ts`, with the role's default if storage is blocked). On a phone both are the same
  drawer, so the switch is hidden there.
- **The side tree.** The group holding the current page opens, the others fold; the current item is marked
  (`aria-current`); a filter narrows every group at once. Items the POC does not build are hidden unless *Show items
  not built* is ticked — the top bar still shows them greyed, as before.
- **Find a screen.** Ctrl+K (⌘K) or the header button searches every working menu item of the role; the arrows choose,
  Enter opens, Escape closes (`MenuSearch.tsx`, a dialog with a combobox and a listbox).
- **Empty headings.** The employer's *Admin* opens users and change requests; *EEC-2026/VISHWAS* links VISHWAS and
  marks EEC-2026 planned until its notification is read; the office *Dashboard* opens the role's home, *Services* the
  PRO counter for PRO roles, *Admin* says postings come from HR; the pension office's *Services* opens enquiries and
  overdue life certificates.
- **Text size** (added after a request for senior citizens): *A− · A · A+* in the header sets the page's base size —
  100, 115, 130 or 150% — which every rem-sized style follows; kept in the browser and applied before the first paint.
  At 150% the header's controls wrap onto a second row; no page scrolls sideways on a desktop or a phone.
- Left for later: task-based member and employer menus (with the legacy ones behind a toggle), keeping the choice in
  the user's profile rather than the browser.

## P2.26a — how it is built

- **The ₹25,000 ceiling as a rule-set version.** `config/demo-rules.yaml` gains `revisions:` — versions already decided
  after the baseline, each the baseline with some keys changed. The first is `demo-rules-2026.2` from 17 Sep 2026: EPS and
  EDLI ceilings and the pensionable salary cap ₹25,000; the higher-pension ceiling table extended. platform-service's seed
  publishes it as an approval would (stored, `PolicyPublished.v1` to every service), so it shows in Policy administration
  with the baseline superseded. `baseline()` leaves `revisions` out.
- **September 2026: one ECR, split by days.** A version can now start inside a wage month. `rules_for_wage_month` takes
  the version on the first day and, when another starts within the month, lists each day's ceilings
  (`contribution.ceiling_periods`); `capped_wages` weighs a member's wages by them — ₹20,000 in September is ₹15,000 x
  16/30 + ₹20,000 x 14/30 = ₹17,333.33, the FAQ's figure (rounded up to the rupee). The ECR check bounds each row's EPS and
  EDLI wages by that; other months are checked as before.
- **The newly covered band.** A row whose wages are within the ceiling but with no EPS wages, for a member under 58, gets
  the warning `W-EPS-MEMBERSHIP` — from 17 Sep 2026 that includes wages up to ₹25,000 (EPF-only members join EPS).
- **Form 10C** takes the Table D wages at the ceiling in force on the exit date (₹15,000 before 17 Sep 2026).
- **VISHWAS, 2026** replaces the illustrative 30%: a 14B demand is eligible when its default is before 14 June 2024, no 7Q
  interest on the same default is open, and the application falls in 29 June – 28 December 2026. The damages are
  recalculated from the arrears in the demand's working: arrears x rate x months of default (days x 12 / 365) — 0.25% a
  month up to two months, 0.50% to under four, 1% beyond — and never more than levied. The employer undertakes not to
  appeal; the screen shows each demand's recalculation or why it is not eligible. A damages order (its own demand, listing
  the defaults it covers with their automatic damages) is recalculated default by default, the amount paid late worked
  back from the automatic damages at the band's yearly rate — exact to a few rupees, as those damages were rounded.
- **Instalments by the circulars.** Up to 36 by the officer whose power covers the arrears (RPFC-II ₹10 lakh, RPFC-I
  ₹25 lakh by the officer's recorded rank; the zone's ACC ₹50 lakh); more than 36 (at most 72) or more arrears, the CPFC.
  A revolving bank guarantee of one instalment (six beyond 36). The Recovery Officer records a missed instalment: the
  facility is withdrawn without notice and recovery resumes; no facility beyond 36 for an establishment that defaulted
  before. New activities: `F06.instalments_zo`, `F06.instalments_ho`.
- Left: EEC, 2026 (P2.26b; official terms in PIB 2300475); the 2026 Schemes' withdrawal and EDLI rules (P2.26c); the
  rule that 14B damages are 1% a month for defaults from 14 June 2024 (to verify); the 2026 Scheme's exemption of
  unexempted-only for 72 instalments (compliance-service does not know exemption yet); screens for the zone and Head
  Office to grant instalments (the API is ready); September 2026 at the old ceiling in the higher-pension dues.

## P2.26b — how it is built

EEC, 2026 (PIB 2300475 of 17 Aug 2026; notified with the EPF Scheme, 2026): from 1 July to 31 October 2026 an employer may
enrol employees left out of EPF between 1 April 2009 and 31 March 2026 who still work for it.
- **Register, then declare.** The employee is registered through the usual onboarding (a face-authenticated UAN, mocked),
  with the real date of joining. They become a candidate when active, joined in the period and nothing was ever
  contributed for them. The signatory gives the monthly wages and whether the employee's share was deducted.
- **The dues, month by month** (contribution-service `eec_routes.py`): from the month of joining (not before April 2009)
  to March 2026, at each month's ceiling (₹6,500, then ₹15,000 from September 2014). The employer's 12% (8.33% to EPS
  under 58, the rest to EPF), EDLI and administrative charges; the employee's 12% only if it was deducted, otherwise
  waived; 7Q interest at the late-payment rate from each month's due date; and ₹100 lump-sum damages. Wages above the
  ceiling at joining are refused (an excluded employee, not one left out). `GET …/eec-declarations/dues` shows them first.
- **One challan.** Declaring (step-up for the amount) raises a challan of kind `EEC` (`ChallanGenerated.v1` now allows
  it); paying it credits the member's EPF account, the pension and EDLI funds, the charges, interest and damages in one
  balanced journal. The employee's ledger shows the period as one line. One declaration per member ID.
- **Screens.** Returns › *EEC, 2026* (menu *EEC-2026/VISHWAS*): the terms, the declarations, and a form that works out
  the dues before declaring.
- Simplified: one monthly wage for the whole period (the real declaration is month-wise ECRs); the 2026 Scheme's other
  conditions for the campaign are not read yet (only the PIB release).

## P2.14 completed — past accumulations: bulk transfer and receipts reconciliation

From the SOP on surrender of exemption (Dec 2023, (ix)–(xxiv)) and the SOP on cancellation ((h)).
- **PAST ACCUM BULK TRANSFER** is the ingestion built in P2.12: the cancellation SOP's "bulk transfer in" of a trust's past
  accumulations, every member credited in one batch against the trust transfer receivable. The menu item opens it for the
  exemption cell; the two planned endpoints that duplicated it (`…/past-accumulation-transfers`,
  `…/past-accumulation-bulk-transfers`) are dropped from the catalogue.
- **PAST ACCUM VDR RECO** (contribution-service `pa_reco_routes.py`, Office › Ledger): the money arrives in parts — the
  cash component by demand draft (the cashier's VDR entry), the SDS balance and the permitted securities (HO's Investment
  Division confirms each with a reference). DA (Accounts) proposes the receipts with the trust's Form SE-6 total; the APFC
  approves with step-up (not the proposer). Each receipt is a journal clearing the receivable (bank collection, SDS or
  securities received); the demand draft's VDR entry is marked reconciled. The trust is *reconciled* when what was received
  equals what was credited and the SE-6 total, otherwise *short* by what is still to come. A receipt or a reference is used
  once; receipts cannot exceed what was credited (the remaining members are ingested first).
- Simplified: one approval (the SOP has DA → APFC (Cash) → RPFC-II (FA) with OTP); the 14B / 7Q on accumulations received
  after the 30 days are noted on ingestion, not yet raised as demands.

## P2.13a — how it is built (disablement pension)

From the Pension Manual (Manual of Accounting Procedure — EPS, 1995: 2.5.2.3–2.5.2.4, 2.7 and the guidelines in Figure 6).
- **Who.** A member permanently and totally incapacitated for the work done at the time, while in service: the disablement
  on or after 1 April 1993 and before 58, the exit recorded by the employer as *permanent disablement* (the employer's exit
  form already offered it; the reason now reaches pension-service with the exit and is kept on the EPS account), at least
  one month's contribution. A Medical Board's certificate, or a disability certificate under the RPwD Act, 2016, saying
  *permanently and totally unfit*.
- **How much, from when.** The formula as if retiring on the day of invalidation — no minimum service, no age limit, no
  reduction for age — and not less than the minimum pension; from the day after the exit, for life (then family pension).
  `pension_on(..., disablement=True)`; the worksheet uses it for a claim of kind `DISABLED`, and a pension in payment keeps
  `pension_kind = DISABLED` so a later revision applies no age test.
- **Screens.** The member's Form 10D page offers *Apply for a disablement pension* with the date and the certificate; the
  pension desks see the claim marked, with the certificate to scrutinise (doubts to the RPFC in charge, 2.7.5).
- **Demo.** New persona `member-disabled` (SURESH DEMO): 7 years at Demo Engineering Works, left on 20 Aug 2026 — no
  monthly pension on ordinary terms, ₹1,500 a month as a disablement pension (₹15,000 x 7 / 70).
- Not built: the RPFC referring the member to a Medical Board (the certificate is taken as given); the case of disablement
  after 50 with 10 years' service, where an early pension needs no certificate (that route already exists).

## P2.13b — how it is built (zone and Head Office above a region's limits)

- **Already built, flags cleared.** Zonal freezing of categories B and C (`F07.freeze_zo`, through the process engine since
  Phase 1, with its tests) and grievances escalated to the zone (`F08.escalate`) worked; the activity map still marked them
  future. The zone dashboard (`F13.zo`) worked too.
- **Instalments beyond the region's power** (Recovery Manual, circulars of 7.4.2006 and 11.02.2014 para 4). The OIC refers a
  request — more arrears than the officer's rank may grant, or more than 36 instalments — with a note; it goes to the zone's
  ACC when the arrears are within ₹50 lakh and at most 36 instalments are asked, else to Head Office. The OIC cannot refer
  what is within the OIC's power. *Instalment referrals* (`/zo/instalments`, for `zo.acc` and `ho.cpfc`) lists them with
  the arrears outstanding, and grants (the instalment rules of P2.26a apply: the guarantee, no second facility beyond 36)
  or refuses with reasons; recovery goes on after a refusal.

## P2.19a — how it is built (edge cases where money is at risk)

Tests first; each found a gap that is now closed.
- **Death during a claim or transfer.** A death in service recorded the date only; the member's own claims went on — an
  approved advance could be paid to a dead member's account while the nominees claimed the same balance. Now the exit for
  death closes every open claim of the member not yet with the bank (advances, final settlement, transfers), with the
  reason, and a debited claim is credited back (ClaimDecided REJECTED); the nominees claim through Form 20. Death claims
  are untouched; a payment already at the bank completes (it becomes part of the estate).
- **A short cheque.** A cheque or DD for less than the TRRN is refused against it — one challan, one payment — and stays
  unallocated; nothing is posted (already so; now tested).
- **A re-employed pensioner.** Nothing stopped a member drawing an EPS pension from contributing to EPS again. Pension-service
  now announces a pension in payment (`PpoIssued.v1`, with the UAN, on dispatch — the contract existed, nothing emitted it);
  contribution-service keeps `eps_pensioners` (also seeded); the ECR refuses pension wages for such a member
  (`E-EPS-PENSIONER`, correctable: the employer's whole 12% to EPF). A family pension does not count.
- **Family pension to a disabled child.** Children's pension had no end: it now ends with the month the child turns 25
  (Pension Manual 2.10.5) and the pension is marked ceased; a child must be under 25 on the member's death to apply
  (2.10.1.1); a disabled child (RPwD certificate; `family_members.disabled`) is paid for life (2.13.10).
- **Back wages after an exit.** The ECR accepted rows for months after a member's exit without a word. Now they are refused
  (`E-AFTER-EXIT`) with the way forward: a court-ordered reinstatement is recorded by correcting the exit date (the
  employer's exit correction, approved), then a supplementary return for those months. Not built: clearing an exit for a
  member reinstated and still working; interest on back wages; the pension recomputed.

## P2.27 — how it is built (contracts and copies)

- **Every event against its contract.** `add_event` (common-persistence) now checks each envelope against
  `contracts/events/<Event>.schema.json` wherever the contracts can be found — a checkout, so every service's unit tests,
  locally and in CI's `make test` (jsonschema is in the package's test extras). A deployed service has no contracts and
  skips it. A mismatch fails the producer's own test and prints `CONTRACT VIOLATION: …` naming each difference.
- **What it found** — events that had drifted from their contracts, never noticed because no consumer checks:
  - stale contracts, corrected to what producers and consumers exchange: `DemandStateChanged` (kind `DUES_7A`, state
    `WITHDRAWN`), `TransferPosted` (a trust leg's source, destination and service), `MemberChangeApproved` (parameters are
    `{parameter, value}`), `InterestCredited` (postings are objects), `NotificationRequested` (pension-service sends it),
    the ledger's account codes (trust receivable, SDS and securities received, interest and TDS accounts…), and the
    aggregate types of seven events;
  - producers corrected: `EpsServiceTransferred` (aggregate `transfer`), `TdsStatementFiled` (a count of deductees, not a
    list of members), `ExemptionShowCauseIssued` (now carries its grounds).
- **Copies agree** (`scripts/consistency_check.py`, `make consistency`; CI runs it after the end-to-end suite on its fresh
  stack). Read-only, it compares an exempted establishment's status and end date (employer vs contribution, claim,
  pension), a member ID's date of exit (member vs contribution, claim, pension), a member ID's balance (the ledger vs the
  claims projection), each demand's state and amount (contribution vs compliance), and the published rule sets (platform
  vs every service that keeps them). On first run it found:
  - **EEC credits never reached claim-service** (P2.26b) — the ledger held them, the claims projection did not, so the
    member could not claim them. The payment now announces the credit (`LedgerAdjusted.v1`, `EEC_ARREARS`).
  - **reporting-service never received a published rule set** — it applied the baseline whatever was published. It now
    keeps the published versions like the other services. (Two reporting screens still read the baseline directly: the
    claims SLA on the office dashboard and the due day in the compliance summary — to move to the version in force.)

## P2.21a — how it is built (transfer unasked, claims offered filled in)

- **The transfer happens by itself.** EPFO already offers auto-transfer; here the member had to confirm it. Now, with the
  rule switch `claims.auto_transfer_automatic`, the first contribution posted on a member's primary member ID moves the
  balances of the member's exited member IDs into it — no request (claim-service, on `ContributionPosted.v1`), the same
  conditions as before: a verified Aadhaar, no claim running on the old ID. The member is told (`AUTO_TRANSFER_STARTED`,
  English and Hindi). Anything that blocks it is shown as before, for the member to confirm later.
- **What the member may claim is offered, filled in.** The home page's *To do* lists each final settlement and pension
  withdrawal the member is now eligible for, with the amount and member ID in the link; the claim form opens with them
  filled in, so the member reviews and confirms (step-up as always). At 58, with enough service and out of service, the
  monthly pension is offered too (Form 10D — service and wages are on record), until an application is on file.
- Planned (P2.21b): the pension case opened on death from a civil-registry feed (mock), a sampled audit of claims settled
  automatically, and the PPO and UAN card pushed to DigiLocker (mock).

## P2.21b — how it is built (death from the registry, claims offered, sampled audit, DigiLocker)

Sources: the Registration of Births and Deaths (Amendment) Act, 2023 — the Registrar General keeps a national database
of registered deaths, which may be shared, with the Central Government's approval, with authorities keeping the
databases listed in the Act "and such other databases as may be notified" (EPFO is not named: it would need that
notification); EPFO's notice that the UAN card, the PPO and the scheme certificate are in DigiLocker.

- **The death comes to EPFO.** The Civil Registration System (mock; a machine login `crs-demo`, role `ext.crs`) sends
  each registered death, signed (`POST /integrations/crs/death-registrations`). member-service matches it to a member by
  the Aadhaar reference — every UAN of that person — or, without one, by name and date of birth when they point at one
  person. The member's open member IDs close as *death while in service*, marked by the civil registry, and the death is
  announced (`MemberDeathRecorded.v1`). A repeated registration is answered with the first outcome; a second registration
  of a death already on record changes nothing; a record that matches nobody, or two people, is kept for the PRO and the
  DA (Pension) (*Deaths from the civil registry*). An employer's death exit announces the death the same way.
- **The nominee is offered the claims, worked out.** claim-service records the death (also for a member who had left
  service) and closes the member's own unpaid claims as before (P2.19a). The nominee with a login sees *What you can
  claim*: Form 20 (the balance) and Form 5IF (the EDLI benefit under the rules in force) with their workings, filed as
  one composite claim with one confirmation; a form already filed is shown as filed. pension-service records the date of
  death, so the spouse or child applies for the family pension (Form 10D) at once, and stops a pension the member was
  drawing from the death (any pension credited after it is recovered) — the member's own PPO only, not a family pension
  on the same UAN. New persona `claimant-b` (MEENA DEMO), the wife and nominee of VIJAY DEMO (UAN 100000000916, in
  service at Demo Engineering Works). `scripts/crs_death_feed.py` plays the registry.
- **Automatic settlements are post-audited by sample.** Claims settled with no officer in the loop are checked after the
  event: the Concurrent Audit Cell's daily extract flags one in five (illustrative) as `AUTO_SETTLEMENT_SAMPLE`, chosen by
  the claim number alone — the same claims on every download, and not something a member or officer can steer — and
  shows how many were settled and sampled; the auditor raises an alert to the office as for any flag. The claim decision
  now carries the settling office.
- **DigiLocker.** member-service issues the e-UAN card when a UAN is allotted (or when a member asks: *View › UAN card ›
  In your DigiLocker*) and the e-PPO when the member's pension is dispatched (`PpoIssued.v1`); a worker pushes them to
  DigiLocker (mock) and retries for an hour and a half while it is down, then marks the push failed (the member can ask
  again). The full UAN never leaves EPFO in the push.
- Not built: the real DigiLocker is a pull — EPFO, as issuer, answers DigiLocker's request for a document by its URI —
  and holds the scheme certificate too; the family pension's PPO, held by the widow or child (no member record here), is
  not pushed; a nominee without a login is not told (nominations hold no contact details); the sampling rate is a
  constant in audit-service, not in the published rules.


## P2.19c — how it is built: erroneous EPS contributions rectified

Source: EPFO Head Office circular No. WSU/2025/E-961539/Refund of erroneous contribution/42, 19 Dec 2025 (saved in
`../manuals/`). Employers have remitted pension (EPS) contributions for members not eligible for EPS, or none for members
who are; the circular fixes one rectification for each case, for unexempted and exempted establishments:

| Scenario | Establishment | Rectification | Money moved |
|---|---|---|---|
| I — EPS allowed to an ineligible member | Unexempted | EPFO works out the EPS remitted with interest at the declared rate; moves it A/c 10 → A/c 1; deletes the pension service | Within EPFO |
| I | Exempted (PF with a trust) | The same, worked out by EPFO; moved A/c 10 → the trust | EPFO → trust |
| II — EPS denied to an eligible member | Unexempted | EPFO works out the EPS due with interest at the declared rate; moves it A/c 1 → A/c 10; credits the pension service, with any non-contributory period | Within EPFO |
| II | Exempted | The trust works out the dues with interest at the trust's declared rate and moves them trust → A/c 10; EPFO credits the pension service | Trust → EPFO |

Built:

- **A rectification per member ID** (Office › Ledger › *EPS rectification*): the DA (Accounts) names the member ID, the
  scenario and the period, with a notesheet; the system works it out from the posted returns month by month — scenario I
  the EPS remitted, scenario II 8.33% of the wages up to that month's ceiling (₹15,000, ₹25,000 from 17 Sep 2026, by days
  in September 2026) — with simple interest from the month after each wage month at the rate declared for its year (the
  trust's declared rate when an exempted trust owes it). A period with nothing to rectify is refused; scenario II needs
  the employer share in A/c 1 to hold it.
- **The APFC approves** (one-time code; not the officer who worked it out): scenario I unexempted moves A/c 10 → the
  member's A/c 1 (employer share), exempted A/c 10 → the trust (payable); scenario II unexempted A/c 1 → A/c 10; exempted
  waits for the trust's remittance, which Cash records (the amount must match) before A/c 10 is credited. The member's
  PF follows (`LedgerAdjusted.v1`, `EPS_RECTIFICATION`); the passbook says what happened and under which circular.
- **The pension service follows** (`EpsRectified.v1`): scenario I deletes the member ID's pension service (the estimate
  counts none; Form 10D is refused with the reason and *claim the PF instead*); scenario II credits it.
- **Later returns follow**: a member ID found not eligible gets no pension wages — the return is refused with
  `E-EPS-NOT-ELIGIBLE` and corrected automatically, the employer's whole 12% to EPF; scenario II lifts it. The consistency
  check compares the two services' records of who is not eligible.
- Not built: finding the ineligible members automatically (wages on joining are not on record: the office starts the
  case, e.g. from Form 11 or an inspection); the non-contributory period credited separately (the service counts from
  joining to exit).

## P2.22 — how it is built (pay runs from payroll software)

Three agy runs in parallel worktrees to one written API contract (employer-service and the gateway; contribution-service;
the screens); the catalogue, events, realm and the e2e test done alongside. On review: event-contract checking, which one
run had switched off for employer-service's tests, switched back on (the contracts were on main); a provider sees only the
pay runs it sent.

- **The employer authorises the software.** The establishment's owner authorises a payroll provider from a directory
  (*Payroll software*; one-time code). It becomes a grant like an operator's — `payroll.submit` for that establishment —
  so the gateway binds the establishment for the provider's machine login exactly as for employer staff; revoking it
  (one-time code, a reason) cuts the provider off at once. Before this the B2B route could never bind an establishment.
- **Each pay run as it happens** (`POST /partners/payroll/pay-runs`): wages per member, checked row by row as an ECR row
  would be — a member of the establishment, wage order, the month's ceilings, no EPS for a pensioner or a member ID found
  not eligible, NCP days — refused whole when a row is wrong; the same run reference twice is stored once. A conformance
  sandbox checks a payload and stores nothing.
- **The ECR stays the one record.** The employer's operator sees the month's runs and each member's totals (*Pay runs*) and
  makes the ECR from them: each member's wages summed (EPS wages capped at the ceiling though the runs add past it), then
  approved by the signatory, submitted and paid as any ECR. Nothing reaches the ledger before the ECR is paid.
- Dropped: a due date on each payday (a foreign practice, not India's); the ECR's due date stands.

## P2.28g–h — how it is built (phone tables, a receipt anyone can check)

Two agy runs in parallel worktrees (the first attempt hit agy's usage quota and was re-run after the reset); merged with the
expected stylesheet conflict. One change on review: the public check does the same work whether or not the claim exists.

- **Phone tables** (P2.28g): up to 640px wide the claim list, the passbook and the work queue become one card per row,
  each value with its column's name — still `<table>` markup, so screen readers and tests read them as before.
- **A claim receipt** (P2.28h): *View and print receipt* from the confirmation and the claim page — what was claimed, when,
  by whom (UAN masked), and a 10-character code (an HMAC of the claim number, amount and date, from claim-service's
  secret) with a QR code of the public check. Anyone — a bank, an employer, a family member — can scan it
  (`/public/receipts/verify`, behind the demo challenge and rate limit): *Genuine receipt* with form, amount, date and
  status, or *This receipt could not be verified* — the same answer for a wrong code and an unknown claim.

## P2.28d–f — how it is built (the officers' screens, accessibility checks)

Three agy runs at once, each in its own git worktree and its own files (separate string files were committed first, so no
two runs edited the same one); merged with one expected conflict (both appended to the stylesheet — both kept). Bulk
approval was dropped from the plan: CITES has each officer scrutinise each case and generate its docket, and paying many
claims at once already exists (Cash's payment scroll).

- **The work queue** (P2.28d): counts by deadline (overdue, due today, this week), search by case, claim or subject, filters
  (kind, overdue only), sort (the soonest deadline first by default, amount, oldest), *Time left* in words ("Overdue by 2
  days", never colour alone), 25 a page, and the filters kept in the address so a view can be bookmarked.
- **The case page** (P2.28e): on a wide screen the evidence (summary, chain, docket, documents, analysis, history) on the
  left and the decision kept in view on the right; on a phone the decision after the evidence; an *At a glance* strip
  (amount, form, time left, the step of the chain, the advisory marker) and *Jump to your decision* for keyboard users.
- **Accessibility checks** (P2.28f): axe runs in the web tests over the three member journeys and the shared components
  (`vitest-axe`; colour contrast is left to a browser check, as jsdom cannot compute it). None found; a deliberately broken
  element must fail, so the check is known to be live.

## P2.28c — how it is built (moving an old account, Form 13)

Built by agy from a brief to copy the two journeys before it; nothing to change on review.

- **The transfer as three steps** (`/member/service/transfer/new`, *Move an old account step by step* on the service
  history): the old account by its employer and years, with about how much will move — or, when none can move, why for
  each (the exit not marked, with the way to mark it; already moved); the current account, preselected when there is one;
  check your answers; the one-time code; a confirmation with the request's reference and the three steps that follow
  (the employer attests, the regional office approves, the balance appears).
- With this the member's three most used journeys — a claim, the bank account, a transfer — run step by step.

## P2.28b — how it is built (changing the bank account)

Built by agy from a brief that pointed it at the claim journey to copy; one fix on review (an error that leads to an action,
not a field, is a button, not a link to "#").

- **The commonest rejection, made hard to get wrong** (`/member/kyc/bank/new`, *Change your bank account* on the KYC
  page): the account on record shown first; the IFSC checked as typed (uppercased); the account number entered twice,
  9–18 digits, and never shown in full again (*ending 1234*); check your answers; the one-time code; the mock penny-drop.
  Verified: a confirmation with the request's reference — the employer approves next, and claims go to the old account
  until then. Refused: the bank's reason at the top, with *Enter another account number*.
- The error helper is shared (`components/ui/problems.ts`) by both journeys.

## P2.28a — how it is built (the claim journey, the first shared components)

Built by agy from a written brief (components, APIs, steps, conventions) and reviewed before it was taken: four fixes on
review — a cancelled one-time code kept the created claim (no second one on Submit), an untranslated line, focus moved to
each step's heading, native fieldsets for the choices.

- **One task, one step at a time** (`/member/claims/new`, *Start a claim* on the claims page): which job (by the
  employer's name and years, not the member ID), what for (the claims open now; the rest folded away with why and what
  fixes it), how much, where it is paid (the bank account on record — blocked, with the way to KYC, when it is not
  verified), check your answers (each with *Change*), then the one-time code and a confirmation: the reference, what
  happens next, the date to expect it (the rule set's settlement days) and a print-ready receipt.
- **Forms that say what is wrong where it is wrong**: an error summary at the top (taking focus, each item linking to its
  field) and the same message on the field; ₹ amounts typed with or without Indian commas and shown grouped; dates as
  dd/mm/yyyy.
- **Shared components** for the journeys that follow (`apps/web/src/components/ui/`): stepper, error summary, money field,
  check-your-answers list, confirmation panel, date and label formatting — strings in English and Hindi
  (`journey.*.json`).
- The old claim form stays at `/member/claims` until the UI lifecycle suites move to the journey; then it goes.
- Not yet: the receipt's QR code, axe checks in CI, the phone layout of the claim list.

## P2.23b — how it is built (every rejection and refusal says what fixes it)

Sources: EPFO's instruction that rejections rest on substantial, justifiable reasons and that a deficiency the member
can cure is given the chance to be cured (Head Office, May 2025, on higher-pension applications); the common grounds on
which claims are rejected — bank details, the cheque image, name or date of birth differing, KYC, the date of exit, earlier
member IDs not transferred, a missing document.

- **A reason, not just a note.** The rule set lists the reasons an officer may reject a claim for (`claims.rejection_reasons`),
  each with what the member does about it and the page where it is done; HO edits the list like any rule. The initiator
  recommending rejection picks one (the case keeps it); the final level keeps or changes it; an unknown reason is refused;
  one not given is *Other* (the officer's note then says what to do). The decision carries it (`CaseDecisionSubmitted.v1`,
  `reason_code`).
- **The member is told what to do.** A rejected claim shows the reason, the officer's note and *What to do*, with a link
  to the page (KYC, Joint Declaration, Mark Exit, transfer, the claim form); the SMS / e-mail says it too.
- **Refusals on the claim form say what fixes them** — or when they lapse: the date the waiting period after an exit ends,
  when the service reaches the minimum, when the claim may be made again; where to mark the exit or transfer the earlier
  member IDs; a pension or scheme certificate instead of a withdrawal. A claim refused when filed carries the same fixes.
- Not built: the higher-pension and transfer rejections (their own reason lists); returning a claim to the member to cure
  a minor deficiency in place (the member claims again).

## P2.23a — how it is built (retirement view, VPF what-if)

Sources: EPF Scheme — a member may contribute above 12% (VPF), which the employer need not match; the Income-tax rule
since the Finance Act, 2021 (Rule 9D) — interest on the employee's own contributions above ₹2,50,000 a year is taxable,
VPF included (the rule set already holds the threshold).

- **One view of retirement** (*View › Retirement view*): the PF balance today across the member's IDs and the wages of the
  latest contribution (contribution-service, `GET /members/me/retirement-forecast`), and the EPS pension at 58 from
  pension-service's estimate, read together: the PF at 58, the PF read as a monthly income, the pension, the total a
  month and the share of the final wages it replaces.
- **How the PF is projected.** Month by month to the 58th birthday: the member's 12% and the employer's EPF share (none to
  EPS from 58), wages rising each April, interest at the latest declared rate on monthly closing balances credited each
  March; today's year counts the months already gone. A member out of service earns interest only.
- **VPF what-if.** VPF up to 88% of wages more: the extra the member pays now, the larger PF and income at 58 — the
  employer's share is unchanged — and the years in which the member's own contributions pass ₹2,50,000, so that part of
  the interest is taxable.
- **Assumptions are rules** (`retirement:` in the rule set — wage growth 5%, the PF read as 6% a year, VPF up to 88%;
  illustrative), shown on the page with the rule version; HO can change them like any rule.
- Not built: deferring the pension to 60 (EPS gives 4% more a year), wages over the ceiling for the pension (higher
  pension), a survivor's view; the replacement rate is on gross wages.
