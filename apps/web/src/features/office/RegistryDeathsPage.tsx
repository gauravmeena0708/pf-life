import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";

import { api, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { statusLabel } from "../statusLabel";

interface Registration { registration_no: string; name: string; date_of_death: string; matched_uan: string | null; matched_by: string | null;
  outcome: string; exits_marked: string[]; received_at: string }

const OUTCOMES: Record<string, string> = {
  RECORDED: "Recorded: the member's open member IDs were closed and the nominees offered their claims",
  ALREADY_RECORDED: "Already recorded (the employer had marked the death)",
  NOT_A_MEMBER: "Matched no member — nothing to do unless a family member comes forward",
  AMBIGUOUS: "Matched more than one person — check the record before anything is done",
};

/** P2.21b: deaths the civil registry reported (mock) — the office's members, and records that matched nobody or several people. */
export function RegistryDeathsPage() {
  const { t } = useTranslation();
  const data = useQuery({ queryKey: ["registry-deaths"], retry: false, queryFn: () => api<Envelope<Registration[]>>("/api/v1/office/civil-registry/deaths") });
  const rows = data.data?.data ?? [];
  return <section className="stack" aria-labelledby="registry-deaths-heading">
    <PageHeader id="registry-deaths-heading" eyebrow="Regional office" title="Deaths from the civil registry" current="Registry deaths"
      description="The Civil Registration System reports registered deaths. A match closes the member's open member IDs and offers the nominees their claims; the rest are listed here." />
    <ProblemMessage error={data.error} />
    {data.isSuccess && !rows.length ? <p className="muted">No deaths reported yet.</p> : null}
    {rows.length ? <div className="table-scroll"><table>
      <thead><tr><th scope="col">Registration</th><th scope="col">Name</th><th scope="col">Date of death</th><th scope="col">Member</th><th scope="col">Outcome</th></tr></thead>
      <tbody>{rows.map((r) => <tr key={r.registration_no}><td>{r.registration_no}<div className="muted small">received {r.received_at.slice(0, 10)}</div></td>
        <td>{r.name}</td><td>{r.date_of_death}</td>
        <td>{r.matched_uan ? <>UAN {r.matched_uan}<div className="muted small">by {r.matched_by === "AADHAAR" ? "Aadhaar" : "name and date of birth"}
          {r.exits_marked.length ? `; exit marked on ${r.exits_marked.join(", ")}` : ""}</div></> : "—"}</td>
        <td><span className="state-pill">{statusLabel(r.outcome, t)}</span><div className="muted small">{OUTCOMES[r.outcome] ?? ""}</div></td></tr>)}</tbody>
    </table></div> : null}
  </section>;
}
