import { useTranslation } from "react-i18next";

export function DemoBanner() {
  const { t } = useTranslation();
  return (
    <div role="note" className="demo-banner">
      {t("banner")}
    </div>
  );
}
