import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink, useLocation } from "react-router-dom";

import { api, type Envelope } from "../api/client";
import { homeFor, memberMenus, menusFor, type NavGroup, type NavItem } from "../data/navigation";
import "./roleNav.css";

/** A menu item is the current page when its path matches and, for a link to a section, its section too. */
const current = (to: string, pathname: string, hash: string) => {
  const [path, section] = to.split("#");
  return path === pathname && (!section || `#${section}` === hash);
};

/** The role's menu bar: plain links, and groups that open a list. Real menus the POC does not build are shown
 * greyed out and cannot be clicked. */
export function RoleNav({ role }: { role: string | undefined }) {
  const { t } = useTranslation();
  const location = useLocation();
  const profile = useQuery({ queryKey: ["member-profile"], enabled: role === "member", retry: false,
    queryFn: () => api<Envelope<{ international_worker?: boolean }>>("/api/v1/members/me") });
  const menus = role === "member" ? memberMenus(profile.data?.data.international_worker === true) : menusFor(role);
  const [open, setOpen] = useState<number | null>(null);
  const [expanded, setExpanded] = useState(false);          // the whole bar, on a phone (see roleNav.css)
  const bar = useRef<HTMLDivElement>(null);
  const text = (x: NavItem | NavGroup) => (x.labelKey ? t(x.labelKey) : x.label) ?? "";

  useEffect(() => { setOpen(null); setExpanded(false); }, [location.pathname, location.hash]);
  useEffect(() => {
    const outside = (e: PointerEvent) => { if (bar.current && !bar.current.contains(e.target as Node)) setOpen(null); };
    const escape = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(null); };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape); };
  }, []);

  const unavailable = (label: string, key: string | number, inMenu = false) => (
    <span key={key} className="nav-unavailable" aria-disabled="true" title={t("navigation.notInPoc")}>
      <span>{label}</span>{inMenu ? <span className="nav-tag" aria-hidden="true">{t("navigation.notInPocShort")}</span> : null}
      <span className="visually-hidden"> — {t("navigation.notInPoc")}</span>
    </span>
  );

  return (
    <div className={`primary-nav-inner shell-width ${expanded ? "nav-expanded" : ""}`} ref={bar}>
      <button type="button" className="nav-toggle" aria-expanded={expanded} aria-controls="primary-nav-items"
        onClick={() => setExpanded(!expanded)}>{expanded ? "Close menu" : "Menu"} <span aria-hidden="true">☰</span></button>
      <div id="primary-nav-items" className="nav-items">
      <NavLink end to={homeFor(role)}>{t("navigation.home")}</NavLink>
      <NavLink to="/public">{t("navigation.public")}</NavLink>
      <NavLink to="/system-map">{t("navigation.systemMap")}</NavLink>
      {menus.map((g, i) => {
        if (!g.items) return g.to ? <NavLink key={i} to={g.to}>{text(g)}</NavLink> : unavailable(text(g), i);
        const active = g.items.some((it) => it.to && current(it.to, location.pathname, location.hash));
        const working = g.items.some((it) => it.to);
        return (
          <div key={i} className="nav-group">
            <button type="button" aria-expanded={open === i} aria-controls={`nav-menu-${i}`}
              className={`${active ? "active" : ""} ${working ? "" : "nav-group-idle"}`} onClick={() => setOpen(open === i ? null : i)}>
              {text(g)} <span aria-hidden="true">▾</span>
            </button>
            {open === i ? (
              <ul id={`nav-menu-${i}`} className="nav-menu">
                {g.items.map((it, j) => (
                  <li key={j}>{it.to ? <Link to={it.to}>{text(it)}</Link> : unavailable(text(it), j, true)}</li>
                ))}
              </ul>
            ) : null}
          </div>
        );
      })}
      </div>
    </div>
  );
}
