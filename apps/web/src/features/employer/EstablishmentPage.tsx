import { statusLabel } from "../statusLabel";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";

import { api, command, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";
import { EsignList } from "./SignaturePanels";
import "./EstablishmentPage.css";

const base = "/api/v1/employers/me";
const text = (form: FormData, key: string) => String(form.get(key) ?? "").trim();
const show = (value: unknown): string => value == null || value === "" ? "—" : typeof value === "boolean" ? value ? "Yes" : "No" : String(value);

interface Address { line: string; city: string; district: string; pincode: string; email?: string; phone?: string }
interface Configuration { coverage_type: string; coverage_date: string | null; exemption_status: string; establishment_type: string;
  industry_group: string; jurisdiction_office: string; schemes: string[]; sub_codes: string[]; address: Address }
interface ChangeRequest { request_id: string; kind: string; changes: Record<string, { from: unknown; to: unknown }>;
  reason: string; state: string; decision_note: string | null }
type KycType = "PAN" | "GSTIN" | "TAN" | "CIN" | "LIN";
interface KycRecord { value: string | null; status: string; reference: string | null }
interface KycResponse { kyc: Record<KycType, KycRecord>; note: string }
interface KycResult { result: string; reason: string; reference: string }
interface BankAccount { account_id: string; bank: string; ifsc: string; account_last4: string; purpose: string; verified: boolean }
interface Exemption { exemption_status: string; exempted: boolean; note: string }
interface Branch { branch_id: string; sub_code: string; name: string; kind: string; address: Address }
interface Person { name: string; designation: string; role: string; pan: string; share_pct: number }
interface Form5A { filed: boolean; note?: string; version?: number; nature_of_business?: string; persons?: Person[]; earlier_versions?: number }
interface PersonDraft { id: number; name: string; designation: string; role: string; pan: string; share_pct: string }
interface Contractor { contractor_id: string; registration_number: string; name: string; registered_with_epfo: boolean;
  establishment_id: string | null; work_order_ref: string; valid_from: string; valid_to: string | null }
interface ComplianceMonth { wage_month: string; members: number; epf_wages_paise: number; contribution_paise: number;
  paid: boolean; filing_id: string; work_order_ref: string }
interface Compliance { months: ComplianceMonth[]; unpaid_months: string[]; note: string }

function Facts({ rows }: { rows: [string, unknown][] }) {
  return <dl className="kv">{rows.map(([label, value]) => <div key={label} style={{ display: "contents" }}>
    <dt>{label}</dt><dd>{label.endsWith("(paise)") && typeof value === "number" ? rupees(value) : show(value)}</dd>
  </div>)}</dl>;
}

export function EstablishmentPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [kycResult, setKycResult] = useState<KycResult | null>(null);
  const [complianceId, setComplianceId] = useState<string | null>(null);
  const nextPersonId = useRef(1);
  const [persons, setPersons] = useState<PersonDraft[]>([{ id: 0, name: "", designation: "", role: "PROPRIETOR", pan: "", share_pct: "0" }]);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const role = session.data?.stakeholder ?? "";
  const employer = role === "employer.owner" || role === "employer.signatory" || role === "employer.operator";
  const canChange = role === "employer.owner" || role === "employer.signatory";
  const owner = role === "employer.owner";
  const me = useQuery({ queryKey: ["establishment-me"], enabled: employer, retry: false,
    queryFn: () => api<Envelope<{ establishment_id: string }>>(base) });
  const config = useQuery({ queryKey: ["establishment-config"], enabled: employer, retry: false,
    queryFn: () => api<Envelope<Configuration>>(`${base}/configuration`) });
  const changes = useQuery({ queryKey: ["establishment-changes"], enabled: employer, retry: false,
    queryFn: () => api<Envelope<ChangeRequest[]>>(`${base}/change-requests`) });
  const kyc = useQuery({ queryKey: ["establishment-kyc"], enabled: employer, retry: false,
    queryFn: () => api<Envelope<KycResponse>>(`${base}/kyc`) });
  const banks = useQuery({ queryKey: ["establishment-banks"], enabled: employer, retry: false,
    queryFn: () => api<Envelope<BankAccount[]>>(`${base}/bank-accounts`) });
  const exemption = useQuery({ queryKey: ["establishment-exemption"], enabled: employer, retry: false,
    queryFn: () => api<Envelope<Exemption>>(`${base}/exemption`) });
  const branches = useQuery({ queryKey: ["establishment-branches"], enabled: employer, retry: false,
    queryFn: () => api<Envelope<Branch[]>>(`${base}/branches`) });
  const form5a = useQuery({ queryKey: ["establishment-form5a"], enabled: employer, retry: false,
    queryFn: () => api<Envelope<Form5A>>(`${base}/ownership-declaration`) });
  const contractors = useQuery({ queryKey: ["establishment-contractors"], enabled: employer, retry: false,
    queryFn: () => api<Envelope<Contractor[]>>(`${base}/contractors`) });
  const compliance = useQuery({ queryKey: ["contractor-compliance", complianceId], enabled: !!complianceId, retry: false,
    queryFn: () => api<Envelope<Compliance>>(`${base}/contractors/${encodeURIComponent(complianceId!)}/compliance`) });
  const loadError = [session.error, me.error, config.error, changes.error, kyc.error, banks.error, exemption.error,
    branches.error, form5a.error, contractors.error].find(Boolean);
  const establishmentId = me.data?.data.establishment_id;

  async function run(work: () => Promise<string | null>) {
    setError(null); setNotice(null);
    try { const result = await work(); if (result) setNotice(result); } catch (cause) { setError(cause); }
  }
  async function refresh(...keys: string[]) {
    await Promise.all(keys.map((key) => qc.invalidateQueries({ queryKey: [key] })));
  }
  function requireId() {
    if (!establishmentId) throw new Error("The establishment record is still loading. Please try again.");
    return establishmentId;
  }
  function requestConfig(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    void run(async () => {
      const id = requireId();
      const token = await stepUp.ask({ action: "request-establishment-change", resourceId: id,
        summary: `Request a change to ${text(f, "field").replaceAll("_", " ")} for ${id}.` });
      if (!token) return null;
      const result = await command<Envelope<ChangeRequest>>("POST", `${base}/configuration/change-requests`,
        { field: text(f, "field"), value: text(f, "value"), reason: text(f, "reason") }, { stepUpToken: token });
      form.reset(); await refresh("establishment-changes");
      return `Change request ${result.data.request_id} submitted.`;
    });
  }
  function requestContact(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    void run(async () => {
      const id = requireId();
      const addressKeys = ["line", "city", "district", "pincode"] as const;
      const addressValues = addressKeys.map((key) => text(f, key));
      if (addressValues.some(Boolean) && addressValues.some((value) => !value)) {
        throw new Error("Complete all four address fields when changing the address.");
      }
      const address = addressValues.every(Boolean) ? Object.fromEntries(addressKeys.map((key) => [key, text(f, key)])) : undefined;
      const email = text(f, "email") || undefined, phone = text(f, "phone") || undefined;
      if (!address && !email && !phone) throw new Error("Enter an address or contact detail to change.");
      const token = await stepUp.ask({ action: "request-establishment-change", resourceId: id,
        summary: `Request an address or contact change for ${id}.` });
      if (!token) return null;
      const result = await command<Envelope<ChangeRequest>>("PATCH", base,
        { ...(address ? { address } : {}), ...(email ? { email } : {}), ...(phone ? { phone } : {}), reason: text(f, "reason") },
        { stepUpToken: token });
      form.reset(); await refresh("establishment-changes");
      return `Change request ${result.data.request_id} submitted.`;
    });
  }
  function seedKyc(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    void run(async () => {
      const kind = text(f, "type");
      const token = await stepUp.ask({ action: "seed-establishment-kyc", resourceId: `${requireId()}:${kind}`,
        summary: `Verify ${kind} against the mock registry.` });
      if (!token) return null;
      const result = await command<Envelope<KycResult>>("POST", `${base}/kyc/${kind}`, { value: text(f, "value").toUpperCase() },
        { stepUpToken: token });
      setKycResult(result.data); form.reset(); await refresh("establishment-kyc");
      return `${kind} verification completed.`;
    });
  }
  function addBranch(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    void run(async () => {
      const result = await command<Envelope<Branch>>("POST", `${base}/branches`, { name: text(f, "name"), kind: text(f, "kind"),
        address: { line: text(f, "line"), city: text(f, "city"), district: text(f, "district"), pincode: text(f, "pincode") } });
      form.reset(); await refresh("establishment-branches", "establishment-config");
      return `Branch ${result.data.sub_code} added.`;
    });
  }
  function updatePerson(id: number, field: keyof Omit<PersonDraft, "id">, value: string) {
    setPersons((current) => current.map((person) => person.id === id ? { ...person, [field]: value } : person));
  }
  function signForm5A(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    void run(async () => {
      const id = requireId();
      if (persons.reduce((sum, person) => sum + Number(person.share_pct), 0) > 100) throw new Error("Shares cannot exceed 100% in total.");
      const token = await stepUp.ask({ action: "sign-form-5a", resourceId: id, summary: "Sign Form 5A with DSC / e-sign (mock)" });
      if (!token) return null;
      const result = await command<Envelope<Form5A>>("PUT", `${base}/ownership-declaration`, {
        nature_of_business: text(f, "nature_of_business"),
        persons: persons.map(({ name, designation, role, pan, share_pct }) => ({ name: name.trim(), designation: designation.trim(),
          role, pan: pan.trim().toUpperCase(), share_pct: Number(share_pct) })) }, { stepUpToken: token });
      form.reset(); setPersons([{ id: nextPersonId.current++, name: "", designation: "", role: "PROPRIETOR", pan: "", share_pct: "0" }]);
      await refresh("establishment-form5a");
      return `Form 5A version ${result.data.version} filed.`;
    });
  }
  function addContractor(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    void run(async () => {
      const from = text(f, "valid_from"), to = text(f, "valid_to");
      if (to && to < from) throw new Error("The end date must be on or after the start date.");
      const result = await command<Envelope<Contractor>>("POST", `${base}/contractors`, {
        registration_number: text(f, "registration_number"), name: text(f, "name"), work_order_ref: text(f, "work_order_ref"),
        valid_from: from, ...(to ? { valid_to: to } : {}) });
      form.reset(); await refresh("establishment-contractors");
      return `Contractor ${result.data.registration_number} added.`;
    });
  }
  function requestCoverage(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    void run(async () => {
      const id = requireId();
      const token = await stepUp.ask({ action: "request-establishment-change", resourceId: id, summary: `Request voluntary coverage for ${id}.` });
      if (!token) return null;
      const result = await command<Envelope<ChangeRequest>>("POST", "/api/v1/employers/voluntary-coverage-requests", {
        employees: Number(text(f, "employees")), employees_consenting: Number(text(f, "employees_consenting")),
        effective_from: text(f, "effective_from"), reason: text(f, "reason") }, { stepUpToken: token });
      form.reset(); await refresh("establishment-changes"); return `Change request ${result.data.request_id} submitted.`;
    });
  }
  function requestClosure(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    void run(async () => {
      const id = requireId();
      const token = await stepUp.ask({ action: "request-closure", resourceId: id, summary: `Request closure of ${id}.` });
      if (!token) return null;
      const result = await command<Envelope<ChangeRequest>>("POST", `${base}/closure-requests`, {
        closed_on: text(f, "closed_on"), reason: text(f, "reason"), last_wage_month: text(f, "last_wage_month"), note: text(f, "note") },
      { stepUpToken: token });
      form.reset(); await refresh("establishment-changes"); return `Change request ${result.data.request_id} submitted.`;
    });
  }
  function requestTransfer(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    void run(async () => {
      const id = requireId();
      const token = await stepUp.ask({ action: "request-office-transfer", resourceId: id, summary: `Request office transfer for ${id}.` });
      if (!token) return null;
      const result = await command<Envelope<ChangeRequest>>("POST", `${base}/office-transfer-requests`, {
        to_office_id: text(f, "to_office_id"), effective_from: text(f, "effective_from"), reason: text(f, "reason") },
      { stepUpToken: token });
      form.reset(); await refresh("establishment-changes"); return `Change request ${result.data.request_id} submitted.`;
    });
  }

  return <section className="stack" aria-labelledby="establishment-heading">
    <PageHeader id="establishment-heading" eyebrow="Employer services" title="Establishment" current="Establishment"
      description="View establishment details, KYC, bank accounts, branches, ownership and contractors. Changes to the record go to the regional office." />
    <ProblemMessage error={error ?? loadError} />
    {notice ? <p role="status" className="ok">{notice}</p> : null}

    <section className="card stack" aria-labelledby="est-config-heading"><h2 id="est-config-heading">Configuration</h2>
      {config.data ? <Facts rows={[["Coverage type", statusLabel(config.data.data.coverage_type, t)], ["Coverage date", config.data.data.coverage_date],
        ["Exemption status", statusLabel(config.data.data.exemption_status, t)], ["Establishment type", config.data.data.establishment_type],
        ["Industry group", config.data.data.industry_group], ["Jurisdiction office", config.data.data.jurisdiction_office],
        ["Schemes", config.data.data.schemes.join(", ")], ["Sub codes", config.data.data.sub_codes.join(", ")],
        ["Address", [config.data.data.address?.line, config.data.data.address?.city, config.data.data.address?.district,
          config.data.data.address?.pincode].filter(Boolean).join(", ")], ["Email", config.data.data.address?.email],
        ["Phone", config.data.data.address?.phone]]} /> : null}
      {canChange ? <>
        <form className="stack" aria-labelledby="config-change-heading" onSubmit={requestConfig}><h3 id="config-change-heading">Ask for a configuration change</h3>
          <div className="form-row"><label>Field<select name="field"><option value="establishment_type">Establishment type</option>
            <option value="industry_group">Industry group</option></select></label>
            <label>New value<input name="value" required minLength={3} maxLength={120} /></label></div>
          <label>Reason<input name="reason" required minLength={10} maxLength={500} /></label>
          <div className="actions"><button type="submit" className="primary" disabled={!establishmentId}>Submit request</button></div>
        </form>
        <form className="stack" aria-labelledby="contact-change-heading" onSubmit={requestContact}><h3 id="contact-change-heading">Change address / contact</h3>
          <p className="muted small">If changing the address, complete all four address fields. Leave other fields empty to keep them as they are.</p>
          <div className="form-row"><label>Address line<input name="line" /></label><label>City<input name="city" /></label>
            <label>District<input name="district" /></label><label>Pincode<input name="pincode" pattern="[0-9]{6}" inputMode="numeric" /></label></div>
          <div className="form-row"><label>Email<input name="email" type="email" /></label>
            <label>Phone<input name="phone" pattern="[0-9]{10}" inputMode="numeric" /></label></div>
          <label>Reason<input name="reason" required minLength={10} maxLength={500} /></label>
          <div className="actions"><button type="submit" className="primary" disabled={!establishmentId}>Submit request</button></div>
        </form>
      </> : null}
      <h3>Your change requests</h3>
      {changes.data?.data.length ? <ul className="plain-list">{changes.data.data.map((request) => <li key={request.request_id}>
        <strong>{request.request_id}</strong> · {statusLabel(request.kind, t)} <span className="state-pill">{statusLabel(request.state, t)}</span>
        <ul>{Object.entries(request.changes).map(([field, value]) => <li key={field}>{field.replaceAll("_", " ")}: {show(value.from)} → {show(value.to)}</li>)}</ul>
        <p className="small">Reason: {request.reason}{request.decision_note ? ` · Decision note: ${request.decision_note}` : ""}</p>
      </li>)}</ul> : changes.data ? <p className="muted">No change requests.</p> : null}
    </section>

    {role === "employer.signatory" ? <section className="card stack" aria-labelledby="coverage-office-heading"><h2 id="coverage-office-heading">Coverage, closure and office</h2>
      <form className="stack lifecycle-form" aria-label="Request voluntary coverage" onSubmit={requestCoverage}><h3>Voluntary coverage under section 1(4)</h3>
        <p className="muted small">Illustrative rule: fewer than 20 employees and consent from a majority of employees.</p>
        <div className="form-row"><label>Employees<input name="employees" type="number" min="1" required /></label>
          <label>Employees consenting<input name="employees_consenting" type="number" min="0" required /></label>
          <label>Effective from<input name="effective_from" type="date" required /></label></div>
        <label>Reason<input name="reason" required minLength={10} maxLength={500} /></label>
        <div className="actions"><button type="submit" className="primary">Request voluntary coverage</button></div></form>
      <form className="stack lifecycle-form" aria-label="Request closure" onSubmit={requestClosure}><h3>Closure</h3>
        <div className="form-row"><label>Closed on<input name="closed_on" type="date" required /></label>
          <label>Reason<select name="reason"><option value="CLOSED">{statusLabel("CLOSED", t)}</option>
            <option value="BUSINESS_DISCONTINUED">{statusLabel("BUSINESS_DISCONTINUED", t)}</option>
            <option value="MERGED">{statusLabel("MERGED", t)}</option></select></label>
          <label>Last wage month<input name="last_wage_month" type="month" required /></label></div>
        <label>Note<input name="note" required minLength={3} maxLength={500} /></label>
        <div className="actions"><button type="submit" className="primary" disabled={!establishmentId}>Request closure</button></div></form>
      <form className="stack lifecycle-form" aria-label="Request office transfer" onSubmit={requestTransfer}><h3>Office transfer</h3>
        <div className="form-row"><label>To office<select name="to_office_id" required>
          {["RO-DEMO-01", "RO-DEMO-02"].filter((office) => office !== config.data?.data.jurisdiction_office).map((office) =>
            <option key={office} value={office}>{office}</option>)}</select></label>
          <label>Effective from<input name="effective_from" type="date" required /></label></div>
        <label>Reason<input name="reason" required minLength={5} maxLength={500} /></label>
        <div className="actions"><button type="submit" className="primary" disabled={!establishmentId || !config.data}>Request office transfer</button></div></form>
    </section> : null}

    <section className="card stack" aria-labelledby="est-kyc-heading"><h2 id="est-kyc-heading">KYC</h2>
      {kyc.data ? <><p className="muted small">{kyc.data.data.note}</p><div className="table-scroll"><table><thead><tr>
        <th scope="col">Type</th><th scope="col">Value</th><th scope="col">Status</th><th scope="col">Reference</th>
      </tr></thead><tbody>{(["PAN", "GSTIN", "TAN", "CIN", "LIN"] as KycType[]).map((kind) => <tr key={kind}>
        <th scope="row">{kind}</th><td>{show(kyc.data.data.kyc[kind]?.value)}</td><td>{statusLabel(kyc.data.data.kyc[kind]?.status, t)}</td>
        <td>{show(kyc.data.data.kyc[kind]?.reference)}</td></tr>)}</tbody></table></div></> : null}
      {canChange ? <form className="stack" aria-labelledby="seed-kyc-heading" onSubmit={seedKyc}><h3 id="seed-kyc-heading">Verify a KYC identifier</h3>
        <div className="form-row"><label>Type<select name="type">{(["PAN", "GSTIN", "TAN", "CIN", "LIN"] as KycType[]).map((kind) =>
          <option key={kind} value={kind}>{kind}</option>)}</select></label>
          <label>Value<input name="value" required minLength={5} maxLength={30} /></label></div>
        <div className="actions"><button type="submit" className="primary" disabled={!establishmentId}>Verify</button></div></form> : null}
      {kycResult ? <p role="status" className={kycResult.result === "VERIFIED" ? "ok" : "pending-notice"}>
        {statusLabel(kycResult.result, t)}: {kycResult.reason} Reference: {kycResult.reference}</p> : null}
    </section>

    <section className="card stack" aria-labelledby="est-bank-heading"><h2 id="est-bank-heading">Bank accounts</h2>
      {banks.data?.data.length ? <div className="table-scroll"><table><thead><tr><th scope="col">Bank</th><th scope="col">IFSC</th>
        <th scope="col">Account</th><th scope="col">Purpose</th><th scope="col">Verified</th></tr></thead><tbody>
        {banks.data.data.map((bank) => <tr key={bank.account_id}><td>{bank.bank}</td><td>{bank.ifsc}</td>
          <td>•••• {bank.account_last4}</td><td>{bank.purpose}</td><td>{show(bank.verified)}</td></tr>)}</tbody></table></div>
        : banks.data ? <p className="muted">No bank accounts recorded.</p> : null}
      <h3>Exemption</h3>{exemption.data ? <Facts rows={[["Status", statusLabel(exemption.data.data.exemption_status, t)],
        ["Exempted", exemption.data.data.exempted], ["Note", exemption.data.data.note]]} /> : null}
    </section>

    <section className="card stack" aria-labelledby="est-branches-heading"><h2 id="est-branches-heading">Branches (Form 2A)</h2>
      {branches.data?.data.length ? <div className="table-scroll"><table><thead><tr><th scope="col">Sub code</th><th scope="col">Name</th>
        <th scope="col">Kind</th><th scope="col">Address</th></tr></thead><tbody>{branches.data.data.map((branch) => <tr key={branch.branch_id}>
          <td>{branch.sub_code}</td><td>{branch.name}</td><td>{branch.kind}</td><td>{[branch.address.line, branch.address.city,
            branch.address.district, branch.address.pincode].join(", ")}</td></tr>)}</tbody></table></div>
        : branches.data ? <p className="muted">No branches recorded.</p> : null}
      {canChange ? <form className="stack" aria-labelledby="add-branch-heading" onSubmit={addBranch}><h3 id="add-branch-heading">Add a branch or department</h3>
        <div className="form-row"><label>Name<input name="name" required minLength={3} /></label><label>Kind<select name="kind">
          <option value="BRANCH">Branch</option><option value="DEPARTMENT">Department</option></select></label></div>
        <div className="form-row"><label>Address line<input name="line" required minLength={3} /></label>
          <label>City<input name="city" required minLength={2} /></label><label>District<input name="district" required minLength={2} /></label>
          <label>Pincode<input name="pincode" required pattern="[0-9]{6}" inputMode="numeric" /></label></div>
        <div className="actions"><button type="submit" className="primary">Add</button></div></form> : null}
    </section>

    <section className="card stack" aria-labelledby="est-form5a-heading"><h2 id="est-form5a-heading">Form 5A</h2>
      {form5a.data?.data.filed ? <><Facts rows={[["Version", form5a.data.data.version],
        ["Nature of business", form5a.data.data.nature_of_business], ["Earlier versions", form5a.data.data.earlier_versions]]} />
        <div className="table-scroll"><table><thead><tr><th scope="col">Name</th><th scope="col">Designation</th><th scope="col">Role</th>
          <th scope="col">PAN</th><th scope="col">Share</th></tr></thead><tbody>{form5a.data.data.persons?.map((person, index) => <tr key={index}>
            <td>{person.name}</td><td>{person.designation}</td><td>{person.role}</td><td>{person.pan}</td><td>{person.share_pct}%</td>
          </tr>)}</tbody></table></div></> : form5a.data ? <p className="muted">{form5a.data.data.note}</p> : null}
      {canChange ? <form className="stack" aria-labelledby="file-form5a-heading" onSubmit={signForm5A}><h3 id="file-form5a-heading">File a new Form 5A version</h3>
        <p className="muted small">Enter each person's full PAN for this filing. Previously filed PANs are masked above.</p>
        <label>Nature of business<input name="nature_of_business" required minLength={3} maxLength={200} /></label>
        {persons.map((person, index) => <div key={person.id} className="stack"><h4>Person {index + 1}</h4>
          <div className="form-row"><label>Name<input required minLength={2} value={person.name} onChange={(e) => updatePerson(person.id, "name", e.target.value)} /></label>
            <label>Designation<input required minLength={2} value={person.designation} onChange={(e) => updatePerson(person.id, "designation", e.target.value)} /></label>
            <label>Role<select value={person.role} onChange={(e) => updatePerson(person.id, "role", e.target.value)}>
              {["PROPRIETOR", "PARTNER", "DIRECTOR", "MANAGER", "OCCUPIER"].map((roleOption) => <option key={roleOption} value={roleOption}>{roleOption}</option>)}</select></label>
            <label>PAN<input required pattern="[A-Z]{5}[0-9]{4}[A-Z]" value={person.pan} onChange={(e) => updatePerson(person.id, "pan", e.target.value.toUpperCase())} /></label>
            <label>Share (%)<input required type="number" min={0} max={100} step="0.01" value={person.share_pct}
              onChange={(e) => updatePerson(person.id, "share_pct", e.target.value)} /></label></div>
          {persons.length > 1 ? <div className="actions"><button type="button" onClick={() => setPersons((current) => current.filter((row) => row.id !== person.id))}>
            Remove person {index + 1}</button></div> : null}</div>)}
        <div className="actions"><button type="button" onClick={() => setPersons((current) => [...current,
          { id: nextPersonId.current++, name: "", designation: "", role: "PROPRIETOR", pan: "", share_pct: "0" }])}>Add person</button>
          <button type="submit" className="primary" disabled={!establishmentId}>Sign and file</button></div></form> : null}
    </section>

    <section className="card stack" aria-labelledby="est-contractors-heading"><h2 id="est-contractors-heading">Contractors (principal employer)</h2>
      {contractors.data?.data.length ? <div className="table-scroll"><table><thead><tr><th scope="col">Registration</th><th scope="col">Name</th>
        <th scope="col">EPFO registered</th><th scope="col">Work order</th><th scope="col">Valid from</th><th scope="col">Valid to</th><th scope="col">Compliance</th>
      </tr></thead><tbody>{contractors.data.data.map((contractor) => <tr key={contractor.contractor_id}>
        <td>{contractor.registration_number}</td><td>{contractor.name}</td><td>{show(contractor.registered_with_epfo)}</td>
        <td>{contractor.work_order_ref}</td><td>{contractor.valid_from}</td><td>{show(contractor.valid_to)}</td>
        <td>{contractor.registered_with_epfo && contractor.establishment_id ? <button type="button" onClick={() => {
          setComplianceId(contractor.establishment_id);
          if (complianceId === contractor.establishment_id) void qc.invalidateQueries({ queryKey: ["contractor-compliance", complianceId] });
        }}>Compliance</button> : "—"}</td></tr>)}</tbody></table></div>
        : contractors.data ? <p className="muted">No contractors recorded.</p> : null}
      {complianceId ? <div className="stack" aria-label={`Compliance for ${complianceId}`}><h3>Compliance · {complianceId}</h3>
        <ProblemMessage error={compliance.error} />
        {compliance.isLoading ? <p role="status">Loading compliance…</p> : null}
        {compliance.data ? <><p className="muted small">{compliance.data.data.note}</p><div className="table-scroll"><table aria-label="Compliance months">
          <thead><tr><th scope="col">Wage month</th><th scope="col">Members</th><th scope="col">EPF wages</th>
            <th scope="col">Contribution</th><th scope="col">Work order</th><th scope="col">Payment</th></tr></thead>
          <tbody>{compliance.data.data.months.map((month) => <tr key={`${month.filing_id}-${month.work_order_ref}`} className={month.paid ? "" : "compliance-unpaid"}>
            <th scope="row">{month.wage_month}</th><td>{month.members}</td><td>{rupees(month.epf_wages_paise)}</td>
            <td>{rupees(month.contribution_paise)}</td><td>{month.work_order_ref}</td>
            <td><span className="state-pill">{month.paid ? "Paid" : "Unpaid"}</span></td></tr>)}</tbody></table></div></> : null}</div> : null}
      {owner ? <form className="stack" aria-labelledby="add-contractor-heading" onSubmit={addContractor}><h3 id="add-contractor-heading">Add a contractor</h3>
        <div className="form-row"><label>Registration number<input name="registration_number" required minLength={5} /></label>
          <label>Name<input name="name" required minLength={3} /></label><label>Work order reference<input name="work_order_ref" required minLength={3} /></label></div>
        <div className="form-row"><label>Valid from<input name="valid_from" type="date" required /></label>
          <label>Valid to (optional)<input name="valid_to" type="date" /></label></div>
        <div className="actions"><button type="submit" className="primary">Add contractor</button></div></form> : null}
    </section>
    <EsignList canManage={role === "employer.owner"} />
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </section>;
}
