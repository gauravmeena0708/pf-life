import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { homeFor, menusFor, type NavGroup, type NavItem } from "../data/navigation";

/** Jump to any screen the role's menu offers: Ctrl+K (⌘K on a Mac) or the button opens a search over every working menu
 *  item; the arrows choose, Enter opens, Escape closes. Items the POC does not build are not offered. */
export function MenuSearch({ role }: { role: string | undefined }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const opener = useRef<HTMLButtonElement>(null);
  const text = (x: NavItem | NavGroup) => (x.labelKey ? t(x.labelKey) : x.label) ?? "";

  const entries = useMemo(() => {
    const out: { label: string; group: string; to: string }[] = [{ label: t("navigation.home"), group: "", to: homeFor(role) },
      { label: t("navigation.systemMap"), group: "", to: "/system-map" }];
    for (const g of menusFor(role)) {
      if (g.to) out.push({ label: text(g), group: "", to: g.to });
      for (const it of g.items ?? []) if (it.to) out.push({ label: text(it), group: text(g), to: it.to });
    }
    return out.filter((e, i) => out.findIndex((o) => o.to === e.to && o.label === e.label) === i);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role, t]);
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const results = entries.filter((e) => words.every((w) => `${e.label} ${e.group}`.toLowerCase().includes(w))).slice(0, 12);

  useEffect(() => {
    const shortcut = (e: globalThis.KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen(true); }
    };
    document.addEventListener("keydown", shortcut);
    return () => document.removeEventListener("keydown", shortcut);
  }, []);
  useEffect(() => { if (open) { setQuery(""); setIndex(0); input.current?.focus(); } }, [open]);

  function close() { setOpen(false); opener.current?.focus(); }
  function go(to: string) { setOpen(false); navigate(to); }
  function keys(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") { e.preventDefault(); setIndex((i) => Math.min(i + 1, results.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setIndex((i) => Math.max(i - 1, 0)); }
    else if (e.key === "Enter" && results[index]) { e.preventDefault(); go(results[index].to); }
    else if (e.key === "Escape") { e.preventDefault(); close(); }
  }

  return <>
    <button type="button" className="menu-search-button" ref={opener} onClick={() => setOpen(true)} aria-haspopup="dialog">
      {t("nav.searchMenus")} <kbd aria-hidden="true">Ctrl K</kbd>
    </button>
    {open ? <div className="menu-search-backdrop" onClick={close}>
      <div className="menu-search" role="dialog" aria-modal="true" aria-label={t("nav.searchMenus")} onClick={(e) => e.stopPropagation()}>
        <label className="visually-hidden" htmlFor="menu-search-input">{t("nav.searchMenus")}</label>
        <input id="menu-search-input" ref={input} type="search" value={query} placeholder={t("nav.searchPlaceholder")} autoComplete="off"
          role="combobox" aria-expanded="true" aria-controls="menu-search-results" aria-activedescendant={results[index] ? `menu-search-${index}` : undefined}
          onChange={(e) => { setQuery(e.target.value); setIndex(0); }} onKeyDown={keys} />
        <ul id="menu-search-results" role="listbox" aria-label={t("nav.searchResults")}>
          {results.map((r, i) => <li key={`${r.to}-${r.label}`} id={`menu-search-${i}`} role="option" aria-selected={i === index}
            onMouseEnter={() => setIndex(i)} onClick={() => go(r.to)}>
            <strong>{r.label}</strong>{r.group ? <span className="muted small"> · {r.group}</span> : null}</li>)}
          {!results.length ? <li className="muted" role="option" aria-selected="false" aria-disabled="true">{t("nav.noMatch")}</li> : null}
        </ul>
      </div>
    </div> : null}
  </>;
}
