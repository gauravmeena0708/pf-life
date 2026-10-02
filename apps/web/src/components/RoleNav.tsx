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

/** The role's menu — as a bar across the top (groups open a list) or a tree down the side (groups fold open, with a filter).
 * Real menus the POC does not build are shown greyed out and cannot be clicked. */
export function RoleNav({ role, layout = "top" }: { role: string | undefined; layout?: "top" | "side" }) {
  const { t } = useTranslation();
  const location = useLocation();
  const profile = useQuery({ queryKey: ["member-profile"], enabled: role === "member", retry: false,
    queryFn: () => api<Envelope<{ international_worker?: boolean }>>("/api/v1/members/me") });
  const menus = role === "member" ? memberMenus(profile.data?.data.international_worker === true) : menusFor(role);
  const [open, setOpen] = useState<number | null>(null);
  const [expanded, setExpanded] = useState(false);          // the whole bar, on a phone (see roleNav.css)
  const [filter, setFilter] = useState("");
  const [folded, setFolded] = useState<Record<number, boolean>>({});
  const [showIdle, setShowIdle] = useState(false);          // side menu: items not built, hidden unless asked for
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

  // An item without a screen says why: planned in a later slice, awaiting EPFO's definition, or not in this POC.
  const unavailable = (label: string, key: string | number, inMenu = false, note?: string) => (
    <span key={key} className="nav-unavailable" aria-disabled="true" title={note ?? t("navigation.notInPoc")}>
      <span>{label}</span>{inMenu ? <span className="nav-tag" aria-hidden="true">
        {note?.startsWith("Planned") ? t("navigation.plannedShort") : t("navigation.notInPocShort")}</span> : null}
      <span className="visually-hidden"> — {note ?? t("navigation.notInPoc")}</span>
    </span>
  );

  if (layout === "side") {
    const words = filter.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const matches = (label: string, group = "") => words.every((w) => `${label} ${group}`.toLowerCase().includes(w));
    return (
      <div className={`side-nav-inner ${expanded ? "nav-expanded" : ""}`} ref={bar}>
        <button type="button" className="nav-toggle" aria-expanded={expanded} aria-controls="side-nav-items"
          onClick={() => setExpanded(!expanded)}>{t(expanded ? "nav.closeMenu" : "nav.menu")} <span aria-hidden="true">☰</span></button>
        <div id="side-nav-items" className="side-nav-items">
          <label className="side-nav-filter">{t("nav.filter")}<input type="search" value={filter} onChange={(e) => setFilter(e.target.value)} /></label>
          <label className="side-nav-show"><input type="checkbox" checked={showIdle} onChange={(e) => setShowIdle(e.target.checked)} />{t("nav.showIdle")}</label>
          <ul className="side-nav-top">
            {[{ to: homeFor(role), label: t("navigation.home"), end: true }, { to: "/public", label: t("navigation.public") }, { to: "/system-map", label: t("navigation.systemMap") }]
              .filter((x) => matches(x.label)).map((x) => <li key={x.to}><NavLink end={x.end} to={x.to}>{x.label}</NavLink></li>)}
          </ul>
          {menus.map((g, i) => {
            const label = text(g);
            if (!g.items) {
              if (!matches(label) || (!g.to && !showIdle)) return null;
              return <ul key={i} className="side-nav-top"><li>{g.to ? <NavLink to={g.to}>{label}</NavLink> : unavailable(label, i)}</li></ul>;
            }
            const items = g.items.filter((it) => matches(text(it), label) && (it.to || showIdle));
            if (!items.length) return null;
            const active = g.items.some((it) => it.to && current(it.to, location.pathname, location.hash));
            const isOpen = words.length > 0 || (folded[i] ?? active);
            return (
              <section key={i} className="side-nav-group">
                <button type="button" aria-expanded={isOpen} aria-controls={`side-nav-${i}`} className={active ? "active" : ""}
                  onClick={() => setFolded({ ...folded, [i]: !isOpen })}>
                  <span aria-hidden="true">{isOpen ? "▾" : "▸"}</span> {label}
                </button>
                {isOpen ? <ul id={`side-nav-${i}`}>{items.map((it, j) => <li key={j}>
                  {it.to ? <Link to={it.to} aria-current={current(it.to, location.pathname, location.hash) ? "page" : undefined}>{text(it)}</Link>
                    : unavailable(text(it), j, true, it.note)}</li>)}</ul> : null}
              </section>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div className={`primary-nav-inner shell-width ${expanded ? "nav-expanded" : ""}`} ref={bar}>
      <button type="button" className="nav-toggle" aria-expanded={expanded} aria-controls="primary-nav-items"
        onClick={() => setExpanded(!expanded)}>{t(expanded ? "nav.closeMenu" : "nav.menu")} <span aria-hidden="true">☰</span></button>
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
                  <li key={j}>{it.to ? <Link to={it.to}>{text(it)}</Link> : unavailable(text(it), j, true, it.note)}</li>
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
