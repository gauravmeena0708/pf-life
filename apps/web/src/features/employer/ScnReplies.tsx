import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";

/** Prosecution show-cause notices to the establishment (Compliance Manual 5.2.2): the particulars, the date the reply is due,
 *  and the reply — after which the RPFC decides whether to sanction a prosecution. */
interface Notice { prosecution_id: string; offence: string; particulars: string; state: string; reply_due: string; reply_overdue: boolean }
const OFFENCE: Record<string, string> = { NON_PAYMENT: "Dues assessed under 7A not paid", NON_FILING_RETURNS: "Returns not filed", OTHER: "Other" };
const STATE: Record<string, string> = { SCN_ISSUED: "Reply awaited", REPLIED: "Replied", SANCTIONED: "Prosecution sanctioned",
  COMPLAINT_FILED: "Complaint filed in court", DROPPED: "Dropped", CONVICTED: "Convicted", ACQUITTED: "Acquitted" };

export function ScnReplies() {
  const qc = useQueryClient();
  const [error, setError] = useState<unknown>(null); const [notice, setNotice] = useState(""); const [busy, setBusy] = useState(false);
  const list = useQuery({ queryKey: ["employer-scn"], retry: false, queryFn: () => api<Envelope<Notice[]>>("/api/v1/employers/me/prosecutions") });
  async function reply(e: FormEvent<HTMLFormElement>, id: string) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    setBusy(true); setError(null); setNotice("");
    try {
      await command("POST", `/api/v1/employers/me/prosecutions/${encodeURIComponent(id)}/replies`, { text: String(f.get("text")).trim(),
        documents: String(f.get("documents") || "").split(",").map((d) => d.trim()).filter(Boolean) });
      form.reset(); setNotice("Your reply is on the record."); await qc.invalidateQueries({ queryKey: ["employer-scn"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  if (!list.data?.data?.length) return null;
  return <section className="card stack" aria-labelledby="scn-heading">
    <h2 id="scn-heading">Show-cause notices before prosecution</h2>
    <ProblemMessage error={error} />{notice ? <p role="status" className="ok">{notice}</p> : null}
    {list.data.data.map((n) => <article key={n.prosecution_id} className="stack" aria-label={`Notice ${n.prosecution_id}`}>
      <h3>{n.prosecution_id} <span className="state-pill">{STATE[n.state] ?? n.state}</span></h3>
      <p>{OFFENCE[n.offence] ?? n.offence}: {n.particulars}</p>
      {n.state === "SCN_ISSUED" ? <form className="stack" aria-label={`Reply to ${n.prosecution_id}`} onSubmit={(e) => void reply(e, n.prosecution_id)}>
        <p className="muted small">Reply by {new Date(n.reply_due).toLocaleDateString("en-IN")}{n.reply_overdue ? " — the time has run out; reply now" : ""}.
          If the default is set right, tell the office: the matter may end there.</p>
        <label>Reply<textarea name="text" required minLength={10} /></label>
        <label>Documents (file names, comma-separated)<input name="documents" /></label>
        <div className="actions"><button className="primary" disabled={busy} type="submit">Send reply</button></div></form> : null}
    </article>)}
  </section>;
}
