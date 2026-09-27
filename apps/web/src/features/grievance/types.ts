export interface GrievanceEntry {
  at: string | null;
  kind: "MESSAGE" | "STATUS" | "EVIDENCE" | "DOCUMENT";
  by: string;
  state: string | null;
  body: string;
  evidence_refs: string[] | null;
}

export interface Grievance {
  grievance_id: string;
  category: string;
  subject: string;
  description: string;
  linked_claim_id: string | null;
  office_id: string;
  tier: "RO" | "ZO" | "HO";
  state: string;
  version: number;
  sla_due_at: string | null;
  resolution: string | null;
  resolved_at: string | null;
  entries: GrievanceEntry[];
  documents: { document_id: string; filename: string; content_type: string; size_bytes: number; sha256: string; uploaded_at: string | null }[];
}

export interface GrievanceRow {
  grievance_id: string;
  category: string;
  subject: string;
  state: string;
  tier: string;
  linked_claim_id: string | null;
  sla_due_at: string | null;
  created_at: string | null;
}

export const CATEGORIES = ["CLAIM_DELAY", "CLAIM_REJECTION", "PASSBOOK", "KYC", "EMPLOYER", "OTHER"] as const;
export const OPEN_STATES = ["REGISTERED", "ROUTED", "IN_PROGRESS", "ESCALATED", "REOPEN_REQUESTED"];
