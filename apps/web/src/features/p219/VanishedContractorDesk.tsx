import { useState, type FormEvent } from "react";
import enTranslations from "../../i18n/p219-compliance-service.en.json";
import hiTranslations from "../../i18n/p219-compliance-service.hi.json";

export interface VanishedContractorDeskProps {
  role?: string;
  onOrderPassed?: (orderDetail: Record<string, unknown>) => void;
}

export function VanishedContractorDesk({ onOrderPassed }: VanishedContractorDeskProps) {
  const [lang, setLang] = useState<"en" | "hi">("en");
  const t = lang === "hi" ? hiTranslations.p219 : enTranslations.p219;

  const [caseId, setCaseId] = useState("");
  const [contractorName, setContractorName] = useState("");
  const [contractorCode, setContractorCode] = useState("");
  const [workOrderRef, setWorkOrderRef] = useState("");
  const [traceable, setTraceable] = useState(false);
  const [amountRupees, setAmountRupees] = useState("");
  const [reasoning, setReasoning] = useState("");

  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [resultMsg, setResultMsg] = useState<string | null>(null);
  const [orderData, setOrderData] = useState<Record<string, unknown> | null>(null);

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErrorMsg(null);
    setResultMsg(null);

    // EPF Act s.8A: A contractor with its own EPF code number who is traceable is liable itself — dues cannot be assessed against principal.
    if (contractorCode.trim() && traceable) {
      setErrorMsg(t.exceptionError);
      return;
    }

    const paise = Math.round(parseFloat(amountRupees || "0") * 100);
    const orderPayload = {
      case_id: caseId.trim(),
      kind: "7A",
      total_paise: paise,
      reasoning: reasoning.trim(),
      contractor: {
        contractor_name: contractorName.trim(),
        contractor_establishment_id: contractorCode.trim() || null,
        traceable,
        work_order_ref: workOrderRef.trim() || null,
      },
      text: `Order under Section 7A read with Section 8A: Dues of ₹${amountRupees} assessed against principal employer for untraceable contractor ${contractorName.trim()}.`,
    };

    setOrderData(orderPayload);
    setResultMsg(`${t.orderSuccess} (${caseId.trim()})`);
    if (onOrderPassed) {
      onOrderPassed(orderPayload);
    }
  }

  return (
    <main
      aria-labelledby="desk-heading"
      style={{
        backgroundColor: "var(--surface)",
        color: "var(--navy)",
        padding: "24px",
        fontFamily: "'Segoe UI', 'Trebuchet MS', sans-serif",
        maxWidth: "960px",
        margin: "0 auto",
      }}
    >
      <header
        style={{
          borderBottom: "3px solid var(--gold)",
          paddingBottom: "16px",
          marginBottom: "24px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <div>
          <h1
            id="desk-heading"
            style={{
              fontSize: "24px",
              fontWeight: 700,
              color: "var(--navy)",
              margin: 0,
              fontFamily: "Georgia, serif",
            }}
          >
            {t.title}
          </h1>
          <p style={{ margin: "4px 0 0 0", color: "var(--muted)", fontSize: "14px" }}>
            {t.subtitle}
          </p>
        </div>
        <div>
          <button
            type="button"
            onClick={() => setLang(lang === "en" ? "hi" : "en")}
            style={{
              backgroundColor: "var(--navy)",
              color: "var(--surface)",
              border: "1px solid var(--gold)",
              padding: "6px 14px",
              cursor: "pointer",
              fontSize: "14px",
              fontWeight: 600,
              borderRadius: "4px",
            }}
          >
            {lang === "en" ? "हिन्दी" : "English"}
          </button>
        </div>
      </header>

      {/* Statutory Banner */}
      <section
        aria-label="Statutory Rule Guidance"
        style={{
          backgroundColor: "var(--bg)",
          borderLeft: "4px solid var(--navy)",
          padding: "16px",
          marginBottom: "24px",
          borderRadius: "0 4px 4px 0",
        }}
      >
        <h2
          style={{
            fontSize: "16px",
            color: "var(--navy)",
            margin: "0 0 8px 0",
            fontWeight: 700,
          }}
        >
          {t.ruleTitle}
        </h2>
        <p style={{ fontSize: "14px", lineHeight: 1.5, margin: "0 0 8px 0", color: "var(--ink)" }}>
          {t.ruleDescription}
        </p>
        <p
          style={{
            fontSize: "13px",
            fontWeight: 600,
            color: "var(--q)",
            margin: 0,
            lineHeight: 1.4,
          }}
        >
          {t.ruleException}
        </p>
      </section>

      {/* Assessment Form */}
      <section aria-labelledby="form-heading">
        <h2
          id="form-heading"
          style={{
            fontSize: "18px",
            fontWeight: 600,
            color: "var(--navy)",
            marginBottom: "16px",
          }}
        >
          {t.assessAgainstPrincipal}
        </h2>

        <form onSubmit={handleSubmit} style={{ display: "grid", gap: "16px" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <label htmlFor="case_id" style={{ fontWeight: 600, fontSize: "14px" }}>
              {t.caseId} *
            </label>
            <input
              id="case_id"
              name="case_id"
              type="text"
              required
              value={caseId}
              onChange={(e) => setCaseId(e.target.value)}
              placeholder="e.g. CMP-A1B2C"
              style={{
                padding: "8px 12px",
                border: "1px solid var(--navy)",
                borderRadius: "4px",
                fontSize: "14px",
              }}
            />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              <label htmlFor="contractor_name" style={{ fontWeight: 600, fontSize: "14px" }}>
                {t.contractorName} *
              </label>
              <input
                id="contractor_name"
                name="contractor_name"
                type="text"
                required
                value={contractorName}
                onChange={(e) => setContractorName(e.target.value)}
                placeholder="e.g. M/s Security Services"
                style={{
                  padding: "8px 12px",
                  border: "1px solid var(--navy)",
                  borderRadius: "4px",
                  fontSize: "14px",
                }}
              />
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              <label htmlFor="contractor_code" style={{ fontWeight: 600, fontSize: "14px" }}>
                {t.contractorCode}
              </label>
              <input
                id="contractor_code"
                name="contractor_code"
                type="text"
                value={contractorCode}
                onChange={(e) => setContractorCode(e.target.value)}
                placeholder="e.g. EST-CTR-1234"
                style={{
                  padding: "8px 12px",
                  border: "1px solid #ccc",
                  borderRadius: "4px",
                  fontSize: "14px",
                }}
              />
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              <label htmlFor="work_order_ref" style={{ fontWeight: 600, fontSize: "14px" }}>
                {t.workOrderRef}
              </label>
              <input
                id="work_order_ref"
                name="work_order_ref"
                type="text"
                value={workOrderRef}
                onChange={(e) => setWorkOrderRef(e.target.value)}
                placeholder="e.g. WO-SEC-2025-01"
                style={{
                  padding: "8px 12px",
                  border: "1px solid #ccc",
                  borderRadius: "4px",
                  fontSize: "14px",
                }}
              />
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              <label htmlFor="traceable" style={{ fontWeight: 600, fontSize: "14px" }}>
                {t.traceable} *
              </label>
              <select
                id="traceable"
                name="traceable"
                value={traceable ? "true" : "false"}
                onChange={(e) => setTraceable(e.target.value === "true")}
                style={{
                  padding: "8px 12px",
                  border: "1px solid var(--navy)",
                  borderRadius: "4px",
                  fontSize: "14px",
                  backgroundColor: "var(--surface)",
                }}
              >
                <option value="false">{t.traceableNo}</option>
                <option value="true">{t.traceableYes}</option>
              </select>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <label htmlFor="amount_rupees" style={{ fontWeight: 600, fontSize: "14px" }}>
              {t.amount} *
            </label>
            <input
              id="amount_rupees"
              name="amount_rupees"
              type="number"
              step="0.01"
              required
              value={amountRupees}
              onChange={(e) => setAmountRupees(e.target.value)}
              placeholder="e.g. 45000.00"
              style={{
                padding: "8px 12px",
                border: "1px solid var(--navy)",
                borderRadius: "4px",
                fontSize: "14px",
              }}
            />
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <label htmlFor="reasoning" style={{ fontWeight: 600, fontSize: "14px" }}>
              {t.reasoning} *
            </label>
            <textarea
              id="reasoning"
              name="reasoning"
              rows={3}
              required
              value={reasoning}
              onChange={(e) => setReasoning(e.target.value)}
              placeholder="e.g. Contractor untraceable at site; assessed against principal employer under EPF Act s.8A"
              style={{
                padding: "8px 12px",
                border: "1px solid var(--navy)",
                borderRadius: "4px",
                fontSize: "14px",
                fontFamily: "inherit",
              }}
            />
          </div>

          <div style={{ marginTop: "8px" }}>
            <button
              type="submit"
              style={{
                backgroundColor: "var(--navy)",
                color: "var(--surface)",
                border: "2px solid var(--gold)",
                padding: "10px 24px",
                fontSize: "15px",
                fontWeight: 600,
                borderRadius: "4px",
                cursor: "pointer",
              }}
            >
              {t.assessAgainstPrincipal}
            </button>
          </div>
        </form>
      </section>

      {/* Live Result / Error Area */}
      <section
        aria-live="polite"
        style={{ marginTop: "24px" }}
      >
        {errorMsg && (
          <div
            role="alert"
            style={{
              backgroundColor: "var(--bg)",
              border: "1px solid var(--q)",
              color: "var(--q)",
              padding: "12px 16px",
              borderRadius: "4px",
              fontSize: "14px",
              fontWeight: 600,
            }}
          >
            {errorMsg}
          </div>
        )}

        {resultMsg && (
          <div
            style={{
              backgroundColor: "var(--bg)",
              border: "1px solid var(--w)",
              color: "var(--w)",
              padding: "16px",
              borderRadius: "4px",
            }}
          >
            <p style={{ margin: "0 0 8px 0", fontWeight: 700, fontSize: "15px" }}>
              {resultMsg}
            </p>
            <p style={{ margin: "0 0 8px 0", fontSize: "14px", color: "var(--muted)" }}>
              {t.principalRecoveryNotice}
            </p>
            {orderData && (
              <pre
                style={{
                  backgroundColor: "var(--surface)",
                  border: "1px solid #ccc",
                  padding: "12px",
                  fontSize: "12px",
                  margin: 0,
                  overflowX: "auto",
                }}
              >
                {JSON.stringify(orderData, null, 2)}
              </pre>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
