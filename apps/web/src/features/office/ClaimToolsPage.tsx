import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";
import { SharesSection } from "../claimant/DeathClaimPages";
import { AnnexureKSection, LocksSection } from "./LedgerTools";

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
  const staticData = useQuery({ queryKey: ["cad-static"], enabled: role === "fo.fa_accounts", retry: false,
    queryFn: () => api<Envelope<Json>>("/api/v1/office/system/cad-static-data") });

  async function run(work: () => Promise<string | null>) {
    setError(null); setNotice(null);
    try { const done = await work(); if (done) setNotice(done); } catch (cause) { setError(cause); }
  }

  const generateCad = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const id = text(new FormData(e.currentTarget), "claim");
    void run(async () => {
      const existing = await api<Envelope<Json>>(`/api/v1/office/claims/${id}/cad`).catch(() => null);
      if (existing) { setCad(existing.data); return "A CAD already exists for this claim."; }
      const trailData = (await api<Envelope<{ amount_paise: number }>>(`/api/v1/office/claims/${id}/audit-trail`).catch(() => null))?.data;
      const token = await stepUp.ask({ action: "generate-cad", resourceId: id, amountPaise: trailData?.amount_paise,
        summary: `Generate the Claim Authorization Document for ${id}${trailData ? ` (${rupees(trailData.amount_paise)})` : ""}.` });
      if (!token) return null;
      setCad((await command<Envelope<Json>>("POST", `/api/v1/office/claims/${id}/cad`, undefined, { stepUpToken: token })).data);
      return `CAD generated for ${id}.`;
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

  return (
    <section className="stack" aria-labelledby="claim-tools-heading">
      <PageHeader id="claim-tools-heading" eyebrow="Regional office" title="Claim office tools" current="Claim tools"
        description="Claim Authorization Document, payment scrolls, member 360 view, inoperative accounts, claim audit trails, death-claim shares, ledger locks and Annexure K." />
      <ProblemMessage error={error} />
      {notice ? <p role="status" className="ok">{notice}</p> : null}

      {role === "fo.fa_accounts" ? <section className="card stack" aria-labelledby="cad-heading"><h2 id="cad-heading">Claim Authorization Document (CAD)</h2>
        <form className="search-input-row" onSubmit={generateCad}><label>Claim ID<input name="claim" required placeholder="CLM-…" /></label>
          <button type="submit" className="primary">Generate or view CAD</button></form>
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

      {role === "fo.da_accounts" || role === "fo.oic" ? <>
        {role === "fo.da_accounts" ? <form className="card stack" aria-labelledby="member360-heading" onSubmit={view360}><h2 id="member360-heading">Member 360 view</h2>
          <div className="form-row"><label>UAN<input name="uan" required pattern="[0-9]{12}" inputMode="numeric" /></label>
            <label>Purpose (recorded)<input name="purpose" required minLength={10} /></label></div>
          <div className="actions"><button type="submit" className="primary">View</button></div>
          {lookup ? <Facts data={lookup} /> : null}
        </form> : null}
        <section className="card stack" aria-labelledby="inoperative-heading"><h2 id="inoperative-heading">Inoperative accounts</h2>
          <p className="muted small">Member IDs with a balance but no credit for 36 months (illustrative, per the SOP on transaction-less and inoperative accounts).</p>
          <div className="actions"><button type="button" onClick={loadInoperative}>List</button></div>
          {inoperative ? inoperative.length ? <div className="table-scroll"><table><thead><tr><th scope="col">Member ID</th><th scope="col">Name</th><th scope="col">Balance</th><th scope="col">Last credit</th></tr></thead>
            <tbody>{inoperative.map((a) => <tr key={String(a.account_link_id)}><td>{String(a.account_link_id)}</td><td>{String(a.name)}</td><td>{rupees(Number(a.balance_paise))}</td><td>{String(a.last_credit)}</td></tr>)}</tbody>
          </table></div> : <p className="muted">None.</p> : null}
        </section>
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
