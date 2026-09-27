import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { StatusBadge } from "../components/StatusBadge";
import { INTERFACES } from "../data/interfaces";

export function Home() {
  const { t } = useTranslation();
  return (
    <section aria-labelledby="interfaces-heading">
      <h1 id="interfaces-heading">{t("home.heading")}</h1>
      <p className="muted">{t("home.intro")}</p>
      <ol className="interface-list">
        {INTERFACES.map((i) => (
          <li key={i.slug}>
            <Link to={`/i/${i.slug}`}>
              {i.id}. {i.name}
            </Link>{" "}
            <StatusBadge status={i.coverage} />
          </li>
        ))}
      </ol>
    </section>
  );
}
