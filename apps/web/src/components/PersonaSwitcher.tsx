import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useLocation } from "react-router-dom";

import { getSession, logout } from "../api/client";
import { DEMO_PASSWORD, PERSONAS } from "../data/personas";

/** Switching persona is a real logout + login through Keycloak — never impersonation. */
export function PersonaSwitcher() {
  const { t } = useTranslation();
  const location = useLocation();
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });

  async function switchTo(username: string) {
    if (session.data?.authenticated) {
      try {
        await logout();
      } catch {
        /* continue to login even if logout failed */
      }
    }
    const returnTo = encodeURIComponent(location.pathname);
    window.location.assign(`/auth/login?persona=${encodeURIComponent(username)}&return_to=${returnTo}`);
  }

  return (
    <section aria-labelledby="persona-heading" className="persona">
      <h2 id="persona-heading">{t("persona.heading")}</h2>
      <p className="muted">
        {session.data?.authenticated
          ? t("persona.current", { label: session.data.persona_label ?? session.data.subject, role: session.data.stakeholder })
          : t("persona.none")}
      </p>
      <label htmlFor="persona-select">{t("persona.choose")}</label>
      <select id="persona-select" defaultValue="" onChange={(e) => e.target.value && switchTo(e.target.value)}>
        <option value="" disabled>
          —
        </option>
        {PERSONAS.map((p) => (
          <option key={p.username} value={p.username}>
            {p.label} ({p.role})
          </option>
        ))}
      </select>
      <p className="muted">
        {t("persona.password")} <code>{DEMO_PASSWORD}</code>
      </p>
      {session.data?.authenticated ? (
        <button type="button" onClick={() => logout().then(() => window.location.assign("/"))}>
          {t("persona.logout")}
        </button>
      ) : null}
    </section>
  );
}
