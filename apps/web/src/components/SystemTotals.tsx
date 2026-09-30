import { useTranslation } from "react-i18next";

import { TOTALS } from "../data/interfaces";

export function SystemTotals() {
  const { t } = useTranslation();
  return <ul className="totals-strip" aria-label={t("home.built")}>
    <li>{t("home.totals.interfaces", { count: TOTALS.interfaces })}</li>
    <li>{t("home.totals.roles", { access: TOTALS.stakeholders_with_access, all: TOTALS.stakeholders })}</li>
    <li>{t("home.totals.working", { count: TOTALS.endpoints.W })}</li>
    <li>{t("home.totals.simulated", { count: TOTALS.endpoints.M })}</li>
    <li>{t("home.totals.planned", { count: TOTALS.endpoints.P })}</li>
    <li>{t("home.totals.personas", { count: TOTALS.personas })}</li>
    {TOTALS.endpoints["?"] > 0 ? <li>{t("home.totals.pending", { count: TOTALS.endpoints["?"] })}</li> : null}
  </ul>;
}
