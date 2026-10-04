import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { api, command, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { ddmmyyyy } from "../../components/ui/format";
import { stateLabel } from "../journeyB";

type Challenge = { challenge_id: string; prompt: string };

interface VerifyResult {
  genuine: boolean;
  claim_id?: string;
  form_type?: string;
  amount_paise?: number;
  filed_on?: string;
  state?: string;
}

export function VerifyReceiptPage() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();

  const [claimIdInput, setClaimIdInput] = useState(searchParams.get("claim") ?? "");
  const [codeInput, setCodeInput] = useState(searchParams.get("code") ?? "");

  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<VerifyResult | null>(null);

  async function loadChallenge() {
    if (busy) return;
    setBusy(true);
    setError(null);
    setChallenge(null);
    setAnswer("");
    try {
      setChallenge((await api<Envelope<Challenge>>("/api/v1/public/demo-challenges")).data);
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(false);
    }
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy || !challenge) return;

    const integerAnswer = Number(answer);
    setError(null);
    setResult(null);

    const claim = claimIdInput.trim().toUpperCase();
    const code = codeInput.trim().toUpperCase();

    if (!/^-?\d+$/.test(answer.trim()) || !Number.isSafeInteger(integerAnswer)) {
      setError(new Error(t("receipt.answerInteger", "Enter an integer answer to the demo question.")));
      return;
    }
    if (!/^CLM-[0-9A-F]{8}$/.test(claim)) {
      setError(new Error(t("receipt.claimIdPatternError", "Enter a valid claim ID (e.g. CLM-1234ABCD).")));
      return;
    }
    if (!/^[A-Z2-7]{10}$/.test(code)) {
      setError(new Error(t("receipt.codePatternError", "Enter a 10-character verification code.")));
      return;
    }

    setBusy(true);
    try {
      const res = await command<Envelope<VerifyResult>>("POST", "/api/v1/public/receipts/verifications", {
        challenge_id: challenge.challenge_id,
        answer: integerAnswer,
        claim_id: claim,
        code,
      });
      setResult(res.data);
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(false);
      setChallenge(null);
      setAnswer("");
    }
  }

  return (
    <section className="stack" aria-labelledby="verify-receipt-page-heading">
      <PageHeader
        id="verify-receipt-page-heading"
        eyebrow="Public services · synthetic POC"
        title={t("receipt.verifyTitle", "Verify claim receipt")}
        description={t("receipt.verifyDescription", "Verify the authenticity of an EPFO claim receipt.")}
        current={t("receipt.verifyTitle", "Verify claim receipt")}
        parent={{ label: "Public services", to: "/public" }}
      />

      <section className="card stack" aria-labelledby="verify-receipt-form-heading">
        <h2 id="verify-receipt-form-heading">{t("receipt.checkReceipt", "Check receipt")}</h2>
        <form className="stack" aria-labelledby="verify-receipt-form-heading" onSubmit={(e) => void submit(e)}>
          <fieldset className="stack" disabled={busy}>
            <legend>{t("receipt.detailsAndVerification", "Details and verification")}</legend>

            <label>
              {t("receipt.claimId", "Claim ID")}
              <input
                name="claim_id"
                required
                pattern="CLM-[0-9A-F]{8}"
                placeholder="CLM-1234ABCD"
                value={claimIdInput}
                onChange={(e) => setClaimIdInput(e.target.value)}
              />
            </label>

            <label>
              {t("receipt.code", "Verification code")}
              <input
                name="code"
                required
                pattern="[A-Z2-7]{10}"
                maxLength={10}
                placeholder="ABCDE23456"
                value={codeInput}
                onChange={(e) => setCodeInput(e.target.value)}
              />
            </label>

            <div className="challenge-row">
              <button type="button" onClick={() => void loadChallenge()}>
                {t("receipt.getQuestion", "Get one-use demo question")}
              </button>
              {challenge ? (
                <label>
                  {challenge.prompt}
                  <input
                    required
                    inputMode="numeric"
                    pattern="-?[0-9]+"
                    value={answer}
                    onChange={(e) => setAnswer(e.target.value)}
                  />
                </label>
              ) : null}
            </div>
            <p className="muted small">
              {t("receipt.demoQuestionHelp", "The arithmetic question is a one-use demo check. Get a new question after each submission.")}
            </p>

            <div className="actions">
              <button type="submit" className="primary" disabled={!challenge || busy}>
                {t("receipt.checkReceipt", "Check receipt")}
              </button>
            </div>
          </fieldset>
        </form>

        {busy ? <p role="status">{t("receipt.pleaseWait", "Please wait…")}</p> : null}
        <ProblemMessage error={error} />

        {result ? (
          result.genuine ? (
            <div className="profile-card stack" role="status">
              <h3>{t("receipt.genuine", "Genuine receipt")}</h3>
              <dl className="kv">
                <dt>{t("receipt.claimId", "Claim ID")}</dt>
                <dd><code>{result.claim_id}</code></dd>

                <dt>{t("receipt.form", "Form")}</dt>
                <dd>{result.form_type}</dd>

                <dt>{t("receipt.amount", "Amount")}</dt>
                <dd><strong>{result.amount_paise !== undefined ? rupees(result.amount_paise) : "—"}</strong></dd>

                <dt>{t("receipt.filedOn", "Filed on")}</dt>
                <dd>{result.filed_on ? ddmmyyyy(result.filed_on) : "—"}</dd>

                <dt>{t("receipt.status", "Status")}</dt>
                <dd><span className="state-pill">{result.state ? stateLabel(result.state, t) : "—"}</span></dd>
              </dl>
            </div>
          ) : (
            <div className="profile-card stack" role="status">
              <p className="ineligible-reasons">
                <strong>{t("receipt.notVerified", "This receipt could not be verified")}</strong>
              </p>
            </div>
          )
        ) : null}
      </section>
    </section>
  );
}
