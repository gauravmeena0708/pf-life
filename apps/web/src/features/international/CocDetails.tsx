import { statusLabel } from "../statusLabel";
import { useTranslation } from "react-i18next";
import type { CocApplication } from "./types";

export function CocDetails({ application }: { application: CocApplication }) {
  const { t } = useTranslation();
  return <dl className="kv"><dt>UAN</dt><dd>{application.uan}</dd><dt>Member ID</dt><dd>{application.account_link_id}</dd>
    <dt>Establishment</dt><dd>{application.legal_name ?? application.establishment_id}</dd>
    <dt>Country</dt><dd>{application.country}</dd><dt>Host employer</dt><dd>{application.host_employer}</dd>
    <dt>Posting</dt><dd>{application.posting_from} to {application.posting_to}</dd>
    <dt>Kind</dt><dd>{application.kind.replaceAll("_", " ")}</dd><dt>Parent application</dt><dd>{application.parent_id ?? "—"}</dd>
    <dt>State</dt><dd>{statusLabel(application.state, t)}</dd>
    <dt>Signed upload</dt><dd>{application.signed_upload?.filename ?? "—"}</dd>
    <dt>Certificate</dt><dd>{application.certificate_no ?? "—"}</dd><dt>Decision reason</dt><dd>{application.decision_reason ?? "—"}</dd>
    <dt>Created</dt><dd>{application.created_at}</dd><dt>Decided</dt><dd>{application.decided_at ?? "—"}</dd>
  </dl>;
}
