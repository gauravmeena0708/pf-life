import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, NavLink, Route, Routes } from "react-router-dom";

import { getSession } from "./api/client";
import { DemoBanner } from "./components/DemoBanner";
import { PersonaSwitcher } from "./components/PersonaSwitcher";
import { EcrPage } from "./features/employer/EcrPage";
import { EmployerHome } from "./features/employer/EmployerHome";
import { PassbookPage } from "./features/member/PassbookPage";
import { ClaimsPage } from "./features/member/ClaimsPage";
import { ClaimDetailPage } from "./features/member/ClaimDetailPage";
import { ProfilePage } from "./features/member/ProfilePage";
import { WorkQueuePage } from "./features/office/WorkQueuePage";
import { CasePage } from "./features/office/CasePage";
import { GrievanceDetailPage } from "./features/grievance/GrievanceDetailPage";
import { GrievanceOfficePage } from "./features/grievance/GrievanceOfficePage";
import { GrievancesPage } from "./features/grievance/GrievancesPage";
import { SecurityPage } from "./features/member/SecurityPage";
import { AssistantPage } from "./features/ai/AssistantPage";
import { AuditLogPage } from "./features/oversight/AuditLogPage";
import { GrievanceMetricsPage } from "./features/oversight/GrievanceMetricsPage";
import { RiskSignalsPage } from "./features/oversight/RiskSignalsPage";
import { SessionsRecoveryPage } from "./features/oversight/SessionsRecoveryPage";
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
        {role === "member" ? <><NavLink to="/member/passbook">{t("navigation.passbook")}</NavLink><NavLink end to="/member/claims">{t("navigation.claims")}</NavLink><NavLink to="/member/grievances">{t("navigation.grievances")}</NavLink><NavLink to="/member/profile">{t("navigation.profile")}</NavLink><NavLink to="/member/security">{t("navigation.accountSecurity")}</NavLink><NavLink to="/member/assistant">{t("navigation.assistant")}</NavLink></> : null}
        {role?.startsWith("fo.") || role === "zo.acc" ? <NavLink to="/office/work-queue">{t("navigation.workQueue")}</NavLink> : null}
        {role === "zo.acc" || role === "ho.cpfc" ? <NavLink to="/monitoring/grievances">{t("navigation.grievanceMetrics")}</NavLink> : null}
        {role === "ho.security" ? <><NavLink to="/security/activity">{t("navigation.security")}</NavLink><NavLink to="/security/sessions">{t("navigation.sessions")}</NavLink><NavLink to="/audit/log">{t("navigation.audit")}</NavLink></> : null}
        {role === "ho.caiu" ? <NavLink to="/caiu/signals">{t("navigation.riskSignals")}</NavLink> : null}
        {role === "ho.audit" ? <NavLink to="/audit/log">{t("navigation.audit")}</NavLink> : null}
      </div></nav>
      <div className="shell-width layout">
        <main id="main">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/i/:slug" element={<InterfacePage />} />
            <Route path="/employer" element={<EmployerHome />} />
            <Route path="/employer/ecr" element={<EcrPage />} />
            <Route path="/member/passbook" element={<PassbookPage />} />
            <Route path="/member/claims" element={<ClaimsPage />} />
            <Route path="/member/claims/:claimId" element={<ClaimDetailPage />} />
            <Route path="/member/profile" element={<ProfilePage />} />
            <Route path="/office/work-queue" element={<WorkQueuePage />} />
            <Route path="/office/cases/:caseId" element={<CasePage />} />
            <Route path="/public" element={<PublicLookups />} />
            <Route path="/security/activity" element={<SecurityActivity />} />
            <Route path="/member/grievances" element={<GrievancesPage />} />
            <Route path="/member/grievances/:grievanceId" element={<GrievanceDetailPage />} />
            <Route path="/member/security" element={<SecurityPage />} />
            <Route path="/member/assistant" element={<AssistantPage />} />
            <Route path="/office/grievances/:grievanceId" element={<GrievanceOfficePage />} />
            <Route path="/caiu/signals" element={<RiskSignalsPage />} />
            <Route path="/security/sessions" element={<SessionsRecoveryPage />} />
            <Route path="/audit/log" element={<AuditLogPage />} />
            <Route path="/monitoring/grievances" element={<GrievanceMetricsPage />} />
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
