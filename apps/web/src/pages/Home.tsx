import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { getSession } from "../api/client";
import { StatusBadge } from "../components/StatusBadge";
import { INTERFACES } from "../data/interfaces";

export function Home() {
  const { t } = useTranslation();
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  return (
    <section aria-labelledby="interfaces-heading">
      <h1 id="interfaces-heading">{t("home.heading")}</h1>
      <p className="muted">{t("home.intro")}</p>
      <p><Link to="/public" className="button primary">{t("home.publicLookups")} →</Link></p>
      {session.data?.stakeholder?.startsWith("employer.") ? (
        <p><Link to="/employer" className="button primary">{t("home.employerWorkspace")} →</Link></p>
      ) : null}
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
