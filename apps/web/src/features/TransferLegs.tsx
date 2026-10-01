import { useTranslation } from "react-i18next";
import { statusLabel } from "./statusLabel";

export interface TransferLeg { state: string; label: string; detail: Record<string, unknown> }
export interface TransferLegsData { transfer_id: string; direction: string; pf_leg: TransferLeg; eps_leg: TransferLeg }

export function TransferLegs({ transfer }: { transfer: TransferLegsData }) {
  const { t } = useTranslation();
  const trust = String(transfer.pf_leg.detail.trust_name ?? t("trustPf.trust"));
  return <div className="profile-card stack" aria-label={`${t("trustPf.transfer")} ${transfer.transfer_id}`}>
    <h3>{transfer.transfer_id} · {statusLabel(transfer.direction, t)}</h3>
    <dl className="kv"><dt>{t("trustPf.pfLeg")}</dt><dd><span className="state-pill">{statusLabel(transfer.pf_leg.state, t)}</span> {t(`trustPf.pfLabels.${transfer.pf_leg.state}`, { trust, defaultValue: transfer.pf_leg.label })}</dd>
      <dt>{t("trustPf.epsLeg")}</dt><dd><span className="state-pill">{statusLabel(transfer.eps_leg.state, t)}</span> {t(`trustPf.epsLabels.${transfer.eps_leg.state}`, { defaultValue: transfer.eps_leg.label })}</dd></dl>
  </div>;
}
