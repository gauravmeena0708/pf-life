import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, command, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { Stepper } from "../../components/ui/Stepper";
import { ErrorSummary, type FieldError } from "../../components/ui/ErrorSummary";
import { SummaryList, type SummaryRow } from "../../components/ui/SummaryList";
import { ConfirmationPanel } from "../../components/ui/ConfirmationPanel";
import { extractErrors } from "../../components/ui/problems";
import { useStepUp } from "../stepup/useStepUp";
import { StepUpDialog } from "../stepup/StepUpDialog";

interface MemberProfile {
  member_id: string;
  name?: string;
  bank?: { ifsc: string; account_last4: string };
  kyc?: { aadhaar: string; pan: string; bank: string };
}

interface KycRequest {
  request_id: string;
  kyc_type: string;
  masked_value: string;
  state: "PENDING_EMPLOYER" | "FAILED_VERIFICATION" | string;
  verification: { verifier: string; verified: boolean; reason?: string };
  decision_note?: string | null;
  created_at?: string;
}

interface KycData {
  aadhaar?: string;
  pan?: string;
  bank?: string;
  bank_ifsc?: string;
  bank_account_last4?: string;
  requests?: KycRequest[];
}

/** P2.28b: Guided journey for members to change their bank account with penny-drop and employer approval. */
export function BankJourneyPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const stepUp = useStepUp();

  const [step, setStep] = useState<number>(0);
  const [ifsc, setIfsc] = useState<string>("");
  const [accountNumber, setAccountNumber] = useState<string>("");
  const [accountNumberAgain, setAccountNumberAgain] = useState<string>("");
  const [stepErrors, setStepErrors] = useState<FieldError[]>([]);
  const [confirmedRequest, setConfirmedRequest] = useState<KycRequest | null>(null);
  const [failedReason, setFailedReason] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const heading = useRef<HTMLHeadingElement>(null);
  const firstRender = useRef(true);
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    heading.current?.focus();
  }, [step]);

  const profileQuery = useQuery({
    queryKey: ["member-profile"],
    queryFn: () => api<Envelope<MemberProfile>>("/api/v1/members/me"),
    retry: false,
  });

  const kycQuery = useQuery({
    queryKey: ["kyc"],
    queryFn: () => api<Envelope<KycData>>("/api/v1/members/me/kyc"),
    retry: false,
  });

  const profile = profileQuery.data?.data;
  const kyc = kycQuery.data?.data;
  const memberId = profile?.member_id ?? "";
  const currentIfsc = profile?.bank?.ifsc || kyc?.bank_ifsc || "—";
  const currentLast4 = profile?.bank?.account_last4 || kyc?.bank_account_last4 || "—";

  const stepLabels = [
    t("kycBankJourney.steps.yourBank"),
    t("kycBankJourney.steps.accountNumber"),
    t("kycBankJourney.steps.checkAnswers"),
  ];

  const serverError = profileQuery.error || kycQuery.error;
  const initialErrors = serverError ? extractErrors(serverError) : [];
  const activeErrors = stepErrors.length > 0 ? stepErrors : initialErrors;

  function handleContinueStep0() {
    const trimmed = ifsc.trim().toUpperCase();
    if (!trimmed) {
      setStepErrors([{ field: "bank-ifsc", message: t("kycBankJourney.errors.ifscEmpty") }]);
      return;
    }
    if (!/^[A-Z]{4}0[A-Z0-9]{6}$/.test(trimmed)) {
      setStepErrors([{ field: "bank-ifsc", message: t("kycBankJourney.errors.ifscFormat") }]);
      return;
    }
    setIfsc(trimmed);
    setStepErrors([]);
    setStep(1);
  }

  function handleContinueStep1() {
    const acc1 = accountNumber.trim();
    const acc2 = accountNumberAgain.trim();
    if (!acc1) {
      setStepErrors([{ field: "bank-account", message: t("kycBankJourney.errors.accountEmpty") }]);
      return;
    }
    if (!/^\d{9,18}$/.test(acc1)) {
      setStepErrors([{ field: "bank-account", message: t("kycBankJourney.errors.accountDigits") }]);
      return;
    }
    if (!acc2) {
      setStepErrors([{ field: "bank-account-again", message: t("kycBankJourney.errors.accountAgainEmpty") }]);
      return;
    }
    if (!/^\d{9,18}$/.test(acc2)) {
      setStepErrors([{ field: "bank-account-again", message: t("kycBankJourney.errors.accountDigits") }]);
      return;
    }
    if (acc1 !== acc2) {
      setStepErrors([{ field: "bank-account-again", message: t("kycBankJourney.errors.accountMismatch") }]);
      return;
    }
    setStepErrors([]);
    setStep(2);
  }

  async function handleSubmit() {
    setBusy(true);
    setStepErrors([]);
    setFailedReason(null);
    try {
      const last4 = accountNumber.trim().slice(-4);
      const token = await stepUp.ask({
        action: "seed-kyc",
        resourceId: memberId,
        summary: t("kycBankJourney.stepUpSummary", { last4 }),
      });
      if (!token) {
        setBusy(false);
        return;
      }
      const response = await command<Envelope<KycRequest>>(
        "POST",
        "/api/v1/members/me/kyc/bank-accounts",
        { ifsc, account_number: accountNumber.trim() },
        { stepUpToken: token }
      );
      const kycResult = response.data;
      if (kycResult.state === "PENDING_EMPLOYER") {
        await qc.invalidateQueries({ queryKey: ["kyc"] });
        await qc.invalidateQueries({ queryKey: ["member-profile"] });
        await qc.invalidateQueries({ queryKey: ["me"] });
        setConfirmedRequest(kycResult);
      } else if (kycResult.state === "FAILED_VERIFICATION") {
        const reason = kycResult.verification?.reason || t("kycBankJourney.errors.defaultFailedReason");
        setFailedReason(reason);
        setStepErrors([
          {
            field: "enter-another-account",
            message: t("kycBankJourney.errors.verificationFailed", { reason }),
            onClick: () => {
              setStep(1);
              setStepErrors([]);
              setFailedReason(null);
            },
          },
        ]);
      } else {
        setStepErrors([{ message: `Status: ${kycResult.state}` }]);
      }
    } catch (cause) {
      setStepErrors(extractErrors(cause));
    } finally {
      setBusy(false);
    }
  }

  const ifscError = activeErrors.find((e) => e.field === "bank-ifsc");
  const accountError = activeErrors.find((e) => e.field === "bank-account");
  const accountAgainError = activeErrors.find((e) => e.field === "bank-account-again");

  const summaryRows: SummaryRow[] = [
    {
      key: "ifsc",
      label: t("kycBankJourney.summary.ifsc"),
      value: ifsc,
      onChange: () => {
        setStep(0);
        setStepErrors([]);
        setFailedReason(null);
      },
    },
    {
      key: "account",
      label: t("kycBankJourney.summary.account"),
      value: t("kycBankJourney.summary.accountValue", { last4: accountNumber.trim().slice(-4) }),
      onChange: () => {
        setStep(1);
        setStepErrors([]);
        setFailedReason(null);
      },
    },
  ];

  if (confirmedRequest) {
    const verifier = confirmedRequest.verification?.verifier ?? "";
    return (
      <section className="stack" aria-labelledby="bank-journey-heading">
        <PageHeader
          id="bank-journey-heading"
          eyebrow={t("kycBankJourney.eyebrow")}
          title={t("kycBankJourney.title")}
          description={t("kycBankJourney.description")}
          parent={{ label: t("kycBankJourney.parent"), to: "/member/kyc" }}
          current={t("kycBankJourney.current")}
        />
        <ConfirmationPanel
          title={t("kycBankJourney.confirmation.title")}
          referenceLabel={t("kycBankJourney.confirmation.referenceLabel")}
          reference={confirmedRequest.request_id}
        >
          <div className="ui-confirmation-body stack">
            <p>{t("kycBankJourney.confirmation.body", { verifier })}</p>
            <div className="actions confirmation-actions">
              <Link to="/member/kyc" className="button">
                {t("kycBankJourney.confirmation.backToKyc")}
              </Link>
              <Link to="/member/claims/new" className="button">
                {t("kycBankJourney.confirmation.startClaim")}
              </Link>
            </div>
          </div>
        </ConfirmationPanel>
      </section>
    );
  }

  const isLoading = profileQuery.isLoading || kycQuery.isLoading;

  return (
    <section className="stack" aria-labelledby="bank-journey-heading">
      <PageHeader
        id="bank-journey-heading"
        eyebrow={t("kycBankJourney.eyebrow")}
        title={t("kycBankJourney.title")}
        description={t("kycBankJourney.description")}
        parent={{ label: t("kycBankJourney.parent"), to: "/member/kyc" }}
        current={t("kycBankJourney.current")}
      />

      <Stepper steps={stepLabels} current={step} />

      <div className="card stack">
        <ErrorSummary errors={activeErrors} />

        {isLoading ? <p role="status">{t("kycBankJourney.loading")}</p> : null}

        {!isLoading && step === 0 ? (
          <div className="journey-step stack" id="bank-ifsc-section">
            <h2 ref={heading} tabIndex={-1}>
              {t("kycBankJourney.step1.heading")}
            </h2>

            <div className="bank-record-box">
              <p>
                {t("kycBankJourney.step1.nowOnRecord", {
                  ifsc: currentIfsc,
                  last4: currentLast4,
                })}
              </p>
            </div>

            <div className={`ui-field${ifscError ? " has-error" : ""}`}>
              <label htmlFor="bank-ifsc">{t("kycBankJourney.step1.ifscLabel")}</label>
              <p id="bank-ifsc-hint" className="ui-hint">
                {t("kycBankJourney.step1.ifscHint")}
              </p>
              {ifscError ? (
                <p id="bank-ifsc-error" className="ui-field-error">
                  <span className="visually-hidden">Error: </span>
                  {ifscError.message}
                </p>
              ) : null}
              <input
                id="bank-ifsc"
                name="bank-ifsc"
                type="text"
                autoComplete="off"
                value={ifsc}
                aria-invalid={!!ifscError}
                aria-describedby={
                  ["bank-ifsc-hint", ifscError ? "bank-ifsc-error" : ""].filter(Boolean).join(" ") ||
                  undefined
                }
                onChange={(e) => {
                  setIfsc(e.target.value.toUpperCase());
                  setStepErrors([]);
                }}
              />
            </div>

            <div className="actions">
              <button type="button" className="primary" onClick={handleContinueStep0}>
                {t("kycBankJourney.actions.continue")}
              </button>
            </div>
          </div>
        ) : null}

        {!isLoading && step === 1 ? (
          <div className="journey-step stack" id="bank-account-section">
            <h2 ref={heading} tabIndex={-1}>
              {t("kycBankJourney.step2.heading")}
            </h2>

            <div className={`ui-field${accountError ? " has-error" : ""}`}>
              <label htmlFor="bank-account">{t("kycBankJourney.step2.accountLabel")}</label>
              <p id="bank-account-hint" className="ui-hint">
                {t("kycBankJourney.step2.accountHint")}
              </p>
              {accountError ? (
                <p id="bank-account-error" className="ui-field-error">
                  <span className="visually-hidden">Error: </span>
                  {accountError.message}
                </p>
              ) : null}
              <input
                id="bank-account"
                name="bank-account"
                type="text"
                inputMode="numeric"
                autoComplete="off"
                value={accountNumber}
                aria-invalid={!!accountError}
                aria-describedby={
                  ["bank-account-hint", accountError ? "bank-account-error" : ""].filter(Boolean).join(" ") ||
                  undefined
                }
                onChange={(e) => {
                  setAccountNumber(e.target.value);
                  setStepErrors([]);
                }}
              />
            </div>

            <div className={`ui-field${accountAgainError ? " has-error" : ""}`}>
              <label htmlFor="bank-account-again">{t("kycBankJourney.step2.accountAgainLabel")}</label>
              {accountAgainError ? (
                <p id="bank-account-again-error" className="ui-field-error">
                  <span className="visually-hidden">Error: </span>
                  {accountAgainError.message}
                </p>
              ) : null}
              <input
                id="bank-account-again"
                name="bank-account-again"
                type="text"
                inputMode="numeric"
                autoComplete="off"
                value={accountNumberAgain}
                aria-invalid={!!accountAgainError}
                aria-describedby={accountAgainError ? "bank-account-again-error" : undefined}
                onChange={(e) => {
                  setAccountNumberAgain(e.target.value);
                  setStepErrors([]);
                }}
              />
            </div>

            <div className="actions">
              <button
                type="button"
                onClick={() => {
                  setStep(0);
                  setStepErrors([]);
                }}
              >
                {t("kycBankJourney.actions.back")}
              </button>
              <button type="button" className="primary" onClick={handleContinueStep1}>
                {t("kycBankJourney.actions.continue")}
              </button>
            </div>
          </div>
        ) : null}

        {!isLoading && step === 2 ? (
          <div className="journey-step stack">
            <h2 ref={heading} tabIndex={-1}>
              {t("kycBankJourney.step3.heading")}
            </h2>

            <SummaryList rows={summaryRows} />

            <p className="muted small">{t("kycBankJourney.step3.note")}</p>

            <div className="actions">
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  setStep(1);
                  setStepErrors([]);
                  setFailedReason(null);
                }}
              >
                {t("kycBankJourney.actions.back")}
              </button>
              <button
                type="button"
                className="primary"
                disabled={busy}
                onClick={() => void handleSubmit()}
              >
                {t("kycBankJourney.actions.submit")}
              </button>
              {failedReason ? (
                <button
                  type="button"
                  id="enter-another-account"
                  className="button"
                  onClick={() => {
                    setStep(1);
                    setStepErrors([]);
                    setFailedReason(null);
                  }}
                >
                  {t("kycBankJourney.actions.enterAnotherAccount")}
                </button>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>

      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}
