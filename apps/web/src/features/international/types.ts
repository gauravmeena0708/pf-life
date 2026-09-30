export interface Agreement {
  country: string; code: string; in_force_from: string; max_posting_months: number;
  max_extension_months: number; totalisation: boolean; note: string;
}
export interface Agreements { agreements: Agreement[]; note: string }
export interface CocApplication {
  application_id: string; kind: string; parent_id: string | null; uan: string; account_link_id: string;
  establishment_id: string; legal_name: string | null; country: string; host_employer: string;
  posting_from: string; posting_to: string; state: "AWAITING_SIGNED_UPLOAD" | "SUBMITTED" | "ISSUED" | "REJECTED";
  signed_upload: { filename: string; uploaded_at: string } | null; certificate_no: string | null;
  decision_reason: string | null; created_at: string; decided_at: string | null;
}
export interface Certificate {
  certificate_no: string; name: string; uan: string; country: string; host_employer: string;
  posting_from: string; posting_to: string; issued_at: string; issued_by_office: string; verification_code: string; text: string;
}
