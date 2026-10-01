import { useState, type FormEvent } from "react";

import { api, command, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";

type Challenge = { challenge_id: string; prompt: string };
type Match = { search_ref: string; member_id_masked: string; establishment_name: string; last_credit_year: number | null };
type SearchResult = { matches: Match[]; otp_sent_to: string; demo: { otp: string | null; otp_by_search_ref: Record<string, string>; note: string } };
type BalanceResult = { member_id_masked: string; balance_paise: number; next_step: string };

export function InoperativeSearchPage() {
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [answer, setAnswer] = useState("");
  const [matches, setMatches] = useState<SearchResult | null>(null);
  const [selected, setSelected] = useState("");
  const [balance, setBalance] = useState<BalanceResult | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function getChallenge() {
    setError(null); setChallenge(null); setAnswer("");
    try { setChallenge((await api<Envelope<Challenge>>("/api/v1/public/demo-challenges")).data); }
    catch (cause) { setError(cause); }
  }
  async function send(body: Record<string, unknown>) {
    if (!challenge || !/^-?\d+$/.test(answer.trim()) || !Number.isSafeInteger(Number(answer))) {
      setError(new Error("Get a demo question and enter an integer answer.")); return null;
    }
    setBusy(true); setError(null);
    try { return (await command<Envelope<SearchResult | BalanceResult>>("POST", "/api/v1/public/inoperative-accounts/searches",
      { ...body, challenge_id: challenge.challenge_id, answer: Number(answer) })).data; }
    catch (cause) { setError(cause); return null; }
    finally { setBusy(false); setChallenge(null); setAnswer(""); }
  }
  async function search(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setMatches(null); setSelected(""); setBalance(null);
    const f = new FormData(e.currentTarget);
    const response = await send({ name: String(f.get("name") ?? "").trim(), date_of_birth: String(f.get("date_of_birth")),
      establishment_query: String(f.get("establishment_query") ?? "").trim() });
    if (response && "matches" in response) setMatches(response);
  }
  async function verify(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setBalance(null);
    const otp = String(new FormData(e.currentTarget).get("otp") ?? "").trim();
    const response = await send({ search_ref: selected, otp });
    if (response && "balance_paise" in response) setBalance(response);
  }
  const challengeField = <div className="challenge-row"><button type="button" onClick={() => void getChallenge()} disabled={busy}>Get one-use demo question</button>
    {challenge ? <label>{challenge.prompt}<input required inputMode="numeric" pattern="-?[0-9]+" value={answer} onChange={(e) => setAnswer(e.target.value)} /></label> : null}</div>;
  return <main className="stack" aria-labelledby="inoperative-public-heading">
    <PageHeader id="inoperative-public-heading" eyebrow="Public service" title="Inoperative account search" current="Inoperative account search"
      description="Find a possible member ID, then verify the demonstration OTP to view its balance." />
    {!matches ? <form className="card stack" aria-label="Search for an inoperative account" onSubmit={(e) => void search(e)}>
      <h2>1. Find matching accounts</h2><div className="form-row"><label>Name<input name="name" required /></label>
        <label>Date of birth<input name="date_of_birth" type="date" required /></label>
        <label>Establishment name<input name="establishment_query" required /></label></div>
      {challengeField}<p className="muted small">The arithmetic question is a one-use demo check. Get a new question after each submission.</p>
      <div className="actions"><button type="submit" className="primary" disabled={!challenge || busy}>Search</button></div>
    </form> : <div className="actions"><button type="button" onClick={() => { setMatches(null); setBalance(null); setSelected(""); setChallenge(null); setAnswer(""); }}>Start a new search</button></div>}
    <ProblemMessage error={error} />
    {matches ? <section className="card stack" aria-labelledby="matches-heading"><h2 id="matches-heading">2. Verify a match</h2>
      {matches.matches.length ? <><p role="status">OTP sent to {matches.otp_sent_to}. <span className="muted small">Demo OTP: {matches.demo.otp_by_search_ref[selected] ?? matches.demo.otp}</span></p>
        <form className="stack" aria-label="Verify selected account" onSubmit={(e) => void verify(e)}>
          <fieldset><legend>Choose a matching member ID</legend>{matches.matches.map((match) => <label key={match.search_ref} className="lookup-result">
            <input type="radio" name="match" required checked={selected === match.search_ref} onChange={() => { setSelected(match.search_ref); setBalance(null); }} />
            {match.member_id_masked} · {match.establishment_name} · Last credit year: {match.last_credit_year ?? "—"}</label>)}</fieldset>
          <label>OTP<input name="otp" required inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code" /></label>
          {challengeField}<div className="actions"><button type="submit" className="primary" disabled={!selected || !challenge || busy}>Verify and view balance</button></div>
        </form></> : <p>No matching inoperative account was found.</p>}
    </section> : null}
    {balance ? <section className="card stack" aria-label="Verified account balance" role="status"><h2>Verified account</h2>
      <p>Member ID: {balance.member_id_masked}</p><p><strong>Balance: {rupees(balance.balance_paise)}</strong></p><p>{balance.next_step}</p></section> : null}
  </main>;
}
