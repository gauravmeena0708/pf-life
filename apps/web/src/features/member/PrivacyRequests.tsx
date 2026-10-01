import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, command, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import { statusLabel } from "../statusLabel";

interface PrivacyItem { request_id: string; kind: string; details: string; state: string; due_on: string; answer: string | null }
const kinds = [{ code: "ACCESS", label: "Access" }, { code: "CORRECTION", label: "Correction" }, { code: "ERASURE", label: "Erasure" },
  { code: "GRIEVANCE", label: "Grievance" }, { code: "NOMINATE", label: "Nominate" }];
export function PrivacyRequests() {
  const { t } = useTranslation(); const qc = useQueryClient(); const [busy, setBusy] = useState(false); const [error, setError] = useState<unknown>(null); const [notice, setNotice] = useState("");
  const requests = useQuery({ queryKey: ["member-privacy"], queryFn: () => api<Envelope<PrivacyItem[]>>( "/api/v1/members/me/privacy-requests"), retry: false });
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (busy) return; const form = e.currentTarget; const f = new FormData(form);
    setBusy(true); setError(null); setNotice("");
    try {
      await command("POST", "/api/v1/members/me/privacy-requests", { kind: String(f.get("kind")), details: String(f.get("details") ?? "").trim() });
      form.reset(); setNotice("Your request has been sent to the data protection office."); await qc.invalidateQueries({ queryKey: ["member-privacy"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  return <section className="card stack" aria-labelledby="member-privacy-heading"><h2 id="member-privacy-heading">Your personal data (DPDP Act)</h2>
    <ProblemMessage error={error ?? requests.error} />{notice ? <p role="status" className="ok">{notice}</p> : null}
    <form className="stack" aria-label="Request about your personal data" onSubmit={(e) => void submit(e)}>
      <label>Request type<select name="kind">{kinds.map((kind) => <option key={kind.code} value={kind.code}>{kind.label}</option>)}</select></label>
      <label>Details<textarea name="details" required minLength={10} maxLength={4000} /></label>
      <div className="actions"><button className="primary" disabled={busy}>Send request</button></div>
    </form><h3>Your requests</h3>
    {requests.data?.data.map((item) => <article className="card stack" key={item.request_id}><h4>{item.request_id} · {statusLabel(item.kind, t)}</h4>
      <p>{statusLabel(item.state, t)} · Due {item.due_on}</p><p>{item.details}</p>{item.answer ? <p>Answer: {item.answer}</p> : null}</article>)}
    {requests.data && !requests.data.data.length ? <p className="muted">No personal data requests yet.</p> : null}
  </section>;
}
