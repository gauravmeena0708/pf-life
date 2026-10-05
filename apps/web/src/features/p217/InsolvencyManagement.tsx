import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, command, rupees, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import i18n from "../../i18n";
import enP217 from "../../i18n/p217-compliance-service.en.json";
import hiP217 from "../../i18n/p217-compliance-service.hi.json";

// Ensure P2.17 translations are registered locally without touching shared i18n
if (!i18n.hasResourceBundle("en", "translation") || !i18n.getResourceBundle("en", "translation")?.p217) {
  i18n.addResourceBundle("en", "translation", enP217, true, true);
  i18n.addResourceBundle("hi", "translation", hiP217, true, true);
}

export interface WatchlistSignal {
  ecr_stopped: boolean;
  last_ecr_month: string | null;
  months_unfiled: number;
  open_demands_count: number;
  open_demands_paise: number;
  mca_status: string | null;
}

export interface WatchlistItem {
  establishment_id: string;
  legal_name: string;
  score: number;
  risk_level: "HIGH" | "MEDIUM" | "LOW";
  reasons: string[];
  signals: WatchlistSignal;
}

export interface WatchlistResponse {
  as_of: string;
  office_id: string;
  total_flagged: number;
  watchlist: WatchlistItem[];
}

export interface InsolvencyCase {
  case_id: string;
  establishment_id: string;
  legal_name?: string;
  office_id: string;
  stage: "CIRP" | "LIQUIDATION";
  practitioner_type: "IRP" | "RP" | "LIQUIDATOR";
  practitioner_name: string;
  practitioner_email?: string | null;
  announcement_date: string;
  claim_deadline: string;
  claim_period_days: number;
  nclt_bench?: string | null;
  order_ref?: string | null;
  claim_filed: boolean;
  claim_filed_at?: string | null;
  claim_reference?: string | null;
  form_type?: string | null;
  claimed_principal_paise: number;
  claimed_damages_paise: number;
  claimed_interest_paise: number;
  total_claimed_paise: number;
  moratorium_active: boolean;
  outside_liquidation_estate: boolean;
  resolution_plan?: {
    plan_reference: string;
    resolution_applicant?: string;
    plan_principal_paise: number;
    plan_damages_paise: number;
    plan_interest_paise: number;
    is_compliant: boolean;
    status: "COMPLIANT" | "NON_COMPLIANT";
    compliance_reason: string;
  } | null;
  plan_status?: "COMPLIANT" | "NON_COMPLIANT" | null;
  realised_paise: number;
  recovery_pct: number;
  outstanding_paise: number;
  state: string;
  warning?: string | null;
  warning_code?: string | null;
  days_to_deadline?: number;
  created_at: string;
}

export interface OfficeSummary {
  as_of: string;
  office_id: string;
  total_cases: number;
  by_stage: Record<string, number>;
  by_state: Record<string, number>;
  claims_pending: number;
  claims_filed: number;
  claims_due_soon: number;
  total_claimed_paise: number;
  total_recovered_paise: number;
  overall_recovery_pct: number;
  resolution_plans: {
    compliant: number;
    non_compliant: number;
    total: number;
  };
  moratorium_active_cases: number;
}

export interface DuesSummary {
  case_id: string;
  establishment_id: string;
  principal_paise: number;
  damages_paise: number;
  interest_paise: number;
  total_dues_paise: number;
  demands: {
    demand_id: string;
    kind: string;
    wage_month?: string | null;
    amount_paise: number;
  }[];
}

const text = (f: FormData, k: string) => String(f.get(k) ?? "").trim();

export function InsolvencyManagementPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();

  const [activeTab, setActiveTab] = useState<"watchlist" | "cases" | "summary">("watchlist");
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [successNotice, setSuccessNotice] = useState<string | null>(null);

  // Queries
  const watchlistQuery = useQuery({
    queryKey: ["insolvency-watchlist"],
    queryFn: () => api<Envelope<WatchlistResponse>>("/api/v1/office/compliance/insolvency/watchlist"),
    enabled: activeTab === "watchlist",
  });

  const casesQuery = useQuery({
    queryKey: ["insolvency-cases"],
    queryFn: () => api<Envelope<InsolvencyCase[]>>("/api/v1/office/compliance/insolvency-cases"),
    enabled: activeTab === "cases",
  });

  const selectedCaseQuery = useQuery({
    queryKey: ["insolvency-case", selectedCaseId],
    queryFn: () => api<Envelope<InsolvencyCase>>(`/api/v1/office/compliance/insolvency-cases/${selectedCaseId}`),
    enabled: Boolean(selectedCaseId && activeTab === "cases"),
  });

  const duesQuery = useQuery({
    queryKey: ["insolvency-dues", selectedCaseId],
    queryFn: () => api<Envelope<DuesSummary>>(`/api/v1/office/compliance/insolvency-cases/${selectedCaseId}/dues-summary`),
    enabled: Boolean(selectedCaseId && activeTab === "cases"),
  });

  const summaryQuery = useQuery({
    queryKey: ["insolvency-summary"],
    queryFn: () => api<Envelope<OfficeSummary>>("/api/v1/office/compliance/insolvency/summary"),
    enabled: activeTab === "summary",
  });

  async function executeAction(actionFn: () => Promise<string | null>) {
    setError(null);
    setSuccessNotice(null);
    try {
      const msg = await actionFn();
      if (msg) setSuccessNotice(msg);
      await qc.invalidateQueries({ queryKey: ["insolvency-watchlist"] });
      await qc.invalidateQueries({ queryKey: ["insolvency-cases"] });
      if (selectedCaseId) {
        await qc.invalidateQueries({ queryKey: ["insolvency-case", selectedCaseId] });
        await qc.invalidateQueries({ queryKey: ["insolvency-dues", selectedCaseId] });
      }
      await qc.invalidateQueries({ queryKey: ["insolvency-summary"] });
    } catch (err) {
      setError(err);
    }
  }

  // Form submit handlers
  const handleRecordAnnouncement = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const body = {
      establishment_id: text(f, "establishment_id"),
      stage: text(f, "stage"),
      practitioner_type: text(f, "practitioner_type"),
      practitioner_name: text(f, "practitioner_name"),
      practitioner_email: text(f, "practitioner_email") || undefined,
      announcement_date: text(f, "announcement_date"),
      claim_period_days: Number(text(f, "claim_period_days")) || 14,
      nclt_bench: text(f, "nclt_bench") || undefined,
      order_ref: text(f, "order_ref") || undefined,
      note: text(f, "note") || undefined,
    };

    void executeAction(async () => {
      const res = await command<Envelope<InsolvencyCase>>("POST", "/api/v1/office/compliance/insolvency-cases", body);
      setSelectedCaseId(res.data.case_id);
      return `Announcement recorded. Case ${res.data.case_id} opened. Claim deadline: ${res.data.claim_deadline}`;
    });
  };

  const handleFileClaim = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!selectedCaseId) return;
    const f = new FormData(e.currentTarget);
    const body = {
      claim_reference: text(f, "claim_reference"),
      form_type: text(f, "form_type"),
      principal_paise: Math.round(Number(text(f, "principal_rupees")) * 100),
      damages_paise: Math.round(Number(text(f, "damages_rupees") || "0") * 100),
      interest_paise: Math.round(Number(text(f, "interest_rupees") || "0") * 100),
      note: text(f, "note") || undefined,
    };

    void executeAction(async () => {
      const res = await command<Envelope<InsolvencyCase>>("POST", `/api/v1/office/compliance/insolvency-cases/${selectedCaseId}/claims`, body);
      return `Proof of claim ${res.data.claim_reference} submitted successfully for ${rupees(res.data.total_claimed_paise)}.`;
    });
  };

  const handleVerifyPlan = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!selectedCaseId) return;
    const f = new FormData(e.currentTarget);
    const body = {
      plan_reference: text(f, "plan_reference"),
      resolution_applicant: text(f, "resolution_applicant") || undefined,
      plan_principal_paise: Math.round(Number(text(f, "plan_principal_rupees")) * 100),
      plan_damages_paise: Math.round(Number(text(f, "plan_damages_rupees") || "0") * 100),
      plan_interest_paise: Math.round(Number(text(f, "plan_interest_rupees") || "0") * 100),
      note: text(f, "note") || undefined,
    };

    void executeAction(async () => {
      const res = await command<Envelope<InsolvencyCase>>("POST", `/api/v1/office/compliance/insolvency-cases/${selectedCaseId}/resolution-plans`, body);
      const plan = res.data.resolution_plan;
      return `Resolution plan evaluated: ${plan?.status}. ${plan?.compliance_reason}`;
    });
  };

  const handleRecordRealisation = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!selectedCaseId) return;
    const f = new FormData(e.currentTarget);
    const body = {
      amount_paise: Math.round(Number(text(f, "recovery_amount_rupees")) * 100),
      mode: text(f, "recovery_mode"),
      reference: text(f, "recovery_ref"),
      realised_on: text(f, "recovery_date"),
      note: text(f, "note") || undefined,
    };

    void executeAction(async () => {
      const res = await command<Envelope<InsolvencyCase>>("POST", `/api/v1/office/compliance/insolvency-cases/${selectedCaseId}/realisations`, body);
      return `Realisation recorded. Total recovered: ${rupees(res.data.realised_paise)} (${res.data.recovery_pct}%).`;
    });
  };

  return (
    <main style={{ padding: "1.5rem", maxWidth: "1200px", margin: "0 auto", color: "var(--navy)", fontFamily: "Segoe UI, Trebuchet MS, sans-serif" }}>
      <header style={{ borderBottom: "3px solid var(--gold)", paddingBottom: "1rem", marginBottom: "1.5rem" }}>
        <h1 style={{ margin: 0, fontSize: "1.75rem", color: "var(--navy)", fontFamily: "Georgia, serif" }}>{t("p217.title")}</h1>
        <p style={{ margin: "0.25rem 0 0", color: "var(--muted)", fontSize: "0.95rem" }}>{t("p217.subtitle")}</p>
        <div style={{ marginTop: "0.75rem", padding: "0.75rem", backgroundColor: "var(--bg)", borderLeft: "4px solid var(--w)", fontSize: "0.85rem", color: "var(--w)" }}>
          <strong>{t("p217.statutory_notice")}</strong>
        </div>
      </header>

      {/* Notifications / Alerts */}
      <div aria-live="polite" style={{ marginBottom: "1rem" }}>
        {error ? <ProblemMessage error={error} /> : null}
        {successNotice && (
          <div role="status" style={{ padding: "0.75rem", backgroundColor: "var(--bg)", border: "1px solid var(--w)", borderRadius: "4px", color: "var(--navy)", fontWeight: 600 }}>
            {successNotice}
          </div>
        )}
      </div>

      {/* Navigation Tabs */}
      <nav aria-label="Insolvency views" style={{ display: "flex", gap: "0.5rem", borderBottom: "2px solid var(--line)", marginBottom: "1.5rem" }}>
        <button
          type="button"
          onClick={() => setActiveTab("watchlist")}
          style={{
            padding: "0.6rem 1.2rem",
            backgroundColor: activeTab === "watchlist" ? "var(--navy)" : "var(--bg)",
            color: activeTab === "watchlist" ? "var(--surface)" : "var(--navy)",
            border: "1px solid var(--line)",
            borderBottom: activeTab === "watchlist" ? "3px solid var(--gold)" : "1px solid var(--line)",
            fontWeight: activeTab === "watchlist" ? 600 : 400,
            cursor: "pointer",
          }}
        >
          {t("p217.tab_watchlist")}
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("cases")}
          style={{
            padding: "0.6rem 1.2rem",
            backgroundColor: activeTab === "cases" ? "var(--navy)" : "var(--bg)",
            color: activeTab === "cases" ? "var(--surface)" : "var(--navy)",
            border: "1px solid var(--line)",
            borderBottom: activeTab === "cases" ? "3px solid var(--gold)" : "1px solid var(--line)",
            fontWeight: activeTab === "cases" ? 600 : 400,
            cursor: "pointer",
          }}
        >
          {t("p217.tab_cases")}
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("summary")}
          style={{
            padding: "0.6rem 1.2rem",
            backgroundColor: activeTab === "summary" ? "var(--navy)" : "var(--bg)",
            color: activeTab === "summary" ? "var(--surface)" : "var(--navy)",
            border: "1px solid var(--line)",
            borderBottom: activeTab === "summary" ? "3px solid var(--gold)" : "1px solid var(--line)",
            fontWeight: activeTab === "summary" ? 600 : 400,
            cursor: "pointer",
          }}
        >
          {t("p217.tab_summary")}
        </button>
      </nav>

      {/* Tab 1: Watchlist & Signals */}
      {activeTab === "watchlist" && (
        <section aria-labelledby="watchlist-heading">
          <h2 id="watchlist-heading" style={{ fontSize: "1.3rem", color: "var(--navy)", marginBottom: "1rem" }}>
            {t("p217.flagged_establishments")}
          </h2>

          {watchlistQuery.isLoading && <p>Loading signals watchlist...</p>}
          {watchlistQuery.data?.data && (
            <div>
              {watchlistQuery.data.data.watchlist.length === 0 ? (
                <p style={{ color: "var(--muted)" }}>{t("p217.no_watchlist")}</p>
              ) : (
                <div style={{ display: "grid", gap: "1rem" }}>
                  {watchlistQuery.data.data.watchlist.map((item) => (
                    <article
                      key={item.establishment_id}
                      style={{
                        backgroundColor: "var(--surface)",
                        border: "1px solid var(--line)",
                        borderLeft: `5px solid ${item.risk_level === "HIGH" ? "var(--q)" : item.risk_level === "MEDIUM" ? "var(--gold)" : "var(--w)"}`,
                        padding: "1rem",
                        boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                        <div>
                          <strong style={{ fontSize: "1.1rem", color: "var(--navy)" }}>{item.legal_name}</strong>
                          <span style={{ marginLeft: "0.5rem", fontSize: "0.85rem", color: "var(--muted)" }}>({item.establishment_id})</span>
                        </div>
                        <span
                          style={{
                            padding: "0.25rem 0.5rem",
                            borderRadius: "4px",
                            fontSize: "0.8rem",
                            fontWeight: 700,
                            backgroundColor: item.risk_level === "HIGH" ? "var(--bg)" : item.risk_level === "MEDIUM" ? "var(--bg)" : "var(--bg)",
                            color: item.risk_level === "HIGH" ? "var(--q)" : item.risk_level === "MEDIUM" ? "var(--gold)" : "var(--navy)",
                          }}
                        >
                          {item.risk_level === "HIGH" ? t("p217.risk_high") : item.risk_level === "MEDIUM" ? t("p217.risk_medium") : t("p217.risk_low")} ({item.score} pts)
                        </span>
                      </div>
                      <div style={{ fontSize: "0.9rem", color: "var(--muted)" }}>
                        <strong>{t("p217.reasons")}:</strong>
                        <ul style={{ margin: "0.25rem 0 0", paddingLeft: "1.25rem" }}>
                          {item.reasons.map((r, idx) => (
                            <li key={idx}>{r}</li>
                          ))}
                        </ul>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {/* Tab 2: Insolvency Cases */}
      {activeTab === "cases" && (
        <section aria-labelledby="cases-heading">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
            {/* Left Column: Record Announcement Form & Cases List */}
            <div>
              <article style={{ backgroundColor: "var(--surface)", border: "1px solid var(--line)", padding: "1rem", marginBottom: "1.5rem" }}>
                <h2 style={{ fontSize: "1.15rem", margin: "0 0 1rem", color: "var(--navy)" }}>{t("p217.record_announcement_heading")}</h2>
                <form onSubmit={handleRecordAnnouncement} style={{ display: "grid", gap: "0.75rem" }}>
                  <div>
                    <label htmlFor="ann_est_id" style={{ display: "block", fontSize: "0.85rem", fontWeight: 600 }}>{t("p217.establishment_id")} *</label>
                    <input id="ann_est_id" name="establishment_id" required defaultValue="EST-DEMO-0002" style={{ width: "100%", padding: "0.4rem" }} />
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
                    <div>
                      <label htmlFor="ann_stage" style={{ display: "block", fontSize: "0.85rem", fontWeight: 600 }}>{t("p217.stage")} *</label>
                      <select id="ann_stage" name="stage" style={{ width: "100%", padding: "0.4rem" }}>
                        <option value="CIRP">{t("p217.stage_cirp")}</option>
                        <option value="LIQUIDATION">{t("p217.stage_liquidation")}</option>
                      </select>
                    </div>
                    <div>
                      <label htmlFor="ann_role" style={{ display: "block", fontSize: "0.85rem", fontWeight: 600 }}>{t("p217.practitioner_type")} *</label>
                      <select id="ann_role" name="practitioner_type" style={{ width: "100%", padding: "0.4rem" }}>
                        <option value="IRP">{t("p217.irp")}</option>
                        <option value="RP">{t("p217.rp")}</option>
                        <option value="LIQUIDATOR">{t("p217.liquidator")}</option>
                      </select>
                    </div>
                  </div>
                  <div>
                    <label htmlFor="ann_name" style={{ display: "block", fontSize: "0.85rem", fontWeight: 600 }}>{t("p217.practitioner_name")} *</label>
                    <input id="ann_name" name="practitioner_name" required defaultValue="Shri V. Sharma, IP" style={{ width: "100%", padding: "0.4rem" }} />
                  </div>
                  <div>
                    <label htmlFor="ann_email" style={{ display: "block", fontSize: "0.85rem", fontWeight: 600 }}>{t("p217.practitioner_email")}</label>
                    <input id="ann_email" name="practitioner_email" type="email" defaultValue="v.sharma@insolvency.demo.invalid" style={{ width: "100%", padding: "0.4rem" }} />
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
                    <div>
                      <label htmlFor="ann_date" style={{ display: "block", fontSize: "0.85rem", fontWeight: 600 }}>{t("p217.announcement_date")} *</label>
                      <input id="ann_date" name="announcement_date" type="date" required defaultValue="2026-10-01" style={{ width: "100%", padding: "0.4rem" }} />
                    </div>
                    <div>
                      <label htmlFor="ann_period" style={{ display: "block", fontSize: "0.85rem", fontWeight: 600 }}>{t("p217.claim_period_days")} *</label>
                      <input id="ann_period" name="claim_period_days" type="number" required defaultValue="14" style={{ width: "100%", padding: "0.4rem" }} />
                    </div>
                  </div>
                  <button
                    type="submit"
                    style={{
                      backgroundColor: "var(--navy)",
                      color: "var(--surface)",
                      padding: "0.6rem",
                      fontWeight: 600,
                      border: "none",
                      cursor: "pointer",
                      marginTop: "0.5rem",
                    }}
                  >
                    {t("p217.submit_announcement_btn")}
                  </button>
                </form>
              </article>

              {/* Case list */}
              <h2 id="cases-heading" style={{ fontSize: "1.15rem", color: "var(--navy)" }}>{t("p217.cases_heading")}</h2>
              {casesQuery.isLoading && <p>Loading cases...</p>}
              {casesQuery.data?.data && (
                <div style={{ display: "grid", gap: "0.75rem" }}>
                  {casesQuery.data.data.length === 0 ? (
                    <p style={{ color: "var(--muted)" }}>{t("p217.no_cases")}</p>
                  ) : (
                    casesQuery.data.data.map((c) => (
                      <div
                        key={c.case_id}
                        onClick={() => setSelectedCaseId(c.case_id)}
                        style={{
                          padding: "0.75rem",
                          border: selectedCaseId === c.case_id ? "2px solid var(--gold)" : "1px solid var(--line)",
                          backgroundColor: selectedCaseId === c.case_id ? "var(--bg)" : "var(--surface)",
                          cursor: "pointer",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <strong>{c.case_id}</strong>
                          <span style={{ fontSize: "0.85rem", fontWeight: 600, color: c.stage === "CIRP" ? "var(--w)" : "var(--w)" }}>{c.stage}</span>
                        </div>
                        <div style={{ fontSize: "0.9rem", color: "var(--muted)", marginTop: "0.25rem" }}>
                          {c.legal_name || c.establishment_id}
                        </div>
                        <div style={{ fontSize: "0.8rem", color: "var(--muted)", marginTop: "0.25rem" }}>
                          {t("p217.claim_deadline")}: <strong>{c.claim_deadline}</strong>
                        </div>
                        {c.warning && (
                          <div style={{ fontSize: "0.8rem", color: "var(--q)", backgroundColor: "var(--bg)", padding: "0.25rem 0.5rem", marginTop: "0.5rem", borderRadius: "3px" }}>
                            {c.warning}
                          </div>
                        )}
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>

            {/* Right Column: Selected Case Details & Actions */}
            <div>
              {selectedCaseQuery.data?.data ? (
                (() => {
                  const c = selectedCaseQuery.data.data;
                  return (
                    <article style={{ backgroundColor: "var(--surface)", border: "1px solid var(--line)", padding: "1.25rem" }}>
                      <div style={{ borderBottom: "2px solid var(--line)", paddingBottom: "0.75rem", marginBottom: "1rem" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <h3 style={{ margin: 0, color: "var(--navy)", fontSize: "1.25rem" }}>{c.case_id}</h3>
                          <span style={{ padding: "0.2rem 0.6rem", backgroundColor: "var(--navy)", color: "var(--surface)", fontSize: "0.8rem", borderRadius: "4px" }}>
                            {c.state}
                          </span>
                        </div>
                        <p style={{ margin: "0.25rem 0 0", color: "var(--muted)" }}>{c.legal_name} ({c.establishment_id})</p>
                      </div>

                      {/* Warnings / Moratorium Status */}
                      {c.warning && (
                        <div role="alert" style={{ padding: "0.75rem", backgroundColor: "var(--bg)", borderLeft: "4px solid var(--q)", color: "var(--q)", marginBottom: "1rem", fontSize: "0.9rem" }}>
                          <strong>{c.warning}</strong>
                        </div>
                      )}

                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem", marginBottom: "1rem", fontSize: "0.85rem" }}>
                        <div>
                          <span style={{ color: "var(--muted)" }}>{t("p217.moratorium_status")}:</span>{" "}
                          <strong style={{ color: c.moratorium_active ? "var(--w)" : "var(--muted)" }}>
                            {c.moratorium_active ? t("p217.moratorium_active") : t("p217.moratorium_inactive")}
                          </strong>
                        </div>
                        <div>
                          <span style={{ color: "var(--muted)" }}>{t("p217.outside_estate")}:</span>{" "}
                          <strong style={{ color: c.outside_liquidation_estate ? "var(--w)" : "var(--muted)" }}>
                            {c.outside_liquidation_estate ? "YES (IBC s.36(4)(a)(iii))" : "N/A (CIRP)"}
                          </strong>
                        </div>
                        <div>
                          <span style={{ color: "var(--muted)" }}>{t("p217.dues_claimed")}:</span>{" "}
                          <strong>₹{(c.total_claimed_paise / 100).toLocaleString("en-IN")}</strong>
                        </div>
                        <div>
                          <span style={{ color: "var(--muted)" }}>{t("p217.dues_recovered")}:</span>{" "}
                          <strong>₹{(c.realised_paise / 100).toLocaleString("en-IN")} ({c.recovery_pct}%)</strong>
                        </div>
                      </div>

                      {/* Action 1: File Proof of Claim */}
                      {!c.claim_filed && (
                        <section style={{ border: "1px solid var(--line)", padding: "1rem", marginBottom: "1rem", backgroundColor: "var(--bg)" }}>
                          <h4 style={{ margin: "0 0 0.75rem", color: "var(--navy)", fontSize: "1rem" }}>{t("p217.file_claim_heading")}</h4>
                          {duesQuery.data?.data && (
                            <div style={{ fontSize: "0.85rem", marginBottom: "0.75rem", padding: "0.5rem", backgroundColor: "var(--bg)" }}>
                              <div>PF Principal: <strong>₹{(duesQuery.data.data.principal_paise / 100).toLocaleString("en-IN")}</strong></div>
                              <div>Damages s.14B: <strong>₹{(duesQuery.data.data.damages_paise / 100).toLocaleString("en-IN")}</strong></div>
                              <div>Interest s.7Q: <strong>₹{(duesQuery.data.data.interest_paise / 100).toLocaleString("en-IN")}</strong></div>
                            </div>
                          )}
                          <form onSubmit={handleFileClaim} style={{ display: "grid", gap: "0.5rem" }}>
                            <div>
                              <label htmlFor="claim_ref" style={{ display: "block", fontSize: "0.8rem", fontWeight: 600 }}>{t("p217.claim_reference")} *</label>
                              <input id="claim_ref" name="claim_reference" required defaultValue={`CLAIM/${c.establishment_id}/01`} style={{ width: "100%", padding: "0.35rem" }} />
                            </div>
                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.5rem" }}>
                              <div>
                                <label htmlFor="pr_amt" style={{ display: "block", fontSize: "0.8rem", fontWeight: 600 }}>{t("p217.principal_rupees")} *</label>
                                <input id="pr_amt" name="principal_rupees" type="number" required defaultValue={(duesQuery.data?.data?.principal_paise ?? 0) / 100} style={{ width: "100%", padding: "0.35rem" }} />
                              </div>
                              <div>
                                <label htmlFor="dmg_amt" style={{ display: "block", fontSize: "0.8rem", fontWeight: 600 }}>{t("p217.damages_rupees")}</label>
                                <input id="dmg_amt" name="damages_rupees" type="number" defaultValue={(duesQuery.data?.data?.damages_paise ?? 0) / 100} style={{ width: "100%", padding: "0.35rem" }} />
                              </div>
                              <div>
                                <label htmlFor="int_amt" style={{ display: "block", fontSize: "0.8rem", fontWeight: 600 }}>{t("p217.interest_rupees")}</label>
                                <input id="int_amt" name="interest_rupees" type="number" defaultValue={(duesQuery.data?.data?.interest_paise ?? 0) / 100} style={{ width: "100%", padding: "0.35rem" }} />
                              </div>
                            </div>
                            <button type="submit" style={{ backgroundColor: "var(--navy)", color: "var(--surface)", padding: "0.5rem", border: "none", cursor: "pointer", fontWeight: 600 }}>
                              {t("p217.file_claim_btn")}
                            </button>
                          </form>
                        </section>
                      )}

                      {/* Action 2: Check Resolution Plan (CIRP) */}
                      {c.claim_filed && c.stage === "CIRP" && (
                        <section style={{ border: "1px solid var(--line)", padding: "1rem", marginBottom: "1rem", backgroundColor: "var(--bg)" }}>
                          <h4 style={{ margin: "0 0 0.75rem", color: "var(--navy)", fontSize: "1rem" }}>{t("p217.check_plan_heading")}</h4>
                          {c.resolution_plan && (
                            <div style={{ marginBottom: "0.75rem", padding: "0.5rem", backgroundColor: c.resolution_plan.is_compliant ? "var(--bg)" : "var(--bg)", fontSize: "0.85rem" }}>
                              <strong>Status: {c.resolution_plan.status}</strong>
                              <p style={{ margin: "0.25rem 0 0" }}>{c.resolution_plan.compliance_reason}</p>
                            </div>
                          )}
                          <form onSubmit={handleVerifyPlan} style={{ display: "grid", gap: "0.5rem" }}>
                            <div>
                              <label htmlFor="plan_ref" style={{ display: "block", fontSize: "0.8rem", fontWeight: 600 }}>{t("p217.plan_reference")} *</label>
                              <input id="plan_ref" name="plan_reference" required defaultValue="PLAN-001" style={{ width: "100%", padding: "0.35rem" }} />
                            </div>
                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.5rem" }}>
                              <div>
                                <label htmlFor="plan_pr_amt" style={{ display: "block", fontSize: "0.8rem", fontWeight: 600 }}>{t("p217.plan_principal_rupees")} *</label>
                                <input id="plan_pr_amt" name="plan_principal_rupees" type="number" required defaultValue={c.claimed_principal_paise / 100} style={{ width: "100%", padding: "0.35rem" }} />
                              </div>
                              <div>
                                <label htmlFor="plan_dmg_amt" style={{ display: "block", fontSize: "0.8rem", fontWeight: 600 }}>{t("p217.plan_damages_rupees")}</label>
                                <input id="plan_dmg_amt" name="plan_damages_rupees" type="number" defaultValue="0" style={{ width: "100%", padding: "0.35rem" }} />
                              </div>
                              <div>
                                <label htmlFor="plan_int_amt" style={{ display: "block", fontSize: "0.8rem", fontWeight: 600 }}>{t("p217.plan_interest_rupees")}</label>
                                <input id="plan_int_amt" name="plan_interest_rupees" type="number" defaultValue="0" style={{ width: "100%", padding: "0.35rem" }} />
                              </div>
                            </div>
                            <button type="submit" style={{ backgroundColor: "var(--gold)", color: "var(--surface)", padding: "0.5rem", border: "none", cursor: "pointer", fontWeight: 600 }}>
                              {t("p217.verify_plan_btn")}
                            </button>
                          </form>
                        </section>
                      )}

                      {/* Action 3: Record Realisation */}
                      {c.claim_filed && c.state !== "CLOSED" && (
                        <section style={{ border: "1px solid var(--line)", padding: "1rem", backgroundColor: "var(--bg)" }}>
                          <h4 style={{ margin: "0 0 0.75rem", color: "var(--navy)", fontSize: "1rem" }}>{t("p217.record_realisation_heading")}</h4>
                          <form onSubmit={handleRecordRealisation} style={{ display: "grid", gap: "0.5rem" }}>
                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
                              <div>
                                <label htmlFor="rec_amt" style={{ display: "block", fontSize: "0.8rem", fontWeight: 600 }}>{t("p217.recovery_amount_rupees")} *</label>
                                <input id="rec_amt" name="recovery_amount_rupees" type="number" required defaultValue="50000" style={{ width: "100%", padding: "0.35rem" }} />
                              </div>
                              <div>
                                <label htmlFor="rec_mode" style={{ display: "block", fontSize: "0.8rem", fontWeight: 600 }}>{t("p217.recovery_mode")} *</label>
                                <select id="rec_mode" name="recovery_mode" style={{ width: "100%", padding: "0.35rem" }}>
                                  <option value="RESOLUTION_PLAN">{t("p217.mode_resolution_plan")}</option>
                                  <option value="LIQUIDATION_PAYOUT">{t("p217.mode_liquidation")}</option>
                                  <option value="IRP_DISBURSEMENT">{t("p217.mode_irp")}</option>
                                  <option value="DIRECT">{t("p217.mode_direct")}</option>
                                </select>
                              </div>
                            </div>
                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
                              <div>
                                <label htmlFor="rec_ref" style={{ display: "block", fontSize: "0.8rem", fontWeight: 600 }}>{t("p217.recovery_ref")} *</label>
                                <input id="rec_ref" name="recovery_ref" required defaultValue="CHQ-2026-001" style={{ width: "100%", padding: "0.35rem" }} />
                              </div>
                              <div>
                                <label htmlFor="rec_date" style={{ display: "block", fontSize: "0.8rem", fontWeight: 600 }}>{t("p217.recovery_date")} *</label>
                                <input id="rec_date" name="recovery_date" type="date" required defaultValue="2026-10-01" style={{ width: "100%", padding: "0.35rem" }} />
                              </div>
                            </div>
                            <button type="submit" style={{ backgroundColor: "var(--w)", color: "var(--surface)", padding: "0.5rem", border: "none", cursor: "pointer", fontWeight: 600 }}>
                              {t("p217.record_realisation_btn")}
                            </button>
                          </form>
                        </section>
                      )}
                    </article>
                  );
                })()
              ) : (
                <div style={{ padding: "2rem", border: "1px dashed var(--line)", textAlign: "center", color: "var(--muted)" }}>
                  Select an insolvency case to view details, file claims, and check resolution plans.
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      {/* Tab 3: Office Summary */}
      {activeTab === "summary" && (
        <section aria-labelledby="summary-heading">
          <h2 id="summary-heading" style={{ fontSize: "1.3rem", color: "var(--navy)", marginBottom: "1rem" }}>
            {t("p217.summary_heading")}
          </h2>
          {summaryQuery.isLoading && <p>Loading office summary...</p>}
          {summaryQuery.data?.data && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "1rem" }}>
              <div style={{ backgroundColor: "var(--surface)", border: "1px solid var(--line)", padding: "1rem", borderTop: "4px solid var(--navy)" }}>
                <span style={{ fontSize: "0.85rem", color: "var(--muted)" }}>{t("p217.total_cases")}</span>
                <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--navy)", marginTop: "0.25rem" }}>
                  {summaryQuery.data.data.total_cases}
                </div>
              </div>
              <div style={{ backgroundColor: "var(--surface)", border: "1px solid var(--line)", padding: "1rem", borderTop: "4px solid var(--q)" }}>
                <span style={{ fontSize: "0.85rem", color: "var(--muted)" }}>{t("p217.claims_due_soon")}</span>
                <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--q)", marginTop: "0.25rem" }}>
                  {summaryQuery.data.data.claims_due_soon}
                </div>
              </div>
              <div style={{ backgroundColor: "var(--surface)", border: "1px solid var(--line)", padding: "1rem", borderTop: "4px solid var(--gold)" }}>
                <span style={{ fontSize: "0.85rem", color: "var(--muted)" }}>{t("p217.claims_pending")}</span>
                <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--gold)", marginTop: "0.25rem" }}>
                  {summaryQuery.data.data.claims_pending}
                </div>
              </div>
              <div style={{ backgroundColor: "var(--surface)", border: "1px solid var(--line)", padding: "1rem", borderTop: "4px solid var(--w)" }}>
                <span style={{ fontSize: "0.85rem", color: "var(--muted)" }}>{t("p217.claims_filed")}</span>
                <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--w)", marginTop: "0.25rem" }}>
                  {summaryQuery.data.data.claims_filed}
                </div>
              </div>
              <div style={{ backgroundColor: "var(--surface)", border: "1px solid var(--line)", padding: "1rem", borderTop: "4px solid var(--w)" }}>
                <span style={{ fontSize: "0.85rem", color: "var(--muted)" }}>{t("p217.total_claimed")}</span>
                <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--w)", marginTop: "0.25rem" }}>
                  ₹{(summaryQuery.data.data.total_claimed_paise / 100).toLocaleString("en-IN")}
                </div>
              </div>
              <div style={{ backgroundColor: "var(--surface)", border: "1px solid var(--line)", padding: "1rem", borderTop: "4px solid var(--w)" }}>
                <span style={{ fontSize: "0.85rem", color: "var(--muted)" }}>{t("p217.total_recovered")}</span>
                <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--w)", marginTop: "0.25rem" }}>
                  ₹{(summaryQuery.data.data.total_recovered_paise / 100).toLocaleString("en-IN")}
                </div>
              </div>
              <div style={{ backgroundColor: "var(--surface)", border: "1px solid var(--line)", padding: "1rem", borderTop: "4px solid var(--navy)" }}>
                <span style={{ fontSize: "0.85rem", color: "var(--muted)" }}>{t("p217.overall_recovery")}</span>
                <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--navy)", marginTop: "0.25rem" }}>
                  {summaryQuery.data.data.overall_recovery_pct}%
                </div>
              </div>
              <div style={{ backgroundColor: "var(--surface)", border: "1px solid var(--line)", padding: "1rem", borderTop: "4px solid var(--w)" }}>
                <span style={{ fontSize: "0.85rem", color: "var(--muted)" }}>{t("p217.compliant_plans")} / {t("p217.non_compliant_plans")}</span>
                <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--w)", marginTop: "0.25rem" }}>
                  {summaryQuery.data.data.resolution_plans.compliant} / {summaryQuery.data.data.resolution_plans.non_compliant}
                </div>
              </div>
            </div>
          )}
        </section>
      )}
    </main>
  );
}
