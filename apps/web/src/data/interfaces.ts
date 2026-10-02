import generated from "./system-map.generated.json";

export type Coverage = "Working" | "Mock" | "Planned";
export interface EndpointCounts { W: number; M: number; P: number; "?": number }
export interface InterfaceDef {
  id: number;
  slug: string;
  name: string;
  coverage: Coverage;
  purpose: string;
  endpoints: EndpointCounts;
  stakeholders: string[];
}
export interface Stakeholder {
  name: string;
  group: string;
  endpoints: EndpointCounts;
  activities: { id: string; does: string }[];
  personas: string[];
}
export interface SystemTotals {
  interfaces: number;
  stakeholders: number;
  stakeholders_with_access: number;
  activities: number;
  endpoints: EndpointCounts;
  personas: number;
}
/** How far an activity is built: every endpoint working (BUILT), some (PARTLY), none (PLANNED); done outside the POC
 *  through an adapter (EXTERNAL) or on paper (OFFLINE); planned for later (FUTURE). */
export type ActivityStatus = "BUILT" | "PARTLY" | "PLANNED" | "EXTERNAL" | "OFFLINE" | "FUTURE";
export interface Activity { id: string; flow: string; actor: string; does: string; next: string[]; status: ActivityStatus; endpoints: number; src: string }
export interface SystemMap {
  generated: string;
  totals: SystemTotals;
  interfaces: InterfaceDef[];
  stakeholders: Record<string, Stakeholder>;
  flows: Record<string, string>;
  activities: Activity[];
}

/** Coverage is emitted as a string by JSON inference; the generator owns its allowed values. */
const systemMap = generated as SystemMap;
export const INTERFACES = systemMap.interfaces;
export const STAKEHOLDERS = systemMap.stakeholders;
export const TOTALS = systemMap.totals;
export const FLOWS = systemMap.flows;
export const ACTIVITIES = systemMap.activities;
export const GENERATED = systemMap.generated;
