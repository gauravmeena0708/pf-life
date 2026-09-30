import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, getSession, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { AgreementsTable } from "../international/AgreementsTable";
import { CocDetails } from "../international/CocDetails";
import type { CocApplication } from "../international/types";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

export function InternationalOfficePage() {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const role = session.data?.stakeholder;
  const officer = role === "fo.iw";
  const queue = useQuery({ queryKey: ["office-coc-applications"], enabled: officer, retry: false,
    queryFn: () => api<Envelope<CocApplication[]>>("/api/v1/office/international/coc-applications") });

  async function decide(e: FormEvent<HTMLFormElement>, application: CocApplication) {
    e.preventDefault();
    if (!officer || busy) return;
    const f = new FormData(e.currentTarget);
    setBusy(true); setError(null); setNotice(null);
    try {
      const decision = String(f.get("decision")); const reason = String(f.get("reason") ?? "").trim();
      if (decision !== "ISSUE" && decision !== "REJECT") throw new Error("Choose whether to issue or reject the certificate.");
      if (reason.length < 10) throw new Error("Enter a reason of at least 10 characters.");
      const token = await stepUp.ask({ action: "decide-coc", resourceId: application.application_id,
        summary: `${decision === "ISSUE" ? "Issue" : "Reject"} certificate of coverage for application ${application.application_id}, UAN ${application.uan}, ${application.country}. ${reason}` });
      if (!token) return;
      await command("POST", `/api/v1/office/international/coc-applications/${encodeURIComponent(application.application_id)}/decisions`,
        { decision, reason }, { stepUpToken: token });
      setNotice(decision === "ISSUE" ? "Certificate of coverage issued." : "Application rejected.");
      await qc.invalidateQueries({ queryKey: ["office-coc-applications"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }

  return <section className="stack" aria-labelledby="international-office-heading">
    <PageHeader id="international-office-heading" eyebrow="International workers" title={role === "ho.iwu" ? "Social-security agreements" : "Certificate of coverage applications"}
      description={role === "ho.iwu" ? "Review the illustrative agreement catalogue." : "Review signed applications and record certificate decisions."} current="International workers" />
    <ProblemMessage error={error ?? session.error ?? queue.error} />
    {notice ? <p role="status" className="ok">{notice}</p> : null}
    {session.isLoading ? <p role="status">Loading role…</p> : null}
    {session.data && !officer && role !== "ho.iwu" ? <p className="pending-notice">This service is available to the International Workers cell and HO International Workers Unit.</p> : null}
    {officer ? <section className="card stack" aria-labelledby="coc-queue-heading"><h2 id="coc-queue-heading">Certificate of coverage queue</h2>
      {queue.isLoading ? <p role="status">Loading applications…</p> : null}
      {queue.data?.data.map((application) => <article key={application.application_id} className="card stack">
        <h3>Application {application.application_id}</h3><CocDetails application={application} />
        {application.state === "SUBMITTED" ? <form className="stack" aria-label={`Decide CoC ${application.application_id}`} onSubmit={(e) => void decide(e, application)}>
          <fieldset className="stack" disabled={busy || !!stepUp.request}><legend>Certificate decision</legend>
            <label>Decision<select name="decision" required><option value="">Choose decision</option><option value="ISSUE">Issue</option><option value="REJECT">Reject</option></select></label>
            <label>Decision reason<textarea name="reason" required minLength={10} maxLength={1000} /></label>
            <div className="actions"><button type="submit" className="primary">Record decision</button></div>
          </fieldset>
        </form> : null}
      </article>)}
      {queue.data && !queue.data.data.length ? <p className="muted">No certificate applications to review.</p> : null}
    </section> : null}
    {officer || role === "ho.iwu" ? <AgreementsTable /> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </section>;
}
