import { useQuery } from "@tanstack/react-query";

import { api, rupees, type Envelope } from "../../api/client";
import { RECOVERY_STATE, type RecoveryCase } from "../office/RecoveryPage";

/** The establishment's recovery certificates: what is certified, realised and outstanding, and whether a court stayed it. */
export function RecoveryCases() {
  const list = useQuery({ queryKey: ["employer-recovery"], retry: false, queryFn: () => api<Envelope<RecoveryCase[]>>("/api/v1/employers/me/recovery-cases") });
  if (!list.data?.data?.length) return null;
  return <section className="card stack" aria-labelledby="employer-recovery-heading">
    <h2 id="employer-recovery-heading">Recovery of arrears</h2>
    <ul>{list.data.data.map((c) => <li key={c.recovery_case_id}><strong>{c.certificate_no}</strong> — {RECOVERY_STATE[c.state] ?? c.state} ·
      certified {rupees(c.amount_paise)}, realised {rupees(c.realised_paise)}, outstanding <strong>{rupees(c.outstanding_paise)}</strong>
      {c.pay_by && c.state === "NOTICE_SERVED" ? ` · pay by ${new Date(c.pay_by).toLocaleDateString("en-IN")}` : ""}{c.stayed ? " · stayed by a court" : ""}</li>)}</ul>
  </section>;
}
