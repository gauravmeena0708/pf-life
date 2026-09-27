import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { getSession } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { StatusBadge } from "../components/StatusBadge";
import { INTERFACES } from "../data/interfaces";

export function Home() {
  const { t } = useTranslation();
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const role = session.data?.stakeholder;
  const workspace = role?.startsWith("employer.") ? { to: "/employer", label: t("navigation.employer") }
    : role === "member" ? { to: "/member/passbook", label: t("navigation.passbook") }
      : role === "ho.security" ? { to: "/security/activity", label: t("navigation.security") } : null;
  const services = [
    { key: "employer", to: role?.startsWith("employer.") ? "/employer" : "/i/employer" },
    { key: "member", to: role === "member" ? "/member/passbook" : "/i/member" },
    { key: "public", to: "/public" },
    { key: "office", to: "/i/office" },
    { key: "security", to: role === "ho.security" ? "/security/activity" : "/i/security" },
  ] as const;
  return (
    <div className="stack home-page">
      <PageHeader eyebrow={t("home.eyebrow")} title={t("home.heading")} description={t("home.intro")} />
      <section className="hero-card" aria-labelledby="hero-title">
        <p className="eyebrow">{t("home.heroEyebrow")}</p>
        <h2 id="hero-title">{t("home.heroTitle")}</h2>
        <p>{t("home.heroDescription")}</p>
        <div className="actions">
          <Link to="/public" className="button primary">{t("navigation.public")}</Link>
          {workspace ? <Link to={workspace.to} className="button secondary">{workspace.label}</Link>
            : <button type="button" className="secondary" onClick={() => window.dispatchEvent(new Event("open-demo-account"))}>{t("home.signIn")}</button>}
        </div>
      </section>
      <section className="stack" aria-labelledby="services-heading">
        <div className="section-heading"><div><p className="eyebrow">{t("home.servicesEyebrow")}</p><h2 id="services-heading">{t("home.servicesTitle")}</h2></div></div>
        <div className="service-grid">{services.map(({ key, to }, index) => <Link key={key} to={to} className="service-tile">
          <span className="service-number">0{index + 1}</span>
          <h3>{t(`home.services.${key}.title`)}</h3>
          <p>{t(`home.services.${key}.description`)}</p>
          <span className="service-link">{t("home.explore")} <span aria-hidden="true">→</span></span>
        </Link>)}</div>
      </section>
      <details className="interface-directory card">
        <summary>{t("home.directoryTitle")}</summary>
        <p className="muted">{t("home.directoryDescription")}</p>
        <ol className="interface-list">{INTERFACES.map((item) => <li key={item.slug}>
          <Link to={`/i/${item.slug}`}>{item.id}. {item.name}</Link> <StatusBadge status={item.coverage} />
        </li>)}</ol>
      </details>
    </div>
  );
}
