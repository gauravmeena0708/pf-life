import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, command, getSession, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";
import { statusLabel } from "../statusLabel";
import { ClearancesTable, SensitivePostsPanel, type Clearance } from "../vigilance/PreventiveVigilance";

interface Office { office_id: string; name?: string; zone_id?: string }
interface Posting { username: string; stakeholder: string; office_id: string; previous: { stakeholder: string; office_id: string }; note: string }
export function HrmPage() {
  const { t } = useTranslation();
  const qc = useQueryClient(); const stepUp = useStepUp();
  const [busy, setBusy] = useState(false); const [error, setError] = useState<unknown>(null); const [result, setResult] = useState<Posting | null>(null);
  const [clearanceBusy, setClearanceBusy] = useState(false); const [clearanceError, setClearanceError] = useState<unknown>(null); const [clearanceResult, setClearanceResult] = useState<Clearance | null>(null);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const hr = session.data?.stakeholder === "ho.hr";
  const me = useQuery({ queryKey: ["hrm-me"], enabled: hr, retry: false,
    queryFn: () => api<Envelope<{ username: string; role: string; office: Office }>>("/api/v1/hrm/me") });
  const offices = useQuery({ queryKey: ["public-offices"], enabled: hr, retry: false,
    queryFn: () => api<Envelope<Office[]>>("/api/v1/public/offices") });
  async function post(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (!hr || busy) return;
    const form = e.currentTarget; const f = new FormData(form); const text = (name: string) => String(f.get(name) ?? "").trim();
    setBusy(true); setError(null); setResult(null);
    try {
      const username = text("username"); const stakeholder = text("stakeholder"); const zone = text("zone_id");
      const office_id = zone || text("office_id"); const reason = text("reason");
      if (username.length < 3 || !/^(fo|zo|do)\..+/.test(stakeholder) || reason.length < 10) throw new Error("Enter an officer username, an office role and reason of at least 10 characters.");
      if (zone ? !/^ZO-.+/.test(zone) : !offices.data?.data.some((office) => office.office_id === office_id)) throw new Error("Choose an office or enter a zonal office ID beginning ZO-.");
      const token = await stepUp.ask({ action: "post-staff", resourceId: username,
        summary: `Post ${username} as ${stakeholder} to ${office_id}. ${reason}` });
      if (!token) return;
      setResult((await command<Envelope<Posting>>("POST", "/api/v1/hrm/postings", { username, stakeholder, office_id, reason }, { stepUpToken: token })).data);
      form.reset(); await qc.invalidateQueries({ queryKey: ["hrm-me"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  async function clear(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (!hr || clearanceBusy) return;
    const form = e.currentTarget; const f = new FormData(form);
    const username = String(f.get("username") ?? "").trim(); const purpose = String(f.get("purpose") ?? ""); const note = String(f.get("note") ?? "").trim();
    setClearanceBusy(true); setClearanceError(null); setClearanceResult(null);
    try {
      const issued = await command<Envelope<Clearance>>("POST", "/api/v1/vigilance/clearances", { username, purpose, ...(note ? { note } : {}) });
      setClearanceResult(issued.data); form.reset(); await qc.invalidateQueries({ queryKey: ["vigilance-clearances"] });
    } catch (cause) { setClearanceError(cause); } finally { setClearanceBusy(false); }
  }
  return <section className="stack" aria-labelledby="hrm-heading">
    <PageHeader id="hrm-heading" eyebrow="Human resources" title="HRM" description="Review your posting and record staff postings for the demonstration." current="HRM" />
    <ProblemMessage error={error ?? session.error ?? me.error ?? offices.error} />
    {session.isLoading ? <p role="status">Loading role…</p> : null}
    {session.data && !hr ? <p className="pending-notice">This service is available to HR.</p> : null}
    {hr ? <>
      {me.isLoading ? <p role="status">Loading current posting…</p> : null}
      {me.data ? <p>{me.data.data.username} · {me.data.data.role} · {me.data.data.office.name ?? me.data.data.office.office_id}</p> : null}
      <section className="card stack" aria-labelledby="postings-heading"><h2 id="postings-heading">Staff postings</h2>
        <form className="stack" aria-label="Post staff" onSubmit={(e) => void post(e)}>
          <fieldset className="stack" disabled={busy || !!stepUp.request}><legend>New posting</legend>
            <label>Username<input name="username" required minLength={3} maxLength={80} /></label>
            <label>Stakeholder role<input name="stakeholder" required placeholder="fo.oic" maxLength={60} /></label>
            <label>Office<select name="office_id"><option value="">Choose office</option>{offices.data?.data.map((office) => <option key={office.office_id} value={office.office_id}>{office.name ?? office.office_id} · {office.office_id}</option>)}</select></label>
            <label>Zonal office ID (optional)<input name="zone_id" pattern="ZO-.+" maxLength={40} aria-describedby="posting-zone-help" /></label>
            <p className="muted" id="posting-zone-help">For a zonal posting, enter a ZO- ID here instead of choosing an office.</p>
            <label>Posting reason<textarea name="reason" required minLength={10} maxLength={1000} /></label>
            <div className="actions"><button type="submit" className="primary">Record posting</button></div>
          </fieldset>
        </form>
        {result ? <section role="status" className="card stack" aria-label="Posting result"><h3>Posting recorded for {result.username}</h3>
          <p>New posting: {result.stakeholder} · {result.office_id}</p><p>Previous posting: {result.previous.stakeholder} · {result.previous.office_id}</p><p>{result.note}</p>
        </section> : null}
      </section>
      <section className="card stack vigilance-panel" aria-labelledby="hr-clearance-heading"><h2 id="hr-clearance-heading">Vigilance clearance</h2>
        <form className="stack" aria-label="Issue vigilance clearance" onSubmit={(e) => void clear(e)}><fieldset className="stack" disabled={clearanceBusy}><legend>Check an officer</legend>
          <label>Officer user name<input name="username" required minLength={3} maxLength={80} /></label>
          <label>Purpose<select name="purpose" required defaultValue=""><option value="">Choose purpose</option>{["POSTING_SENSITIVE", "PROMOTION", "RETIREMENT", "DEPUTATION", "PASSPORT_NOC"].map((purpose) => <option key={purpose} value={purpose}>{statusLabel(purpose, t)}</option>)}</select></label>
          <label>Note (optional)<textarea name="note" maxLength={1000} /></label>
          <div className="actions"><button type="submit" className="primary">Request clearance</button></div>
        </fieldset></form>
        <ProblemMessage error={clearanceError} />
        {clearanceResult ? <p role="status"><span className="state-pill">{clearanceResult.cleared ? `Cleared until ${clearanceResult.valid_until}` : `Withheld — ${clearanceResult.reason}`}</span></p> : null}
        <ClearancesTable />
      </section>
      <SensitivePostsPanel />
    </> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </section>;
}
