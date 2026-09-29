import { useState, type FormEvent } from "react";

import { api, command, type Envelope } from "../api/client";
import { ProblemMessage } from "../components/ProblemMessage";

type Challenge = { challenge_id: string; prompt: string };
type Kind = "ppo" | "status" | "payment" | "lc";

const KINDS: { kind: Kind; label: string; path: string }[] = [
  { kind: "ppo", label: "Know your PPO No.", path: "/api/v1/public/pension/ppo-lookups" },
  { kind: "status", label: "Know your pension status", path: "/api/v1/public/pension/status-enquiries" },
  { kind: "payment", label: "Pension payment enquiry", path: "/api/v1/public/pension/payment-enquiries" },
  { kind: "lc", label: "Jeevan Pramaan / life certificate", path: "/api/v1/public/pension/life-certificate-lookups" },
];

/** Pensioners' portal enquiries: login-free, a one-use demo question first, minimal disclosure. */
export function PensionEnquiries() {
  const [kind, setKind] = useState<Kind>("ppo");
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<unknown>(null);
  const current = KINDS.find((k) => k.kind === kind)!;

  async function loadChallenge() {
    setError(null); setResult(null); setAnswer("");
    try { setChallenge((await api<Envelope<Challenge>>("/api/v1/public/demo-challenges")).data); } catch (cause) { setError(cause); }
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!challenge) return;
    const f = new FormData(e.currentTarget);
    const value = (k: string) => String(f.get(k) ?? "").trim() || undefined;
    const body: Record<string, unknown> = kind === "ppo" ? { uan: value("uan"), bank_account_last4: value("last4"), date_of_birth: value("dob") }
      : kind === "lc" ? { ppo_id: value("ppo"), pramaan_id: value("pramaan") }
      : { ppo_id: value("ppo"), date_of_birth: value("dob") };
    setError(null);
    try {
      const r = await command<Envelope<Record<string, unknown>>>("POST", current.path, { ...body, challenge_id: challenge.challenge_id, answer: Number(answer) });
      setResult(r.data);
    } catch (cause) { setError(cause); }
    setChallenge(null); setAnswer("");
  }

  return (
    <section className="card stack" aria-labelledby="pension-enquiries">
      <div className="section-heading"><div><p className="eyebrow">03 / Pensioners</p><h2 id="pension-enquiries">Pension enquiries</h2></div><span className="badge badge-mock">Mock</span></div>
      <p className="muted">Login-free enquiries of the Pensioners' Portal on synthetic pensions. Answers disclose as little as possible.</p>
      <p className="demo-tip">Demo: PPO <code>PPO-DEMO-0001</code>, date of birth <code>1965-05-10</code>, UAN <code>100000000901</code>.</p>
      <div className="actions" aria-label="Enquiry">{KINDS.map((k) => <button key={k.kind} type="button" aria-pressed={kind === k.kind}
        onClick={() => { setKind(k.kind); setResult(null); }}>{k.label}</button>)}</div>
      <form className="stack" onSubmit={(e) => void submit(e)}>
        <div className="form-row">
          {kind === "ppo" ? <>
            <label>UAN / member ID<input name="uan" inputMode="numeric" pattern="[0-9]{12}" /></label>
            <label>or bank account (last 4 digits)<input name="last4" inputMode="numeric" pattern="[0-9]{4}" /></label>
          </> : <label>PPO number<input name="ppo" required={kind !== "lc"} /></label>}
          {kind === "lc" ? <label>or Jeevan Pramaan ID<input name="pramaan" pattern="JP[0-9]{8}" /></label>
            : kind !== "status" ? <label>Date of birth<input type="date" name="dob" required /></label> : null}
        </div>
        <div className="challenge-row"><button type="button" onClick={() => void loadChallenge()}>Get one-use demo question</button>
          {challenge ? <label>{challenge.prompt}<input inputMode="numeric" value={answer} onChange={(e) => setAnswer(e.target.value)} required /></label> : null}</div>
        <button className="primary" disabled={!challenge}>{current.label}</button>
      </form>
      <ProblemMessage error={error} />
      {result ? <div className="profile-card" aria-live="polite"><p className="eyebrow">Synthetic result</p>
        {result.found === false ? <p>No matching pension. {String(result.next_step ?? "")}</p> : <dl className="kv">
          {Object.entries(result).filter(([k]) => !["found", "label"].includes(k)).map(([k, v]) => <div key={k} style={{ display: "contents" }}>
            <dt>{k.replaceAll("_", " ")}</dt><dd>{Array.isArray(v) ? v.map((m) => (m as { month: string; credited_on: string }).month + " credited " + (m as { credited_on: string }).credited_on).join("; ") : String(v ?? "—")}</dd></div>)}
        </dl>}
      </div> : null}
    </section>
  );
}
