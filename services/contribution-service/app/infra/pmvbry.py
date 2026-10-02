"""Paid ECR projection and deterministic synthetic history."""
from datetime import date
from sqlalchemy import text
from epfo_persistence.policy import rules_on, section
from app.domain.pmvbry import months, first_completed

INSERT = text('''INSERT INTO pmvbry_ecr_rows
(establishment_id,wage_month,uan,epf_wage_paise,gross_wage_paise,date_of_joining,contribution_received,kind,face_authenticated,aadhaar_authenticated,aadhaar_seeded_bank)
VALUES (:establishment_id,:wage_month,:uan,:epf_wage_paise,:gross_wage_paise,:date_of_joining,:contribution_received,:kind,:face_authenticated,:aadhaar_authenticated,:aadhaar_seeded_bank)
ON CONFLICT (establishment_id,wage_month,uan) DO NOTHING''')


def demo_rows(demo, rules):
    exits = {x['month']: x['count'] for x in demo.get('old_staff_exits', [])}
    old = demo['old_staff']
    for month in months(demo['history_from'], demo['history_to']):
        old -= exits.get(month, 0)
        for index in range(old):
            yield {'establishment_id': demo['establishment_id'], 'wage_month': month, 'uan': f'2000070000{index+1:02d}', 'epf_wage_paise': demo['old_epf_wage_paise'], 'gross_wage_paise': demo['old_gross_wage_paise'], 'date_of_joining': date(2019, 4, 1), 'contribution_received': True, 'kind': 'OLD', 'face_authenticated': True, 'aadhaar_authenticated': True, 'aadhaar_seeded_bank': True}
        for member in demo['joiners']:
            start = first_completed(member['date_of_joining'], rules)
            if start <= month and (not member.get('exit_month') or month < member['exit_month']):
                yield {'establishment_id': demo['establishment_id'], 'wage_month': month, 'uan': member['uan'], 'epf_wage_paise': member['epf_wage_paise'], 'gross_wage_paise': member['gross_wage_paise'], 'date_of_joining': date.fromisoformat(member['date_of_joining']), 'contribution_received': True, 'kind': member['kind'], 'face_authenticated': member['face_authenticated'], 'aadhaar_authenticated': member['aadhaar_authenticated'], 'aadhaar_seeded_bank': member['aadhaar_seeded_bank']}


async def seed_demo(session, demo):
    rules = section(await rules_on(session, date.fromisoformat(demo['history_to'] + '-01')), 'pmvbry')
    await session.execute(text('''INSERT INTO pmvbry_establishments (establishment_id,manufacturing,gstin)
        VALUES (:e,:m,:g) ON CONFLICT (establishment_id) DO UPDATE SET manufacturing=excluded.manufacturing,gstin=excluded.gstin'''),
        {'e': demo['establishment_id'], 'm': demo['manufacturing'], 'g': demo['gstin']})
    for exclusion in demo.get('exclusions', []):
        await session.execute(text('''INSERT INTO pmvbry_establishments (establishment_id,manufacturing,excluded_reason)
            VALUES (:e,false,:r) ON CONFLICT (establishment_id) DO UPDATE SET excluded_reason=excluded.excluded_reason'''),
            {'e': exclusion['establishment_id'], 'r': exclusion['reason']})
    for row in demo_rows(demo, rules):
        await session.execute(INSERT, row)


async def project_paid_filing(session, filing, lines, members):
    rules = section(await rules_on(session, date.fromisoformat(filing['wage_month'] + '-01')), 'pmvbry')
    by_uan = {m['uan']: m for m in members}
    await session.execute(text('''INSERT INTO pmvbry_establishments (establishment_id,manufacturing)
        VALUES (:e,false) ON CONFLICT (establishment_id) DO NOTHING'''), {'e': filing['establishment_id']})
    for line in lines:
        uan = line['UAN']
        member = by_uan.get(uan)
        if not member: continue
        joined = member['date_of_joining']
        joined = joined if isinstance(joined, date) else date.fromisoformat(str(joined)[:10])
        prior = (await session.execute(text('''SELECT 1 FROM establishment_members WHERE uan=:u AND date_of_joining<:start LIMIT 1'''),
                                       {'u': uan, 'start': date.fromisoformat(rules['registration_from'])})).first()
        kind = 'FIRST_TIMER' if not prior and joined.isoformat() >= rules['registration_from'] else 'REJOINEE' if rules['registration_from'] <= joined.isoformat() <= rules['registration_to'] else 'OLD'
        contributions = sum(int(line.get(key, 0) or 0) for key in ('EPF Contribution (EE share)', 'EPS Contribution', 'EPF-EPS Difference (ER share)')) * 100
        await session.execute(INSERT, {'establishment_id': filing['establishment_id'], 'wage_month': filing['wage_month'], 'uan': uan,
            'epf_wage_paise': contributions * 100 // rules['contribution_rate_pct'], 'gross_wage_paise': int(line['Gross Wages']) * 100,
            'date_of_joining': joined, 'contribution_received': True, 'kind': kind, 'face_authenticated': True,
            'aadhaar_authenticated': True, 'aadhaar_seeded_bank': True})


WITHHOLDING_SECTIONS = ("7A", "7C", "26B")      # inquiries under 7A / 7B / 7C and Para 26B (guidelines 6.2.3)


async def on_inquiry_event(session, event) -> None:
    """InquiryRegistered.v1 / InquiryOrderPassed.v1 from compliance-service: track the inquiries that withhold Part B."""
    p = event["payload"]
    if p.get("section") not in WITHHOLDING_SECTIONS:
        return
    if event.get("event_type") == "InquiryRegistered.v1":
        await session.execute(text("""INSERT INTO pmvbry_inquiries (case_id,establishment_id,section,diary_no,state,demand_id)
            VALUES (:c,:e,:s,:d,'PENDING',NULL) ON CONFLICT (case_id) DO NOTHING"""),
            {"c": p["case_id"], "e": p["establishment_id"], "s": p["section"], "d": p["diary_no"]})
    else:
        await session.execute(text("""INSERT INTO pmvbry_inquiries (case_id,establishment_id,section,diary_no,state,demand_id)
            VALUES (:c,:e,:s,:d,'ORDERED',:m) ON CONFLICT (case_id) DO UPDATE SET state='ORDERED', demand_id=excluded.demand_id"""),
            {"c": p["case_id"], "e": p["establishment_id"], "s": p["section"], "d": p["diary_no"], "m": p.get("demand_id") or None})
    await session.execute(text("INSERT INTO pmvbry_establishments (establishment_id,manufacturing) VALUES (:e,false) ON CONFLICT (establishment_id) DO NOTHING"),
                          {"e": p["establishment_id"]})


async def inquiry_exclusion(session, establishment_id: str) -> str | None:
    """Why Part B is withheld for an inquiry: one pending, or an order whose dues are not paid (not complied with)."""
    rows = (await session.execute(text("""SELECT i.section, i.diary_no, i.state, d.state AS demand_state FROM pmvbry_inquiries i
        LEFT JOIN demands d ON d.demand_id = i.demand_id WHERE i.establishment_id=:e ORDER BY i.diary_no"""), {"e": establishment_id})).mappings().all()
    for r in rows:
        if r["state"] == "PENDING":
            return f"Inquiry under {'Para ' if r['section'] == '26B' else 'section '}{r['section']} pending ({r['diary_no']})"
        if r["demand_state"] == "OPEN":
            return f"Order under section {r['section']} ({r['diary_no']}) not complied with: dues unpaid"
    return None
