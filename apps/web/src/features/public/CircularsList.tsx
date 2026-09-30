import { statusLabel } from "../statusLabel";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";

export const CIRCULAR_CATEGORIES = ["CLAIMS", "PENSION", "COMPLIANCE", "MEMBER_SERVICES", "GENERAL"];
export interface Circular {
  circular_id: string; number: string; version: number; title: string; category: string; issued_on: string;
  summary: string; state: string; sha256: string; published_at: string | null; body: string;
}
interface CircularList { circulars: Circular[]; categories: string[]; note: string }

export function CircularsList() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const category = params.get("category") ?? "";
  const q = params.get("q") ?? "";
  const number = params.get("number") ?? "";
  const search = new URLSearchParams();
  if (category) search.set("category", category);
  if (q) search.set("q", q);
  if (number) search.set("number", number);
  const query = search.toString();
  const list = useQuery({ queryKey: ["public-circulars", query], retry: false,
    queryFn: () => api<Envelope<CircularList>>(`/api/v1/public/circulars${query ? `?${query}` : ""}`) });
  const selected = list.data?.data.circulars.find((item) => item.circular_id === selectedId);

  return <section className="card stack" aria-labelledby="circulars-heading">
    <h2 id="circulars-heading">{number ? `Versions of circular ${number}` : "Circulars"}</h2>
    <form className="form-row" aria-label="Filter circulars" key={params.toString()} onSubmit={(e) => {
      e.preventDefault(); const f = new FormData(e.currentTarget); const next = new URLSearchParams();
      for (const key of ["category", "q"]) { const value = String(f.get(key) ?? "").trim(); if (value) next.set(key, value); }
      if (number) next.set("number", number);
      setSelectedId(null); setParams(next);
    }}>
      <label>Category<select name="category" defaultValue={category}><option value="">All categories</option>
        {(list.data?.data.categories ?? CIRCULAR_CATEGORIES).map((value) => <option key={value} value={value}>{value.replaceAll("_", " ").toLowerCase()}</option>)}
      </select></label>
      <label>Search circulars<input name="q" defaultValue={q} maxLength={100} /></label>
      <button type="submit">Search</button>
      {number ? <Link to="?">Current circulars</Link> : null}
    </form>
    <ProblemMessage error={list.error} />
    {list.isLoading ? <p role="status">Loading circulars…</p> : null}
    {list.data ? <p className="muted">{list.data.data.note}</p> : null}
    {list.data?.data.circulars.length === 0 ? <p>No matching circulars.</p> : null}
    <ul className="result-cards">{list.data?.data.circulars.map((item) => <li key={item.circular_id}>
      <div className="stack"><h3><button type="button" className="lookup-link" onClick={() => setSelectedId(item.circular_id)}>{item.title}</button></h3>
        <p>{item.number} · Version {item.version} · {item.issued_on} · {statusLabel(item.state, t)}</p>
        <p>{item.summary}</p><Link to={`?${new URLSearchParams({ number: item.number })}`}>Versions of {item.number}</Link>
      </div>
    </li>)}</ul>
    {selected ? <article className="profile-card stack" aria-labelledby="circular-body-heading">
      <h3 id="circular-body-heading">{selected.title}</h3>
      <p>{selected.number} · Version {selected.version} · {selected.category.replaceAll("_", " ").toLowerCase()}</p>
      <p>Published: {selected.published_at ?? "Not recorded"}</p>
      <div style={{ whiteSpace: "pre-wrap" }}>{selected.body}</div>
      <p className="small">SHA-256: <code>{selected.sha256}</code></p>
      <Link to={`?${new URLSearchParams({ number: selected.number })}`}>Versions of {selected.number}</Link>
    </article> : null}
  </section>;
}

export function PublicCircularsPage() {
  return <section className="stack" aria-labelledby="public-circulars-page-heading">
    <PageHeader id="public-circulars-page-heading" eyebrow="Public services · synthetic POC" title="Circulars and notifications"
      description="Read current demonstration circulars and their earlier versions." current="Circulars" parent={{ label: "Public services", to: "/public" }} />
    <CircularsList />
  </section>;
}
