"""Additional descriptive analyses for the JSS revision; standard library only."""
import argparse
import collections
import datetime as dt
import json
import math
from pathlib import Path

STEPS = ['build', 'validation', 'idempotent_build', 'traversal', 'capture']
KINDS = ['current', 'visual_self_reworks', 'technical_self_reworks', 'rollovers']


def main(data, output):
    read = lambda name: json.loads((data / (name + '.json')).read_text(encoding='utf-8'))
    tickets, states, archives, evidence = map(read, ['tickets', 'states', 'archives', 'evidence_observations'])
    tmap = {t['request_id']: t for t in tickets}
    historic = [e for e in evidence if e['origin'] != 'current' and e['step'] in STEPS]
    joint = [[0, 0], [0, 0]]
    for e in historic:
        assert not e['exists'] or e['hash_match']
        joint[0 if e['hash_match'] else 1][0 if e['broker_request_id'] in tmap else 1] += 1
    assert sum(map(sum, joint)) == 1876
    stages = {step: {kind: {'joined': 0, 'unmatched': 0, 'lease_h': 0.0} for kind in KINDS} for step in STEPS}
    seen = set()
    for state in states:
        for step in STEPS:
            a = state['attestations'].get(step)
            if not a:
                continue
            request = a['broker_request_id']
            assert request not in seen
            seen.add(request)
            cell = stages[step][state['origin']]
            if request in tmap:
                t = tmap[request]
                assert t['status'] == 'DONE'
                cell['joined'] += 1
                cell['lease_h'] += (t['finished_at'] - t['started_at']) / 3600
            else:
                cell['unmatched'] += 1
    per_poi = collections.defaultdict(collections.Counter)
    for a in archives:
        per_poi[a['poi_id']][a['kind']] += 1
    ranked = sorted(per_poi, key=lambda p: (-sum(per_poi[p].values()), p))
    concentration = [{'poi_id': p, 'counts': dict(per_poi[p]), 'total': sum(per_poi[p].values())} for p in ranked]
    by_day = collections.defaultdict(list)
    for t in tickets:
        by_day[dt.datetime.fromtimestamp(t['created_at'], dt.timezone.utc).date().isoformat()].append(t)
    first, last = map(dt.date.fromisoformat, [min(by_day), max(by_day)])
    daily = []
    for i in range((last - first).days + 1):
        day = (first + dt.timedelta(days=i)).isoformat()
        rows = by_day.get(day, [])
        waits = sorted(t['started_at'] - t['accepted_at'] for t in rows if t['started_at'] is not None)
        daily.append({'date': day, 'requests': len(rows), 'started': len(waits),
                      'by_app': dict(collections.Counter(t['app'] for t in rows)),
                      'wait_p90_s': waits[math.floor(.9 * (len(waits) - 1))] if waits else None})
    top5 = [c['poi_id'] for c in concentration[:5]]
    current = {s['poi_id']: s for s in states if s['origin'] == 'current'}
    histories = []
    for p in top5:
        observed = {s['assignment_attempt']: s['origin'] for s in states if s['poi_id'] == p}
        end = current[p]['assignment_attempt']
        histories.append({'poi_id': p, 'current_attempt': end,
                          'slots': [observed.get(i, 'unobserved') for i in range(1, end + 1)]})
    results = {'historical_technical_joint': {'rows': ['file_matches', 'file_missing'],
               'columns': ['broker_joined', 'broker_unmatched'], 'counts': joint, 'denominator': len(historic)},
               'stage_cohorts': stages, 'archive_concentration': concentration,
               'daily': daily, 'top5_attempt_histories': histories,
               'definitions': {'daily_date': 'UTC request creation date; P90 among requests that started',
                 'empty_day': 'No requests in retained snapshot, not verified absence of production',
                 'joint': 'Historical technical attestations only; excludes one historical Fresh QA record',
                 'history_axis': 'Numbered attempts, not time; origin labels indicate stored outgoing transition',
                 'stage_cost': 'Joined successful attested requests only; unmatched duration unknown'}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'joint': joint, 'top5': top5,
                      'top10_count': sum(c['total'] for c in concentration[:10]),
                      'empty_days': [d['date'] for d in daily if not d['requests']],
                      'stage_counts': {s: [sum(stages[s][k][m] for k in KINDS) for m in ['joined', 'unmatched']] for s in STEPS}}, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--data', type=Path, default=Path(__file__).parent / 'data')
    p.add_argument('--out', type=Path, default=Path(__file__).parent / 'expected_results/extended_results.json')
    a = p.parse_args()
    main(a.data, a.out)
