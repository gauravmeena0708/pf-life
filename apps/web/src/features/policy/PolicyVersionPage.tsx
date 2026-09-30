import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { api, command, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";
import { BenefitPreview, InterestSection, PensionSection, TdsSection } from "./BenefitRules";
import { Money, Num, toPaise, toRupees } from "./fields";
import type { Band, ClaimType, RuleDocument, RuleSet } from "./types";

const ROLE: Record<string, string> = { "fo.da_accounts": "DA", "fo.ss": "SS", "fo.ao": "AO", "fo.apfc": "APFC", "fo.oic": "OIC" };
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;
const shown = (v: unknown, path: string) => v === null || v === undefined ? "—"
  : typeof v === "number" && path.endsWith("_paise") ? rupees(v) : typeof v === "object" ? JSON.stringify(v) : String(v);
/** Approval chain by amount: DA, then SS or AO, then optionally APFC and/or OIC. */
function BandsEditor({ bands, onChange, disabled }: { bands: Band[]; onChange: (b: Band[]) => void; disabled: boolean }) {
  const set = (i: number, band: Band) => onChange(bands.map((b, j) => j === i ? band : b));
  return (
    <div className="stack">
      <div className="table-scroll"><table>
        <thead><tr><th scope="col">Claims up to</th><th scope="col">First approver</th><th scope="col">Then APFC</th><th scope="col">Then OIC</th><th scope="col">Chain</th><th /></tr></thead>
        <tbody>{bands.map((b, i) => {
          const last = i === bands.length - 1;
          const later = b.chain.slice(2);
          const withLater = (apfc: boolean, oic: boolean) => ["fo.da_accounts", b.chain[1], ...(apfc ? ["fo.apfc"] : []), ...(oic ? ["fo.oic"] : [])];
          return (
            <tr key={i}>
              <td>{last ? "no upper limit" : <input aria-label={`Band ${i + 1} upper limit in rupees`} inputMode="numeric" disabled={disabled}
                value={toRupees(b.upto_paise)} onChange={(e) => set(i, { ...b, upto_paise: toPaise(e.target.value.replace(/[^0-9.]/g, "")) })} />}</td>
              <td><select aria-label={`Band ${i + 1} first approver`} value={b.chain[1]} disabled={disabled}
                onChange={(e) => set(i, { ...b, chain: ["fo.da_accounts", e.target.value, ...later] })}>
                <option value="fo.ss">Section supervisor</option><option value="fo.ao">Accounts officer</option></select></td>
              <td><input type="checkbox" aria-label={`Band ${i + 1} adds APFC`} checked={later.includes("fo.apfc")} disabled={disabled}
                onChange={(e) => set(i, { ...b, chain: withLater(e.target.checked, later.includes("fo.oic")) })} /></td>
              <td><input type="checkbox" aria-label={`Band ${i + 1} adds OIC`} checked={later.includes("fo.oic")} disabled={disabled}
                onChange={(e) => set(i, { ...b, chain: withLater(later.includes("fo.apfc"), e.target.checked) })} /></td>
              <td><code>{b.chain.map((r) => ROLE[r] ?? r).join(" → ")}</code></td>
              <td>{!disabled && bands.length > 1 && !last ? <button type="button" onClick={() => onChange(bands.filter((_, j) => j !== i))}>Remove</button> : null}</td>
            </tr>
          );
        })}</tbody>
      </table></div>
      {!disabled ? <div className="actions"><button type="button" onClick={() => {
        const copy = clone(bands);
        const previous = copy.length > 1 ? copy[copy.length - 2].upto_paise ?? 0 : 0;
        copy.splice(copy.length - 1, 0, { upto_paise: previous + 10000000, chain: ["fo.da_accounts", "fo.ss"] });
        onChange(copy);
      }}>Add a band</button></div> : null}
    </div>
  );
}

function ClaimTypeEditor({ code, t, onChange, disabled, defaults }: { code: string; t: ClaimType; onChange: (t: ClaimType) => void; disabled: boolean; defaults: Band[] }) {
  const set = (patch: Partial<ClaimType>) => onChange({ ...t, ...patch });
  const own = !!t.approval_bands;
  return (
    <details className="filter-panel">
      <summary><strong>{code}</strong> · Form {t.form_type} · {t.label}{t.retired ? " · retired" : ""} · {t.auto_settle_up_to_paise === null ? "always officer-reviewed" : `automatic up to ${rupees(t.auto_settle_up_to_paise ?? 0)}`}</summary>
      <div className="stack">
        <div className="form-row">
          <label>Name shown to members<input value={t.label} disabled={disabled} onChange={(e) => set({ label: e.target.value })} /></label>
          <label>Form<input value={t.form_type} disabled={disabled} onChange={(e) => set({ form_type: e.target.value })} /></label>
        </div>
        <label>Rule in plain words (shown to members)<textarea value={t.plain_rule} disabled={disabled} onChange={(e) => set({ plain_rule: e.target.value })} /></label>
        <div className="form-row">
          <label>Limit is based on<select value={t.max_from} disabled={disabled} onChange={(e) => set({ max_from: e.target.value as ClaimType["max_from"] })}>
            <option value="employee_share">Member's own (employee) share</option><option value="total_balance">Total balance</option>
            <option value="eps_table_d">Pension withdrawal (Table D)</option></select></label>
          <Num label="Share of that base" suffix="% — 100 = all of it" value={(t.max_pct_bp ?? 10000) / 100} disabled={disabled}
            onChange={(n) => set({ max_pct_bp: n === null ? undefined : Math.round(n * 100) })} />
          <Money label="Cap per claim (₹, blank = none)" value={t.cap_paise} disabled={disabled} onChange={(p) => set({ cap_paise: p ?? undefined })} />
        </div>
        <div className="form-row">
          <Num label="Minimum service" suffix="months" value={t.min_service_months} disabled={disabled} onChange={(n) => set({ min_service_months: n ?? undefined })} />
          <Num label="At most once every" suffix="months" value={t.once_every_months} disabled={disabled} onChange={(n) => set({ once_every_months: n ?? undefined })} />
          <Num label="Only after leaving employment for" suffix="months, blank = not required" value={t.requires_exit_months} disabled={disabled}
            onChange={(n) => set({ requires_exit_months: n ?? undefined, ...(n !== null ? { requires_active_employment: false } : {}) })} />
        </div>
        <label className="check-row"><input type="checkbox" checked={!!t.requires_active_employment} disabled={disabled}
          onChange={(e) => set({ requires_active_employment: e.target.checked })} />Only while still employed</label>
        <div className="form-row">
          <label className="check-row"><input type="checkbox" checked={t.auto_settle_up_to_paise === null} disabled={disabled}
            onChange={(e) => set({ auto_settle_up_to_paise: e.target.checked ? null : 10000000 })} />Always decided by officers (never automatic)</label>
          {t.auto_settle_up_to_paise !== null ? <Money label="Settle automatically up to (₹)" value={t.auto_settle_up_to_paise} disabled={disabled}
            onChange={(p) => set({ auto_settle_up_to_paise: p ?? 0 })} /> : null}
        </div>
        <label className="check-row"><input type="checkbox" checked={own} disabled={disabled}
          onChange={(e) => set({ approval_bands: e.target.checked ? clone(defaults) : undefined })} />Use its own approval chain instead of the default matrix</label>
        {own ? <BandsEditor bands={t.approval_bands!} disabled={disabled} onChange={(b) => set({ approval_bands: b })} /> : null}
        <label className="check-row"><input type="checkbox" checked={!!t.retired} disabled={disabled}
          onChange={(e) => set({ retired: e.target.checked })} />Retired — no new claims (claims in progress continue)</label>
      </div>
    </details>
  );
}

/** One rule-set version: edit (drafter), see checks, what changed and worked examples, approve (CPFC). */
export function PolicyVersionPage() {
  const { versionId } = useParams();
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [doc, setDoc] = useState<RuleDocument | null>(null);
  const [newCode, setNewCode] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const detail = useQuery({ queryKey: ["rule-set", versionId], enabled: !!versionId, retry: false,
    queryFn: () => api<Envelope<RuleSet>>(`/api/v1/ho/config/rule-sets/${versionId}`) });
  const r = detail.data?.data;
  useEffect(() => { if (r) setDoc(clone(r.document)); }, [r]);
  const role = session.data?.stakeholder;
  const editable = r?.status === "DRAFT" && role === "ho.acc_hq";

  async function run(work: () => Promise<unknown>, ok: string) {
    setError(null); setNotice(null);
    try { await work(); setNotice(ok); await qc.invalidateQueries({ queryKey: ["rule-set", versionId] }); await qc.invalidateQueries({ queryKey: ["rule-sets"] }); }
    catch (cause) { setError(cause); }
  }
  const save = () => run(() => command("PUT", `/api/v1/ho/config/rule-sets/${versionId}`, { document: doc }, { ifMatch: r!.version }), "Saved. The checks and examples below are up to date.");
  const submit = () => run(() => command("POST", `/api/v1/ho/config/rule-sets/${versionId}/submissions`), "Submitted to the CPFC for approval.");
  async function decide(decision: "APPROVE" | "RETURN", note: string) {
    const token = await stepUp.ask({ action: "publish-policy", resourceId: versionId!, resourceVersion: r!.version,
      summary: decision === "APPROVE" ? `Publish rule set ${r!.rule_version}, effective from ${r!.effective_from}. Every service applies it from that date.`
        : `Return rule set ${r!.rule_version} to the drafter.` });
    if (token) await run(() => command("POST", `/api/v1/ho/config/rule-sets/${versionId}/decisions`, { decision, note }, { stepUpToken: token }),
      decision === "APPROVE" ? "Published." : "Returned to the drafter.");
  }
  const setContribution = (key: string, value: number | null) => setDoc((d) => d && { ...d, contribution: { ...d.contribution, [key]: value ?? 0 } });
  const setType = (code: string, t: ClaimType) => setDoc((d) => d && { ...d, claims: { ...d.claims, types: { ...d.claims.types, [code]: t } } });

  return (
    <section className="stack" aria-labelledby="version-heading">
      <PageHeader id="version-heading" eyebrow="Policy administration" title={r ? r.rule_version : "Rule set"}
        description={r ? `Effective from ${r.effective_from} · ${r.change_note}` : ""} current={r?.rule_version ?? ""}
        parent={{ label: "Rules and limits", to: "/policy" }}>
        {r ? <span className="state-pill">{r.status.replaceAll("_", " ").toLowerCase()}</span> : null}
      </PageHeader>
      <ProblemMessage error={detail.error} />
      <ProblemMessage error={error} />
      {notice ? <p role="status" className="ok">{notice}</p> : null}
      {r && doc ? (
        <>
          {r.checks.length ? <section className="problem" aria-label="Checks"><strong>Must be fixed before submitting:</strong><ul>{r.checks.map((c) => <li key={c}>{c}</li>)}</ul></section>
            : <p className="ok">All checks pass.</p>}
          {r.decision_note ? <p className="demo-tip"><strong>CPFC's note:</strong> {r.decision_note}</p> : null}

          <section className="card stack" aria-labelledby="contrib-heading"><h2 id="contrib-heading">Wages and contribution rates</h2>
            <div className="form-row">
              <Money label="EPS wage ceiling (₹ a month)" value={doc.contribution.eps_wage_ceiling_paise} disabled={!editable} onChange={(p) => setContribution("eps_wage_ceiling_paise", p)} />
              <Money label="EDLI wage ceiling (₹ a month)" value={doc.contribution.edli_wage_ceiling_paise} disabled={!editable} onChange={(p) => setContribution("edli_wage_ceiling_paise", p)} />
            </div>
            <div className="form-row">
              <Num label="Employee EPF rate" suffix="basis points, 1200 = 12%" value={doc.contribution.epf_employee_rate_bp} disabled={!editable} onChange={(n) => setContribution("epf_employee_rate_bp", n)} />
              <Num label="EPS rate" suffix="basis points, 833 = 8.33%" value={doc.contribution.eps_rate_bp} disabled={!editable} onChange={(n) => setContribution("eps_rate_bp", n)} />
              <Num label="EDLI rate" suffix="basis points" value={doc.contribution.edli_rate_bp} disabled={!editable} onChange={(n) => setContribution("edli_rate_bp", n)} />
            </div>
            <div className="form-row">
              <Num label="Admin charges" suffix="basis points" value={doc.contribution.admin_charges_rate_bp} disabled={!editable} onChange={(n) => setContribution("admin_charges_rate_bp", n)} />
              <Money label="Minimum admin charges (₹)" value={doc.contribution.admin_charges_min_paise} disabled={!editable} onChange={(p) => setContribution("admin_charges_min_paise", p)} />
              <Num label="No EPS from age" suffix="years" value={doc.contribution.eps_age_limit_years} disabled={!editable} onChange={(n) => setContribution("eps_age_limit_years", n)} />
            </div>
          </section>

          <section className="card stack" aria-labelledby="types-heading"><h2 id="types-heading">Claim types</h2>
            <p className="muted small">What members can claim, the conditions, the limit, whether it can be settled automatically, and who approves it.</p>
            {Object.entries(doc.claims.types).map(([code, t]) => (
              <ClaimTypeEditor key={code} code={code} t={t} disabled={!editable} defaults={doc.claims.approval_bands} onChange={(nt) => setType(code, nt)} />
            ))}
            {editable ? (
              <div className="search-input-row">
                <input aria-label="New claim type code" placeholder="NEW_TYPE_CODE" value={newCode} onChange={(e) => setNewCode(e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, ""))} />
                <button type="button" disabled={!newCode || !!doc.claims.types[newCode]} onClick={() => {
                  setType(newCode, { form_type: "31", label: "New claim type", plain_rule: "Describe the rule for members.", max_from: "employee_share",
                    requires_active_employment: true, auto_settle_up_to_paise: null });
                  setNewCode("");
                }}>Add claim type</button>
              </div>
            ) : null}
          </section>

          <section className="card stack" aria-labelledby="matrix-heading"><h2 id="matrix-heading">Default approval matrix</h2>
            <p className="muted small">Who decides a claim by amount (types with their own chain override this). The dealing assistant always recommends first.</p>
            <BandsEditor bands={doc.claims.approval_bands} disabled={!editable}
              onChange={(b) => setDoc((d) => d && { ...d, claims: { ...d.claims, approval_bands: b } })} />
            <div className="form-row">
              <Money label="Default automatic settlement limit (₹)" value={doc.claims.auto_settlement_limit_paise} disabled={!editable}
                onChange={(p) => setDoc((d) => d && { ...d, claims: { ...d.claims, auto_settlement_limit_paise: p ?? 0 } })} />
              <Num label="Claim settlement service level" suffix="days" value={doc.claims.settlement_sla_days} disabled={!editable}
                onChange={(n) => setDoc((d) => d && { ...d, claims: { ...d.claims, settlement_sla_days: n ?? 0 } })} />
            </div>
          </section>

          <InterestSection value={doc.interest} disabled={!editable} onChange={(interest) => setDoc((d) => d && { ...d, interest })} />
          <TdsSection value={doc.tds} claimTypes={Object.keys(doc.claims.types)} disabled={!editable} onChange={(tds) => setDoc((d) => d && { ...d, tds })} />
          <PensionSection value={doc.pension} effectiveFrom={r.effective_from} disabled={!editable} onChange={(pension) => setDoc((d) => d && { ...d, pension })} />

          <section className="card stack" aria-labelledby="griev-heading"><h2 id="griev-heading">Grievances</h2>
            <label>Categories (comma separated; OTHER is required)<input value={doc.grievances.categories.join(", ")} disabled={!editable}
              onChange={(e) => setDoc((d) => d && { ...d, grievances: { ...d.grievances, categories: e.target.value.split(",").map((c) => c.trim().toUpperCase().replace(/\s+/g, "_")).filter(Boolean) } })} /></label>
            <div className="form-row">
              {(["RO", "ZO", "HO"] as const).map((tier) => <Num key={tier} label={`Service level at ${tier}`} suffix="days" value={doc.grievances.sla_days[tier]} disabled={!editable}
                onChange={(n) => setDoc((d) => d && { ...d, grievances: { ...d.grievances, sla_days: { ...d.grievances.sla_days, [tier]: n ?? 0 } } })} />)}
              <Num label="Reopen window" suffix="days" value={doc.grievances.reopen_window_days} disabled={!editable}
                onChange={(n) => setDoc((d) => d && { ...d, grievances: { ...d.grievances, reopen_window_days: n ?? 0 } })} />
            </div>
          </section>

          {editable ? <div className="actions">
            <button type="button" className="primary" onClick={() => void save()}>Save and check</button>
            <button type="button" disabled={r.checks.length > 0} onClick={() => void submit()}>Submit for approval</button>
          </div> : null}

          <section className="card stack" aria-labelledby="changes-heading"><h2 id="changes-heading">What changes (saved version)</h2>
            {r.changes.length === 0 ? <p className="muted">No changes from the version it was copied from.</p> : (
              <div className="table-scroll"><table><thead><tr><th scope="col">Setting</th><th scope="col">Before</th><th scope="col">After</th></tr></thead>
                <tbody>{r.changes.filter((c) => !["rule_version", "effective_from"].includes(c.path)).map((c) => (
                  <tr key={c.path}><td><code>{c.path}</code></td><td>{shown(c.before, c.path)}</td><td><strong>{shown(c.after, c.path)}</strong></td></tr>
                ))}</tbody></table></div>)}
          </section>

          {r.preview ? <section className="card stack" aria-labelledby="preview-heading"><h2 id="preview-heading">Effect, with worked examples</h2>
            <p className="muted small">{r.preview.note}</p>
            {r.preview.contribution.length ? <div className="table-scroll"><table><thead><tr><th scope="col">Monthly wages</th><th scope="col">Employer EPS</th><th scope="col">Employer EPF</th><th scope="col">EDLI</th><th scope="col">Challan total</th></tr></thead>
              <tbody>{r.preview.contribution.map((c) => (
                <tr key={c.monthly_wages}><td>{c.monthly_wages}</td>
                  {(["employer_eps", "employer_epf", "edli", "total_challan"] as const).map((k) => <td key={k}>{c.before[k]} → <strong>{c.after[k]}</strong></td>)}</tr>
              ))}</tbody></table></div> : <p className="muted">Contributions are unchanged.</p>}
            {r.preview.claims.length ? <div className="table-scroll"><table><thead><tr><th scope="col">Claim type</th><th scope="col">Amount</th><th scope="col">Decided by — before</th><th scope="col">After</th></tr></thead>
              <tbody>{r.preview.claims.map((c) => <tr key={`${c.claim_type}-${c.amount}`}><td>{c.claim_type}</td><td>{c.amount}</td><td>{c.before}</td><td><strong>{c.after}</strong></td></tr>)}</tbody>
            </table></div> : <p className="muted">Who decides claims is unchanged.</p>}
            <BenefitPreview preview={r.preview} />
          </section> : null}

          {r.status === "SUBMITTED" && role === "ho.cpfc" ? (
            <form className="card stack" onSubmit={(e) => { e.preventDefault(); const f = new FormData(e.currentTarget);
              void decide(String(f.get("decision")) as "APPROVE" | "RETURN", String(f.get("note")).trim()); }}>
              <h2>Decision</h2>
              <fieldset className="case-options"><legend>Decision</legend>
                <label className="check-row"><input type="radio" name="decision" value="APPROVE" required />Approve and publish from {r.effective_from}</label>
                <label className="check-row"><input type="radio" name="decision" value="RETURN" />Return to the drafter</label>
              </fieldset>
              <label>Note (kept with the decision)<textarea name="note" required minLength={10} maxLength={2000} /></label>
              <div className="actions"><button type="submit" className="primary">Record decision</button></div>
            </form>
          ) : null}
        </>
      ) : null}
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}
