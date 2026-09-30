export interface LifeEvent { id: string; titleKey: string; descriptionKey: string; actions: { labelKey: string; to: string }[] }

export const lifeEvents: LifeEvent[] = [
  { id: "changed-jobs", titleKey: "memberHome.events.changedJobs.title", descriptionKey: "memberHome.events.changedJobs.description", actions: [
    { labelKey: "memberHome.events.changedJobs.transfer", to: "/member/service#transfer-heading" }, { labelKey: "memberHome.events.changedJobs.autoTransfer", to: "/member/service#auto-transfer-heading" },
    { labelKey: "memberHome.events.changedJobs.uan", to: "/member/nomination#uan-lookup-heading" }] },
  { id: "need-money", titleKey: "memberHome.events.needMoney.title", descriptionKey: "memberHome.events.needMoney.description", actions: [
    { labelKey: "memberHome.events.needMoney.advances", to: "/member/claims" }] },
  { id: "leaving-work", titleKey: "memberHome.events.leavingWork.title", descriptionKey: "memberHome.events.leavingWork.description", actions: [
    { labelKey: "memberHome.events.leavingWork.exit", to: "/member/service#exit-heading" }, { labelKey: "memberHome.events.leavingWork.settlement", to: "/member/claims" }] },
  { id: "retiring", titleKey: "memberHome.events.retiring.title", descriptionKey: "memberHome.events.retiring.description", actions: [
    { labelKey: "memberHome.events.retiring.estimate", to: "/member/profile#pension-estimate-heading" }, { labelKey: "memberHome.events.retiring.form10d", to: "/member/pension" },
    { labelKey: "memberHome.events.retiring.higher", to: "/member/higher-pension#higher-pension-heading" }] },
  { id: "family-death", titleKey: "memberHome.events.familyDeath.title", descriptionKey: "memberHome.events.familyDeath.description", actions: [
    { labelKey: "memberHome.events.familyDeath.public", to: "/public" }] },
  { id: "wrong-record", titleKey: "memberHome.events.wrongRecord.title", descriptionKey: "memberHome.events.wrongRecord.description", actions: [
    { labelKey: "memberHome.events.wrongRecord.declaration", to: "/member/profile#correction-heading" }, { labelKey: "memberHome.events.wrongRecord.grievance", to: "/member/grievances" }] },
];
