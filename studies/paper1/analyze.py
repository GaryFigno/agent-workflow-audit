"""Recompute the retrospective paper's descriptive results from frozen JSON.

Uses Python standard library only. No network or production filesystem access.
"""
import argparse
import collections
import datetime as dt
import hashlib
import json
import math
import pathlib
import statistics

STEPS = ['build', 'validation', 'idempotent_build', 'traversal', 'capture']
KINDS = ['current', 'visual_self_reworks', 'technical_self_reworks', 'rollovers']

def counts(values):
    return dict(sorted(collections.Counter(str(v) for v in values).items()))

def stats(values):
    values = sorted(values)
    n = len(values)
    if not n:
        return {'n': 0}
    total = sum(values)
    top = max(1, math.ceil(n * .1))
    return {'n': n, 'min_s': min(values), 'median_s': statistics.median(values),
            'p90_s': values[math.floor(.9 * (n - 1))],
            'p95_s': values[math.floor(.95 * (n - 1))],
            'p99_s': values[math.floor(.99 * (n - 1))],
            'max_s': max(values), 'sum_h': total / 3600,
            'top_decile_sum_share': sum(values[-top:]) / total if total else None,
            'over_60s': sum(x > 60 for x in values),
            'over_300s': sum(x > 300 for x in values),
            'over_600s': sum(x > 600 for x in values)}

def ticket_summary(rows):
    started = [x for x in rows if x['started_at'] is not None]
    finished = [x for x in started if x['finished_at'] is not None]
    return {'n': len(rows), 'status': counts(x['status'] for x in rows),
            'wait': stats([x['started_at'] - x['accepted_at'] for x in started]),
            'lease': stats([x['finished_at'] - x['started_at'] for x in finished]),
            'wait_exceeds_lease': sum(x['started_at'] - x['accepted_at'] >
                                      x['finished_at'] - x['started_at'] for x in finished)}

def main(data, output):
    def read(name):
        return json.loads((data / (name + '.json')).read_text(encoding='utf-8'))
    tickets, states, archives, evidence, catalog = map(read,
        ['tickets', 'states', 'archives', 'evidence_observations', 'catalog'])
    current = [x for x in states if x['origin'] == 'current']
    tmap = {x['request_id']: x for x in tickets}
    smap = {(x['poi_id'], x['assignment_attempt'], x['assignment_epoch']): x for x in states}
    attemptmap = {(x['poi_id'], x['assignment_attempt']): x for x in states}
    cmap = {x['poi_id']: x for x in current}
    assert len(tmap) == len(tickets)
    assert len(smap) == len(states)
    assert len(attemptmap) == len(states)
    assert all(x['accepted_at'] is not None for x in tickets)
    assert all(x['accepted_at'] >= x['created_at'] for x in tickets)
    assert all(x['started_at'] >= x['accepted_at'] for x in tickets if x['started_at'] is not None)
    assert all(x['finished_at'] >= x['started_at'] for x in tickets if x['started_at'] is not None and x['finished_at'] is not None)
    assert all(x['filename_hash_match'] for x in archives)
    result = {'units': {'tickets': len(tickets), 'assignment_states': len(states),
                        'current_pois': len(current), 'archives': len(archives)},
              'broker': {'all': ticket_summary(tickets),
                         'by_app': {a: ticket_summary([x for x in tickets if x['app'] == a]) for a in sorted({x['app'] for x in tickets})},
                         'by_mode': {a: ticket_summary([x for x in tickets if x['mode'] == a]) for a in sorted({x['mode'] for x in tickets})},
                         'by_status': {a: ticket_summary([x for x in tickets if x['status'] == a]) for a in sorted({x['status'] for x in tickets})}}}
    created = [x['created_at'] for x in tickets]
    result['broker']['created_range_utc'] = [dt.datetime.fromtimestamp(v, dt.timezone.utc).isoformat() for v in [min(created), max(created)]]
    days = collections.defaultdict(list)
    for x in tickets:
        days[dt.datetime.fromtimestamp(x['created_at'], dt.timezone.utc).date().isoformat()].append(x)
    result['broker']['by_day'] = {k: ticket_summary(v) for k, v in sorted(days.items())}
    result['archives'] = {}
    for kind in KINDS[1:]:
        rows = [x for x in archives if x['kind'] == kind]
        post = []
        for row in rows:
            # Epoch is revised by subsequent gate transitions within the same attempt.
            dest = attemptmap.get((row['poi_id'], row['attempt'] + 1))
            post.append({'poi_id': row['poi_id'], 'attempt': row['attempt'],
                         'found': dest is not None,
                         'complete': all(dest['attestations'].get(s) for s in STEPS) if dest else None})
        result['archives'][kind] = {
            'n': len(rows), 'unique_pois': len({x['poi_id'] for x in rows}),
            'complete_chains': sum(x['complete_chain'] for x in rows),
            'gates': counts(x['gate'] for x in rows), 'severity': counts(x['severity'] for x in rows),
            'rework_evidence_match': sum(x.get('evidence_hash_match') is True for x in rows),
            'rework_evidence_drift': sum(x.get('evidence_hash_match') is False for x in rows),
            'rework_evidence_missing': sum(x.get('evidence_exists') is False for x in rows),
            'invalid_chain_recovery_present': sum(x['invalid_chain_recovery_present'] for x in rows),
            'invalid_chain_recovery_with_issues': sum(bool(x['invalid_chain_issues']) for x in rows),
            'invalid_chain_codes': counts(code for x in rows for code in x['invalid_chain_issues']),
            'next_state_observed': sum(x['found'] for x in post),
            'next_state_complete': sum(x['complete'] is True for x in post),
            'by_poi': counts(x['poi_id'] for x in rows)}
    result['archives']['source_updated_range_utc'] = [min(x['source_updated_utc'] for x in archives), max(x['source_updated_utc'] for x in archives)]
    result['archives']['unique_pois'] = len({x['poi_id'] for x in archives})
    result['archives']['top5_share'] = sum(v for _, v in collections.Counter(x['poi_id'] for x in archives).most_common(5)) / len(archives)
    result['evidence'] = {}
    for kind in KINDS:
        rows = [x for x in evidence if x['origin'] == kind]
        technical = [x for x in rows if x['step'] in STEPS]
        joined = [x for x in technical if x['broker_request_id'] in tmap]
        result['evidence'][kind] = {'records': len(rows), 'technical': len(technical),
            'exists': sum(x['exists'] for x in rows), 'hash_matches': sum(x['hash_match'] for x in rows),
            'missing': sum(not x['exists'] for x in rows),
            'digest_drift': sum(x['exists'] and not x['hash_match'] for x in rows),
            'identity_mismatches': sum(bool(x['identity_mismatch_fields']) for x in rows),
            'broker_joined': len(joined),
            'broker_status': counts(tmap[x['broker_request_id']]['status'] for x in joined),
            'missing_by_poi': counts(x['poi_id'] for x in rows if not x['exists']),
            'steps': counts(x['step'] for x in rows)}
    # Resource time belongs to each unique broker ticket once, regardless of reference count.
    result['chain_resource'] = {}
    for kind in KINDS + ['all']:
        group = [x for x in states if kind == 'all' or x['origin'] == kind]
        ids = {a['broker_request_id'] for x in group for s, a in x['attestations'].items() if s in STEPS and a.get('broker_request_id')}
        linked = [tmap[i] for i in sorted(ids) if i in tmap]
        result['chain_resource'][kind] = {'distinct_referenced_tickets': len(ids),
                                          'unmatched': len(ids) - len(linked),
                                          **ticket_summary(linked)}
    result['chain_resource']['by_step'] = {}
    for step in STEPS:
        ids = {x['attestations'][step]['broker_request_id'] for x in states if x['attestations'].get(step)}
        result['chain_resource']['by_step'][step] = ticket_summary([tmap[i] for i in sorted(ids) if i in tmap])
    current_ids = {a['broker_request_id'] for x in current for s,a in x['attestations'].items() if s in STEPS}
    archive_ids = {a['broker_request_id'] for x in states if x['origin'] != 'current' for s,a in x['attestations'].items() if s in STEPS}
    result['chain_resource']['overlap_current_archive'] = len(current_ids & archive_ids)
    failure_ids = {x['native_broker_request_id'] for x in archives
                   if x['kind'] == 'technical_self_reworks' and x['native_broker_request_id']}
    result['technical_failure_tickets'] = {
        'distinct_referenced': len(failure_ids),
        'unmatched': len(failure_ids - set(tmap)),
        'overlap_with_attested_tickets': len(failure_ids & (current_ids | archive_ids)),
        **ticket_summary([tmap[i] for i in sorted(failure_ids) if i in tmap])}
    result['current'] = {'gates': counts(x['current_gate'] for x in current),
                         'status': counts(x['status'] for x in current),
                         'complete_chains': sum(all(x['attestations'].get(s) for s in STEPS) for x in current),
                         'founder': sum(bool(x['attestations'].get('founder')) for x in current),
                         'fresh_qa': sum(bool(x['attestations'].get('fresh_qa')) for x in current),
                         'unique_nonnull_releases': len({x['factory_release_id'] for x in current if x['factory_release_id']})}
    result['catalog'] = {'n': len(catalog), 'projects': counts(x['project'] for x in catalog),
                         'fixed_all': sum(x['fixed'] for x in catalog),
                         'cinderage_n': sum(x['project'] == 'Cinderage' for x in catalog),
                         'cinderage_fixed': sum(x['fixed'] and x['project'] == 'Cinderage' for x in catalog),
                         'capture_path_matches': sum(x['capture_path_text_match'] is True for x in catalog),
                         'capture_path_mismatches': sum(x['capture_path_text_match'] is False for x in catalog),
                         'capture_path_unavailable': sum(x['capture_path_text_match'] is None for x in catalog),
                         'images_references': sum(x['images_n'] for x in catalog)}
    matched = [x for x in catalog if x['project'] == 'Cinderage' and x['poi_id'] in cmap]
    result['catalog']['cinderage_assignment_matched'] = len(matched)
    result['catalog']['cinderage_cross_table'] = counts((cmap[x['poi_id']]['current_gate'], x['fixed']) for x in matched)
    result['catalog']['fixed_with_complete_chain'] = sum(x['fixed'] and all(cmap[x['poi_id']]['attestations'].get(s) for s in STEPS) for x in matched)
    result['catalog']['fixed_capture_matches'] = sum(x['fixed'] and x['capture_path_text_match'] is True for x in matched)
    result['coverage'] = {'sum_current_attempt_numbers': sum(x['assignment_attempt'] for x in current),
                           'observed_poi_attempt_pairs': len({(x['poi_id'], x['assignment_attempt']) for x in states}),
                           'missing_intermediate_attempt_numbers': sum(len(set(range(1,x['assignment_attempt']+1)) - {s['assignment_attempt'] for s in states if s['poi_id']==x['poi_id']}) for x in current)}
    result['integrity_checks'] = {'unique_ticket_ids': True, 'unique_state_identities': True,
                                   'nonnegative_time_intervals': True, 'archive_filename_hashes_match': True}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    # A per-POI reconstruction includes all observed attempts, including missing files.
    pois = []
    for poi, latest in sorted(cmap.items()):
        observed = sorted([s for s in states if s['poi_id'] == poi], key=lambda s: (s['assignment_attempt'], s['assignment_epoch']))
        rows = [x for x in archives if x['poi_id'] == poi]
        pois.append({'poi_id': poi, 'current_attempt': latest['assignment_attempt'],
                     'observed_attempts': [s['assignment_attempt'] for s in observed],
                     'missing_attempt_numbers': sorted(set(range(1, latest['assignment_attempt']+1)) - {s['assignment_attempt'] for s in observed}),
                     'archived_actions': counts(x['kind'] for x in rows),
                     'states': [{'attempt': s['assignment_attempt'], 'epoch': s['assignment_epoch'], 'origin': s['origin'], 'gate': s['current_gate'], 'updated_utc': s['updated_utc'], 'steps': list(s['attestations'])} for s in observed]})
    (output / 'poi_histories.json').write_text(json.dumps(pois, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k,v in result.items() if k not in ['broker','archives','chain_resource']}, indent=2))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parent / 'data')
    parser.add_argument('--out', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parent / 'results')
    args = parser.parse_args()
    main(args.data, args.out)
