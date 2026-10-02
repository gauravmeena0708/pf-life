import { useTranslation } from "react-i18next";
import { statusLabel } from "../statusLabel";
import { dateTime } from "../journeyB";
import "./ProceedingView.css";

export interface Proceeding {
  proceeding_id: string; establishment_id: string; kind: string; stage: string; open: boolean;
  due_by: string | null; overdue: boolean;
  history: { step: string; stage_after: string; actor_stakeholder: string; note: string; reference: string | null; at: string; form: string | null }[];
  what_is_due_next: { step: string; role: string; due_by: string; overdue: boolean }[];
}
/** Who acts at each stage, in the SOPs' words. */
export const ROLE_NAMES: Record<string, string> = { "exempted.trust": "The trust", "fo.exemption": "Exemption cell (RO)",
  "fo.oic": "RPFC-I (RO)", "zo.acc": "Zonal ACC", "ho.exemption": "HO Exemption Division" };
const who = (role: string) => ROLE_NAMES[role] ?? role;
export function ProceedingView({ proceeding }: { proceeding: Proceeding }) {
  const { t, i18n } = useTranslation();
  return <article className="profile-card stack" aria-label={`Proceeding ${proceeding.proceeding_id}`}>
    <h3>{statusLabel(proceeding.kind, t)} · <span className="state-pill">{statusLabel(proceeding.stage, t)}</span></h3>
    <p className="muted small">{proceeding.establishment_id} · {proceeding.proceeding_id}</p>
    <h4>History</h4><ol className="proceeding-timeline">{proceeding.history.map((item, index) => <li key={`${item.step}-${item.at}-${index}`}>
      <strong>{statusLabel(item.step, t)}</strong>{item.form ? ` · Form ${item.form}` : ""}
      <span className="muted small"> · {who(item.actor_stakeholder)} · <time dateTime={item.at}>{dateTime(item.at, i18n.language)}</time></span>
      <p>{item.note}{item.reference ? ` · Reference ${item.reference}` : ""}</p>
    </li>)}</ol>
    <h4>Next</h4>{proceeding.what_is_due_next.length ? <ul className="proceeding-next">{proceeding.what_is_due_next.map((due) => <li key={`${due.step}-${due.role}`}>
      {statusLabel(due.step, t)} · {who(due.role)} · Due <time dateTime={due.due_by}>{due.due_by}</time> {due.overdue ? <strong className="proceeding-overdue">Overdue</strong> : null}
    </li>)}</ul> : <p className="muted">No further step due.</p>}
  </article>;
}
