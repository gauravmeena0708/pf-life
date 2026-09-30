import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, command, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { dateOnly, stateLabel } from "../journeyB";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

interface MemberIdRow {
  account_link_id: string; establishment_name: string; date_of_joining: string; date_of_exit: string | null;
  exit_marked_by: string | null; last_contribution_month: string | null; transferred_to: string | null; status: string;
  service_months: number; mark_exit_allowed: boolean; transfer_status: string; primary?: boolean;
}
interface Application { application_id: string; process: string; title: string; state: string; pending: boolean; account_link_id: string | null; submitted_at: string; updated_at: string }
interface AnnexureK {
  transfer_id: string; uan: string; member_name: string; employee_share_paise: number; employer_share_paise: number; total_paise: number; posted_at: string;
  transferred_from: { member_id: string; establishment: string; date_of_joining: string | null; date_of_exit: string | null };
  transferred_to: { member_id: string; establishment: string; date_of_joining: string | null; date_of_exit: string | null };
}
interface AutoTransfer {
  transfer_id: string; state: string; from_account_link_id: string; to_account_link_id: string; amount_paise: number;
}
interface AutoTransfers {
  primary_account_link_id: string | null; reasons: string[]; note: string;
  eligible: (AutoTransfer & { uan: string; date_of_exit: string })[];
  history: (AutoTransfer & { confirmed_at: string | null; posted_at: string | null })[];
}

const lastDay = (month: string) => { const [y, m] = month.split("-").map(Number); return new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10); };
const years = (months: number) => `${Math.floor(months / 12)} years ${months % 12} months`;

/** View › Service History, Manage › Mark Exit, Online Services › One Member – One EPF Account (Form 13) and Annexure K. */
export function ServicePage() {
  const { i18n, t } = useTranslation();
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [annexure, setAnnexure] = useState<AnnexureK | null>(null);
  const [busy, setBusy] = useState(false);
  const history = useQuery({ queryKey: ["service-history"], retry: false,
    queryFn: () => api<Envelope<{ uan: string; member_ids: MemberIdRow[]; total_service_months: number; primary_member_id?: string | null;
      aadhaar_set_uans?: string[]; note?: string }>>("/api/v1/members/me/service-history") });
  const apps = useQuery({ queryKey: ["applications"], retry: false, queryFn: () => api<Envelope<Application[]>>("/api/v1/members/me/applications") });
  const autoTransfers = useQuery({ queryKey: ["member-auto-transfers"], retry: false,
    queryFn: () => api<Envelope<AutoTransfers>>("/api/v1/members/me/transfers/auto") });
  const h = history.data?.data;
  const ids = h?.member_ids ?? [];
  const canExit = ids.filter((m) => m.mark_exit_allowed);
  const from = ids.filter((m) => m.date_of_exit && !m.transferred_to);
  const to = ids.filter((m) => !m.date_of_exit && (m.primary ?? true));   // a transfer goes to the primary member ID only
  const refresh = async () => { await Promise.all([
    qc.invalidateQueries({ queryKey: ["service-history"] }), qc.invalidateQueries({ queryKey: ["applications"] }),
    qc.invalidateQueries({ queryKey: ["member-auto-transfers"] }), qc.invalidateQueries({ queryKey: ["member-passbook"] }),
  ]); };

  async function run(work: () => Promise<string | null>) {
    setError(null); setNotice(null); setBusy(true);
    try { const done = await work(); if (done) { setNotice(done); await refresh(); } } catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }

  const markExit = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const f = new FormData(e.currentTarget);
    const account = String(f.get("account")); const row = ids.find((m) => m.account_link_id === account)!;
    const day = String(f.get("date_of_exit"));
    void run(async () => {
      const token = await stepUp.ask({ action: "mark-exit", resourceId: account,
        summary: `Mark ${day} as your date of exit from ${row.establishment_name} (member ID ${account}). You cannot edit it afterwards.` });
      if (!token) return null;
      await command("POST", "/api/v1/members/me/exits", { account_link_id: account, date_of_exit: day, reason: String(f.get("reason")) }, { stepUpToken: token });
      return `Date of exit ${day} recorded for member ID ${account}.`;
    }); };

  const requestTransfer = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const f = new FormData(e.currentTarget);
    const body = { from_account_link_id: String(f.get("from")), to_account_link_id: String(f.get("to")), attesting_employer: "PRESENT" };
    void run(async () => {
      const token = await stepUp.ask({ action: "submit-transfer", resourceId: h!.uan,
        summary: `Transfer the PF balance of member ID ${body.from_account_link_id} to ${body.to_account_link_id}. Your present employer attests it, then your regional office approves it.` });
      if (!token) return null;
      const r = await command<Envelope<{ case_id: string }>>("POST", "/api/v1/members/me/transfers", body, { stepUpToken: token });
      return `Transfer request ${r.data.case_id} sent to your present employer for attestation.`;
    }); };

  const showAnnexure = (id: string) => void run(async () => {
    setAnnexure((await api<Envelope<AnnexureK>>(`/api/v1/members/me/transfers/${id}/annexure-k`)).data);
    return null;
  });

  function confirmAutoTransfer(item: AutoTransfer) {
    void run(async () => {
      const token = await stepUp.ask({ action: "confirm-auto-transfer", resourceId: item.transfer_id,
        amountPaise: item.amount_paise, summary: `Confirm auto-transfer ${item.transfer_id} of ${rupees(item.amount_paise)} from ${item.from_account_link_id} to ${item.to_account_link_id}.` });
      if (!token) return null;
      await command("POST", `/api/v1/members/me/transfers/auto/${encodeURIComponent(item.transfer_id)}/confirmations`, undefined, { stepUpToken: token });
      return `Auto-transfer ${item.transfer_id} confirmed.`;
    });
  }

  return (
    <section className="stack" aria-labelledby="service-page-heading">
      <PageHeader id="service-page-heading" eyebrow="Member services" title="Service history and transfers"
        description="Your member IDs, dates of exit, transfers between member IDs (Form 13) and their Annexure K." current="Service history" />
      <ProblemMessage error={history.error} />
      <ProblemMessage error={error} />
      {notice ? <p role="status" className="ok">{notice}</p> : null}

      <section className="card stack" aria-labelledby="service-heading"><h2 id="service-heading">Service history</h2>
        {h ? <p className="muted small">UAN {h.uan} · total service {years(h.total_service_months)}
          {h.aadhaar_set_uans?.length ? ` · also linked by your Aadhaar: UAN ${h.aadhaar_set_uans.join(", ")}` : ""}</p> : null}
        {h?.note ? <p className="muted small">{h.note}</p> : null}
        <div className="table-scroll"><table>
          <thead><tr><th scope="col">Member ID</th><th scope="col">Establishment</th><th scope="col">Joined</th><th scope="col">Exit</th><th scope="col">Last contribution</th><th scope="col">Service</th><th scope="col">Transfer</th></tr></thead>
          <tbody>{ids.map((m) => (
            <tr key={m.account_link_id}><td><code>{m.account_link_id}</code>{m.primary ? <> <span className="state-pill" title="Primary member ID">P</span></> : null}</td><td>{m.establishment_name}</td>
              <td>{dateOnly(m.date_of_joining, i18n.language)}</td>
              <td>{m.date_of_exit ? <>{dateOnly(m.date_of_exit, i18n.language)} <span className="muted small">({(m.exit_marked_by ?? "").toLowerCase()})</span></> : "—"}</td>
              <td>{m.last_contribution_month ?? "—"}</td><td>{years(m.service_months)}</td><td>{m.transfer_status}</td></tr>
          ))}</tbody>
        </table></div>
      </section>

      <form className="card stack" aria-labelledby="exit-heading" onSubmit={markExit}><h2 id="exit-heading">Mark exit</h2>
        <p className="muted small">If your employer has not marked your date of exit, you can mark it two months after the last contribution. The date must be in the month of the last contribution received, and it cannot be edited afterwards. Not allowed while another request of yours is in progress.</p>
        {canExit.length === 0 ? <p className="muted">No member ID can be marked now.</p> : <>
          <div className="form-row">
            <label>Member ID<select name="account" required>{canExit.map((m) => <option key={m.account_link_id} value={m.account_link_id}>{m.account_link_id} · {m.establishment_name} (last contribution {m.last_contribution_month})</option>)}</select></label>
            <label>Date of exit<input type="date" name="date_of_exit" required defaultValue={lastDay(canExit[0].last_contribution_month!)} /></label>
            <label>Reason<select name="reason"><option value="CESSATION">Cessation (short service)</option><option value="SUPERANNUATION">Superannuation</option><option value="RETIREMENT">Retirement</option></select></label>
          </div>
          <div className="actions"><button type="submit" className="primary" disabled={busy || !!stepUp.request}>Mark exit</button></div>
        </>}
      </form>

      <form className="card stack" aria-labelledby="transfer-heading" onSubmit={requestTransfer}><h2 id="transfer-heading">One Member – One EPF Account (transfer request)</h2>
        <p className="muted small">Move the balance of a previous member ID into your current one (Form 13). Your present employer attests the request; the regional office verifies and approves it.</p>
        {from.length === 0 || to.length === 0 ? <p className="muted">{from.length === 0 ? "No previous member ID with a date of exit is waiting to be transferred." : "You have no current member ID to transfer into."}</p> : <>
          <div className="form-row">
            <label>From (previous member ID)<select name="from" required>{from.map((m) => <option key={m.account_link_id} value={m.account_link_id}>{m.account_link_id} · {m.establishment_name}</option>)}</select></label>
            <label>To (your primary member ID)<select name="to" required>{to.map((m) => <option key={m.account_link_id} value={m.account_link_id}>{m.account_link_id} · {m.establishment_name}</option>)}</select></label>
          </div>
          <div className="actions"><button type="submit" className="primary" disabled={busy || !!stepUp.request}>Request transfer</button></div>
        </>}
      </form>

      <section className="card stack" aria-labelledby="auto-transfer-heading"><h2 id="auto-transfer-heading">Auto-transfer</h2>
        <ProblemMessage error={autoTransfers.error} />
        {autoTransfers.isLoading ? <p role="status">Loading auto-transfers…</p> : null}
        {autoTransfers.data ? <>
          <p>Primary member ID: <code>{autoTransfers.data.data.primary_account_link_id ?? "Not available"}</code></p>
          <p className="muted">{autoTransfers.data.data.note}</p>
          {autoTransfers.data.data.reasons.length ? <ul className="pending-notice">{autoTransfers.data.data.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul> : null}
          <h3>Eligible transfers</h3>
          {autoTransfers.data.data.eligible.length ? <div className="table-scroll"><table><thead><tr>
            <th scope="col">Transfer</th><th scope="col">UAN</th><th scope="col">From member ID</th><th scope="col">To member ID</th>
            <th scope="col">Date of exit</th><th scope="col">Amount</th><th scope="col">State</th><th scope="col">Confirmation</th>
          </tr></thead><tbody>{autoTransfers.data.data.eligible.map((item) => <tr key={item.transfer_id}>
            <th scope="row">{item.transfer_id}</th><td>{item.uan}</td><td>{item.from_account_link_id}</td><td>{item.to_account_link_id}</td>
            <td>{item.date_of_exit}</td><td>{rupees(item.amount_paise)}</td><td>{item.state.replaceAll("_", " ")}</td>
            <td><button type="button" className="primary" disabled={busy || !!stepUp.request}
              aria-label={`Confirm auto-transfer ${item.transfer_id}`} onClick={() => confirmAutoTransfer(item)}>Confirm transfer</button></td>
          </tr>)}</tbody></table></div> : <p className="muted">No eligible auto-transfers.</p>}
          <h3>Auto-transfer history</h3>
          {autoTransfers.data.data.history.length ? <div className="table-scroll"><table><thead><tr>
            <th scope="col">Transfer</th><th scope="col">From member ID</th><th scope="col">To member ID</th>
            <th scope="col">Amount</th><th scope="col">State</th><th scope="col">Confirmed</th><th scope="col">Posted</th>
          </tr></thead><tbody>{autoTransfers.data.data.history.map((item) => <tr key={item.transfer_id}>
            <th scope="row">{item.transfer_id}</th><td>{item.from_account_link_id}</td><td>{item.to_account_link_id}</td>
            <td>{rupees(item.amount_paise)}</td><td>{item.state.replaceAll("_", " ")}</td>
            <td>{item.confirmed_at ?? "—"}</td><td>{item.posted_at ?? "—"}</td>
          </tr>)}</tbody></table></div> : <p className="muted">No auto-transfer history.</p>}
        </> : null}
      </section>

      <section className="card stack" aria-labelledby="applications-heading"><h2 id="applications-heading">Recent applications</h2>
        {apps.data?.data.length ? <div className="table-scroll"><table>
          <thead><tr><th scope="col">Application</th><th scope="col">Reference</th><th scope="col">Status</th><th scope="col">Updated</th><th scope="col" /></tr></thead>
          <tbody>{apps.data.data.map((a) => (
            <tr key={a.application_id}><td>{a.title}{a.account_link_id ? <span className="muted small"> · {a.account_link_id}</span> : null}</td><td><code>{a.application_id}</code></td>
              <td><span className="state-pill">{stateLabel(a.state, t) || a.state.replaceAll("_", " ").toLowerCase()}</span></td>
              <td>{dateOnly(a.updated_at, i18n.language)}</td>
              <td>{a.process === "transfer_form13" && a.state === "APPROVED" ? <button type="button" disabled={busy || !!stepUp.request} onClick={() => showAnnexure(a.application_id)}>Annexure K</button> : null}</td></tr>
          ))}</tbody>
        </table></div> : <p className="muted">No applications yet.</p>}
      </section>

      {annexure ? <section className="card stack" aria-labelledby="annexure-heading"><h2 id="annexure-heading">Annexure K — transfer {annexure.transfer_id}</h2>
        <dl className="kv"><dt>Member</dt><dd>{annexure.member_name} · UAN {annexure.uan}</dd>
          <dt>Transferred from</dt><dd>{annexure.transferred_from.member_id} · {annexure.transferred_from.establishment} ({dateOnly(annexure.transferred_from.date_of_joining, i18n.language)} to {dateOnly(annexure.transferred_from.date_of_exit, i18n.language)})</dd>
          <dt>Transferred to</dt><dd>{annexure.transferred_to.member_id} · {annexure.transferred_to.establishment}</dd>
          <dt>Employee share</dt><dd>{rupees(annexure.employee_share_paise)}</dd><dt>Employer share</dt><dd>{rupees(annexure.employer_share_paise)}</dd>
          <dt>Total transferred</dt><dd><strong>{rupees(annexure.total_paise)}</strong></dd><dt>Posted</dt><dd>{dateOnly(annexure.posted_at, i18n.language)}</dd></dl>
        <p className="muted small">Illustrative statement; the real Annexure K also carries pension service details.</p>
      </section> : null}
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}
