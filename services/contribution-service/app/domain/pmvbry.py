"""Pure PMVBRY calculations over paid ECR projections (amounts are paise)."""
from collections import defaultdict
from datetime import date, timedelta
import calendar


def next_month(month):
    year, number = map(int, month.split('-'))
    return f'{year + (number == 12):04d}-{number % 12 + 1:02d}'


def month_end(month):
    year, number = map(int, month.split('-'))
    return date(year, number, calendar.monthrange(year, number)[1])


def months(start, end):
    while start <= end:
        yield start
        start = next_month(start)


def first_completed(joined, rules):
    joined = date.fromisoformat(str(joined)[:10])
    month = joined.strftime('%Y-%m')
    return month if joined.day <= rules['joining_day'] else next_month(month)


def rounded_average(values):
    return (sum(values) * 2 + len(values)) // (2 * len(values)) if values else 0


def incentive(wage, rules):
    for slab in rules['slabs']:
        if slab['up_to_paise'] is None or wage <= slab['up_to_paise']:
            return min(wage * slab['percent'] // 100, slab['max_paise']) if 'percent' in slab else slab['amount_paise']
    return 0


def paying_slots(net_additional, month_index, first_paid, duration, eligible=True):
    if not eligible:
        return 0
    for slot in range(1, net_additional + 1):
        first_paid.setdefault(slot, month_index)
    return sum(1 for slot in range(1, net_additional + 1)
               if month_index - first_paid[slot] < duration)


def _history(rows):
    by_uan = defaultdict(dict)
    for row in rows:
        by_uan[row['uan']][row['wage_month']] = row
    return by_uan


def _continuous(by_month, start, count, as_of):
    period = list(months(start, as_of))[:count]
    return len(period) == count and all(m in by_month and by_month[m]['contribution_received'] for m in period)


def part_a(rows, rules, as_of, literacy=False, payments=()):
    by_uan = _history(rows)
    output = []
    paid = {(p['uan'], p['instalment']): p for p in payments if p['state'] == 'PAID'}
    for uan, history in by_uan.items():
        first_row = min(history.values(), key=lambda r: r['wage_month'])
        latest_row = max(history.values(), key=lambda r: r['wage_month'])
        joined = str(first_row['date_of_joining'])[:10]
        if first_row['kind'] != 'FIRST_TIMER' or not (rules['registration_from'] <= joined <= rules['registration_to']):
            continue
        start = first_completed(joined, rules)
        eligible = first_row['face_authenticated'] and first_row['gross_wage_paise'] <= rules['gross_wage_cap_paise']
        six = _continuous(history, start, rules['qualifying_months'], as_of)
        twelve = _continuous(history, start, 2 * rules['qualifying_months'], as_of)
        first_period = list(months(start, as_of))[:rules['qualifying_months']]
        second_period = list(months(start, as_of))[:2 * rules['qualifying_months']]
        first_amt = min(sum(history[m]['epf_wage_paise'] for m in first_period) // (2 * len(first_period)), rules['part_a_first_cap_paise']) if six else 0
        full_amt = min(sum(history[m]['epf_wage_paise'] for m in second_period) // len(second_period), rules['part_a_cap_paise']) if twelve else 0
        within = (int(second_period[-1][:4]) - int(joined[:4])) * 12 + int(second_period[-1][5:7]) - int(joined[5:7]) < rules['part_a_second_within_months'] if twelve else False
        instalments = []
        for number, amount, ready, due_month in ((1, first_amt, six, first_period[-1] if six else None), (2, max(0, full_amt-first_amt), twelve and within and literacy, second_period[-1] if twelve else None)):
            prior = paid.get((uan, number))
            if prior:
                state, missing, amount = 'PAID', [], int(prior['amount_paise'])
            elif not eligible:
                state, missing = 'NOT_YET', ['face authentication' if not first_row['face_authenticated'] else 'gross wage cap']
            elif not ready and latest_row['wage_month'] < as_of and not (six if number == 1 else twelve):
                state, missing = 'CEASED', ['left the establishment before qualifying: the incentive ceased']
            elif not ready:
                missing = []
                if not (six if number == 1 else twelve): missing.append(f'{rules["qualifying_months"] * number} continuous paid ECR months')
                if number == 2 and twelve and not within: missing.append('second instalment filing deadline')
                if number == 2 and not literacy: missing.append('financial literacy course')
                state = 'NOT_YET'
            else:
                state, missing = ('DUE', []) if latest_row['aadhaar_seeded_bank'] else ('HELD', ['Aadhaar-seeded bank account'])
            instalments.append({'instalment': number, 'amount_paise': amount, 'state': state, 'missing': missing, 'due_month': due_month,
                                'disbursal_deadline': (month_end(due_month) + timedelta(days=rules['disbursal_days'])).isoformat() if due_month else None})
        output.append({'uan': uan, 'first_completed_month': start, 'instalments': instalments})
    return output


def part_b(rows, rules, as_of, manufacturing=False, registered_on=None, excluded_reason=None, option_exercised=False, payments=()):
    rows = [r for r in rows if r['wage_month'] <= as_of]
    by_month = defaultdict(list)
    for row in rows: by_month[row['wage_month']].append(row)
    by_uan = _history(rows)
    baseline = rules['new_establishment_baseline'] if registered_on and str(registered_on)[:10] >= rules['registration_from'] else rounded_average([len(by_month[m]) for m in months(rules['baseline_from'], rules['baseline_to'])])
    threshold = rules['threshold_small'] if baseline < rules['threshold_baseline_split'] else rules['threshold_large']
    crossing = next((m for m in months(rules['registration_from'][:7], min(as_of, rules['registration_to'][:7])) if sum(bool(r['contribution_received']) for r in by_month[m]) >= baseline + threshold), None)
    if not crossing: return {'baseline': baseline, 'threshold': threshold, 'crossing_month': None, 'manufacturing': manufacturing, 'incentive_months': rules['manufacturing_incentive_months'] if manufacturing else rules['incentive_months'], 'months': [], 'cycles': [], 'excluded_reason': excluded_reason, 'totals': {'computed_paise': 0, 'paid_paise': 0, 'payable_paise': 0}}
    period = list(months(crossing, as_of))
    heads = {m: sum(bool(r['contribution_received']) for r in by_month[m]) for m in period}
    slot_start = {}
    results = []
    duration = rules['manufacturing_incentive_months'] if manufacturing else rules['incentive_months']
    for index, month in enumerate(period):
        annual = 2 * rules['qualifying_months']
        window = period[:rules['first_cycle_months']] if index < rules['first_cycle_months'] else period[:index+1] if index < annual else period[index-annual+1:index+1]
        eligible_est = month in by_month and len(window) >= rules['first_cycle_months'] and all(m in by_month for m in window) and rounded_average([heads[m] for m in window]) >= baseline + threshold
        eligible = []
        for row in by_month[month]:
            joined = str(row['date_of_joining'])[:10]
            joining_row = min(by_uan[row['uan']].values(), key=lambda r: r['wage_month'])
            if not row['contribution_received'] or row['kind'] not in ('FIRST_TIMER', 'REJOINEE') or not (rules['registration_from'] <= joined <= rules['registration_to']) or joining_row['gross_wage_paise'] > rules['gross_wage_cap_paise'] or row['kind'] == 'REJOINEE' and not row['aadhaar_authenticated']:
                continue
            start = first_completed(joined, rules)
            if month >= start and _continuous(by_uan[row['uan']], start, rules['qualifying_months'], as_of):
                eligible.append(incentive(by_uan[row['uan']][start]['epf_wage_paise'], rules))
        net = max(0, min(heads[month]-baseline, len(eligible)))
        slots = paying_slots(net, index, slot_start, duration, eligible_est and not excluded_reason)
        amount = sum(eligible) * slots // len(eligible) if eligible and slots else 0
        results.append({'wage_month': month, 'headcount': heads[month], 'eligible_employees': len(eligible), 'net_additional': net, 'eligible': eligible_est and not excluded_reason, 'slots_paid': slots, 'incentive_paise': amount, 'reason': excluded_reason if excluded_reason else None})
    paid_by_cycle = {p['cycle_month']: int(p['amount_paise']) for p in payments if p['state'] == 'PAID'}
    cycles = []
    paid_so_far = 0
    first_filed = len(period) >= rules['first_cycle_months'] and all(m in by_month for m in period[:rules['first_cycle_months']])
    for index, month in enumerate(period):
        if index < rules['first_cycle_months']-1: continue
        if not first_filed: continue
        if month not in by_month: continue
        computed = sum(r['incentive_paise'] for r in results[:index+1])
        payable = max(0, computed-paid_so_far)
        paid = paid_by_cycle.get(month, 0)
        cycles.append({'cycle_month': month, 'period_from': crossing if index == rules['first_cycle_months']-1 else month, 'period_to': month, 'computed_paise': computed, 'paid_paise': paid, 'payable_paise': max(0, payable-paid), 'state': 'PAID' if paid else 'DUE' if payable and option_exercised else 'OPTION_REQUIRED' if payable else 'NOT_YET',
                       'disbursal_deadline': (month_end(month) + timedelta(days=rules['disbursal_days'])).isoformat()})
        paid_so_far += paid
    for cycle in cycles:
        if cycle['state'] == 'DUE' and paid_so_far >= cycle['computed_paise']:
            cycle['state'] = 'PAID'
            cycle['payable_paise'] = 0
            cycle['covered_by_later_cycle'] = True
    return {'baseline': baseline, 'threshold': threshold, 'crossing_month': crossing, 'manufacturing': manufacturing, 'incentive_months': duration, 'months': results, 'cycles': cycles, 'excluded_reason': excluded_reason, 'totals': {'computed_paise': sum(x['incentive_paise'] for x in results), 'paid_paise': paid_so_far, 'payable_paise': cycles[-1]['payable_paise'] if cycles else 0}}
