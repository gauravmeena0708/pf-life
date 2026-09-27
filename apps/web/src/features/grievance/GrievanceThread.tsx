import { useTranslation } from "react-i18next";

import { dateTime, roleLabel, stateLabel } from "../journeyB";
import type { Grievance } from "./types";

const AUTHOR: Record<string, string> = { member: "You", system: "EPFO system (automatic)" };

/** The grievance conversation, status changes, evidence and documents, oldest first. Shared by member and office views. */
export function GrievanceThread({ grievance, viewer }: { grievance: Grievance; viewer: "member" | "office" }) {
  const { t, i18n } = useTranslation();
  const author = (by: string) => (viewer === "member" && AUTHOR[by]) || (by === "member" ? "Member" : roleLabel(by, t));
  return (
    <section className="card stack" aria-labelledby="thread-heading">
      <h2 id="thread-heading">{t("grievances.thread")}</h2>
      <ol className="claim-timeline">
        {grievance.entries.map((e, index) => (
          <li key={`${e.at}-${index}`} className={`${e.kind.toLowerCase()}${index === grievance.entries.length - 1 ? " current" : ""}`}>
            <div className="detail-head">
              <strong>{e.kind === "STATUS" && e.state ? stateLabel(e.state, t) : t(`grievances.kinds.${e.kind}`)}</strong>
              <time dateTime={e.at ?? undefined}>{dateTime(e.at, i18n.language)}</time>
            </div>
            <p className="muted small">{t("claimDetail.by")}: {author(e.by)}</p>
            <p>{e.body}</p>
            {e.evidence_refs?.length ? <p className="small">{t("grievances.evidence")}: {e.evidence_refs.map((ref) => <code key={ref}>{ref} </code>)}</p> : null}
          </li>
        ))}
      </ol>
      {grievance.documents.length ? (
        <div className="stack">
          <h3>{t("grievances.documents")}</h3>
          <ul className="lookup-results">
            {grievance.documents.map((d) => (
              <li key={d.document_id}>
                <strong>{d.filename}</strong>
                <span>{d.content_type} · {Math.ceil(d.size_bytes / 1024)} KB · SHA-256 <code>{d.sha256.slice(0, 16)}…</code></span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
