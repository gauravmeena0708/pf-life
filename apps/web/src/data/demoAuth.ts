import { homeFor } from "./navigation";
import type { Persona } from "./personas";

export function personaLoginUrl(persona: Persona): string {
  return `/auth/login?${new URLSearchParams({ persona: persona.username, return_to: homeFor(persona.role) })}`;
}

/** A top-level POST follows the Keycloak sign-out redirect; fetch cannot complete that browser flow. */
export function leaveSession(nextPersona?: string, returnTo = "/") {
  const params = new URLSearchParams();
  if (nextPersona) {
    params.set("next_persona", nextPersona);
    params.set("return_to", returnTo);
  }
  const form = document.createElement("form");
  form.method = "POST";
  form.action = `/auth/logout${params.size ? `?${params}` : ""}`;
  const token = document.cookie.split("; ").find((cookie) => cookie.startsWith("epfo-csrf="))?.split("=")[1];
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
export function signInAs(persona: Persona, authenticated: boolean) {
  if (authenticated) leaveSession(persona.username, homeFor(persona.role));
  else window.location.assign(personaLoginUrl(persona));
}
