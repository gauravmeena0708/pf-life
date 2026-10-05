import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { ApiError, command, type Envelope, rupees } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";

export interface StepUpRequest {
  action: string;
  resourceId: string;
  resourceVersion?: number;
  amountPaise?: number;
  summary: string;
}

interface Props {
  request: StepUpRequest | null;
  onConfirmed: (token: string) => void;
  onCancel: () => void;
  labels?: Partial<StepUpLabels>;
}

export interface StepUpLabels {
  title: string;
  authorising: string;
  amount: string;
  rate: string;
  reference: string;
  demoCode: string;
  demoNotice: string;
  oneTimeCode: string;
  retry: string;
  preparing: string;
  cancel: string;
  confirm: string;
}

const defaults: StepUpLabels = {
  title: "Confirm this action", authorising: "You are authorising", amount: "Amount", rate: "Rate",
  reference: "Reference", demoCode: "Demo one-time code", demoNotice: "", oneTimeCode: "One-time code",
  retry: "Close this dialog and try confirmation again.", preparing: "Preparing confirmation…",
  cancel: "Cancel", confirm: "Confirm",
};

/** Transaction-intent confirmation (init.md §6.3): says exactly what is authorised; OTP is a labelled simulation. */
export function StepUpDialog({ request, onConfirmed, onCancel, labels }: Props) {
  const copy = { ...defaults, ...labels };
  const dialog = useRef<HTMLDialogElement>(null);
  const [challenge, setChallenge] = useState<{ challenge_id: string; demo_otp: string; demo_notice: string } | null>(null);
  const [otp, setOtp] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!request) {
      if (dialog.current?.open) dialog.current.close();
      return;
    }
    let active = true;
    setChallenge(null);
    setOtp("");
    setError(null);
    if (!dialog.current?.open) dialog.current?.showModal();
    command<Envelope<{ challenge_id: string; demo_otp: string; demo_notice: string }>>("POST", "/api/v1/security/step-up-challenges", {
      action: request.action,
      resource_id: request.resourceId,
      resource_version: request.resourceVersion ?? null,
      amount_paise: request.amountPaise ?? null,
      summary: request.summary,
    })
      .then((r) => { if (active) setChallenge(r.data); })
      .catch((cause) => { if (active) setError(cause); });
    return () => { active = false; };
  }, [request]);

  async function verify(e: React.FormEvent) {
    e.preventDefault();
    if (!challenge) return;
    setBusy(true);
    setError(null);
    try {
      const r = await command<Envelope<{ step_up_token: string }>>(
        "POST",
        `/api/v1/security/step-up-challenges/${challenge.challenge_id}/verifications`,
        { otp },
      );
      onConfirmed(r.data.step_up_token);
    } catch (err) {
      setError(err);
      if (err instanceof ApiError && err.problem.title.includes("Too many")) setChallenge(null);
    } finally {
      setBusy(false);
    }
  }

  // rendered at the end of the page: the dialog holds a form, and a page may place it inside a form of its own
  return createPortal(
    <dialog ref={dialog} aria-labelledby="stepup-title" onCancel={onCancel} className="stepup">
      <form onSubmit={verify}>
        <h2 id="stepup-title">{copy.title}</h2>
        {request ? (
          <dl className="kv">
            <dt>{copy.authorising}</dt>
            <dd><strong>{request.summary}</strong></dd>
            {request.amountPaise !== undefined ? request.action === "record-interest-rate"
              ? <><dt>{copy.rate}</dt><dd>{(request.amountPaise / 100).toFixed(2)}%</dd></>
              : <><dt>{copy.amount}</dt><dd>{rupees(request.amountPaise)}</dd></> : null}
            <dt>{copy.reference}</dt>
            <dd><code>{request.resourceId}</code>{request.resourceVersion !== undefined ? ` (version ${request.resourceVersion})` : ""}</dd>
          </dl>
        ) : null}
        {challenge ? (
          <>
            <p className="demo-otp" role="note" aria-live="polite">
              {copy.demoCode}: <code>{challenge.demo_otp}</code>
              <br />
              <span className="muted small">{copy.demoNotice || challenge.demo_notice}</span>
            </p>
            <label htmlFor="stepup-otp">{copy.oneTimeCode}</label>
            <input id="stepup-otp" inputMode="numeric" autoComplete="one-time-code" value={otp}
              onChange={(e) => setOtp(e.target.value.trim())} required pattern="[0-9]{6}" />
          </>
        ) : (
          <p className="muted" aria-live="polite">{error ? copy.retry : copy.preparing}</p>
        )}
        <ProblemMessage error={error} />
        <div className="actions">
          <button type="button" onClick={onCancel}>{copy.cancel}</button>
          <button type="submit" className="primary" disabled={!challenge || busy || otp.length !== 6}>{copy.confirm}</button>
        </div>
      </form>
    </dialog>,
    document.body,
  );
}
