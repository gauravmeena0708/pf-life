import { FormEvent, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api, command, Envelope } from "../api/client";
import { PensionEnquiries } from "./PensionEnquiries";
import { PageHeader } from "../components/PageHeader";
import { ProblemMessage } from "../components/ProblemMessage";

type SearchMode = "any" | "name" | "code" | "registration" | "pincode" | "industry";
type NameMatch = "contains" | "starts_with";
type Coverage = "" | "REGISTERED" | "VERIFIED";
type Establishment = {
  establishment_id: string; registration_number: string; legal_name: string;
  office_id: string; pincode?: string; city?: string; district?: string;
  establishment_type?: string; industry_group?: string; exemption_status?: string; status: string;
};
type Profile = Omit<Establishment, "status"> & {
  coverage_status: string; coverage_date: string | null; verified_at: string | null;
};
type Challenge = { challenge_id: string; prompt: string; proof_type: string };
type TrrnStatus = {
  trrn: string; status: string; wage_month: string | null; issued_at: string | null;
  paid_at: string | null; next_step: string; label: string;
};
type PublicDefaulters = {
  establishments: { establishment_id: string; legal_name: string | null; office_id: string;
    defaults: { kind: string; wage_months: string[] }[]; since: string }[];
  label: string; note: string;
};

const SEARCH_MODES: { value: SearchMode; label: string; hint: string }[] = [
  { value: "any", label: "All fields", hint: "Name, industry, exact code, registration or pincode" },
  { value: "name", label: "Name", hint: "Try Demo Engineering" },
  { value: "code", label: "EPF code", hint: "Try EST-DEMO-0002" },
  { value: "registration", label: "Registration no.", hint: "Try DEMO/00002/000" },
  { value: "pincode", label: "Pincode", hint: "Try 110002" },
  { value: "industry", label: "Industry", hint: "Try engineering" },
];

function dateTime(value: string | null): string {
  return value ? new Date(value).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "Not recorded";
}

function dateOnly(value: string | null): string {
  return value ? new Date(`${value}T00:00:00Z`).toLocaleDateString("en-IN", { dateStyle: "medium", timeZone: "UTC" }) : "Not recorded";
}

function label(value: string): string {
  return value.replaceAll("_", " ").toLowerCase().replace(/^./, (letter) => letter.toUpperCase());
}

export function PublicLookups() {
  const defaulters = useQuery({ queryKey: ["public-defaulting-establishments"], retry: false,
    queryFn: () => api<Envelope<PublicDefaulters>>("/api/v1/public/defaulting-establishments") });
  const [mode, setMode] = useState<SearchMode>("name");
  const [query, setQuery] = useState("");
  const [match, setMatch] = useState<NameMatch>("contains");
  const [office, setOffice] = useState("");
  const [city, setCity] = useState("");
  const [district, setDistrict] = useState("");
  const [establishmentType, setEstablishmentType] = useState("");
  const [exemption, setExemption] = useState("");
  const [coverage, setCoverage] = useState<Coverage>("");
  const [page, setPage] = useState(1);
  const [results, setResults] = useState<Establishment[] | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [searchError, setSearchError] = useState<unknown>(null);
  const [searchBusy, setSearchBusy] = useState(false);
  const [trrn, setTrrn] = useState("");
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [answer, setAnswer] = useState("");
  const [trrnResult, setTrrnResult] = useState<TrrnStatus | null>(null);
  const [trrnError, setTrrnError] = useState<unknown>(null);
  const [trrnBusy, setTrrnBusy] = useState(false);

  async function search(nextPage: number) {
    setSearchBusy(true);
    setSearchError(null);
    setProfile(null);
    try {
      const params = new URLSearchParams({ query: query.trim(), mode, match, page: String(nextPage) });
      if (office.trim()) params.set("office_id", office.trim());
      if (city.trim()) params.set("city", city.trim());
      if (district.trim()) params.set("district", district.trim());
      if (establishmentType) params.set("establishment_type", establishmentType);
      if (exemption) params.set("exemption_status", exemption);
      if (coverage) params.set("status", coverage);
      const response = await api<Envelope<Establishment[]>>(`/api/v1/public/establishments?${params}`);
      setResults(response.data);
      setPage(nextPage);
    } catch (error) {
      setSearchError(error);
    } finally {
      setSearchBusy(false);
    }
  }

  async function openProfile(id: string) {
    setSearchError(null);
    try {
      const response = await api<Envelope<Profile>>(`/api/v1/public/establishments/${encodeURIComponent(id)}`);
      setProfile(response.data);
    } catch (error) {
      setSearchError(error);
    }
  }

  async function loadChallenge() {
    setTrrnError(null);
    setTrrnResult(null);
    setAnswer("");
    try {
      const response = await api<Envelope<Challenge>>( "/api/v1/public/demo-challenges");
      setChallenge(response.data);
    } catch (error) {
      setChallenge(null);
      setTrrnError(error);
    }
  }

  async function lookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!challenge) return;
    setTrrnBusy(true);
    setTrrnError(null);
    setTrrnResult(null);
    try {
      const response = await command<Envelope<TrrnStatus>>( "POST", "/api/v1/public/trrn-status-lookups", {
        trrn: trrn.trim().toUpperCase(), challenge_id: challenge.challenge_id, answer: Number(answer),
      });
      setTrrnResult(response.data);
    } catch (error) {
      setTrrnError(error);
    } finally {
      setTrrnBusy(false);
      setChallenge(null);
      setAnswer("");
    }
  }

  const activeMode = SEARCH_MODES.find((item) => item.value === mode)!;

  return <div className="stack public-lookups">
    <PageHeader eyebrow="Public register · synthetic POC" title="Find an establishment"
      description="Search by name, EPF code, registration number, pincode or industry. Open a result to see its public demo profile."
      current="Public services"><span className="state-pill">Seeded demo records</span></PageHeader>

    <section className="card stack" aria-labelledby="establishment-search">
      <div className="section-heading"><div><p className="eyebrow">01 / Directory</p><h2 id="establishment-search">Establishment search</h2></div><span className="muted small">20 per page · first 5 pages</span></div>
      <form className="stack" onSubmit={(event) => { event.preventDefault(); void search(1); }}>
        <fieldset className="search-modes"><legend>Search by</legend><div className="mode-options">
          {SEARCH_MODES.map((item) => <label key={item.value} className={mode === item.value ? "mode-option selected" : "mode-option"}>
            <input type="radio" name="search-mode" value={item.value} checked={mode === item.value} onChange={() => { setMode(item.value); setResults(null); setProfile(null); }} />{item.label}
          </label>)}
        </div></fieldset>
        <div className="search-input-row"><label>Search term
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={activeMode.hint}
            minLength={mode === "pincode" ? 6 : 3} maxLength={60} pattern={mode === "pincode" ? "[0-9]{6}" : undefined} required />
        </label><button className="primary" disabled={searchBusy}>{searchBusy ? "Searching…" : "Search register"}</button></div>
        <details className="filter-panel"><summary>Refine results</summary><div className="form-row">
          {(mode === "name" || mode === "any") && <label>Name match<select value={match} onChange={(event) => setMatch(event.target.value as NameMatch)}><option value="contains">Contains</option><option value="starts_with">Starts with</option></select></label>}
          <label>Coverage status<select value={coverage} onChange={(event) => setCoverage(event.target.value as Coverage)}><option value="">Any active status</option><option value="REGISTERED">Registered</option><option value="VERIFIED">Verified</option></select></label>
          <label>Office code<input value={office} onChange={(event) => setOffice(event.target.value)} placeholder="RO-DEMO-01" maxLength={40} /></label>
          <label>City<input value={city} onChange={(event) => setCity(event.target.value)} placeholder="New Delhi" maxLength={80} /></label>
          <label>District<input value={district} onChange={(event) => setDistrict(event.target.value)} placeholder="Central Delhi" maxLength={80} /></label>
          <label>Establishment type<select value={establishmentType} onChange={(event) => setEstablishmentType(event.target.value)}><option value="">Any type</option><option value="PRIVATE_COMPANY">Private company</option><option value="PARTNERSHIP">Partnership</option><option value="COOPERATIVE">Cooperative</option></select></label>
          <label>Exemption<select value={exemption} onChange={(event) => setExemption(event.target.value)}><option value="">Any status</option><option value="NOT_EXEMPT">Not exempt</option><option value="EXEMPT">Exempt</option></select></label>
        </div></details>
      </form>
      <ProblemMessage error={searchError} />
      {results && <div className="stack" aria-live="polite">
        <div className="section-heading"><strong>{results.length ? `Page ${page} · ${results.length} result${results.length === 1 ? "" : "s"}` : "No matching demo establishments"}</strong><span className="muted small">Synthetic records only</span></div>
        <ul className="result-cards">{results.map((row) => <li key={row.establishment_id}>
          <div><span className="eyebrow">{row.establishment_id}</span><h3><button type="button" className="lookup-link" onClick={() => void openProfile(row.establishment_id)}>{row.legal_name} ↗</button></h3>
            <p className="muted small">Registration {row.registration_number} · {row.city || "City unavailable"}, {row.district || "District unavailable"} · {row.pincode || "Pincode unavailable"}</p>
            <p className="muted small">{row.establishment_type ? label(row.establishment_type) : "Type unavailable"} · {row.industry_group ? label(row.industry_group) : "Industry unavailable"} · {row.office_id}</p></div>
          <span className="state-pill">{label(row.status)}</span>
        </li>)}</ul>
        <div className="actions"><button type="button" disabled={searchBusy || page <= 1} onClick={() => void search(page - 1)}>Previous</button><button type="button" disabled={searchBusy || results.length < 20 || page >= 5} onClick={() => void search(page + 1)}>Next</button></div>
      </div>}
      {profile && <div className="profile-card" aria-live="polite"><p className="eyebrow">Public profile · synthetic record</p><h3>{profile.legal_name}</h3>
        <dl className="profile-grid"><div><dt>EPF code</dt><dd>{profile.establishment_id}</dd></div><div><dt>Registration number</dt><dd>{profile.registration_number}</dd></div>
          <div><dt>Office</dt><dd>{profile.office_id}</dd></div><div><dt>City and district</dt><dd>{profile.city || "Unavailable"}, {profile.district || "Unavailable"}</dd></div>
          <div><dt>Pincode</dt><dd>{profile.pincode || "Unavailable"}</dd></div><div><dt>Establishment type</dt><dd>{profile.establishment_type ? label(profile.establishment_type) : "Not recorded"}</dd></div>
          <div><dt>Industry group</dt><dd>{profile.industry_group ? label(profile.industry_group) : "Not recorded"}</dd></div><div><dt>Coverage date</dt><dd>{dateOnly(profile.coverage_date)}</dd></div>
          <div><dt>Coverage status</dt><dd>{label(profile.coverage_status)}</dd></div><div><dt>Verified on</dt><dd>{dateTime(profile.verified_at)}</dd></div>
          <div><dt>Exemption</dt><dd>{profile.exemption_status === "NOT_MODELLED" || !profile.exemption_status ? "Not modelled in this demo" : label(profile.exemption_status)}</dd></div></dl>
      </div>}
    </section>

    <section className="card stack" aria-labelledby="trrn-lookup">
      <div className="section-heading"><div><p className="eyebrow">02 / Payment reference</p><h2 id="trrn-lookup">TRRN status</h2></div><span className="badge badge-mock">Mock</span></div>
      <p className="muted">Check a synthetic challan reference. The result shows payment state, wage month and recorded dates without employer or member details.</p>
      <p className="demo-tip">Demo reference: <code>TRRN0000000000000</code> · A due challan</p>
      <form className="stack" onSubmit={(event) => void lookup(event)}>
        <label>TRRN<input value={trrn} onChange={(event) => setTrrn(event.target.value.toUpperCase())} placeholder="TRRN0000000000000" pattern="TRRN[0-9]{13}" required /></label>
        <div className="challenge-row"><button type="button" onClick={() => void loadChallenge()}>Get one-use demo question</button>
          {challenge && <label>{challenge.prompt}<input inputMode="numeric" value={answer} onChange={(event) => setAnswer(event.target.value)} required /></label>}</div>
        <p className="muted small">This arithmetic question demonstrates a one-use gate. It is not a production CAPTCHA.</p>
        <button className="primary" disabled={!challenge || trrnBusy}>{trrnBusy ? "Checking…" : "Check TRRN"}</button>
      </form>
      <ProblemMessage error={trrnError} />
      {trrnResult && <div className="profile-card" aria-live="polite"><p className="eyebrow">Synthetic challan status</p><div className="section-heading"><h3>{trrnResult.trrn}</h3><span className="state-pill">{label(trrnResult.status)}</span></div>
        <dl className="profile-grid"><div><dt>Wage month</dt><dd>{trrnResult.wage_month || "Not found"}</dd></div><div><dt>Issued</dt><dd>{dateTime(trrnResult.issued_at)}</dd></div>
          <div><dt>Payment recorded</dt><dd>{dateTime(trrnResult.paid_at)}</dd></div><div><dt>Next step</dt><dd>{trrnResult.next_step}</dd></div></dl>
      </div>}
    </section>
    <section className="card stack" aria-labelledby="defaulters-public-heading"><h2 id="defaulters-public-heading">Defaulting establishments (synthetic)</h2>
      <ProblemMessage error={defaulters.error} />
      {defaulters.isLoading ? <p role="status">Loading defaulting establishments…</p> : null}
      {defaulters.data ? <><p className="muted">{label(defaulters.data.data.label)} · {defaulters.data.data.note}</p>
        <p className="muted">Showing up to the 6 latest wage months per default.</p></> : null}
      {defaulters.data?.data.establishments.length ? <ul>{defaulters.data.data.establishments.map((item) =>
        <li key={item.establishment_id}><h3>{item.legal_name ?? item.establishment_id}</h3>
          <p>{item.establishment_id} · Office {item.office_id} · Since {item.since}</p>
          <ul>{item.defaults.map((entry, index) => <li key={`${entry.kind}-${index}`}>
            {entry.kind === "NON_FILING" ? "Returns not filed" : entry.kind === "NON_PAYMENT" ? "Dues not paid" : label(entry.kind)}
            {" · "}{entry.wage_months.length} months in total
            {entry.wage_months.length ? <ul>{[...entry.wage_months].sort((a, b) => b.localeCompare(a)).slice(0, 6)
              .map((month) => <li key={month}>{month}</li>)}</ul> : null}
          </li>)}</ul>
        </li>)}</ul> : defaulters.data ? <p className="muted">No defaulting establishments published.</p> : null}
    </section>
    <PensionEnquiries />
  </div>;
}
