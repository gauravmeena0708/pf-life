import json
from tests.test_ecr_api import ctx  # noqa: F401
from datetime import date
from pathlib import Path
from epfo_persistence.policy import baseline, section
from app.domain.pmvbry import first_completed, incentive, part_a, part_b, paying_slots
from app.infra.pmvbry import demo_rows

RULES = section(baseline(), 'pmvbry')
DEMO = json.loads((Path(__file__).resolve().parents[3] / 'scripts/seed/synthetic.json').read_text())['pmvbry_demo']


def test_first_completed_and_slab():
    assert first_completed('2025-10-05', RULES) == '2025-10'
    assert first_completed('2025-10-06', RULES) == '2025-11'
    assert incentive(950000, RULES) == 95000


def test_synthetic_history_counts_and_part_a():
    rows = list(demo_rows(DEMO, RULES))
    assert sum(r['wage_month'] == '2025-07' for r in rows) == 30
    assert sum(r['wage_month'] == '2025-10' for r in rows) == 33
    assert sum(r['wage_month'] == '2025-12' for r in rows) == 33
    assert sum(r['wage_month'] == '2026-03' for r in rows) == 35
    assert not any(r['uan'] == '200007000102' and r['wage_month'] == '2026-03' for r in rows)
    arjun = part_a([r for r in rows if r['uan'] == '100000000914'], RULES, '2026-09')[0]
    assert arjun['instalments'][0]['amount_paise'] == 700000
    assert arjun['instalments'][0]['state'] == 'DUE'
    assert arjun['instalments'][1]['state'] == 'NOT_YET'
    after_course = part_a([r for r in rows if r['uan'] == '100000000914'], RULES, '2026-09', literacy=True)[0]
    assert after_course['instalments'][1]['amount_paise'] == 700000
    assert after_course['instalments'][1]['state'] == 'DUE'


def test_demo_employer_and_exclusion():
    rows = list(demo_rows(DEMO, RULES))
    plan = part_b(rows, RULES, '2026-09', manufacturing=True)
    assert (plan['baseline'], plan['threshold'], plan['crossing_month'], plan['incentive_months']) == (30, 2, '2025-10', 48)
    assert plan['months'][0]['net_additional'] == 2
    excluded = part_b(rows, RULES, '2026-09', manufacturing=True, excluded_reason='inquiry')
    assert excluded['totals']['computed_paise'] == 0


def test_sop_net_additional_cases():
    def rows(old):
        result = []
        for month in ('2025-10', '2025-11', '2025-12', '2026-01', '2026-02', '2026-03'):
            for i in range(old):
                result.append({'uan': f'O{i}', 'wage_month': month, 'date_of_joining': date(2019,4,1), 'kind': 'OLD', 'contribution_received': True, 'epf_wage_paise': 1000000, 'gross_wage_paise': 1000000, 'aadhaar_authenticated': True})
            for i in range(4):
                result.append({'uan': f'N{i}', 'wage_month': month, 'date_of_joining': date(2025,10,1), 'kind': 'FIRST_TIMER', 'contribution_received': True, 'epf_wage_paise': 1000000, 'gross_wage_paise': 1000000, 'aadhaar_authenticated': True})
        return result
    # The SOP cases stipulate a baseline of 30 independent of current old staff.
    for old, expected in ((29, 3), (32, 4)):
        prior = []
        for month in ('2024-08','2024-09','2024-10','2024-11','2024-12','2025-01','2025-02','2025-03','2025-04','2025-05','2025-06','2025-07'):
            prior.extend({'uan': f'B{i}', 'wage_month': month, 'date_of_joining': date(2019,4,1), 'kind': 'OLD', 'contribution_received': True} for i in range(30))
        plan = part_b(prior + rows(old), RULES, '2026-03')
        assert plan['months'][-1]['net_additional'] == expected


def test_sop_slot_periods():
    starts = {}
    sequence = [70] * 5 + [93] * 25
    paid = [paying_slots(count, index, starts, RULES['incentive_months']) for index, count in enumerate(sequence)]
    assert paid[24] == 23
    starts = {}
    sequence = [4] + [3] * 3 + [5] * 25
    paid = [paying_slots(count, index, starts, RULES['incentive_months']) for index, count in enumerate(sequence)]
    assert starts[4] == 0 and starts[5] == 4
    assert paid[1] == 3 and paid[4] == 5 and paid[24] == 1 and paid[27] == 1 and paid[28] == 0


import pytest
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem
from app.api import pmvbry_routes


@pytest.mark.asyncio
async def test_pmvbry_role_guards():
    for dependency, role in ((pmvbry_routes.EMPLOYER, 'member'),
                             (pmvbry_routes.MEMBER, 'employer.owner'),
                             (pmvbry_routes.HO, 'member'),
                             (pmvbry_routes.FINANCE, 'ho.cpfc'),
                             (require_stakeholder('employer.owner'), 'employer.operator')):
        with pytest.raises(Problem) as exc:
            await dependency(Actor(subject='x', stakeholder=role, correlation_id='c'))
        assert exc.value.status == 403
    with pytest.raises(Problem) as exc:
        require_step_up(Actor(subject='x', stakeholder='employer.owner', correlation_id='c'), 'pmvbry-option', 'EST-1')
    assert exc.value.status == 428


def test_part_a_ceases_when_the_first_timer_leaves():
    rows = [r for r in demo_rows(DEMO, RULES) if r['uan'] == '200007000102']      # left in March 2026 after 5 months
    left = part_a(rows, RULES, '2026-09')[0]
    assert left['instalments'][0]['state'] == 'CEASED'


def test_http_views_option_run_and_replay(ctx):
    import uuid
    from tests.test_ecr_api import hdr
    client, q = ctx
    AUTO, OWNER = 'EST-DEMO-0007', '00000000-0000-4000-8000-000000000073'
    ARJUN = '00000000-0000-4000-8000-000000000072'
    owner = lambda **k: hdr(OWNER, 'employer.owner', ['establishment.manage'], establishment=AUTO, **k)
    view = client.get('/api/v1/employers/me/pmvbry', headers=owner())
    assert view.status_code == 200, view.json()
    data = view.json()['data']
    assert data['baseline'] == 30 and data['crossing_month'] == '2025-10'
    option = {'gstin': '07AAAAD0007A1Z5', 'bank_account_ref': 'PAN-LINKED-0007'}
    assert client.post('/api/v1/employers/me/pmvbry/options', json=option, headers=owner()).status_code == 428      # step-up
    done = client.post('/api/v1/employers/me/pmvbry/options', json=option,
                       headers=owner(step_up={'action': 'pmvbry-option', 'resource_id': AUTO}))
    assert done.status_code in (200, 201), done.json()
    assert q("SELECT COUNT(*) FROM outbox WHERE event_type='PmvbryOptionExercised.v1'")[0][0] == 1

    member = lambda: hdr(ARJUN, 'member', [], establishment=None)
    mine = client.get('/api/v1/members/me/pmvbry', headers=member())
    assert mine.status_code == 200, mine.json()
    assert client.post('/api/v1/members/me/pmvbry/financial-literacy-completions', json={}, headers=member()).status_code in (200, 201)

    finance = lambda **k: hdr('ho-finance-1', 'ho.fa_cao', [], establishment=None, **k)
    month = date.today().replace(day=1).isoformat()[:7]
    preview = client.get('/api/v1/ho/pmvbry/disbursement-runs/preview?as_of_month=2026-09', headers=finance())
    assert preview.status_code == 200, preview.json()
    plan = preview.json()['data']
    assert plan['amount_paise'] > 0 and plan['held_paise'] > 0          # SYNTH FT THREE's bank is not Aadhaar-seeded
    assert {p['kind'] for p in plan['payments']} == {'A', 'B'}
    key = str(uuid.uuid4())
    step = {'action': 'pmvbry-disbursement', 'resource_id': '2026-09', 'amount_paise': plan['amount_paise']}
    run = client.post('/api/v1/ho/pmvbry/disbursement-runs', json={'as_of_month': '2026-09'},
                      headers=finance(step_up=step, **{'Idempotency-Key': key}))
    assert run.status_code == 200, run.json()
    assert run.json()['data']['part_a_paise'] + run.json()['data']['part_b_paise'] == plan['amount_paise']
    replay = client.post('/api/v1/ho/pmvbry/disbursement-runs', json={'as_of_month': '2026-09'},
                         headers=finance(step_up=step, **{'Idempotency-Key': key}))
    assert replay.json()['data'] == run.json()['data']
    again = client.get('/api/v1/ho/pmvbry/disbursement-runs/preview?as_of_month=2026-09', headers=finance())
    assert again.json()['data']['amount_paise'] == 0                    # nothing new to pay for the same month
    payload = json.loads(q("SELECT payload FROM outbox WHERE event_type='PmvbryIncentiveDisbursed.v1'")[0][0])['envelope']['payload']
    assert isinstance(payload['payments'], int)
    board = client.get('/api/v1/ho/pmvbry/dashboard', headers=hdr('ho-cpfc-1', 'ho.cpfc', [], establishment=None))
    assert board.status_code == 200
    assert board.json()['data']['part_a_beneficiaries'] == 3       # ARJUN, FT ONE, FT THREE (held); not the leaver, the high pay or no FAT
    assert client.get('/api/v1/ho/pmvbry/dashboard', headers=member()).status_code == 403
    assert client.get('/api/v1/ho/pmvbry/disbursement-runs/preview?as_of_month=2026-09', headers=member()).status_code == 403
    assert month
