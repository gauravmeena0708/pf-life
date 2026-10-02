import { useTranslation } from "react-i18next";

import { TEXT_SIZES, useTextSize } from "../data/textSize";

/** A− · A · A+ in the header: smaller, the default, larger text. */
export function TextSizeControl() {
  const { t } = useTranslation();
  const [size, setSize] = useTextSize();
  const at = TEXT_SIZES.indexOf(size);
  return <div className="text-size" role="group" aria-label={t("nav.textSize")}>
    <button type="button" onClick={() => setSize(TEXT_SIZES[at - 1])} disabled={at === 0} aria-label={t("nav.textSmaller")}>A−</button>
    <button type="button" onClick={() => setSize(100)} aria-pressed={size === 100} aria-label={t("nav.textDefault")}>A</button>
    <button type="button" onClick={() => setSize(TEXT_SIZES[at + 1])} disabled={at === TEXT_SIZES.length - 1} aria-label={t("nav.textLarger")}>A+</button>
    <span className="visually-hidden" aria-live="polite">{t("nav.textNow", { size })}</span>
  </div>;
}
