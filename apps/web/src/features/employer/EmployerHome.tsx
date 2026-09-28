import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api, command, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { JointDeclarations } from "./JointDeclarations";
import { useStepUp } from "../stepup/useStepUp";

interface Establishment {
  establishment_id: string;
  legal_name: string;
  registration_number: string;
  office_id: string;
  status: string;
  verified_at: string | null;
  registration_request_id: string | null;
  your_permissions: string[];
}

interface Grant {
  grant_id: string;
  username: string;
  kind: string;
  grants: string[];
  status: string;
  created_at: string | null;
  revoked_at: string | null;
}

const OPERATOR_GRANTS = ["ecr.prepare"];
const SIGNATORY_GRANTS = ["ecr.approve", "ecr.submit", "payment.initiate"];

export function EmployerHome() {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const est = useQuery({ queryKey: ["employer-me"], queryFn: () => api<Envelope<Establishment>>("/api/v1/employers/me"), retry: false });
  const perms = est.data?.data.your_permissions ?? [];
  const canManageOperators = perms.includes("operators.manage");
  const canManageSignatories = perms.includes("signatories.manage");
  const operators = useQuery({
    queryKey: ["operators"], enabled: canManageOperators,
    queryFn: () => api<Envelope<Grant[]>>("/api/v1/employers/me/operators"),
  });
  const signatories = useQuery({
    queryKey: ["signatories"], enabled: canManageSignatories,
    queryFn: () => api<Envelope<Grant[]>>("/api/v1/employers/me/signatories"),
  });

  async function run(fn: () => Promise<unknown>, ok: string) {
    setError(null);
    setNotice(null);
    try {
      await fn();
      setNotice(ok);
      await qc.invalidateQueries();
    } catch (e) {
      setError(e);
    }
  }

  async function verify(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const reqId = est.data?.data.registration_request_id;
    if (!reqId) {
      setError(new Error("This establishment has no registration request to verify."));
      return;
    }
    await run(async () => {
      const r = await command<Envelope<{ state: string; result_reason: string; fix: string | null }>>(
        "POST", `/api/v1/employers/registration-requests/${reqId}/verification-evidence`,
        { pan: String(f.get("pan")).toUpperCase(), gstin: String(f.get("gstin") || "").toUpperCase() || null });
      if (r.data.state !== "VERIFIED") throw new Error(`${r.data.result_reason} ${r.data.fix ?? ""}`);
    }, "Establishment verified (mock registry).");
  }

  async function grant(kind: "OPERATOR" | "SIGNATORY", username: string) {
    const e = est.data!.data;
    const isOperator = kind === "OPERATOR";
    const grants = isOperator ? OPERATOR_GRANTS : SIGNATORY_GRANTS;
    const token = await stepUp.ask({
      action: isOperator ? "invite-operator" : "authorise-signatory",
      resourceId: e.establishment_id,
      summary: `${isOperator ? "Add payroll operator" : "Authorise signatory"} ${username} with: ${grants.join(", ")}`,
    });
    if (!token) return;
    await run(() => command("POST", isOperator ? "/api/v1/employers/me/operators/invitations" : "/api/v1/employers/me/signatories/authorisations",
      { username, grants }, { stepUpToken: token }), `${username} now has: ${grants.join(", ")}.`);
  }

  async function revoke(g: Grant) {
    const isOperator = g.kind === "OPERATOR";
    const token = await stepUp.ask({
      action: isOperator ? "revoke-operator" : "revoke-signatory",
      resourceId: g.grant_id,
      summary: `Revoke all permissions of ${g.username} at this establishment, effective immediately`,
    });
    if (!token) return;
    await run(() => command("POST", `/api/v1/employers/me/${isOperator ? "operators" : "signatories"}/${g.grant_id}/revocations`,
      { reason: "Revoked from the employer workspace" }, { stepUpToken: token }),
      `${g.username} was revoked. Their next request is denied, even in an open browser session.`);
  }

  if (est.isLoading || est.error) return <div className="stack">
    <PageHeader eyebrow="Employer services · workspace" title="Employer workspace"
      description="Manage your synthetic establishment and role permissions." current="Employer workspace" />
    {est.isLoading ? <p role="status">Loading…</p> : <ProblemMessage error={est.error} />}
  </div>;
  const e = est.data!.data;
  return (
    <section aria-labelledby="emp-heading" className="stack">
      <PageHeader id="emp-heading" eyebrow="Employer services · workspace" title={e.legal_name}
        description={`${e.establishment_id} · ${e.registration_number} · office ${e.office_id} · status ${e.status}`}
        current="Employer workspace" />
      <p>Your permissions: {perms.length ? perms.map((p) => <code key={p}>{p} </code>) : "none"}</p>
      {notice ? <p role="status" className="ok">{notice}</p> : null}
      <ProblemMessage error={error} />

      {e.status !== "VERIFIED" && perms.includes("establishment.manage") ? (
        <form onSubmit={verify} className="card">
          <h2>Verify the establishment</h2>
          <p className="muted">Checked against a MOCK registry. Synthetic record PAN: <code>AAAPD0000D</code>, GSTIN <code>07AAAPD0000D1Z5</code>.</p>
          <label htmlFor="pan">PAN</label>
          <input id="pan" name="pan" required pattern="[A-Za-z]{5}[0-9]{4}[A-Za-z]" />
          <label htmlFor="gstin">GSTIN (optional)</label>
          <input id="gstin" name="gstin" />
          <button type="submit" className="primary">Submit evidence</button>
        </form>
      ) : null}

      {perms.some((p) => p.startsWith("ecr.") || p === "payment.initiate") ? (
        <p><Link to="/employer/ecr" className="button primary">Open monthly returns (ECR)</Link></p>
      ) : null}

      {(["OPERATOR", "SIGNATORY"] as const).map((kind) => {
        const canManage = kind === "OPERATOR" ? canManageOperators : canManageSignatories;
        if (!canManage) return null;
        const list = (kind === "OPERATOR" ? operators : signatories).data?.data ?? [];
        const listError = (kind === "OPERATOR" ? operators : signatories).error;
        return (
          <div key={kind} className="card">
            <h2>{kind === "OPERATOR" ? "Payroll operators (prepare returns)" : "Authorised signatories (approve, submit, pay)"}</h2>
            <ProblemMessage error={listError} />
            <table>
              <thead><tr><th>User</th><th>Permissions</th><th>Status</th><th /></tr></thead>
              <tbody>
                {list.map((g) => (
                  <tr key={g.grant_id}>
                    <td>{g.username}</td>
                    <td>{g.grants.join(", ")}</td>
                    <td>{g.status}</td>
                    <td>{canManage && g.status === "ACTIVE" ? <button type="button" onClick={() => revoke(g)}>Revoke</button> : null}</td>
                  </tr>
                ))}
                {list.length === 0 ? <tr><td colSpan={4} className="muted">None yet.</td></tr> : null}
              </tbody>
            </table>
            {canManage ? (
              <button type="button" onClick={() => grant(kind, kind === "OPERATOR" ? "emp-preparer" : "emp-signatory")}>
                {kind === "OPERATOR" ? "Add demo operator (emp-preparer)" : "Authorise demo signatory (emp-signatory)"}
              </button>
            ) : null}
          </div>
        );
      })}
      {perms.includes("ecr.approve") ? <JointDeclarations /> : null}
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}
