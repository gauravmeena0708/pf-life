# Samadhan Setu → pf-life Mapping

Every item from the two Samadhan Setu files, and where it lives in this repository. Nothing was changed silently: each difference from the source text is listed with its reason.

**Sources** (`../samadhan-setu files/`):
- **SPEC** — `PF_LIFE_INTEGRATION_SPECIFICATION.md`
- **KB** — `SAMADHAN_SETU_KNOWLEDGE_BASE.md`
- **ISSUES** — `samadhan_setu_parsed_issues.json` (raw tracker error texts; used to verify SPEC and KB claims)

**Conventions applied to every item** (why contract text differs from SPEC/KB text):

| Source text | Contract | Reason |
|---|---|---|
| Money as `type: number, format: double` | Integer paise (`*_paise`) | `init.md` §3.3 forbids binary floating point for money |
| Share percent as `number` 0.1–100.0 | Integer basis points (`*_bp`, 100 = 1%, 10000 = 100%) | Exact arithmetic; shares must sum exactly |
| camelCase fields | snake_case fields | Envelope and events already use snake_case (`init.md` §3.2) |
| `nullable: true` | `type: [X, "null"]` | Contracts are OpenAPI 3.1 |
| `ProblemDetails` | `Problem` (RFC 9457) | Existing shared schema |
| Bare response body | `{data, meta}` envelope | `init.md` §3.2 |
| `{memberId}` in office paths | `{uan}` | Matches existing `/office/members/{uan}` routes |
| `/members/{memberId}/…` (KB) | `/members/me/…` | Self-service is `/me`-scoped (anti-IDOR, `init.md` §3) |
| Statutory thresholds (e.g. 9.5 years) | Value from `config/demo-rules.yaml`, returned with `rule_version` | `init.md` §0.5: no statutory assertions |

Hand-written schemas live in `contracts/openapi/overlays/`; `docs/tools/build_gate0.py` merges them into the generated specs. Status, phase and callers always come from `docs/endpoint-catalogue.md`.

## 1. Stakeholders (`docs/stakeholders.md`)

| SPEC ID | Repo ID | Evidence found in ISSUES | Note |
|---|---|---|---|
| `claimant.nominee` | `claimant.nominee` | Form-20 / 5IF share errors ("100% share is gone in legacy", "Edit Share % of Beneficiary") | As specified |
| `fo.pro_intake` | `fo.pro_intake` | PRO module ("UAN is not registered…" at PRO) | SPEC's source keys (OUL, SOP-B) do not mention this role; cited as SS |
| `fo.fa_accounts` | `fo.fa_accounts` | "Failed to generate CAD", "Failed to load CAD static Data" | As specified |
| `exempted.trust_liquidator` | `exempted.trust_liquidator` | Module "Surrender_Of_Exem._and_Past_accumulation" | As specified |
| `govt.pmvbry_admin` | `gov.pmvbry_admin` | Module "PMVBRY" (no issue texts) | Prefix aligned with existing `gov.*` IDs |
| `tech.batch.annual_accounts` | `tech.batch.annual_accounts` | "Annual accounting is under process for this member" | As specified |
| `tech.vishwas` | **not added** | Module "Vishwas" (no issue texts) | VISHWAS is EPFO's 2025–26 settlement scheme for 14B damages / penalty disputes, not a risk engine. Modelled as endpoints below |

## 2. Endpoints from SPEC §2 (`docs/endpoint-catalogue.md`)

| SPEC | Contract | Service | Note |
|---|---|---|---|
| `POST /office/claims/{claimId}/cad` | same | claim | Schema `ClaimCad` |
| `GET /office/claims/{claimId}/cad` | same | claim | |
| `GET /office/system/cad-static-data` | same | claim | Schema `CadStaticDataStatus` |
| `POST /claimants/death-claims/{claimId}/beneficiaries` | same | claim | Schemas `BeneficiaryInwardRequest`, `BeneficiaryRecord` |
| `PUT /office/death-claims/{claimId}/beneficiaries/{beneficiaryId}/shares` | same | claim | Schemas `ShareAmendmentRequest`, `SharesSummary` (SPEC referenced `SharesSummaryResponse` without defining it) |
| `GET /office/death-claims/{claimId}/shares-summary` | same | claim | |
| `POST /members/me/claims/{claimId}/re-disbursement-requests` | same | claim | Schema `ReDisbursementRequest` |
| `POST /office/claims/{claimId}/re-disbursement-approvals` | same | claim | |
| `GET /members/me/pension-eligibility-preview` | same | pension | Schema `PensionEligibilityPreview`; threshold from config |
| `POST /office/pension/service-aggregations` | `POST /office/pensions/service-aggregations` | pension | Existing `/office/pensions/` prefix |
| `POST /members/me/pension-scheme-certificates/surrender` | `POST /members/me/pension-scheme-certificates/{certId}/surrenders` | pension | A surrender acts on one certificate |
| `POST /office/pension/scheme-certificates/{certId}/surrender-adjudications` | `POST /office/pensions/scheme-certificates/{certId}/surrender-adjudications` | pension | Prefix |
| `POST /office/pension/brs/reconciliations` | `POST /office/pensions/brs-reconciliations` | pension | Prefix |
| `POST /employers/me/ecr-filings/{filingId}/cancellations` | already existed | contribution | Not duplicated |
| `POST /office/ecr-filings/{filingId}/payment-rejections` | same | contribution | ISSUES: "Unable to reject ecr payment" |
| `POST /office/transfers/{transferId}/recredits` | same | contribution | ISSUES: "Recredit of transfer-in rejected cases" |
| `POST /office/exempted/past-accumulations/ingestions` | `POST /office/exempted/{estId}/past-accumulation-ingestions` | contribution | Scoped to one establishment like the existing past-accumulation route |
| `GET /office/members/{memberId}/locks` | `GET /office/members/{uan}/locks` | workflow | Schema `LedgerLock` |
| `POST /office/system/locks/{lockId}/release` | same | workflow | |
| `POST /office/cases/{caseId}/documents/{docId}/attestation-views` | same | workflow | ISSUES: "View the employer signed pdf first" |
| — (VISHWAS, replaces `tech.vishwas`) | `POST /employers/me/vishwas-applications`, `POST /office/compliance/vishwas-applications/{applicationId}/decisions` | compliance | Designed |

## 3. Pre-flight and post-submission APIs (designed — not in SPEC or KB)

Requested in the task prompt; neither source file defines them. Designed to repo conventions and grounded in ISSUES error texts.

| Requested | Contract | Service | Design note |
|---|---|---|---|
| `/account-status` | `GET /members/me/account-status` | member | Blocker codes (`BlockerCode`) each tied to a production error text |
| `/eligibility-preview` | `GET /members/me/claims/eligibility-preview?formType=` | claim | Per form type; same blocker codes plus rule failures (`ClaimEligibilityPreview`) |
| `/service-history` | `GET /members/me/service-history` | member | Contributory months, NCP days, pension service, transfer status (`ServiceHistory`). Complements the existing `GET /members/me/employment-history` |
| `/audit-trail` | `GET /members/me/claims/{claimId}/audit-trail` (member view, roles only) and `GET /office/claims/{claimId}/audit-trail` (full) | claim | `ClaimAuditEntryMemberView`, `ClaimAuditEntry` |
| `/cancel` | `POST /members/me/claims/{claimId}/cancellations` | claim | **Renamed** from existing `…/withdrawals` (same meaning), matching the ECR `cancellations` convention. State `WITHDRAWN` is now `CANCELLED` |
| `/update-bank-details` | `PUT /members/me/claims/{claimId}/bank-details` | claim | Before payment only; takes a KYC-verified account ID so it cannot bypass employer KYC approval. After a return, `…/re-disbursement-requests` applies |

## 4. KB recommendations (§6)

| KB item | Where | Note |
|---|---|---|
| 6.1 Lock leases with TTL, hierarchical scopes, admin unlock | `workflow-service`: `LedgerLock`, `LockState`, `LockKeyPattern`, `LockLifecycle` (`x-transitions`, fencing-token invariant); `init.md` §3.3 | Lease acquire / renew are library operations inside services, not public APIs |
| 6.2 Composite death claim, incremental settlement, share edit | `claim-service`: `DeathClaimRecord` (on `GET /claimants/death-claims/{claimId}`), `BeneficiaryRecord.status` incl. `CAD_GENERATED`, `SharesSummary` invariant | `DEPENDENT` split into `DEPENDENT_BROTHER` / `DEPENDENT_SISTER` as in SPEC |
| 6.3 Pension pre-flight and untransferred service | `GET /members/me/pension-eligibility-preview` | KB's `meetsThreshold9Years6Months` → `meets_threshold` + `threshold_months` from config |
| 6.4 Return state and re-disburse; late credits | `ClaimStateMachine`: KB `RETURNED_TO_OFFICE` = `PAYMENT_RETURNED`; KB `POST /claims/{claimId}/re-disburse` = SPEC's re-disbursement request + approval; late credit on SETTLED emits `SupplementaryClaimEligible.v1` | |
| 6.5 CAD fallback with warning tag | `ClaimCad.rules_source`, `audit_tags: [CAD_GENERATED_FALLBACK_RULES]`, `warnings` | Approver must acknowledge before payment |
| 6.6 ECR cancel / void | Existing `POST /employers/me/ecr-filings/{filingId}/cancellations` | KB offered `DELETE …/cancel` or `POST …/void`; kept the existing route |
| 6.7 Transactional outbox for DA task sync | Already required by `init.md` §2.1 and §3.3; `ClaimStateMachine` guard "case opened in workflow-service (transactional outbox)" | |

## 5. Events (`contracts/events/`)

| SPEC / KB | Contract | Change |
|---|---|---|
| `CADGenerated` | `CADGenerated.v1` | Standard envelope; paise; `memberId` dropped (claim ID suffices) |
| `BeneficiaryShareAmended` | `BeneficiaryShareAmended.v1` | Envelope; basis points |
| `LockReleased` | `LockReleased.v1` | Envelope; adds `lock_scope` |
| KB 6.4 late credit | `SupplementaryClaimEligible.v1` | Designed |

## 6. Not done here

SPEC §5 test cases (`tests/test_claim_service.py`, `tests/test_workflow_service.py`) need running services; they are build-phase work.
