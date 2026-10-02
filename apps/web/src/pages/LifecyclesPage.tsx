import { useMemo, type KeyboardEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { PageHeader } from "../components/PageHeader";
import { ACTIVITIES, FLOWS, GENERATED, STAKEHOLDERS, type Activity } from "../data/interfaces";
import { STATUS_TEXT } from "./StakeholdersPage";
import "./StakeholdersPage.css";
import "./LifecyclesPage.css";

/** Each lifecycle (flow) as a network: who does what, and what follows. Activities are placed left to right by the
 *  longest chain of "next" steps that leads to them; a step that loops back is drawn dashed. */
const W = 220, H = 74, GAP_X = 64, GAP_Y = 18, PAD = 16;
const name = (id: string) => STAKEHOLDERS[id]?.name ?? id;
const clip = (text: string, n: number) => (text.length > n ? text.slice(0, n - 1).trimEnd() + "…" : text);
function wrap(text: string, width: number, lines: number): string[] {
  const out: string[] = []; let line = "";
  for (const word of text.split(/\s+/)) {
    if ((line + " " + word).trim().length > width) { out.push(line.trim()); line = word; if (out.length === lines) break; } else line = `${line} ${word}`;
  }
  if (out.length < lines && line.trim()) out.push(line.trim());
  const used = out.join(" ").length;
  if (used < text.length && out.length) out[out.length - 1] = clip(out[out.length - 1] + " …", width);
  return out.slice(0, lines);
}

export interface Placed { act: Activity; layer: number; row: number }
/** Layers by the longest path over forward edges (an edge into a node already on the path is a loop and ignored). */
export function layout(acts: Activity[]): { placed: Placed[]; back: Set<string> } {
  const ids = new Set(acts.map((a) => a.id));
  const byId = new Map(acts.map((a) => [a.id, a]));
  const layer = new Map<string, number>(); const back = new Set<string>(); const state = new Map<string, number>();
  const visit = (id: string, depth: number) => {
    if (state.get(id) === 1) return;                          // on the current path: a loop
    if ((layer.get(id) ?? -1) >= depth && state.get(id) === 2) return;
    layer.set(id, Math.max(layer.get(id) ?? 0, depth)); state.set(id, 1);
    for (const next of byId.get(id)?.next ?? []) {
      if (!ids.has(next)) continue;
      if (state.get(next) === 1) { back.add(`${id}>${next}`); continue; }
      visit(next, depth + 1);
    }
    state.set(id, 2);
  };
  const targets = new Set(acts.flatMap((a) => a.next.filter((n) => ids.has(n))));
  for (const a of acts) if (!targets.has(a.id)) visit(a.id, 0);
  for (const a of acts) if (!layer.has(a.id)) visit(a.id, 0);   // a flow that is all loop
  for (let pass = 0; pass < acts.length; pass += 1) {           // a step nothing leads to sits just before its first successor
    let moved = false;
    for (const a of acts) {
      if (targets.has(a.id)) continue;
      const succ = a.next.filter((n) => ids.has(n) && !back.has(`${a.id}>${n}`)).map((n) => layer.get(n) ?? 0);
      const want = succ.length ? Math.max(0, Math.min(...succ) - 1) : layer.get(a.id) ?? 0;
      if (want > (layer.get(a.id) ?? 0)) { layer.set(a.id, want); moved = true; }
    }
    if (!moved) break;
  }
  const rows = new Map<number, string[]>();
  for (const a of acts) { const l = layer.get(a.id) ?? 0; rows.set(l, [...(rows.get(l) ?? []), a.id]); }
  const rowOf = new Map<string, number>();
  for (const l of [...rows.keys()].sort((x, y) => x - y)) {     // order each layer by where its predecessors sit
    const avg = (id: string) => { const preds = acts.filter((a) => a.next.includes(id) && rowOf.has(a.id)).map((a) => rowOf.get(a.id) ?? 0);
      return preds.length ? preds.reduce((s, v) => s + v, 0) / preds.length : Number.MAX_SAFE_INTEGER; };
    (rows.get(l) ?? []).sort((x, y) => avg(x) - avg(y)).forEach((id, i) => rowOf.set(id, i));
  }
  return { placed: acts.map((act) => ({ act, layer: layer.get(act.id) ?? 0, row: rowOf.get(act.id) ?? 0 })), back };
}

const flowIds = Object.keys(FLOWS).sort();
export function LifecyclesPage() {
  const [params, setParams] = useSearchParams();
  const flow = params.get("flow") && FLOWS[params.get("flow") ?? ""] ? String(params.get("flow")) : "F06";
  const selected = params.get("activity") ?? "";
  const acts = useMemo(() => ACTIVITIES.filter((a) => a.flow === flow), [flow]);
  const { placed, back } = useMemo(() => layout(acts), [acts]);
  const pos = new Map(placed.map((p) => [p.act.id, { x: PAD + p.layer * (W + GAP_X), y: PAD + p.row * (H + GAP_Y) }]));
  const width = PAD * 2 + (Math.max(0, ...placed.map((p) => p.layer)) + 1) * (W + GAP_X) - GAP_X;
  const height = PAD * 2 + (Math.max(0, ...placed.map((p) => p.row)) + 1) * (H + GAP_Y) - GAP_Y;
  const choose = (id: string) => setParams({ flow, ...(id ? { activity: id } : {}) }, { replace: true });
  const current = acts.find((a) => a.id === selected);
  const actors = new Set(acts.map((a) => a.actor));
  const counts = (f: string) => { const xs = ACTIVITIES.filter((a) => a.flow === f); return `${xs.length} activities, ${xs.filter((a) => a.status === "BUILT").length} built`; };
  const key = (e: KeyboardEvent, id: string) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); choose(id); } };
  const steps = [...placed].sort((a, b) => a.layer - b.layer || a.row - b.row);

  return <div className="stack lifecycles-page">
    <PageHeader eyebrow="Interfaces and roles" title="Lifecycles" current="Lifecycles"
      description="Each lifecycle as a network of stakeholders and what they do, step by step, with how much of it this demonstration has built." />
    <section className="card map-filters" aria-label="Choose a lifecycle">
      <label>Lifecycle<select value={flow} onChange={(e) => setParams({ flow: e.target.value }, { replace: true })}>
        {flowIds.map((f) => <option key={f} value={f}>{f} · {FLOWS[f]} — {counts(f)}</option>)}</select></label>
      <p className="muted small">{acts.length} activities by {actors.size} stakeholders. Colours: <span className="life-status life-built">Built</span>{" "}
        <span className="life-status life-partly">Partly built</span> <span className="life-status life-planned">Planned</span>{" "}
        <span className="life-status life-external">Outside the POC / future</span>. A dashed arrow loops back.</p>
    </section>
    <div className="life-layout">
      <section className="card life-canvas" aria-labelledby="network-heading">
        <h2 id="network-heading">{FLOWS[flow]}</h2>
        <div className="life-scroll">
          <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="group" aria-label={`Network of ${FLOWS[flow]}`}>
            <defs><marker id="life-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" fill="#667085" /></marker></defs>
            {acts.flatMap((a) => a.next.filter((n) => pos.has(n)).map((n) => {
              const s = pos.get(a.id)!, t = pos.get(n)!; const loop = back.has(`${a.id}>${n}`) || t.x <= s.x;
              const x1 = s.x + W, y1 = s.y + H / 2, x2 = t.x, y2 = t.y + H / 2;
              const d = loop ? `M${s.x + W / 2},${s.y + H} C${s.x + W / 2},${Math.max(s.y, t.y) + H + 40} ${t.x + W / 2},${Math.max(s.y, t.y) + H + 40} ${t.x + W / 2},${t.y + H}`
                : `M${x1},${y1} C${x1 + GAP_X / 2},${y1} ${x2 - GAP_X / 2},${y2} ${x2},${y2}`;
              const lit = selected === a.id || selected === n;
              return <path key={`${a.id}>${n}`} d={d} className={`life-edge${loop ? " life-loop" : ""}${lit ? " life-lit" : ""}`} markerEnd="url(#life-arrow)" />;
            }))}
            {placed.map(({ act }) => {
              const { x, y } = pos.get(act.id)!;
              return <g key={act.id} transform={`translate(${x},${y})`} className={`life-node life-${act.status.toLowerCase()}${selected === act.id ? " life-selected" : ""}`}
                role="button" tabIndex={0} aria-pressed={selected === act.id} aria-label={`${name(act.actor)}: ${act.does}. ${STATUS_TEXT[act.status]}.`}
                onClick={() => choose(act.id)} onKeyDown={(e) => key(e, act.id)}>
                <rect width={W} height={H} rx="6" />
                <rect width="5" height={H} rx="2" className="life-band" />
                <text x="12" y="18" className="life-actor">{clip(name(act.actor), 30)}</text>
                {wrap(act.does, 34, 3).map((line, i) => <text key={i} x="12" y={36 + i * 14} className="life-does">{line}</text>)}
              </g>;
            })}
          </svg>
        </div>
      </section>
      <aside className="card stack org-detail" aria-live="polite" aria-labelledby="step-heading">
        {current ? <>
          <h2 id="step-heading">{current.does}</h2>
          <p><span className={`life-status life-${current.status.toLowerCase()}`}>{STATUS_TEXT[current.status]}</span> · <code>{current.id}</code>
            {current.endpoints ? ` · ${current.endpoints} endpoint${current.endpoints === 1 ? "" : "s"}` : ""}</p>
          <p>By <Link to={`/stakeholders?role=${encodeURIComponent(current.actor)}`}>{name(current.actor)}</Link>
            {STAKEHOLDERS[current.actor]?.personas.length ? ` — demo login ${STAKEHOLDERS[current.actor].personas.join(", ")}` : " — no demo login"}.</p>
          {current.next.length ? <><h3>What follows</h3><ul>{current.next.map((n) => {
            const target = ACTIVITIES.find((a) => a.id === n);
            return <li key={n}>{target ? <Link to={`/lifecycles?flow=${target.flow}&activity=${encodeURIComponent(n)}`}>{target.does}</Link> : n}
              {target && target.flow !== flow ? <span className="muted small"> (in {FLOWS[target.flow]})</span> : null}</li>;
          })}</ul></> : <p className="muted">The lifecycle ends here.</p>}
          {current.src ? <p className="muted small">Source: {current.src}</p> : null}
        </> : <><h2 id="step-heading">Select a step</h2><p className="muted">Choose a box in the network (or a step below) to see who does it,
          whether its screens and services are built, and what follows — including steps that continue in another lifecycle.</p></>}
      </aside>
    </div>
    <section className="card stack" aria-labelledby="steps-heading">
      <h2 id="steps-heading">Steps in order</h2>
      <ol className="life-steps">{steps.map(({ act, layer }) => <li key={act.id}>
        <button type="button" className="life-step" aria-pressed={selected === act.id} onClick={() => choose(act.id)}>
          <span className="muted small">Stage {layer + 1}</span> <strong>{name(act.actor)}</strong> — {act.does}</button>
        <span className={`life-status life-${act.status.toLowerCase()}`}>{STATUS_TEXT[act.status]}</span></li>)}</ol>
    </section>
    <p className="muted small">{GENERATED}</p>
  </div>;
}
