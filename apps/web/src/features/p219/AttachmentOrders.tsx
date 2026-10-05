import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, command, rupees, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import i18n from "../../i18n";
import enP219 from "../../i18n/p219-claim-service.en.json";
import hiP219 from "../../i18n/p219-claim-service.hi.json";

// Ensure P2.19 translations are registered without modifying shared index.ts
if (!i18n.hasResourceBundle("en", "translation") || !i18n.getResourceBundle("en", "translation")?.p219) {
  i18n.addResourceBundle("en", "translation", enP219, true, true);
  i18n.addResourceBundle("hi", "translation", hiP219, true, true);
}

export interface AttachmentOrder {
  order_id: string;
  order_number: string;
  court_name: string;
  order_date: string | null;
  order_type: string;
  amount_paise: number;
  target_uan: string;
  claim_id?: string | null;
  debtor_name?: string | null;
  status: "REFUSED" | "ACCEPTED";
  refusal_reason?: string | null;
  section?: string;
  payments_diverted: boolean;
  created_at: string | null;
}

const text = (f: FormData, k: string) => String(f.get(k) ?? "").trim();

/**
 * P2.19: Attachment orders under EPF Act s.10 and shared bank account fraud review.
 * Under EPF Act s.10, member balance, nominee amount, pension, and EDLI cannot be attached
 * under any court decree for member's debt. Maintenance orders are not exempt.
 * Payments are never diverted.
 */
export function AttachmentOrdersPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [lastOrder, setLastOrder] = useState<AttachmentOrder | null>(null);

  const list = useQuery({
    queryKey: ["office-attachment-orders"],
    retry: false,
    queryFn: () => api<Envelope<AttachmentOrder[]>>("/api/v1/office/attachment-orders"),
  });

  async function run(work: () => Promise<string | null>) {
    setError(null);
    setNotice(null);
    try {
      const done = await work();
      if (done) setNotice(done);
      await qc.invalidateQueries({ queryKey: ["office-attachment-orders"] });
    } catch (cause) {
      setError(cause);
    }
  }

  const recordOrder = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    const amountRupees = Number(text(f, "amount_rupees"));
    const amountPaise = Math.round(amountRupees * 100);

    void run(async () => {
      const payload = {
        order_number: text(f, "order_number"),
        court_name: text(f, "court_name"),
        order_date: text(f, "order_date"),
        order_type: text(f, "order_type"),
        amount_paise: amountPaise,
        target_uan: text(f, "target_uan"),
        claim_id: text(f, "claim_id") || undefined,
        debtor_name: text(f, "debtor_name") || undefined,
      };
      const res = await command<Envelope<AttachmentOrder>>("POST", "/api/v1/office/attachment-orders", payload);
      setLastOrder(res.data);
      form.reset();
      return `${res.data.order_id}: ${res.data.status} (${res.data.order_type === "EPF_ACT_RECOVERY" ? "Accepted under EPF Act" : "Refused under EPF Act s.10; payments never diverted"}).`;
    });
  };

  const clearHold = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    const claimId = text(f, "claim_id");
    const note = text(f, "note");

    void run(async () => {
      await command("POST", `/api/v1/office/claims/${claimId}/clear-hold`, { note });
      form.reset();
      return `Claim ${claimId}: Hold cleared. Proceeded to settlement processing.`;
    });
  };

  const orders = list.data?.data ?? [];

  return (
    <main className="stack" style={{ maxWidth: "1200px", margin: "0 auto", padding: "1.5rem" }}>
      <header
        style={{
          borderBottom: "3px solid var(--gold)",
          paddingBottom: "0.75rem",
          marginBottom: "1rem",
        }}
      >
        <h1 style={{ color: "var(--navy)", margin: 0 }}>{t("p219.title", "Attachment Orders & Fraud Prevention")}</h1>
        <p className="muted" style={{ margin: "0.25rem 0 0" }}>
          {t("p219.subtitle", "Record received court decree / garnishee attachment orders under EPF Act s.10 and review fraud hold claims.")}
        </p>
      </header>

      {/* Statutory Section 10 notice banner */}
      <aside
        style={{
          backgroundColor: "var(--bg)",
          borderLeft: "4px solid var(--navy)",
          padding: "1rem",
          borderRadius: "4px",
        }}
        aria-label="Statutory Section 10 Notice"
      >
        <strong style={{ color: "var(--navy)" }}>EPF Act s.10 Statutory Immunity:</strong>
        <p style={{ margin: "0.25rem 0 0", fontSize: "0.95rem" }}>
          {t(
            "p219.section10_notice",
            "Under Section 10 of the EPF Act, 1952, member provident fund accumulations, nominee amounts, pension, and EDLI benefits are immune from attachment under any decree or order of any court. Maintenance orders are not exempt. Only recovery orders under the EPF Act itself are accepted. Payments to members are never diverted."
          )}
        </p>
      </aside>

      <ProblemMessage error={error ?? list.error} />

      {/* Result feedback banner with aria-live */}
      <div aria-live="polite" aria-atomic="true">
        {notice ? (
          <div
            role="status"
            style={{
              padding: "0.75rem 1rem",
              backgroundColor: "var(--bg)",
              border: "1px solid var(--w)",
              color: "var(--w)",
              borderRadius: "4px",
              fontWeight: 500,
            }}
          >
            {notice}
          </div>
        ) : null}
      </div>

      {lastOrder ? (
        <article
          style={{
            border: `1px solid ${lastOrder.status === "REFUSED" ? "var(--q)" : "var(--w)"}`,
            backgroundColor: lastOrder.status === "REFUSED" ? "var(--bg)" : "var(--bg)",
            padding: "1rem",
            borderRadius: "4px",
          }}
          aria-live="polite"
        >
          <h2 style={{ fontSize: "1.1rem", margin: "0 0 0.5rem", color: lastOrder.status === "REFUSED" ? "var(--q)" : "var(--w)" }}>
            {lastOrder.status === "REFUSED" ? "Refusal Notice Generated (EPF Act s.10)" : "Order Accepted (EPF Act Recovery)"}
          </h2>
          <p style={{ margin: "0 0 0.25rem" }}>
            <strong>Order:</strong> {lastOrder.order_number} ({lastOrder.court_name}) · <strong>UAN:</strong> {lastOrder.target_uan} ·{" "}
            <strong>Amount:</strong> {rupees(lastOrder.amount_paise)}
          </p>
          {lastOrder.refusal_reason ? (
            <blockquote style={{ margin: "0.5rem 0 0", paddingLeft: "1rem", borderLeft: "3px solid var(--q)", color: "#555" }}>
              {lastOrder.refusal_reason}
            </blockquote>
          ) : null}
          <p style={{ margin: "0.5rem 0 0", fontWeight: 600, color: "var(--navy)" }}>
            Payments diverted: {lastOrder.payments_diverted ? "Yes" : "No (Payments remain protected for member/beneficiary)"}
          </p>
        </article>
      ) : null}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(350px, 1fr))", gap: "1.5rem" }}>
        {/* Attachment Order Recording Form */}
        <section
          style={{
            backgroundColor: "var(--surface)",
            border: "1px solid var(--line)",
            borderRadius: "6px",
            padding: "1.25rem",
            boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
          }}
        >
          <h2 style={{ color: "var(--navy)", fontSize: "1.2rem", marginTop: 0, borderBottom: "2px solid var(--gold)", paddingBottom: "0.5rem" }}>
            {t("p219.record_heading", "Record received attachment order")}
          </h2>
          <form className="stack" onSubmit={recordOrder} aria-label="Record received attachment order">
            <div>
              <label htmlFor="order_number" style={{ display: "block", fontWeight: 600, marginBottom: "0.25rem" }}>
                {t("p219.order_number", "Order number / Case reference")}
              </label>
              <input id="order_number" name="order_number" required minLength={3} style={{ width: "100%", padding: "0.5rem" }} />
            </div>

            <div>
              <label htmlFor="court_name" style={{ display: "block", fontWeight: 600, marginBottom: "0.25rem" }}>
                {t("p219.court_name", "Court / Issuing authority name")}
              </label>
              <input id="court_name" name="court_name" required minLength={3} style={{ width: "100%", padding: "0.5rem" }} />
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
              <div>
                <label htmlFor="order_date" style={{ display: "block", fontWeight: 600, marginBottom: "0.25rem" }}>
                  {t("p219.order_date", "Date of order")}
                </label>
                <input id="order_date" name="order_date" type="date" required style={{ width: "100%", padding: "0.5rem" }} />
              </div>
              <div>
                <label htmlFor="order_type" style={{ display: "block", fontWeight: 600, marginBottom: "0.25rem" }}>
                  {t("p219.order_type", "Order category")}
                </label>
                <select id="order_type" name="order_type" style={{ width: "100%", padding: "0.5rem" }}>
                  <option value="COURT_DECREE">{t("p219.court_decree", "Civil Court Decree")}</option>
                  <option value="MAINTENANCE_ORDER">{t("p219.maintenance_order", "Maintenance Order")}</option>
                  <option value="COMMERCIAL_DEBT">{t("p219.commercial_debt", "Commercial Debt Attachment")}</option>
                  <option value="EPF_ACT_RECOVERY">{t("p219.epf_act_recovery", "EPF Act Recovery (EPFO)")}</option>
                  <option value="OTHER">{t("p219.other_type", "Other Court Order")}</option>
                </select>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
              <div>
                <label htmlFor="amount_rupees" style={{ display: "block", fontWeight: 600, marginBottom: "0.25rem" }}>
                  {t("p219.amount_rupees", "Attachment amount (₹)")}
                </label>
                <input
                  id="amount_rupees"
                  name="amount_rupees"
                  type="number"
                  min="1"
                  step="0.01"
                  required
                  style={{ width: "100%", padding: "0.5rem" }}
                />
              </div>
              <div>
                <label htmlFor="target_uan" style={{ display: "block", fontWeight: 600, marginBottom: "0.25rem" }}>
                  {t("p219.target_uan", "Target Member UAN")}
                </label>
                <input
                  id="target_uan"
                  name="target_uan"
                  pattern="[0-9]{12}"
                  maxLength={12}
                  required
                  placeholder="100000000001"
                  style={{ width: "100%", padding: "0.5rem" }}
                />
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
              <div>
                <label htmlFor="claim_id" style={{ display: "block", fontWeight: 600, marginBottom: "0.25rem" }}>
                  {t("p219.claim_id", "Claim ID (if specified)")}
                </label>
                <input id="claim_id" name="claim_id" placeholder="CLM-..." style={{ width: "100%", padding: "0.5rem" }} />
              </div>
              <div>
                <label htmlFor="debtor_name" style={{ display: "block", fontWeight: 600, marginBottom: "0.25rem" }}>
                  {t("p219.debtor_name", "Debtor / Member name")}
                </label>
                <input id="debtor_name" name="debtor_name" placeholder="Member name" style={{ width: "100%", padding: "0.5rem" }} />
              </div>
            </div>

            <div style={{ marginTop: "1rem" }}>
              <button
                type="submit"
                style={{
                  backgroundColor: "var(--navy)",
                  color: "var(--surface)",
                  padding: "0.6rem 1.25rem",
                  border: "none",
                  borderRadius: "4px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {t("p219.submit_order", "Record order & verify immunity")}
              </button>
            </div>
          </form>
        </section>

        {/* Shared Account Hold Clearance Form */}
        <section
          style={{
            backgroundColor: "var(--surface)",
            border: "1px solid var(--line)",
            borderRadius: "6px",
            padding: "1.25rem",
            boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
          }}
        >
          <h2 style={{ color: "var(--navy)", fontSize: "1.2rem", marginTop: 0, borderBottom: "2px solid var(--gold)", paddingBottom: "0.5rem" }}>
            {t("p219.clear_hold_heading", "Shared bank account hold review")}
          </h2>
          <p className="muted" style={{ fontSize: "0.9rem", marginTop: 0 }}>
            {t(
              "p219.clear_hold_desc",
              "Review claims held due to shared bank account fraud pattern (same payee bank account across multiple members)."
            )}
          </p>

          <form className="stack" onSubmit={clearHold} aria-label="Clear shared bank account hold">
            <div>
              <label htmlFor="hold_claim_id" style={{ display: "block", fontWeight: 600, marginBottom: "0.25rem" }}>
                {t("p219.claim_id_label", "Held claim ID")}
              </label>
              <input id="hold_claim_id" name="claim_id" required placeholder="CLM-..." style={{ width: "100%", padding: "0.5rem" }} />
            </div>

            <div>
              <label htmlFor="hold_note" style={{ display: "block", fontWeight: 600, marginBottom: "0.25rem" }}>
                {t("p219.officer_note", "Officer verification note")}
              </label>
              <textarea
                id="hold_note"
                name="note"
                required
                minLength={5}
                rows={4}
                placeholder="Verified genuine identity documentation and payee account ownership..."
                style={{ width: "100%", padding: "0.5rem" }}
              />
            </div>

            <div style={{ marginTop: "1rem" }}>
              <button
                type="submit"
                style={{
                  backgroundColor: "var(--navy)",
                  color: "var(--surface)",
                  padding: "0.6rem 1.25rem",
                  border: "none",
                  borderRadius: "4px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {t("p219.clear_hold_btn", "Verify & clear hold")}
              </button>
            </div>
          </form>
        </section>
      </div>

      {/* Orders List Table */}
      <section
        style={{
          marginTop: "1.5rem",
          backgroundColor: "var(--surface)",
          border: "1px solid var(--line)",
          borderRadius: "6px",
          padding: "1.25rem",
          boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
        }}
      >
        <h2 style={{ color: "var(--navy)", fontSize: "1.2rem", marginTop: 0 }}>
          {t("p219.recorded_orders", "Recorded attachment orders in this office")}
        </h2>

        {orders.length ? (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "0.95rem" }}>
              <thead>
                <tr style={{ backgroundColor: "var(--navy)", color: "var(--surface)" }}>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Order ID</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Order / Court</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>UAN</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Amount</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Type</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Status</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Protection / s.10</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.order_id} style={{ borderBottom: "1px solid #eee" }}>
                    <td style={{ padding: "0.6rem 0.75rem", fontFamily: "monospace" }}>{o.order_id}</td>
                    <td style={{ padding: "0.6rem 0.75rem" }}>
                      <strong>{o.order_number}</strong>
                      <div className="muted small">{o.court_name}</div>
                    </td>
                    <td style={{ padding: "0.6rem 0.75rem", fontFamily: "monospace" }}>{o.target_uan}</td>
                    <td style={{ padding: "0.6rem 0.75rem", fontWeight: 600 }}>{rupees(o.amount_paise)}</td>
                    <td style={{ padding: "0.6rem 0.75rem" }}>{o.order_type}</td>
                    <td style={{ padding: "0.6rem 0.75rem" }}>
                      <span
                        style={{
                          display: "inline-block",
                          padding: "0.2rem 0.5rem",
                          borderRadius: "3px",
                          fontWeight: 600,
                          fontSize: "0.85rem",
                          backgroundColor: o.status === "REFUSED" ? "var(--bg)" : "var(--bg)",
                          color: o.status === "REFUSED" ? "var(--q)" : "var(--w)",
                        }}
                      >
                        {o.status}
                      </span>
                    </td>
                    <td style={{ padding: "0.6rem 0.75rem", fontSize: "0.85rem" }}>
                      {o.status === "REFUSED" ? (
                        <span style={{ color: "var(--q)" }}>Protected under s.10 (Payments not diverted)</span>
                      ) : (
                        <span style={{ color: "var(--w)" }}>EPF Act recovery order</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : list.isSuccess ? (
          <p className="muted">{t("p219.no_orders", "No attachment orders recorded in this office.")}</p>
        ) : null}
      </section>
    </main>
  );
}
