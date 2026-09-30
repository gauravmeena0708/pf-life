import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { command, getSession, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { CIRCULAR_CATEGORIES, CircularsList, type Circular } from "../public/CircularsList";

export function CircularsPage() {
  const qc = useQueryClient();
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const publisher = session.data?.stakeholder === "ho.publicity";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function publish(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!publisher || busy) return;
    const f = new FormData(e.currentTarget);
    const body = Object.fromEntries(["number", "title", "category", "issued_on", "summary", "body"].map((key) => [key, String(f.get(key) ?? "").trim()]));
    setBusy(true); setError(null); setNotice(null);
    try {
      if (body.number.length < 3 || body.title.length < 5 || body.summary.length < 10 || body.body.length < 20
        || !body.issued_on || !CIRCULAR_CATEGORIES.includes(body.category)) throw new Error("Complete the circular details before publishing.");
      const response = await command<Envelope<Circular>>("POST", "/api/v1/ho/circulars", body);
      setNotice(`Published circular ${response.data.number}, version ${response.data.version}.`);
      await qc.invalidateQueries({ queryKey: ["public-circulars"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }

  return <section className="stack" aria-labelledby="publish-circular-heading">
    <PageHeader id="publish-circular-heading" eyebrow="HO Public Relations" title="Publish a circular"
      description="Publish a demonstration circular. Reusing its number creates a new version; earlier versions remain readable." current="Circulars" />
    <ProblemMessage error={error ?? session.error} />
    {notice ? <p role="status" className="ok">{notice}</p> : null}
    {session.isLoading ? <p role="status">Loading role…</p> : null}
    {session.data && !publisher ? <p className="pending-notice">Publishing is available to HO Public Relations.</p> : null}
    {publisher ? <>
      <form className="card stack" aria-label="Publish a circular" onSubmit={(e) => void publish(e)}>
        <fieldset className="stack" disabled={busy}><legend>Circular details</legend>
          <div className="form-row">
            <label>Number<input name="number" required minLength={3} maxLength={60} /></label>
            <label>Category<select name="category" required>{CIRCULAR_CATEGORIES.map((category) => <option key={category} value={category}>{category.replaceAll("_", " ").toLowerCase()}</option>)}</select></label>
            <label>Issued on<input name="issued_on" type="date" required /></label>
          </div>
          <label>Title<input name="title" required minLength={5} maxLength={200} /></label>
          <label>Summary<textarea name="summary" required minLength={10} maxLength={1000} /></label>
          <label>Body<textarea name="body" required minLength={20} maxLength={20000} rows={10} /></label>
          <div className="actions"><button type="submit" className="primary">Publish circular</button></div>
        </fieldset>
      </form>
      <CircularsList />
    </> : null}
  </section>;
}
