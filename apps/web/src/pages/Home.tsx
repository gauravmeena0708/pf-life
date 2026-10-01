import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { getSession } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { PersonaLink } from "../components/PersonaLink";
import { SystemTotals } from "../components/SystemTotals";
import { JOURNEYS } from "../data/journeys";
import { homeFor } from "../data/navigation";
import { PERSONAS } from "../data/personas";

const publicServices = [
  { key: "establishments", to: "/public#establishment-search" },
  { key: "claims", to: "/public/claims#claim-status-heading" },
  { key: "grievance", to: "/public/grievances#public-grievance-heading" },
  { key: "grievanceStatus", to: "/public/grievances#grievance-status-heading" },
  { key: "circulars", to: "/public/circulars#circulars-heading" },
  { key: "defaulters", to: "/public#defaulters-public-heading" },
  { key: "pension", to: "/public#pension-enquiries" },
];

export function Home() {
  const { t } = useTranslation();
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const authenticated = !!session.data?.authenticated;
  return <div className="stack home-page">
    <PageHeader eyebrow={t("home.eyebrow")} title={t("home.heading")} description={t("home.intro")} />
    <section className="card stack handbook-card" aria-labelledby="handbook-heading">
      <h2 id="handbook-heading">{t("home.handbookTitle")}</h2>
      <p className="muted">{t("home.handbookDescription")}</p>
      <div className="actions">
        <a href="/cto-handbook/index.html" className="button primary" target="_blank" rel="noopener noreferrer">{t("home.handbookOpen")}</a>
        <a href="/cto-handbook/epfo-cto-handbook.pdf" download>{t("home.handbookPdf")}</a>
      </div>
      <p className="muted handbook-language-note">{t("home.handbookLanguageNote")}</p>
    </section>
    <section className="stack" aria-labelledby="built-heading">
      <h2 id="built-heading">{t("home.built")}</h2>
      <SystemTotals />
    </section>
    <section className="stack" aria-labelledby="journeys-heading">
      <h2 id="journeys-heading">{t("home.journeysTitle")}</h2>
      <div className="journey-grid">{JOURNEYS.map((journey, index) => {
        const personas = journey.personas.flatMap((username) => {
          const persona = PERSONAS.find((item) => item.username === username);
          return persona ? [persona] : [];
        });
        return <article className="card journey-card stack" key={journey.id} aria-labelledby={`journey-${journey.id}`}>
          <span className="service-number" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
          <h3 id={`journey-${journey.id}`}>{t(`home.journeys.${journey.id}.title`, { defaultValue: journey.title })}</h3>
          <p className="muted">{t(`home.journeys.${journey.id}.description`, { defaultValue: journey.description })}</p>
          <ol className="journey-personas" aria-label={t("home.personasInvolved")}>{personas.map((persona) => <li key={persona.username}>{persona.label}</li>)}</ol>
          <div className="actions">{personas[0] ? <PersonaLink persona={personas[0]} authenticated={authenticated} className="button secondary">
            {t("home.startAs", { label: personas[0].label })}
          </PersonaLink> : null}
          {journey.publicForm ? <Link to={journey.publicForm}>{t("home.publicForm")}</Link> : null}</div>
        </article>;
      })}</div>
    </section>
    <section className="card stack" aria-labelledby="public-services-heading">
      <h2 id="public-services-heading">{t("home.publicTitle")}</h2>
      <ul className="public-service-links">{publicServices.map(({ key, to }) => <li key={key}><Link to={to}>{t(`home.publicServices.${key}`)}</Link></li>)}</ul>
    </section>
    <section className="card stack" aria-labelledby="explore-heading">
      <h2 id="explore-heading">{t("home.exploreTitle")}</h2>
      <p className="muted">{t("home.exploreDescription")}</p>
      <div className="actions"><Link to="/system-map" className="button primary">{t("navigation.systemMap")}</Link>
        {authenticated ? <Link to={homeFor(session.data?.stakeholder)} className="button secondary">{t("home.workspace")}</Link>
          : <button type="button" className="secondary" onClick={() => window.dispatchEvent(new Event("open-demo-account"))}>{t("home.signIn")}</button>}
      </div>
    </section>
  </div>;
}
