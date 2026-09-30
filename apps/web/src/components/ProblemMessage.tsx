import { ApiError } from "../api/client";

export function ProblemMessage({ error }: { error: unknown }) {
  if (!error) return null;
  const p = error instanceof ApiError ? error.problem : { title: String(error), status: 0 };
  return (
    <div role="alert" className="problem">
      <strong>{p.title}</strong>
      {"detail" in p && p.detail ? <div>{p.detail}</div> : null}
      {"errors" in p && p.errors?.length ? <ul>{p.errors.map((item, index) => <li key={index}>
        {typeof item === "string" ? item : `${item.field ?? item.loc?.join(".") ?? ""}${item.field || item.loc?.length ? ": " : ""}${item.message ?? item.msg ?? "Invalid value"}`}
      </li>)}</ul> : null}
      {"correlation_id" in p && p.correlation_id ? <div className="muted">Correlation ID: <code>{p.correlation_id}</code></div> : null}
    </div>
  );
}
