import { useQuery } from "@tanstack/react-query";

import { PageHeader } from "../components/PageHeader";
import "./ManualsPage.css";

/** The user manuals the UI tests generate from verified screenshots (scripts/ui_manuals.py), published into the web
 *  app by scripts/publish_manuals.py: each scenario has one manual per role and one for the whole process, as HTML and
 *  Word, and a lifecycle case report. */
interface Manual { name: string; title: string; role: string; steps: number; kind: string; case_ids: string[] }
interface Catalogue { status: string; manuals: Manual[] }
interface Published { run: string; published_at: string; suite?: string }
const ROOT = "/manuals";
async function json<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(String(response.status));
  return response.json() as Promise<T>;
}

export function ManualsPage() {
  const catalogue = useQuery({ queryKey: ["manuals"], retry: false, queryFn: () => json<Catalogue>(`${ROOT}/manuals/catalogue.json`) });
  const published = useQuery({ queryKey: ["manuals-published"], retry: false, queryFn: () => json<Published>(`${ROOT}/published.json`) });
  const byTitle = new Map<string, Manual[]>();
  for (const m of catalogue.data?.manuals ?? []) byTitle.set(m.title, [...(byTitle.get(m.title) ?? []), m]);
  return <div className="stack">
    <PageHeader eyebrow="Guides" title="User manuals" current="User manuals"
      description="Step-by-step manuals for each role, made from screenshots of the screens the automated UI tests verified." />
    {published.data ? <p className="muted small">Published from test run {published.data.run} on {new Date(published.data.published_at).toLocaleString("en-IN")}
      {catalogue.data?.status === "verified" ? " · every step verified" : ""}.</p> : null}
    {catalogue.isError ? <section className="card stack" aria-labelledby="none-heading">
      <h2 id="none-heading">No manuals are published yet</h2>
      <p>Generate them from the UI tests on a running stack, then publish the latest verified run into the portal:</p>
      <pre className="manuals-command">python3 scripts/ui_manuals.py --suite smoke --no-pdf{"\n"}python3 scripts/publish_manuals.py</pre>
    </section> : null}
    {[...byTitle].map(([title, manuals]) => <section key={title} className="card stack" aria-labelledby={`m-${manuals[0].name}`}>
      <h2 id={`m-${manuals[0].name}`}>{title}</h2>
      <ul>{manuals.map((m) => <li key={m.name}>
        <a href={`${ROOT}/manuals/${m.name}.html`} target="_blank" rel="noopener noreferrer">{m.kind === "role" ? m.role : `${m.role} (whole process)`}</a>
        {" "}<span className="muted small">· {m.steps} steps · <a href={`${ROOT}/manuals/${m.name}.docx`} download>Word</a></span></li>)}</ul>
      {manuals[0].case_ids.length ? <p className="muted small">Lifecycle cases: {manuals[0].case_ids.join(", ")}</p> : null}
    </section>)}
    {catalogue.data ? <p><a href={`${ROOT}/lifecycles/index.html`} target="_blank" rel="noopener noreferrer">Lifecycle case report</a>
      <span className="muted small"> — which lifecycle cases the end-to-end tests cover, and their results.</span></p> : null}
  </div>;
}
