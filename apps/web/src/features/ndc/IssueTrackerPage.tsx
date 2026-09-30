import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, getSession, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

interface TrackerRequest {
  request_id: string; kind: string; target_uan: string; order_ref: string;
  order_document: { filename: string; size_bytes: number; sha256: string } | null;
  reason: string; notice: string | null; state: "RAISED" | "EXECUTED" | "REJECTED";
  raised_role: string; raised_at: string; executed_at: string | null; execution_note: string | null;
}
const kinds = ["FREEZE_MEMBER", "DEFREEZE_MEMBER", "LOGIN_NOTICE"] as const;
function readPdf(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("The order PDF could not be read."));
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.readAsDataURL(file);
  });
}
export function IssueTrackerRequests({ executor = false }: { executor?: boolean }) {
  const qc = useQueryClient(); const stepUp = useStepUp();
  const [busy, setBusy] = useState(false); const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null); const [kind, setKind] = useState<string>(kinds[0]);
  const requests = useQuery({ queryKey: ["issue-tracker-requests"], retry: false,
    queryFn: () => api<Envelope<TrackerRequest[]>>("/api/v1/ndc/issue-tracker/requests") });
  async function submit(e: FormEvent<HTMLFormElement>, request?: TrackerRequest) {
    e.preventDefault(); if (busy) return;
    const form = e.currentTarget; const f = new FormData(form);
    const text = (name: string) => String(f.get(name) ?? "").trim();
    setBusy(true); setError(null); setNotice(null);
    try {
      if (executor) {
        if (!request || request.state !== "RAISED") return;
        const decision = text("decision"); const note = text("note");
        if (!["EXECUTE", "REJECT"].includes(decision) || note.length < 5) throw new Error("Choose a decision and enter a note of at least 5 characters.");
        const token = await stepUp.ask({ action: "execute-issue-tracker", resourceId: request.request_id,
          summary: `${decision === "EXECUTE" ? "Execute" : "Reject"} ${request.kind} request ${request.request_id} for UAN ${request.target_uan}, order ${request.order_ref}. ${note}` });
        if (!token) return;
        await command("POST", `/api/v1/ndc/issue-tracker/requests/${encodeURIComponent(request.request_id)}/executions`, { decision, note }, { stepUpToken: token });
        setNotice(`Request ${request.request_id} ${decision === "EXECUTE" ? "executed" : "rejected"}.`);
      } else {
        const submittedKind = text("kind");
        if (!kinds.some((value) => value === submittedKind) || !/^[0-9]{12}$/.test(text("target_uan")) || text("order_ref").length < 3 || text("reason").length < 10)
          throw new Error("Choose a request kind and enter a 12-digit UAN, order reference and reason of at least 10 characters.");
        if (submittedKind === "LOGIN_NOTICE" && !text("notice")) throw new Error("Enter the notice the member will see.");
        const file = f.get("order"); let document: { order_filename: string; order_base64: string } | undefined;
        if (file instanceof File && file.size) {
          if (file.size > 2 * 1024 * 1024) throw new Error("Attach a PDF of at most 2 MB.");
          const order_base64 = await readPdf(file);
          if (!atob(order_base64).startsWith("%PDF")) throw new Error("Attach the order as a PDF.");
          document = { order_filename: file.name, order_base64 };
        }
        const result = await command<Envelope<TrackerRequest>>("POST", "/api/v1/ndc/issue-tracker/requests", {
          kind: submittedKind, target_uan: text("target_uan"), order_ref: text("order_ref"), reason: text("reason"),
          ...(submittedKind === "LOGIN_NOTICE" ? { notice: text("notice") } : {}), ...document,
        });
        setNotice(`Request ${result.data.request_id} raised for IS Division review.`);
      }
      form.reset(); await qc.invalidateQueries({ queryKey: ["issue-tracker-requests"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  const heading = executor ? "issue-tracker-heading" : "issue-tracker-raise-heading";
  return <section className="card stack" aria-labelledby={heading}><h2 id={heading}>{executor ? "Issue Tracker requests" : "Raise an Issue Tracker request"}</h2>
    <ProblemMessage error={error ?? requests.error} />{notice ? <p role="status" className="ok">{notice}</p> : null}
    {!executor ? <form className="stack" aria-label="Raise an Issue Tracker request" onSubmit={(e) => void submit(e)}>
      <fieldset className="stack" disabled={busy}><legend>Request and order</legend>
        <label>Request kind<select name="kind" value={kind} onChange={(e) => setKind(e.target.value)}>{kinds.map((value) => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select></label>
        <label>Target UAN<input name="target_uan" required pattern="[0-9]{12}" inputMode="numeric" /></label>
        <label>Order reference<input name="order_ref" required minLength={3} maxLength={80} /></label>
        <label>Reason<textarea name="reason" required minLength={10} maxLength={2000} /></label>
        {kind === "LOGIN_NOTICE" ? <label>Login notice<textarea name="notice" required maxLength={500} /></label> : null}
        <label>Order PDF (optional, up to 2 MB)<input name="order" type="file" accept="application/pdf,.pdf" /></label>
        <div className="actions"><button type="submit" className="primary">Raise request</button></div>
      </fieldset>
    </form> : null}
    {requests.isLoading ? <p role="status">Loading requests…</p> : null}
    {requests.data?.data.map((request) => <article className="card stack" key={request.request_id}><h3>{request.request_id} · {request.kind}</h3>
      <dl className="kv"><dt>Target UAN</dt><dd>{request.target_uan}</dd><dt>Order</dt><dd>{request.order_ref}</dd>
        <dt>Status</dt><dd>{request.state}</dd><dt>Raised by role</dt><dd>{request.raised_role}</dd><dt>Raised at</dt><dd>{request.raised_at}</dd>
        <dt>Executed at</dt><dd>{request.executed_at ?? "—"}</dd><dt>Execution note</dt><dd>{request.execution_note ?? "—"}</dd></dl>
      <p>{request.reason}</p>{request.notice ? <p>Login notice: {request.notice}</p> : null}
      {request.order_document ? <p>Order document: {request.order_document.filename} · {request.order_document.size_bytes} bytes · SHA-256 {request.order_document.sha256}</p> : <p className="muted">No order document attached.</p>}
      {executor && request.state === "RAISED" ? <form className="stack" aria-label={`Decide request ${request.request_id}`} onSubmit={(e) => void submit(e, request)}>
        <fieldset className="stack" disabled={busy || !!stepUp.request}><legend>IS Division decision</legend>
          <label>Decision<select name="decision" required><option value="">Choose decision</option><option value="EXECUTE">Execute</option><option value="REJECT">Reject</option></select></label>
          <label>Decision note<textarea name="note" required minLength={5} maxLength={1000} /></label>
          <div className="actions"><button className="primary" type="submit">Record decision</button></div>
        </fieldset>
      </form> : null}
    </article>)}
    {requests.data && !requests.data.data.length ? <p className="muted">No Issue Tracker requests.</p> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </section>;
}
export function IssueTrackerPage() {
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  return <section className="stack" aria-labelledby="issue-tracker-page-heading">
    <PageHeader id="issue-tracker-page-heading" eyebrow="IS Division" title="Issue Tracker" description="Review orders and execute or reject requests for synthetic member accounts." current="Issue Tracker" />
    <ProblemMessage error={session.error} />
    {session.isLoading ? <p role="status">Loading role…</p> : null}
    {session.data?.stakeholder === "ho.is" ? <IssueTrackerRequests executor /> : session.data ? <p className="pending-notice">This service is available to the IS Division.</p> : null}
  </section>;
}
