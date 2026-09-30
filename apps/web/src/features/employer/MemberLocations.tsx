import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";

interface MemberLocation { branch_code: string; district: string; pincode: string }
interface Member { uan: string; name: string; account_link_id: string; status: string; location: MemberLocation | null }
export function MemberLocations({ canMap }: { canMap: boolean }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false); const [error, setError] = useState<unknown>(null); const [notice, setNotice] = useState<string | null>(null);
  const members = useQuery({ queryKey: ["employer-members"], retry: false,
    queryFn: () => api<Envelope<Member[]>>("/api/v1/employers/me/members") });
  async function map(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (!canMap || busy) return;
    const form = e.currentTarget; const f = new FormData(form); const text = (name: string) => String(f.get(name) ?? "").trim();
    setBusy(true); setError(null); setNotice(null);
    try {
      const uan = text("uan"); const account_link_id = text("account_link_id"); const branch_code = text("branch_code"); const district = text("district"); const pincode = text("pincode");
      if (!/^[0-9]{12}$/.test(uan) || !account_link_id || !/^[A-Z0-9-]+$/.test(branch_code) || !district || !/^[0-9]{6}$/.test(pincode))
        throw new Error("Enter a 12-digit UAN, member ID, branch code using A–Z, 0–9 or hyphens, district and 6-digit pincode.");
      const result = await command<Envelope<{ uan: string; account_link_id: string; location: MemberLocation }>>("POST", `/api/v1/employers/me/members/${encodeURIComponent(uan)}/location-mappings`, { account_link_id, branch_code, district, pincode });
      setNotice(`Location recorded for ${result.data.uan}: ${result.data.location.branch_code}, ${result.data.location.district}, ${result.data.location.pincode}.`);
      form.reset(); await qc.invalidateQueries({ queryKey: ["employer-members"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  return <section className="card stack" aria-labelledby="location-heading"><h2 id="location-heading">Member Location Mapping</h2>
    <ProblemMessage error={error ?? members.error} />{notice ? <p role="status" className="ok">{notice}</p> : null}
    {canMap ? <form className="stack" aria-label="Map member location" onSubmit={(e) => void map(e)}>
      <fieldset className="stack" disabled={busy}><legend>Member location</legend>
        <label>UAN<input name="uan" required pattern="[0-9]{12}" inputMode="numeric" /></label>
        <label>Member ID at this establishment<input name="account_link_id" required /></label>
        <label>Branch code<input name="branch_code" required pattern="[A-Z0-9-]+" /></label>
        <label>District<input name="district" required /></label>
        <label>Pincode<input name="pincode" required pattern="[0-9]{6}" inputMode="numeric" /></label>
        <div className="actions"><button type="submit" className="primary">Save location</button></div>
      </fieldset>
    </form> : null}
    {members.isLoading ? <p role="status">Loading members…</p> : null}
    {members.data ? <div className="table-scroll"><table><thead><tr><th scope="col">UAN</th><th scope="col">Name</th><th scope="col">Member ID</th><th scope="col">Status</th><th scope="col">Location</th></tr></thead>
      <tbody>{members.data.data.map((member) => <tr key={member.account_link_id}><th scope="row">{member.uan}</th><td>{member.name}</td><td>{member.account_link_id}</td><td>{member.status}</td>
        <td>{member.location ? `${member.location.branch_code} · ${member.location.district} · ${member.location.pincode}` : "Not mapped"}</td></tr>)}</tbody>
    </table></div> : null}
    {members.data && !members.data.data.length ? <p className="muted">No members at this establishment.</p> : null}
  </section>;
}
