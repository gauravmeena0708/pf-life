import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { api, command, Envelope } from "../api/client";
import { ProblemMessage } from "../components/ProblemMessage";

type Establishment = { establishment_id: string; legal_name: string; office_id: string; pincode?: string; status: string };
type Profile = { establishment_id: string; legal_name: string; office_id: string; pincode?: string; coverage_status: string; exemption_status: string };
type Challenge = { challenge_id: string; prompt: string; proof_type: string };
type TrrnStatus = { trrn: string; status: string; label: string };

export function PublicLookups() {
  const [query, setQuery] = useState("");
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
      const response = await api<Envelope<Establishment[]>>(`/api/v1/public/establishments?query=${encodeURIComponent(query.trim())}&page=${nextPage}`);
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

  return <div className="stack public-lookups">
    <p><Link to="/">← All interfaces</Link></p>
    <header className="workspace-head"><div><p className="eyebrow">Public · synthetic POC</p><h1>Public lookups</h1><p className="muted">Search the demo establishment directory and check a synthetic challan reference.</p></div></header>
    <section className="card stack" aria-labelledby="establishment-search"><h2 id="establishment-search">Establishment search</h2>
      <p className="muted">Search by name, registration number, establishment code or six digit pincode. Up to 20 results per page.</p>
      <form className="actions" onSubmit={(event) => { event.preventDefault(); void search(1); }}>
        <label>Search term<input value={query} onChange={(event) => setQuery(event.target.value)} minLength={3} maxLength={60} required /></label>
        <button className="primary" disabled={searchBusy}>Search</button>
      </form>
      <ProblemMessage error={searchError} />
      {results && <><p aria-live="polite">{results.length ? `Page ${page} · ${results.length} result${results.length === 1 ? "" : "s"}` : "No matching demo establishments."}</p>
        <ul className="lookup-results">{results.map((row) => <li key={row.establishment_id}><button type="button" className="lookup-link" onClick={() => void openProfile(row.establishment_id)}>{row.legal_name}</button><span>{row.establishment_id} · {row.office_id} · {row.pincode || "Pincode unavailable"}</span></li>)}</ul>
        <div className="actions"><button type="button" disabled={searchBusy || page <= 1} onClick={() => void search(page - 1)}>Previous</button><button type="button" disabled={searchBusy || results.length < 20 || page >= 5} onClick={() => void search(page + 1)}>Next</button></div></>}
      {profile && <div className="filing-detail" aria-live="polite"><h3>{profile.legal_name}</h3><dl className="kv"><dt>Code</dt><dd>{profile.establishment_id}</dd><dt>Office</dt><dd>{profile.office_id}</dd><dt>Pincode</dt><dd>{profile.pincode || "Unavailable"}</dd><dt>Coverage</dt><dd>{profile.coverage_status}</dd><dt>Exemption</dt><dd>{profile.exemption_status}</dd></dl></div>}
    </section>
    <section className="card stack" aria-labelledby="trrn-lookup"><h2 id="trrn-lookup">TRRN status</h2>
      <p className="muted">This lookup reads synthetic challans only. Try <code>TRRN0000000000000</code> for the seeded due challan. The arithmetic question is a one-use demo proof, not a production CAPTCHA.</p>
      <form className="stack" onSubmit={(event) => void lookup(event)}>
        <label>TRRN<input value={trrn} onChange={(event) => setTrrn(event.target.value)} placeholder="TRRN0000000000001" pattern="TRRN[0-9]{13}" required /></label>
        <div className="actions"><button type="button" onClick={() => void loadChallenge()}>Get demo question</button>{challenge && <label>{challenge.prompt}<input inputMode="numeric" value={answer} onChange={(event) => setAnswer(event.target.value)} required /></label>}</div>
        <button className="primary" disabled={!challenge || trrnBusy}>Check status</button>
      </form>
      <ProblemMessage error={trrnError} />
      {trrnResult && <p className="ok" aria-live="polite">{trrnResult.trrn}: <strong>{trrnResult.status.replaceAll("_", " ")}</strong> · Synthetic demo record</p>}
    </section>
  </div>;
}
