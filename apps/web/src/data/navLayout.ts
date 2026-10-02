import { useCallback, useEffect, useState } from "react";

/** Where the role's menu sits: a bar across the top (few items: members, employers, the public) or a tree down the side
 *  (many groups: office, zone, head office). Each user may choose; the choice is kept in this browser. */
export type NavLayout = "top" | "side";
const KEY = "epfo.nav-layout";
const EVENT = "epfo-nav-layout";
const OFFICE = /^(fo|do|zo|ho|gov|train|tech|ext)\.|^audit|^cert/;

export function defaultLayout(role: string | undefined): NavLayout {
  return role && OFFICE.test(role) ? "side" : "top";
}

function stored(): NavLayout | null {
  try {
    const value = window.localStorage.getItem(KEY);
    return value === "top" || value === "side" ? value : null;
  } catch { return null; }            // storage blocked (private window, previews): the role's default applies
}

export function useNavLayout(role: string | undefined): [NavLayout, (layout: NavLayout) => void] {
  const [chosen, setChosen] = useState<NavLayout | null>(stored);
  useEffect(() => {
    const sync = () => setChosen(stored());
    window.addEventListener(EVENT, sync);
    window.addEventListener("storage", sync);
    return () => { window.removeEventListener(EVENT, sync); window.removeEventListener("storage", sync); };
  }, []);
  const choose = useCallback((layout: NavLayout) => {
    try { window.localStorage.setItem(KEY, layout); } catch { /* kept for this page only */ }
    setChosen(layout);
    window.dispatchEvent(new Event(EVENT));
  }, []);
  return [chosen ?? defaultLayout(role), choose];
}
