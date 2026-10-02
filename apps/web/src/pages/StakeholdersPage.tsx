import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { PageHeader } from "../components/PageHeader";
import { ACTIVITIES, GENERATED, STAKEHOLDERS, type ActivityStatus } from "../data/interfaces";
import { PERSONAS } from "../data/personas";
import "./StakeholdersPage.css";

/** EPFO's hierarchy as the stakeholder register groups it: the governance bodies over Head Office (with the technology
 *  and training units), then the zones, the regional offices and the district offices; outside EPFO, the members,
 *  the employers and the institutions EPFO works with. */
const LETTER = (group: string) => group.slice(0, 1);
const TIERS: { letter: string; title: string; note: string }[] = [
  { letter: "G", title: "Governance and oversight", note: "Central Board of Trustees, its committees, the Ministry, Parliament, auditors" },
  { letter: "F", title: "Head Office", note: "Central Provident Fund Commissioner and the divisions" },
  { letter: "E", title: "Zonal Offices", note: "Additional Central PF Commissioners (Zone)" },
  { letter: "C", title: "Regional Offices", note: "RPFC-I in charge; RPFC-II / APFC; sections and their staff" },
  { letter: "D", title: "District Offices", note: "Facilitation and compliance at the district" },
];
const SIDE_UNITS = [{ letter: "H", title: "Technology and national operations" }, { letter: "I", title: "Training" }];
const OUTSIDE = [{ letter: "A", title: "Members, beneficiaries and the public" }, { letter: "B", title: "Employers and intermediaries" },
  { letter: "J", title: "External institutions and systems" }];
export const STATUS_TEXT: Record<ActivityStatus, string> = { BUILT: "Built", PARTLY: "Partly built", PLANNED: "Planned",
  EXTERNAL: "Outside the POC (adapter)", OFFLINE: "Offline / on paper", FUTURE: "Future" };
const personaLabel = new Map(PERSONAS.map((p) => [p.username, p.label]));
const ids = Object.keys(STAKEHOLDERS);
const byLetter = (letter: string) => ids.filter((id) => LETTER(STAKEHOLDERS[id].group) === letter).sort((a, b) => STAKEHOLDERS[a].name.localeCompare(STAKEHOLDERS[b].name));

function RoleChips({ letter, selected, query, onSelect }: { letter: string; selected: string; query: string; onSelect: (id: string) => void }) {
  return <ul className="org-roles">{byLetter(letter).map((id) => {
    const role = STAKEHOLDERS[id];
    const match = !query || `${role.name} ${id}`.toLowerCase().includes(query);
    return <li key={id}><button type="button" aria-pressed={selected === id} className={`org-role${match ? "" : " org-dim"}${role.personas.length ? " org-login" : ""}`}
      onClick={() => onSelect(id)} title={role.name}>{role.name}{role.personas.length ? <span className="visually-hidden"> (has a demo login)</span> : null}</button></li>;
  })}</ul>;
}

export function StakeholdersPage() {
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const selected = params.get("role") ?? "";
  const select = (id: string) => setParams(id ? { role: id } : {}, { replace: true });
  const query = search.trim().toLowerCase();
  const role = selected ? STAKEHOLDERS[selected] : undefined;
  const acts = useMemo(() => ACTIVITIES.filter((a) => a.actor === selected), [selected]);
  const tier = (letter: string, title: string, note?: string, side = false) =>
    <section className={`org-tier${side ? " org-side" : ""}`} aria-labelledby={`tier-${letter}`} key={letter}>
      <h3 id={`tier-${letter}`}>{title} <span className="muted small">· {byLetter(letter).length}</span></h3>
      {note ? <p className="muted small">{note}</p> : null}
      <RoleChips letter={letter} selected={selected} query={query} onSelect={select} />
    </section>;

  return <div className="stack stakeholders-page">
    <PageHeader eyebrow="Interfaces and roles" title="Stakeholders" current="Stakeholders"
      description="Who works in and with EPFO, arranged by the organisation's hierarchy. Select a role for its demo login, what it does and how much of that is built." />
    <section className="card map-filters" aria-label="Find a role">
      <label>Find a role<input type="search" value={search} onChange={(e) => setSearch(e.target.value)} /></label>
      <p className="muted small">Roles with a gold edge have a demo login. {ids.length} roles in all.</p>
    </section>
    <div className="org-layout">
      <div className="org-chart" role="group" aria-label="EPFO hierarchy">
        {TIERS.map((t, i) => <div key={t.letter} className="org-level">
          {i > 0 ? <div className="org-connector" aria-hidden="true" /> : null}
          {t.letter === "F" ? <div className="org-row">{tier("F", t.title, t.note)}<div className="org-units">{SIDE_UNITS.map((u) => tier(u.letter, u.title, undefined, true))}</div></div>
            : tier(t.letter, t.title, t.note)}
        </div>)}
        <h2 className="org-outside-heading">Outside EPFO</h2>
        <div className="org-outside">{OUTSIDE.map((o) => tier(o.letter, o.title, undefined, true))}</div>
      </div>
      <aside className="card stack org-detail" aria-live="polite" aria-labelledby="role-heading">
        {role ? <>
          <h2 id="role-heading">{role.name}</h2>
          <p className="muted small"><code>{selected}</code> · {role.group}</p>
          <p>{role.personas.length ? <>Demo login: {role.personas.map((u) => <span key={u} className="state-pill">{personaLabel.get(u) ?? u} ({u})</span>)}</> : "No demo login."}</p>
          <p>Endpoints it may call: {role.endpoints.W} working, {role.endpoints.M} simulated, {role.endpoints.P} planned.</p>
          <h3>What it does ({acts.length})</h3>
          {acts.length ? <ul className="org-acts">{acts.map((a) => <li key={a.id}>
            <Link to={`/lifecycles?flow=${a.flow}&activity=${encodeURIComponent(a.id)}`}>{a.does}</Link>
            <span className={`life-status life-${a.status.toLowerCase()}`}>{STATUS_TEXT[a.status]}</span></li>)}</ul>
            : <p className="muted">No activity recorded.</p>}
          <button type="button" className="secondary" onClick={() => select("")}>Clear</button>
        </> : <><h2 id="role-heading">Select a role</h2><p className="muted">The chart follows EPFO's line of authority: the Central Board of Trustees
          and the Ministry over Head Office; Head Office over the zones; each zone over its regional offices; regional offices over the district
          offices. Choose any role to see its work and its demo login.</p></>}
      </aside>
    </div>
    <p className="muted small">{GENERATED}</p>
  </div>;
}
