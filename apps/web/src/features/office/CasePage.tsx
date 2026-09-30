import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { api, command, getSession, newIdempotencyKey, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { dateTime, roleLabel, stateLabel } from "../journeyB";
import { ClaimAnalysisPanel } from "../ai/ClaimAnalysisPanel";
import { ProcessForm } from "./ProcessForm";
import { SignedDocuments } from "./SignedDocuments";
import { ClaimDocket } from "./ClaimDocket";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";
import type { CaseDetail } from "./types";

const CHECK_KEYS = ["kyc", "bank", "balance", "freeze"] as const;
const CHECK_VALUES: Record<typeof CHECK_KEYS[number], string> = {
  kyc: "KYC verified", bank: "Bank account verified", balance: "Balance sufficient", freeze: "No open grievance or freeze",
};
type Decision = "APPROVE" | "RETURN" | "REJECT";
type Scenario = "SUCCESS" | "RETURN";

export function CasePage() {
  const { t, i18n } = useTranslation();
  const { caseId } = useParams();
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const retryKey = useRef<string | null>(null);
  const [checks, setChecks] = useState<(typeof CHECK_KEYS)[number][]>([]);
  const [note, setNote] = useState("");
  const [decision, setDecision] = useState<Decision>("APPROVE");
  const [reason, setReason] = useState("");
  const [scenario, setScenario] = useState<Scenario>("SUCCESS");
  const [recommendation, setRecommendation] = useState<"APPROVE" | "REJECT">("APPROVE");
  const [accountStatus, setAccountStatus] = useState("OPERATIVE");
  const [stopReason, setStopReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState(false);
  const detail = useQuery({ queryKey: ["office-case", caseId], queryFn: () => api<Envelope<CaseDetail>>(`/api/v1/office/cases/${caseId}`), enabled: !!caseId, retry: false });
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const item = detail.data?.data;
  const role = session.data?.stakeholder;
  const action = item?.your_turn && item.current_role === role ? item.next_action : null;
  const allowed = action === "recommend" && role === "fo.da_accounts" || action === "decide" && (role === "fo.ss" || role === "fo.ao")
    || action === "second-approve" && (role === "fo.apfc" || role === "fo.oic") || (action === "instruct-payment" || action === "reissue") && role === "fo.cash"
    || action === "approve-redisbursement" && role === "fo.apfc";
  // CITES: only the final level decides; the options follow the initiator's recommendation.
  const rec = String(item?.data?.recommendation ?? "APPROVE");
  const finalLevel = !!item && item.step + 1 === item.chain.length;
  const options: Decision[] = finalLevel ? (rec === "REJECT" ? ["REJECT", "RETURN"] : ["APPROVE", "RETURN"])
    : rec === "REJECT" ? ["REJECT", "RETURN"] : ["APPROVE", "REJECT", "RETURN"];
  const chosen: Decision = options.includes(decision) ? decision : options[0];
  const optionLabel = (value: Decision) => value === "RETURN" ? "Send back to first level / initiator"
    : value === "APPROVE" ? (finalLevel ? "Approve" : "Recommend to Approve (forward)")
    : finalLevel ? "Reject" : rec === "REJECT" ? "Recommend to Reject (forward)" : "Recommend to Reject (returns to the initiator)";
  const reviewing = !!item?.claim_id && (action === "recommend" || action === "decide" || action === "second-approve") && allowed;

  async function run(work: () => Promise<unknown>) {
    setBusy(true); setError(null); setNotice(false);
    try {
      await work();
      retryKey.current = null;
      await Promise.all([qc.invalidateQueries({ queryKey: ["office-case", caseId] }), qc.invalidateQueries({ queryKey: ["office-work-queue"] })]);
      setNotice(true);
    } catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!item || !allowed || !action) return;
    if (action === "recommend") {
      const token = await stepUp.ask({ action: "recommend-case", resourceId: item.case_id, resourceVersion: item.version,
        summary: `Recommend to ${recommendation === "APPROVE" ? "approve" : "reject"} claim ${item.claim_id ?? item.case_id}.` });
      if (!token) return;
      await run(() => command("POST", `/api/v1/office/cases/${item.case_id}/recommendations`, { checks: checks.map((key) => CHECK_VALUES[key]),
        note: note.trim(), recommendation, account_status: accountStatus }, { stepUpToken: token }));
      return;
    }
    if (action === "decide" || action === "second-approve") {
      if (chosen !== "APPROVE" && !reason.trim()) { setError(new Error(t("office.reasonRequired"))); return; }
      const token = await stepUp.ask({ action: "decide-case", resourceId: item.case_id, resourceVersion: item.version,
        amountPaise: item.amount_paise, summary: `${optionLabel(chosen)} — case ${item.case_id}.` });
      if (!token) return;
      await run(() => command("POST", `/api/v1/office/cases/${item.case_id}/${action === "decide" ? "decisions" : "second-approvals"}`,
        { decision: chosen, reason: reason.trim() || null }, { stepUpToken: token }));
      return;
    }
    if (action === "approve-redisbursement") {
      if (!reason.trim()) { setError(new Error(t("office.reasonRequired"))); return; }
      const claimId = item.claim_id ?? "";
      const token = await stepUp.ask({ action: "approve-redisbursement", resourceId: claimId, amountPaise: item.amount_paise,
        summary: t("office.redisbursementSummary", { claimId, decision: t(`office.decisions.${decision === "APPROVE" ? "APPROVE" : "REJECT"}`) }) });
      if (!token) return;
      await run(() => command("POST", `/api/v1/office/claims/${claimId}/re-disbursement-approvals`,
        { decision: decision === "APPROVE" ? "APPROVE" : "REJECT", note: reason.trim() }, { stepUpToken: token }));
      return;
    }
    const isReissue = action === "reissue";
    const claimId = item.claim_id ?? "";
    const token = await stepUp.ask({ action: isReissue ? "reissue-payment" : "instruct-payment", resourceId: claimId,
      amountPaise: item.amount_paise, summary: t(isReissue ? "office.reissueSummary" : "office.paymentSummary", { claimId, scenario: t(`office.scenarios.${scenario}`) }) });
    if (!token) return;
    retryKey.current ??= newIdempotencyKey();
    await run(() => command("POST", `/api/v1/office/claims/${claimId}/${isReissue ? "reissues" : "payment-instructions"}`,
      { demo_scenario: scenario }, { stepUpToken: token, idempotencyKey: retryKey.current! }));
  }

  return <section className="stack" aria-labelledby="office-case-heading"><PageHeader id="office-case-heading" eyebrow={t("office.eyebrow")} title={t("office.caseTitle")}
    description={item ? `${item.case_id} · ${item.office_id}` : t("office.caseDescription")}
    current={t("office.caseTitle")} parent={{ label: t("navigation.workQueue"), to: "/office/work-queue" }}>
    {item ? <span className="state-pill">{stateLabel(item.state, t)}</span> : null}</PageHeader>
    <ProblemMessage error={detail.error} />{detail.isLoading ? <p role="status">{t("office.loadingCase")}</p> : null}
    {notice ? <p role="status" className="ok">{t("office.actionSaved")}</p> : null}<ProblemMessage error={error} />
    {item ? <>
      {item.process ? <section className="card stack" aria-labelledby="process-heading"><h2 id="process-heading">{item.kind.replaceAll("_", " ").toLowerCase()}</h2>
        <dl className="kv"><dt>Process</dt><dd><code>{item.process}</code> (tier-2, config/processes)</dd><dt>Subject</dt><dd><code>{item.subject_ref}</code></dd>
          <dt>State</dt><dd>{item.state}</dd><dt>{t("office.slaDue")}</dt><dd>{dateTime(item.sla_due_at, i18n.language)}</dd></dl>
        {item.data && Object.keys(item.data).length ? <dl className="kv">{Object.entries(item.data).map(([k, v]) => <Fragment key={k}><dt>{k.replaceAll("_", " ")}</dt><dd>{String(v)}</dd></Fragment>)}</dl> : null}
        <SignedDocuments caseId={item.case_id} documents={item.documents ?? []} onViewed={() => void qc.invalidateQueries({ queryKey: ["office-case", caseId] })} />
        {item.your_turn && item.operation ? <ProcessForm operation={item.operation} caseRef={{ id: item.case_id, version: item.version }} onDone={(msg) => { setNotice(true); void msg; void qc.invalidateQueries({ queryKey: ["office-case", caseId] }); }} />
          : <p className="muted">{item.current_role ? `Waiting for ${roleLabel(item.current_role, t)}.` : "Finished."}</p>}
      </section> : null}
      {!item.process ? <section className="card stack" aria-labelledby="case-summary-heading"><h2 id="case-summary-heading">{t("office.caseSummary")}</h2>
        <dl className="kv"><dt>{t("office.caseId")}</dt><dd><code>{item.case_id}</code></dd><dt>{t("claims.claimId")}</dt><dd><code>{item.claim_id}</code></dd>
          <dt>{t("claims.account")}</dt><dd><code>{item.account_link_id}</code></dd><dt>{t("claims.form")}</dt><dd>{item.form_type}</dd>
          <dt>{t("claims.amount")}</dt><dd>{rupees(item.amount_paise)}</dd><dt>{t("office.kind")}</dt><dd>{item.kind}</dd>
          <dt>{t("claims.ruleVersion")}</dt><dd>{item.rule_version} <span className="state-pill">{t("claims.illustrative")}</span></dd>
          <dt>{t("office.round")}</dt><dd>{item.round}</dd><dt>{t("office.slaDue")}</dt><dd>{dateTime(item.sla_due_at, i18n.language)}</dd></dl>
      </section> : null}
      {item.advisory_signal_id ? <p className="demo-tip"><strong>{t("office.advisory")}:</strong> {t("office.advisoryHelp")} (<code>{item.advisory_signal_id}</code>)</p> : null}
      {role === "fo.da_accounts" && item.claim_id ? <ClaimAnalysisPanel claimId={item.claim_id} /> : null}
      <section className="card stack" aria-labelledby="chain-heading"><h2 id="chain-heading">{t("office.approvalChain")}</h2>
        <ol className="chain-stepper">{item.chain.map((chainRole, index) => {
          const current = item.state === "IN_REVIEW" && index === item.step;
          const status = index < item.step || item.state !== "IN_REVIEW" ? "done" : current ? "current" : "pending";
          return <li key={`${chainRole}-${index}`} className={status} aria-current={current ? "step" : undefined}><span className="chain-number">{index + 1}</span><span><strong>{roleLabel(chainRole, t)}</strong><small>{t(`office.chainStates.${status}`)}</small></span></li>;
        })}</ol>
      </section>
      <section className="card stack" aria-labelledby="case-history-heading"><h2 id="case-history-heading">{t("office.history")}</h2>
        {item.history.length === 0 ? <p className="muted">{t("office.noHistory")}</p> : <div className="table-scroll"><table><thead><tr><th scope="col">{t("office.when")}</th><th scope="col">{t("office.round")}</th><th scope="col">{t("office.officer")}</th><th scope="col">{t("office.action")}</th><th scope="col">{t("office.reasonChecks")}</th></tr></thead><tbody>{item.history.map((entry, index) => <tr key={`${entry.at}-${index}`}>
          <td>{dateTime(entry.at, i18n.language)}</td><td>{entry.round}</td><td>{roleLabel(entry.officer_role, t)}<br /><span className="muted small">{entry.officer_subject}</span></td><td>{entry.action} {entry.approval_level ?? ""}</td><td>{entry.reason}{entry.reason && entry.checks?.length ? "; " : ""}{(entry.checks ?? []).join(", ")}</td>
        </tr>)}</tbody></table></div>}
      </section>
      {item.claim_id && (reviewing || role === "fo.fa_accounts") ? <ClaimDocket claimId={item.claim_id} ready={!!item.docket_ready} canGenerate={reviewing}
        onGenerated={() => void qc.invalidateQueries({ queryKey: ["office-case", caseId] })} /> : null}
      {item.data?.returned_for_rejection && action === "recommend" ? <p className="pending-notice">{String(item.data.returned_for_rejection)} — re-forward it as
        "Recommend to Reject" if you agree.</p> : null}
      {role === "fo.da_accounts" && item.claim_id && (item.state === "IN_REVIEW" || item.state === "STOPPED") ? <section className="card stack" aria-labelledby="stop-heading">
        <h2 id="stop-heading">{item.state === "STOPPED" ? "Restart claim" : "Stop claim processing"}</h2>
        {item.state === "STOPPED" ? <><p>Stopped: {String((item.data?.stopped as { reason?: string } | undefined)?.reason ?? "")}</p>
          <div className="actions"><button type="button" className="primary" disabled={busy} onClick={() => void run(() => command("POST", `/api/v1/office/cases/${item.case_id}/restarts`))}>Restart claim</button></div></>
          : <form className="stack" onSubmit={(event) => { event.preventDefault(); void run(() => command("POST", `/api/v1/office/cases/${item.case_id}/stops`, { reason: stopReason.trim() })); }}>
            <p className="muted small">When a parallel activity must finish first. The claim leaves every work queue until restarted.</p>
            <label>Reason (recorded)<input value={stopReason} onChange={(event) => setStopReason(event.target.value)} required minLength={10} /></label>
            <div className="actions"><button type="submit" disabled={busy}>Stop claim processing</button></div></form>}
      </section> : null}
      {allowed && action ? <section className="card stack" aria-labelledby="case-action-heading"><h2 id="case-action-heading">{t(`office.actions.${action}`)}</h2>
        <form className="stack" onSubmit={(event) => void submit(event)}>
          {action === "recommend" ? <><fieldset className="case-options"><legend>{t("office.checksTitle")}</legend>{CHECK_KEYS.map((key) => <label className="check-row" key={key}>
            <input type="checkbox" checked={checks.includes(key)} onChange={(event) => setChecks(event.target.checked ? [...checks, key] : checks.filter((value) => value !== key))} />{t(`office.checks.${key}`)}</label>)}</fieldset>
            <label>{t("office.note")}<textarea value={note} onChange={(event) => setNote(event.target.value)} required minLength={3} /></label></> : null}
          {action === "recommend" ? <><fieldset className="case-options"><legend>Recommendation</legend>{(["APPROVE", "REJECT"] as const).map((value) => <label className="check-row" key={value}>
            <input type="radio" name="recommendation" value={value} checked={recommendation === value} onChange={() => setRecommendation(value)} />{value === "APPROVE" ? "Recommend to Approve" : "Recommend to Reject"}</label>)}</fieldset>
            <label>Account status<select value={accountStatus} onChange={(event) => setAccountStatus(event.target.value)}>
              <option value="OPERATIVE">Operative</option><option value="INOPERATIVE">Inoperative</option><option value="DORMANT">Dormant</option></select></label></> : null}
          {action === "decide" || action === "second-approve" ? <><p className="muted small">{rec === "REJECT" ? "The initiator recommends rejection." : "The initiator recommends approval."}
            {finalLevel ? " You are the final level for this amount." : " A higher level decides; only the final level may reject."}</p>
            <fieldset className="case-options"><legend>{t("office.decision")}</legend>{options.map((value) => <label className="check-row" key={value}>
            <input type="radio" name="decision" value={value} checked={chosen === value} onChange={() => setDecision(value)} />{optionLabel(value)}</label>)}</fieldset>
            <label>{t("office.reason")}<textarea value={reason} onChange={(event) => setReason(event.target.value)} required={chosen !== "APPROVE"} /></label></> : null}
          {action === "approve-redisbursement" ? <><p className="demo-tip">{t("office.redisbursementHelp")}</p>
            <fieldset className="case-options"><legend>{t("office.decision")}</legend>{(["APPROVE", "REJECT"] as const).map((value) => <label className="check-row" key={value}>
              <input type="radio" name="decision" value={value} checked={decision === value} onChange={() => setDecision(value)} />{t(`office.decisions.${value}`)}</label>)}</fieldset>
            <label>{t("office.reason")}<textarea value={reason} onChange={(event) => setReason(event.target.value)} required /></label></> : null}
          {action === "instruct-payment" || action === "reissue" ? <><p className="demo-tip">{t("office.demoPaymentNotice")}</p>
            <label>{t("office.demoScenario")}<select value={scenario} onChange={(event) => { setScenario(event.target.value as Scenario); retryKey.current = null; }}>
              <option value="SUCCESS">{t("office.scenarios.SUCCESS")}</option><option value="RETURN">{t("office.scenarios.RETURN")}</option></select></label></> : null}
          <div className="actions"><button type="submit" className="primary" disabled={busy || (reviewing && !item.docket_ready)}>{t("office.submitAction")}</button></div>
        </form>
      </section> : null}
    </> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </section>;
}
