export interface OfficeCase {
  case_id: string;
  claim_id: string | null;
  grievance_id: string | null;
  advisory_signal_id: string | null;
  process: string | null;
  subject_ref: string | null;
  data?: Record<string, unknown>;
  kind: string;
  office_id: string;
  form_type: string;
  account_link_id: string;
  amount_paise: number;
  rule_version: string;
  chain: string[];
  step: number;
  round: number;
  state: string;
  current_role: string | null;
  assignee_subject: string | null;
  version: number;
  sla_due_at: string | null;
  next_action: "recommend" | "decide" | "second-approve" | "instruct-payment" | "reissue" | "handle-grievance" | string | null;
}
export interface CaseDetail extends OfficeCase {
  history: { at: string; round: number; officer_role: string; officer_subject: string; action: string; approval_level: string | null; reason: string | null; checks: string[] | null }[];
  your_turn: boolean;
  documents?: import("./SignedDocuments").CaseDocument[];
  docket_ready?: boolean;
  operation: import("./ProcessForm").ProcessOperation | null;
}
