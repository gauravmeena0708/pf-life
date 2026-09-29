import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, command, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";
import { PensionEstimate } from "./PensionEstimate";

interface Claim { claim_id: string; state: string; pension_from: string; ppo_id: string | null; next_step: string | null;
  worksheet: { monthly_paise: number; working: string; rule_version: string } | null; arrears: { months: string[]; amount_paise: number } | null;
  history: { state: string; role: string; note: string; at: string }[] }
interface Certificate { cert_id: string; service_months: number; state: string; surrender_purpose: string | null; issued_at: string }

/** Online Services › Claim (Form 10D): apply for a monthly pension and follow it desk by desk; or keep service
 * with a scheme certificate (Form 10C option) and later surrender it. */
export function PensionApplicationPage() {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const claims = useQuery({ queryKey: ["pension-applications"], retry: false, queryFn: () => api<Envelope<Claim[]>>("/api/v1/members/me/pension-applications") });
  const cert = useQuery({ queryKey: ["scheme-certificate"], retry: false, queryFn: () => api<Envelope<Certificate>>("/api/v1/members/me/pension-scheme-certificate") });
  const me = useQuery({ queryKey: ["me"], retry: false, queryFn: () => api<Envelope<{ uan: string }>>("/api/v1/members/me") });
  const claim = claims.data?.data[0];

  async function run(work: () => Promise<string | null>) {
    setError(null); setNotice(null);
    try {
      const done = await work();
      if (done) { setNotice(done); await qc.invalidateQueries({ queryKey: ["pension-applications"] }); await qc.invalidateQueries({ queryKey: ["scheme-certificate"] }); }
    } catch (cause) { setError(cause); }
  }
  const apply = () => void run(async () => {
    const r = await command<Envelope<Claim & { estimate: { monthly_paise: number } }>>("POST", "/api/v1/members/me/pension-applications", {});
    return `Form 10D filed (${r.data.claim_id}); pension from ${r.data.pension_from}, estimated ${rupees(r.data.estimate.monthly_paise)} a month.`;
  });
  const requestCertificate = () => void run(async () => {
    const token = await stepUp.ask({ action: "request-scheme-certificate", resourceId: me.data!.data.uan,
      summary: "Ask for a scheme certificate: your pension service is kept instead of being withdrawn." });
    if (!token) return null;
    const r = await command<Envelope<Certificate>>("POST", "/api/v1/members/me/pension-scheme-certificates", { confirm: true }, { stepUpToken: token });
    return `Scheme certificate ${r.data.cert_id} issued for ${r.data.service_months} months of service.`;
  });
  const surrender = (c: Certificate) => void run(async () => {
    const token = await stepUp.ask({ action: "surrender-scheme-certificate", resourceId: c.cert_id,
      summary: `Surrender scheme certificate ${c.cert_id} so that its service counts towards a monthly pension.` });
    if (!token) return null;
    await command("POST", `/api/v1/members/me/pension-scheme-certificates/${c.cert_id}/surrenders`, { purpose: "MONTHLY_PENSION" }, { stepUpToken: token });
    return `Scheme certificate ${c.cert_id} surrendered; your office validates it.`;
  });

  return (
    <section className="stack" aria-labelledby="pension-application-heading">
      <PageHeader id="pension-application-heading" eyebrow="Member services" title="Pension (Form 10D) and scheme certificate" current="Pension"
        description="Apply for a monthly pension after leaving service, and follow it through each desk of your office." />
      <ProblemMessage error={error} />
      {notice ? <p role="status" className="ok">{notice}</p> : null}
      <section className="card stack" aria-labelledby="form10d-heading"><h2 id="form10d-heading">Monthly pension (Form 10D)</h2>
        {claim ? <>
          <p>Application <code>{claim.claim_id}</code> · pension from {claim.pension_from} · <span className="state-pill">{claim.state.replaceAll("_", " ").toLowerCase()}</span>
            {claim.ppo_id ? <> · PPO <code>{claim.ppo_id}</code></> : null}</p>
          {claim.next_step ? <p className="demo-tip">Next: {claim.next_step}.</p> : null}
          {claim.worksheet ? <p>Pension <strong>{rupees(claim.worksheet.monthly_paise)}</strong> a month — {claim.worksheet.working} <span className="muted small">({claim.worksheet.rule_version})</span></p> : null}
          {claim.arrears ? <p>Initial arrear {rupees(claim.arrears.amount_paise)} for {claim.arrears.months.length} months.</p> : null}
          <ol className="claim-timeline">{claim.history.map((h, i) => <li key={i}><div className="detail-head"><strong>{h.state.replaceAll("_", " ").toLowerCase()}</strong>
            <time dateTime={h.at}>{new Date(h.at).toLocaleString("en-IN")}</time></div><p className="muted small">By {h.role}</p><p>{h.note}</p></li>)}</ol>
        </> : <>
          <p className="muted small">Needs a date of exit, at least 10 years of service and age 50 or more (a reduced pension before 58). Illustrative rules.</p>
          <div className="actions"><button type="button" className="primary" onClick={apply}>Apply for monthly pension</button></div>
        </>}
      </section>
      <PensionEstimate />
      <section className="card stack" aria-labelledby="scheme-certificate-heading"><h2 id="scheme-certificate-heading">Scheme certificate (Form 10C option)</h2>
        {cert.data ? <p>Certificate <code>{cert.data.data.cert_id}</code> · {cert.data.data.service_months} months of service ·
          <span className="state-pill">{cert.data.data.state.toLowerCase()}</span>
          {cert.data.data.state === "ISSUED" ? <button type="button" onClick={() => surrender(cert.data!.data)}>Surrender for monthly pension</button> : null}</p>
          : <><p className="muted small">With less than 10 years of service you can keep your pension service for later instead of withdrawing it.</p>
            <div className="actions"><button type="button" onClick={requestCertificate}>Ask for a scheme certificate</button></div></>}
      </section>
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}
