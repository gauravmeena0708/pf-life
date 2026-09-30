import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { lifeEvents } from "../../data/lifeEvents";
import { balances, nudges, pendingItems, type MemberHomeInput } from "./memberHome";
import "./memberHome.css";

type Data<K extends keyof MemberHomeInput> = NonNullable<MemberHomeInput[K]>;
const base = "/api/v1/members/me";
const load = <K extends keyof MemberHomeInput>(path: string) => api<Envelope<Data<K>>>(`${base}${path}`);
const words = (value: string) => value.replaceAll("_", " ").toLowerCase();

export function MemberHomePage() {
  const profile = useQuery({ queryKey: ["member-profile"], queryFn: () => load<"profile">(""), retry: false });
  const service = useQuery({ queryKey: ["service-history"], queryFn: () => load<"service">("/service-history"), retry: false });
  const eligibility = useQuery({ queryKey: ["member-claim-eligibility"], queryFn: () => load<"eligibility">("/claims/eligible-types"), retry: false });
  const claims = useQuery({ queryKey: ["member-claims"], queryFn: () => load<"claims">("/claims"), retry: false });
  const applications = useQuery({ queryKey: ["applications"], queryFn: () => load<"applications">("/applications"), retry: false });
  const nominations = useQuery({ queryKey: ["member-nominations"], queryFn: () => load<"nominations">("/nominations"), retry: false });
  const pension = useQuery({ queryKey: ["pension-estimate"], queryFn: () => load<"pension">("/pension-eligibility-preview"), retry: false });
  const passbook = useQuery({ queryKey: ["member-passbook"], queryFn: () => load<"passbook">("/passbook"), retry: false });
  const input: MemberHomeInput = { profile: profile.data?.data, service: service.data?.data, eligibility: eligibility.data?.data,
    claims: claims.data?.data, applications: applications.data?.data, nominations: nominations.data?.data,
    pension: pension.data?.data, passbook: passbook.data?.data };
  const savings = balances(input);
  const pending = pendingItems(input);
  const tasks = nudges(input, new Date());
  const best = input.pension?.scenarios.filter((scenario) => scenario.eligible)
    .reduce<(typeof input.pension.scenarios)[number] | null>((top, scenario) => !top || scenario.monthly_paise > top.monthly_paise ? scenario : top, null);

  return <div className="stack member-home">
    <PageHeader eyebrow="Member services" title="Your PF at a glance" description="Your accounts, requests and next steps in one place." current="My PF">
      {input.profile ? <div className="member-home-identity"><strong>{input.profile.name}</strong><span>UAN <code>{input.profile.uan}</code></span></div> : null}
    </PageHeader>
    <ProblemMessage error={profile.error} />{profile.isLoading ? <p role="status">Loading your profile…</p> : null}

    <section className="card stack" aria-labelledby="savings-heading"><h2 id="savings-heading">Your savings</h2>
      <ProblemMessage error={service.error} /><ProblemMessage error={eligibility.error} /><ProblemMessage error={pension.error} />
      {service.isLoading || eligibility.isLoading || pension.isLoading ? <p role="status">Loading your savings…</p> : null}
      {input.eligibility ? <div className="member-home-total"><span>Total across all member IDs</span><strong>{rupees(savings.total_paise)}</strong></div> : null}
      {input.service && input.eligibility ? <ul className="member-home-accounts" aria-label="Balance by member ID">{savings.accounts.map((row) => <li key={row.account_link_id}>
        <span><strong>{row.establishment_name}</strong><small>Member ID <code>{row.account_link_id}</code>{row.primary ? <span className="state-pill member-home-primary">Primary</span> : null} · {words(row.status)}</small></span>
        <strong className="numeric">{rupees(row.balance_paise)}</strong></li>)}</ul> : null}
      {input.service ? <p><strong>Total service:</strong> {Math.floor(input.service.total_service_months / 12)} years {input.service.total_service_months % 12} months</p> : null}
      {input.pension ? <p><strong>Best eligible pension estimate:</strong> {best ? `${rupees(best.monthly_paise)} per month (${best.label})` : "No eligible scenario yet."} <Link to="/member/profile#pension-estimate-heading">See the pension estimate</Link></p> : null}
      {input.eligibility || input.pension ? <p className="muted small">Illustrative figures for this demonstration. Check the account and pension details before making a decision.</p> : null}
    </section>

    <section className="card stack" aria-labelledby="pending-heading"><h2 id="pending-heading">What is pending</h2>
      <ProblemMessage error={claims.error} /><ProblemMessage error={applications.error} /><ProblemMessage error={eligibility.error} />
      {claims.isLoading || applications.isLoading || eligibility.isLoading ? <p role="status">Loading pending requests…</p> : null}
      {pending.length ? <ul className="member-home-list">{pending.map((item) => <li key={item.id}><Link to={item.to}><strong>{item.next}</strong><span>{item.title}</span></Link></li>)}</ul>
        : !claims.isLoading && !applications.isLoading && !claims.error && !applications.error ? <p className="muted">Nothing is pending.</p> : null}
    </section>

    <section className="card stack" aria-labelledby="todo-heading"><h2 id="todo-heading">To do</h2>
      <ProblemMessage error={profile.error} /><ProblemMessage error={service.error} /><ProblemMessage error={eligibility.error} />
      <ProblemMessage error={nominations.error} /><ProblemMessage error={passbook.error} />
      {profile.isLoading || service.isLoading || eligibility.isLoading || nominations.isLoading || passbook.isLoading ? <p role="status">Loading your next steps…</p> : null}
      {tasks.length ? <ul className="member-home-list">{tasks.map((item) => <li key={item.id}><Link to={item.to} className={item.tone === "info" ? "member-home-info" : ""}>
        <strong>{item.title}</strong><span>{item.detail}</span></Link></li>)}</ul>
        : !profile.isLoading && !service.isLoading && !eligibility.isLoading && !nominations.isLoading && !passbook.isLoading
          && !profile.error && !service.error && !eligibility.error && !nominations.error && !passbook.error ? <p className="muted">You are all set.</p> : null}
    </section>

    <section className="stack" aria-labelledby="events-heading"><h2 id="events-heading">What do you want to do?</h2>
      <div className="member-home-events">{lifeEvents.map((event) => <article className="card stack" key={event.id}><h3>{event.title}</h3>
        <p className="muted">{event.description}</p><div className="actions">{event.actions.map((action) => <Link key={action.to} to={action.to}>{action.label}</Link>)}</div>
      </article>)}</div>
    </section>
  </div>;
}
