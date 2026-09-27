import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { api, command, getCurrentPolicy, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { dateTime, stateLabel } from "../journeyB";
import type { Grievance, GrievanceRow } from "./types";

interface ClaimRow { claim_id: string; claim_type: string; state: string }
const MAX_BYTES = 256 * 1024;

async function toBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  bytes.forEach((b) => { binary += String.fromCharCode(b); });
  return btoa(binary);
}

/** Member grievances (Journey C1): file one, optionally about a claim and with a document, and follow it. */
export function GrievancesPage() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const list = useQuery({ queryKey: ["member-grievances"], queryFn: () => api<Envelope<GrievanceRow[]>>("/api/v1/members/me/grievances"), retry: false });
  const policy = useQuery({ queryKey: ["current-policy"], queryFn: getCurrentPolicy, retry: false });
  const categories = policy.data?.data.grievance_categories ?? ["OTHER"];      // set in Policy administration
  const claims = useQuery({ queryKey: ["member-claims"], queryFn: () => api<Envelope<ClaimRow[]>>("/api/v1/members/me/claims"), retry: false });

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const file = form.get("document") as File | null;
    if (file && file.size > MAX_BYTES) {
      setError(new Error(t("grievances.fileTooLarge")));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await command<Envelope<Grievance>>("POST", "/api/v1/members/me/grievances", {
        category: form.get("category"), subject: String(form.get("subject")).trim(),
        description: String(form.get("description")).trim(), linked_claim_id: form.get("linked_claim_id") || null,
      });
      if (file && file.size > 0) {
        await command("POST", `/api/v1/grievances/${created.data.grievance_id}/documents`, {
          filename: file.name, content_type: file.type || "application/octet-stream", content_base64: await toBase64(file),
        });
      }
      await qc.invalidateQueries({ queryKey: ["member-grievances"] });
      navigate(`/member/grievances/${created.data.grievance_id}`);
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="stack" aria-labelledby="grievances-heading">
      <PageHeader id="grievances-heading" eyebrow={t("grievances.eyebrow")} title={t("grievances.title")}
        description={t("grievances.description")} current={t("navigation.grievances")} />
      <ProblemMessage error={error} />
      <form className="card stack" onSubmit={(e) => void submit(e)} aria-labelledby="new-grievance-heading">
        <div className="section-heading"><div><p className="eyebrow">01</p><h2 id="new-grievance-heading">{t("grievances.new")}</h2></div></div>
        <div className="form-row">
          <label>{t("grievances.category")}
            <select name="category" required defaultValue={categories.includes("CLAIM_DELAY") ? "CLAIM_DELAY" : categories[0]} key={categories.join()}>
              {categories.map((c) => <option key={c} value={c}>{t(`grievances.categories.${c}`, { defaultValue: c.replaceAll("_", " ").toLowerCase() })}</option>)}
            </select>
          </label>
          <label>{t("grievances.linkedClaim")}
            <select name="linked_claim_id" defaultValue="">
              <option value="">{t("grievances.noClaim")}</option>
              {claims.data?.data.map((c) => <option key={c.claim_id} value={c.claim_id}>{c.claim_id} · {stateLabel(c.state, t)}</option>)}
            </select>
          </label>
        </div>
        <label>{t("grievances.subject")}<input name="subject" required minLength={5} maxLength={200} /></label>
        <label>{t("grievances.details")}<textarea name="description" required minLength={10} maxLength={4000} /></label>
        <label>{t("grievances.document")}
          <input name="document" type="file" accept=".pdf,.png,.jpg,.jpeg,.txt,application/pdf,image/png,image/jpeg,text/plain" />
        </label>
        <p className="muted small">{t("grievances.documentHelp")}</p>
        <div className="actions"><button type="submit" className="primary" disabled={busy}>{t("grievances.submit")}</button></div>
      </form>
      <section className="card stack" aria-labelledby="my-grievances-heading">
        <div className="section-heading"><div><p className="eyebrow">02</p><h2 id="my-grievances-heading">{t("grievances.yours")}</h2></div></div>
        <ProblemMessage error={list.error} />
        {list.data?.data.length === 0 ? <p className="muted">{t("grievances.none")}</p> : null}
        {list.data?.data.length ? (
          <div className="table-scroll"><table>
            <thead><tr><th scope="col">{t("grievances.id")}</th><th scope="col">{t("grievances.subject")}</th><th scope="col">{t("grievances.status")}</th><th scope="col">{t("grievances.level")}</th><th scope="col">{t("grievances.dueBy")}</th></tr></thead>
            <tbody>{list.data.data.map((g) => (
              <tr key={g.grievance_id}>
                <td><Link to={`/member/grievances/${g.grievance_id}`}><code>{g.grievance_id}</code></Link></td>
                <td>{g.subject}</td>
                <td><span className="state-pill">{stateLabel(g.state, t)}</span></td>
                <td>{t(`grievances.tiers.${g.tier}`)}</td>
                <td>{dateTime(g.sla_due_at, i18n.language)}</td>
              </tr>
            ))}</tbody>
          </table></div>
        ) : null}
      </section>
    </section>
  );
}
