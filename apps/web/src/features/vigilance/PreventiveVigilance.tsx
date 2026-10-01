import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import { statusLabel } from "../statusLabel";
import "./vigilance.css";

export interface Clearance { clearance_id: string; username: string; purpose: string; cleared: boolean; valid_until: string; issued_at: string | null; reason: string; case_ids?: string[] }
interface SensitivePosts { officers: { username: string; stakeholder: string; office_id: string; posted_since: string | null; tenure_months: number | null; rotation: string }[]; transfer_list: string[] }

export function SensitivePostsPanel({ cvo = false }: { cvo?: boolean }) {
  const { t } = useTranslation();
  const posts = useQuery({ queryKey: ["vigilance-sensitive-posts"], queryFn: () => api<Envelope<SensitivePosts>>("/api/v1/vigilance/sensitive-posts"), retry: false });
  return <section className="card stack vigilance-panel" aria-labelledby="sensitive-posts-heading">
    <h2 id="sensitive-posts-heading">{cvo ? "Sensitive posts and rotation" : "Sensitive posts"}</h2>
    <ProblemMessage error={posts.error} />
    {posts.isLoading ? <p role="status">Loading sensitive posts…</p> : null}
    {posts.data ? <><div className="table-scroll"><table><thead><tr><th scope="col">User name</th><th scope="col">Role</th><th scope="col">Office</th><th scope="col">Posted since</th><th scope="col">Tenure</th><th scope="col">Rotation</th></tr></thead>
      <tbody>{posts.data.data.officers.map((officer) => <tr key={officer.username}><th scope="row">{officer.username}</th><td>{officer.stakeholder}</td><td>{officer.office_id}</td><td>{officer.posted_since ?? "—"}</td><td>{officer.tenure_months === null ? "—" : `${officer.tenure_months} months`}</td>
        <td><span className={officer.rotation === "ROTATION_OVERDUE" ? "vigilance-alert-pill" : "state-pill"}>{statusLabel(officer.rotation, t)}</span></td></tr>)}</tbody></table></div>
      <p>Due or overdue for the annual general transfer: {posts.data.data.transfer_list.join(", ") || "None"}</p></> : null}
  </section>;
}

export function ClearancesTable({ cvo = false }: { cvo?: boolean }) {
  const { t } = useTranslation();
  const clearances = useQuery({ queryKey: ["vigilance-clearances"], queryFn: () => api<Envelope<{ clearances: Clearance[] }>>("/api/v1/vigilance/clearances"), retry: false });
  return <><ProblemMessage error={clearances.error} />
    {clearances.isLoading ? <p role="status">Loading clearances…</p> : null}
    {clearances.data ? <div className="table-scroll"><table><thead><tr><th scope="col">User name</th><th scope="col">Purpose</th><th scope="col">Result</th><th scope="col">Valid until</th><th scope="col">Reason</th>{cvo ? <th scope="col">Withholding cases</th> : null}</tr></thead>
      <tbody>{clearances.data.data.clearances.map((item) => <tr key={item.clearance_id}><th scope="row">{item.username}</th><td>{statusLabel(item.purpose, t)}</td><td><span className="state-pill">{item.cleared ? "Cleared" : "Withheld"}</span></td><td>{item.valid_until}</td><td>{item.reason}</td>
        {cvo ? <td>{item.case_ids?.length ? item.case_ids.map((id, index) => <span key={id}>{index ? ", " : ""}<Link to={`?case=${encodeURIComponent(id)}`}>{id}</Link></span>) : "—"}</td> : null}</tr>)}</tbody></table></div> : null}
  </>;
}
