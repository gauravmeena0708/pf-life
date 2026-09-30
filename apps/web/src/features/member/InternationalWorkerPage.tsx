import { useQuery } from "@tanstack/react-query";

import { api, getSession, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import type { Agreement } from "../international/types";

interface InternationalWorker {
  uan: string; name: string; international_worker: boolean; nationality: string | null; passport_masked: string | null;
  employment: { account_link_id: string; establishment: string; date_of_joining: string; date_of_exit: string | null }[];
  agreement: Agreement | null; coverage: string;
}

export function InternationalWorkerPage() {
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const allowed = session.data?.stakeholder === "intl_worker";
  const worker = useQuery({ queryKey: ["international-worker"], enabled: allowed, retry: false,
    queryFn: () => api<Envelope<InternationalWorker>>("/api/v1/members/me/international") });
  const data = worker.data?.data;
  return <section className="stack" aria-labelledby="intl-worker-heading">
    <PageHeader id="intl-worker-heading" eyebrow="Member services" title="International worker coverage"
      description="Review your employment and coverage under the demonstration scheme." current="International worker" />
    <ProblemMessage error={session.error ?? worker.error} />
    {session.isLoading || worker.isLoading ? <p role="status">Loading coverage…</p> : null}
    {session.data && !allowed ? <p className="pending-notice">This service is available to international workers.</p> : null}
    {allowed && data ? <><section className="card stack"><h2>Worker details</h2>
      <dl className="kv"><dt>Name</dt><dd>{data.name}</dd><dt>UAN</dt><dd>{data.uan}</dd>
        <dt>International worker</dt><dd>{data.international_worker ? "Yes" : "No"}</dd><dt>Nationality</dt><dd>{data.nationality ?? "—"}</dd>
        <dt>Passport</dt><dd>{data.passport_masked ?? "—"}</dd></dl><p className="pending-notice">{data.coverage}</p>
      <h3>Agreement</h3>{data.agreement ? <><p>{data.agreement.country} · {data.agreement.code} · In force from {data.agreement.in_force_from}</p>
        <p>Maximum posting: {data.agreement.max_posting_months} months · Maximum extension: {data.agreement.max_extension_months} months · Totalisation: {data.agreement.totalisation ? "Yes" : "No"}</p>
        <p>{data.agreement.note}</p></> : <p>No agreement in this catalogue for your nationality.</p>}
    </section><section className="card stack"><h2>Employment</h2>
      {data.employment.length ? <div className="table-scroll"><table><thead><tr><th scope="col">Member ID</th><th scope="col">Establishment</th>
        <th scope="col">Date of joining</th><th scope="col">Date of exit</th></tr></thead><tbody>{data.employment.map((item) => <tr key={item.account_link_id}>
          <th scope="row">{item.account_link_id}</th><td>{item.establishment}</td><td>{item.date_of_joining}</td><td>{item.date_of_exit ?? "In service"}</td>
        </tr>)}</tbody></table></div> : <p className="muted">No employment records.</p>}
    </section></> : null}
  </section>;
}
