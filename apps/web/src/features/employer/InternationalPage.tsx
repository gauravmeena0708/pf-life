import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, getSession, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { AgreementsTable, useAgreements } from "../international/AgreementsTable";
import { CocDetails } from "../international/CocDetails";
import type { Certificate, CocApplication } from "../international/types";

interface Member { uan: string; account_link_id: string; name: string; date_of_joining: string; date_of_exit: string | null }

function pdfBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("The PDF could not be read. Choose the file again."));
    reader.onabort = () => reject(new Error("Reading the PDF was cancelled."));
    reader.onload = () => {
      if (typeof reader.result !== "string" || !reader.result.includes(",")) reject(new Error("The PDF could not be read."));
      else resolve(reader.result.slice(reader.result.indexOf(",") + 1));
    };
    reader.readAsDataURL(file);
  });
}

export function InternationalPage() {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [certificate, setCertificate] = useState<Certificate | null>(null);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const allowed = session.data?.stakeholder === "employer.signatory";
  const agreements = useAgreements(allowed);
  const members = useQuery({ queryKey: ["international-employer-members"], enabled: allowed, retry: false,
    queryFn: () => api<Envelope<Member[]>>("/api/v1/employers/me/members") });
  const applications = useQuery({ queryKey: ["employer-coc-applications"], enabled: allowed, retry: false,
    queryFn: () => api<Envelope<CocApplication[]>>("/api/v1/international/coc-applications") });

  async function run(work: () => Promise<string | null>) {
    if (!allowed || busy) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      const result = await work();
      if (result) { setNotice(result); await qc.invalidateQueries({ queryKey: ["employer-coc-applications"] }); }
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }

  function apply(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    void run(async () => {
      const member = members.data?.data.find((item) => item.account_link_id === f.get("member"));
      const country = String(f.get("country") ?? "");
      const host = String(f.get("host_employer") ?? "").trim();
      const from = String(f.get("posting_from") ?? ""); const to = String(f.get("posting_to") ?? "");
      if (!member || !agreements.data?.data.agreements.some((item) => item.country === country) || !host || !from || !to || to < from)
        throw new Error("Choose a member and agreement country, and enter a host employer and valid posting dates.");
      const result = await command<Envelope<CocApplication>>("POST", "/api/v1/international/coc-applications", {
        uan: member.uan, account_link_id: member.account_link_id, country, host_employer: host, posting_from: from, posting_to: to,
      });
      form.reset();
      return `Application ${result.data.application_id} created. Upload the signed PDF to submit it for review.`;
    });
  }

  function upload(e: FormEvent<HTMLFormElement>, application: CocApplication) {
    e.preventDefault(); const form = e.currentTarget; const file = new FormData(form).get("pdf");
    void run(async () => {
      if (!(file instanceof File) || !file.size || (file.type && file.type !== "application/pdf") || !/\.pdf$/i.test(file.name))
        throw new Error("Choose a signed PDF file.");
      await command("POST", `/api/v1/international/coc-applications/${encodeURIComponent(application.application_id)}/signed-uploads`,
        { filename: file.name, content_base64: await pdfBase64(file) });
      form.reset();
      return `Signed PDF uploaded for application ${application.application_id}.`;
    });
  }

  function extend(e: FormEvent<HTMLFormElement>, application: CocApplication) {
    e.preventDefault(); const form = e.currentTarget; const to = String(new FormData(form).get("posting_to") ?? "");
    void run(async () => {
      if (!to || to <= application.posting_to) throw new Error("Choose an extension end date after the current posting ends.");
      const result = await command<Envelope<CocApplication>>("POST", `/api/v1/international/coc-applications/${encodeURIComponent(application.application_id)}/extensions`, { posting_to: to });
      form.reset();
      return `Extension application ${result.data.application_id} created. Upload its signed PDF for review.`;
    });
  }

  function showCertificate(application: CocApplication) {
    setCertificate(null);
    void run(async () => {
      setCertificate((await api<Envelope<Certificate>>(`/api/v1/international/coc-applications/${encodeURIComponent(application.application_id)}/certificate`)).data);
      return null;
    });
  }

  return <section className="stack" aria-labelledby="international-employer-heading">
    <PageHeader id="international-employer-heading" eyebrow="Employer services" title="International workers (CoC)"
      description="Apply for certificates of coverage, upload signed applications and review issued certificates." current="International workers" />
    <ProblemMessage error={error ?? session.error ?? members.error ?? applications.error} />
    {notice ? <p role="status" className="ok">{notice}</p> : null}
    {session.isLoading ? <p role="status">Loading employer role…</p> : null}
    {session.data && !allowed ? <p className="pending-notice">This service is available to the authorised employer signatory.</p> : null}
    {allowed ? <>
      <section className="card stack" aria-labelledby="coc-apply-heading"><h2 id="coc-apply-heading">Apply for certificate of coverage</h2>
        {members.isLoading || agreements.isLoading ? <p role="status">Loading members and agreement countries…</p> : null}
        <form className="stack" aria-label="Apply for CoC" onSubmit={apply}>
          <fieldset className="stack" disabled={busy || !members.data || !agreements.data}><legend>Posting details</legend>
            <div className="form-row"><label>Member<select name="member" required defaultValue=""><option value="">Choose member</option>
              {members.data?.data.map((member) => <option key={member.account_link_id} value={member.account_link_id}>{member.name} · {member.uan} · {member.account_link_id}</option>)}
            </select></label><label>Agreement country<select name="country" required defaultValue=""><option value="">Choose country</option>
              {agreements.data?.data.agreements.map((item) => <option key={item.code} value={item.country}>{item.country}</option>)}
            </select></label><label>Host employer<input name="host_employer" required maxLength={200} /></label>
              <label>Posting from<input name="posting_from" type="date" required /></label><label>Posting to<input name="posting_to" type="date" required /></label>
            </div><div className="actions"><button type="submit" className="primary">Apply</button></div>
          </fieldset>
        </form>
      </section>
      <section className="card stack" aria-labelledby="coc-list-heading"><h2 id="coc-list-heading">Certificate applications</h2>
        {applications.isLoading ? <p role="status">Loading applications…</p> : null}
        {applications.data?.data.map((application) => <article key={application.application_id} className="card stack">
          <h3>Application {application.application_id}</h3><CocDetails application={application} />
          {application.state === "AWAITING_SIGNED_UPLOAD" ? <form className="stack" aria-label={`Upload signed PDF ${application.application_id}`} onSubmit={(e) => upload(e, application)}>
            <label>Signed PDF<input name="pdf" type="file" accept="application/pdf" required disabled={busy} /></label>
            <div className="actions"><button type="submit" className="primary" disabled={busy}>Upload signed PDF</button></div>
          </form> : null}
          {application.state === "ISSUED" ? <>
            <div className="actions"><button type="button" disabled={busy} onClick={() => showCertificate(application)}>View certificate</button></div>
            <form className="stack" aria-label={`Extend CoC ${application.application_id}`} onSubmit={(e) => extend(e, application)}>
              <label>Extension posting to<input name="posting_to" type="date" required disabled={busy} /></label>
              <div className="actions"><button type="submit" disabled={busy}>Apply for extension</button></div>
            </form>
          </> : null}
        </article>)}
        {applications.data && !applications.data.data.length ? <p className="muted">No certificate applications.</p> : null}
      </section>
      {certificate ? <section className="card stack coc-certificate" aria-labelledby="certificate-heading">
        <h2 id="certificate-heading">Certificate of coverage {certificate.certificate_no}</h2>
        <dl className="kv"><dt>Name</dt><dd>{certificate.name}</dd><dt>UAN</dt><dd>{certificate.uan}</dd>
          <dt>Country</dt><dd>{certificate.country}</dd><dt>Host employer</dt><dd>{certificate.host_employer}</dd>
          <dt>Posting</dt><dd>{certificate.posting_from} to {certificate.posting_to}</dd><dt>Issued</dt><dd>{certificate.issued_at}</dd>
          <dt>Issuing office</dt><dd>{certificate.issued_by_office}</dd><dt>Verification code</dt><dd>{certificate.verification_code}</dd></dl>
        <p className="certificate-text">{certificate.text}</p><div className="actions no-print">
          <button type="button" onClick={() => window.print()}>Print certificate</button><button type="button" onClick={() => setCertificate(null)}>Close certificate</button>
        </div>
      </section> : null}
      <AgreementsTable />
    </> : null}
  </section>;
}
