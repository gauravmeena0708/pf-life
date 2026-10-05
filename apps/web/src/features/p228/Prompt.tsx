import { createRoot } from "react-dom/client";

import type { Problem } from "../../api/client";
import en from "../../i18n/p228-gateway.en.json";
import hi from "../../i18n/p228-gateway.hi.json";
import { StepUpDialog } from "../stepup/StepUpDialog";

/** Mount only while a gateway risk challenge is pending; existing page-specific dialogs stay independent. */
export function confirmRiskStepUp(problem: Problem): Promise<string | null> {
  const copy: typeof en = document.documentElement.lang.startsWith("hi") ? hi : en;
  const reason = (problem.reason_codes ?? []).map((code) => (copy as Record<string, string>)[code]).filter(Boolean).join(" ");
  const host = document.createElement("section");
  host.setAttribute("aria-live", "polite");
  host.style.color = "#102f59";
  host.style.backgroundColor = "#ffffff";
  document.body.append(host);
  const root = createRoot(host);
  return new Promise((resolve) => {
    const finish = (token: string | null) => {
      root.unmount();
      host.remove();
      resolve(token);
    };
    root.render(<StepUpDialog request={{ action: problem.action!, resourceId: problem.resource_id!,
      summary: `${reason} ${copy.prompt}`.trim() }} labels={copy} onConfirmed={finish} onCancel={() => finish(null)} />);
  });
}
