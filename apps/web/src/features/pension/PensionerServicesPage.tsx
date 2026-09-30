import { statusLabel } from "../statusLabel";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

interface Ppo { ppo_id: string; name: string; uan: string; date_of_birth: string; pension_type: string; pension_start: string; original_monthly_paise: number;
  current_monthly_paise: number; working: string; rule_version: string; issuing_office: string; disbursing_bank: { ifsc: string; account_last4: string }; status: string }
interface Lc { ppo_id: string; state: string; valid_till: string | null; source: string | null; reference: string | null; pension_status: string }
interface Slip { month: string; lines: { kind: string; amount_paise: number; paid_on: string }[]; gross_paise: number; net_paise: number; deductions: Record<string, number>; bank_account_last4: string }

const lastMonth = () => { const d = new Date(); d.setDate(0); return d.toISOString().slice(0, 7); };

/** Pensioner services: life certificate (mock Jeevan Pramaan), PPO, pension slip, bank change, declarations. */
export function PensionerServicesPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [slip, setSlip] = useState<Slip | null>(null);
  const ppo = useQuery({ queryKey: ["ppo"], retry: false, queryFn: () => api<Envelope<Ppo>>("/api/v1/pensioners/me/ppo") });
  const lc = useQuery({ queryKey: ["life-certificate"], retry: false, queryFn: () => api<Envelope<Lc>>("/api/v1/pensioners/me/life-certificate") });
  const p = ppo.data?.data;

  async function run(work: () => Promise<string | null>) {
    setError(null); setNotice(null);
    try {
      const done = await work();
      if (done) { setNotice(done); await qc.invalidateQueries({ queryKey: ["ppo"] }); await qc.invalidateQueries({ queryKey: ["life-certificate"] }); }
    } catch (cause) { setError(cause); }
  }

  const submitDlc = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const f = new FormData(e.currentTarget);
    void run(async () => {
      const r = await command<Envelope<{ pramaan_id: string; valid_till: string; resumed: boolean }>>("POST", "/api/v1/pensioners/me/life-certificate/submissions",
        { face_authentication_consent: f.get("consent") === "on" });
      return `Life certificate recorded (Jeevan Pramaan ID ${r.data.pramaan_id}), valid till ${r.data.valid_till}.${r.data.resumed ? " Your pension is resumed." : ""}`;
    }); };

  const showSlip = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const f = new FormData(e.currentTarget);
    void run(async () => { setSlip((await api<Envelope<Slip>>(`/api/v1/pensioners/me/pension-slips?month=${String(f.get("month"))}`)).data); return null; }); };

  const changeBank = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    void run(async () => {
      const token = await stepUp.ask({ action: "change-pension-bank", resourceId: p!.ppo_id, summary: "Change the bank account your pension is paid into. Your office approves the change." });
      if (!token) return null;
      const r = await command<Envelope<{ activity_id: string }>>("POST", "/api/v1/pensioners/me/bank-change-requests",
        { ifsc: String(f.get("ifsc")).trim().toUpperCase(), account_number: String(f.get("account")).trim() }, { stepUpToken: token });
      form.reset();
      return `Bank change request ${r.data.activity_id} sent to your office for approval.`;
    }); };

  const declare = (kind: "NON_REMARRIAGE" | "NON_EMPLOYMENT") => void run(async () => {
    await command("POST", "/api/v1/pensioners/me/declarations", { kind, declared: true });
    return `${kind === "NON_REMARRIAGE" ? "Non-remarriage" : "Non-employment"} declaration recorded.`;
  });

  return (
    <section className="stack" aria-labelledby="pensioner-services-heading">
      <PageHeader id="pensioner-services-heading" eyebrow="Pensioner services" title="Life certificate and services" current="Services"
        description="Submit your Digital Life Certificate, see your PPO and pension slips, change your bank account, and make declarations." />
      <ProblemMessage error={ppo.error} />
      <ProblemMessage error={error} />
      {notice ? <p role="status" className="ok">{notice}</p> : null}

      <form className="card stack" aria-labelledby="lc-heading" onSubmit={submitDlc}><h2 id="lc-heading">Life certificate</h2>
        {lc.data ? <p>Status: <span className="state-pill">{statusLabel(lc.data.data.state, t)}</span> · valid till <strong>{lc.data.data.valid_till ?? "—"}</strong>
          {lc.data.data.reference ? <span className="muted small"> · {lc.data.data.source?.replaceAll("_", " ").toLowerCase()} {lc.data.data.reference}</span> : null}
          {lc.data.data.pension_status === "SUSPENDED" ? <span className="state-pill"> pension suspended</span> : null}</p> : null}
        <p className="muted small">A certificate keeps your pension in payment for a year. This demonstration simulates Jeevan Pramaan face authentication (no real check).</p>
        <label className="check-row"><input type="checkbox" name="consent" required />I consent to face authentication with my Aadhaar (mock)</label>
        <div className="actions"><button type="submit" className="primary">Submit Digital Life Certificate</button></div>
      </form>

      {p ? <section className="card stack" aria-labelledby="ppo-heading"><h2 id="ppo-heading">Pension Payment Order</h2>
        <dl className="kv"><dt>PPO number</dt><dd><code>{p.ppo_id}</code></dd><dt>Name</dt><dd>{p.name}</dd><dt>Pension type</dt><dd>{p.pension_type}</dd>
          <dt>Pension from</dt><dd>{p.pension_start}</dd><dt>Pension at issue</dt><dd>{rupees(p.original_monthly_paise)} a month</dd>
          <dt>Pension now</dt><dd><strong>{rupees(p.current_monthly_paise)}</strong> a month <span className="muted small">— {p.working} ({p.rule_version})</span></dd>
          <dt>Issuing office</dt><dd>{p.issuing_office}</dd><dt>Paid into</dt><dd>account ending {p.disbursing_bank.account_last4} · IFSC {p.disbursing_bank.ifsc}</dd>
          <dt>Status</dt><dd>{statusLabel(p.status, t)}</dd></dl>
        <div className="actions"><button type="button" onClick={() => window.print()}>Print</button></div>
      </section> : null}

      <form className="card stack" aria-labelledby="slip-heading" onSubmit={showSlip}><h2 id="slip-heading">Pension slip</h2>
        <div className="form-row"><label>Month<input type="month" name="month" required defaultValue={lastMonth()} /></label></div>
        <div className="actions"><button type="submit">Show slip</button></div>
        {slip ? <div className="table-scroll"><table>
          <thead><tr><th scope="col">Credit</th><th scope="col">Paid on</th><th scope="col">Amount</th></tr></thead>
          <tbody>{slip.lines.map((l, i) => <tr key={i}><td>{l.kind === "MONTHLY" ? `Pension for ${slip.month}` : "Arrears"}</td><td>{l.paid_on}</td><td>{rupees(l.amount_paise)}</td></tr>)}
            <tr><td>Deductions (commutation, recovery, TDS)</td><td /><td>{rupees(Object.values(slip.deductions).reduce((a, b) => a + b, 0))}</td></tr>
            <tr><th scope="row" colSpan={2}>Net paid into account ending {slip.bank_account_last4}</th><td><strong>{rupees(slip.net_paise)}</strong></td></tr></tbody>
        </table></div> : null}
      </form>

      <form className="card stack" aria-labelledby="bank-change-heading" onSubmit={changeBank}><h2 id="bank-change-heading">Change bank account</h2>
        <div className="form-row">
          <label>IFSC<input name="ifsc" required pattern="[A-Za-z]{4}0[A-Za-z0-9]{6}" maxLength={11} /></label>
          <label>Account number<input name="account" required inputMode="numeric" pattern="[0-9]{9,18}" /></label>
        </div>
        <p className="muted small">Checked by a mock penny-drop (numbers ending 0000 fail); your office approves the change.</p>
        <div className="actions"><button type="submit" className="primary">Request change</button></div>
      </form>

      <section className="card stack" aria-labelledby="declarations-heading"><h2 id="declarations-heading">Declarations</h2>
        <p className="muted small">Some pensions continue only while you declare that you have not remarried or are not employed.</p>
        <div className="actions"><button type="button" onClick={() => declare("NON_REMARRIAGE")}>Declare non-remarriage</button>
          <button type="button" onClick={() => declare("NON_EMPLOYMENT")}>Declare non-employment</button></div>
      </section>
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}
