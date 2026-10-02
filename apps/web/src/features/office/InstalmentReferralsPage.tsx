import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";

interface Referral { recovery_case_id: string; certificate_no: string | null; establishment_id: string; legal_name: string | null; office_id: string;
  outstanding_paise: number; count: number; note: string; by_rank: string; referred_at: string }

/** Instalments the region may not grant (circular 11.02.2014 para 4): the zone's ACC decides up to ₹50 lakh and 36
 *  instalments, Head Office (the CPFC) beyond — with a revolving bank guarantee of one instalment, or six beyond 36. */
export function InstalmentReferralsPage() {
  const qc = useQueryClient();
  const data = useQuery({ queryKey: ["instalment-referrals"], retry: false, queryFn: () => api<Envelope<Referral[]>>("/api/v1/zo/recovery/instalment-referrals") });
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(form: HTMLFormElement, work: () => Promise<string>) {
    setBusy(true); setError(null); setNotice(null);
    try { setNotice(await work()); form.reset(); await qc.invalidateQueries({ queryKey: ["instalment-referrals"] }); } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  function grant(e: FormEvent<HTMLFormElement>, r: Referral) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    void run(form, async () => {
      await command("POST", `/api/v1/office/recovery/${r.recovery_case_id}/instalments`, { count: Number(f.get("count")), first_due: String(f.get("first_due")),
        note: String(f.get("note")), bank_guarantee_paise: Math.round(Number(f.get("guarantee")) * 100), bank_guarantee_ref: String(f.get("guarantee_ref")) });
      return `${r.certificate_no ?? r.recovery_case_id}: ${String(f.get("count"))} instalments granted.`;
    });
  }
  function refuse(e: FormEvent<HTMLFormElement>, r: Referral) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    void run(form, async () => {
      await command("POST", `/api/v1/zo/recovery/instalment-referrals/${r.recovery_case_id}/refusals`, { reasons: String(f.get("reasons")) });
      return `${r.certificate_no ?? r.recovery_case_id}: instalments refused; recovery goes on.`;
    });
  }

  return <section className="stack" aria-labelledby="referrals-heading">
    <PageHeader id="referrals-heading" eyebrow="Recovery" title="Instalments referred by the regions" current="Instalment referrals"
      description="Arrears or instalments beyond a region's power: the zone's ACC up to ₹50 lakh and 36 instalments, Head Office beyond (at most 72)." />
    <ProblemMessage error={error ?? data.error} />
    {notice ? <p role="status" className="ok">{notice}</p> : null}
    {data.data && !data.data.data.length ? <p className="muted">No referral is waiting.</p> : null}
    {data.data?.data.map((r) => <article key={r.recovery_case_id} className="card stack" aria-label={`Referral ${r.certificate_no ?? r.recovery_case_id}`}>
      <h2>{r.legal_name ?? r.establishment_id} — {r.certificate_no ?? r.recovery_case_id}</h2>
      <dl className="kv"><div><dt>Office</dt><dd>{r.office_id}</dd></div><div><dt>Outstanding</dt><dd><strong>{rupees(r.outstanding_paise)}</strong></dd></div>
        <div><dt>Instalments asked</dt><dd>{r.count}</dd></div><div><dt>Referred by</dt><dd>{r.by_rank}, {r.referred_at.slice(0, 10)}</dd></div></dl>
      <p>{r.note}</p>
      <div className="activity-columns">
        <form className="stack" aria-label={`Grant ${r.recovery_case_id}`} onSubmit={(e) => grant(e, r)}><h3>Grant</h3>
          <div className="form-row"><label>Number<input name="count" type="number" min="2" max="72" defaultValue={r.count} required /></label>
            <label>First due<input name="first_due" type="date" required /></label></div>
          <div className="form-row"><label>Bank guarantee (₹)<input name="guarantee" type="number" min="0" step="0.01" required /></label>
            <label>Guarantee reference<input name="guarantee_ref" required /></label></div>
          <label>Note<input name="note" required /></label>
          <div className="actions"><button type="submit" className="primary" disabled={busy}>Grant instalments</button></div></form>
        <form className="stack" aria-label={`Refuse ${r.recovery_case_id}`} onSubmit={(e) => refuse(e, r)}><h3>Refuse</h3>
          <label>Reasons<textarea name="reasons" required minLength={10} /></label>
          <div className="actions"><button type="submit" disabled={busy}>Refuse</button></div></form>
      </div>
    </article>)}
  </section>;
}
