import { useQuery } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, command, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";
import { SharesSection } from "../claimant/DeathClaimPages";
import { AnnexureKSection, LocksSection } from "./LedgerTools";
import { statusLabel } from "../statusLabel";

type Json = Record<string, unknown>;
const text = (f: FormData, k: string) => String(f.get(k) ?? "").trim();
const show = (v: unknown): string => typeof v === "number" ? String(v) : v === null || v === undefined ? "—" : typeof v === "object" ? JSON.stringify(v) : String(v);

function Facts({ data }: { data: Json }) {
  return <dl className="kv">{Object.entries(data).map(([k, v]) => <div key={k} style={{ display: "contents" }}>
    <dt>{k.replace(/_paise$/, "").replaceAll("_", " ")}</dt><dd>{k.endsWith("_paise") && typeof v === "number" ? rupees(v) : show(v)}</dd></div>)}</dl>;
}

/** Claim office tools: the accounts wing's CAD, the cash section's payment scroll, and the dealing assistant's
 * member 360 view, inoperative accounts and claim audit trail. Each role sees its own sections. */
export function ClaimToolsPage() {
  const { t } = useTranslation();
  const stepUp = useStepUp();
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const role = session.data?.stakeholder ?? "";
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [cad, setCad] = useState<Json | null>(null);
  const [scroll, setScroll] = useState<Json | null>(null);
  const [lookup, setLookup] = useState<Json | null>(null);
  const [trail, setTrail] = useState<Json | null>(null);
  const [inoperative, setInoperative] = useState<Json[] | null>(null);
  const [tds, setTds] = useState<Json | null>(null);
  const [transfer, setTransfer] = useState<{ option_id: string; state: string; next_step: string } | null>(null);
  const transferKeys = useRef<Record<string, string>>({});
  const options = useQuery({ queryKey: ["accounts", "higher-pension-options"], enabled: role === "fo.da_accounts", retry: false,
    queryFn: () => api<Envelope<{ option_id: string; dues_paise: number; state: string; next_step: string }[]>>(
      "/api/v1/office/pensions/higher-pension-options?state=APPROVED") });
  const [tdsYear, setTdsYear] = useState(() => {
    const today = new Date(); const start = today.getFullYear() - (today.getMonth() < 3 ? 1 : 0);
    return `${start}-${String(start + 1).slice(-2)}`;
  });
  const staticData = useQuery({ queryKey: ["cad-static"], enabled: role === "fo.fa_accounts", retry: false,
    queryFn: () => api<Envelope<Json>>("/api/v1/office/system/cad-static-data") });

  async function run(work: () => Promise<string | null>) {
    setError(null); setNotice(null);
    try { const done = await work(); if (done) setNotice(done); } catch (cause) { setError(cause); }
  }

  const viewCad = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const id = text(new FormData(e.currentTarget), "claim");
    void run(async () => {
      setCad((await api<Envelope<Json>>(`/api/v1/office/claims/${id}/cad`)).data);
      return null;
    }); };

  const previewScroll = () => void run(async () => {
    setScroll((await api<Envelope<Json>>("/api/v1/office/payment-scrolls/ready")).data); return null;
  });
  const sendScroll = (scenario: string) => void run(async () => {
    const preview = (await api<Envelope<{ total_paise: number; claims: unknown[] }>>("/api/v1/office/payment-scrolls/ready")).data;
    const token = await stepUp.ask({ action: "generate-scroll", resourceId: "RO-DEMO-01", amountPaise: preview.total_paise,
      summary: `Send ${preview.claims.length} approved claims (${rupees(preview.total_paise)}) to the bank in one scroll.` });
    if (!token) return null;
    const r = await command<Envelope<Json>>("POST", "/api/v1/office/payment-scrolls", { demo_scenario: scenario }, { stepUpToken: token });
    setScroll(r.data);
    return `Scroll ${String(r.data.scroll_id)} sent to the bank.`;
  });
  const reconcileScroll = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const f = new FormData(e.currentTarget); const id = text(f, "scroll");
    void run(async () => {
      const token = await stepUp.ask({ action: "reconcile-scroll", resourceId: id, amountPaise: Math.round(Number(text(f, "total")) * 100),
        summary: `Reconcile the bank's returns for scroll ${id}.` });
      if (!token) return null;
      setScroll((await command<Envelope<Json>>("POST", `/api/v1/office/payment-scrolls/${id}/return-reconciliations`, undefined, { stepUpToken: token })).data);
      return `Scroll ${id} reconciled.`;
    }); };

  const view360 = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const f = new FormData(e.currentTarget);
    void run(async () => {
      setLookup((await api<Envelope<Json>>(`/api/v1/office/members/${text(f, "uan")}?purpose=${encodeURIComponent(text(f, "purpose"))}`)).data);
      return "Recorded in the audit log with its purpose.";
    }); };
  const viewTrail = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const id = text(new FormData(e.currentTarget), "claim");
    void run(async () => {
      const [t, forms] = await Promise.all([api<Envelope<Json>>(`/api/v1/office/claims/${id}/audit-trail`), api<Envelope<Json>>(`/api/v1/office/claims/${id}/additional-forms`)]);
      setTrail({ ...t.data, additional_forms: forms.data.forms });
      return null;
    }); };
  const loadInoperative = () => void run(async () => {
    setInoperative((await api<Envelope<{ accounts: Json[] }>>("/api/v1/office/accounts/inoperative")).data.accounts); return null;
  });
  const verifyInoperative = (e: FormEvent<HTMLFormElement>, id: string) => {
    e.preventDefault(); const form = e.currentTarget; const fields = new FormData(form);
    void run(async () => {
      const co_worker_uans = text(fields, "co_workers").split(",").map((item) => item.trim()).filter(Boolean);
      await command("POST", `/api/v1/office/accounts/${encodeURIComponent(id)}/crowdsource-verifications`,
        { co_worker_uans, note: text(fields, "note") });
      form.reset();
      setInoperative((current) => current?.map((a) => a.account_link_id === id ? { ...a, verified: true } : a) ?? null);
      return `Member ID ${id} verified through co-workers.`;
    });
  };
  const reactivate = (e: FormEvent<HTMLFormElement>, id: string, balance: number) => {
    e.preventDefault(); const note = text(new FormData(e.currentTarget), "note");
    void run(async () => {
      const token = await stepUp.ask({ action: "reactivate-account", resourceId: id, amountPaise: balance,
        summary: `Reactivate member ID ${id} with a balance of ${rupees(balance)}.` });
      if (!token) return null;
      await command("POST", `/api/v1/office/accounts/${encodeURIComponent(id)}/reactivations`,
        { decision: "REACTIVATE", note }, { stepUpToken: token });
      setInoperative((current) => current?.map((a) => a.account_link_id === id ? { ...a, reactivated: true, status: "REACTIVATED" } : a) ?? null);
      return `Member ID ${id} reactivated.`;
    });
  };
  const fileTds = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault(); const quarter = text(new FormData(e.currentTarget), "quarter");
    setTds(null);
    void run(async () => {
      setTds((await command<Envelope<Json>>("POST", "/api/v1/office/tds/computations",
        { financial_year: tdsYear, quarter })).data); return null;
    });
  };
  const requestTransfer = (option: { option_id: string; dues_paise: number }) => void run(async () => {
    const token = await stepUp.ask({ action: "transfer-higher-pension-dues", resourceId: option.option_id,
      amountPaise: option.dues_paise, summary: `Request transfer of ${rupees(option.dues_paise)} for higher-pension option ${option.option_id}.` });
    if (!token) return null;
    const key = transferKeys.current[option.option_id] ??= crypto.randomUUID();
    const result = await command<Envelope<{ option_id: string; state: string; next_step: string }>>(
      "POST", `/api/v1/office/pensions/higher-pension-options/${encodeURIComponent(option.option_id)}/ledger-transfers`,
      undefined, { stepUpToken: token, idempotencyKey: key });
    setTransfer(result.data); delete transferKeys.current[option.option_id];
    await options.refetch();
    return `Transfer requested for ${option.option_id}.`;
  });

  return (
    <section className="stack" aria-labelledby="claim-tools-heading">
      <PageHeader id="claim-tools-heading" eyebrow="Regional office" title="Claim office tools" current="Claim tools"
        description="Claim Approval Dockets, payment scrolls, member 360 view, inoperative accounts, claim audit trails, death-claim shares, ledger locks and Annexure K." />
      <ProblemMessage error={error} />
      {notice ? <p role="status" className="ok">{notice}</p> : null}

      {role === "fo.da_accounts" ? <section className="card stack" aria-labelledby="higher-dues-heading"><h2 id="higher-dues-heading">Higher pension dues transfer</h2>
        <ProblemMessage error={options.error} />{options.isLoading ? <p role="status">Loading approved options…</p> : null}
        {options.data?.data.length === 0 ? <p className="muted small">No approved options awaiting transfer.</p> : null}
        {options.data?.data.map((option) => <div className="profile-card stack" key={option.option_id}>
          <p><strong>{option.option_id}</strong> · {statusLabel(option.state, t)} · {rupees(option.dues_paise)}</p>
          <p>{option.next_step}</p><div className="actions"><button type="button" onClick={() => requestTransfer(option)}>Request dues transfer</button></div>
        </div>)}
        {transfer ? <p role="status">{transfer.option_id} · {statusLabel(transfer.state, t)}. {transfer.next_step}</p> : null}
      </section> : null}

      {role === "fo.fa_accounts" ? <section className="card stack" aria-labelledby="cad-heading"><h2 id="cad-heading">Claim Approval Docket (CAD)</h2>
        <p className="muted small">Each scrutinising officer generates the docket before acting (CITES); the accounts wing views the latest and every level's version.</p>
        <form className="search-input-row" onSubmit={viewCad}><label>Claim ID<input name="claim" required placeholder="CLM-…" /></label>
          <button type="submit" className="primary">View docket</button></form>
        {cad ? <Facts data={cad} /> : null}
        {staticData.data ? <details><summary>CAD static data {String(staticData.data.data.version)}</summary><Facts data={staticData.data.data} /></details> : null}
      </section> : null}

      {role === "fo.cash" ? <section className="card stack" aria-labelledby="scroll-heading"><h2 id="scroll-heading">Payment scroll</h2>
        <p className="muted small">Every approved claim of the office whose ledger debit is posted goes to the bank in one scroll (one-time code bound to the total).</p>
        <div className="actions"><button type="button" onClick={previewScroll}>Show claims ready for payment</button>
          <button type="button" className="primary" onClick={() => sendScroll("SUCCESS")}>Send scroll to the bank</button>
          <button type="button" onClick={() => sendScroll("RETURN")}>Send (simulate bank return)</button></div>
        <form className="search-input-row" onSubmit={reconcileScroll}><label>Scroll ID<input name="scroll" required placeholder="SCR-…" /></label>
          <label>Scroll total (₹)<input name="total" required inputMode="numeric" /></label><button type="submit">Reconcile returns</button></form>
        {scroll ? <Facts data={scroll} /> : null}
      </section> : null}

      {["fo.da_accounts", "fo.oic", "fo.ao", "fo.apfc"].includes(role) ? <>
        {role === "fo.da_accounts" ? <form className="card stack" aria-labelledby="member360-heading" onSubmit={view360}><h2 id="member360-heading">Member 360 view</h2>
          <div className="form-row"><label>UAN<input name="uan" required pattern="[0-9]{12}" inputMode="numeric" /></label>
            <label>Purpose (recorded)<input name="purpose" required minLength={10} /></label></div>
          <div className="actions"><button type="submit" className="primary">View</button></div>
          {lookup ? <Facts data={lookup} /> : null}
        </form> : null}
        <section className="card stack" aria-labelledby="inoperative-heading"><h2 id="inoperative-heading">Inoperative accounts</h2>
          <p className="muted small">Member IDs with a balance but no credit for 36 months (illustrative, per the SOP on transaction-less and inoperative accounts).</p>
          <div className="actions"><button type="button" onClick={loadInoperative}>List</button></div>
          {inoperative ? inoperative.length ? <div className="stack">{inoperative.map((a) => {
            const id = String(a.account_link_id); const balance = Number(a.balance_paise);
            return <section className="profile-card stack" key={id} aria-label={`Inoperative account ${id}`}>
              <h3>{id} · {String(a.name)}</h3>
              <p>Balance: {rupees(balance)} · Last credit: {show(a.last_credit)}</p>
              <p><span className="state-pill">{statusLabel(a.verified ? "VERIFIED" : "NOT_VERIFIED", t)}</span>{" "}
                <span className="state-pill">{statusLabel(a.reactivated ? "REACTIVATED" : "INOPERATIVE", t)}</span></p>
              {role === "fo.da_accounts" && !a.verified ? <form className="stack" aria-label={`Verify ${id} through co-workers`} onSubmit={(e) => verifyInoperative(e, id)}>
                <h4>Verify through co-workers</h4><label>Co-worker UANs (comma separated)<input name="co_workers" required /></label>
                <label>Verification note<textarea name="note" required minLength={2} maxLength={1000} /></label>
                <div className="actions"><button type="submit">Verify</button></div></form> : null}
              {(role === "fo.ao" || role === "fo.apfc") && !a.reactivated ? <form className="stack" aria-label={`Reactivate ${id}`} onSubmit={(e) => reactivate(e, id, balance)}>
                <label>Decision note<textarea name="note" required maxLength={2000} /></label>
                <div className="actions"><button type="submit" className="primary">Reactivate</button></div></form> : null}
            </section>;
          })}</div> : <p className="muted">None.</p> : null}
        </section>
        {role === "fo.da_accounts" ? <section className="card stack" aria-labelledby="tds-heading"><h2 id="tds-heading">Quarterly TDS statement (Form 26Q, mock filing)</h2>
          <form className="search-input-row" onSubmit={fileTds}><label>Financial year<input value={tdsYear} onChange={(e) => setTdsYear(e.target.value)} required pattern="[0-9]{4}-[0-9]{2}" placeholder="2025-26" /></label>
            <label>Quarter<select name="quarter"><option>Q1</option><option>Q2</option><option>Q3</option><option>Q4</option></select></label>
            <button type="submit" className="primary">File mock statement</button></form>
          {tds ? <><p><strong>Acknowledgement:</strong> {show(tds.acknowledgement)}</p>
            <div className="table-scroll"><table><thead><tr><th scope="col">Deductee UAN</th><th scope="col">Claim</th><th scope="col">Paid on</th><th scope="col" className="numeric">Amount paid</th><th scope="col" className="numeric">TDS</th><th scope="col">PAN</th></tr></thead>
              <tbody>{(tds.deductees as Json[]).map((item) => <tr key={String(item.claim_id)}><td>{show(item.uan_masked)}</td><td>{show(item.claim_id)}</td><td>{show(item.paid_on)}</td><td className="numeric">{rupees(Number(item.amount_paid_paise))}</td><td className="numeric">{rupees(Number(item.tds_paise))}</td><td>{statusLabel(String(item.pan_status), t)}</td></tr>)}</tbody>
              <tfoot><tr><th scope="row" colSpan={3}>Total</th><td className="numeric">{rupees(Number((tds.totals as Json).amount_paid_paise))}</td><td className="numeric">{rupees(Number((tds.totals as Json).tds_paise))}</td><td /></tr></tfoot></table></div>
            <p className="muted small">{show(tds.note)}</p></> : null}
        </section> : null}
        {role === "fo.da_accounts" ? <form className="card stack" aria-labelledby="trail-heading" onSubmit={viewTrail}><h2 id="trail-heading">Claim audit trail</h2>
          <label>Claim ID<input name="claim" required placeholder="CLM-…" /></label>
          <div className="actions"><button type="submit">Show</button></div>
          {trail ? <Facts data={trail} /> : null}
        </form> : null}
      </> : null}
      {role === "fo.apfc" ? <SharesSection /> : null}
      {role === "fo.oic" ? <LocksSection /> : null}
      {role === "fo.da_accounts" ? <AnnexureKSection /> : null}
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}
