import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { api, command, newIdempotencyKey, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { roleLabel, stateLabel, dateTime } from "../journeyB";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { TaxDeclaration } from "./TaxDeclaration";
import { Form16A } from "./Form16A";
import { useStepUp } from "../stepup/useStepUp";

interface ClaimType { claim_type: string; form_type: string; label: string; plain_rule: string; eligible: boolean; max_amount_paise: number; reasons: string[] }
interface Account { account_link_id: string; primary?: boolean; balance: { employee_paise: number; employer_paise: number; total_paise: number }; types: ClaimType[] }
interface Eligibility { rule_version: string; illustrative_only: boolean; auto_settlement_limit_paise: number; accounts: Account[] }
interface ClaimRow { claim_id: string; claim_type: string; form_type: string; amount_paise: number; state: string; next_step: string; created_at: string }
interface CreatedClaim { claim_id: string; state: string; summary: string; version: number; amount_paise: number; next_step: string; rules_applied: { rule_version: string; plain_rule: string; max_amount_paise: number; route: "AUTO" | "REVIEW"; approval_chain: string[] }; confirmation: { action: string; resource_id: string; resource_version: number; amount_paise: number } }

export function ClaimsPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const createKey = useRef<string | null>(null);
  const [choice, setChoice] = useState<{ accountId: string; claimType: string } | null>(null);
  const [amount, setAmount] = useState("");
  const [created, setCreated] = useState<CreatedClaim | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const eligibility = useQuery({ queryKey: ["member-claim-eligibility"], queryFn: () => api<Envelope<Eligibility>>("/api/v1/members/me/claims/eligible-types"), retry: false });
  const claims = useQuery({ queryKey: ["member-claims"], queryFn: () => api<Envelope<ClaimRow[]>>("/api/v1/members/me/claims"), retry: false });
  const selected = eligibility.data?.data.accounts.find((account) => account.account_link_id === choice?.accountId)?.types.find((type) => type.claim_type === choice?.claimType);
  const numericAmount = Number(amount);
  const amountPaise = numericAmount * 100;
  const amountValid = !!selected?.eligible && /^\d+$/.test(amount) && numericAmount > 0 && Number.isSafeInteger(amountPaise) && amountPaise <= selected.max_amount_paise;

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!choice || !selected || !amountValid) {
      setError(new Error(t("claims.invalidAmount")));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      createKey.current ??= newIdempotencyKey();
      const result = await command<Envelope<CreatedClaim>>("POST", "/api/v1/members/me/claims", {
        account_link_id: choice.accountId, claim_type: choice.claimType, amount_paise: amountPaise,
      }, { idempotencyKey: createKey.current });
      setCreated(result.data);
      createKey.current = null;
      await qc.invalidateQueries({ queryKey: ["member-claims"] });
    } catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }

  async function confirm() {
    if (!created) return;
    const intent = created.confirmation;
    const token = await stepUp.ask({ action: intent.action, resourceId: intent.resource_id, resourceVersion: intent.resource_version,
      amountPaise: intent.amount_paise, summary: created.summary });
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      await command("POST", `/api/v1/members/me/claims/${created.claim_id}/confirmations`, undefined, { stepUpToken: token });
      await qc.invalidateQueries({ queryKey: ["member-claims"] });
      navigate(`/member/claims/${created.claim_id}`);
    } catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }

  return <section className="stack" aria-labelledby="claims-heading">
    <PageHeader id="claims-heading" eyebrow={t("claims.eyebrow")} title={t("claims.title")} description={t("claims.description")} current={t("navigation.claims")} />
    <ProblemMessage error={error} />
    <div className="card stack">
      <div className="section-heading"><div><p className="eyebrow">01 · {t("claims.memberService")}</p><h2>{t("claims.start")}</h2></div></div>
      <p className="demo-tip">{t("claims.illustrativeNotice")}</p>
      <ProblemMessage error={eligibility.error} />
      {eligibility.isLoading ? <p role="status">{t("claims.loadingEligibility")}</p> : null}
      {eligibility.data?.data.accounts.length === 0 ? <p className="muted">{t("claims.noAccounts")}</p> : null}
      {!created ? <>
        {eligibility.data?.data.accounts.map((account) => <section className="claim-account stack" key={account.account_link_id} aria-labelledby={`account-${account.account_link_id}`}>
          <h3 id={`account-${account.account_link_id}`}>{t("claims.account")} <code>{account.account_link_id}</code>
            {account.primary ? <> <span className="state-pill" title="Primary member ID: claims are made against it">P</span></>
              : <span className="muted small"> (secondary: transfer it to your primary member ID)</span>}</h3>
          <div className="metrics passbook-metrics"><div><span>{t("claims.employeeBalance")}</span><strong>{rupees(account.balance.employee_paise)}</strong></div><div><span>{t("claims.employerBalance")}</span><strong>{rupees(account.balance.employer_paise)}</strong></div><div><span>{t("claims.totalBalance")}</span><strong>{rupees(account.balance.total_paise)}</strong></div></div>
          <div className="claim-type-grid">{account.types.map((type) => {
            const active = choice?.accountId === account.account_link_id && choice.claimType === type.claim_type;
            return <label key={type.claim_type} className={`claim-type${active ? " selected" : ""}${!type.eligible ? " unavailable" : ""}`}>
              <input type="radio" name="claim-type" value={`${account.account_link_id}:${type.claim_type}`} checked={active} disabled={!type.eligible || busy}
                onChange={() => { setChoice({ accountId: account.account_link_id, claimType: type.claim_type }); setAmount(""); createKey.current = null; setError(null); }} />
              <span className="claim-type-content"><strong>{type.label}</strong><span className="muted small">{t("claims.form")} {type.form_type}</span><span>{type.plain_rule}</span>
                {type.eligible ? <span className="small">{t("claims.maxAmount")}: <strong>{rupees(type.max_amount_paise)}</strong></span>
                  : <span className="ineligible-reasons">{t("claims.notEligible")}: {type.reasons.join("; ")}</span>}</span>
            </label>;
          })}</div>
        </section>)}
        {selected ? <form className="claim-amount-form stack" onSubmit={(event) => void create(event)}>
          <label htmlFor="claim-amount">{t("claims.amountRupees")}
            <input id="claim-amount" type="number" inputMode="numeric" min="1" step="1" max={Math.floor(selected.max_amount_paise / 100)} value={amount}
              onChange={(event) => { setAmount(event.target.value); createKey.current = null; }} required aria-describedby="claim-amount-help" />
          </label>
          <p id="claim-amount-help" className="muted small">{t("claims.wholeRupees")} {t("claims.maxAmount")}: {rupees(selected.max_amount_paise)}</p>
          {amount && !amountValid ? <p className="ineligible-reasons" role="alert">{t("claims.invalidAmount")}</p> : null}
          <div className="actions"><button type="submit" className="primary" disabled={!amountValid || busy}>{t("claims.createReview")}</button></div>
        </form> : null}
      </> : <section className="pending-notice stack" aria-labelledby="claim-review-heading">
        <p className="eyebrow">{t("claims.reviewEyebrow")}</p><h2 id="claim-review-heading">{t("claims.reviewTitle")}</h2>
        <p>{created.summary}</p><p><strong>{rupees(created.amount_paise)}</strong> · <code>{created.claim_id}</code></p>
        <h3>{t("claims.howDecided")}</h3>
        {created.rules_applied.route === "AUTO" ? <ol><li>{t("claims.automaticApproval")}</li></ol>
          : <ol>{created.rules_applied.approval_chain.map((role, index) => <li key={`${role}-${index}`}>{roleLabel(role, t)}</li>)}</ol>}
        <p className="muted small">{created.rules_applied.plain_rule}</p>
        <p><span className="state-pill">{t("claims.illustrative")}</span> {t("claims.ruleVersion")}: {created.rules_applied.rule_version}</p>
        <div className="actions"><button type="button" className="primary" disabled={busy} onClick={() => void confirm()}>{t("claims.confirmOtp")}</button></div>
      </section>}
    </div>
    <section className="card stack" aria-labelledby="your-claims-heading"><div className="section-heading"><div><p className="eyebrow">02 · {t("claims.memberService")}</p><h2 id="your-claims-heading">{t("claims.yourClaims")}</h2></div></div>
      <ProblemMessage error={claims.error} />
      {claims.isLoading ? <p role="status">{t("claims.loadingClaims")}</p> : null}
      {claims.data?.data.length === 0 ? <p className="muted">{t("claims.noClaims")}</p> : null}
      {claims.data?.data.length ? <div className="table-scroll"><table><thead><tr><th scope="col">{t("claims.claimId")}</th><th scope="col">{t("claims.type")}</th><th scope="col" className="numeric">{t("claims.amount")}</th><th scope="col">{t("claims.nextStep")}</th><th scope="col">{t("claims.status")}</th><th scope="col">{t("claims.created")}</th></tr></thead><tbody>{claims.data.data.map((claim) => <tr key={claim.claim_id}>
        <td><Link to={`/member/claims/${claim.claim_id}`}><code>{claim.claim_id}</code></Link></td><td>{eligibility.data?.data.accounts.flatMap((account) => account.types).find((type) => type.claim_type === claim.claim_type)?.label ?? `Form ${claim.form_type}`}<br /><span className="muted small">Form {claim.form_type}</span></td><td className="numeric">{rupees(claim.amount_paise)}</td><td>{claim.next_step}</td><td><span className="state-pill">{stateLabel(claim.state, t)}</span></td><td>{dateTime(claim.created_at, i18n.language)}</td>
      </tr>)}</tbody></table></div> : null}
    </section>
    <TaxDeclaration />
    <Form16A />
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </section>;
}
