import { ApiError } from "../api/client";

export function ProblemMessage({ error }: { error: unknown }) {
  if (!error) return null;
  const p = error instanceof ApiError ? error.problem : { title: String(error), status: 0 };
  return (
    <div role="alert" className="problem">
      <strong>{p.title}</strong>
      {"detail" in p && p.detail ? <div>{p.detail}</div> : null}
      {"correlation_id" in p && p.correlation_id ? <div className="muted">Correlation ID: <code>{p.correlation_id}</code></div> : null}
    </div>
  );
}
