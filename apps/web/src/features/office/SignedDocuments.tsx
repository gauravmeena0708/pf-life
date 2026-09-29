import { useState } from "react";

import { command, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";

export interface CaseDocument { doc_id: string; doc_type: string; title: string; signed_by_role: string; sha256: string; viewed_by_you: boolean }
interface Opened { doc_id: string; title: string; sha256: string; content: Record<string, unknown> }

/** Documents signed outside the office (the employer's DSC on a Form 13). Opening one is recorded; the step that
 * relies on it is enabled only after the officer has seen it ("View the employer signed pdf first"). */
export function SignedDocuments({ caseId, documents, onViewed }: { caseId: string; documents: CaseDocument[]; onViewed: () => void }) {
  const [opened, setOpened] = useState<Opened | null>(null);
  const [error, setError] = useState<unknown>(null);
  if (!documents.length) return null;
  const open = async (doc: CaseDocument) => {
    setError(null);
    try {
      setOpened((await command<Envelope<Opened>>("POST", `/api/v1/office/cases/${caseId}/documents/${doc.doc_id}/attestation-views`)).data);
      onViewed();
    } catch (cause) { setError(cause); }
  };
  return (
    <section className="stack" aria-labelledby="documents-heading">
      <h3 id="documents-heading">Signed documents</h3>
      <ProblemMessage error={error} />
      <ul className="plain-list">{documents.map((d) => <li key={d.doc_id}>
        <strong>{d.title}</strong> — signed by {d.signed_by_role.replace("employer.", "employer ")}{" "}
        {d.viewed_by_you ? <span className="state-pill">Viewed</span> : <span className="state-pill">Not yet viewed</span>}{" "}
        <button type="button" onClick={() => void open(d)}>View signed document</button></li>)}</ul>
      {opened ? <div className="pending-notice" role="region" aria-label={opened.title}>
        <p><strong>{opened.title}</strong> · SHA-256 <code>{opened.sha256.slice(0, 16)}…</code></p>
        <dl className="kv">{Object.entries(opened.content).map(([k, v]) => <div key={k} style={{ display: "contents" }}>
          <dt>{k.replaceAll("_", " ")}</dt><dd>{typeof v === "object" && v !== null ? JSON.stringify(v) : String(v ?? "—")}</dd></div>)}</dl>
      </div> : null}
    </section>
  );
}
