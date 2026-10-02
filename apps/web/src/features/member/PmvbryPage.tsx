import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, command, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { statusLabel } from "../statusLabel";
import "./PmvbryPage.css";

interface Instalment { instalment: number; amount_paise: number; state: string; missing: string[]; due_month: string | null; disbursal_deadline: string | null }
interface Membership { member_id: string; establishment_id: string; uan: string; financial_literacy_completed: boolean; part_a: { first_completed_month: string; instalments: Instalment[] } | null }
export function PmvbryPage() {
  const { t } = useTranslation(); const qc = useQueryClient();
  const [error, setError] = useState<unknown>(null); const [notice, setNotice] = useState(""); const [busy, setBusy] = useState(false);
  const view = useQuery({ queryKey: ["member-pmvbry"], queryFn: () => api<Envelope<{ memberships: Membership[] }>>("/api/v1/members/me/pmvbry"), retry: false });
  const memberships = view.data?.data.memberships ?? [];
  async function complete() {
    setError(null); setNotice(""); setBusy(true);
    try { await command("POST", "/api/v1/members/me/pmvbry/financial-literacy-completions");
      setNotice("Financial literacy course completion recorded."); await qc.invalidateQueries({ queryKey: ["member-pmvbry"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  return <section className="stack pmvbry" aria-labelledby="member-pmvbry-heading">
    <PageHeader id="member-pmvbry-heading" eyebrow="Employment incentive" title="PMVBRY — first-timer incentive (Part A)" current="PMVBRY" description="Pradhan Mantri Viksit Bharat Rozgar Yojana · Part A" />
    <p className="card">Eligible first-time employees may receive one month's EPF wage, up to ₹15,000, in two instalments: after six months, then after twelve months and completion of the financial literacy course. Payment is made by Aadhaar-bridge DBT to an Aadhaar-seeded bank account.</p>
    <ProblemMessage error={view.error} /><ProblemMessage error={error} />{view.isLoading ? <p role="status">Loading PMVBRY record…</p> : null}{notice ? <p role="status" className="ok">{notice}</p> : null}
    {view.data && !memberships.some((m) => m.part_a) ? <p className="card">There is no first-timer incentive entry for your membership at present.</p> : null}
    {memberships.map((m) => m.part_a ? <section className="card stack" key={m.member_id} aria-label={`PMVBRY entry for ${m.uan}`}>
      <h2>UAN {m.uan}</h2><p>First completed wage month: <strong>{m.part_a.first_completed_month}</strong></p>
      <div className="pmvbry-instalments">{m.part_a.instalments.map((inst) => <article className="pmvbry-instalment" key={inst.instalment}>
        <h3>Instalment {inst.instalment}</h3><p><strong>{rupees(inst.amount_paise)}</strong> · <span className="state-pill">{statusLabel(inst.state, t)}</span></p>
        <p>Disbursal deadline: {inst.disbursal_deadline ?? "Not set"}</p>
        {inst.missing.length ? <><h4>Still needed</h4><ul>{inst.missing.map((item) => <li key={item}>{item}</li>)}</ul></> : <p className="muted">No outstanding requirements recorded.</p>}
      </article>)}</div>
    </section> : null)}
    {memberships.some((m) => m.part_a) ? <section className="card stack" aria-labelledby="pmvbry-course-heading"><h2 id="pmvbry-course-heading">Financial literacy course</h2>
      <p>Save a part of each wage before spending. A small regular deposit helps prepare for unexpected needs.</p>
      <p>Interest adds to savings over time. Compare the rate and terms before choosing a savings or borrowing product.</p>
      <p>Keep your OTP, PIN and bank details private. Check the source of payment messages and report suspected fraud to your bank promptly.</p>
      {memberships.every((m) => !m.part_a || m.financial_literacy_completed) ? <p className="ok">Course completion recorded.</p> : <button type="button" className="primary" disabled={busy} onClick={() => void complete()}>I have completed the course</button>}
    </section> : null}
  </section>;
}
