import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import QRCode from "qrcode";

import { api, rupees, type Envelope } from "../../api/client";
import { ddmmyyyy } from "../../components/ui/format";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { stateLabel } from "../journeyB";

export interface ReceiptData {
  claim_id: string;
  form_type: string;
  claim_label: string;
  amount_paise: number;
  filed_on: string;
  state: string;
  member_name: string | null;
  uan_masked: string | null;
  employer: string | null;
  code: string;
  verify_path: string;
}

export function ReceiptPage() {
  const { t } = useTranslation();
  const { claimId } = useParams();
  const [qrDataUrl, setQrDataUrl] = useState<string>("");

  const query = useQuery({
    queryKey: ["member-claim-receipt", claimId],
    queryFn: () => api<Envelope<ReceiptData>>(`/api/v1/members/me/claims/${encodeURIComponent(claimId!)}/receipt`),
    enabled: !!claimId,
    retry: false,
  });

  const receipt = query.data?.data;

  useEffect(() => {
    if (!receipt?.verify_path) return;
    const origin = typeof window !== "undefined" && window.location ? window.location.origin : "";
    const targetUrl = `${origin}${receipt.verify_path}`;
    QRCode.toDataURL(targetUrl, { width: 160, margin: 1 })
      .then((url) => setQrDataUrl(url))
      .catch((err) => {
        console.error("Failed to generate receipt QR code", err);
      });
  }, [receipt?.verify_path]);

  return (
    <section className="stack receipt-page-container" aria-labelledby="receipt-page-heading">
      <div className="no-print">
        <PageHeader
          id="receipt-page-heading"
          eyebrow={t("claimJourney.eyebrow")}
          title={t("receipt.title", "Receipt")}
          description={receipt ? `${rupees(receipt.amount_paise)} · ${receipt.claim_id}` : ""}
          parent={{ label: t("navigation.claims"), to: "/member/claims" }}
          current={t("receipt.title", "Receipt")}
        />
      </div>

      <ProblemMessage error={query.error} />
      {query.isLoading ? <p role="status">{t("receipt.pleaseWait", "Please wait…")}</p> : null}

      {receipt ? (
        <div className="receipt-container">
          <article className="receipt-card stack" aria-labelledby="receipt-heading">
            <header className="receipt-header">
              <span className="receipt-emblem" aria-hidden="true">EPFO</span>
              <h2 className="receipt-org-title">Employees' Provident Fund Organisation</h2>
              <p className="receipt-demo-notice">{t("banner")}</p>
              <h1 id="receipt-heading" className="receipt-title">{t("receipt.heading", "Claim receipt")}</h1>
            </header>

            <div className="receipt-body">
              <dl className="receipt-dl">
                <dt>{t("receipt.claimId", "Claim ID")}</dt>
                <dd><code>{receipt.claim_id}</code></dd>

                <dt>{t("receipt.claimType", "Claim type")}</dt>
                <dd>{receipt.claim_label} ({t("receipt.form", "Form")} {receipt.form_type})</dd>

                <dt>{t("receipt.amount", "Amount")}</dt>
                <dd><strong>{rupees(receipt.amount_paise)}</strong></dd>

                <dt>{t("receipt.filedOn", "Filed on")}</dt>
                <dd>{ddmmyyyy(receipt.filed_on)}</dd>

                <dt>{t("receipt.status", "Status")}</dt>
                <dd><span className="state-pill">{stateLabel(receipt.state, t)}</span></dd>

                {receipt.member_name ? (
                  <>
                    <dt>{t("receipt.memberName", "Member name")}</dt>
                    <dd>{receipt.member_name}</dd>
                  </>
                ) : null}

                {receipt.uan_masked ? (
                  <>
                    <dt>{t("receipt.uan", "UAN")}</dt>
                    <dd><code>{receipt.uan_masked}</code></dd>
                  </>
                ) : null}

                {receipt.employer ? (
                  <>
                    <dt>{t("receipt.employer", "Employer")}</dt>
                    <dd>{receipt.employer}</dd>
                  </>
                ) : null}
              </dl>

              <div className="receipt-verification-section">
                <div className="receipt-code-box">
                  <span className="receipt-code-label">{t("receipt.code", "Verification code")}</span>
                  <code className="receipt-code">{receipt.code}</code>
                </div>
                <div className="receipt-qr-wrap">
                  {qrDataUrl ? (
                    <img src={qrDataUrl} alt="QR code to verify this receipt" className="receipt-qr" />
                  ) : null}
                </div>
              </div>
            </div>

            <div className="receipt-actions actions no-print">
              <button type="button" className="button primary" onClick={() => window.print()}>
                {t("receipt.printOrSave", "Print or save")}
              </button>
              <Link to={`/member/claims/${receipt.claim_id}`} className="button">
                {t("claimJourney.confirmation.trackClaim", "Track claim")}
              </Link>
            </div>
          </article>
        </div>
      ) : null}
    </section>
  );
}
