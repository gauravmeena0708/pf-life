import { useTranslation } from "react-i18next";
import { Route, Routes } from "react-router-dom";

import { DemoBanner } from "./components/DemoBanner";
import { PersonaSwitcher } from "./components/PersonaSwitcher";
import { EcrPage } from "./features/employer/EcrPage";
import { EmployerHome } from "./features/employer/EmployerHome";
import { Home } from "./pages/Home";
import { InterfacePage } from "./pages/InterfacePage";
import { PublicLookups } from "./pages/PublicLookups";

export function App() {
  const { t, i18n } = useTranslation();
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
        <strong>{t("title")}</strong>
        <nav aria-label={t("language")}>
          <button type="button" onClick={() => setLanguage("en")} aria-pressed={i18n.language === "en"}>
            English
          </button>
          <button type="button" onClick={() => setLanguage("hi")} aria-pressed={i18n.language === "hi"}>
            हिन्दी
          </button>
        </nav>
      </header>
      <div className="layout">
        <aside>
          <PersonaSwitcher />
        </aside>
        <main id="main">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/i/:slug" element={<InterfacePage />} />
            <Route path="/employer" element={<EmployerHome />} />
            <Route path="/employer/ecr" element={<EcrPage />} />
            <Route path="/public" element={<PublicLookups />} />
          </Routes>
        </main>
      </div>
    </>
  );
}
