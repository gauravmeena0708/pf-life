import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, command, newIdempotencyKey, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { Stepper } from "../../components/ui/Stepper";
import { ErrorSummary, type FieldError } from "../../components/ui/ErrorSummary";
import { extractErrors } from "../../components/ui/problems";
import { MoneyInput, parseRupees } from "../../components/ui/MoneyInput";
import { SummaryList, type SummaryRow } from "../../components/ui/SummaryList";
import { ConfirmationPanel } from "../../components/ui/ConfirmationPanel";
import { employmentLabel, ddmmyyyy, addDays } from "../../components/ui/format";
import { useStepUp } from "../stepup/useStepUp";
import { StepUpDialog } from "../stepup/StepUpDialog";

interface ClaimType {
  claim_type: string;
  form_type: string;
  label: string;
  plain_rule: string;
  eligible: boolean;
  max_amount_paise: number;
  reasons: string[];
  fixes?: { reason: string; fix: string | null; link: string | null }[];
}

interface Account {
  account_link_id: string;
  primary?: boolean;
  balance: { employee_paise: number; employer_paise: number; total_paise: number };
  types: ClaimType[];
}

interface Eligibility {
  accounts: Account[];
}

interface Employment {
  account_link_id: string;
  establishment_name: string;
  date_of_joining: string;
  date_of_exit: string | null;
  status: string;
}

interface MemberProfile {
  bank?: { ifsc: string; account_last4: string };
  kyc?: { aadhaar: string; pan: string; bank: string };
}

interface CreatedClaim {
  claim_id: string;
  summary: string;
  amount_paise: number;
  rules_applied: {
    route: "AUTO" | "REVIEW";
    approval_chain: string[];
    settlement_sla_days?: number;
    rule_version?: string;
    plain_rule?: string;
  };
  confirmation: {
    action: string;
    resource_id: string;
    resource_version: number;
    amount_paise: number;
  };
}


export function ClaimJourneyPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const createKey = useRef<string | null>(null);

  const [step, setStep] = useState<number>(0);
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const [selectedClaimType, setSelectedClaimType] = useState<string | null>(null);
  const [amountRupees, setAmountRupees] = useState<number | null>(null);
  const [amountText, setAmountText] = useState<string>("");
  const [stepErrors, setStepErrors] = useState<FieldError[]>([]);
  const [confirmedClaim, setConfirmedClaim] = useState<CreatedClaim | null>(null);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<CreatedClaim | null>(null);    // created, waiting for the one-time code
  const heading = useRef<HTMLHeadingElement>(null);
  const firstRender = useRef(true);
  useEffect(() => {                                    // a new step: tell assistive technology where the person now is
    if (firstRender.current) { firstRender.current = false; return; }
    heading.current?.focus();
  }, [step, pending]);

  const eligibilityQuery = useQuery({
    queryKey: ["member-claim-eligibility"],
    queryFn: () => api<Envelope<Eligibility>>("/api/v1/members/me/claims/eligible-types"),
    retry: false,
  });

  const historyQuery = useQuery({
    queryKey: ["member-employment"],
    queryFn: () => api<Envelope<Employment[]>>("/api/v1/members/me/employment-history"),
    retry: false,
  });

  const profileQuery = useQuery({
    queryKey: ["member-profile"],
    queryFn: () => api<Envelope<MemberProfile>>("/api/v1/members/me"),
    retry: false,
  });

  const employmentMap = useMemo(() => {
    const map = new Map<string, Employment>();
    for (const item of historyQuery.data?.data ?? []) {
      map.set(item.account_link_id, item);
    }
    return map;
  }, [historyQuery.data]);

  const accounts = eligibilityQuery.data?.data.accounts ?? [];
  const selectedAccount = accounts.find((a) => a.account_link_id === selectedAccountId);
  const selectedType = selectedAccount?.types.find((t) => t.claim_type === selectedClaimType);

  const stepLabels = [
    t("claimJourney.steps.whichJob"),
    t("claimJourney.steps.whatFor"),
    t("claimJourney.steps.howMuch"),
    t("claimJourney.steps.wherePaid"),
    t("claimJourney.steps.checkAnswers"),
  ];

  const serverError = eligibilityQuery.error || historyQuery.error || profileQuery.error;
  const initialErrors = serverError ? extractErrors(serverError) : [];
  const activeErrors = stepErrors.length > 0 ? stepErrors : initialErrors;

  const eligibleJobAccounts = accounts.filter((a) => a.types.some((t) => t.eligible));

  function handleContinueStep0() {
    if (!selectedAccountId) {
      const firstId = eligibleJobAccounts[0]?.account_link_id;
      setStepErrors([{ field: firstId ? `job-${firstId}` : "job-selection", message: t("claimJourney.errors.chooseJob") }]);
      return;
    }
    setStepErrors([]);
    setStep(1);
  }

  function handleContinueStep1() {
    if (!selectedClaimType) {
      const firstEligible = selectedAccount?.types.find((t) => t.eligible);
      setStepErrors([{
        field: firstEligible ? `claim-${firstEligible.claim_type}` : "claim-selection",
        message: t("claimJourney.errors.chooseClaim"),
      }]);
      return;
    }
    setStepErrors([]);
    setStep(2);
  }

  function handleContinueStep2() {
    const trimmed = amountText.trim();
    if (!trimmed) {
      setStepErrors([{ field: "claim-amount", message: t("claimJourney.errors.amountEmpty") }]);
      return;
    }
    if (trimmed.includes(".") || parseRupees(trimmed) === null) {
      setStepErrors([{ field: "claim-amount", message: t("claimJourney.errors.notWholeNumber") }]);
      return;
    }
    const val = parseRupees(trimmed)!;
    if (val <= 0) {
      setStepErrors([{ field: "claim-amount", message: t("claimJourney.errors.amountZero") }]);
      return;
    }
    const maxPaise = selectedType?.max_amount_paise ?? 0;
    if (val * 100 > maxPaise) {
      setStepErrors([{ field: "claim-amount", message: t("claimJourney.errors.amountAboveMax", { max: rupees(maxPaise) }) }]);
      return;
    }
    setAmountRupees(val);
    setStepErrors([]);
    setStep(3);
  }

  const profile = profileQuery.data?.data;
  const bank = profile?.bank;
  const isBankVerified = profile?.kyc?.bank === "VERIFIED";

  function handleContinueStep3() {
    if (!isBankVerified) {
      setStepErrors([{ message: t("claimJourney.step4.bankNotVerified") }]);
      return;
    }
    setStepErrors([]);
    setStep(4);
  }

  async function handleSubmitClaim() {
    if (!selectedAccountId || !selectedClaimType || !amountRupees || !isBankVerified) {
      return;
    }
    setBusy(true);
    setStepErrors([]);
    try {
      createKey.current ??= newIdempotencyKey();
      const amountPaise = amountRupees * 100;
      const reuse = pending && pending.amount_paise === amountPaise ? pending : null;   // answers changed: start afresh
      const result = reuse ? { data: reuse } : await command<Envelope<CreatedClaim>>(
        "POST",
        "/api/v1/members/me/claims",
        {
          account_link_id: selectedAccountId,
          claim_type: selectedClaimType,
          amount_paise: amountPaise,
        },
        { idempotencyKey: createKey.current }
      );
      const created = result.data;
      createKey.current = null;
      setPending(created);                             // a cancelled code keeps it: the next Submit asks again, no second claim

      const intent = created.confirmation;
      const token = await stepUp.ask({
        action: intent.action,
        resourceId: intent.resource_id,
        resourceVersion: intent.resource_version,
        amountPaise: intent.amount_paise,
        summary: created.summary,
      });

      if (!token) {
        setBusy(false);
        return;
      }

      await command(
        "POST",
        `/api/v1/members/me/claims/${created.claim_id}/confirmations`,
        undefined,
        { stepUpToken: token }
      );
      await qc.invalidateQueries({ queryKey: ["member-claims"] });
      setPending(null);
      setConfirmedClaim(created);
    } catch (cause) {
      setStepErrors(extractErrors(cause));
    } finally {
      setBusy(false);
    }
  }

  const empLabel = selectedAccount
    ? employmentLabel(
        employmentMap.get(selectedAccount.account_link_id),
        t("claimJourney.memberId", { id: selectedAccount.account_link_id }),
        t("claimJourney.now")
      )
    : "";

  const summaryRows: SummaryRow[] = [
    {
      key: "job",
      label: t("claimJourney.summary.job"),
      value: empLabel,
      onChange: () => { setStep(0); setStepErrors([]); },
    },
    {
      key: "claim",
      label: t("claimJourney.summary.claim"),
      value: selectedType?.label ?? "",
      onChange: () => { setStep(1); setStepErrors([]); },
    },
    {
      key: "amount",
      label: t("claimJourney.summary.amount"),
      value: rupees((amountRupees ?? 0) * 100),
      onChange: () => { setStep(2); setStepErrors([]); },
    },
    {
      key: "paidTo",
      label: t("claimJourney.summary.paidTo"),
      value: `${bank?.ifsc ?? ""} · ${t("claimJourney.step4.accountEnding", { last4: bank?.account_last4 ?? "" })}`,
      onChange: () => { setStep(3); setStepErrors([]); },
    },
  ];

  if (confirmedClaim) {
    const slaDays = confirmedClaim.rules_applied?.settlement_sla_days ?? 20;
    const expectDate = ddmmyyyy(addDays(new Date(), slaDays));
    const whatNext = confirmedClaim.rules_applied?.route === "AUTO"
      ? t("claimJourney.confirmation.autoApproved")
      : (confirmedClaim.rules_applied?.approval_chain?.length
          ? t("claimJourney.confirmation.approvalChain", { chain: confirmedClaim.rules_applied.approval_chain.join(" → ") })
          : t("claimJourney.confirmation.toReview"));

    return (
      <section className="stack" aria-labelledby="claim-journey-heading">
        <PageHeader
          id="claim-journey-heading"
          eyebrow={t("claimJourney.eyebrow")}
          title={t("claimJourney.title")}
          description={t("claimJourney.description")}
          parent={{ label: t("navigation.claims"), to: "/member/claims" }}
          current={t("claimJourney.current")}
        />
        <ConfirmationPanel
          title={t("claimJourney.confirmation.title")}
          referenceLabel={t("claimJourney.confirmation.referenceLabel")}
          reference={confirmedClaim.claim_id}
        >
          <div className="ui-confirmation-body stack">
            <p>{whatNext}</p>
            <p>{t("claimJourney.confirmation.expectBy", { date: expectDate })}</p>
            <div className="actions confirmation-actions">
              <Link to={`/member/claims/${confirmedClaim.claim_id}`} className="button">
                {t("claimJourney.confirmation.trackClaim")}
              </Link>
              <Link to="/member/claims" className="button">
                {t("claimJourney.confirmation.backToClaims")}
              </Link>
              <Link to={`/member/claims/${confirmedClaim.claim_id}/receipt`} className="button">
                {t("receipt.viewAndPrint", "View and print receipt")}
              </Link>
              <button type="button" className="button" onClick={() => window.print()}>
                {t("claimJourney.confirmation.printReceipt")}
              </button>
            </div>
          </div>
        </ConfirmationPanel>
      </section>
    );
  }

  const isLoading = eligibilityQuery.isLoading || historyQuery.isLoading || profileQuery.isLoading;

  return (
    <section className="stack" aria-labelledby="claim-journey-heading">
      <PageHeader
        id="claim-journey-heading"
        eyebrow={t("claimJourney.eyebrow")}
        title={t("claimJourney.title")}
        description={t("claimJourney.description")}
        parent={{ label: t("navigation.claims"), to: "/member/claims" }}
        current={t("claimJourney.current")}
      />

      <Stepper steps={stepLabels} current={step} />

      <div className="card stack">
        <ErrorSummary errors={activeErrors} />

        {isLoading ? <p role="status">{t("claimJourney.loading")}</p> : null}

        {!isLoading && step === 0 ? (
          <div className="journey-step stack" id="job-selection">
            <h2 ref={heading} tabIndex={-1}>{t("claimJourney.step1.heading")}</h2>
            <fieldset className="radio-group stack"><legend className="visually-hidden">{t("claimJourney.step1.heading")}</legend>
              {accounts.map((account) => {
                const emp = employmentMap.get(account.account_link_id);
                const employerText = employmentLabel(
                  emp,
                  t("claimJourney.memberId", { id: account.account_link_id }),
                  t("claimJourney.now")
                );
                const hasEligible = account.types.some((t) => t.eligible);
                const isSelected = selectedAccountId === account.account_link_id;

                return (
                  <label
                    key={account.account_link_id}
                    className={`journey-radio-item ${isSelected ? "selected" : ""} ${!hasEligible ? "muted-item" : ""}`}
                    htmlFor={`job-${account.account_link_id}`}
                  >
                    <input
                      type="radio"
                      id={`job-${account.account_link_id}`}
                      name="account_choice"
                      value={account.account_link_id}
                      checked={isSelected}
                      disabled={!hasEligible}
                      onChange={() => {
                        setSelectedAccountId(account.account_link_id);
                        setSelectedClaimType(null);
                        setAmountRupees(null);
                        setAmountText("");
                        setStepErrors([]);
                      }}
                    />
                    <div className="journey-radio-content">
                      <div className="radio-title-row">
                        <strong>{employerText}</strong>
                        {account.primary ? <span className="state-pill">{t("claimJourney.step1.primary")}</span> : null}
                      </div>
                      <span className="muted small">{t("claimJourney.memberId", { id: account.account_link_id })}</span>
                      <span className="small">{t("claimJourney.step1.totalBalance")}: <strong>{rupees(account.balance.total_paise)}</strong></span>
                      {!hasEligible ? (
                        <span className="muted small ineligibility-note">{t("claimJourney.step1.noClaimOpen")}</span>
                      ) : null}
                    </div>
                  </label>
                );
              })}
            </fieldset>
            <div className="actions">
              <button type="button" className="primary" onClick={handleContinueStep0}>
                {t("claimJourney.actions.continue")}
              </button>
            </div>
          </div>
        ) : null}

        {!isLoading && step === 1 ? (
          <div className="journey-step stack" id="claim-selection">
            <h2 ref={heading} tabIndex={-1}>{t("claimJourney.step2.heading")}</h2>
            {selectedAccount ? (
              <>
                <fieldset className="radio-group stack"><legend className="visually-hidden">{t("claimJourney.step2.heading")}</legend>
                  {selectedAccount.types
                    .filter((t) => t.eligible)
                    .map((type) => {
                      const isSelected = selectedClaimType === type.claim_type;
                      return (
                        <label
                          key={type.claim_type}
                          className={`journey-radio-item ${isSelected ? "selected" : ""}`}
                          htmlFor={`claim-${type.claim_type}`}
                        >
                          <input
                            type="radio"
                            id={`claim-${type.claim_type}`}
                            name="claim_type_choice"
                            value={type.claim_type}
                            checked={isSelected}
                            onChange={() => {
                              setSelectedClaimType(type.claim_type);
                              setAmountRupees(null);
                              setAmountText("");
                              setStepErrors([]);
                            }}
                          />
                          <div className="journey-radio-content">
                            <strong>{type.label}</strong>
                            <span className="muted small">{type.plain_rule}</span>
                            <span className="small">
                              <strong>{t("claimJourney.step2.upTo", { amount: rupees(type.max_amount_paise) })}</strong>
                            </span>
                          </div>
                        </label>
                      );
                    })}
                </fieldset>

                {selectedAccount.types.filter((t) => !t.eligible).length > 0 ? (
                  <details className="ineligible-details">
                    <summary>
                      {t("claimJourney.step2.notAvailableNow", {
                        count: selectedAccount.types.filter((t) => !t.eligible).length,
                      })}
                    </summary>
                    <ul className="ineligible-list">
                      {selectedAccount.types
                        .filter((t) => !t.eligible)
                        .map((type) => (
                          <li key={type.claim_type}>
                            <strong>{type.label}</strong>
                            <p className="small muted">{type.reasons.join("; ")}</p>
                            {(type.fixes ?? [])
                              .filter((f) => f.fix)
                              .map((f, i) => (
                                <p key={i} className="small">
                                  {t("claimJourney.step2.whatToDo", { fix: f.fix })}
                                  {f.link ? (
                                    <>
                                      {" "}
                                      <Link to={f.link}>{t("claimJourney.step2.goThere")}</Link>
                                    </>
                                  ) : null}
                                </p>
                              ))}
                          </li>
                        ))}
                    </ul>
                  </details>
                ) : null}
              </>
            ) : null}

            <div className="actions">
              <button type="button" onClick={() => { setStep(0); setStepErrors([]); }}>
                {t("claimJourney.actions.back")}
              </button>
              <button type="button" className="primary" onClick={handleContinueStep1}>
                {t("claimJourney.actions.continue")}
              </button>
            </div>
          </div>
        ) : null}

        {!isLoading && step === 2 ? (
          <div className="journey-step stack">
            <h2 ref={heading} tabIndex={-1}>{t("claimJourney.step3.heading")}</h2>
            <MoneyInput
              id="claim-amount"
              label={t("claimJourney.step3.amountLabel")}
              hint={t("claimJourney.step3.upTo", { amount: rupees(selectedType?.max_amount_paise) })}
              error={stepErrors.find((e) => e.field === "claim-amount")?.message}
              value={amountRupees}
              onChange={(val, txt) => {
                setAmountRupees(val);
                setAmountText(txt);
                setStepErrors([]);
              }}
            />
            <div className="actions">
              <button type="button" onClick={() => { setStep(1); setStepErrors([]); }}>
                {t("claimJourney.actions.back")}
              </button>
              <button type="button" className="primary" onClick={handleContinueStep2}>
                {t("claimJourney.actions.continue")}
              </button>
            </div>
          </div>
        ) : null}

        {!isLoading && step === 3 ? (
          <div className="journey-step stack">
            <h2 ref={heading} tabIndex={-1}>{t("claimJourney.step4.heading")}</h2>
            <div className="bank-record-box">
              <p><strong>{t("claimJourney.step4.bankAccountOnRecord")}</strong></p>
              <p>{t("claimJourney.step4.ifsc")}: <code>{bank?.ifsc ?? "—"}</code></p>
              <p>{t("claimJourney.step4.accountEnding", { last4: bank?.account_last4 ?? "—" })}</p>
            </div>

            {!isBankVerified ? (
              <div className="ui-field-error-block" role="alert">
                <p className="ui-field-error">{t("claimJourney.step4.bankNotVerified")}</p>
                <p>
                  <Link to="/member/kyc">{t("claimJourney.step4.updateBankKyc")}</Link>
                </p>
              </div>
            ) : null}

            <div className="actions">
              <button type="button" onClick={() => { setStep(2); setStepErrors([]); }}>
                {t("claimJourney.actions.back")}
              </button>
              <button type="button" className="primary" disabled={!isBankVerified} onClick={handleContinueStep3}>
                {t("claimJourney.actions.continue")}
              </button>
            </div>
          </div>
        ) : null}

        {!isLoading && step === 4 ? (
          <div className="journey-step stack">
            <h2 ref={heading} tabIndex={-1}>{t("claimJourney.step5.heading")}</h2>
            <SummaryList rows={summaryRows} />
            <div className="actions">
              <button type="button" disabled={busy} onClick={() => { setStep(3); setStepErrors([]); }}>
                {t("claimJourney.actions.back")}
              </button>
              <button type="button" className="primary" disabled={busy} onClick={() => void handleSubmitClaim()}>
                {t("claimJourney.actions.submitClaim")}
              </button>
            </div>
          </div>
        ) : null}
      </div>

      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}
