import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, getSession, newIdempotencyKey, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

export interface PreDeposit {
  amount_paise: number;
  reference: string;
  deposited_on: string;
  recorded_by?: string;
  idempotency_key?: string | null;
}

export interface LegalOrder {
  order_date: string;
  outcome: string;
  note?: string;
  revised_amount_paise?: number | null;
  percent?: number;
  reference?: string;
  recorded_by?: string;
}

export interface LegalCase {
  legal_case_id: string;
  office_id?: string;
  establishment_id: string;
  kind: "APPEAL_7I" | "WRIT" | "NCLT" | "OTHER" | "PROSECUTION";
  forum: string;
  case_no: string;
  filed_on: string;
  inquiry_case_id: string | null;
  impugned_demand_ids?: string[];
  amount_paise: number | null;
  pre_deposit_percent: number | null;
  pre_deposits: PreDeposit[] | null;
  delay_condonation: boolean | null;
  stayed: boolean;
  state: "PENDING" | "DECIDED";
  orders: LegalOrder[];
  note?: string | null;
  created_by?: string;
  created_at?: string;
  pre_deposit_required_paise?: number;
  pre_deposited_paise?: number;
  heard?: boolean;
}

const KIND_LABELS: Record<string, string> = {
  APPEAL_7I: "Appeal under 7-I",
  WRIT: "Writ",
  NCLT: "NCLT",
  PROSECUTION: "Prosecution",
  OTHER: "Other",
};

const field = (f: FormData, name: string) => String(f.get(name) ?? "").trim();

function OrderForm({
  caseItem,
  busy,
  run,
}: {
  caseItem: LegalCase;
  busy: boolean;
  run: (work: () => Promise<string | void>, ok: string, form?: HTMLFormElement) => void;
}) {
  const isProsecution = caseItem.kind === "PROSECUTION";
  const defaultOutcome = isProsecution ? "CONVICTED" : "DISMISSED";
  const [outcome, setOutcome] = useState<string>(defaultOutcome);

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    const order_date = field(f, "order_date");
    const note = field(f, "note");
    const body: Record<string, unknown> = {
      order_date,
      outcome,
      note,
    };
    if (outcome === "PARTLY_ALLOWED") {
      body.revised_amount_paise = Math.round(Number(f.get("revised_amount") || 0) * 100);
    }
    run(
      async () => {
        const res = await command<Envelope<LegalCase & { effect?: string }>>(
          "POST",
          `/api/v1/office/legal/cases/${caseItem.legal_case_id}/orders`,
          body
        );
        const effect = res?.data?.effect ?? (res as unknown as { effect?: string })?.effect;
        return effect ? `Order recorded: ${effect}.` : "Order recorded.";
      },
      "Order recorded.",
      form
    );
  }

  return (
    <form className="card stack" aria-label="Record an order" onSubmit={handleSubmit}>
      <h4>Record an order</h4>
      <div className="form-row">
        <label>
          Order date
          <input name="order_date" type="date" required />
        </label>
        <label>
          Outcome
          <select name="outcome" value={outcome} onChange={(e) => setOutcome(e.target.value)}>
            {isProsecution ? (
              <>
                <option value="CONVICTED">Convicted</option>
                <option value="ACQUITTED">Acquitted</option>
                <option value="OTHER">Other</option>
                <option value="INTERIM_STAY">Interim stay</option>
              </>
            ) : (
              <>
                <option value="INTERIM_STAY">Interim stay</option>
                <option value="STAY_VACATED">Stay vacated</option>
                <option value="DISMISSED">Dismissed</option>
                <option value="ALLOWED">Allowed</option>
                <option value="PARTLY_ALLOWED">Partly allowed</option>
                <option value="REMANDED">Remanded</option>
                <option value="OTHER">Other</option>
              </>
            )}
          </select>
        </label>
      </div>
      {outcome === "PARTLY_ALLOWED" ? (
        <label>
          Revised amount (₹)
          <input name="revised_amount" type="number" min="0" step="0.01" required />
        </label>
      ) : null}
      <label>
        Note
        <textarea name="note" required />
      </label>
      <div className="actions">
        <button className="primary" disabled={busy} type="submit">
          Record order
        </button>
      </div>
    </form>
  );
}

function PreDepositForm({
  caseItem,
  busy,
  run,
}: {
  caseItem: LegalCase;
  busy: boolean;
  run: (work: () => Promise<string | void>, ok: string, form?: HTMLFormElement) => void;
}) {
  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    const amount_paise = Math.round(Number(f.get("amount") || 0) * 100);
    const reference = field(f, "reference");
    const deposited_on = field(f, "deposited_on");
    const inquiryCaseId = caseItem.inquiry_case_id || "";

    run(
      () =>
        command(
          "POST",
          `/api/v1/office/compliance/cases/${inquiryCaseId}/appeals/${caseItem.legal_case_id}/pre-deposits`,
          { amount_paise, reference, deposited_on },
          { idempotencyKey: newIdempotencyKey() }
        ),
      "Pre-deposit recorded.",
      form
    );
  }

  return (
    <form className="card stack" aria-label="Record a pre-deposit" onSubmit={handleSubmit}>
      <h4>Record a pre-deposit</h4>
      <div className="form-row">
        <label>
          Amount (₹)
          <input name="amount" type="number" min="0.01" step="0.01" required />
        </label>
        <label>
          Reference
          <input name="reference" required minLength={4} placeholder="Challan (TRRN) or receipt ref" />
        </label>
        <label>
          Deposited on
          <input name="deposited_on" type="date" required />
        </label>
      </div>
      <div className="actions">
        <button className="primary" disabled={busy} type="submit">
          Record pre-deposit
        </button>
      </div>
    </form>
  );
}

function WaiverForm({
  caseItem,
  busy,
  run,
  ask,
}: {
  caseItem: LegalCase;
  busy: boolean;
  run: (work: () => Promise<string | void>, ok: string, form?: HTMLFormElement) => void;
  ask: (request: { action: string; resourceId: string; summary: string }) => Promise<string | null>;
}) {
  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    const percent = Number(f.get("percent"));
    const tribunal_order_ref = field(f, "tribunal_order_ref");
    const order_date = field(f, "order_date");
    const inquiryCaseId = caseItem.inquiry_case_id || "";

    const token = await ask({
      action: "record-pre-deposit-waiver",
      resourceId: caseItem.legal_case_id,
      summary: `Record pre-deposit reduction to ${percent}% for ${caseItem.case_no}`,
    });
    if (!token) return;

    run(
      () =>
        command(
          "POST",
          `/api/v1/office/compliance/cases/${inquiryCaseId}/appeals/${caseItem.legal_case_id}/pre-deposit-waivers`,
          { percent, tribunal_order_ref, order_date },
          { stepUpToken: token }
        ),
      "Pre-deposit reduction or waiver recorded.",
      form
    );
  }

  return (
    <form className="card stack" aria-label="Record the Tribunal's reduction or waiver" onSubmit={(e) => void handleSubmit(e)}>
      <h4>Record the Tribunal's reduction or waiver</h4>
      <div className="form-row">
        <label>
          Percent (%)
          <input name="percent" type="number" min="0" max="100" defaultValue={caseItem.pre_deposit_percent ?? 25} required />
        </label>
        <label>
          Tribunal order ref
          <input name="tribunal_order_ref" required minLength={3} placeholder="Order reference / number" />
        </label>
        <label>
          Order date
          <input name="order_date" type="date" required />
        </label>
      </div>
      <div className="actions">
        <button className="primary" disabled={busy} type="submit">
          Record waiver
        </button>
      </div>
    </form>
  );
}

export function LegalPage() {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [stateFilter, setStateFilter] = useState("");
  const [kindFilter, setKindFilter] = useState("");

  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  void session;

  const params = new URLSearchParams();
  if (stateFilter) params.set("state", stateFilter);
  if (kindFilter) params.set("kind", kindFilter);
  const queryPath = `/api/v1/office/legal/cases${params.toString() ? `?${params.toString()}` : ""}`;

  const casesQuery = useQuery({
    queryKey: ["legal-cases", stateFilter, kindFilter],
    queryFn: () => api<Envelope<LegalCase[]>>(queryPath),
    retry: false,
  });

  async function run(work: () => Promise<string | void>, ok: string, form?: HTMLFormElement) {
    setBusy(true);
    setError(null);
    setNotice("");
    try {
      const result = await work();
      form?.reset();
      setNotice(typeof result === "string" ? result : ok);
      await qc.invalidateQueries();
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(false);
    }
  }

  function registerAppeal(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    const caseId = field(f, "inquiry_case_id");
    const forum = field(f, "forum");
    const case_no = field(f, "case_no");
    const filed_on = field(f, "filed_on");
    const delay_condonation = f.has("delay_condonation");
    const noteVal = field(f, "note");
    const note = noteVal || null;

    void run(
      () =>
        command("POST", `/api/v1/office/compliance/cases/${caseId}/appeals`, {
          forum,
          case_no,
          filed_on,
          delay_condonation,
          note,
        }),
      "Appeal registered on the legal register.",
      form
    );
  }

  function registerOtherCase(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    const establishment_id = field(f, "establishment_id");
    const kind = field(f, "kind");
    const forum = field(f, "forum");
    const case_no = field(f, "case_no");
    const filed_on = field(f, "filed_on");
    const inquiry_case_id = field(f, "inquiry_case_id") || undefined;
    const noteVal = field(f, "note");
    const note = noteVal || undefined;

    void run(
      () =>
        command("POST", "/api/v1/office/legal/cases", {
          establishment_id,
          kind,
          forum,
          case_no,
          filed_on,
          ...(inquiry_case_id ? { inquiry_case_id } : {}),
          ...(note ? { note } : {}),
        }),
      "Case registered on the legal register.",
      form
    );
  }

  const cases = casesQuery.data?.data ?? [];

  return (
    <section className="stack" aria-labelledby="legal-heading">
      <PageHeader
        id="legal-heading"
        eyebrow="Legal Cell"
        title="Legal cases"
        current="Legal cases"
        description="Appeals under section 7-I with the section 7-O pre-deposit, writs, and prosecutions."
      />
      <ProblemMessage error={error || casesQuery.error} />
      {notice ? <p role="status" className="ok">{notice}</p> : null}

      <form className="card stack" aria-label="Register an appeal (section 7-I)" onSubmit={registerAppeal}>
        <h2>Register an appeal (section 7-I)</h2>
        <p className="muted small">
          Register an appeal filed before the EPF Appellate Tribunal under section 7-I against an inquiry order (7A, 7B, 7C or 14B).
        </p>
        <div className="form-row">
          <label>
            Inquiry case ID
            <input name="inquiry_case_id" required placeholder="e.g. CMP-1" />
          </label>
          <label>
            Tribunal case number
            <input name="case_no" required placeholder="e.g. ATA-45/2026" />
          </label>
          <label>
            Filed on
            <input name="filed_on" type="date" required />
          </label>
          <label>
            Forum
            <input name="forum" required defaultValue="CGIT-cum-Labour Court (EPF Appellate Tribunal)" />
          </label>
        </div>
        <label className="check-row">
          <input type="checkbox" name="delay_condonation" />
          Delay condonation
        </label>
        <label>
          Note
          <textarea name="note" />
        </label>
        <div className="actions">
          <button className="primary" disabled={busy} type="submit">
            Register appeal
          </button>
        </div>
      </form>

      <form className="card stack" aria-label="Register another case" onSubmit={registerOtherCase}>
        <h2>Register another case</h2>
        <p className="muted small">
          Register a writ petition, NCLT insolvency proceedings, or other litigation involving the establishment.
        </p>
        <div className="form-row">
          <label>
            Establishment ID
            <input name="establishment_id" required defaultValue="EST-DEMO-0001" />
          </label>
          <label>
            Kind
            <select name="kind" defaultValue="WRIT">
              <option value="WRIT">Writ</option>
              <option value="NCLT">NCLT</option>
              <option value="OTHER">Other</option>
            </select>
          </label>
          <label>
            Forum
            <input name="forum" required placeholder="e.g. High Court of Delhi" />
          </label>
          <label>
            Case number
            <input name="case_no" required placeholder="e.g. WP(C) 1234/2026" />
          </label>
          <label>
            Filed on
            <input name="filed_on" type="date" required />
          </label>
          <label>
            Linked inquiry case (optional)
            <input name="inquiry_case_id" placeholder="e.g. CMP-1" />
          </label>
        </div>
        <label>
          Note
          <textarea name="note" />
        </label>
        <div className="actions">
          <button className="primary" disabled={busy} type="submit">
            Register case
          </button>
        </div>
      </form>

      <section className="card stack" aria-labelledby="register-heading">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "12px" }}>
          <h2 id="register-heading">Legal cases register</h2>
          <div style={{ display: "flex", gap: "12px", flexWrap: "wrap", alignItems: "center" }}>
            <label style={{ display: "flex", alignItems: "center", gap: "6px", fontWeight: "normal" }}>
              State:
              <select value={stateFilter} onChange={(e) => setStateFilter(e.target.value)}>
                <option value="">All states</option>
                <option value="PENDING">Pending</option>
                <option value="DECIDED">Decided</option>
              </select>
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: "6px", fontWeight: "normal" }}>
              Kind:
              <select value={kindFilter} onChange={(e) => setKindFilter(e.target.value)}>
                <option value="">All kinds</option>
                <option value="APPEAL_7I">Appeal under 7-I</option>
                <option value="WRIT">Writ</option>
                <option value="NCLT">NCLT</option>
                <option value="PROSECUTION">Prosecution</option>
                <option value="OTHER">Other</option>
              </select>
            </label>
          </div>
        </div>

        {casesQuery.isLoading ? <p className="muted">Loading cases...</p> : null}
        {!casesQuery.isLoading && cases.length === 0 ? <p className="muted">No legal cases found.</p> : null}

        {cases.map((item) => (
          <article key={item.legal_case_id} className="profile-card stack" aria-label={`Legal case ${item.case_no}`}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "10px", flexWrap: "wrap" }}>
              <div>
                <span className="eyebrow">{KIND_LABELS[item.kind] ?? item.kind}</span>
                <h3 style={{ margin: "4px 0" }}>{item.forum} · {item.case_no}</h3>
                <p className="muted small" style={{ margin: 0 }}>
                  Case ID: <code>{item.legal_case_id}</code> · Establishment: <strong>{item.establishment_id}</strong>
                  {item.inquiry_case_id ? <> · Inquiry case: <code>{item.inquiry_case_id}</code></> : null}
                  · Filed on {item.filed_on}
                </p>
              </div>
              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <span className="state-pill">{item.state}</span>
                {item.stayed ? (
                  <span className="state-pill" style={{ color: "#cc0000", borderColor: "#cc0000" }}>
                    Stayed
                  </span>
                ) : null}
              </div>
            </div>

            {item.note ? <p style={{ margin: 0 }}>{item.note}</p> : null}

            {item.kind === "APPEAL_7I" ? (
              <div className="card" style={{ background: "#f8fafc", padding: "14px", borderTop: "3px solid #b8860b" }}>
                <div style={{ display: "grid", gap: "6px" }}>
                  <p style={{ margin: 0 }}>
                    <strong>Amount under appeal:</strong> {rupees(item.amount_paise)}
                  </p>
                  <p style={{ margin: 0 }}>
                    <strong>Pre-deposit status:</strong> {rupees(item.pre_deposited_paise ?? 0)} of {rupees(item.pre_deposit_required_paise ?? 0)} deposited ({item.pre_deposit_percent ?? 75}%)
                  </p>
                  <p style={{ margin: 0 }}>
                    <strong>Hearing status:</strong> {item.heard ? "Can be heard" : "Cannot be heard (pre-deposit pending)"}
                  </p>
                </div>
                {item.pre_deposits && item.pre_deposits.length > 0 ? (
                  <div style={{ marginTop: "10px" }}>
                    <h4 style={{ margin: "0 0 6px 0", fontSize: "0.9rem" }}>Pre-deposits recorded</h4>
                    <ul className="plain-list">
                      {item.pre_deposits.map((dep, idx) => (
                        <li key={idx} className="small">
                          {rupees(dep.amount_paise)} · Ref: <code>{dep.reference}</code> · Deposited on {dep.deposited_on}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            ) : null}

            <div style={{ marginTop: "8px" }}>
              <h4 style={{ margin: "4px 0 8px 0" }}>Orders</h4>
              {item.orders && item.orders.length > 0 ? (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th scope="col">Date</th>
                        <th scope="col">Outcome</th>
                        <th scope="col">Details</th>
                        <th scope="col">Note</th>
                      </tr>
                    </thead>
                    <tbody>
                      {item.orders.map((ord, idx) => (
                        <tr key={idx}>
                          <th scope="row">{ord.order_date}</th>
                          <td><span className="state-pill">{ord.outcome}</span></td>
                          <td>
                            {ord.revised_amount_paise != null ? `Revised to ${rupees(ord.revised_amount_paise)}` : null}
                            {ord.percent != null ? `Reduced to ${ord.percent}% (Ref: ${ord.reference ?? "—"})` : null}
                            {ord.revised_amount_paise == null && ord.percent == null ? "—" : null}
                          </td>
                          <td>{ord.note ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="muted small" style={{ margin: 0 }}>No orders recorded yet.</p>
              )}
            </div>

            {item.state === "PENDING" ? (
              <div className="stack" style={{ marginTop: "12px", borderTop: "1px solid var(--line)", paddingTop: "14px" }}>
                <OrderForm caseItem={item} busy={busy} run={run} />
                {item.kind === "APPEAL_7I" ? (
                  <>
                    <PreDepositForm caseItem={item} busy={busy} run={run} />
                    <WaiverForm caseItem={item} busy={busy} run={run} ask={stepUp.ask} />
                  </>
                ) : null}
              </div>
            ) : null}
          </article>
        ))}
      </section>

      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}
