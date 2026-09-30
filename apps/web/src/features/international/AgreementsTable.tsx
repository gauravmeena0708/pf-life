import { useQuery } from "@tanstack/react-query";

import { api, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import type { Agreements } from "./types";

export function useAgreements(enabled = true) {
  return useQuery({ queryKey: ["international-agreements"], enabled, retry: false,
    queryFn: () => api<Envelope<Agreements>>("/api/v1/international/agreements") });
}

export function AgreementsTable() {
  const agreements = useAgreements();
  return <section className="card stack" aria-labelledby="agreements-heading"><h2 id="agreements-heading">Social-security agreements</h2>
    <ProblemMessage error={agreements.error} />
    {agreements.isLoading ? <p role="status">Loading agreements…</p> : null}
    {agreements.data ? <><p className="pending-notice">{agreements.data.data.note}</p>
      {agreements.data.data.agreements.length ? <div className="table-scroll"><table><thead><tr>
        <th scope="col">Country</th><th scope="col">Code</th><th scope="col">In force from</th>
        <th scope="col">Maximum posting (months)</th><th scope="col">Maximum extension (months)</th>
        <th scope="col">Totalisation</th><th scope="col">Note</th>
      </tr></thead><tbody>{agreements.data.data.agreements.map((item) => <tr key={item.code}>
        <th scope="row">{item.country}</th><td>{item.code}</td><td>{item.in_force_from}</td>
        <td>{item.max_posting_months}</td><td>{item.max_extension_months}</td><td>{item.totalisation ? "Yes" : "No"}</td><td>{item.note}</td>
      </tr>)}</tbody></table></div> : <p className="muted">No agreements in this catalogue.</p>}
    </> : null}
  </section>;
}
