import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";

interface PensionRevision {
  revision_id: string;
  state: "PROPOSED" | "APPROVED" | "REJECTED";
  effective_from: string;
  from_rule_version: string;
  to_rule_version: string;
  old_monthly_paise: number;
  new_monthly_paise: number;
  working: string;
  arrears_paise: number | null;
  decided_at: string | null;
  note: string | null;
}

interface Pension {
  ppo_id: string;
  name: string;
  pension_type: string;
  pension_start: string;
  service_months: number;
  pensionable_salary_paise: number;
  age_at_start: number;
  monthly_paise: number;
  rule_version: string;
  working: string;
  bank_account_last4: string;
  revisions: PensionRevision[];
}

interface PensionPayment {
  month: string;
  kind: "MONTHLY" | "ARREARS";
  amount_paise: number;
  paid_on: string;
  revision_id: string | null;
}

export function PensionerPage() {
  const [showAllPayments, setShowAllPayments] = useState(false);
  const pension = useQuery({
    queryKey: ["pensioner-me"],
    queryFn: () => api<Envelope<Pension>>("/api/v1/pensioners/me"),
    retry: false,
  });
  const payments = useQuery({
    queryKey: ["pensioner-payments"],
    queryFn: () => api<Envelope<PensionPayment[]>>("/api/v1/pensioners/me/payments"),
    retry: false,
  });
  const record = pension.data?.data;
  const paymentRows = payments.data?.data ?? [];

  return (
    <section className="stack" aria-labelledby="pension-heading">
      <PageHeader id="pension-heading" eyebrow="Pensioner services" title="Your pension"
        description={record ? `${record.name} · PPO ${record.ppo_id}` : "Your pension record and payments"}
        current="Your pension" />
      <ProblemMessage error={pension.error} />
      {pension.isLoading ? <p role="status">Loading your pension…</p> : null}

      {record ? <>
        <section className="card stack" aria-labelledby="monthly-pension-heading">
          <h2 id="monthly-pension-heading">Monthly pension</h2>
          <p><strong className="figure">{rupees(record.monthly_paise)}</strong></p>
          <p><strong>How it is worked out:</strong> {record.working} <span className="muted small">(rule set {record.rule_version})</span></p>
          <dl className="kv">
            <dt>Pension type</dt><dd>{record.pension_type}</dd>
            <dt>Pension start date</dt><dd>{record.pension_start}</dd>
            <dt>Service</dt><dd>{Math.floor(record.service_months / 12)} years and {record.service_months % 12} months</dd>
            <dt>Bank account</dt><dd>Ending {record.bank_account_last4}</dd>
          </dl>
        </section>

        <section className="card stack" aria-labelledby="pension-revisions-heading">
          <h2 id="pension-revisions-heading">Revisions</h2>
          {record.revisions.some((revision) => revision.state === "PROPOSED")
            ? <p className="demo-tip">A revision under the new rules is waiting for approval by the APFC (Pension).</p>
            : null}
          {record.revisions.length ? <div className="table-scroll"><table>
            <thead><tr>
              <th scope="col">Effective from</th><th scope="col">Monthly pension</th>
              <th scope="col">Arrears</th><th scope="col">Status</th><th scope="col">Rules version</th>
            </tr></thead>
            <tbody>{record.revisions.map((revision) => <tr key={revision.revision_id}>
              <td>{revision.effective_from}</td>
              <td>{rupees(revision.old_monthly_paise)} → {rupees(revision.new_monthly_paise)}</td>
              <td>{rupees(revision.arrears_paise)}</td>
              <td><span className="state-pill">{revision.state.toLowerCase()}</span></td>
              <td>{revision.from_rule_version} → {revision.to_rule_version}</td>
            </tr>)}</tbody>
          </table></div> : <p className="muted small">No revisions.</p>}
        </section>
      </> : null}

      <section className="card stack" aria-labelledby="pension-payments-heading">
        <h2 id="pension-payments-heading">Payments</h2>
        <ProblemMessage error={payments.error} />
        {payments.isLoading ? <p role="status">Loading payments…</p> : null}
        {payments.data && !paymentRows.length ? <p className="muted small">No payments.</p> : null}
        {paymentRows.length ? <>
          <div className="table-scroll"><table>
            <thead><tr><th scope="col">Month</th><th scope="col">Kind</th><th scope="col">Amount</th><th scope="col">Paid on</th></tr></thead>
            <tbody>{(showAllPayments ? paymentRows : paymentRows.slice(0, 12)).map((payment, index) => <tr key={`${payment.month}-${payment.kind}-${payment.revision_id ?? "monthly"}-${index}`}>
              <td>{payment.month}</td><td>{payment.kind === "MONTHLY" ? "Monthly pension" : "Arrears"}</td>
              <td>{rupees(payment.amount_paise)}</td><td>{payment.paid_on}</td>
            </tr>)}</tbody>
          </table></div>
          {paymentRows.length > 12 ? <div className="actions"><button type="button" onClick={() => setShowAllPayments((shown) => !shown)}>
            {showAllPayments ? "Show fewer" : "Show all"}
          </button></div> : null}
        </> : null}
      </section>
    </section>
  );
}
