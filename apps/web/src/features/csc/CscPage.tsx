import { useState, type FormEvent } from "react";

import { command, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";

interface Allotment { uan: string; next_step: string }

export function CscPage() {
  const [faceToken, setFaceToken] = useState("");
  const [maskedAadhaar, setMaskedAadhaar] = useState("");
  const [result, setResult] = useState<Allotment | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fields = new FormData(form);
    const aadhaar = String(fields.get("aadhaar") ?? "").trim();
    (form.elements.namedItem("aadhaar") as HTMLInputElement).value = "";
    setError(null); setResult(null); setBusy(true); setMaskedAadhaar(`********${aadhaar.slice(-4)}`);
    try {
      const response = await command<Envelope<Allotment>>("POST", "/api/v1/members/uan-allotments", {
        aadhaar, name: String(fields.get("name") ?? "").trim(), date_of_birth: String(fields.get("date_of_birth")),
        gender: String(fields.get("gender")), mobile: String(fields.get("mobile") ?? "").trim(), face_auth_token: faceToken,
      });
      setResult(response.data);
      form.reset();
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  return <main className="stack" aria-labelledby="csc-heading">
    <PageHeader id="csc-heading" eyebrow="Common Service Centre" title="UAN allotment (Aadhaar face authentication, mock)" current="UAN allotment"
      description="Enter identity details and complete the mock face check before allotment." />
    <form className="card stack" onSubmit={(e) => void submit(e)}>
      <div className="form-row"><label>Aadhaar number<input name="aadhaar" required inputMode="numeric" pattern="[0-9]{12}" maxLength={12} autoComplete="off" /></label>
        <label>Name<input name="name" required minLength={2} maxLength={120} /></label></div>
      <div className="form-row"><label>Date of birth<input name="date_of_birth" type="date" required /></label>
        <label>Gender<select name="gender" required defaultValue=""><option value="" disabled>Select gender</option><option value="MALE">Male</option><option value="FEMALE">Female</option><option value="TRANSGENDER">Transgender</option></select></label>
        <label>Mobile<input name="mobile" required inputMode="numeric" pattern="[6-9][0-9]{9}" maxLength={10} /></label></div>
      <fieldset className="stack"><legend>Face authentication</legend><p className="muted small">This is a mock check; no camera or Aadhaar service is used.</p>
        <div className="actions"><button type="button" onClick={() => setFaceToken("MOCK-FACE-MATCH")}>Capture face (mock)</button>
          <button type="button" className="text-button" onClick={() => setFaceToken("MOCK-FACE-MISMATCH")}>Simulate a mismatch</button></div>
        <p role="status">{faceToken === "MOCK-FACE-MATCH" ? "Mock face match captured." : faceToken ? "Mock face mismatch selected." : "Capture a mock face check to continue."}</p>
      </fieldset>
      <div className="actions"><button type="submit" className="primary" disabled={!faceToken || busy}>Allot UAN</button></div>
    </form>
    {maskedAadhaar ? <p role="status">Aadhaar: {maskedAadhaar}</p> : null}
    <ProblemMessage error={error} />
    {result ? <section className="card stack" aria-label="Allotment result"><h2>UAN allotted</h2><p><strong>{result.uan}</strong></p><p>{result.next_step}</p></section> : null}
  </main>;
}
