import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, command, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import { statusLabel } from "../statusLabel";

interface RtiItem { request_id: string; registration_no: string; subject: string; state: string; outcome: string | null; reply_due: string; days_left: number; overdue: boolean }
const exemptions = ["8(1)(d)", "8(1)(e)", "8(1)(g)", "8(1)(j)", "9", "11"];
export function RtiApplications() {
  const { t } = useTranslation(); const qc = useQueryClient(); const [busy, setBusy] = useState(false); const [error, setError] = useState<unknown>(null); const [notice, setNotice] = useState("");
  const [outcomes, setOutcomes] = useState<Record<string, string>>({});
  const list = useQuery({ queryKey: ["office-rti"], queryFn: () => api<Envelope<RtiItem[]>>( "/api/v1/office/rti-requests"), retry: false });
  async function submit(e: FormEvent<HTMLFormElement>, item?: RtiItem) {
    e.preventDefault(); if (busy) return; const form = e.currentTarget; const f = new FormData(form); const value = (key: string) => String(f.get(key) ?? "").trim();
    setBusy(true); setError(null); setNotice("");
    try {
      if (item) {
        const outcome = value("outcome"); const exemption_section = value("exemption_section"); const transferred_to = value("transferred_to");
        if (["REFUSED", "PARTLY_PROVIDED"].includes(outcome) && !exemption_section) throw new Error("Choose an exemption section.");
        if (outcome === "TRANSFERRED" && !transferred_to) throw new Error("Enter the receiving authority.");
        await command("POST", `/api/v1/office/rti-requests/${encodeURIComponent(item.request_id)}/replies`, { outcome, reply: value("reply"), exemption_section: exemption_section || null, transferred_to: transferred_to || null });
        setNotice(`${item.registration_no} replied to.`);
      } else {
        if (!f.has("fee_paid") && !f.has("bpl")) throw new Error("Record either the RTI fee or BPL status.");
        const result = await command<Envelope<{ registration_no: string }>>( "POST", "/api/v1/office/rti-requests", { applicant_name: value("applicant_name"), received_on: value("received_on"), mode: value("mode"), subject: value("subject"), information_sought: value("information_sought"), fee_paid: f.has("fee_paid"), bpl: f.has("bpl") });
        setNotice(`${result.data.registration_no} registered.`);
      }
      form.reset(); await qc.invalidateQueries({ queryKey: ["office-rti"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  return <section className="card stack" aria-labelledby="rti-applications-heading"><h2 id="rti-applications-heading">RTI applications</h2>
    <ProblemMessage error={error ?? list.error} />{notice ? <p role="status" className="ok">{notice}</p> : null}
    <form className="stack" aria-label="Register RTI application" onSubmit={(e) => void submit(e)}>
      <h3>Register application</h3><label>Applicant<input name="applicant_name" required minLength={2} maxLength={120} /></label>
      <div className="form-row"><label>Received on<input name="received_on" type="date" required max={new Date().toISOString().slice(0, 10)} /></label>
        <label>Mode<select name="mode"><option value="POST">Post</option><option value="COUNTER">Counter</option><option value="RTI_PORTAL">RTI portal</option></select></label></div>
      <label>Subject<input name="subject" required minLength={10} maxLength={200} /></label><label>Information sought<textarea name="information_sought" required minLength={20} maxLength={4000} /></label>
      <label><input type="checkbox" name="fee_paid" /> Fee paid</label><label><input type="checkbox" name="bpl" /> BPL</label>
      <div className="actions"><button className="primary" disabled={busy}>Register application</button></div>
    </form>
    <h3>Office register</h3>{list.data?.data.map((item) => <article className="card stack" key={item.request_id}><h4>{item.registration_no} · {item.subject}</h4>
      <p>{statusLabel(item.state, t)}{item.outcome ? ` · ${statusLabel(item.outcome, t)}` : ""} · Reply due {item.reply_due} · {item.overdue ? <span className="state-pill">Overdue</span> : `${item.days_left} days left`}</p>
      {item.state === "OPEN" ? <form className="stack" aria-label={`Reply to RTI ${item.registration_no}`} onSubmit={(e) => void submit(e, item)}>
        <label>Outcome<select name="outcome" value={outcomes[item.request_id] ?? "INFORMATION_PROVIDED"} onChange={(e) => setOutcomes({ ...outcomes, [item.request_id]: e.target.value })}>
          <option value="INFORMATION_PROVIDED">Information provided</option><option value="PARTLY_PROVIDED">Partly provided</option><option value="REFUSED">Refused</option><option value="TRANSFERRED">Transferred</option></select></label>
        <label>Reply<textarea name="reply" required minLength={20} maxLength={4000} /></label>
        {["REFUSED", "PARTLY_PROVIDED"].includes(outcomes[item.request_id]) ? <label>Exemption section<select name="exemption_section" required defaultValue=""><option value="">Choose section</option>{exemptions.map((section) => <option key={section}>{section}</option>)}</select></label> : null}
        {outcomes[item.request_id] === "TRANSFERRED" ? <label>Transferred to<input name="transferred_to" required /></label> : null}
        <div className="actions"><button className="primary" disabled={busy}>Send RTI reply</button></div>
      </form> : null}
    </article>)}{list.data && !list.data.data.length ? <p className="muted">No RTI applications.</p> : null}
  </section>;
}
