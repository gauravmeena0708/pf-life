import { useState, type FormEvent, type ReactNode } from "react";

import { api, command, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { dateTime } from "../journeyB";

type Challenge = { challenge_id: string; prompt: string };
interface PublicResult {
  registration_no?: string; claim_id?: string; state: string; office_id?: string; sla_due_at?: string | null;
  note?: string; tier?: string; resolved_at?: string | null; resolution?: string | null;
  form_type?: string; next_step?: string; filed_on?: string; steps?: { at: string | null; state: string }[];
}
const label = (value: string) => value.replaceAll("_", " ").toLowerCase();

function PublicForm({ id, title, path, children }: { id: string; title: string; path: string; children: ReactNode }) {
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<PublicResult | null>(null);

  async function loadChallenge() {
    if (busy) return;
    setBusy(true); setError(null); setChallenge(null); setAnswer("");
    try { setChallenge((await api<Envelope<Challenge>>("/api/v1/public/demo-challenges")).data); }
    catch (cause) { setError(cause); } finally { setBusy(false); }
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy || !challenge) return;
    const fields = Object.fromEntries(new FormData(e.currentTarget).entries());
    const body = Object.fromEntries(Object.entries(fields).map(([key, value]) => [key, String(value).trim()]));
    setError(null); setResult(null);
    const integerAnswer = Number(answer);
    if (!/^-?\d+$/.test(answer.trim()) || !Number.isSafeInteger(integerAnswer)) {
      setError(new Error("Enter an integer answer to the demo question.")); return;
    }
    if (!/^[0-9]{6}$/.test(body.otp) || body.otp === "000000") {
      setError(new Error("Enter a mock one-time code of six digits except 000000.")); return;
    }
    if (body.mobile !== undefined && !/^[6-9][0-9]{9}$/.test(body.mobile)) {
      setError(new Error("Enter a 10-digit mobile number starting with 6, 7, 8 or 9.")); return;
    }
    if (body.claim_id !== undefined && (!/^CLM-[0-9A-F]{8}$/.test(body.claim_id) || !/^[0-9]{12}$/.test(body.uan))) {
      setError(new Error("Enter a claim ID as CLM-XXXXXXXX and a 12-digit UAN.")); return;
    }
    if (body.subject !== undefined && (body.subject.length < 5 || body.subject.length > 200
      || body.description.length < 10 || body.description.length > 4000 || body.name.length < 2)) {
      setError(new Error("Enter your name, a subject of 5–200 characters and a description of 10–4000 characters.")); return;
    }
    if (body.reference === "") delete body.reference;
    setBusy(true);
    try {
      setResult((await command<Envelope<PublicResult>>("POST", `/api/v1/public/${path}`, {
        ...body, challenge_id: challenge.challenge_id, answer: integerAnswer,
      })).data);
    } catch (cause) { setError(cause); }
    finally { setBusy(false); setChallenge(null); setAnswer(""); }
  }

  return <section className="card stack" aria-labelledby={id}>
    <h2 id={id}>{title}</h2>
    <form className="stack" aria-labelledby={id} onSubmit={(e) => void submit(e)}>
      <fieldset className="stack" disabled={busy}><legend>Details and verification</legend>
        {children}
        <p id={`${id}-otp-help`} className="muted">Mock one-time code: any six digits except 000000.</p>
        <label>Mock one-time code<input name="otp" required pattern="[0-9]{6}" maxLength={6} inputMode="numeric"
          autoComplete="one-time-code" aria-describedby={`${id}-otp-help`} /></label>
        <div className="challenge-row"><button type="button" onClick={() => void loadChallenge()}>Get one-use demo question</button>
          {challenge ? <label>{challenge.prompt}<input required inputMode="numeric" pattern="-?[0-9]+" value={answer} onChange={(e) => setAnswer(e.target.value)} /></label> : null}
        </div>
        <p className="muted small">The arithmetic question is a one-use demo check. Get a new question after each submission.</p>
        <div className="actions"><button type="submit" className="primary" disabled={!challenge}>{title}</button></div>
      </fieldset>
    </form>
    {busy ? <p role="status">Please wait…</p> : null}
    <ProblemMessage error={error} />
    {result ? <div className="profile-card stack" role="status">
      <p><strong>{result.registration_no ?? result.claim_id}</strong> · {label(result.state)}</p>
      <dl className="kv">
        {result.office_id ? <><dt>Office</dt><dd>{result.office_id}</dd></> : null}
        {result.tier ? <><dt>Handling tier</dt><dd>{result.tier}</dd></> : null}
        {result.sla_due_at !== undefined ? <><dt>Response due</dt><dd>{dateTime(result.sla_due_at, "en")}</dd></> : null}
        {result.resolved_at !== undefined ? <><dt>Resolved</dt><dd>{dateTime(result.resolved_at, "en")}</dd></> : null}
        {result.resolution ? <><dt>Resolution</dt><dd>{result.resolution}</dd></> : null}
        {result.form_type ? <><dt>Form</dt><dd>{result.form_type}</dd></> : null}
        {result.filed_on ? <><dt>Filed</dt><dd>{dateTime(result.filed_on, "en")}</dd></> : null}
      </dl>
      {result.note ? <p>{result.note}</p> : null}
      {result.next_step ? <p>{result.next_step}</p> : null}
      {result.steps?.length ? <ol>{result.steps.map((step, index) => <li key={index}>{dateTime(step.at, "en")} · {label(step.state)}</li>)}</ol> : null}
    </div> : null}
  </section>;
}

function MobileField() {
  return <label>Mobile number<input name="mobile" required pattern="[6-9][0-9]{9}" maxLength={10} inputMode="tel" autoComplete="tel-national" /></label>;
}

export function PublicGrievancesPage() {
  return <section className="stack" aria-labelledby="public-grievances-page-heading">
    <PageHeader id="public-grievances-page-heading" eyebrow="Public services · synthetic POC" title="Grievances without login"
      description="File a grievance or check its progress using your registration number and mobile number." current="Grievances" parent={{ label: "Public services", to: "/public" }} />
    <PublicForm id="public-grievance-heading" title="File a grievance" path="grievances">
      <label>Name<input name="name" required minLength={2} maxLength={120} autoComplete="name" /></label><MobileField />
      <div className="form-row">
        <label>Complainant type<select name="complainant_type" required>{["PENSIONER", "EMPLOYER", "MEMBER", "OTHER"].map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
        <label>Category<select name="category" required>{["CLAIM_DELAY", "CLAIM_REJECTION", "PASSBOOK", "KYC", "EMPLOYER", "OTHER"].map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
      </div>
      <label>Subject<input name="subject" required minLength={5} maxLength={200} /></label>
      <label>Description<textarea name="description" required minLength={10} maxLength={4000} /></label>
      <label>Reference (optional)<input name="reference" maxLength={40} /></label>
    </PublicForm>
    <PublicForm id="grievance-status-heading" title="Check grievance status" path="grievances/status-lookups">
      <label>Registration number<input name="registration_no" required pattern="GRV-[0-9A-F]{8}" placeholder="GRV-1234ABCD" /></label><MobileField />
    </PublicForm>
  </section>;
}

export function PublicClaimStatusPage() {
  return <section className="stack" aria-labelledby="public-claim-page-heading">
    <PageHeader id="public-claim-page-heading" eyebrow="Public services · synthetic POC" title="Claim status"
      description="Check a claim using its ID, UAN and a mock one-time code." current="Claim status" parent={{ label: "Public services", to: "/public" }} />
    <PublicForm id="claim-status-heading" title="Check claim status" path="claims/status-lookups">
      <label>Claim ID<input name="claim_id" required pattern="CLM-[0-9A-F]{8}" placeholder="CLM-1234ABCD" /></label>
      <label>UAN<input name="uan" required pattern="[0-9]{12}" maxLength={12} inputMode="numeric" /></label>
    </PublicForm>
  </section>;
}
