# Phase 2 — plan and progress

Phase 2 is every operation marked **P, phase 2** in `docs/endpoint-catalogue.md` (177 at the start). It is built
in slices, each finishing journeys the POC already demonstrates; a slice is done when its operations are **W**,
its menus in the web app are clickable, and unit, end-to-end and must-deny tests pass on the running stack.

| Slice | Scope | Status |
|---|---|---|
| **P2.1** | Dates of exit (member Mark Exit; employer marks, signatory approves), service history, the member's pending / processed applications, Form 13 transfer (member → present employer → DA → AO; ledger moves the balance), Annexure K | **Done** (28 Sep 2026) |
| P2.2 | Employer member registration (single, bulk), Form 11 declarations, KYC approvals, member KYC, UAN card, Member › Approvals for other changes, exit-bulk, missing details, active-member export | Next |
| P2.3 | Pension office and pensioner self-service: pension enquiry, updation activities and tracker, suspend / resume, life-certificate monitoring, PPO, slips, public pension enquiries | |
| P2.4 | Pension settlement: Form 10D, scheme certificate, IDS, worksheet, PPO issue, e-sign, dispatch, initial arrears, CPPS runs, BRS, service aggregation | |
| P2.5 | Death and EDLI claims, CAD, payment scrolls, physical intake, claim documents, cancellations, audit trail | |
| P2.6 | Establishment registration and configuration, Form 5A, branches, DSC / e-sign approvals | |
| P2.7 | Returns, receipts and ledger: arrear / supplementary ECR, demands, direct challans, 14B/7Q knock-offs, VDR rejection, reversals, recredits | |
| P2.8 | The rest: compliance and VISHWAS, international workers, grievance extras, public lookups, audit, NDC, HRM, DO dashboards | |

Operations marked **?** (scope unconfirmed, e.g. *ECR Approval*, *VDR Member Beneficiary*) wait until their
meaning is confirmed.

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
