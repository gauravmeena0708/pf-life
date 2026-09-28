import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { api, command, getSession, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

interface KycRequest { request_id: string; kyc_type: string; masked_value: string; source: string; state: string; verification: { verifier: string; verified: boolean; reason?: string }; decision_note: string | null; created_at: string }
interface Kyc { aadhaar: string; pan: string; bank: string; pan_masked: string | null; bank_ifsc: string; bank_account_last4: string; requests: KycRequest[] }
interface Readiness { uan: string; accounts: { account_link_id: string; establishment_name: string; ready_for: string[]; blockers: { code: string; blocks: string[]; fix: string }[] }[] }

const pill = (v: string) => <span className="state-pill">{v.replaceAll("_", " ").toLowerCase()}</span>;

/** Manage › KYC: status, seeding PAN and bank (mock NSDL / penny-drop), the employer's approval, and readiness. */
export function KycPage() {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const me = useQuery({ queryKey: ["me"], retry: false, queryFn: () => api<Envelope<{ member_id: string }>>("/api/v1/members/me") });
  useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const kyc = useQuery({ queryKey: ["kyc"], retry: false, queryFn: () => api<Envelope<Kyc>>("/api/v1/members/me/kyc") });
  const ready = useQuery({ queryKey: ["account-status"], retry: false, queryFn: () => api<Envelope<Readiness>>("/api/v1/members/me/account-status") });
  const k = kyc.data?.data;

  function seed(kind: "PAN" | "BANK") {
    return (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
      void (async () => {
        setError(null); setNotice(null);
        const token = await stepUp.ask({ action: "seed-kyc", resourceId: me.data!.data.member_id,
          summary: kind === "PAN" ? "Add your PAN. It is checked with NSDL (mock) and then approved by your employer." : "Add a bank account. It is checked by a penny-drop (mock) and then approved by your employer." });
        if (!token) return;
        try {
          const body = kind === "PAN" ? { number: String(f.get("pan")).trim().toUpperCase() } : { ifsc: String(f.get("ifsc")).trim().toUpperCase(), account_number: String(f.get("account")).trim() };
          const r = await command<Envelope<KycRequest>>("POST", kind === "PAN" ? "/api/v1/members/me/kyc/PAN" : "/api/v1/members/me/kyc/bank-accounts", body, { stepUpToken: token });
          form.reset();
          setNotice(r.data.state === "PENDING_EMPLOYER" ? `${kind} verified (${r.data.verification.verifier}); waiting for your employer's approval (${r.data.request_id}).`
            : `${kind} could not be verified: ${r.data.verification.reason ?? ""}`);
          await qc.invalidateQueries({ queryKey: ["kyc"] }); await qc.invalidateQueries({ queryKey: ["account-status"] });
        } catch (cause) { setError(cause); }
      })(); };
  }

  return (
    <section className="stack" aria-labelledby="kyc-page-heading">
      <PageHeader id="kyc-page-heading" eyebrow="Member services" title="KYC" current="KYC"
        description="Your Aadhaar, PAN and bank details. New details are checked (mock verifiers) and approved by your present employer." />
      <ProblemMessage error={kyc.error} />
      <ProblemMessage error={error} />
      {notice ? <p role="status" className="ok">{notice}</p> : null}
      {k ? (
        <section className="card stack" aria-labelledby="kyc-heading"><h2 id="kyc-heading">KYC status</h2>
          <dl className="kv">
            <dt>Aadhaar</dt><dd>{pill(k.aadhaar)}</dd>
            <dt>PAN</dt><dd>{pill(k.pan)} {k.pan_masked ? <code>{k.pan_masked}</code> : null}</dd>
            <dt>Bank account</dt><dd>{pill(k.bank)} {k.bank_account_last4 !== "-" ? <>ending <code>{k.bank_account_last4}</code> · IFSC <code>{k.bank_ifsc}</code></> : null}</dd>
          </dl>
          <p className="muted small"><Link to="/member/uan-card">View your UAN card</Link></p>
        </section>
      ) : null}
      <div className="form-row">
        <form className="card stack" aria-labelledby="pan-heading" onSubmit={seed("PAN")}><h2 id="pan-heading">Add PAN</h2>
          <label>PAN<input name="pan" required pattern="[A-Za-z]{5}[0-9]{4}[A-Za-z]" maxLength={10} autoComplete="off" /></label>
          <p className="muted small">Demo: an individual PAN has P as the fourth letter; one ending in Z shows a name mismatch.</p>
          <div className="actions"><button type="submit" className="primary">Verify and send for approval</button></div>
        </form>
        <form className="card stack" aria-labelledby="bank-heading" onSubmit={seed("BANK")}><h2 id="bank-heading">Add or change bank account</h2>
          <div className="form-row">
            <label>IFSC<input name="ifsc" required pattern="[A-Za-z]{4}0[A-Za-z0-9]{6}" maxLength={11} /></label>
            <label>Account number<input name="account" required inputMode="numeric" pattern="[0-9]{9,18}" /></label>
          </div>
          <p className="muted small">Demo: numbers ending 0000 fail the penny-drop.</p>
          <div className="actions"><button type="submit" className="primary">Verify and send for approval</button></div>
        </form>
      </div>
      {k?.requests.length ? (
        <section className="card stack" aria-labelledby="kyc-requests-heading"><h2 id="kyc-requests-heading">Your KYC requests</h2>
          <div className="table-scroll"><table>
            <thead><tr><th scope="col">Request</th><th scope="col">Type</th><th scope="col">Detail</th><th scope="col">Check</th><th scope="col">Status</th></tr></thead>
            <tbody>{k.requests.map((r) => <tr key={r.request_id}><td><code>{r.request_id}</code></td><td>{r.kyc_type}</td><td><code>{r.masked_value}</code></td>
              <td>{r.verification.verifier}: {r.verification.verified ? "verified" : r.verification.reason}</td>
              <td>{pill(r.state)}{r.decision_note ? <span className="muted small"> — {r.decision_note}</span> : null}</td></tr>)}</tbody>
          </table></div>
        </section>
      ) : null}
      {ready.data ? (
        <section className="card stack" aria-labelledby="readiness-heading"><h2 id="readiness-heading">Ready to claim?</h2>
          {ready.data.data.accounts.map((a) => (
            <div key={a.account_link_id} className="stack">
              <p><strong>{a.account_link_id}</strong> · {a.establishment_name} — {a.ready_for.length ? `ready for: ${a.ready_for.map((x) => x.replace("_", " ").toLowerCase()).join(", ")}` : "not ready for any claim"}</p>
              {a.blockers.length ? <ul>{a.blockers.map((b) => <li key={b.code}><code>{b.code}</code> — {b.fix}</li>)}</ul> : null}
            </div>
          ))}
        </section>
      ) : null}
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}

interface Card { uan: string; name: string; father_or_spouse_name: string | null; date_of_birth: string; gender: string; kyc: Record<string, string>; issued_by: string }

/** View › UAN Card (printable). */
export function UanCardPage() {
  const card = useQuery({ queryKey: ["uan-card"], retry: false, queryFn: () => api<Envelope<Card>>("/api/v1/members/me/uan-card") });
  const c = card.data?.data;
  return (
    <section className="stack" aria-labelledby="uan-card-heading">
      <PageHeader id="uan-card-heading" eyebrow="Member services" title="UAN card" current="UAN card" description="Print or save it as PDF from your browser." />
      <ProblemMessage error={card.error} />
      {c ? (
        <div className="card stack uan-card">
          <p className="eyebrow">Employees' Provident Fund Organisation — synthetic demonstration</p>
          <p className="figure">UAN {c.uan.replace(/(\d{4})(?=\d)/g, "$1 ")}</p>
          <dl className="kv"><dt>Name</dt><dd>{c.name}</dd><dt>Father's / spouse's name</dt><dd>{c.father_or_spouse_name ?? "—"}</dd>
            <dt>Date of birth</dt><dd>{c.date_of_birth}</dd><dt>Gender</dt><dd>{c.gender}</dd>
            <dt>KYC</dt><dd>Aadhaar {c.kyc.aadhaar?.toLowerCase()} · PAN {c.kyc.pan?.toLowerCase().replaceAll("_", " ")} · bank {c.kyc.bank?.toLowerCase().replaceAll("_", " ")}</dd></dl>
          <p className="muted small">{c.issued_by}</p>
          <div className="actions"><button type="button" onClick={() => window.print()}>Print</button></div>
        </div>
      ) : null}
    </section>
  );
}
