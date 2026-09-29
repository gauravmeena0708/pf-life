import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

const ENQUIRY_TABS = [
  { key: "ppo_details", label: "PPO Details" },
  { key: "beneficiary_details", label: "Beneficiary Details" },
  { key: "pension_payment_details", label: "Pension Payment Details" },
  { key: "scheme_certificate_issue_details", label: "Scheme Certificate Issue Details" },
  { key: "service_details", label: "Service Details" },
  { key: "arrears_adjustment_details", label: "Arrears Adjustment Details" },
  { key: "recovery_details", label: "Recovery Details" },
  { key: "tds_details", label: "TDS Details" },
] as const;

type EnquiryTab = (typeof ENQUIRY_TABS)[number]["key"];
type DetailObject = Record<string, unknown>;

interface Enquiry {
  ppo_details: DetailObject;
  beneficiary_details: DetailObject[];
  pension_payment_details: DetailObject[];
  scheme_certificate_issue_details: DetailObject | null;
  service_details: DetailObject;
  arrears_adjustment_details: DetailObject[];
  recovery_details: DetailObject[];
  tds_details: DetailObject[];
  note: string;
}

interface OverduePension {
  ppo_id: string;
  name: string;
  status: string;
  state: string;
  valid_till: string;
  source: string;
  reference: string;
}

interface ActivityRow {
  activity_id: string;
  ppo_id: string;
  activity: string;
  mode: string;
  status: string;
  details: DetailObject;
  initiated_role: string;
  decision_note: string | null;
  created_at: string;
  updated_at: string;
}

type Decision = "SETTLE" | "REJECT" | "SEND_BACK";

const ACTIVITY_OPTIONS = [
  { value: "BASIC_DETAILS", label: "Basic details" },
  { value: "PENSION_START", label: "Pension start" },
  { value: "PENSION_STOP", label: "Pension stop" },
  { value: "DLC_REVALIDATION", label: "DLC revalidation" },
  { value: "UNHOLD_TRANSACTIONS", label: "Unhold transactions" },
  { value: "PHYSICAL_LC", label: "Physical life certificate (PRO)" },
  { value: "DEATH", label: "Death updation (PRO)" },
  { value: "SPOUSE_REMARRIAGE", label: "Spouse remarriage updation (PRO)" },
] as const;

function fieldLabel(key: string): string {
  return key.replace(/_paise$/, "").replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function detailValue(key: string, value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (key.endsWith("_paise") && typeof value === "number") return rupees(value);
  if (Array.isArray(value)) return value.length ? value.map(String).join(", ") : "No records.";
  if (typeof value === "object") return detailList(value as DetailObject);
  return String(value);
}

function detailList(value: DetailObject) {
  const entries = Object.entries(value);
  if (entries.length === 0) return <p className="muted small">No records.</p>;
  return <dl className="kv">{entries.map(([key, entry]) => (
    <div key={key}><dt>{fieldLabel(key)}</dt><dd>{detailValue(key, entry)}</dd></div>
  ))}</dl>;
}

function enquiryPanel(value: DetailObject | DetailObject[] | null) {
  if (value === null || (Array.isArray(value) && value.length === 0)) return <p className="muted small">No records.</p>;
  if (!Array.isArray(value)) return detailList(value);
  const columns = Array.from(new Set(value.flatMap((row) => Object.keys(row))));
  if (columns.length === 0) return <p className="muted small">No records.</p>;
  return <div className="table-scroll"><table>
    <thead><tr>{columns.map((column) => <th key={column} scope="col">{fieldLabel(column)}</th>)}</tr></thead>
    <tbody>{value.map((row, index) => <tr key={index}>{columns.map((column) => (
      <td key={column}>{detailValue(column, row[column])}</td>
    ))}</tr>)}</tbody>
  </table></div>;
}

export function PensionOfficePage() {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [search, setSearch] = useState<{ ppo: string; memberId: string; uan: string } | null>(null);
  const [tab, setTab] = useState<EnquiryTab>("ppo_details");
  const [activity, setActivity] = useState<string>("BASIC_DETAILS");
  const [activityFilter, setActivityFilter] = useState("");
  const [modeFilter, setModeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const isDa = session.data?.stakeholder === "fo.da_pension";
  const isApfc = session.data?.stakeholder === "fo.apfc_pension";
  const enquiry = useQuery({
    queryKey: ["pension-office", "enquiry", search],
    queryFn: () => {
      const params = new URLSearchParams();
      if (search?.ppo) params.set("ppo", search.ppo);
      if (search?.memberId) params.set("memberId", search.memberId);
      if (search?.uan) params.set("uan", search.uan);
      return api<Envelope<Enquiry>>(`/api/v1/office/pensions/enquiries?${params.toString()}`);
    },
    enabled: search !== null,
    retry: false,
  });
  const overdue = useQuery({
    queryKey: ["pension-office", "overdue"],
    queryFn: () => api<Envelope<OverduePension[]>>("/api/v1/office/pensions/life-certificates/overdue"),
    retry: false,
  });
  const activities = useQuery({
    queryKey: ["pension-office", "activities", activityFilter, modeFilter, statusFilter],
    queryFn: () => {
      const params = new URLSearchParams();
      if (activityFilter) params.set("activity", activityFilter);
      if (modeFilter) params.set("mode", modeFilter);
      if (statusFilter) params.set("status", statusFilter);
      const query = params.toString();
      return api<Envelope<ActivityRow[]>>(`/api/v1/office/pensions/updation-activities${query ? `?${query}` : ""}`);
    },
    retry: false,
  });

  function searchPension(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const next = {
      ppo: String(form.get("ppo") ?? "").trim(),
      memberId: String(form.get("memberId") ?? "").trim(),
      uan: String(form.get("uan") ?? "").trim(),
    };
    setError(null);
    if (!next.ppo && !next.memberId && !next.uan) {
      setError(new Error("Enter a PPO number, member ID or UAN to search."));
      return;
    }
    setTab("ppo_details");
    setSearch(next);
  }

  async function changePension(row: OverduePension, action: "suspend" | "resume") {
    const reason = window.prompt(`Reason to ${action} pension ${row.ppo_id} (at least 10 characters):`)?.trim();
    if (!reason || reason.length < 10) return;
    setError(null);
    setNotice(null);
    setBusy(row.ppo_id);
    try {
      const token = await stepUp.ask({
        action: action === "suspend" ? "suspend-pension" : "resume-pension",
        resourceId: row.ppo_id,
        summary: action === "suspend"
          ? `Suspend the pension ${row.ppo_id} (${row.name}): the life certificate lapsed on ${row.valid_till}.`
          : `Resume the pension ${row.ppo_id}; months held back are credited now.`,
      });
      if (!token) return;
      if (action === "suspend") {
        await command("POST", `/api/v1/office/pensions/${encodeURIComponent(row.ppo_id)}/suspensions`, { reason }, { stepUpToken: token });
        setNotice(`Suspended the pension ${row.ppo_id}.`);
      } else {
        const result = await command<Envelope<{ released_months: string[]; released_paise: number }>>(
          "POST", `/api/v1/office/pensions/${encodeURIComponent(row.ppo_id)}/resumptions`, { reason }, { stepUpToken: token });
        const months = result.data.released_months;
        setNotice(`Resumed the pension ${row.ppo_id}. Released months: ${months.length ? months.join(", ") : "none"}. Amount released: ${rupees(result.data.released_paise)}.`);
      }
      await qc.invalidateQueries({ queryKey: ["pension-office"] });
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(null);
    }
  }

  async function initiate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const ppo = String(form.get("ppo") ?? "").trim();
    const reason = String(form.get("reason") ?? "").trim();
    const mode = String(form.get("mode") ?? "PHYSICAL");
    if (!ppo || reason.length < 10) {
      setError(new Error("Enter a PPO number and a reason of at least 10 characters."));
      return;
    }
    const details: Record<string, string> = {};
    if (activity === "DEATH") details.date_of_death = String(form.get("date_of_death") ?? "");
    if (activity === "BASIC_DETAILS") {
      const ifsc = String(form.get("bank_ifsc") ?? "").trim();
      const last4 = String(form.get("bank_account_last4") ?? "").trim();
      if (ifsc) details.bank_ifsc = ifsc;
      if (last4) details.bank_account_last4 = last4;
    }
    setError(null);
    setNotice(null);
    setBusy("initiate");
    try {
      const token = await stepUp.ask({ action: "initiate-pension-updation", resourceId: ppo, summary: `Initiate ${activity} for ${ppo}.` });
      if (!token) return;
      await command("POST", `/api/v1/office/pensions/${encodeURIComponent(ppo)}/updation-activities`,
        { activity, mode, reason, details }, { stepUpToken: token });
      setNotice(`Initiated ${fieldLabel(activity).toLowerCase()} for ${ppo}.`);
      formElement.reset();
      setActivity("BASIC_DETAILS");
      await qc.invalidateQueries({ queryKey: ["pension-office"] });
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(null);
    }
  }

  async function decide(row: ActivityRow, decision: Decision, label: string) {
    const note = window.prompt(`${label} ${row.activity_id}: enter a decision note (at least 5 characters):`)?.trim();
    if (!note || note.length < 5) return;
    setError(null);
    setNotice(null);
    setBusy(row.activity_id);
    try {
      const token = await stepUp.ask({
        action: "decide-pension-updation",
        resourceId: row.activity_id,
        summary: `${label} ${row.activity} ${row.activity_id} for ${row.ppo_id}.`,
      });
      if (!token) return;
      await command("POST", `/api/v1/office/pensions/updation-activities/${encodeURIComponent(row.activity_id)}/decisions`,
        { decision, note }, { stepUpToken: token });
      setNotice(`${label} recorded for activity ${row.activity_id}.`);
      await qc.invalidateQueries({ queryKey: ["pension-office"] });
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(null);
    }
  }

  return <div className="stack">
    <PageHeader id="pension-office-heading" eyebrow="Pension administration" title="Pension office"
      description="Pension enquiry, life certificates and updation activities (synthetic)." current="Pension office" />
    {notice ? <p role="status" className="ok">{notice}</p> : null}
    <ProblemMessage error={error} />
    <ProblemMessage error={session.error} />

    <section className="card stack" aria-labelledby="enquiry-heading">
      <h2 id="enquiry-heading">Pension Enquiry Details</h2>
      <form className="stack" onSubmit={searchPension}>
        <div className="form-row">
          <label>PPO No.<input name="ppo" /></label>
          <label>Member ID<input name="memberId" /></label>
          <label>UAN<input name="uan" /></label>
        </div>
        <div className="actions"><button type="submit" className="primary">Search</button></div>
      </form>
      <ProblemMessage error={enquiry.error} />
      {enquiry.isLoading ? <p role="status">Loading pension enquiry…</p> : null}
      {enquiry.data ? <>
        <div className="actions" aria-label="Pension enquiry details">
          {ENQUIRY_TABS.map((item) => <button key={item.key} type="button" aria-pressed={tab === item.key}
            onClick={() => setTab(item.key)}>{item.label}</button>)}
        </div>
        {enquiryPanel(enquiry.data.data[tab])}
        <p className="muted small">{enquiry.data.data.note}</p>
      </> : null}
    </section>

    <section className="card stack" aria-labelledby="overdue-heading">
      <h2 id="overdue-heading">Overdue life certificates</h2>
      <ProblemMessage error={overdue.error} />
      {overdue.isLoading ? <p role="status">Loading overdue life certificates…</p> : null}
      {overdue.data?.data.length === 0 ? <p className="muted small">No records.</p> : null}
      {overdue.data?.data.length ? <div className="table-scroll"><table>
        <thead><tr><th scope="col">PPO</th><th scope="col">Name</th><th scope="col">Valid till</th>
          <th scope="col">Pension status</th>{isApfc ? <th scope="col">Action</th> : null}</tr></thead>
        <tbody>{overdue.data.data.map((row) => <tr key={row.ppo_id}>
          <td>{row.ppo_id}</td><td>{row.name}</td><td>{row.valid_till}</td>
          <td><span className="state-pill">{fieldLabel(row.status)}</span></td>
          {isApfc ? <td>{row.status === "IN_PAYMENT" || row.status === "SUSPENDED"
            ? <button type="button" disabled={busy !== null} onClick={() => void changePension(row, row.status === "IN_PAYMENT" ? "suspend" : "resume")}>{row.status === "IN_PAYMENT" ? "Suspend" : "Resume"}</button>
            : null}</td> : null}
        </tr>)}</tbody>
      </table></div> : null}
    </section>

    <section className="card stack" aria-labelledby="updation-heading">
      <h2 id="updation-heading">Updation activities</h2>
      {isDa ? <form className="stack" onSubmit={(event) => void initiate(event)}>
        <h3>Initiate an activity</h3>
        <div className="form-row">
          <label>PPO number<input name="ppo" required /></label>
          <label>Activity<select name="activity" value={activity} onChange={(event) => setActivity(event.target.value)}>
            {ACTIVITY_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select></label>
          <label>Mode<select name="mode" defaultValue="PHYSICAL"><option value="PHYSICAL">Physical</option><option value="ONLINE">Online</option></select></label>
        </div>
        {activity === "DEATH" ? <label>Date of death<input name="date_of_death" type="date" required /></label> : null}
        {activity === "BASIC_DETAILS" ? <div className="form-row">
          <label>IFSC (optional)<input name="bank_ifsc" /></label>
          <label>Account last 4 digits (optional)<input name="bank_account_last4" inputMode="numeric" pattern="[0-9]{4}" maxLength={4} /></label>
        </div> : null}
        <label>Reason<textarea name="reason" required minLength={10} maxLength={500} /></label>
        <div className="actions"><button type="submit" className="primary" disabled={busy !== null}>Initiate activity</button></div>
      </form> : null}

      <div className="stack">
        <h3>Activity tracker</h3>
        <div className="form-row">
          <label>Activity<select value={activityFilter} onChange={(event) => setActivityFilter(event.target.value)}>
            <option value="">All activities</option>
            {ACTIVITY_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select></label>
          <label>Mode<select value={modeFilter} onChange={(event) => setModeFilter(event.target.value)}>
            <option value="">All modes</option><option value="PHYSICAL">Physical</option><option value="ONLINE">Online</option>
          </select></label>
          <label>Status<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="">All statuses</option>
            {(["NEW", "PENDING", "SETTLED", "REJECTED", "SENT_BACK_TO_DA"] as const).map((status) => (
              <option key={status} value={status}>{fieldLabel(status)}</option>
            ))}
          </select></label>
        </div>
        <ProblemMessage error={activities.error} />
        {activities.isLoading ? <p role="status">Loading activities…</p> : null}
        {activities.data?.data.length === 0 ? <p className="muted small">No records.</p> : null}
        {activities.data?.data.length ? <div className="table-scroll"><table>
          <thead><tr><th scope="col">Activity ID</th><th scope="col">PPO</th><th scope="col">Activity</th>
            <th scope="col">Mode</th><th scope="col">Status</th><th scope="col">Note</th>
            <th scope="col">Updated</th>{isApfc ? <th scope="col">Decision</th> : null}</tr></thead>
          <tbody>{activities.data.data.map((row) => <tr key={row.activity_id}>
            <td>{row.activity_id}</td><td>{row.ppo_id}</td><td>{row.activity.replace(/_/g, " ").toLowerCase()}</td>
            <td>{fieldLabel(row.mode)}</td><td><span className="state-pill">{fieldLabel(row.status)}</span></td>
            <td>{row.decision_note ?? "—"}</td><td>{new Date(row.updated_at).toLocaleString("en-IN")}</td>
            {isApfc ? <td>{row.status === "PENDING" || row.status === "NEW" ? <div className="actions">
              <button type="button" disabled={busy !== null} onClick={() => void decide(row, "SETTLE", "Settle")}>Settle</button>
              <button type="button" disabled={busy !== null} onClick={() => void decide(row, "REJECT", "Reject")}>Reject</button>
              <button type="button" disabled={busy !== null} onClick={() => void decide(row, "SEND_BACK", "Send back")}>Send back</button>
            </div> : null}</td> : null}
          </tr>)}</tbody>
        </table></div> : null}
      </div>
    </section>
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </div>;
}
