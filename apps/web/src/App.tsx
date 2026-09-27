import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, NavLink, Route, Routes } from "react-router-dom";

import { getSession } from "./api/client";
import { DemoBanner } from "./components/DemoBanner";
import { PersonaSwitcher } from "./components/PersonaSwitcher";
import { EcrPage } from "./features/employer/EcrPage";
import { EmployerHome } from "./features/employer/EmployerHome";
import { PassbookPage } from "./features/member/PassbookPage";
import { Home } from "./pages/Home";
import { InterfacePage } from "./pages/InterfacePage";
import { PublicLookups } from "./pages/PublicLookups";
import { SecurityActivity } from "./pages/SecurityActivity";

export function App() {
  const { t, i18n } = useTranslation();
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const role = session.data?.stakeholder;
  function setLanguage(lng: string) {
    void i18n.changeLanguage(lng);
    document.documentElement.lang = lng;
  }
  return (
    <>
      <a href="#main" className="skip">
        {t("skip")}
      </a>
      <DemoBanner />
      <header className="topbar">
        <div className="shell-width topbar-inner">
          <Link to="/" className="brand" aria-label={t("navigation.home")}>
            <span className="emblem" aria-hidden="true">EPFO</span>
            <span className="brand-copy"><strong>{t("title")}</strong><small>{t("portal.subtitle")}</small></span>
          </Link>
          <div className="header-tools">
            <nav aria-label={t("language")} className="language-toggle">
              <button type="button" onClick={() => setLanguage("en")} aria-pressed={i18n.language === "en"}>English</button>
              <button type="button" onClick={() => setLanguage("hi")} aria-pressed={i18n.language === "hi"}>हिन्दी</button>
            </nav>
            <PersonaSwitcher />
          </div>
        </div>
      </header>
      <nav className="primary-nav" aria-label={t("navigation.primary")}><div className="shell-width primary-nav-inner">
        <NavLink end to="/">{t("navigation.home")}</NavLink>
        <NavLink to="/public">{t("navigation.public")}</NavLink>
        {role?.startsWith("employer.") ? <><NavLink end to="/employer">{t("navigation.employer")}</NavLink><NavLink to="/employer/ecr">{t("navigation.ecr")}</NavLink></> : null}
        {role === "member" ? <NavLink to="/member/passbook">{t("navigation.passbook")}</NavLink> : null}
        {role === "ho.security" ? <NavLink to="/security/activity">{t("navigation.security")}</NavLink> : null}
      </div></nav>
      <div className="shell-width layout">
        <main id="main">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/i/:slug" element={<InterfacePage />} />
            <Route path="/employer" element={<EmployerHome />} />
            <Route path="/employer/ecr" element={<EcrPage />} />
            <Route path="/member/passbook" element={<PassbookPage />} />
            <Route path="/public" element={<PublicLookups />} />
            <Route path="/security/activity" element={<SecurityActivity />} />
          </Routes>
        </main>
      </div>
      <footer className="site-footer"><div className="shell-width footer-inner">
        <div><p>{t("portal.disclaimer")}</p><small>{t("portal.built")}</small></div>
        <nav aria-label={t("navigation.footer")}><Link to="/">{t("navigation.home")}</Link><Link to="/public">{t("navigation.public")}</Link></nav>
      </div></footer>
    </>
  );
}
