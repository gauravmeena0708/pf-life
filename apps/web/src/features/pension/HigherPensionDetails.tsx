import { statusLabel } from "../statusLabel";
import { useTranslation } from "react-i18next";
import { rupees } from "../../api/client";

export interface HigherPensionWage {
  month: string; wage_paise: number; ceiling_paise: number; excess_paise: number; dues_paise: number;
}
export interface HigherPensionPreview { dues_paise: number; working: string | null; wages: HigherPensionWage[] }
export interface HigherPensionOption extends Omit<HigherPensionPreview, "dues_paise"> {
  dues_paise: number | null;
  option_id: string; uan: string; account_link_id: string;
  state: "SUBMITTED" | "VALIDATED" | "REJECTED_BY_EMPLOYER"; higher_wages_from: string;
  rule_version: string | null; employer_note: string | null; submitted_at: string | null; validated_at: string | null; next_step: string;
  name?: string; date_of_joining?: string;
}

export function HigherPensionDues({ data }: { data: Omit<HigherPensionPreview, "dues_paise"> & { dues_paise: number | null } }) {
  return <div className="stack"><p><strong>Dues: {rupees(data.dues_paise)}</strong></p>
    {data.working ? <p>{data.working}</p> : null}
    {data.wages.length ? <div className="table-scroll"><table><thead><tr>
      <th scope="col">Month</th><th scope="col">Wages</th><th scope="col">Ceiling</th><th scope="col">Excess</th><th scope="col">Dues</th>
    </tr></thead><tbody>{data.wages.map((wage) => <tr key={wage.month}><th scope="row">{wage.month}</th>
      <td>{rupees(wage.wage_paise)}</td><td>{rupees(wage.ceiling_paise)}</td><td>{rupees(wage.excess_paise)}</td>
      <td>{rupees(wage.dues_paise)}</td></tr>)}</tbody></table></div> : null}
  </div>;
}

export function HigherPensionDetails({ option }: { option: HigherPensionOption }) {
  const { t } = useTranslation();
  return <div className="stack"><dl className="kv"><dt>UAN</dt><dd>{option.uan}</dd>
    <dt>Member ID</dt><dd>{option.account_link_id}</dd><dt>State</dt><dd>{statusLabel(option.state, t)}</dd>
    <dt>Higher wages from</dt><dd>{option.higher_wages_from}</dd><dt>Rule version</dt><dd>{option.rule_version ?? "—"}</dd>
    <dt>Submitted</dt><dd>{option.submitted_at ?? "—"}</dd><dt>Validated</dt><dd>{option.validated_at ?? "—"}</dd>
    <dt>Employer note</dt><dd>{option.employer_note ?? "—"}</dd></dl>
    <HigherPensionDues data={option} /><p className="pending-notice">{option.next_step}</p>
  </div>;
}
