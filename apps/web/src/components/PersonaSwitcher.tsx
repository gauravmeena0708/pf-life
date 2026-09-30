import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { getSession } from "../api/client";
import { leaveSession, signInAs } from "../data/demoAuth";
import { DEMO_PASSWORD, PERSONAS, PERSONA_GROUPS } from "../data/personas";

/** Switching persona is a real logout + login through Keycloak — never impersonation. */
export function PersonaSwitcher() {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
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

  const matching = PERSONAS.filter((persona) =>
    [persona.label, persona.username, persona.role, persona.description, persona.group].join(" ").toLowerCase().includes(search.trim().toLowerCase()));

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
      <label htmlFor="persona-search">{t("persona.search")}</label>
      <input id="persona-search" type="search" value={search} onChange={(event) => setSearch(event.target.value)} />
      <div className="persona-groups">
        {PERSONA_GROUPS.map((group) => {
          const items = matching.filter((persona) => persona.group === group);
          return items.length ? <section key={group} aria-label={group}>
            <h3>{group}</h3>
            <ul className="persona-options">{items.map((persona) => <li key={persona.username}>
              <button type="button" className="persona-option" data-persona={persona.username} onClick={() => signInAs(persona, !!session.data?.authenticated)}>
                <strong>{persona.label}</strong>
                <span>{persona.description}</span>
                <code>{persona.role}</code>
              </button>
            </li>)}</ul>
          </section> : null;
        })}
        {!matching.length ? <p role="status">{t("persona.noMatches")}</p> : null}
      </div>
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
