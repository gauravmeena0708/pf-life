import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api, command, getSession, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { ErrorSummary, type FieldError } from "../../components/ui/ErrorSummary";
import { ddmmyyyy } from "../../components/ui/format";
import { extractErrors } from "../../components/ui/problems";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

export interface AvailableProvider {
  provider_id: string;
  name: string;
}

export interface AuthorisedProvider {
  grant_id: string;
  provider_id: string;
  name: string;
  scopes: string[];
  status: "ACTIVE" | "REVOKED";
  granted_at: string;
}

export interface PayrollProvidersData {
  available: AvailableProvider[];
  authorised: AuthorisedProvider[];
}

export function PayrollProvidersPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const stepUp = useStepUp();

  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<FieldError[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [revokeReasons, setRevokeReasons] = useState<Record<string, string>>({});

  const session = useQuery({
    queryKey: ["session"],
    queryFn: getSession,
    retry: false,
  });
  const role = session.data?.stakeholder ?? "";
  const isOwner = role === "employer.owner";

  const providersQuery = useQuery({
    queryKey: ["payroll-providers"],
    queryFn: () => api<Envelope<PayrollProvidersData>>("/api/v1/employers/me/payroll-providers"),
    retry: false,
  });

  const available = providersQuery.data?.data?.available ?? [];
  const authorised = providersQuery.data?.data?.authorised ?? [];

  async function handleAuthorise(provider: AvailableProvider) {
    if (!isOwner) return;
    setErrors([]);
    setNotice(null);
    setBusy(true);

    try {
      const token = await stepUp.ask({
        action: "authorise-payroll-provider",
        resourceId: provider.provider_id,
        summary: t("payroll.authoriseStepUpSummary", { name: provider.name }),
      });
      if (!token) {
        setBusy(false);
        return;
      }

      await command<Envelope<unknown>>(
        "POST",
        "/api/v1/employers/me/payroll-providers/authorisations",
        { provider_id: provider.provider_id },
        { stepUpToken: token }
      );

      await qc.invalidateQueries({ queryKey: ["payroll-providers"] });
      setNotice(t("payroll.authoriseSuccess", { name: provider.name }));
    } catch (cause) {
      setErrors(extractErrors(cause));
    } finally {
      setBusy(false);
    }
  }

  async function handleRevoke(auth: AuthorisedProvider) {
    if (!isOwner) return;
    setErrors([]);
    setNotice(null);

    const reason = (revokeReasons[auth.grant_id] || "").trim();
    if (!reason || reason.length < 5 || reason.length > 300) {
      setErrors([
        {
          field: `revoke-reason-${auth.grant_id}`,
          message: t("payroll.revokeReasonRequired"),
        },
      ]);
      return;
    }

    setBusy(true);
    try {
      const token = await stepUp.ask({
        action: "revoke-payroll-provider",
        resourceId: auth.grant_id,
        summary: t("payroll.revokeStepUpSummary", { name: auth.name }),
      });
      if (!token) {
        setBusy(false);
        return;
      }

      await command<Envelope<unknown>>(
        "POST",
        `/api/v1/employers/me/payroll-providers/authorisations/${encodeURIComponent(auth.grant_id)}/revocations`,
        { reason },
        { stepUpToken: token }
      );

      await qc.invalidateQueries({ queryKey: ["payroll-providers"] });
      setRevokeReasons((prev) => {
        const next = { ...prev };
        delete next[auth.grant_id];
        return next;
      });
      setNotice(t("payroll.revokeSuccess", { name: auth.name }));
    } catch (cause) {
      setErrors(extractErrors(cause));
    } finally {
      setBusy(false);
    }
  }

  function formatScope(scope: string): string {
    if (scope === "payroll.submit") {
      return t("payroll.scopeSendPayRuns");
    }
    return scope;
  }

  return (
    <section className="stack" aria-labelledby="payroll-providers-heading">
      <PageHeader
        id="payroll-providers-heading"
        eyebrow={t("payroll.eyebrow")}
        title={t("payroll.title")}
        description={t("payroll.whatItMeans")}
        parent={{ label: "Employer", to: "/employer" }}
        current={t("payroll.title")}
      />

      <ErrorSummary errors={errors} />
      <ProblemMessage error={providersQuery.error} />

      {notice ? (
        <div className="notice" role="status">
          <p>{notice}</p>
        </div>
      ) : null}

      {!isOwner && !session.isLoading ? (
        <div className="info-callout" role="note">
          <p className="muted small">{t("payroll.ownerOnlyNotice")}</p>
        </div>
      ) : null}

      <div className="card stack">
        <h2>{t("payroll.explanationTitle")}</h2>
        <p>{t("payroll.explanationBody")}</p>
      </div>

      <section className="card stack" aria-labelledby="authorised-providers-heading">
        <div className="section-heading">
          <div>
            <h2 id="authorised-providers-heading">{t("payroll.authorisedHeading")}</h2>
          </div>
        </div>

        {providersQuery.isLoading ? (
          <p className="muted" role="status">Loading...</p>
        ) : null}

        {!providersQuery.isLoading && authorised.length === 0 ? (
          <p className="muted">{t("payroll.noAuthorised")}</p>
        ) : null}

        {authorised.length > 0 ? (
          <div className="table-scroll">
            <table className="responsive-table">
              <thead>
                <tr>
                  <th scope="col">{t("payroll.grantId")}</th>
                  <th scope="col">{t("payroll.provider")}</th>
                  <th scope="col">{t("payroll.providerId")}</th>
                  <th scope="col">{t("payroll.scope")}</th>
                  <th scope="col">{t("payroll.status")}</th>
                  <th scope="col">{t("payroll.grantedAt")}</th>
                  {isOwner ? <th scope="col">{t("payroll.actions")}</th> : null}
                </tr>
              </thead>
              <tbody>
                {authorised.map((auth) => {
                  const isRevoked = auth.status === "REVOKED";
                  return (
                    <tr key={auth.grant_id}>
                      <td data-label={t("payroll.grantId")}>
                        <code>{auth.grant_id}</code>
                      </td>
                      <td data-label={t("payroll.provider")}>
                        <strong>{auth.name}</strong>
                      </td>
                      <td data-label={t("payroll.providerId")}>
                        <code>{auth.provider_id}</code>
                      </td>
                      <td data-label={t("payroll.scope")}>
                        {auth.scopes.map(formatScope).join(", ")}
                      </td>
                      <td data-label={t("payroll.status")}>
                        <span className={`state-pill ${isRevoked ? "state-pill-revoked" : "state-pill-active"}`}>
                          {auth.status}
                        </span>
                      </td>
                      <td data-label={t("payroll.grantedAt")}>
                        {ddmmyyyy(auth.granted_at)}
                      </td>
                      {isOwner ? (
                        <td data-label={t("payroll.actions")}>
                          {!isRevoked ? (
                            <form
                              className="revoke-form"
                              onSubmit={(e) => {
                                e.preventDefault();
                                void handleRevoke(auth);
                              }}
                            >
                              <div className="revoke-input-group">
                                <label
                                  htmlFor={`revoke-reason-${auth.grant_id}`}
                                  className="visually-hidden"
                                >
                                  {t("payroll.revokeReasonLabel")}
                                </label>
                                <input
                                  id={`revoke-reason-${auth.grant_id}`}
                                  name="reason"
                                  type="text"
                                  aria-label={t("payroll.revokeReasonLabel")}
                                  placeholder={t("payroll.revokeReasonPlaceholder")}
                                  value={revokeReasons[auth.grant_id] || ""}
                                  onChange={(e) =>
                                    setRevokeReasons((prev) => ({
                                      ...prev,
                                      [auth.grant_id]: e.target.value,
                                    }))
                                  }
                                  disabled={busy}
                                  minLength={5}
                                  maxLength={300}
                                />
                              </div>
                              <button
                                type="submit"
                                className="button alert"
                                disabled={busy}
                              >
                                {t("payroll.revoke")}
                              </button>
                            </form>
                          ) : (
                            <span className="muted small">—</span>
                          )}
                        </td>
                      ) : null}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <section className="card stack" aria-labelledby="available-providers-heading">
        <div className="section-heading">
          <div>
            <h2 id="available-providers-heading">{t("payroll.availableHeading")}</h2>
          </div>
        </div>

        {providersQuery.isLoading ? (
          <p className="muted" role="status">Loading...</p>
        ) : null}

        {!providersQuery.isLoading && available.length === 0 ? (
          <p className="muted">{t("payroll.noAvailable")}</p>
        ) : null}

        {available.length > 0 ? (
          <div className="table-scroll">
            <table className="responsive-table">
              <thead>
                <tr>
                  <th scope="col">{t("payroll.provider")}</th>
                  <th scope="col">{t("payroll.providerId")}</th>
                  {isOwner ? <th scope="col">{t("payroll.actions")}</th> : null}
                </tr>
              </thead>
              <tbody>
                {available.map((provider) => {
                  const isActive = authorised.some(
                    (a) => a.provider_id === provider.provider_id && a.status === "ACTIVE"
                  );
                  return (
                    <tr key={provider.provider_id}>
                      <td data-label={t("payroll.provider")}>
                        <strong>{provider.name}</strong>
                      </td>
                      <td data-label={t("payroll.providerId")}>
                        <code>{provider.provider_id}</code>
                      </td>
                      {isOwner ? (
                        <td data-label={t("payroll.actions")}>
                          {isActive ? (
                            <span className="state-pill state-pill-active">
                              {t("payroll.alreadyAuthorised")}
                            </span>
                          ) : (
                            <button
                              type="button"
                              className="primary"
                              disabled={busy}
                              onClick={() => void handleAuthorise(provider)}
                            >
                              {t("payroll.authorise")}
                            </button>
                          )}
                        </td>
                      ) : null}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <StepUpDialog
        request={stepUp.request}
        onConfirmed={stepUp.onConfirmed}
        onCancel={stepUp.onCancel}
      />
    </section>
  );
}
