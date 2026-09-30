import { statusLabel } from "../statusLabel";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";

import { api, command, getSession, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

interface Nominee {
  name: string; relation: string; date_of_birth: string; share_bp: number; minor: boolean; guardian_name: string | null;
}
interface Nomination {
  nomination_id: string; state: string; has_family: boolean; signed_with: string | null; signed_at: string | null; nominees: Nominee[];
}
interface Nominations {
  uan: string; current: Nomination | null; history: Nomination[]; aadhaar_verified: boolean;
  relations: string[]; family_relations: string[]; note: string;
}
interface NomineeRow { id: number; name: string; relation: string; date_of_birth: string; share: string; guardian_name: string }
interface UanLookup {
  found: { uan: string; aadhaar_verified: boolean; latest_establishment: string | null; status: string }[];
  sent_to: string; note: string;
}

function NominationDetails({ item }: { item: Nomination }) {
  const { t } = useTranslation();
  return <div className="stack"><p><code>{item.nomination_id}</code> · {statusLabel(item.state, t)}
    {item.has_family ? " · Has family" : " · No family"}</p>
    <p>Signed with {item.signed_with ?? "—"} · {item.signed_at ?? "—"}</p>
    <div className="table-scroll"><table><thead><tr><th scope="col">Name</th><th scope="col">Relation</th>
      <th scope="col">Date of birth</th><th scope="col">Share</th><th scope="col">Minor</th><th scope="col">Guardian</th>
    </tr></thead><tbody>{item.nominees.map((nominee, index) => <tr key={index}>
      <th scope="row">{nominee.name}</th><td>{nominee.relation.replaceAll("_", " ")}</td><td>{nominee.date_of_birth}</td>
      <td>{nominee.share_bp / 100}%</td><td>{nominee.minor ? "Yes" : "No"}</td><td>{nominee.guardian_name || "—"}</td>
    </tr>)}</tbody></table></div>
  </div>;
}

export function NominationPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const nextRow = useRef(1);
  const [hasFamily, setHasFamily] = useState(true);
  const [rows, setRows] = useState<NomineeRow[]>([
    { id: 0, name: "", relation: "", date_of_birth: "", share: "100", guardian_name: "" },
  ]);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [lookupError, setLookupError] = useState<unknown>(null);
  const [lookup, setLookup] = useState<UanLookup | null>(null);
  const [busy, setBusy] = useState(false);
  const [lookupBusy, setLookupBusy] = useState(false);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const member = session.data?.stakeholder === "member";
  const nominations = useQuery({ queryKey: ["member-nominations"], enabled: member, retry: false,
    queryFn: () => api<Envelope<Nominations>>("/api/v1/members/me/nominations") });
  const data = nominations.data?.data;
  const relations = data ? (hasFamily ? data.family_relations : data.relations) : [];
  const disabled = busy || !!stepUp.request;
  const totalBp = rows.reduce((sum, row) => sum + Math.round(Number(row.share) * 100), 0);

  function updateRow(id: number, key: keyof Omit<NomineeRow, "id">, value: string) {
    setRows((current) => current.map((row) => row.id === id ? { ...row, [key]: value } : row));
  }

  async function nominate(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!data || !member || !data.aadhaar_verified) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      const nominees = rows.map((row) => ({ name: row.name.trim(), relation: row.relation,
        date_of_birth: row.date_of_birth, share_bp: Math.round(Number(row.share) * 100),
        ...(row.guardian_name.trim() ? { guardian_name: row.guardian_name.trim() } : {}) }));
      if (!nominees.length || nominees.some((row) => !row.name || !relations.includes(row.relation)
        || !row.date_of_birth || !Number.isSafeInteger(row.share_bp) || row.share_bp <= 0 || row.share_bp > 10000)
        || totalBp !== 10000) throw new Error("Enter nominee details and shares totalling 100%.");
      const token = await stepUp.ask({ action: "e-nominate", resourceId: data.uan,
        summary: `Sign Form 2 for UAN ${data.uan} with Aadhaar e-sign (mock): ${nominees.map((row) => `${row.name} (${row.share_bp / 100}%)`).join(", ")}.` });
      if (!token) return;
      await command("POST", "/api/v1/members/me/nominations", { has_family: hasFamily, nominees }, { stepUpToken: token });
      setNotice("Your e-Nomination has been signed with Aadhaar e-sign (mock).");
      await qc.invalidateQueries({ queryKey: ["member-nominations"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }

  async function findUan(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!member) return;
    const f = new FormData(e.currentTarget);
    const body = Object.fromEntries(["name", "date_of_birth", "mobile_last4", "otp"].map((key) => [key, String(f.get(key) ?? "").trim()]));
    setLookupBusy(true); setLookupError(null); setLookup(null);
    try {
      if (!body.name || !body.date_of_birth || !/^[0-9]{4}$/.test(body.mobile_last4)
        || !/^[0-9]{6}$/.test(body.otp) || body.otp === "000000") throw new Error("Enter your details and a mock OTP of six digits other than 000000.");
      setLookup((await command<Envelope<UanLookup>>("POST", "/api/v1/members/uan-lookups", body)).data);
    } catch (cause) { setLookupError(cause); } finally { setLookupBusy(false); }
  }

  return <section className="stack" aria-labelledby="nomination-page-heading">
    <PageHeader id="nomination-page-heading" eyebrow="Member services" title="e-Nomination and UAN lookup"
      description="Record your Form 2 nomination and find UANs linked to your details." current="e-Nomination" />
    <ProblemMessage error={session.error} />
    {session.isLoading ? <p role="status">Loading member role…</p> : null}
    {session.data && !member ? <p className="pending-notice">These services are available to members.</p> : null}
    {member ? <>
      <section className="card stack" aria-labelledby="nomination-heading"><h2 id="nomination-heading">e-Nomination (Form 2)</h2>
        <ProblemMessage error={error ?? nominations.error} />
        {notice ? <p role="status" className="ok">{notice}</p> : null}
        {nominations.isLoading ? <p role="status">Loading nominations…</p> : null}
        {data ? <>
          <p>UAN <code>{data.uan}</code></p><p className="muted">{data.note}</p>
          {!data.aadhaar_verified ? <p className="pending-notice" role="note">Aadhaar verification is required before you can sign an e-Nomination.</p> : null}
          <h3>Current nomination</h3>
          {data.current ? <NominationDetails item={data.current} /> : <p className="muted">No current nomination.</p>}
          <form className="stack" onSubmit={(e) => void nominate(e)} aria-label="New e-Nomination">
            <fieldset disabled={disabled || !data.aadhaar_verified} className="stack"><legend>Nominee details</legend>
              <label className="check-row"><input type="checkbox" checked={hasFamily} onChange={(e) => {
                setHasFamily(e.target.checked); setRows((current) => current.map((row) => ({ ...row, relation: "" })));
              }} />I have a family</label>
              {rows.map((row, index) => <fieldset key={row.id} className="stack"><legend>Nominee {index + 1}</legend>
                <div className="form-row">
                  <label>Name<input required maxLength={120} value={row.name} onChange={(e) => updateRow(row.id, "name", e.target.value)} /></label>
                  <label>Relation<select required value={row.relation} onChange={(e) => updateRow(row.id, "relation", e.target.value)}>
                    <option value="">Choose relation</option>{relations.map((relation) => <option key={relation} value={relation}>{relation.replaceAll("_", " ")}</option>)}
                  </select></label>
                  <label>Date of birth<input type="date" required value={row.date_of_birth} onChange={(e) => updateRow(row.id, "date_of_birth", e.target.value)} /></label>
                  <label>Share (%)<input type="number" required min="0.01" max="100" step="0.01" value={row.share} onChange={(e) => updateRow(row.id, "share", e.target.value)} /></label>
                  <label>Guardian name (required for a minor)<input maxLength={120} value={row.guardian_name} onChange={(e) => updateRow(row.id, "guardian_name", e.target.value)} /></label>
                </div>
                <div className="actions"><button type="button" disabled={rows.length === 1} aria-label={`Remove nominee ${index + 1}`}
                  onClick={() => setRows((current) => current.filter((item) => item.id !== row.id))}>Remove nominee</button></div>
              </fieldset>)}
              <p aria-live="polite">Total share: {totalBp / 100}% (must equal 100%).</p>
              <div className="actions"><button type="button" onClick={() => {
                const row = { id: nextRow.current++, name: "", relation: "", date_of_birth: "", share: "", guardian_name: "" };
                setRows((current) => [...current, row]);
              }}>Add nominee</button>
                <button type="submit" className="primary">Sign with Aadhaar e-sign (mock)</button></div>
            </fieldset>
          </form>
          <h3>Nomination history</h3>
          {data.history.length ? data.history.map((item) => <NominationDetails key={item.nomination_id} item={item} />)
            : <p className="muted">No nomination history.</p>}
        </> : null}
      </section>
      <section className="card stack" aria-labelledby="uan-lookup-heading"><h2 id="uan-lookup-heading">Know your UAN</h2>
        <ProblemMessage error={lookupError} />
        <form className="stack" onSubmit={(e) => void findUan(e)}>
          <p id="uan-otp-help" className="muted">Mock OTP: any six digits except 000000.</p>
          <fieldset disabled={lookupBusy} className="form-row"><legend>Lookup details</legend>
            <label>Name<input name="name" required maxLength={120} /></label>
            <label>Date of birth<input name="date_of_birth" type="date" required /></label>
            <label>Mobile last four digits<input name="mobile_last4" required pattern="[0-9]{4}" maxLength={4} inputMode="numeric" /></label>
            <label>Mock OTP<input name="otp" required pattern="[0-9]{6}" maxLength={6} inputMode="numeric" autoComplete="one-time-code" aria-describedby="uan-otp-help" /></label>
          </fieldset>
          <div className="actions"><button type="submit" className="primary" disabled={lookupBusy}>Find UAN</button></div>
        </form>
        {lookupBusy ? <p role="status">Looking up UANs…</p> : null}
        {lookup ? <div className="stack" role="status"><p>{lookup.note}</p><p>Sent to: {lookup.sent_to}</p>
          {lookup.found.length ? <div className="table-scroll"><table><thead><tr><th scope="col">UAN</th><th scope="col">Aadhaar verified</th>
            <th scope="col">Latest establishment</th><th scope="col">Status</th></tr></thead><tbody>{lookup.found.map((item) => <tr key={item.uan}>
            <th scope="row"><code>{item.uan}</code></th><td>{item.aadhaar_verified ? "Yes" : "No"}</td>
            <td>{item.latest_establishment || "—"}</td><td>{statusLabel(item.status, t)}</td>
          </tr>)}</tbody></table></div> : <p className="muted">No matching UAN found.</p>}
        </div> : null}
      </section>
    </> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </section>;
}
