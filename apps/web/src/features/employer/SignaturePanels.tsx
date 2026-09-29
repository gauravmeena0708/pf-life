import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

const base = "/api/v1/employers/me";
const text = (form: FormData, key: string) => String(form.get(key) ?? "").trim();

interface Signatory {
  grant_id: string;
  username: string;
  kind: string;
  grants: string[];
  status: "ACTIVE" | "REVOKED";
}

interface SignatureRegistration {
  reg_id: string;
  signatory_id: string;
  username: string;
  purpose: "REGISTER" | "REVOKE";
  method: "DSC" | "ESIGN" | null;
  details: Record<string, unknown>;
  letter: { filename: string; size: number; sha256: string } | null;
  state: "LETTER_PENDING" | "PENDING_OFFICE" | "APPROVED" | "REJECTED" | "REVOKED";
  decision_note: string | null;
  created_at: string;
}

interface PendingApproval {
  case_id: string;
  title: string;
  subject_ref: string;
  state: string;
  action: string;
  since: string | null;
}

interface PendingApprovalsResponse { items: PendingApproval[]; note: string }

function fileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error ?? new Error("Could not read the PDF."));
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== "string" || !/^data:.*;base64,/.test(result)) {
        reject(new Error("Could not read the PDF as base64."));
        return;
      }
      resolve(result.slice(result.indexOf(",") + 1));
    };
    reader.readAsDataURL(file);
  });
}

export function EsignList({ canManage }: { canManage: boolean }) {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const signatories = useQuery({ queryKey: ["employer-signatories"], retry: false,
    queryFn: () => api<Envelope<Signatory[]>>(`${base}/signatories`) });
  const registrations = useQuery({ queryKey: ["employer-signature-registrations"], retry: false,
    queryFn: () => api<Envelope<SignatureRegistration[]>>(`${base}/signature-registrations`) });

  async function run(work: () => Promise<string | null>) {
    setError(null); setNotice(null); setBusy(true);
    try {
      const result = await work();
      if (result) {
        await Promise.all([
          qc.invalidateQueries({ queryKey: ["employer-signatories"] }),
          qc.invalidateQueries({ queryKey: ["employer-signature-registrations"] }),
        ]);
        setNotice(result);
      }
    } catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }

  function register(e: FormEvent<HTMLFormElement>, signatory: Signatory, method: "DSC" | "ESIGN") {
    e.preventDefault(); const form = e.currentTarget; const fields = new FormData(form);
    void run(async () => {
      const token = await stepUp.ask({ action: "register-signature", resourceId: signatory.grant_id,
        summary: `Register ${method === "DSC" ? "DSC" : "Aadhaar e-sign"} for ${signatory.username}.` });
      if (!token) return null;
      const body = method === "DSC"
        ? { certificate_serial: text(fields, "certificate_serial"), issuer: text(fields, "issuer"),
            holder_name: text(fields, "holder_name"), valid_to: text(fields, "valid_to") }
        : { holder_name: text(fields, "holder_name"), aadhaar_last4: text(fields, "aadhaar_last4") };
      await command<Envelope<SignatureRegistration>>("POST",
        `${base}/signatories/${encodeURIComponent(signatory.grant_id)}/${method === "DSC" ? "dsc" : "esign"}-registrations`,
        body, { stepUpToken: token });
      form.reset();
      return `${method === "DSC" ? "DSC" : "Aadhaar e-sign"} registration submitted for ${signatory.username}. Upload the signed request letter.`;
    });
  }

  function uploadLetter(e: FormEvent<HTMLFormElement>, signatory: Signatory, purpose: "request" | "revoke") {
    e.preventDefault(); const form = e.currentTarget;
    const file = (new FormData(form).get("letter") as File | null);
    void run(async () => {
      if (!file || !file.name) throw new Error("Select a signed PDF letter.");
      if ((file.type && file.type !== "application/pdf") || file.size > 1_000_000) {
        throw new Error("Upload a PDF letter of at most 1 MB.");
      }
      await command<Envelope<SignatureRegistration>>("POST",
        `${base}/signatories/${encodeURIComponent(signatory.grant_id)}/${purpose}-letters`,
        { filename: file.name, content_base64: await fileAsBase64(file) });
      form.reset();
      return `${purpose === "request" ? "Request" : "Revoke"} letter uploaded for ${signatory.username}.`;
    });
  }

  return <section className="card stack" aria-labelledby="esign-heading"><h2 id="esign-heading">Authorized eSign List (DSC / e-sign)</h2>
    <ProblemMessage error={error ?? signatories.error ?? registrations.error} />
    {notice ? <p role="status" className="ok">{notice}</p> : null}
    {signatories.data?.data.length ? <ul className="plain-list">{signatories.data.data.map((signatory) =>
      <li key={signatory.grant_id} className="stack">
        <h3>{signatory.username} <span className="state-pill">{signatory.status}</span></h3>
        {canManage && signatory.status === "ACTIVE" ? <>
          <form className="stack" aria-label={`Register DSC for ${signatory.username}`} onSubmit={(e) => register(e, signatory, "DSC")}>
            <h4>Register DSC</h4><div className="form-row">
              <label>Certificate serial<input name="certificate_serial" required pattern="[0-9A-Fa-f]{8,40}" minLength={8} maxLength={40} /></label>
              <label>Issuer<input name="issuer" required minLength={3} maxLength={80} /></label>
              <label>Holder name<input name="holder_name" required minLength={2} maxLength={120} /></label>
              <label>Valid to<input name="valid_to" type="date" required /></label>
            </div><div className="actions"><button type="submit" className="primary" disabled={busy}>Register DSC</button></div>
          </form>
          <form className="stack" aria-label={`Register Aadhaar e-sign for ${signatory.username}`} onSubmit={(e) => register(e, signatory, "ESIGN")}>
            <h4>Register Aadhaar e-sign</h4><div className="form-row">
              <label>Holder name<input name="holder_name" required minLength={2} maxLength={120} /></label>
              <label>Aadhaar last four digits<input name="aadhaar_last4" required pattern="[0-9]{4}" inputMode="numeric" maxLength={4} /></label>
            </div><div className="actions"><button type="submit" className="primary" disabled={busy}>Register Aadhaar e-sign</button></div>
          </form>
          <form className="stack" aria-label={`Upload signed request letter for ${signatory.username}`} onSubmit={(e) => uploadLetter(e, signatory, "request")}>
            <h4>Upload signed request letter</h4><label>Signed letter (PDF)<input name="letter" type="file" accept="application/pdf" required /></label>
            <div className="actions"><button type="submit" disabled={busy}>Upload signed request letter</button></div>
          </form>
        </> : null}
        {canManage && signatory.status === "REVOKED" ?
          <form className="stack" aria-label={`Upload signed revoke letter for ${signatory.username}`} onSubmit={(e) => uploadLetter(e, signatory, "revoke")}>
            <h4>Upload signed revoke letter</h4><label>Signed letter (PDF)<input name="letter" type="file" accept="application/pdf" required /></label>
            <div className="actions"><button type="submit" disabled={busy}>Upload signed revoke letter</button></div>
          </form> : null}
      </li>)}</ul> : signatories.data ? <p className="muted">No authorised signatories recorded.</p> : null}
    <h3>Registration and revoke requests</h3>
    {registrations.data?.data.length ? <div className="table-scroll"><table><thead><tr>
      <th scope="col">Signatory</th><th scope="col">Purpose</th><th scope="col">Method</th><th scope="col">State</th>
      <th scope="col">Letter file name</th><th scope="col">Office note</th>
    </tr></thead><tbody>{registrations.data.data.map((registration) => <tr key={registration.reg_id}>
      <th scope="row">{registration.username}</th><td>{registration.purpose}</td><td>{registration.method ?? "—"}</td>
      <td>{registration.state.replaceAll("_", " ")}</td><td>{registration.letter?.filename ?? "—"}</td>
      <td>{registration.decision_note || "—"}</td>
    </tr>)}</tbody></table></div> : registrations.data ? <p className="muted">No signature registrations recorded.</p> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </section>;
}

export function PendingApprovals() {
  const approvals = useQuery({ queryKey: ["employer-pending-approvals"], retry: false,
    queryFn: () => api<Envelope<PendingApprovalsResponse>>(`${base}/pending-approvals`) });
  return <section className="card stack" aria-labelledby="pending-approvals-heading"><h2 id="pending-approvals-heading">Pending approvals (DSC / e-sign)</h2>
    <ProblemMessage error={approvals.error} />
    {approvals.data?.data.items.length ? <div className="table-scroll"><table><thead><tr>
      <th scope="col">Title</th><th scope="col">Subject (UAN)</th><th scope="col">Waiting step</th><th scope="col">Since</th>
    </tr></thead><tbody>{approvals.data.data.items.map((item) => <tr key={item.case_id}>
      <th scope="row">{item.title}</th><td>{item.subject_ref}</td><td>{item.action}</td><td>{item.since?.slice(0, 10) ?? "—"}</td>
    </tr>)}</tbody></table></div> : approvals.data ? <p className="muted">Nothing waits for your signature.</p> : null}
    {approvals.data?.data.note ? <p className="muted small">{approvals.data.data.note}</p> : null}
  </section>;
}
