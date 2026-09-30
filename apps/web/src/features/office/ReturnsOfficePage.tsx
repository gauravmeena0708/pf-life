import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

interface OfficeFiling {
  filing_id: string; establishment_id: string; wage_month: string; type: string; state: string;
  trrn: string; challan: string; total_paise: number; submitted_at: string;
}
interface KnockOff {
  knock_off_id: string; establishment_id: string; trrn: string; demand_ids: string[];
  amount_paise: number; state: "PROPOSED" | "APPROVED" | "REJECTED"; note: string | null;
}
interface OpenDemand {
  demand_id: string; establishment_id: string; kind: string; trrn: string; wage_month: string;
  amount_paise: number; working: string;
}
interface MiscChallan { trrn: string; establishment_id: string; total_paise: number; applied_paise: number }
interface KnockOffData { knock_offs: KnockOff[]; open_demands: OpenDemand[]; misc_challans_with_balance: MiscChallan[] }

function reasonFrom(form: HTMLFormElement, minimum: number): string {
  const reason = String(new FormData(form).get("reason") ?? "").trim();
  if (reason.length < minimum) throw new Error(`Enter a reason of at least ${minimum} characters.`);
  return reason;
}

export function ReturnsOfficePage() {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [trrn, setTrrn] = useState("");
  const [selectedDemands, setSelectedDemands] = useState<string[]>([]);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const role = session.data?.stakeholder ?? "";
  const accounts = role === "fo.da_accounts";
  const cash = role === "fo.cash";
  const compliance = role === "fo.da_compliance";
  const ss = role === "fo.ss";
  const filings = useQuery({ queryKey: ["office-ecr-filings"], enabled: accounts || cash, retry: false,
    queryFn: () => api<Envelope<OfficeFiling[]>>("/api/v1/office/ecr-filings") });
  const knockOffs = useQuery({ queryKey: ["office-damages-knock-offs"], enabled: compliance || ss, retry: false,
    queryFn: () => api<Envelope<KnockOffData>>("/api/v1/office/damages-knock-offs") });
  const selectedChallan = knockOffs.data?.data.misc_challans_with_balance.find((item) => item.trrn === trrn);
  const availableDemands = knockOffs.data?.data.open_demands.filter((item) => item.establishment_id === selectedChallan?.establishment_id) ?? [];
  const chosen = availableDemands.filter((item) => selectedDemands.includes(item.demand_id));
  const chosenPaise = chosen.reduce((sum, item) => sum + item.amount_paise, 0);

  async function run(work: () => Promise<string | null>) {
    setError(null); setNotice(null); setBusy(true);
    try { const message = await work(); if (message) setNotice(message); }
    catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }

  function rejectFiling(e: FormEvent<HTMLFormElement>, filing: OfficeFiling, payment: boolean) {
    e.preventDefault();
    const form = e.currentTarget;
    void run(async () => {
      const reason = reasonFrom(form, 10);
      const action = payment ? "reject-ecr-payment" : "reject-ecr";
      const token = await stepUp.ask({ action, resourceId: filing.filing_id,
        summary: `${payment ? "Reject stuck payment" : "Reject return"} for TRRN ${filing.trrn}` });
      if (!token) return null;
      await command("POST", `/api/v1/office/ecr-filings/${encodeURIComponent(filing.filing_id)}/${payment ? "payment-rejections" : "rejections"}`,
        { reason }, { stepUpToken: token });
      await qc.invalidateQueries({ queryKey: ["office-ecr-filings"] });
      form.reset();
      return `${payment ? "Payment" : "Return"} rejected for TRRN ${filing.trrn}.`;
    });
  }

  function toggleDemand(id: string, checked: boolean) {
    setSelectedDemands((current) => checked ? [...current, id] : current.filter((item) => item !== id));
  }

  function propose(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    void run(async () => {
      if (!selectedChallan || !chosen.length) throw new Error("Choose a miscellaneous challan and at least one open demand.");
      const balance = selectedChallan.total_paise - selectedChallan.applied_paise;
      if (chosenPaise > balance) throw new Error(`Chosen demands exceed the ${rupees(balance)} challan balance.`);
      const token = await stepUp.ask({ action: "propose-knock-off", resourceId: selectedChallan.establishment_id,
        amountPaise: chosenPaise, summary: `Propose ${rupees(chosenPaise)} knock-off against ${trrn}` });
      if (!token) return null;
      await command("POST", `/api/v1/office/establishments/${encodeURIComponent(selectedChallan.establishment_id)}/damages-knock-offs`,
        { trrn, demand_ids: chosen.map((item) => item.demand_id) }, { stepUpToken: token });
      await qc.invalidateQueries({ queryKey: ["office-damages-knock-offs"] });
      setTrrn(""); setSelectedDemands([]);
      return `Knock-off proposed for ${rupees(chosenPaise)} against ${trrn}.`;
    });
  }

  function decide(e: FormEvent<HTMLFormElement>, item: KnockOff) {
    e.preventDefault();
    const form = e.currentTarget;
    const submitter = (e.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
    const decision = submitter?.value;
    if (decision !== "APPROVE" && decision !== "REJECT") return;
    void run(async () => {
      const note = reasonFrom(form, 5);
      const token = await stepUp.ask({ action: "approve-knock-off", resourceId: item.knock_off_id,
        amountPaise: item.amount_paise, summary: `${decision === "APPROVE" ? "Approve" : "Reject"} ${rupees(item.amount_paise)} knock-off ${item.knock_off_id}` });
      if (!token) return null;
      await command("POST", `/api/v1/office/damages-knock-offs/${encodeURIComponent(item.knock_off_id)}/approvals`,
        { decision, note }, { stepUpToken: token });
      await qc.invalidateQueries({ queryKey: ["office-damages-knock-offs"] });
      form.reset();
      return `Knock-off ${item.knock_off_id} ${decision === "APPROVE" ? "approved" : "rejected"}.`;
    });
  }

  return <main className="stack">
    <PageHeader eyebrow="Regional office" title="Returns, payments and 14B / 7Q" current="Returns office"
      description="Review submitted returns, stuck payments, and demand knock-offs." />
    <ProblemMessage error={error ?? session.error ?? filings.error ?? knockOffs.error} />
    {notice ? <p role="status" className="ok">{notice}</p> : null}

    {(accounts || cash) ? <section className="card stack" aria-labelledby="office-returns-heading"><h2 id="office-returns-heading">Submitted returns and payments</h2>
      {filings.isLoading ? <p role="status">Loading returns…</p> : null}
      {filings.data?.data.length ? <div className="table-scroll"><table><thead><tr>
        <th scope="col">Establishment</th><th scope="col">Wage month</th><th scope="col">Type</th><th scope="col">State</th>
        <th scope="col">TRRN</th><th scope="col">Challan</th><th scope="col">Total</th><th scope="col">Submitted</th><th scope="col">Action</th>
      </tr></thead><tbody>{filings.data.data.map((filing) => <tr key={filing.filing_id}>
        <th scope="row">{filing.establishment_id}</th><td>{filing.wage_month}</td><td>{filing.type}</td>
        <td>{filing.state.replaceAll("_", " ")}</td><td><code>{filing.trrn}</code></td><td>{filing.challan}</td>
        <td>{rupees(filing.total_paise)}</td><td>{filing.submitted_at}</td><td>
          {accounts || (cash && filing.challan === "DUE") ? <form className="stack"
            aria-label={`${accounts ? "Reject return" : "Reject stuck payment"} ${filing.trrn}`}
            onSubmit={(e) => rejectFiling(e, filing, cash)}>
            <label>Reason <input name="reason" required minLength={10} maxLength={500} /></label>
            <button type="submit" disabled={busy}>{accounts ? "Reject return" : "Reject stuck payment"}</button>
          </form> : "—"}</td>
      </tr>)}</tbody></table></div> : filings.data ? <p className="muted">No submitted returns awaiting office action.</p> : null}
    </section> : null}

    {(compliance || ss) ? <section className="card stack" aria-labelledby="knock-off-heading"><h2 id="knock-off-heading">14B / 7Q knock-offs</h2>
      {knockOffs.isLoading ? <p role="status">Loading knock-offs…</p> : null}
      {compliance ? <form className="stack" onSubmit={propose}>
        <h3>Propose a knock-off</h3>
        <label>Paid miscellaneous challan <select value={trrn} onChange={(e) => { setTrrn(e.target.value); setSelectedDemands([]); }} required>
          <option value="">Choose a challan</option>
          {knockOffs.data?.data.misc_challans_with_balance.map((item) => <option key={item.trrn} value={item.trrn}>
            {item.trrn} · {item.establishment_id} · {rupees(item.total_paise - item.applied_paise)} available
          </option>)}</select></label>
        {selectedChallan ? <fieldset><legend>Open demands for {selectedChallan.establishment_id}</legend>
          {availableDemands.length ? availableDemands.map((item) => <label key={item.demand_id}>
            <input type="checkbox" checked={selectedDemands.includes(item.demand_id)}
              onChange={(e) => toggleDemand(item.demand_id, e.target.checked)} /> {item.demand_id} · {item.kind} · {item.wage_month} · {rupees(item.amount_paise)}
          </label>) : <p className="muted">No open demands for this establishment.</p>}</fieldset> : null}
        {selectedChallan ? <p>Selected total: {rupees(chosenPaise)} · Challan balance: {rupees(selectedChallan.total_paise - selectedChallan.applied_paise)}</p> : null}
        <div className="actions"><button type="submit" className="primary" disabled={busy || !selectedChallan || !chosen.length}>Propose knock-off</button></div>
      </form> : null}
      {knockOffs.data?.data.knock_offs.length ? <div className="table-scroll"><table><thead><tr>
        <th scope="col">Knock-off</th><th scope="col">Establishment</th><th scope="col">TRRN</th><th scope="col">Demands</th>
        <th scope="col">Amount</th><th scope="col">State</th><th scope="col">Note</th>{ss ? <th scope="col">Decision</th> : null}
      </tr></thead><tbody>{knockOffs.data.data.knock_offs.map((item) => <tr key={item.knock_off_id}>
        <th scope="row">{item.knock_off_id}</th><td>{item.establishment_id}</td><td><code>{item.trrn}</code></td>
        <td>{item.demand_ids.join(", ")}</td><td>{rupees(item.amount_paise)}</td><td>{item.state}</td><td>{item.note ?? "—"}</td>
        {ss ? <td>{item.state === "PROPOSED" ? <form className="stack" aria-label={`Decide knock-off ${item.knock_off_id}`}
          onSubmit={(e) => decide(e, item)}>
          <label>Decision note <input name="reason" required minLength={5} maxLength={500} /></label>
          <div className="actions"><button type="submit" value="APPROVE" className="primary" disabled={busy}>Approve</button>
            <button type="submit" value="REJECT" disabled={busy}>Reject</button></div>
        </form> : "—"}</td> : null}
      </tr>)}</tbody></table></div> : knockOffs.data ? <p className="muted">No knock-offs recorded.</p> : null}
    </section> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </main>;
}
