import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";

import { api, getCurrentPolicy, type CurrentPolicy, command, newIdempotencyKey, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

type FilingState = "DRAFT" | "VALIDATION_FAILED" | "VALIDATED" | "APPROVED" | "SUBMITTED" | "PAYMENT_PENDING" | "PAYMENT_CONFIRMED" | "PAYMENT_FAILED" | "POSTED" | "SUPERSEDED";

interface Establishment {
  legal_name: string;
  status: string;
  your_permissions: string[];
}

interface Filing {
  filing_id: string;
  wage_month: string;
  type: string;
  version: number;
  state: FilingState;
  rule_version: string;
  trrn: string | null;
  validation_report?: ValidationReport | string | null;
}

interface ValidationIssue {
  row: number;
  field: string;
  code: string;
  severity: "error" | "warning";
  message: string;
  fix?: string;
  uan_masked?: string;
}

interface ValidationReport {
  valid: boolean;
  summary: {
    rows: number;
    accepted_rows: number;
    warnings: number;
    totals_paise: { TOTAL: number };
  };
  issues: ValidationIssue[];
  corrected_content?: string | null;
}

interface Challan {
  trrn: string;
  total_paise: number;
  status: string;
}

const HEADER = "UAN,Member Name,Gross Wages,EPF Wages,EPS Wages,EDLI Wages,EPF Contribution (EE share),EPS Contribution,EPF-EPS Difference (ER share),NCP Days,Refund of Advances";

/** A synthetic sample that is correct under the rules in force: ₹20,000 wages, capped at the current ceilings. */
function sampleCsv(policy: CurrentPolicy | undefined): string {
  const c = policy?.contribution ?? { epf_employee_rate_bp: 1200, eps_rate_bp: 833, eps_wage_ceiling_paise: 1500000, edli_wage_ceiling_paise: 1500000 };
  const gross = 20000;
  const epf = Math.min(gross, c.eps_wage_ceiling_paise / 100);
  const eps = epf;
  const edli = Math.min(gross, c.edli_wage_ceiling_paise / 100);
  const ee = Math.round((epf * c.epf_employee_rate_bp) / 10000);
  const epsShare = Math.round((eps * c.eps_rate_bp) / 10000);
  const line = (uan: string, name: string) => [uan, name, gross, epf, eps, edli, ee, epsShare, ee - epsShare, 0, 0].join(",");
  return [HEADER, line("100000000001", "ASHA DEMO"), line("100000000002", "BHARAT DEMO")].join("\n");
}

function reportOf(value: Filing["validation_report"]): ValidationReport | null {
  if (!value) return null;
  if (typeof value !== "string") return value;
  try {
    return JSON.parse(value) as ValidationReport;
  } catch {
    return null;
  }
}

export function EcrPage() {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const retryKeys = useRef<Record<string, string>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [wageMonth, setWageMonth] = useState("2026-08");
  const [format, setFormat] = useState<"CSV" | "ECR_TXT">("CSV");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [paymentScenario, setPaymentScenario] = useState<"SUCCESS" | "RETURN">("SUCCESS");

  const policy = useQuery({ queryKey: ["current-policy"], queryFn: getCurrentPolicy, retry: false });
  const establishment = useQuery({
    queryKey: ["employer-me"],
    queryFn: () => api<Envelope<Establishment>>("/api/v1/employers/me"),
    retry: false,
  });
  const grants = establishment.data?.data.your_permissions ?? [];
  const canPrepare = grants.includes("ecr.prepare");
  const canApprove = grants.includes("ecr.approve");
  const canSubmit = grants.includes("ecr.submit");
  const canPay = grants.includes("payment.initiate");
  const canReadFilings = canPrepare || canApprove || canSubmit;

  const filings = useQuery({
    queryKey: ["ecr-filings"],
    queryFn: () => api<Envelope<Filing[]>>("/api/v1/employers/me/ecr-filings"),
    enabled: canReadFilings,
    retry: false,
  });
  const currentId = selectedId ?? filings.data?.data[0]?.filing_id ?? null;
  const detail = useQuery({
    queryKey: ["ecr-filing", currentId],
    queryFn: () => api<Envelope<Filing>>(`/api/v1/employers/me/ecr-filings/${currentId}`),
    enabled: !!currentId && canReadFilings,
    retry: false,
  });
  const challans = useQuery({
    queryKey: ["challans"],
    queryFn: () => api<Envelope<Challan[]>>("/api/v1/employers/me/challans"),
    enabled: canPay,
    retry: false,
  });
  const filing = detail.data?.data;
  const report = reportOf(filing?.validation_report);

  function keyFor(action: string) {
    return (retryKeys.current[action] ??= newIdempotencyKey());
  }

  async function run(action: string, work: () => Promise<unknown>, success: string) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await work();
      delete retryKeys.current[action];
      await qc.invalidateQueries({ queryKey: ["ecr-filings"] });
      await qc.invalidateQueries({ queryKey: ["ecr-filing"] });
      await qc.invalidateQueries({ queryKey: ["challans"] });
      setNotice(success);
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(false);
    }
  }

  async function loadFile(file: File | undefined) {
    if (!file) return;
    try {
      setContent(await file.text());
      setFormat(file.name.toLowerCase().endsWith(".csv") ? "CSV" : "ECR_TXT");
      setError(null);
    } catch (cause) {
      setError(cause);
    }
  }

  async function create(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!content.trim()) {
      setError(new Error("Choose a file or paste ECR content first."));
      return;
    }
    await run("create", async () => {
      const result = await command<Envelope<{ filing: Filing }>>("POST", "/api/v1/employers/me/ecr-filings", {
        wage_month: wageMonth, type: "REGULAR", format, content,
      });
      setSelectedId(result.data.filing.filing_id);
    }, "Return created. Review the validation report before asking the signatory to approve it.");
  }

  async function validateAgain() {
    if (!filing) return;
    await run("validate", () => command("POST", `/api/v1/employers/me/ecr-filings/${filing.filing_id}/validations`),
      "Validation complete. Review the updated report.");
  }

  async function approve() {
    if (!filing || !report) return;
    const token = await stepUp.ask({
      action: "approve-ecr", resourceId: filing.filing_id, resourceVersion: filing.version,
      amountPaise: report.summary.totals_paise.TOTAL,
      summary: `Approve the ${filing.wage_month} return, version ${filing.version}`,
    });
    if (!token) return;
    await run("approve", () => command("POST", `/api/v1/employers/me/ecr-filings/${filing.filing_id}/approvals`,
      { decision: "APPROVE" }, { stepUpToken: token }), "Return approved. It is ready for submission.");
  }

  async function submit() {
    if (!filing || !report) return;
    const token = await stepUp.ask({
      action: "submit-ecr", resourceId: filing.filing_id, resourceVersion: filing.version,
      amountPaise: report.summary.totals_paise.TOTAL,
      summary: `Submit the ${filing.wage_month} return and generate a TRRN`,
    });
    if (!token) return;
    await run(`submit:${filing.filing_id}`, () => command("POST",
      `/api/v1/employers/me/ecr-filings/${filing.filing_id}/submissions`, undefined,
      { stepUpToken: token, ifMatch: filing.version, idempotencyKey: keyFor(`submit:${filing.filing_id}`) }),
    "Return submitted. The challan may take a few seconds to appear in the mock payment service.");
  }

  async function pay(challan: Challan) {
    const token = await stepUp.ask({
      action: "pay-challan", resourceId: challan.trrn, amountPaise: challan.total_paise,
      summary: `Start a simulated bank payment for challan ${challan.trrn}`,
    });
    if (!token) return;
    await run(`pay:${challan.trrn}`, () => command("POST",
      `/api/v1/employers/me/challans/${challan.trrn}/payment-intents`,
      { channel: "NET_BANKING", demo_scenario: paymentScenario },
      { stepUpToken: token, idempotencyKey: keyFor(`pay:${challan.trrn}`) }),
    "Mock payment started. Refresh challans to see the bank result.");
  }

  if (establishment.isLoading || establishment.error) return <div className="stack">
    <PageHeader eyebrow="Monthly returns · Journey A" title="ECR workbench"
      description="Prepare and track synthetic monthly returns." current="Monthly returns (ECR)"
      parent={{ label: "Employer workspace", to: "/employer" }} />
    {establishment.isLoading ? <p role="status">Loading employer workspace…</p> : <ProblemMessage error={establishment.error} />}
  </div>;

  return (
    <section className="stack" aria-labelledby="ecr-heading">
      <PageHeader id="ecr-heading" eyebrow="Monthly returns · Journey A" title="ECR workbench"
        description={`${establishment.data?.data.legal_name} · synthetic demonstration · illustrative contribution rules`}
        current="Monthly returns (ECR)" parent={{ label: "Employer workspace", to: "/employer" }}>
        <button type="button" onClick={() => void qc.invalidateQueries()} disabled={busy}>Refresh status</button>
      </PageHeader>
      {notice ? <p role="status" className="ok">{notice}</p> : null}
      <ProblemMessage error={error} />
      {!canPrepare && !canReadFilings && !canPay ? <p className="card">This persona has no return or payment grant. The establishment owner can assign a payroll operator or signatory from the employer workspace.</p> : null}

      {canPrepare ? (
        <form className="card stack" onSubmit={create}>
          <p className="eyebrow">01 · Payroll operator</p>
          <h2>Prepare a regular return</h2>
          <p className="muted">Upload an 11 field CSV or ECR TXT file. The service checks each member and explains any errors.</p>
          <div className="form-row">
            <label>Wage month <input type="month" value={wageMonth} onChange={(e) => setWageMonth(e.target.value)} required /></label>
            <label>File format <select value={format} onChange={(e) => setFormat(e.target.value as "CSV" | "ECR_TXT")}><option value="CSV">CSV</option><option value="ECR_TXT">ECR TXT</option></select></label>
          </div>
          <label>ECR file <input type="file" accept=".csv,.txt,text/csv,text/plain" onChange={(e) => void loadFile(e.target.files?.[0])} /></label>
          <label>Or paste file content <textarea rows={6} value={content} onChange={(e) => setContent(e.target.value)} spellCheck={false} /></label>
          <div className="actions">
            <button type="button" onClick={() => { setContent(sampleCsv(policy.data?.data)); setFormat("CSV"); setWageMonth("2026-08"); }}>Load synthetic sample</button>
            <button className="primary" type="submit" disabled={busy || !content.trim()}>Create and validate return</button>
          </div>
          <p className="muted small">The sample uses two synthetic members and the ceilings in force ({policy.data ? `rules ${policy.data.data.rule_version}, EPS ceiling ${rupees(policy.data.data.contribution.eps_wage_ceiling_paise)}` : "loading rules"}). The other seeded members appear as warnings, so the operator can review them.</p>
        </form>
      ) : null}

      {canReadFilings ? (
        <div className="card stack">
          <p className="eyebrow">{canPrepare ? "02 · Validation" : "02 · Signatory review"}</p>
          <h2>Returns</h2>
          <ProblemMessage error={filings.error} />
          {filings.isLoading ? <p>Loading returns…</p> : null}
          {filings.data?.data.length === 0 ? <p className="muted">No returns have been created for this establishment.</p> : null}
          {filings.data?.data.length ? (
            <label>Choose a return
              <select value={currentId ?? ""} onChange={(e) => setSelectedId(e.target.value)}>
                {filings.data.data.map((item) => <option key={item.filing_id} value={item.filing_id}>{item.wage_month} · v{item.version} · {item.state}</option>)}
              </select>
            </label>
          ) : null}
          <ProblemMessage error={detail.error} />
          {filing ? (
            <div className="filing-detail">
              <div className="detail-head"><strong>{filing.wage_month}</strong><span className="state-pill">{filing.state.replaceAll("_", " ")}</span></div>
              <p className="muted small">Version {filing.version} · rule set {filing.rule_version} · {filing.filing_id}</p>
              {filing.trrn ? <p>TRRN <code>{filing.trrn}</code></p> : null}
              {report ? (
                <>
                  <div className="metrics">
                    <div><span>Rows</span><strong>{report.summary.rows}</strong></div>
                    <div><span>Accepted</span><strong>{report.summary.accepted_rows}</strong></div>
                    <div><span>Warnings</span><strong>{report.summary.warnings}</strong></div>
                    <div><span>Illustrative total</span><strong>{rupees(report.summary.totals_paise.TOTAL)}</strong></div>
                  </div>
                  <p className={report.valid ? "ok" : "problem"}>{report.valid ? "Validation passed. Review warnings before approval." : "Validation found errors. Correct the file and create a new version."}</p>
                  {report.issues.length ? <ul className="issue-list">{report.issues.map((issue, index) => (
                    <li key={`${issue.row}-${issue.code}-${index}`}><strong>{issue.severity.toUpperCase()} · {issue.code}</strong> Row {issue.row || "all"}{issue.uan_masked ? ` · ${issue.uan_masked}` : ""}: {issue.message}{issue.fix ? <span className="muted"> {issue.fix}</span> : null}</li>
                  ))}</ul> : null}
                </>
              ) : null}
              <div className="actions">
                {canPrepare && ["DRAFT", "VALIDATION_FAILED", "VALIDATED"].includes(filing.state) ? <button type="button" disabled={busy} onClick={() => void validateAgain()}>Validate again</button> : null}
                {canApprove && filing.state === "VALIDATED" && report?.valid ? <button type="button" className="primary" disabled={busy} onClick={() => void approve()}>Approve with confirmation</button> : null}
                {canSubmit && filing.state === "APPROVED" && report ? <button type="button" className="primary" disabled={busy} onClick={() => void submit()}>Submit and generate TRRN</button> : null}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      {canPay ? (
        <div className="card stack">
          <p className="eyebrow">03 · Authorised signatory</p>
          <h2>Challans and mock bank</h2>
          <p className="muted">A submitted return creates a challan. Payments here are simulated; no funds move.</p>
          <ProblemMessage error={challans.error} />
          <label>Demo bank outcome
            <select value={paymentScenario} onChange={(e) => { setPaymentScenario(e.target.value as "SUCCESS" | "RETURN"); retryKeys.current = {}; }}>
              <option value="SUCCESS">Confirm payment</option>
              <option value="RETURN">Return payment</option>
            </select>
          </label>
          {challans.data?.data.length === 0 ? <p className="muted">No challans yet. Submit a return, then refresh.</p> : null}
          {challans.data?.data.map((challan) => (
            <div className="challan" key={challan.trrn}>
              <div><strong>{challan.trrn}</strong><p className="muted small">{challan.status} · {rupees(challan.total_paise)}</p></div>
              {["DUE", "FAILED"].includes(challan.status) ? <button type="button" className="primary" disabled={busy} onClick={() => void pay(challan)}>Pay with mock bank</button> : null}
            </div>
          ))}
        </div>
      ) : null}
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}
