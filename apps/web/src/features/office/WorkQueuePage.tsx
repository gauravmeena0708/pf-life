import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";

import { api, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { dateTime, roleLabel } from "../journeyB";
import { ProcessForm, type ProcessOperation } from "./ProcessForm";
import type { OfficeCase } from "./types";
import {
  filterCases,
  getQueueCounts,
  sortCases,
  timeLeft,
  type CaseKindCategory,
  type SortOption,
} from "./queue";

interface Queue { office_id: string; role: string; items: OfficeCase[]; startable_processes?: ProcessOperation[] }

export function WorkQueuePage() {
  const { t, i18n } = useTranslation();
  const queue = useQuery({ queryKey: ["office-work-queue"], queryFn: () => api<Envelope<Queue>>("/api/v1/office/work-queue"), retry: false, refetchInterval: 5000 });
  const data = queue.data?.data;
  const qc = useQueryClient();
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const isDa = session.data?.stakeholder === "fo.da_accounts";
  const stopped = useQuery({ queryKey: ["stopped-cases"], enabled: isDa, retry: false, refetchInterval: 10000,
    queryFn: () => api<Envelope<OfficeCase[]>>("/api/v1/office/stopped-cases") });
  const [notice, setNotice] = useState<string | null>(null);

  const [searchParams, setSearchParams] = useSearchParams();
  const querySearch = searchParams.get("q") ?? "";
  const queryKind = (searchParams.get("kind") as CaseKindCategory) || "all";
  const queryOverdue = searchParams.get("overdue") === "true";
  const querySort = (searchParams.get("sort") as SortOption) || "deadline";
  const queryPage = Math.max(1, parseInt(searchParams.get("page") ?? "1", 10) || 1);

  const [searchInput, setSearchInput] = useState(querySearch);

  useEffect(() => {
    setSearchInput(querySearch);
  }, [querySearch]);

  const updateFilters = (updates: Partial<{ q: string; kind: string; overdue: boolean; sort: string; page: number }>) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if ("q" in updates) {
        if (updates.q && updates.q.trim()) {
          next.set("q", updates.q.trim());
        } else {
          next.delete("q");
        }
      }
      if ("kind" in updates) {
        if (updates.kind && updates.kind !== "all") {
          next.set("kind", updates.kind);
        } else {
          next.delete("kind");
        }
      }
      if ("overdue" in updates) {
        if (updates.overdue) {
          next.set("overdue", "true");
        } else {
          next.delete("overdue");
        }
      }
      if ("sort" in updates) {
        if (updates.sort && updates.sort !== "deadline") {
          next.set("sort", updates.sort);
        } else {
          next.delete("sort");
        }
      }
      if ("page" in updates) {
        if (updates.page && updates.page > 1) {
          next.set("page", String(updates.page));
        } else {
          next.delete("page");
        }
      }
      return next;
    }, { replace: true });
  };

  const handleClearFilters = () => {
    setSearchInput("");
    setSearchParams({}, { replace: true });
  };

  const rawItems = useMemo(() => data?.items ?? [], [data?.items]);
  const counts = useMemo(() => getQueueCounts(rawItems), [rawItems]);

  const filteredCases = useMemo(() => {
    return filterCases(rawItems, {
      search: querySearch,
      kind: queryKind,
      overdueOnly: queryOverdue,
    });
  }, [rawItems, querySearch, queryKind, queryOverdue]);

  const sortedCases = useMemo(() => {
    return sortCases(filteredCases, querySort);
  }, [filteredCases, querySort]);

  const PAGE_SIZE = 25;
  const totalFiltered = sortedCases.length;
  const totalPages = Math.max(1, Math.ceil(totalFiltered / PAGE_SIZE));
  const currentPage = Math.min(Math.max(1, queryPage), totalPages);
  const startIndex = (currentPage - 1) * PAGE_SIZE;
  const pagedCases = sortedCases.slice(startIndex, startIndex + PAGE_SIZE);

  return <section className="stack" aria-labelledby="work-queue-heading">
    <PageHeader id="work-queue-heading" eyebrow={t("office.eyebrow")} title={t("office.queueTitle")}
      description={data ? `${data.office_id} · ${roleLabel(data.role, t)}` : t("office.queueDescription")} current={t("navigation.workQueue")} />
    {notice ? <p role="status" className="ok">{notice}</p> : null}
    {data?.startable_processes?.map((op) => (
      <section key={`${op.process}-${op.name}`} className="card stack" aria-labelledby={`start-${op.process}`}>
        <div className="section-heading"><div><p className="eyebrow">Start a process</p><h2 id={`start-${op.process}`}>{op.title}</h2></div></div>
        <ProcessForm operation={op} askSubject onDone={(msg) => { setNotice(msg); void qc.invalidateQueries({ queryKey: ["office-work-queue"] }); }} />
      </section>
    ))}
    <section className="card stack" aria-labelledby="queue-cases-heading">
      <h2 id="queue-cases-heading">{t("office.cases")}</h2>
      <ProblemMessage error={queue.error} />
      {queue.isLoading ? <p role="status">{t("office.loadingQueue")}</p> : null}

      <div className="metrics queue-metrics" aria-label={t("queueUx.metricsSummary")}>
        <div className="metric-cell">
          <span>{t("queueUx.countOverdue")}</span>
          <strong className="queue-metric-overdue">{counts.overdue}</strong>
        </div>
        <div className="metric-cell">
          <span>{t("queueUx.countDueToday")}</span>
          <strong>{counts.dueToday}</strong>
        </div>
        <div className="metric-cell">
          <span>{t("queueUx.countDueThisWeek")}</span>
          <strong>{counts.dueThisWeek}</strong>
        </div>
        <div className="metric-cell">
          <span>{t("queueUx.countTotal")}</span>
          <strong>{counts.total}</strong>
        </div>
      </div>

      <form
        role="search"
        aria-label="Filter the queue"
        className="queue-filter-form"
        onSubmit={(e) => {
          e.preventDefault();
          updateFilters({ q: searchInput, page: 1 });
        }}
      >
        <div className="queue-filter-field">
          <label htmlFor="queue-search">{t("queueUx.searchLabel")}</label>
          <input
            id="queue-search"
            type="search"
            value={searchInput}
            onChange={(e) => {
              const val = e.target.value;
              setSearchInput(val);
              updateFilters({ q: val, page: 1 });
            }}
            placeholder={t("queueUx.searchPlaceholder")}
          />
        </div>
        <div className="queue-filter-field">
          <label htmlFor="queue-kind">{t("queueUx.kindFilterLabel")}</label>
          <select
            id="queue-kind"
            value={queryKind}
            onChange={(e) => {
              updateFilters({ kind: e.target.value as CaseKindCategory, page: 1 });
            }}
          >
            <option value="all">{t("queueUx.kindAll")}</option>
            <option value="claims">{t("queueUx.kindClaims")}</option>
            <option value="grievances">{t("queueUx.kindGrievances")}</option>
            <option value="other">{t("queueUx.kindOther")}</option>
          </select>
        </div>
        <div className="queue-filter-field queue-filter-checkbox">
          <label htmlFor="queue-overdue">
            <input
              id="queue-overdue"
              type="checkbox"
              checked={queryOverdue}
              onChange={(e) => {
                updateFilters({ overdue: e.target.checked, page: 1 });
              }}
            />
            {t("queueUx.overdueOnly")}
          </label>
        </div>
        <div className="queue-filter-field">
          <label htmlFor="queue-sort">{t("queueUx.sortLabel")}</label>
          <select
            id="queue-sort"
            value={querySort}
            onChange={(e) => {
              updateFilters({ sort: e.target.value as SortOption, page: 1 });
            }}
          >
            <option value="deadline">{t("queueUx.sortDeadline")}</option>
            <option value="amount">{t("queueUx.sortAmount")}</option>
            <option value="oldest">{t("queueUx.sortOldest")}</option>
          </select>
        </div>
      </form>

      {data?.items.length === 0 ? <p className="empty-state">{t("office.emptyQueue")}</p> : null}

      {data && data.items.length > 0 && totalFiltered === 0 ? (
        <div className="empty-state stack">
          <p>{t("queueUx.noMatches")}</p>
          <button type="button" className="button secondary" onClick={handleClearFilters}>
            {t("queueUx.clearFilters")}
          </button>
        </div>
      ) : null}

      {totalFiltered > 0 ? (
        <>
          <div className="table-scroll">
            <table className="responsive-table">
              <thead>
                <tr>
                  <th scope="col">{t("office.caseId")}</th>
                  <th scope="col">{t("claims.claimId")}</th>
                  <th scope="col">{t("claims.form")}</th>
                  <th scope="col" className="numeric">{t("claims.amount")}</th>
                  <th scope="col">{t("office.chainProgress")}</th>
                  <th scope="col">{t("office.slaDue")}</th>
                  <th scope="col">{t("office.nextAction")}</th>
                  <th scope="col">{t("queueUx.timeLeftCol")}</th>
                </tr>
              </thead>
              <tbody>
                {pagedCases.map((item) => {
                  const tl = timeLeft(item.sla_due_at, undefined, t);
                  return (
                    <tr key={item.case_id}>
                      <td data-label={t("office.caseId")}>
                        <Link to={item.grievance_id ? `/office/grievances/${item.grievance_id}` : `/office/cases/${item.case_id}`}>
                          <code>{item.case_id}</code>
                        </Link>
                      </td>
                      <td data-label={t("claims.claimId")}>
                        <code>{item.claim_id ?? item.grievance_id ?? item.subject_ref}</code>
                        {item.advisory_signal_id ? (
                          <>
                            <br />
                            <span className="state-pill" title={t("office.advisoryHelp")}>{t("office.advisory")}</span>
                          </>
                        ) : null}
                      </td>
                      <td data-label={t("claims.form")}>
                        {item.grievance_id
                          ? t("office.grievanceKind")
                          : item.process
                            ? `${item.kind.replaceAll("_", " ").toLowerCase()} · ${item.subject_ref}`
                            : item.form_type}
                      </td>
                      <td data-label={t("claims.amount")} className="numeric">{item.grievance_id || item.process ? "—" : rupees(item.amount_paise)}</td>
                      <td data-label={t("office.chainProgress")}>
                        {item.chain.length
                          ? t("office.stepOf", { step: Math.min(item.step + 1, item.chain.length), total: item.chain.length })
                          : "—"}
                      </td>
                      <td data-label={t("office.slaDue")}>{dateTime(item.sla_due_at, i18n.language)}</td>
                      <td data-label={t("office.nextAction")}>
                        {item.next_action ? (
                          <span className="state-pill">{t(`office.actions.${item.next_action}`, { defaultValue: item.next_action })}</span>
                        ) : "—"}
                      </td>
                      <td data-label={t("queueUx.timeLeftCol")}>
                        <span className={tl.overdue ? "queue-overdue" : undefined}>{tl.text}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="queue-pagination">
            <span className="pagination-summary">
              {t("queueUx.showing", {
                start: startIndex + 1,
                end: Math.min(startIndex + PAGE_SIZE, totalFiltered),
                total: totalFiltered,
                defaultValue: `Showing ${startIndex + 1}–${Math.min(startIndex + PAGE_SIZE, totalFiltered)} of ${totalFiltered}`,
              })}
            </span>
            <div className="pagination-buttons">
              <button
                type="button"
                className="button secondary"
                disabled={currentPage <= 1}
                onClick={() => updateFilters({ page: currentPage - 1 })}
              >
                {t("queueUx.previous")}
              </button>
              <button
                type="button"
                className="button secondary"
                disabled={currentPage >= totalPages}
                onClick={() => updateFilters({ page: currentPage + 1 })}
              >
                {t("queueUx.next")}
              </button>
            </div>
          </div>
        </>
      ) : null}
    </section>
    {isDa ? <section className="card stack" aria-labelledby="stopped-heading"><h2 id="stopped-heading">Stopped claims</h2>
      {stopped.data?.data.length ? <ul className="plain-list">{stopped.data.data.map((c) => <li key={c.case_id}>
        <Link to={`/office/cases/${c.case_id}`}><code>{c.case_id}</code></Link> — claim <code>{c.claim_id}</code>:{" "}
        {String((c.data?.stopped as { reason?: string } | undefined)?.reason ?? "")}</li>)}</ul> : <p className="muted">No stopped claims.</p>}
    </section> : null}
  </section>;
}
