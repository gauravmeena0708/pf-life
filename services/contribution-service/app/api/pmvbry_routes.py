"""PMVBRY synthetic calculations and mock disbursements."""
import uuid
from datetime import UTC, date, datetime
from fastapi import Query, APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from app.domain.pmvbry import month_end, part_a, part_b
from app.infra.db import sessions
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit, find_response, request_hash, store_response
from epfo_persistence.policy import rules_on, section

router = APIRouter()
EMPLOYER = require_stakeholder('employer.owner', 'employer.operator', 'employer.signatory')
MEMBER = require_stakeholder('member')
HO = require_stakeholder('ho.cpfc', 'ho.fa_cao')
FINANCE = require_stakeholder('ho.fa_cao')

class OptionInput(BaseModel):
    gstin: str = Field(min_length=15, max_length=15)
    bank_account_ref: str = Field(min_length=1, max_length=120)

class RunInput(BaseModel):
    as_of_month: str = Field(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')
    dry_run: bool = False                     # preview what a run would pay (no step-up, nothing recorded)


def _est(actor):
    if not actor.establishment_id:
        raise Problem(403, '/problems/forbidden', 'No establishment bound to actor')
    return actor.establishment_id

async def _rules(session, month):
    return section(await rules_on(session, date.fromisoformat(month + '-01')), 'pmvbry')

async def _est_data(session, eid):
    return (await session.execute(text('SELECT * FROM pmvbry_establishments WHERE establishment_id=:e'), {'e': eid})).mappings().first()

async def _rows(session, eid, month):
    return [dict(r) for r in (await session.execute(text('SELECT * FROM pmvbry_ecr_rows WHERE establishment_id=:e AND wage_month<=:m ORDER BY wage_month,uan'), {'e': eid, 'm': month})).mappings()]

async def _payments(session, eid):
    return [dict(r) for r in (await session.execute(text('SELECT * FROM pmvbry_payments WHERE establishment_id=:e ORDER BY created_at,id'), {'e': eid})).mappings()]

async def _employer_plan(session, eid, month):
    cfg = await _est_data(session, eid)
    rows = await _rows(session, eid, month)
    payments = await _payments(session, eid)
    rules = await _rules(session, month)
    # This service has no establishment registration-date projection. A history beginning
    # in the registration period is treated as a new establishment for this POC.
    registered_on = rules['registration_from'] if rows and min(r['wage_month'] for r in rows) >= rules['registration_from'][:7] else None
    from app.infra.pmvbry import inquiry_exclusion
    excluded = (cfg['excluded_reason'] if cfg else None) or await inquiry_exclusion(session, eid)   # the seed's, or a compliance inquiry
    plan = part_b(rows, rules, month, bool(cfg['manufacturing']) if cfg else False, registered_on=registered_on, excluded_reason=excluded, option_exercised=bool(cfg and cfg['option_exercised_at']), payments=payments)
    plan.update({'establishment_id': eid, 'option_exercised_at': cfg['option_exercised_at'].isoformat() if cfg and hasattr(cfg['option_exercised_at'], 'isoformat') else cfg['option_exercised_at'] if cfg else None, 'gstin': cfg['gstin'] if cfg else None, 'bank_account_ref': cfg['bank_account_ref'] if cfg else None})
    return plan

@router.get('/api/v1/employers/me/pmvbry')
async def employer_view(actor: Actor = Depends(EMPLOYER)):
    async with sessions()() as session:
        month = date.today().strftime('%Y-%m')
        return envelope(await _employer_plan(session, _est(actor), month))

@router.post('/api/v1/employers/me/pmvbry/options')
async def option(body: OptionInput, actor: Actor = Depends(require_stakeholder('employer.owner'))):
    eid = _est(actor)
    require_step_up(actor, 'pmvbry-option', eid)
    async with sessions()() as session, session.begin():
        existing = await _est_data(session, eid)
        if existing and existing['option_exercised_at']:
            return envelope({'establishment_id': eid, 'option_exercised_at': str(existing['option_exercised_at']), 'gstin': existing['gstin']})
        await session.execute(text('''INSERT INTO pmvbry_establishments (establishment_id,manufacturing,gstin,bank_account_ref,option_exercised_at)
            VALUES (:e,false,:g,:b,:at) ON CONFLICT (establishment_id) DO UPDATE SET gstin=excluded.gstin,bank_account_ref=excluded.bank_account_ref,option_exercised_at=excluded.option_exercised_at'''), {'e': eid, 'g': body.gstin, 'b': body.bank_account_ref, 'at': datetime.now(UTC)})
        plan = await _employer_plan(session, eid, date.today().strftime('%Y-%m'))
        await add_event(session, producer='contribution-service', event_type='PmvbryOptionExercised.v1', aggregate_type='establishment', aggregate_id=eid, payload={'establishment_id': eid, 'gstin': body.gstin, 'baseline': plan['baseline']}, correlation_id=actor.correlation_id)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action='pmvbry.option', target_type='establishment', target_id=eid)
        return envelope({'establishment_id': eid, 'option_exercised_at': plan['option_exercised_at'], 'gstin': body.gstin, 'baseline': plan['baseline']})

async def _member_plans(session, subject, month):
    members = (await session.execute(text('SELECT account_link_id,establishment_id,uan FROM establishment_members WHERE member_subject=:s'), {'s': subject})).mappings().all()
    plans = []
    for member in members:
        rows = [r for r in await _rows(session, member['establishment_id'], month) if r['uan'] == member['uan']]
        literacy = (await session.execute(text('SELECT 1 FROM pmvbry_literacy WHERE uan=:u'), {'u': member['uan']})).first() is not None
        entries = part_a(rows, await _rules(session, month), month, literacy, await _payments(session, member['establishment_id']))
        plans.append({'member_id': member['account_link_id'], 'establishment_id': member['establishment_id'], 'uan': member['uan'], 'financial_literacy_completed': literacy, 'part_a': entries[0] if entries else None})
    return plans

@router.get('/api/v1/members/me/pmvbry')
async def member_view(actor: Actor = Depends(MEMBER)):
    async with sessions()() as session:
        return envelope({'memberships': await _member_plans(session, actor.subject, date.today().strftime('%Y-%m'))})

@router.post('/api/v1/members/me/pmvbry/financial-literacy-completions')
async def literacy_completion(actor: Actor = Depends(MEMBER)):
    async with sessions()() as session, session.begin():
        members = (await session.execute(text('SELECT uan FROM establishment_members WHERE member_subject=:s'), {'s': actor.subject})).scalars().all()
        if not members: raise Problem(404, '/problems/not-found', 'Member not found')
        for uan in set(members):
            await session.execute(text('INSERT INTO pmvbry_literacy (uan,completed_at,member_subject) VALUES (:u,:at,:s) ON CONFLICT (uan) DO NOTHING'), {'u': uan, 'at': datetime.now(UTC), 's': actor.subject})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action='pmvbry.literacy.completed', target_type='member', target_id=actor.subject)
        return envelope({'uans': sorted(set(members)), 'completed': True})

@router.get('/api/v1/ho/pmvbry/dashboard')
async def dashboard(actor: Actor = Depends(HO)):
    async with sessions()() as session:
        month = date.today().strftime('%Y-%m')
        ids = (await session.execute(text('SELECT establishment_id FROM pmvbry_establishments'))).scalars().all()
        records = []
        for eid in ids:
            cfg = await _est_data(session, eid)
            rows = await _rows(session, eid, month)
            payments = await _payments(session, eid)
            rules = await _rules(session, month)
            a = part_a(rows, rules, month, payments=payments)
            b = await _employer_plan(session, eid, month)
            records.append({'establishment_id': eid, 'industry_group': 'manufacturing' if cfg['manufacturing'] else 'other', 'part_a': a, 'part_b': b, 'payments': payments})
        buckets = {'0-15': 0, '16-45': 0, '>45': 0}
        states = {'PAID': 0, 'HELD': 0, 'DUE': 0}
        by_industry = {}
        for record in records:
            group = by_industry.setdefault(record['industry_group'], {'part_a_beneficiaries': 0, 'part_b_establishments': 0, 'paid_paise': 0, 'held_paise': 0, 'due_paise': 0})
            for member in record['part_a']:
                # a beneficiary has an instalment earned (paid, held or due); a first timer who does not qualify is not one
                group['part_a_beneficiaries'] += any(i['state'] in states for i in member['instalments'])
                for inst in member['instalments']:
                    if inst['state'] in states:
                        states[inst['state']] += 1
                        group[inst['state'].lower() + '_paise'] += inst['amount_paise']
                        if inst['state'] == 'DUE' and inst['due_month']:
                            age = (date.today() - month_end(inst['due_month'])).days
                            buckets['0-15' if age <= 15 else '16-45' if age <= 45 else '>45'] += 1
            if record['part_b']['crossing_month']: group['part_b_establishments'] += 1
            group['paid_paise'] += record['part_b']['totals']['paid_paise']
            group['due_paise'] += record['part_b']['totals']['payable_paise']
            latest_cycle = record['part_b']['cycles'][-1] if record['part_b']['cycles'] else None
            if latest_cycle and latest_cycle['state'] == 'DUE':
                states['DUE'] += 1
                age = (date.today() - month_end(latest_cycle['cycle_month'])).days
                buckets['0-15' if age <= 15 else '16-45' if age <= 45 else '>45'] += 1
        return envelope({'part_a_beneficiaries': sum(v['part_a_beneficiaries'] for v in by_industry.values()), 'part_b_establishments': sum(v['part_b_establishments'] for v in by_industry.values()), 'states': states, 'due_age_buckets': buckets, 'by_industry_group': by_industry, 'excluded_establishments': [{'establishment_id': r['establishment_id'], 'reason': r['part_b']['excluded_reason']} for r in records if r['part_b']['excluded_reason']]})

@router.get('/api/v1/ho/pmvbry/disbursement-runs/preview')
async def disbursement_preview(as_of_month: str = Query(pattern=r'^\d{4}-(0[1-9]|1[0-2])$'), actor: Actor = Depends(FINANCE)):
    """What a run for the month would pay, before the one-time code (which is bound to that amount)."""
    return await disbursement_run(RunInput(as_of_month=as_of_month, dry_run=True), actor, None)


@router.post('/api/v1/ho/pmvbry/disbursement-runs')
async def disbursement_run(body: RunInput, actor: Actor = Depends(FINANCE), idempotency_key: str | None = Header(default=None, alias='Idempotency-Key')):
    if not idempotency_key and not body.dry_run: raise Problem(400, '/problems/idempotency-key-required', 'Idempotency-Key is required')
    async with sessions()() as session, session.begin():
        digest = request_hash(body.model_dump())
        cached = await find_response(session, actor.subject, 'pmvbry-disbursement', idempotency_key, digest)
        if cached: return JSONResponse(envelope(cached.body['data']), status_code=cached.status)
        ids = (await session.execute(text('SELECT establishment_id FROM pmvbry_establishments'))).scalars().all()
        planned = []
        for eid in ids:
            rows = await _rows(session, eid, body.as_of_month)
            payments = await _payments(session, eid)
            rules = await _rules(session, body.as_of_month)
            literacy = set((await session.execute(text('SELECT uan FROM pmvbry_literacy'))).scalars().all())
            for uan in {r['uan'] for r in rows}:
                for member in part_a([r for r in rows if r['uan'] == uan], rules, body.as_of_month, uan in literacy, payments):
                    for inst in member['instalments']:
                        if inst['state'] in ('DUE', 'HELD') and inst['amount_paise'] > 0:
                            prior = next((p for p in payments if p['kind'] == 'A' and p['uan'] == uan and p['instalment'] == inst['instalment']), None)
                            if prior and prior['state'] == 'PAID': continue
                            if prior and prior['state'] == 'HELD' and inst['state'] == 'HELD': continue
                            planned.append({'kind': 'A', 'beneficiary': uan, 'establishment_id': eid, 'uan': uan, 'instalment': inst['instalment'], 'cycle_month': None, 'amount_paise': inst['amount_paise'], 'state': 'HELD' if inst['state'] == 'HELD' else 'PAID', 'prior': prior})
            b = await _employer_plan(session, eid, body.as_of_month)
            if b['option_exercised_at']:
                cycle = b['cycles'][-1] if b['cycles'] else None
                if cycle and cycle['state'] == 'DUE' and cycle['payable_paise'] > 0:
                    planned.append({'kind': 'B', 'beneficiary': eid, 'establishment_id': eid, 'uan': None, 'instalment': None, 'cycle_month': cycle['cycle_month'], 'amount_paise': cycle['payable_paise'], 'state': 'PAID', 'prior': None})
        amount = sum(p['amount_paise'] for p in planned if p['state'] == 'PAID')
        if body.dry_run:
            preview = [{k: v for k, v in p.items() if k != 'prior'} for p in planned]
            return JSONResponse(envelope({'as_of_month': body.as_of_month, 'dry_run': True, 'amount_paise': amount,
                                          'held_paise': sum(p['amount_paise'] for p in preview if p['state'] == 'HELD'), 'payments': preview}))
        require_step_up(actor, 'pmvbry-disbursement', body.as_of_month, None, amount)
        run_id = str(uuid.uuid4())
        public = []
        for item in planned:
            prior = item.pop('prior')
            if prior:
                await session.execute(text("UPDATE pmvbry_payments SET state='PAID',run_id=:r,mock_reference=:ref WHERE id=:id"), {'r': run_id, 'ref': 'MOCK-' + run_id[:8], 'id': prior['id']})
            else:
                payment_key = f"{item['kind']}:{item['establishment_id']}:{item['uan'] or item['cycle_month']}:{item['instalment'] or ''}"
                await session.execute(text('''INSERT INTO pmvbry_payments (id,payment_key,kind,beneficiary,establishment_id,uan,instalment,cycle_month,amount_paise,state,run_id,mock_reference)
                    VALUES (:id,:payment_key,:kind,:beneficiary,:establishment_id,:uan,:instalment,:cycle_month,:amount_paise,:state,:run_id,:mock_reference)'''), {**item, 'id': str(uuid.uuid4()), 'payment_key': payment_key, 'run_id': run_id, 'mock_reference': 'MOCK-' + run_id[:8] if item['state'] == 'PAID' else None})
            public.append(item)
        totals = {'part_a_paise': sum(p['amount_paise'] for p in public if p['kind'] == 'A' and p['state'] == 'PAID'), 'part_b_paise': sum(p['amount_paise'] for p in public if p['kind'] == 'B'), 'held_paise': sum(p['amount_paise'] for p in public if p['state'] == 'HELD')}
        result = {'run_id': run_id, 'as_of_month': body.as_of_month, **totals, 'payments': public}
        await add_event(session, producer='contribution-service', event_type='PmvbryIncentiveDisbursed.v1', aggregate_type='pmvbry_run', aggregate_id=run_id, payload={'run_id': run_id, 'as_of': body.as_of_month, **totals, 'payments': len(public)}, correlation_id=actor.correlation_id)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action='pmvbry.disbursement', target_type='pmvbry_run', target_id=run_id, detail=f'{amount} paise')
        wrapped = envelope(result)
        await store_response(session, actor.subject, 'pmvbry-disbursement', idempotency_key, digest, 200, wrapped)
        return JSONResponse(wrapped)
