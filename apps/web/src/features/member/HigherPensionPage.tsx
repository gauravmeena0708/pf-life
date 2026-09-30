import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, getSession, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { HigherPensionDetails, type HigherPensionOption } from "../pension/HigherPensionDetails";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

interface Options { options: HigherPensionOption[]; in_service_on: string; note: string }

export function HigherPensionPage() {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const member = session.data?.stakeholder === "member";
  const profile = useQuery({ queryKey: ["higher-pension-member"], enabled: member, retry: false,
    queryFn: () => api<Envelope<{ uan: string }>>("/api/v1/members/me") });
  const options = useQuery({ queryKey: ["member-higher-pension"], enabled: member, retry: false,
    queryFn: () => api<Envelope<Options>>("/api/v1/members/me/higher-pension-options") });

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const uan = profile.data?.data.uan;
    if (!member || !uan || busy) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      const higherFrom = String(f.get("higher_wages_from") ?? "");
      if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(higherFrom) || f.get("declaration") !== "on" || f.get("consent") !== "on")
        throw new Error("Enter the month of higher wages and confirm both declarations.");
      const token = await stepUp.ask({ action: "submit-higher-pension-option", resourceId: uan,
        summary: `Submit the joint option for pension on higher wages from ${higherFrom} for UAN ${uan}, with consent to dues adjustment.` });
      if (!token) return;
      await command("POST", "/api/v1/members/me/higher-pension-options", {
        higher_wages_from: higherFrom, declaration: true, consent_to_dues_adjustment: true,
      }, { stepUpToken: token });
      setNotice("Your higher-pension option has been submitted for employer validation.");
      await qc.invalidateQueries({ queryKey: ["member-higher-pension"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }

  return <section className="stack" aria-labelledby="higher-pension-heading">
    <PageHeader id="higher-pension-heading" eyebrow="Member services" title="Pension on higher wages"
      description="Submit a joint option and review employer validation and dues." current="Higher pension" />
    <ProblemMessage error={error ?? session.error ?? profile.error ?? options.error} />
    {notice ? <p role="status" className="ok">{notice}</p> : null}
    {session.isLoading || profile.isLoading || options.isLoading ? <p role="status">Loading higher-pension details…</p> : null}
    {session.data && !member ? <p className="pending-notice">This service is available to members.</p> : null}
    {member && options.data ? <>
      <section className="card stack"><h2>Joint option</h2><p>{options.data.data.note}</p>
        <p>In-service date: {options.data.data.in_service_on} · UAN {profile.data?.data.uan ?? "—"}</p>
        <form className="stack" aria-label="Submit higher-pension option" onSubmit={(e) => void submit(e)}>
          <fieldset className="stack" disabled={busy || !!stepUp.request || !profile.data}><legend>Member declaration</legend>
            <label>Higher wages from<input type="month" name="higher_wages_from" required /></label>
            <label className="check-row"><input type="checkbox" name="declaration" required />I declare that the option details are correct</label>
            <label className="check-row"><input type="checkbox" name="consent" required />I consent to adjustment of the higher-pension dues</label>
            <div className="actions"><button type="submit" className="primary">Submit joint option</button></div>
          </fieldset>
        </form>
      </section>
      <section className="card stack"><h2>Your options</h2>
        {options.data.data.options.length ? options.data.data.options.map((option) => <article className="card stack" key={option.option_id}>
          <h3>Option {option.option_id}</h3><HigherPensionDetails option={option} />
        </article>) : <p className="muted">No higher-pension options submitted.</p>}
      </section>
    </> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </section>;
}
