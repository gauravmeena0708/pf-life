import type { ReactNode } from "react";

import { personaLoginUrl, signInAs } from "../data/demoAuth";
import type { Persona } from "../data/personas";

export function PersonaLink({ persona, authenticated, children, className }: {
  persona: Persona; authenticated: boolean; children: ReactNode; className?: string;
}) {
  return <a href={personaLoginUrl(persona)} className={className} onClick={(event) => {
    event.preventDefault();
    signInAs(persona, authenticated);
  }}>{children}</a>;
}
