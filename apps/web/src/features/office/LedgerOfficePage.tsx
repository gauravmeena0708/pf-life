import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";
import { PastAccumulationReco } from "./PastAccumulationReco";

interface Allocation { trrn: string; amount_paise: number; at: string }
interface Receipt {
  vdr_id: string; establishment_id: string; instrument: string; instrument_ref: string;
  amount_paise: number; allocated_paise: number; unallocated_paise: number;
  received_on: string; state: string; allocations: Allocation[]; remarks: string | null;
}
interface UnpaidChallan { trrn: string; establishment_id: string; total_paise: number; status: string; kind: string }
interface ReceiptData { receipts: Receipt[]; unpaid_challans: UnpaidChallan[] }
interface AdjustmentLine { account_code: string; side: string; amount_paise: number; share?: string }
interface Adjustment {
  adjustment_id: string; account_link_id: string; uan: string; appendix_type: string;
  lines: AdjustmentLine[]; notesheet_no: string; notesheet_date: string; remarks: string;
  state: "PROPOSED" | "APPROVED" | "REJECTED"; decision_note: string | null; journal_id: string | null;
}
interface RecreditResult { journal_id: string; recredited_to: string }

const appendixTypes = {
  OTHER: "Other Appendix E (employer, employee and EPS balances)",
  INTEREST_ON_RETURNS: "Transfer-in / MO / ECS / NEFT / cheque return interest (employee and employer, not EPS)",
  EPS_DIVERSION: "Transfer of 1.16% from employer share to EPS (higher wages)",
  EXCESS_INTEREST_DEBIT: "Debiting of excess interest credited by the software",
} as const;
type AppendixType = keyof typeof appendixTypes;

const field = (data: FormData, name: string) => String(data.get(name) ?? "").trim();

function amountPaise(data: FormData, name: string, allowNegative = false): number {
  const value = field(data, name);
  if (!/^-?\d+$/.test(value)) throw new Error("Enter whole rupees for each amount.");
  const paise = Number(value) * 100;
  if (!Number.isSafeInteger(paise) || (!allowNegative && paise < 0)) {
    throw new Error("Enter a valid whole-rupee amount.");
  }
  return paise;
}

function reason(data: FormData, name: string, minimum: number): string {
  const value = field(data, name);
  if (value.length < minimum) throw new Error(`Enter at least ${minimum} characters for ${name.replaceAll("_", " ")}.`);
  return value;
}

async function pdfBase64(file: File | null): Promise<string | undefined> {
  if (!file) return undefined;
  if (file.type !== "application/pdf" || file.size > 1_000_000) {
    throw new Error("Attach a PDF notesheet of at most 1 MB.");
  }
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Could not read the notesheet PDF."));
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== "string" || !result.includes(",")) {
        reject(new Error("Could not read the notesheet PDF."));
        return;
      }
      resolve(result.slice(result.indexOf(",") + 1));
    };
    reader.readAsDataURL(file);
  });
}

export function LedgerOfficePage() {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [appendixType, setAppendixType] = useState<AppendixType>("OTHER");
  const [recreditResult, setRecreditResult] = useState<RecreditResult | null>(null);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const role = session.data?.stakeholder ?? "";
  const cash = role === "fo.cash";
  const accounts = role === "fo.da_accounts";
  const apfc = role === "fo.apfc";
  const receipts = useQuery({ queryKey: ["office-unreconciled-receipts"], enabled: cash || accounts, retry: false,
    queryFn: () => api<Envelope<ReceiptData>>("/api/v1/office/receipts/unreconciled") });
  const adjustments = useQuery({ queryKey: ["office-ledger-adjustments"], enabled: accounts || apfc, retry: false,
    queryFn: () => api<Envelope<Adjustment[]>>("/api/v1/office/ledger-adjustments") });

  async function refresh() {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["office-unreconciled-receipts"] }),
      qc.invalidateQueries({ queryKey: ["office-ledger-adjustments"] }),
    ]);
  }

  async function run(work: () => Promise<string | null>) {
    setError(null); setNotice(null); setBusy(true);
    try {
      const message = await work();
      if (message) setNotice(message);
    } catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }

  function recordReceipt(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    void run(async () => {
      const establishmentId = field(data, "establishment_id");
      const instrumentRef = field(data, "instrument_ref");
      const amount = amountPaise(data, "amount");
      if (amount <= 0) throw new Error("Enter a receipt amount greater than zero.");
      const token = await stepUp.ask({ action: "record-vdr", resourceId: instrumentRef, amountPaise: amount,
        summary: `Record ${rupees(amount)} receipt ${instrumentRef} for ${establishmentId}` });
      if (!token) return null;
      await command("POST", "/api/v1/office/vdr-entries", {
        establishment_id: establishmentId, instrument: field(data, "instrument"), instrument_ref: instrumentRef,
        amount_paise: amount, received_on: field(data, "received_on"),
      }, { stepUpToken: token });
      await refresh();
      form.reset();
      return `Receipt ${instrumentRef} recorded.`;
    });
  }

  function allocate(e: FormEvent<HTMLFormElement>, receipt: Receipt) {
    e.preventDefault();
    const form = e.currentTarget;
    const trrn = field(new FormData(form), "trrn");
    void run(async () => {
      const challan = receipts.data?.data.unpaid_challans.find((item) =>
        item.trrn === trrn && item.establishment_id === receipt.establishment_id);
      if (!challan) throw new Error("Choose an unpaid TRRN for this establishment.");
      if (challan.total_paise > receipt.unallocated_paise) throw new Error("The receipt does not cover this challan.");
      const token = await stepUp.ask({ action: "adjust-trrn", resourceId: receipt.vdr_id,
        amountPaise: challan.total_paise, summary: `Allocate ${rupees(challan.total_paise)} from ${receipt.vdr_id} to ${trrn}` });
      if (!token) return null;
      await command("POST", `/api/v1/office/receipts/${encodeURIComponent(receipt.vdr_id)}/trrn-adjustments`,
        { trrn }, { stepUpToken: token });
      await refresh();
      form.reset();
      return `Receipt ${receipt.vdr_id} allocated to ${trrn}.`;
    });
  }

  function rejectReceipt(e: FormEvent<HTMLFormElement>, receipt: Receipt) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    void run(async () => {
      const rejectionReason = reason(data, "reason", 10);
      const token = await stepUp.ask({ action: "reject-vdr", resourceId: receipt.vdr_id,
        summary: `Reject receipt ${receipt.vdr_id}: ${rejectionReason}` });
      if (!token) return null;
      await command("POST", `/api/v1/office/vdr-entries/${encodeURIComponent(receipt.vdr_id)}/rejections`,
        { reason: rejectionReason }, { stepUpToken: token });
      await refresh();
      form.reset();
      return `Receipt ${receipt.vdr_id} rejected.`;
    });
  }

  function reverseJournal(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    void run(async () => {
      const journalId = field(data, "journal_id");
      const amount = amountPaise(data, "amount");
      if (amount <= 0) throw new Error("Enter the positive expected journal amount.");
      const reversalReason = reason(data, "reason", 10);
      const token = await stepUp.ask({ action: "reverse-journal", resourceId: journalId, amountPaise: amount,
        summary: `Reverse journal ${journalId}: ${reversalReason}` });
      if (!token) return null;
      const result = await command<Envelope<{ journal_id: string }>>("POST",
        `/api/v1/office/ledger-journals/${encodeURIComponent(journalId)}/reversals`,
        { reason: reversalReason }, { stepUpToken: token });
      await refresh();
      form.reset();
      return `Journal ${journalId} reversed as ${result.data.journal_id}.`;
    });
  }

  function recreditTransfer(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    setRecreditResult(null);
    void run(async () => {
      const transferId = field(data, "transfer_id");
      const amount = amountPaise(data, "amount");
      if (amount <= 0) throw new Error("Enter a positive transfer amount.");
      const recreditReason = reason(data, "reason", 10);
      const token = await stepUp.ask({ action: "recredit-transfer", resourceId: transferId, amountPaise: amount,
        summary: `Recredit transfer ${transferId}: ${recreditReason}` });
      if (!token) return null;
      const result = await command<Envelope<RecreditResult>>("POST",
        `/api/v1/office/transfers/${encodeURIComponent(transferId)}/recredits`,
        { reason: recreditReason }, { stepUpToken: token });
      await refresh();
      setRecreditResult(result.data);
      form.reset();
      return `Transfer ${transferId} recredited.`;
    });
  }

  function proposeAppendix(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    void run(async () => {
      const accountLinkId = field(data, "account_link_id");
      const employee = appendixType === "EPS_DIVERSION" ? 0 : amountPaise(data, "employee", appendixType === "OTHER");
      const employer = amountPaise(data, "employer", appendixType === "OTHER");
      const eps = appendixType === "OTHER" ? amountPaise(data, "eps", true) : 0;
      if (appendixType === "EPS_DIVERSION" && employer <= 0) throw new Error("Enter a positive amount moved to EPS.");
      if ((appendixType === "INTEREST_ON_RETURNS" || appendixType === "EXCESS_INTEREST_DEBIT") && employee + employer <= 0) {
        throw new Error("Enter a positive employee or employer amount.");
      }
      if (appendixType === "OTHER" && !employee && !employer && !eps) throw new Error("Enter an amount to adjust.");
      const remarks = reason(data, "remarks", 10);
      const attachment = data.get("notesheet_pdf");
      const notesheet = await pdfBase64(attachment instanceof File && attachment.size ? attachment : null);
      const amount = [employee, employer, eps].reduce((sum, value) => sum + Math.abs(value), 0);   // the backend binds the code to this
      const token = await stepUp.ask({ action: "propose-appendix-e", resourceId: accountLinkId, amountPaise: amount,
        summary: `Propose ${appendixTypes[appendixType]} for ${accountLinkId}` });
      if (!token) return null;
      await command("POST", "/api/v1/office/ledger-adjustments", {
        type: "APPENDIX_E", appendix_type: appendixType, account_link_id: accountLinkId,
        employee_paise: employee, employer_paise: employer, eps_paise: eps,
        notesheet_no: field(data, "notesheet_no"), notesheet_date: field(data, "notesheet_date"), remarks,
        ...(notesheet ? { notesheet_pdf_base64: notesheet } : {}),
      }, { stepUpToken: token });
      await refresh();
      form.reset(); setAppendixType("OTHER");
      return `Appendix E proposed for ${accountLinkId}.`;
    });
  }

  function decideAppendix(e: FormEvent<HTMLFormElement>, adjustment: Adjustment) {
    e.preventDefault();
    const form = e.currentTarget;
    const decision = ((e.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null)?.value;
    if (decision !== "APPROVE" && decision !== "REJECT") return;
    const data = new FormData(form);
    void run(async () => {
      const note = reason(data, "note", 5);
      const amount = adjustment.lines.filter((line) => line.side === "credit")
        .reduce((sum, line) => sum + line.amount_paise, 0);
      const token = await stepUp.ask({ action: "approve-appendix-e", resourceId: adjustment.adjustment_id,
        amountPaise: amount, summary: `${decision === "APPROVE" ? "Approve" : "Reject"} Appendix E ${adjustment.adjustment_id}` });
      if (!token) return null;
      await command("POST", `/api/v1/office/ledger-adjustments/${encodeURIComponent(adjustment.adjustment_id)}/approvals`,
        { decision, note }, { stepUpToken: token });
      await refresh();
      form.reset();
      return `Appendix E ${adjustment.adjustment_id} ${decision === "APPROVE" ? "approved" : "rejected"}.`;
    });
  }

  return <main className="stack">
    <PageHeader eyebrow="Regional office" title="Receipts and ledger" current="Ledger"
      description="Record offline receipts, correct ledger postings, and review Appendix E adjustments." />
    <ProblemMessage error={error ?? session.error ?? receipts.error ?? adjustments.error} />
    {notice ? <p role="status" className="ok">{notice}</p> : null}

    {(cash || accounts) ? <section className="card stack" aria-labelledby="vdr-heading"><h2 id="vdr-heading">Receipts outside the challan flow (VDR)</h2>
      {cash ? <form className="stack" onSubmit={recordReceipt}><h3>Record a receipt</h3>
        <div className="form-row">
          <label>Establishment ID<input name="establishment_id" defaultValue="EST-DEMO-0001" required minLength={3} maxLength={80} /></label>
          <label>Instrument<select name="instrument"><option value="CHEQUE">Cheque</option><option value="DD">Demand draft</option>
            <option value="NEFT_UNMATCHED">Unmatched NEFT</option></select></label>
          <label>Instrument reference<input name="instrument_ref" required minLength={3} maxLength={60} /></label>
          <label>Amount (₹)<input name="amount" type="number" min="1" step="1" required /></label>
          <label>Received on<input name="received_on" type="date" required /></label>
        </div>
        <div className="actions"><button type="submit" className="primary" disabled={busy}>Record receipt</button></div>
      </form> : null}
      {receipts.isLoading ? <p role="status">Loading receipts…</p> : null}
      {receipts.data?.data.receipts.length ? <div className="table-scroll"><table><thead><tr>
        <th scope="col">Receipt</th><th scope="col">Establishment</th><th scope="col">Instrument</th>
        <th scope="col">Received</th><th scope="col">Amount</th><th scope="col">Allocated</th>
        <th scope="col">Unallocated</th><th scope="col">State</th><th scope="col">Allocations</th><th scope="col">Remarks</th>
        {accounts ? <th scope="col">Action</th> : null}
      </tr></thead><tbody>{receipts.data.data.receipts.map((receipt) => {
        const challans = receipts.data.data.unpaid_challans.filter((item) => item.establishment_id === receipt.establishment_id);
        const allocatable = challans.some((item) => item.total_paise <= receipt.unallocated_paise);
        return <tr key={receipt.vdr_id}><th scope="row">{receipt.vdr_id}</th><td>{receipt.establishment_id}</td>
          <td>{receipt.instrument} · {receipt.instrument_ref}</td><td>{receipt.received_on}</td>
          <td>{rupees(receipt.amount_paise)}</td><td>{rupees(receipt.allocated_paise)}</td><td>{rupees(receipt.unallocated_paise)}</td>
          <td>{receipt.state.replaceAll("_", " ")}</td><td>{receipt.allocations.length ? <ul>{receipt.allocations.map((allocation) =>
            <li key={allocation.trrn}>{allocation.trrn}: {rupees(allocation.amount_paise)}</li>)}</ul> : "—"}</td>
          <td>{receipt.remarks ?? "—"}</td>
          {accounts ? <td><div className="stack"><form className="stack" aria-label={`Allocate receipt ${receipt.vdr_id} to TRRN`}
            onSubmit={(event) => allocate(event, receipt)}>
            <label>Unpaid TRRN<select name="trrn" required defaultValue=""><option value="">Choose a challan</option>
              {challans.map((item) => <option key={item.trrn} value={item.trrn} disabled={item.total_paise > receipt.unallocated_paise}>
                {item.trrn} · {item.kind} · {item.status} · {rupees(item.total_paise)}
              </option>)}</select></label>
            <button type="submit" disabled={busy || !allocatable}>Allocate to TRRN</button>
          </form>
          {receipt.state === "UNRECONCILED" ? <form className="stack" aria-label={`Reject receipt ${receipt.vdr_id}`}
            onSubmit={(event) => rejectReceipt(event, receipt)}>
            <label>Rejection reason<input name="reason" required minLength={10} maxLength={500} /></label>
            <button type="submit" disabled={busy}>Reject</button>
          </form> : null}</div></td> : null}
        </tr>;
      })}</tbody></table></div> : receipts.data ? <p className="muted">No unreconciled receipts.</p> : null}
    </section> : null}

    {accounts ? <section className="card stack" aria-labelledby="reversal-heading"><h2 id="reversal-heading">Reverse a posted journal / recredit a transfer</h2>
      <form className="stack" onSubmit={reverseJournal}><h3>Reverse a posted journal</h3>
        <p className="muted">Contributions, direct challans and Appendix E only.</p>
        <div className="form-row"><label>Journal ID<input name="journal_id" required /></label>
          <label>Expected amount (₹)<input name="amount" type="number" min="1" step="1" required /></label>
          <label>Reason<input name="reason" required minLength={10} maxLength={500} /></label></div>
        <div className="actions"><button type="submit" className="primary" disabled={busy}>Reverse journal</button></div>
      </form>
      <form className="stack" onSubmit={recreditTransfer}><h3>Recredit a transfer</h3>
        <div className="form-row"><label>Transfer ID<input name="transfer_id" required /></label>
          <label>Amount (₹)<input name="amount" type="number" min="1" step="1" required /></label>
          <label>Reason<input name="reason" required minLength={10} maxLength={500} /></label></div>
        <div className="actions"><button type="submit" className="primary" disabled={busy}>Recredit transfer</button></div>
      </form>
      {recreditResult ? <dl className="kv"><dt>Recredit journal</dt><dd>{recreditResult.journal_id}</dd>
        <dt>Recredited to member ID</dt><dd>{recreditResult.recredited_to}</dd></dl> : null}
    </section> : null}

    {(accounts || apfc) ? <PastAccumulationReco role={role} /> : null}
    {(accounts || apfc) ? <section className="card stack" aria-labelledby="appendix-e-heading"><h2 id="appendix-e-heading">Appendix E</h2>
      {accounts ? <form className="stack" onSubmit={proposeAppendix}><h3>Propose an adjustment</h3>
        <div className="form-row"><label>Member ID<input name="account_link_id" required minLength={3} maxLength={80} /></label>
          <label>Appendix E type<select value={appendixType} onChange={(event) => setAppendixType(event.target.value as AppendixType)}>
            {Object.entries(appendixTypes).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select></label></div>
        <div className="form-row">
          {appendixType !== "EPS_DIVERSION" ? <label>Employee (₹)<input name="employee" type="number" step="1"
            min={appendixType === "OTHER" ? undefined : "0"} defaultValue="0" required /></label> : null}
          <label>{appendixType === "EPS_DIVERSION" ? "Amount moved to EPS (₹)" : "Employer (₹)"}
            <input name="employer" type="number" step="1" min={appendixType === "OTHER" ? undefined : appendixType === "EPS_DIVERSION" ? "1" : "0"}
              defaultValue="0" required /></label>
          {appendixType === "OTHER" ? <label>EPS (₹)<input name="eps" type="number" step="1" defaultValue="0" required /></label> : null}
        </div>
        <div className="form-row"><label>Notesheet number<input name="notesheet_no" required minLength={3} maxLength={60} /></label>
          <label>Notesheet date<input name="notesheet_date" type="date" required /></label>
          <label>Notesheet PDF (optional)<input name="notesheet_pdf" type="file" accept="application/pdf,.pdf" /></label></div>
        <label>Remarks<textarea name="remarks" required minLength={10} maxLength={1000} /></label>
        <div className="actions"><button type="submit" className="primary" disabled={busy}>Propose Appendix E</button></div>
      </form> : null}
      {adjustments.isLoading ? <p role="status">Loading adjustments…</p> : null}
      {adjustments.data?.data.length ? <div className="table-scroll"><table><thead><tr>
        <th scope="col">Adjustment</th><th scope="col">Member ID / UAN</th><th scope="col">Type</th>
        <th scope="col">Journal lines</th><th scope="col">Notesheet</th><th scope="col">Remarks</th>
        <th scope="col">State</th><th scope="col">Decision note</th><th scope="col">Journal ID</th>
        {apfc ? <th scope="col">Decision</th> : null}
      </tr></thead><tbody>{adjustments.data.data.map((item) => <tr key={item.adjustment_id}>
        <th scope="row">{item.adjustment_id}</th><td>{item.account_link_id}<br />{item.uan}</td>
        <td>{appendixTypes[item.appendix_type as AppendixType] ?? item.appendix_type}</td>
        <td><ul>{item.lines.map((line, index) => <li key={`${line.account_code}-${line.side}-${index}`}>
          {line.account_code} · {line.share ? `${line.share} · ` : ""}{line.side} {rupees(line.amount_paise)}
        </li>)}</ul></td><td>{item.notesheet_no}<br />{item.notesheet_date}</td><td>{item.remarks}</td>
        <td>{item.state}</td><td>{item.decision_note ?? "—"}</td><td>{item.journal_id ?? "—"}</td>
        {apfc ? <td>{item.state === "PROPOSED" ? <form className="stack"
          aria-label={`Decide Appendix E ${item.adjustment_id}`} onSubmit={(event) => decideAppendix(event, item)}>
          <label>Decision note<input name="note" required minLength={5} maxLength={500} /></label>
          <div className="actions"><button type="submit" value="APPROVE" className="primary" disabled={busy}>Approve</button>
            <button type="submit" value="REJECT" disabled={busy}>Reject</button></div>
        </form> : "—"}</td> : null}
      </tr>)}</tbody></table></div> : adjustments.data ? <p className="muted">No Appendix E adjustments recorded.</p> : null}
    </section> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </main>;
}
