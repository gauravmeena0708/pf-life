import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useLocation } from "react-router-dom";

import { getSession } from "../api/client";
import { DEMO_PASSWORD, PERSONAS } from "../data/personas";

function csrfToken(): string | undefined {
  return document.cookie.split("; ").find((cookie) => cookie.startsWith("epfo-csrf="))?.split("=")[1];
}

/** A top-level POST follows the Keycloak sign-out redirect; fetch cannot complete that browser flow. */
function leaveSession(nextPersona?: string, returnTo = "/") {
  const params = new URLSearchParams();
  if (nextPersona) {
    params.set("next_persona", nextPersona);
    params.set("return_to", returnTo);
  }
  const form = document.createElement("form");
  form.method = "POST";
  form.action = `/auth/logout${params.size ? `?${params}` : ""}`;
  const token = csrfToken();
  if (token) {
    const field = document.createElement("input");
    field.type = "hidden";
    field.name = "csrf_token";
    field.value = token;
    form.append(field);
  }
  document.body.append(form);
  form.submit();
}

/** Switching persona is a real logout + login through Keycloak — never impersonation. */
export function PersonaSwitcher() {
  const { t } = useTranslation();
  const location = useLocation();
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const menuRef = useRef<HTMLDetailsElement>(null);

  useEffect(() => {
    function closeOutside(event: PointerEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) menuRef.current.open = false;
    }
    function closeEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && menuRef.current?.open) {
        menuRef.current.open = false;
        menuRef.current.querySelector<HTMLElement>("summary")?.focus();
      }
    }
    function openAccount() {
      if (menuRef.current) {
        menuRef.current.open = true;
        menuRef.current.querySelector<HTMLElement>("summary")?.focus();
      }
    }
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeEscape);
    window.addEventListener("open-demo-account", openAccount);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeEscape);
      window.removeEventListener("open-demo-account", openAccount);
    };
  }, []);

  function switchTo(username: string) {
    const role = PERSONAS.find((persona) => persona.username === username)?.role;
    const returnTo = role === "ho.security" ? "/security/activity" : role === "member" ? "/member/passbook"
      : role?.startsWith("fo.") || role === "zo.acc" || role === "zo.rpfc1" ? "/office/work-queue"
      : role === "ho.caiu" ? "/caiu/signals" : role === "ho.audit" ? "/audit/log" : role === "ho.cpfc" ? "/monitoring/grievances"
      : role?.startsWith("employer.") ? (location.pathname.startsWith("/employer") ? location.pathname : "/employer")
        : "/";
    if (session.data?.authenticated) {
      leaveSession(username, returnTo);
    } else {
      window.location.assign(`/auth/login?${new URLSearchParams({ persona: username, return_to: returnTo })}`);
    }
  }

  return (
    <details className="account-menu" ref={menuRef}>
      <summary>{session.data?.authenticated
        ? t("persona.account", { label: session.data.persona_label ?? session.data.subject, role: session.data.stakeholder })
        : t("persona.signIn")}</summary>
      <section aria-labelledby="persona-heading" className="persona account-panel">
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
        <button type="button" onClick={() => leaveSession()}>
          {t("persona.logout")}
        </button>
      ) : null}
      </section>
    </details>
  );
}
