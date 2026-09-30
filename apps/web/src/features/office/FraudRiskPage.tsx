import { useQuery } from "@tanstack/react-query";

import { api, getSession, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";

interface FraudCases {
  zone_id: string; note: string;
  cases: { case_id: string; kind: string; process: string | null; office_id: string; office: string | null; subject_ref: string;
    claim_id: string | null; state: string; advisory_signal_id: string | null; why: string; opened_at: string | null }[];
}
export function FraudRiskPage() {
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const authorised = session.data?.stakeholder === "zo.fraud_committee";
  const cases = useQuery({ queryKey: ["fraud-risk-cases"], enabled: authorised, retry: false,
    queryFn: () => api<Envelope<FraudCases>>("/api/v1/zo/fraud-risk/cases") });
  const data = cases.data?.data;
  return <section className="stack" aria-labelledby="fraud-risk-heading">
    <PageHeader id="fraud-risk-heading" eyebrow="Zonal fraud-risk committee" title="Fraud-risk cases"
      description="Review illustrative account freezes and claims carrying an advisory risk signal in your zone." current="Fraud-risk cases" />
    <ProblemMessage error={session.error ?? cases.error} />
    {session.isLoading || cases.isLoading ? <p role="status">Loading cases…</p> : null}
    {session.data && !authorised ? <p className="pending-notice">This service is available to the zonal fraud-risk committee.</p> : null}
    {data ? <><p>Zone {data.zone_id}</p><p className="pending-notice">{data.note}</p>
      {data.cases.map((item) => <article key={item.case_id} className="card stack"><h2>{item.case_id}</h2>
        <dl className="kv"><dt>Kind</dt><dd>{item.kind}</dd><dt>Process</dt><dd>{item.process ?? "—"}</dd>
          <dt>Office</dt><dd>{item.office ?? item.office_id} · {item.office_id}</dd><dt>Subject</dt><dd>{item.subject_ref}</dd>
          <dt>Claim</dt><dd>{item.claim_id ?? "—"}</dd><dt>Status</dt><dd>{item.state}</dd>
          <dt>Advisory signal</dt><dd>{item.advisory_signal_id ?? "None"}</dd><dt>Opened</dt><dd>{item.opened_at ?? "—"}</dd></dl>
        <p>{item.why}</p><p className="muted">Risk signals are advisory and require review.</p>
      </article>)}
      {!data.cases.length ? <p className="muted">No fraud-risk cases in your zone.</p> : null}
    </> : null}
  </section>;
}
