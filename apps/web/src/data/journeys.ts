export interface GuidedJourney {
  id: string;
  title: string;
  description: string;
  personas: string[];
  publicForm?: string;
}

export const JOURNEYS: GuidedJourney[] = [
  { id: "claim", title: "A member's claim through the office", description: "File a claim, follow the officer's checks and approval, and see it paid.", personas: ["member-a", "do-caseworker", "ro-ao", "ro-cashier"] },
  { id: "return", title: "An employer's monthly return and payment", description: "Prepare and validate an ECR, then approve, submit and pay through the simulated bank.", personas: ["emp-preparer", "emp-signatory"] },
  { id: "pension", title: "A pension from Form 10D to the PPO", description: "Follow a retired member's application through the pension desks to the signed PPO.", personas: ["member-e", "ro-da-pension", "ro-ss-pension", "ro-pension"] },
  { id: "death", title: "A death claim and the EDLI benefit", description: "File as a nominee, review the death claim and record the EDLI benefit decision.", personas: ["claimant-a", "do-caseworker", "ro-ao", "ro-edli"] },
  { id: "transfer", title: "Changing jobs: auto-transfer and the primary member ID", description: "Confirm an auto-transfer and explore why previous service must reach the primary member ID.", personas: ["member-g", "member-d"] },
  { id: "compliance", title: "Compliance: defaulters, demands and VISHWAS", description: "Review defaulting establishments, settle demands and follow the VISHWAS case.", personas: ["ro-da-compliance", "emp-signatory", "ro-apfc"] },
  { id: "grievance", title: "A grievance, with or without a login", description: "File and track a grievance, then follow the office's reply; a public form is also available.", personas: ["member-a", "ro-pro"], publicForm: "/public/grievances#public-grievance-heading" },
  { id: "oversight", title: "Oversight: concurrent audit and the Issue Tracker", description: "Raise an audit alert, reply from the regional office and execute an approved Issue Tracker request.", personas: ["zo-audit", "ro-oic", "ndc-is"] },
];
