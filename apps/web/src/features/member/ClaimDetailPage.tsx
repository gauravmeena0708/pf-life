import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { api, command, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { dateTime, stateLabel } from "../journeyB";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

interface ClaimDetail { claim_id: string; account_link_id: string; claim_type: string; form_type: string; amount_paise: number; state: string; version: number; rule_version: string; summary: string; decision_reason: string | null; payment_id: string | null; next_step: string;
  decision_fix?: { code: string; label: string; fix: string; link: string | null } | null;
  tax: { gross_paise: number; tds_paise: number; net_paise: number; rate_bp: number; basis: string; rule_version: string; financial_year: string; declaration: string | null } | null; timeline: { at: string; state: string; by: string; note: string }[] }
interface BankDetails {
  claim_id: string; switchable: boolean; current_account_last4: string | null;
  verified_accounts: { bank_ifsc: string; bank_account_last4: string }[];
}

export function ClaimDetailPage() {
  const { t, i18n } = useTranslation();
  const { claimId } = useParams();
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const claim = useQuery({ queryKey: ["member-claim", claimId], queryFn: () => api<Envelope<ClaimDetail>>(`/api/v1/members/me/claims/${claimId}`), enabled: !!claimId, retry: false,
    refetchInterval: (query) => query.state.data && !["SETTLED", "REJECTED_WITH_REASON", "REJECTED_BY_EMPLOYER", "CANCELLED"].includes(query.state.data.data.state) ? 3000 : false });
  const item = claim.data?.data;
  const bankDetails = useQuery({ queryKey: ["member-claim-bank", claimId, item?.version], enabled: !!item, retry: false,
    queryFn: () => api<Envelope<BankDetails>>(`/api/v1/members/me/claims/${encodeURIComponent(claimId!)}/bank-details`) });
  const [bankNotice, setBankNotice] = useState<string | null>(null);
  const [docNotice, setDocNotice] = useState<string | null>(null);
  async function withdraw() {
    if (!item) return;
    const token = await stepUp.ask({ action: "cancel-claim", resourceId: item.claim_id, summary: `Withdraw claim ${item.claim_id} (${rupees(item.amount_paise)}). You can file a new one afterwards.` });
    if (!token) return;
    setBusy(true); setError(null);
    try {
      await command("POST", `/api/v1/members/me/claims/${item.claim_id}/cancellations`, undefined, { stepUpToken: token });
      await Promise.all([qc.invalidateQueries({ queryKey: ["member-claim", item.claim_id] }), qc.invalidateQueries({ queryKey: ["member-claims"] })]);
    } catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }
  async function upload(file: File | undefined) {
    if (!item || !file) return;
    setError(null); setDocNotice(null);
    try {
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = ""; bytes.forEach((b) => { binary += String.fromCharCode(b); });
      const r = await command<Envelope<{ doc_id: string }>>("POST", `/api/v1/members/me/claims/${item.claim_id}/documents`,
        { filename: file.name, content_type: file.type, content_base64: btoa(binary) });
      setDocNotice(`${file.name} uploaded (${r.data.doc_id}).`);
    } catch (cause) { setError(cause); }
  }
  async function confirm() {
    if (!item || item.state !== "AWAITING_CONFIRMATION") return;
    const token = await stepUp.ask({ action: "confirm-claim", resourceId: item.claim_id, resourceVersion: item.version,
      amountPaise: item.amount_paise, summary: item.summary });
    if (!token) return;
    setBusy(true); setError(null);
    try {
      await command("POST", `/api/v1/members/me/claims/${item.claim_id}/confirmations`, undefined, { stepUpToken: token });
      await Promise.all([qc.invalidateQueries({ queryKey: ["member-claim", item.claim_id] }), qc.invalidateQueries({ queryKey: ["member-claims"] })]);
    } catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }
  async function switchBank(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!item || !bankDetails.data?.data.switchable) return;
    const selected = Number(new FormData(e.currentTarget).get("bank"));
    const account = bankDetails.data.data.verified_accounts[selected];
    setBusy(true); setError(null); setBankNotice(null);
    try {
      if (!account) throw new Error("Choose a verified bank account.");
      const token = await stepUp.ask({ action: "switch-claim-bank", resourceId: item.claim_id, resourceVersion: item.version,
        summary: `Switch claim ${item.claim_id} to verified bank account ending ${account.bank_account_last4} (${account.bank_ifsc}).` });
      if (!token) return;
      await command("PUT", `/api/v1/members/me/claims/${encodeURIComponent(item.claim_id)}/bank-details`, account, { stepUpToken: token });
      setBankNotice(`Claim bank account changed to the verified account ending ${account.bank_account_last4}.`);
      await Promise.all([qc.invalidateQueries({ queryKey: ["member-claim-bank", item.claim_id] }),
        qc.invalidateQueries({ queryKey: ["member-claim", item.claim_id] }), qc.invalidateQueries({ queryKey: ["member-claims"] })]);
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  return <section className="stack" aria-labelledby="claim-detail-heading">
    <PageHeader id="claim-detail-heading" eyebrow={t("claimDetail.eyebrow")} title={t("claimDetail.title")} description={item ? `${rupees(item.amount_paise)} · ${item.form_type}` : t("claimDetail.description")}
      current={t("claimDetail.title")} parent={{ label: t("navigation.claims"), to: "/member/claims" }}>
      {item ? <span className="state-pill">{stateLabel(item.state, t)}</span> : null}
    </PageHeader>
    <ProblemMessage error={claim.error} />
    <ProblemMessage error={error} />
    {claim.isLoading ? <p role="status">{t("claimDetail.loading")}</p> : null}
    {item ? <>
      {!["SETTLED", "REJECTED_WITH_REASON", "REJECTED_BY_EMPLOYER", "CANCELLED"].includes(item.state) ? <section className="card stack" aria-labelledby="claim-actions-heading">
        <h2 id="claim-actions-heading">Documents and withdrawal</h2>
        {docNotice ? <p role="status" className="ok">{docNotice}</p> : null}
        <label>Upload a supporting document (PDF, JPEG or PNG, up to 1 MB)<input type="file" accept="application/pdf,image/jpeg,image/png" onChange={(e) => void upload(e.target.files?.[0])} /></label>
        {["AWAITING_CONFIRMATION", "SUBMITTED", "UNDER_REVIEW", "RECOMMENDED"].includes(item.state)
          ? <div className="actions"><button type="button" disabled={busy} onClick={() => void withdraw()}>Withdraw this claim</button>
            <span className="muted small">Possible until an approving officer decides.</span></div> : null}
      </section> : null}
      <aside className="pending-notice" aria-label={t("claims.nextStep")}><h2>{t("claims.nextStep")}</h2><p>{item.next_step}</p>
        {item.state === "AWAITING_CONFIRMATION" ? <button type="button" className="primary" disabled={busy} onClick={() => void confirm()}>{t("claims.confirmOtp")}</button> : null}</aside>
      <section className="card stack" aria-labelledby="bank-switch-heading"><h2 id="bank-switch-heading">Switch claim bank account</h2>
        <ProblemMessage error={bankDetails.error} />
        {bankNotice ? <p role="status" className="ok">{bankNotice}</p> : null}
        {bankDetails.isLoading ? <p role="status">Loading claim bank details…</p> : null}
        {bankDetails.data ? <>
          <p>Current account: {bankDetails.data.data.current_account_last4 ? `ending ${bankDetails.data.data.current_account_last4}` : "Not recorded"}.</p>
          {!bankDetails.data.data.switchable ? <p className="muted">The bank account cannot be switched at this claim stage.</p>
            : bankDetails.data.data.verified_accounts.length ? <form className="stack" onSubmit={(e) => void switchBank(e)}>
              <label>Verified bank account<select name="bank" required disabled={busy || !!stepUp.request}>
                {bankDetails.data.data.verified_accounts.map((account, index) => <option key={`${account.bank_ifsc}-${account.bank_account_last4}`} value={index}>
                  {account.bank_ifsc} · account ending {account.bank_account_last4}</option>)}
              </select></label>
              <div className="actions"><button type="submit" className="primary" disabled={busy || !!stepUp.request}>Switch bank with one-time code</button></div>
            </form> : <p className="muted">No verified bank accounts are available for switching.</p>}
        </> : null}
      </section>
      {item.state === "PAYMENT_RETURNED" ? <form className="card stack" onSubmit={(e) => { e.preventDefault(); const f = new FormData(e.currentTarget);
        void (async () => { setBusy(true); setError(null); try {
          await command("POST", `/api/v1/members/me/claims/${item.claim_id}/re-disbursement-requests`,
            { ifsc: String(f.get("ifsc")).trim().toUpperCase(), account_number: String(f.get("account_number")).trim() });
          await qc.invalidateQueries({ queryKey: ["member-claim", item.claim_id] });
        } catch (cause) { setError(cause); } finally { setBusy(false); } })(); }}>
        <h2>{t("claimDetail.newBankTitle")}</h2>
        <p className="muted small">{t("claimDetail.newBankHelp")}</p>
        <div className="form-row">
          <label>IFSC<input name="ifsc" required pattern="[A-Za-z]{4}0[A-Za-z0-9]{6}" maxLength={11} /></label>
          <label>{t("claimDetail.accountNumber")}<input name="account_number" required inputMode="numeric" pattern="[0-9]{9,18}" /></label>
        </div>
        <div className="actions"><button type="submit" className="primary" disabled={busy}>{t("claimDetail.sendBank")}</button></div>
      </form> : null}
      <section className="card stack" aria-labelledby="claim-summary-heading"><h2 id="claim-summary-heading">{t("claimDetail.summary")}</h2><p>{item.summary}</p>
        <dl className="kv"><dt>{t("claims.claimId")}</dt><dd><code>{item.claim_id}</code></dd><dt>{t("claims.account")}</dt><dd><code>{item.account_link_id}</code></dd>
          <dt>{t("claims.type")}</dt><dd>{item.form_type} · {item.claim_type}</dd><dt>{t("claims.ruleVersion")}</dt><dd>{item.rule_version} <span className="state-pill">{t("claims.illustrative")}</span></dd>
          {item.payment_id ? <><dt>{t("claimDetail.paymentId")}</dt><dd><code>{item.payment_id}</code></dd></> : null}
          {item.tax ? <><dt>{t("claimDetail.gross")}</dt><dd>{rupees(item.tax.gross_paise)}</dd>
            <dt>{t("claimDetail.tds")}</dt><dd>{item.tax.tds_paise ? rupees(item.tax.tds_paise) : t("claimDetail.noTds")} <span className="muted small">— {item.tax.basis} ({item.tax.rule_version})</span></dd>
            <dt>{t("claimDetail.net")}</dt><dd><strong>{rupees(item.tax.net_paise)}</strong></dd></> : null}</dl>
        {item.decision_reason ? <p className={["REJECTED_WITH_REASON", "REJECTED_BY_EMPLOYER"].includes(item.state) ? "ineligible-reasons" : "muted"}><strong>{t("claimDetail.decisionReason")}:</strong> {item.decision_reason}</p> : null}
        {item.decision_fix ? <p className="pending-notice"><strong>What to do:</strong> {item.decision_fix.fix}
          {item.decision_fix.link ? <> <Link to={item.decision_fix.link}>Go there</Link></> : null}</p> : null}
      </section>
      <section className="card stack" aria-labelledby="claim-timeline-heading"><h2 id="claim-timeline-heading">{t("claimDetail.timeline")}</h2>
        <ol className="claim-timeline">{item.timeline.map((event, index) => <li key={`${event.at}-${event.state}-${index}`} className={index === item.timeline.length - 1 ? "current" : ""}>
          <div className="detail-head"><strong>{stateLabel(event.state, t)}</strong><time dateTime={event.at}>{dateTime(event.at, i18n.language)}</time></div>
          <p className="muted small">{t("claimDetail.by")}: {event.by}</p><p>{event.note}</p>
        </li>)}</ol>
      </section>
    </> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </section>;
}
