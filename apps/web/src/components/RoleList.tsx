import { useQuery } from "@tanstack/react-query";

import { getSession } from "../api/client";
import { STAKEHOLDERS } from "../data/interfaces";
import { PERSONAS } from "../data/personas";
import { EndpointCounts } from "./EndpointCounts";
import { PersonaLink } from "./PersonaLink";

export function RoleList({ ids }: { ids: string[] }) {
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  return <ul className="role-list">{ids.map((id) => {
    const role = STAKEHOLDERS[id];
    if (!role) return null;
    const personas = PERSONAS.filter((persona) => role.personas.includes(persona.username));
    return <li key={id}><details className="role-details">
      <summary><span>{role.name}</span> <code className="small muted">{id}</code></summary>
      <div className="role-content stack">
        <p className="muted small">{role.group}</p>
        <EndpointCounts counts={role.endpoints} />
        {role.activities.length ? <ul className="role-activities">{role.activities.map((activity) =>
          <li key={activity.id}>{activity.does}</li>)}</ul> : <p className="muted small">No activities recorded.</p>}
        {personas.length ? <div className="actions">{personas.map((persona) => <PersonaLink key={persona.username}
          persona={persona} authenticated={!!session.data?.authenticated} className="button secondary">
          Try as {persona.label}
        </PersonaLink>)}</div> : null}
      </div>
    </details></li>;
  })}</ul>;
}
