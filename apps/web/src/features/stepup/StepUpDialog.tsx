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
}

/** Transaction-intent confirmation (init.md §6.3): says exactly what is authorised; OTP is a labelled simulation. */
export function StepUpDialog({ request, onConfirmed, onCancel }: Props) {
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
        <h2 id="stepup-title">Confirm this action</h2>
        {request ? (
          <dl className="kv">
            <dt>You are authorising</dt>
            <dd><strong>{request.summary}</strong></dd>
            {request.amountPaise !== undefined ? request.action === "record-interest-rate"
              ? <><dt>Rate</dt><dd>{(request.amountPaise / 100).toFixed(2)}%</dd></>
              : <><dt>Amount</dt><dd>{rupees(request.amountPaise)}</dd></> : null}
            <dt>Reference</dt>
            <dd><code>{request.resourceId}</code>{request.resourceVersion !== undefined ? ` (version ${request.resourceVersion})` : ""}</dd>
          </dl>
        ) : null}
        {challenge ? (
          <>
            <p className="demo-otp" role="note">
              Demo one-time code: <code>{challenge.demo_otp}</code>
              <br />
              <span className="muted small">{challenge.demo_notice}</span>
            </p>
            <label htmlFor="stepup-otp">One-time code</label>
            <input id="stepup-otp" inputMode="numeric" autoComplete="one-time-code" value={otp}
              onChange={(e) => setOtp(e.target.value.trim())} required pattern="[0-9]{6}" />
          </>
        ) : (
          <p className="muted">{error ? "Close this dialog and try confirmation again." : "Preparing confirmation…"}</p>
        )}
        <ProblemMessage error={error} />
        <div className="actions">
          <button type="button" onClick={onCancel}>Cancel</button>
          <button type="submit" className="primary" disabled={!challenge || busy || otp.length !== 6}>Confirm</button>
        </div>
      </form>
    </dialog>,
    document.body,
  );
}
