import { type FormEvent } from "react";

import { command, rupees } from "../../api/client";

/** On a passed order left unpaid: the recovery certificate to the Recovery Officer (s.8B), and the s.8F notice to a bank or a
 *  debtor of the employer to pay EPFO directly. */
const base = "/api/v1/office/compliance";
type Run = (work: () => Promise<unknown>, ok: string, form?: HTMLFormElement) => void;
type Ask = (request: { action: string; resourceId: string; amountPaise?: number; summary: string }) => Promise<string | null>;

export function RecoveryActions({ caseId, busy, run, ask }: { caseId: string; busy: boolean; run: Run; ask: Ask }) {
  async function certify(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const note = String(new FormData(form).get("note") ?? "").trim();
    const token = await ask({ action: "issue-recovery-certificate", resourceId: caseId, summary: `Certify the arrears of ${caseId} for recovery` }); if (!token) return;
    run(() => command("POST", `${base}/cases/${caseId}/recovery-certificates`, { note }, { stepUpToken: token }), "Recovery certificate issued to the Recovery Officer.", form);
  }
  async function garnishee(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form); const amount = Math.round(Number(f.get("amount")) * 100);
    const token = await ask({ action: "garnishee-8f", resourceId: caseId, amountPaise: amount, summary: `8F notice for ${rupees(amount)}` }); if (!token) return;
    run(() => command("POST", `${base}/cases/${caseId}/recovery-8f`, { garnishee: String(f.get("garnishee")), name: String(f.get("name")).trim(),
      reference: String(f.get("reference")).trim(), amount_paise: amount }, { stepUpToken: token }), "8F notice recorded; what was paid is realised.", form);
  }
  return <div className="stack">
    <form className="stack" aria-label="Issue recovery certificate" onSubmit={(e) => void certify(e)}>
      <h3>Recovery certificate (section 8B)</h3><p className="muted small">When the order's dues are unpaid after the 15 days it allows.</p>
      <label>Note<textarea name="note" required /></label>
      <div className="actions"><button disabled={busy} type="submit">Issue certificate</button></div></form>
    <form className="stack" aria-label="Notice under 8F" onSubmit={(e) => void garnishee(e)}>
      <h3>Notice to a bank or debtor (section 8F)</h3><p className="muted small">On a certificate being executed: they pay EPFO what they hold for the employer.</p>
      <div className="form-row"><label>To<select name="garnishee"><option value="BANK">A bank</option><option value="DEBTOR">A debtor</option></select></label>
        <label>Name<input name="name" required /></label><label>Account or debt<input name="reference" required /></label>
        <label>Amount (₹)<input name="amount" type="number" min="1" step="0.01" required /></label></div>
      <div className="actions"><button disabled={busy} type="submit">Issue 8F notice</button></div></form>
  </div>;
}
