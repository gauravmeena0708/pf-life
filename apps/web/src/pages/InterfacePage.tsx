import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { getMyPermissions, getSession, type Grant } from "../api/client";
import { ProblemMessage } from "../components/ProblemMessage";
import { StatusBadge } from "../components/StatusBadge";
import { INTERFACES } from "../data/interfaces";

const ORDER: Grant["status"][] = ["W", "M", "P", "?"];

export function InterfacePage() {
  const { t } = useTranslation();
  const { slug } = useParams();
  const def = INTERFACES.find((i) => i.slug === slug);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const perms = useQuery({
    queryKey: ["permissions"],
    queryFn: getMyPermissions,
    enabled: !!session.data?.authenticated,
    retry: false,
  });

  if (!def) return <p>{t("interface.unknown")}</p>;
  const grants = perms.data?.data.endpoints ?? [];
  return (
    <section aria-labelledby="interface-heading">
      <p>
        <Link to="/">← {t("interface.back")}</Link>
      </p>
      <h1 id="interface-heading">
        {def.id}. {def.name} <StatusBadge status={def.coverage} />
      </h1>
      <p className="muted">
        {t("interface.stakeholders")}: {def.stakeholders.map((s) => <code key={s}>{s} </code>)}
      </p>
      {!session.data?.authenticated ? <p>{t("interface.login")}</p> : null}
      <ProblemMessage error={perms.error} />
      {session.data?.authenticated && perms.data ? (
        <>
          <h2>{t("interface.yourEndpoints", { role: perms.data.data.stakeholder })}</h2>
          {grants.length === 0 ? <p>{t("interface.none")}</p> : null}
          {ORDER.map((status) => {
            const rows = grants.filter((g) => g.status === status);
            if (rows.length === 0) return null;
            return (
              <div key={status}>
                <h3>
                  <StatusBadge status={status} /> ({rows.length})
                </h3>
                <ul className="grant-list">
                  {rows.map((g) => (
                    <li key={g.endpoint}>
                      <code>{g.endpoint}</code>
                      {g.step_up ? <span className="muted"> · {t("interface.stepUp")}</span> : null}
                      <div className="muted small">{g.scope}</div>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </>
      ) : null}
    </section>
  );
}
