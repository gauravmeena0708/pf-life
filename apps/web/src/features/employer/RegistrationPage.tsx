import { statusLabel } from "../statusLabel";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

interface ExportRow { uan: string; member_id: string; name: string; date_of_birth: string; gender: string; date_of_joining: string; aadhaar: string; pan: string; bank: string; form11: string; missing_details: string[] }
interface KycItem { request_id: string; uan: string; name: string; kyc_type: string; masked_value: string; source: string; verification: { verifier: string } }
interface Ledger { uan: string; member_id: string; name: string; months: { wage_month: string; trrn: string; employee_paise: number; employer_paise: number }[] }

const csv = (rows: ExportRow[]) => ["UAN,Member ID,Name,Date of birth,Gender,Date of joining,Aadhaar,PAN,Bank,Form 11,Missing details",
  ...rows.map((r) => [r.uan, r.member_id, r.name, r.date_of_birth, r.gender, r.date_of_joining, r.aadhaar, r.pan, r.bank, r.form11, r.missing_details.join(" ")]
    .map((v) => `"${String(v).replaceAll('"', '""')}"`).join(","))].join("\n");

/** Member › Register-Individual / Register-Bulk / Missing details / KYC BULK, Dashboards › Active Members,
 * and (signatory) Approve KYC pending for Digital Signature / seeded by member. */
export function RegistrationPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [result, setResult] = useState<unknown>(null);
  const [ledger, setLedger] = useState<Ledger | null>(null);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const signatory = session.data?.stakeholder === "employer.signatory";
  const exported = useQuery({ queryKey: ["active-export"], retry: false, queryFn: () => api<Envelope<{ members: ExportRow[] }>>("/api/v1/employers/me/members/active-export") });
  const kyc = useQuery({ queryKey: ["kyc-approvals"], enabled: signatory, retry: false, queryFn: () => api<Envelope<KycItem[]>>("/api/v1/employers/me/kyc-approvals") });
  const rows = exported.data?.data.members ?? [];

  async function run(work: () => Promise<string | null>) {
    setError(null); setNotice(null);
    try {
      const done = await work();
      if (done) { setNotice(done); await qc.invalidateQueries({ queryKey: ["active-export"] }); await qc.invalidateQueries({ queryKey: ["kyc-approvals"] }); }
    } catch (cause) { setError(cause); }
  }
  const text = (f: FormData, k: string) => String(f.get(k) ?? "").trim();

  const register = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    void run(async () => {
      const r = await command<Envelope<{ uan: string; account_link_id: string; new_uan: boolean }>>("POST", "/api/v1/employers/me/members", {
        name: text(f, "name"), date_of_birth: text(f, "dob"), gender: text(f, "gender"), aadhaar: text(f, "aadhaar"), mobile: text(f, "mobile"),
        date_of_joining: text(f, "doj"), existing_uan: text(f, "existing_uan") || null });
      form.reset();
      return `${r.data.new_uan ? "New UAN" : "New member ID under UAN"} ${r.data.uan} · member ID ${r.data.account_link_id}. File the Form 11 declaration next.`;
    }); };

  const form11 = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const f = new FormData(e.currentTarget);
    void run(async () => {
      await command("POST", `/api/v1/employers/me/members/${text(f, "uan")}/declarations`, {
        previous_pf_member: f.get("prev_pf") === "on", previous_eps_member: f.get("prev_eps") === "on", previous_uan: text(f, "previous_uan") || null,
        international_worker: f.get("iw") === "on", country_of_origin: text(f, "country") || null, declared_on: text(f, "declared_on") });
      return `Form 11 recorded for UAN ${text(f, "uan")}.`;
    }); };

  const bulk = (path: string) => (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const f = new FormData(e.currentTarget);
    void run(async () => { const r = await command<Envelope<unknown>>("POST", path, { content: text(f, "content") }); setResult(r.data); return "File processed; see the result below."; }); };

  const missing = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const f = new FormData(e.currentTarget); const uan = text(f, "uan");
    void run(async () => {
      const token = await stepUp.ask({ action: "update-member-profile", resourceId: uan, summary: `Fill in missing details for UAN ${uan}.` });
      if (!token) return null;
      const body = Object.fromEntries(["father_name", "mother_name", "marital_status", "nationality"].map((k) => [k, text(f, k) || null]));
      await command("PATCH", `/api/v1/employers/me/members/${uan}/profile`, body, { stepUpToken: token });
      return `Details filled for UAN ${uan}.`;
    }); };

  const decideKyc = (item: KycItem, decision: "APPROVE" | "REJECT") => void run(async () => {
    const token = await stepUp.ask({ action: "approve-kyc", resourceId: item.request_id,
      summary: `${decision === "APPROVE" ? "Approve" : "Reject"} the ${item.kyc_type} KYC ${item.masked_value} of ${item.name} (UAN ${item.uan}) with your DSC / e-sign.` });
    if (!token) return null;
    await command("POST", `/api/v1/employers/me/kyc-approvals/${item.request_id}/decisions`,
      { decision, note: decision === "APPROVE" ? "Documents checked by the employer" : "Details do not match our records" }, { stepUpToken: token });
    return `${item.request_id} ${decision === "APPROVE" ? "approved" : "rejected"}.`;
  });

  const showLedger = (uan: string) => void run(async () => { setLedger((await api<Envelope<Ledger>>(`/api/v1/employers/me/members/${uan}/contribution-ledger`)).data); return null; });

  const download = () => {
    const url = URL.createObjectURL(new Blob([csv(rows)], { type: "text/csv" }));
    const a = document.createElement("a"); a.href = url; a.download = "active-members.csv"; a.click(); URL.revokeObjectURL(url);
  };

  return (
    <section className="stack" aria-labelledby="registration-heading">
      <PageHeader id="registration-heading" eyebrow="Employer services · members" title="Member registration and KYC" current="Registration"
        description="Register joinees (Aadhaar checked by a mock UIDAI), file Form 11, fill missing details, upload KYC in bulk; the authorised signatory approves KYC." />
      <ProblemMessage error={error} />
      {notice ? <p role="status" className="ok">{notice}</p> : null}

      {signatory ? (
        <section className="card stack" aria-labelledby="kyc-approvals-heading"><h2 id="kyc-approvals-heading">KYC awaiting your approval</h2>
          <ProblemMessage error={kyc.error} />
          {kyc.data?.data.length ? <div className="table-scroll"><table>
            <thead><tr><th scope="col">Member</th><th scope="col">KYC</th><th scope="col">Source</th><th scope="col">Check</th><th scope="col">Decision</th></tr></thead>
            <tbody>{kyc.data.data.map((k) => <tr key={k.request_id}><td>{k.name}<br /><span className="muted small">UAN {k.uan}</span></td>
              <td>{k.kyc_type} <code>{k.masked_value}</code></td><td>{k.source === "MEMBER" ? "Seeded by member" : "Employer bulk upload (pending digital signature)"}</td>
              <td>{k.verification.verifier}: verified</td>
              <td><div className="actions"><button type="button" className="primary" onClick={() => decideKyc(k, "APPROVE")}>Approve</button>
                <button type="button" onClick={() => decideKyc(k, "REJECT")}>Reject</button></div></td></tr>)}</tbody>
          </table></div> : <p className="muted">Nothing awaiting approval.</p>}
        </section>
      ) : <>
        <form className="card stack" aria-labelledby="register-heading" onSubmit={register}><h2 id="register-heading">Register-Individual</h2>
          <div className="form-row">
            <label>Name as in Aadhaar<input name="name" required minLength={2} /></label>
            <label>Date of birth<input type="date" name="dob" required /></label>
            <label>Gender<select name="gender"><option value="FEMALE">Female</option><option value="MALE">Male</option><option value="TRANSGENDER">Transgender</option></select></label>
          </div>
          <div className="form-row">
            <label>Aadhaar<input name="aadhaar" required inputMode="numeric" pattern="[0-9]{12}" autoComplete="off" /></label>
            <label>Mobile<input name="mobile" required inputMode="numeric" pattern="[6-9][0-9]{9}" /></label>
            <label>Date of joining<input type="date" name="doj" required /></label>
            <label>Existing UAN <span className="muted small">(previous employment)</span><input name="existing_uan" inputMode="numeric" pattern="[0-9]{12}" /></label>
          </div>
          <p className="muted small">Demo: Aadhaar numbers are synthetic; one ending 0000 fails the mock UIDAI check.</p>
          <div className="actions"><button type="submit" className="primary">Register</button></div>
        </form>

        <form className="card stack" aria-labelledby="form11-heading" onSubmit={form11}><h2 id="form11-heading">Form 11 declaration</h2>
          <div className="form-row">
            <label>UAN<input name="uan" required pattern="[0-9]{12}" inputMode="numeric" /></label>
            <label>Declared on<input type="date" name="declared_on" required /></label>
            <label>Previous UAN<input name="previous_uan" pattern="[0-9]{12}" inputMode="numeric" /></label>
            <label>Country of origin <span className="muted small">(international worker)</span><input name="country" /></label>
          </div>
          <div className="form-row">
            <label className="check-row"><input type="checkbox" name="prev_pf" />Earlier a member of the EPF Scheme</label>
            <label className="check-row"><input type="checkbox" name="prev_eps" />Earlier a member of the EPS</label>
            <label className="check-row"><input type="checkbox" name="iw" />International worker</label>
          </div>
          <div className="actions"><button type="submit">Record Form 11</button></div>
        </form>

        <form className="card stack" aria-labelledby="bulk-heading" onSubmit={bulk("/api/v1/employers/me/members/bulk-registrations")}><h2 id="bulk-heading">Register-Bulk</h2>
          <label>One joinee per line: name, date of birth, gender, Aadhaar, mobile, date of joining[, existing UAN]<textarea name="content" required rows={4} /></label>
          <div className="actions"><button type="submit">Upload</button></div>
        </form>

        <form className="card stack" aria-labelledby="missing-heading" onSubmit={missing}><h2 id="missing-heading">Missing details</h2>
          <p className="muted small">Fill only what the record lacks; a recorded detail is changed through a Joint Declaration.</p>
          <div className="form-row">
            <label>UAN<input name="uan" required pattern="[0-9]{12}" inputMode="numeric" /></label>
            <label>Father's name<input name="father_name" /></label>
            <label>Mother's name<input name="mother_name" /></label>
          </div>
          <div className="form-row">
            <label>Marital status<select name="marital_status"><option value="">—</option><option>SINGLE</option><option>MARRIED</option><option>WIDOWED</option><option>DIVORCED</option></select></label>
            <label>Nationality<input name="nationality" /></label>
          </div>
          <div className="actions"><button type="submit">Save details</button></div>
        </form>

        <form className="card stack" aria-labelledby="kyc-bulk-heading" onSubmit={bulk("/api/v1/employers/me/kyc-bulk-uploads")}><h2 id="kyc-bulk-heading">KYC Bulk</h2>
          <label>One line per member: UAN, PAN or BANK, number[, IFSC]. Accepted lines wait for the authorised signatory's digital signature.<textarea name="content" required rows={4} /></label>
          <div className="actions"><button type="submit">Upload</button></div>
        </form>
      </>}

      {result ? <section className="card stack" aria-labelledby="upload-result-heading"><h2 id="upload-result-heading">Upload result</h2>
        <pre className="small">{JSON.stringify(result, (key, value: unknown) => (key === "state" || key === "status") && typeof value === "string" ? statusLabel(value, t) : value, 2)}</pre></section> : null}

      <section className="card stack" aria-labelledby="active-heading"><h2 id="active-heading">Active members</h2>
        <div className="actions"><button type="button" onClick={download} disabled={!rows.length}>Download CSV</button></div>
        <div className="table-scroll"><table>
          <thead><tr><th scope="col">UAN</th><th scope="col">Name</th><th scope="col">Joined</th><th scope="col">Aadhaar · PAN · bank</th><th scope="col">Form 11</th><th scope="col">Missing</th><th scope="col" /></tr></thead>
          <tbody>{rows.map((r) => <tr key={r.member_id}><td>{r.uan}<br /><span className="muted small">{r.member_id}</span></td><td>{r.name}</td><td>{r.date_of_joining}</td>
            <td>{[r.aadhaar, r.pan, r.bank].map((x) => statusLabel(x, t)).join(" · ")}</td><td>{statusLabel(r.form11, t)}</td>
            <td>{r.missing_details.join(", ").replaceAll("_", " ") || "—"}</td>
            <td><button type="button" onClick={() => showLedger(r.uan)}>Ledger</button></td></tr>)}</tbody>
        </table></div>
      </section>

      {ledger ? <section className="card stack" aria-labelledby="ledger-heading"><h2 id="ledger-heading">Contribution ledger — {ledger.name} ({ledger.member_id})</h2>
        {ledger.months.length ? <div className="table-scroll"><table><thead><tr><th scope="col">Wage month</th><th scope="col">TRRN</th><th scope="col">Employee share</th><th scope="col">Employer share</th></tr></thead>
          <tbody>{ledger.months.map((m) => <tr key={m.wage_month}><td>{m.wage_month}</td><td>{m.trrn}</td><td>{rupees(m.employee_paise)}</td><td>{rupees(m.employer_paise)}</td></tr>)}</tbody>
        </table></div> : <p className="muted">No paid returns credited yet.</p>}
      </section> : null}
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}
