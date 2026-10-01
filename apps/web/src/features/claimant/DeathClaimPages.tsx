import { statusLabel } from "../statusLabel";
import { useTranslation } from "react-i18next";
import { useState, type FormEvent } from "react";

import { api, command, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

type Json = Record<string, unknown>;
const text = (f: FormData, k: string) => String(f.get(k) ?? "").trim();

interface Share { beneficiary_id: string; name: string; relation: string; share_pct: number; source: string; allocated_paise: number;
  legacy_settled_paise: number; disbursed_paise: number; pending_paise: number }
interface TimelineEntry { at: string | null; state: string; by: string; note: string }
interface DeathClaim { claim_id: string; claim_type: string; form_type: string; amount_paise: number; state: string; summary: string;
  next_step: string; decision_reason: string | null; timeline: TimelineEntry[]; beneficiaries: Share[] }
interface CompositeClaim { composite_ref: string; claims: DeathClaim[]; next_step: string }

export function SharesTable({ rows }: { rows: Share[] }) {
  return <div className="table-scroll"><table>
    <thead><tr><th scope="col">Beneficiary</th><th scope="col">Relation</th><th scope="col">Share</th><th scope="col">Allocated</th>
      <th scope="col">Settled earlier</th><th scope="col">Paid</th><th scope="col">Pending</th></tr></thead>
    <tbody>{rows.map((b) => <tr key={b.beneficiary_id}><td>{b.name}<div className="muted small">{b.beneficiary_id}</div></td>
      <td>{b.relation.toLowerCase()}</td><td>{b.share_pct}%</td><td>{rupees(b.allocated_paise)}</td><td>{rupees(b.legacy_settled_paise)}</td>
      <td>{rupees(b.disbursed_paise)}</td><td>{rupees(b.pending_paise)}</td></tr>)}</tbody>
  </table></div>;
}

/** A nominee files the PF (Form 20) and EDLI (Form 5IF) claims on a member's death and follows them. */
export function ClaimantPage() {
  const { t } = useTranslation();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [claim, setClaim] = useState<DeathClaim | null>(null);
  const [composite, setComposite] = useState<CompositeClaim | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function run(work: () => Promise<string | null>) {
    setError(null); setNotice(null);
    try { const done = await work(); if (done) setNotice(done); } catch (cause) { setError(cause); }
  }

  const file = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const f = new FormData(e.currentTarget);
    const uan = text(f, "uan"), form = text(f, "form");
    void run(async () => {
      const token = await stepUp.ask({ action: "file-death-claim", resourceId: uan,
        summary: `File the ${form === "CCF_DEATH" ? "composite PF and EDLI" : form === "FORM_5IF" ? "EDLI (Form 5IF)" : "PF (Form 20)"} claim for the member with UAN ending ${uan.slice(-4)}.` });
      if (!token) return null;
      const r = await command<Envelope<DeathClaim | CompositeClaim>>("POST", "/api/v1/claimants/death-claims",
        { form_type: form, deceased_uan: uan, process_as: "E_NOMINATION" }, { stepUpToken: token });
      if ("claims" in r.data) { setComposite(r.data); setClaim(null); return `Composite claim ${r.data.composite_ref} filed.`; }
      setClaim(r.data); setComposite(null); return `Claim ${r.data.claim_id} filed.`;
    }); };
  const track = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const id = text(new FormData(e.currentTarget), "claim");
    void run(async () => { setClaim((await api<Envelope<DeathClaim>>(`/api/v1/claimants/death-claims/${id}`)).data); setComposite(null); return null; }); };
  const addBeneficiary = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const f = new FormData(e.currentTarget); const form = e.currentTarget;
    if (!claim) return;
    void run(async () => {
      const r = await command<Envelope<DeathClaim>>("POST", `/api/v1/claimants/death-claims/${claim.claim_id}/beneficiaries`,
        { name: text(f, "name"), relation: text(f, "relation") });
      setClaim(r.data); form.reset();
      return "Beneficiary added. The APFC sets the shares.";
    }); };

  return (
    <section className="stack" aria-labelledby="death-claim-heading">
      <PageHeader id="death-claim-heading" eyebrow="Claimant" title="Claims on a member's death" current="Death claims"
        description="A nominee files the Provident Fund (Form 20) and EDLI insurance (Form 5IF) claims. Payment is shared among the beneficiaries." />
      <ProblemMessage error={error} />
      {notice ? <p role="status" className="ok">{notice}</p> : null}

      <form className="card stack" aria-labelledby="file-heading" onSubmit={file}><h2 id="file-heading">File a claim</h2>
        <p className="muted small">The claim uses the member's latest nomination. Synthetic demo: the deceased member's UAN is 100000000901.</p>
        <div className="form-row">
          <label>Deceased member's UAN<input name="uan" required pattern="[0-9]{12}" inputMode="numeric" defaultValue="100000000901" /></label>
          <label>Claim<select name="form" defaultValue="FORM_20">
            <option value="FORM_20">Provident Fund — Form 20</option><option value="FORM_5IF">EDLI insurance — Form 5IF</option>
            <option value="CCF_DEATH">Composite claim (PF and EDLI)</option></select></label>
        </div>
        <div className="actions"><button type="submit" className="primary">File claim</button></div>
      </form>

      <form className="card search-input-row" aria-label="Track a claim" onSubmit={track}>
        <label>Claim ID<input name="claim" required placeholder="CLM-…" /></label><button type="submit">Track</button></form>

      {composite ? <section className="card stack" aria-labelledby="composite-heading"><h2 id="composite-heading">Composite reference {composite.composite_ref}</h2>
        <ul>{composite.claims.map((item) => <li key={item.claim_id}><strong>{item.claim_id}</strong> · {item.form_type === "FORM_20" ? "PF (Form 20)" : "EDLI (Form 5IF)"} · {statusLabel(item.state, t)}</li>)}</ul>
        <p>{composite.next_step}</p></section> : null}

      {claim ? <section className="card stack" aria-labelledby="claim-status-heading">
        <h2 id="claim-status-heading">{claim.claim_id} · Form {claim.form_type} <span className="state-pill">{statusLabel(claim.state, t)}</span></h2>
        <p>{claim.summary}</p>
        <p className="muted">{claim.next_step}{claim.decision_reason ? ` Reason: ${claim.decision_reason}` : ""}</p>
        <h3>Beneficiaries</h3>
        <SharesTable rows={claim.beneficiaries} />
        <form className="stack" aria-labelledby="add-heading" onSubmit={addBeneficiary}><h3 id="add-heading">Add a co-beneficiary or legal heir</h3>
          <div className="form-row"><label>Name<input name="name" required minLength={2} /></label>
            <label>Relation<select name="relation">{["SPOUSE", "SON", "DAUGHTER", "FATHER", "MOTHER", "LEGAL_HEIR", "GUARDIAN"].map((r) =>
              <option key={r} value={r}>{r.replace("_", " ").toLowerCase()}</option>)}</select></label></div>
          <div className="actions"><button type="submit">Add</button></div>
        </form>
        <h3>Timeline</h3>
        <ol className="claim-timeline">{claim.timeline.map((entry, i) => <li key={i} className={i === claim.timeline.length - 1 ? "current" : ""}><strong>{statusLabel(entry.state, t)}</strong> — {entry.by}. {entry.note}</li>)}</ol>
      </section> : null}
      <FamilyPensionSection />
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}

interface FamilyClaim { claim_id: string; state: string; kind: string; pension_from: string; ppo_id: string | null; next_step: string | null;
  family: { deceased_name: string; relation: string; died_on: string } | null; worksheet: { monthly_paise: number; working: string } | null;
  estimate?: { monthly_paise: number; working: string }; history: { state: string; role: string; note: string }[] }

/** Family pension: the widow / widower or a child of a member who died in service files Form 10D. */
export function FamilyPensionSection() {
  const { t } = useTranslation();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [filed, setFiled] = useState<FamilyClaim | null>(null);
  const [list, setList] = useState<FamilyClaim[] | null>(null);
  const load = async () => {
    try { setList((await api<Envelope<FamilyClaim[]>>("/api/v1/claimants/family-pension-applications")).data); } catch (cause) { setError(cause); }
  };
  const file = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const uan = text(new FormData(e.currentTarget), "uan");
    setError(null);
    void (async () => {
      try {
        const token = await stepUp.ask({ action: "file-family-pension", resourceId: uan, summary: `File Form 10D for a family pension on UAN ending ${uan.slice(-4)}.` });
        if (!token) return;
        setFiled((await command<Envelope<FamilyClaim>>("POST", "/api/v1/claimants/family-pension-applications",
          { form_type: "FORM_10D", deceased_uan: uan }, { stepUpToken: token })).data);
        await load();
      } catch (cause) { setError(cause); }
    })(); };
  return (
    <section className="card stack" aria-labelledby="family-pension-heading"><h2 id="family-pension-heading">Family pension (Form 10D)</h2>
      <p className="muted small">For the spouse or a child of a member who died in service. The regional office then works it out desk by desk,
        as for a member's pension, and issues the PPO in your name.</p>
      <ProblemMessage error={error} />
      <form className="search-input-row" onSubmit={file}><label>Deceased member's UAN<input name="uan" required pattern="[0-9]{12}"
        inputMode="numeric" defaultValue="100000000901" /></label><button type="submit" className="primary">File Form 10D</button></form>
      {filed?.estimate ? <p role="status" className="ok">Filed {filed.claim_id}: about {rupees(filed.estimate.monthly_paise)} a month from {filed.pension_from}
        ({filed.estimate.working}; illustrative rules).</p> : null}
      <div className="actions"><button type="button" onClick={() => void load()}>Show my applications</button></div>
      {list ? list.length ? <ul className="plain-list">{list.map((c) => <li key={c.claim_id}><strong>{c.claim_id}</strong> ·{" "}
        <span className="state-pill">{statusLabel(c.state, t)}</span> — {c.family?.relation.toLowerCase()} of {c.family?.deceased_name}
        {c.worksheet ? `, ${rupees(c.worksheet.monthly_paise)} a month` : ""}{c.ppo_id ? `, PPO ${c.ppo_id}` : ""}.
        {c.next_step ? <span className="muted small"> Next: {c.next_step}.</span> : null}</li>)}</ul> : <p className="muted">No applications.</p> : null}
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}

const PRO_FORMS: [string, string][] = [
  ["FORM_19", "Form 19 — final settlement"], ["FORM_31", "Form 31 — advance"], ["FORM_20", "Form 20 — PF on death"],
  ["FORM_5IF", "Form 5IF — EDLI"], ["FORM_10D", "Form 10D — pension"], ["FORM_13", "Form 13 — transfer"],
  ["SCHEME_CERTIFICATE_SURRENDER", "Scheme certificate surrender"],
  ["PHYSICAL_LC_UPDATION", "Pensioner: physical life certificate"], ["DEATH_UPDATION", "Pensioner: death"],
  ["SPOUSE_REMARRIAGE_UPDATION", "Pensioner: spouse remarriage"], ["PPO_AMENDMENT_BENEFICIARY", "PPO amendment: beneficiary"],
  ["PPO_AMENDMENT_SERVICE", "PPO amendment: service"], ["PPO_AMENDMENT_POHW", "PPO amendment: pension on higher wages"],
];

/** PRO counter: inward a paper claim or pensioner updation, then match the filer with the member's record. */
export function ProCounterPage() {
  const { t } = useTranslation();
  const [error, setError] = useState<unknown>(null);
  const [intake, setIntake] = useState<Json | null>(null);
  const [identity, setIdentity] = useState<Json | null>(null);

  async function run(work: () => Promise<void>) {
    setError(null);
    try { await work(); } catch (cause) { setError(cause); }
  }
  const inward = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const f = new FormData(e.currentTarget);
    void run(async () => {
      setIdentity(null);
      setIntake((await command<Envelope<Json>>("POST", "/api/v1/office/physical-claims", {
        form_type: text(f, "form"), uan: text(f, "uan"), ppo_id: text(f, "ppo") || null, filed_by: text(f, "filed_by"),
        claim_mode: text(f, "mode"), details: { remarks: text(f, "remarks") } })).data);
    }); };
  const validate = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const f = new FormData(e.currentTarget);
    if (!intake) return;
    void run(async () => {
      setIdentity((await command<Envelope<Json>>("POST", `/api/v1/office/physical-claims/${String(intake.intake_id)}/identity-validations`, {
        uan: String(intake.uan), name: text(f, "name"), date_of_birth: text(f, "dob"), evidence: text(f, "evidence") })).data);
    }); };

  const checks = (identity?.checks ?? {}) as Record<string, boolean>;
  return (
    <section className="stack" aria-labelledby="pro-heading">
      <PageHeader id="pro-heading" eyebrow="Regional office" title="PRO counter" current="PRO counter"
        description="Inward paper claims and pensioner updations. Pension updations go straight to the pension office's tracker." />
      <ProblemMessage error={error} />
      <form className="card stack" aria-labelledby="inward-heading" onSubmit={inward}><h2 id="inward-heading">Inward a paper form</h2>
        <div className="form-row">
          <label>Form<select name="form">{PRO_FORMS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
          <label>UAN<input name="uan" required pattern="[0-9]{12}" inputMode="numeric" /></label>
          <label>PPO number (pension updations)<input name="ppo" placeholder="PPO-DEMO-0001" /></label>
        </div>
        <div className="form-row">
          <label>Filed by<select name="filed_by"><option value="MEMBER">Member</option><option value="BENEFICIARY">Beneficiary / nominee</option>
            <option value="PENSIONER">Pensioner</option></select></label>
          <label>Received<select name="mode"><option value="IN_PERSON">In person</option><option value="BY_POST">By post</option></select></label>
          <label>Remarks<input name="remarks" maxLength={300} /></label>
        </div>
        <div className="actions"><button type="submit" className="primary">Inward</button></div>
      </form>
      {intake ? <section className="card stack" aria-labelledby="intake-heading">
        <h2 id="intake-heading">{String(intake.intake_id)} <span className="state-pill">{statusLabel(String(intake.state), t)}</span></h2>
        <p>{String(intake.next_step)}</p>
        {intake.state === "INWARDED" ? <form className="stack" aria-labelledby="identity-heading" onSubmit={validate}>
          <h3 id="identity-heading">Validate the filer's identity</h3>
          <div className="form-row"><label>Name on the form<input name="name" required minLength={2} /></label>
            <label>Date of birth<input name="dob" type="date" required /></label>
            <label>Evidence<select name="evidence"><option value="AADHAAR_OTP">Aadhaar OTP (mock)</option>
              <option value="AADHAAR_BIOMETRIC">Aadhaar biometric (mock)</option><option value="DOCUMENTS_SEEN">Documents seen</option></select></label></div>
          <div className="actions"><button type="submit">Validate</button></div>
        </form> : null}
        {identity ? <div role="status" className={identity.result === "MATCHED" ? "ok" : "pending-notice"}>
          <strong>{statusLabel(String(identity.result), t)}</strong> — {Object.entries(checks).map(([k, v]) => `${k.replaceAll("_", " ")}: ${v ? "yes" : "no"}`).join(" · ")}.
          <p>{String(identity.next_step)}</p></div> : null}
      </section> : null}
    </section>
  );
}

/** APFC: the beneficiaries' shares on a death claim; payment waits until they add up to 100 %. */
export function SharesSection() {
  const { t } = useTranslation();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [summary, setSummary] = useState<{ claim_id: string; state: string; shares_total_pct: number; payable: boolean; beneficiaries: Share[] } | null>(null);

  async function run(work: () => Promise<void>) {
    setError(null);
    try { await work(); } catch (cause) { setError(cause); }
  }
  const load = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const id = text(new FormData(e.currentTarget), "claim");
    void run(async () => { setSummary((await api<Envelope<NonNullable<typeof summary>>>(`/api/v1/office/death-claims/${id}/shares-summary`)).data); }); };
  const amend = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const f = new FormData(e.currentTarget);
    if (!summary) return;
    const bid = text(f, "beneficiary");
    void run(async () => {
      const pct = Number(text(f, "pct"));
      const token = await stepUp.ask({ action: "amend-share", resourceId: bid, summary: `Set the share of ${bid} to ${pct}%.` });
      if (!token) return;
      setSummary((await command<Envelope<NonNullable<typeof summary>>>("PUT", `/api/v1/office/death-claims/${summary.claim_id}/beneficiaries/${bid}/shares`, {
        share_bp: Math.round(pct * 100), legacy_settled_paise: Math.round(Number(text(f, "legacy") || "0") * 100),
        reason: text(f, "reason"), note: text(f, "note") }, { stepUpToken: token })).data);
    }); };

  return (
    <section className="card stack" aria-labelledby="shares-heading"><h2 id="shares-heading">Death claims: beneficiaries' shares</h2>
      <ProblemMessage error={error} />
      <form className="search-input-row" onSubmit={load}><label>Claim ID<input name="claim" required placeholder="CLM-…" /></label>
        <button type="submit">Show shares</button></form>
      {summary ? <>
        <p>{summary.claim_id} · {statusLabel(summary.state, t)} · shares total <strong>{summary.shares_total_pct}%</strong>
          {summary.payable ? " — payable." : " — payment is held until the shares add up to 100%."}</p>
        <SharesTable rows={summary.beneficiaries} />
        <form className="stack" aria-labelledby="amend-heading" onSubmit={amend}><h3 id="amend-heading">Amend a share</h3>
          <div className="form-row">
            <label>Beneficiary<select name="beneficiary">{summary.beneficiaries.map((b) => <option key={b.beneficiary_id} value={b.beneficiary_id}>{b.name}</option>)}</select></label>
            <label>New share (%)<input name="pct" required type="number" min={0} max={100} step="0.01" /></label>
            <label>Settled in legacy system (₹)<input name="legacy" type="number" min={0} defaultValue={0} /></label>
          </div>
          <div className="form-row">
            <label>Reason<select name="reason"><option value="COURT_ORDER">Court order / succession certificate</option>
              <option value="NOMINEE_DECEASED">Nominee deceased</option><option value="LEGACY_SETTLEMENT_OFFSET">Share already settled (legacy)</option>
              <option value="GUARDIAN_APPOINTMENT">Guardian appointed</option><option value="ADDED_HEIR">Legal heir added</option></select></label>
            <label>Note (recorded)<input name="note" required minLength={5} /></label>
          </div>
          <div className="actions"><button type="submit" className="primary">Amend share</button></div>
        </form>
      </> : null}
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}
