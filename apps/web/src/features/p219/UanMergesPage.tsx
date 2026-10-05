import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, command, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { ErrorSummary, type FieldError } from "../../components/ui/ErrorSummary";
import i18n from "../../i18n";
import en from "../../i18n/p219-uan.en.json";
import hi from "../../i18n/p219-uan.hi.json";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

i18n.addResourceBundle("en", "translation", en, true, true);
i18n.addResourceBundle("hi", "translation", hi, true, true);

interface UanMerge {
  merge_id: string;
  active_uan: string;
  duplicate_uan: string;
  account_link_ids: string[];
  note: string;
  merged_by: string;
  merged_at: string;
}

const path = "/api/v1/office/uan-merges";
const validUan = (value: string) => /^\d{12}$/.test(value);

export function UanMergesPage() {
  const { t, i18n: language } = useTranslation();
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [active, setActive] = useState("");
  const [duplicate, setDuplicate] = useState("");
  const [note, setNote] = useState("");
  const [touched, setTouched] = useState({ active: false, duplicate: false, note: false });
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<UanMerge | null>(null);
  const list = useQuery({ queryKey: ["office-uan-merges"], queryFn: () => api<Envelope<UanMerge[]>>(path), retry: false });

  const activeError = (touched.active || submitted) && !validUan(active) ? t("p219Uan.activeError") : "";
  const duplicateError = (touched.duplicate || submitted) && !validUan(duplicate) ? t("p219Uan.duplicateError") : "";
  const sameError = (touched.duplicate || submitted) && validUan(active) && validUan(duplicate) && active === duplicate
    ? t("p219Uan.sameError") : "";
  const noteError = (touched.note || submitted) && (!note.trim() || note.trim().length > 1000) ? t("p219Uan.noteError") : "";
  const errors: FieldError[] = [
    ...(activeError ? [{ field: "active-uan", message: activeError }] : []),
    ...(duplicateError || sameError ? [{ field: "duplicate-uan", message: duplicateError || sameError }] : []),
    ...(noteError ? [{ field: "merge-note", message: noteError }] : []),
  ];

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);
    setError(null);
    setResult(null);
    if (!validUan(active) || !validUan(duplicate) || active === duplicate || !note.trim() || note.trim().length > 1000) return;
    setBusy(true);
    try {
      const token = await stepUp.ask({
        action: "merge-uan", resourceId: duplicate,
        summary: t("p219Uan.stepSummary", { duplicate, active }),
      });
      if (!token) return;
      const response = await command<Envelope<UanMerge>>("POST", path,
        { active_uan: active, duplicate_uan: duplicate, note: note.trim() }, { stepUpToken: token });
      setResult(response.data);
      setActive(""); setDuplicate(""); setNote("");
      setTouched({ active: false, duplicate: false, note: false });
      setSubmitted(false);
      await qc.invalidateQueries({ queryKey: ["office-uan-merges"] });
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(false);
    }
  }

  return <main className="page stack">
    <PageHeader eyebrow={t("p219Uan.eyebrow")} title={t("p219Uan.title")} description={t("p219Uan.description")}
      current={t("p219Uan.title")} />

    <section className="card stack" aria-labelledby="merge-form-heading">
      <h2 id="merge-form-heading">{t("p219Uan.formHeading")}</h2>
      <p className="muted">{t("p219Uan.formHelp")}</p>
      <ErrorSummary errors={errors} />
      <ProblemMessage error={error} />
      <form className="stack" aria-label={t("p219Uan.formHeading")} noValidate onSubmit={(event) => void submit(event)}>
        <div className="form-row">
          <div className="ui-field">
            <label htmlFor="active-uan">{t("p219Uan.active")}</label>
            <input id="active-uan" name="active_uan" inputMode="numeric" autoComplete="off" value={active}
              aria-invalid={!!activeError} aria-describedby={activeError ? "active-uan-error" : undefined}
              onChange={(event) => { setActive(event.target.value); setTouched((old) => ({ ...old, active: true })); }} />
            {activeError ? <p className="ui-field-error" id="active-uan-error">{activeError}</p> : null}
          </div>
          <div className="ui-field">
            <label htmlFor="duplicate-uan">{t("p219Uan.duplicate")}</label>
            <input id="duplicate-uan" name="duplicate_uan" inputMode="numeric" autoComplete="off" value={duplicate}
              aria-invalid={!!(duplicateError || sameError)} aria-describedby={duplicateError || sameError ? "duplicate-uan-error" : undefined}
              onChange={(event) => { setDuplicate(event.target.value); setTouched((old) => ({ ...old, duplicate: true })); }} />
            {duplicateError || sameError ? <p className="ui-field-error" id="duplicate-uan-error">{duplicateError || sameError}</p> : null}
          </div>
        </div>
        <div className="ui-field">
          <label htmlFor="merge-note">{t("p219Uan.note")}</label>
          <textarea id="merge-note" name="note" value={note} maxLength={1000}
            aria-invalid={!!noteError} aria-describedby={noteError ? "merge-note-error" : undefined}
            onChange={(event) => { setNote(event.target.value); setTouched((old) => ({ ...old, note: true })); }} />
          {noteError ? <p className="ui-field-error" id="merge-note-error">{noteError}</p> : null}
        </div>
        <div className="actions"><button className="primary" type="submit" disabled={busy}>{t("p219Uan.submit")}</button></div>
      </form>
    </section>

    <div aria-live="polite" aria-atomic="true">
      {result ? <section className="card stack" aria-labelledby="merge-result-heading">
        <h2 id="merge-result-heading">{t("p219Uan.resultHeading")}</h2>
        <p>{t("p219Uan.result", { duplicate: result.duplicate_uan, active: result.active_uan })}</p>
        <p>{t("p219Uan.links", { count: result.account_link_ids.length })} {result.account_link_ids.length ? result.account_link_ids.join(", ") : t("p219Uan.noLinks")}</p>
        <p>{t("p219Uan.balanceFollows")}</p>
        <p className="muted">{t("p219Uan.reference")}: <code>{result.merge_id}</code></p>
      </section> : null}
    </div>

    <section className="card stack" aria-labelledby="merge-list-heading">
      <h2 id="merge-list-heading">{t("p219Uan.listHeading")}</h2>
      <ProblemMessage error={list.error} />
      {list.isPending ? <p className="muted">{t("p219Uan.loading")}</p>
        : list.data?.data.length ? <div className="table-scroll"><table className="responsive-table">
          <thead><tr><th scope="col">{t("p219Uan.active")}</th><th scope="col">{t("p219Uan.duplicate")}</th>
            <th scope="col">{t("p219Uan.when")}</th><th scope="col">{t("p219Uan.byWhom")}</th></tr></thead>
          <tbody>{list.data.data.map((merge) => <tr key={merge.merge_id}>
            <td data-label={t("p219Uan.active")}>{merge.active_uan}</td>
            <td data-label={t("p219Uan.duplicate")}>{merge.duplicate_uan}</td>
            <td data-label={t("p219Uan.when")}>{new Date(merge.merged_at).toLocaleString(language.language === "hi" ? "hi-IN" : "en-IN", { dateStyle: "medium", timeStyle: "short" })}</td>
            <td data-label={t("p219Uan.byWhom")}>{merge.merged_by}</td>
          </tr>)}</tbody>
        </table></div> : !list.error ? <p className="muted">{t("p219Uan.empty")}</p> : null}
    </section>
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel}
      labels={{ title: t("p219Uan.stepTitle"), authorising: t("p219Uan.authorising"), reference: t("p219Uan.duplicate"),
        demoCode: t("p219Uan.demoCode"), demoNotice: t("p219Uan.demoNotice"), oneTimeCode: t("p219Uan.oneTimeCode"),
        retry: t("p219Uan.retry"), preparing: t("p219Uan.preparing"), cancel: t("p219Uan.cancel"), confirm: t("p219Uan.confirm") }} />
  </main>;
}
