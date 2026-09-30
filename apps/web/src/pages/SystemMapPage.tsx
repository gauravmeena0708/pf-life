import { useState } from "react";
import { Link } from "react-router-dom";

import { EndpointCounts } from "../components/EndpointCounts";
import { PageHeader } from "../components/PageHeader";
import { RoleList } from "../components/RoleList";
import { StatusBadge } from "../components/StatusBadge";
import { SystemTotals } from "../components/SystemTotals";
import { GENERATED, INTERFACES, STAKEHOLDERS, type Coverage } from "../data/interfaces";
import { PERSONAS } from "../data/personas";

const groups = [...new Set(Object.values(STAKEHOLDERS).map((role) => role.group))].sort();
const usernames = new Set(PERSONAS.map((persona) => persona.username));

export function SystemMapPage() {
  const [search, setSearch] = useState("");
  const [coverage, setCoverage] = useState<Coverage | "">("");
  const [group, setGroup] = useState("");
  const [hasPersona, setHasPersona] = useState(false);
  const query = search.trim().toLowerCase();
  const cards = INTERFACES.flatMap((item) => {
    if (coverage && item.coverage !== coverage) return [];
    const interfaceMatches = [item.name, item.purpose].join(" ").toLowerCase().includes(query);
    const ids = item.stakeholders.filter((id) => {
      const role = STAKEHOLDERS[id];
      if (!role || (group && role.group !== group) || (hasPersona && !role.personas.some((username) => usernames.has(username)))) return false;
      const descriptions = PERSONAS.filter((persona) => role.personas.includes(persona.username)).map((persona) => persona.description);
      return interfaceMatches || [role.name, id, role.group, ...descriptions, ...role.activities.map((activity) => activity.does)].join(" ").toLowerCase().includes(query);
    });
    return ids.length || (!group && !hasPersona && interfaceMatches) ? [{ item, ids }] : [];
  });

  return <div className="stack system-map-page">
    <PageHeader eyebrow="Interfaces and roles" title="System map" description="Explore the interfaces, roles and activities recorded for this demonstration." />
    <SystemTotals />
    <section className="card map-filters" aria-label="System map filters">
      <label>Search interfaces and roles<input type="search" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
      <label>Coverage status<select value={coverage} onChange={(event) => setCoverage(event.target.value as Coverage | "")}>
        <option value="">All statuses</option><option value="Working">Working</option><option value="Mock">Simulated</option><option value="Planned">Planned</option>
      </select></label>
      <label>Stakeholder group<select value={group} onChange={(event) => setGroup(event.target.value)}>
        <option value="">All groups</option>{groups.map((value) => <option key={value} value={value}>{value}</option>)}
      </select></label>
      <label className="check-row"><input type="checkbox" checked={hasPersona} onChange={(event) => setHasPersona(event.target.checked)} />Has a demo persona</label>
    </section>
    <p className="muted small" role="status">{cards.length} of {INTERFACES.length} interfaces shown</p>
    <div className="system-map-grid">{cards.map(({ item, ids }) => <article key={item.slug} className="card stack" aria-labelledby={`map-${item.slug}`}>
      <div className="section-heading"><h2 id={`map-${item.slug}`}><Link to={`/i/${item.slug}`}>{item.name}</Link></h2><StatusBadge status={item.coverage} /></div>
      <p>{item.purpose}</p>
      <EndpointCounts counts={item.endpoints} />
      <RoleList ids={ids} />
    </article>)}</div>
    {!cards.length ? <p>No interfaces match these filters.</p> : null}
    <p className="muted small">{GENERATED}</p>
  </div>;
}
