import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { api, command, setActingFor, type Envelope } from "../../api/client";
import en from "../../i18n/p224-reps.en.json";
import hi from "../../i18n/p224-reps.hi.json";

const scopes = ["VIEW_PROFILE", "VIEW_PASSBOOK", "VIEW_CLAIMS", "VIEW_SERVICE_HISTORY", "TRACK_GRIEVANCES", "RAISE_GRIEVANCE"] as const;
type Scope = typeof scopes[number];
type Grant = { grant_id: string; representative_subject: string; relation: string; scopes: Scope[]; valid_until: string; state: string };
type ActingMember = { grant_id: string; member_name: string; member_subject: string; relation: string; scopes: Scope[]; valid_until: string };
const destinations: Record<Scope, string> = {
  VIEW_PROFILE: "/member/profile", VIEW_PASSBOOK: "/member/passbook", VIEW_CLAIMS: "/member/claims",
  VIEW_SERVICE_HISTORY: "/member/service", TRACK_GRIEVANCES: "/member/grievances", RAISE_GRIEVANCE: "/member/grievances",
};
function useLabels() {
  const { i18n } = useTranslation();
  const labels: Record<string, string> = i18n.language?.startsWith("hi") ? hi : en;
  return (key: string) => labels[key] ?? key;
}

export function MyRepresentatives() {
  const t = useLabels();
  const [grants, setGrants] = useState<Grant[]>([]);
  const [username, setUsername] = useState("");
  const [relation, setRelation] = useState("AGENT");
  const [selected, setSelected] = useState<Scope[]>([]);
  const [validUntil, setValidUntil] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const reload = () => api<Envelope<Grant[]>>("/api/v1/members/me/representatives").then(r => setGrants(r.data));
  useEffect(() => { void reload().catch(() => setError(t("loadError"))); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!selected.length) { setError(t("chooseScope")); return; }
    setBusy(true); setError("");
    try {
      await command("POST", "/api/v1/members/me/representatives", { representative_username: username.trim(), relation, scopes: selected, valid_until: validUntil });
      setUsername(""); setSelected([]); setValidUntil("");
      await reload();
    } catch { setError(t("saveError")); } finally { setBusy(false); }
  }
  async function revoke(grantId: string) {
    if (!window.confirm(t("confirmRevoke"))) return;
    setBusy(true); setError("");
    try { await command("POST", `/api/v1/members/me/representatives/${encodeURIComponent(grantId)}/revocations`); await reload(); }
    catch { setError(t("saveError")); } finally { setBusy(false); }
  }
  return <main className="stack">
    <header><h1>{t("title")}</h1><p>{t("intro")}</p></header>
    {error && <p role="alert">{error}</p>}
    <form className="card stack" onSubmit={e => void submit(e)}>
      <div className="form-row">
        <label>{t("username")}<input required value={username} onChange={e => setUsername(e.target.value)} /></label>
        <label>{t("relation")}<select value={relation} onChange={e => setRelation(e.target.value)}><option value="AGENT">{t("agent")}</option><option value="GUARDIAN">{t("guardian")}</option></select></label>
      </div>
      <fieldset><legend>{t("scopes")}</legend>{scopes.map(scope => <label key={scope} style={{ display: "block" }}><input type="checkbox" checked={selected.includes(scope)} onChange={e => setSelected(current => e.target.checked ? [...current, scope] : current.filter(s => s !== scope))} /> {t(scope)}</label>)}</fieldset>
      <label>{t("validUntil")}<input type="date" required min={new Date(Date.now() + 86400000).toISOString().slice(0, 10)} value={validUntil} onChange={e => setValidUntil(e.target.value)} /></label>
      <button type="submit" disabled={busy}>{t("grant")}</button>
    </form>
    <section className="card stack" aria-label={t("title")}>
      {grants.length === 0 && <p>{t("empty")}</p>}
      {grants.map(grant => <article key={grant.grant_id} className="profile-card stack">
        <h2>{grant.representative_subject}</h2><p>{t(grant.relation.toLowerCase())} · {t(grant.state.toLowerCase())} · {t("validUntil")}: {grant.valid_until}</p>
        <ul>{grant.scopes.map(scope => <li key={scope}>{t(scope)}</li>)}</ul>
        {grant.state === "ACTIVE" && <button type="button" disabled={busy} onClick={() => void revoke(grant.grant_id)}>{t("revoke")}</button>}
      </article>)}
    </section>
  </main>;
}

export function RepresentativeHome() {
  const t = useLabels();
  const [members, setMembers] = useState<ActingMember[]>([]);
  const [selected, setSelected] = useState(sessionStorage.getItem("epfo-acting-for"));
  const [error, setError] = useState("");
  useEffect(() => { void api<Envelope<ActingMember[]>>("/api/v1/representatives/me/members").then(r => setMembers(r.data)).catch(() => setError(t("loadError"))); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  function choose(grantId: string | null) { setActingFor(grantId); setSelected(grantId); }
  return <main className="stack"><header><h1>{t("repTitle")}</h1><p>{t("repIntro")}</p></header>
    {error && <p role="alert">{error}</p>}
    {selected && <button type="button" onClick={() => choose(null)}>{t("stop")}</button>}
    {!members.length && <p className="card">{t("repEmpty")}</p>}
    {members.map(member => <article key={member.grant_id} className="card stack">
      <h2>{member.member_name}</h2><p>{t(member.relation.toLowerCase())} · {t("validUntil")}: {member.valid_until}</p>
      <ul>{member.scopes.map(scope => <li key={scope}>{t(scope)}</li>)}</ul>
      <button type="button" onClick={() => choose(member.grant_id)}>{t("act")}</button>
      {selected === member.grant_id && <div role="status" className="stack"><p>{t("selected")}</p>
        <nav aria-label={t("scopes")} className="actions">{member.scopes.map(scope => <a key={scope} href={destinations[scope]}>{t(scope)}</a>)}</nav>
      </div>}
    </article>)}
  </main>;
}
