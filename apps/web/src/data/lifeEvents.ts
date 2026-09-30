export interface LifeEvent { id: string; title: string; description: string; actions: { label: string; to: string }[] }

export const lifeEvents: LifeEvent[] = [
  { id: "changed-jobs", title: "I changed jobs", description: "Bring your earlier PF balance into your current member account.", actions: [
    { label: "Transfer my PF", to: "/member/service#transfer-heading" }, { label: "Check auto-transfer", to: "/member/service#auto-transfer-heading" },
    { label: "Know your UAN", to: "/member/nomination#uan-lookup-heading" }] },
  { id: "need-money", title: "I need money for illness, a house, education or a wedding", description: "Check the advances available to you and their conditions.", actions: [
    { label: "See advances", to: "/member/claims" }] },
  { id: "leaving-work", title: "I am leaving work", description: "Record your exit and review the claims available after leaving.", actions: [
    { label: "Mark exit", to: "/member/service#exit-heading" }, { label: "Final settlement", to: "/member/claims" }] },
  { id: "retiring", title: "I am retiring or want my pension", description: "Estimate your pension and explore pension applications.", actions: [
    { label: "Pension estimate", to: "/member/profile#pension-estimate-heading" }, { label: "Form 10D", to: "/member/pension" },
    { label: "Higher pension", to: "/member/higher-pension#higher-pension-heading" }] },
  { id: "family-death", title: "Someone in my family has died", description: "The nominee or family files the death claims — Forms 20, 10D and 5IF (EDLI) — at the regional office or through the claimant login.", actions: [
    { label: "Public services", to: "/public" }] },
  { id: "wrong-record", title: "Something in my record is wrong", description: "Request a correction or raise a grievance.", actions: [
    { label: "Joint Declaration", to: "/member/profile#correction-heading" }, { label: "Raise a grievance", to: "/member/grievances" }] },
];
