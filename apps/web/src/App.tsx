import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useEffect } from "react";
import { Link, Route, Routes, useLocation } from "react-router-dom";

import { getSession } from "./api/client";
import { DemoBanner } from "./components/DemoBanner";
import { PersonaSwitcher } from "./components/PersonaSwitcher";
import { RoleNav } from "./components/RoleNav";
import { EcrPage } from "./features/employer/EcrPage";
import { EmployerHome } from "./features/employer/EmployerHome";
import { PassbookPage } from "./features/member/PassbookPage";
import { ClaimsPage } from "./features/member/ClaimsPage";
import { ClaimDetailPage } from "./features/member/ClaimDetailPage";
import { ProfilePage } from "./features/member/ProfilePage";
import { ServicePage } from "./features/member/ServicePage";
import { KycPage, UanCardPage } from "./features/member/KycPage";
import { PensionApplicationPage } from "./features/member/PensionApplicationPage";
import { PensionClaimsPage } from "./features/pension/PensionClaimsPage";
import { CppsPage } from "./features/pension/CppsPage";
import { RegistrationPage } from "./features/employer/RegistrationPage";
import { MemberActionsPage } from "./features/employer/MemberActionsPage";
import { EstablishmentPage } from "./features/employer/EstablishmentPage";
import { OlrePage } from "./features/office/OlrePage";
import { WorkQueuePage } from "./features/office/WorkQueuePage";
import { CasePage } from "./features/office/CasePage";
import { ClaimToolsPage } from "./features/office/ClaimToolsPage";
import { ClaimantPage, ProCounterPage } from "./features/claimant/DeathClaimPages";
import { GrievanceDetailPage } from "./features/grievance/GrievanceDetailPage";
import { GrievanceOfficePage } from "./features/grievance/GrievanceOfficePage";
import { GrievancesPage } from "./features/grievance/GrievancesPage";
import { SecurityPage } from "./features/member/SecurityPage";
import { AssistantPage } from "./features/ai/AssistantPage";
import { AuditLogPage } from "./features/oversight/AuditLogPage";
import { PolicyListPage } from "./features/policy/PolicyListPage";
import { PolicyVersionPage } from "./features/policy/PolicyVersionPage";
import { InterestPage } from "./features/finance/InterestPage";
import { PensionerPage } from "./features/pension/PensionerPage";
import { PensionerServicesPage } from "./features/pension/PensionerServicesPage";
import { PensionOfficePage } from "./features/pension/PensionOfficePage";
import { PensionRevisionsPage } from "./features/pension/PensionRevisionsPage";
import { DashboardsPage } from "./features/oversight/DashboardsPage";
import { GrievanceMetricsPage } from "./features/oversight/GrievanceMetricsPage";
import { RiskSignalsPage } from "./features/oversight/RiskSignalsPage";
import { SessionsRecoveryPage } from "./features/oversight/SessionsRecoveryPage";
import { Home } from "./pages/Home";
import { InterfacePage } from "./pages/InterfacePage";
import { PublicLookups } from "./pages/PublicLookups";
import { SecurityActivity } from "./pages/SecurityActivity";

/** Menu links point at sections (`/member/profile#correction-heading`); scroll there once the section has rendered. */
function ScrollToHash() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (!hash) return;
    let tries = 0;
    const timer = window.setInterval(() => {
      const el = document.getElementById(decodeURIComponent(hash.slice(1)));
      if (el || ++tries > 20) { window.clearInterval(timer); el?.scrollIntoView({ behavior: "smooth", block: "start" }); }
    }, 100);
    return () => window.clearInterval(timer);
  }, [pathname, hash]);
  return null;
}

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
      <ScrollToHash />
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
      <nav className="primary-nav" aria-label={t("navigation.primary")}><RoleNav role={role} /></nav>
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
            <Route path="/member/service" element={<ServicePage />} />
            <Route path="/member/kyc" element={<KycPage />} />
            <Route path="/member/pension" element={<PensionApplicationPage />} />
            <Route path="/office/pension-claims" element={<PensionClaimsPage />} />
            <Route path="/office/claim-tools" element={<ClaimToolsPage />} />
            <Route path="/claimant" element={<ClaimantPage />} />
            <Route path="/office/pro-counter" element={<ProCounterPage />} />
            <Route path="/cpps" element={<CppsPage />} />
            <Route path="/member/uan-card" element={<UanCardPage />} />
            <Route path="/employer/registration" element={<RegistrationPage />} />
            <Route path="/employer/members" element={<MemberActionsPage />} />
            <Route path="/employer/establishment" element={<EstablishmentPage />} />
            <Route path="/office/olre" element={<OlrePage />} />
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
            <Route path="/dashboards" element={<DashboardsPage />} />
            <Route path="/policy" element={<PolicyListPage />} />
            <Route path="/policy/:versionId" element={<PolicyVersionPage />} />
            <Route path="/finance/interest" element={<InterestPage />} />
            <Route path="/pensioner" element={<PensionerPage />} />
            <Route path="/pensioner/services" element={<PensionerServicesPage />} />
            <Route path="/office/pensions" element={<PensionOfficePage />} />
            <Route path="/office/pension-revisions" element={<PensionRevisionsPage />} />
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
