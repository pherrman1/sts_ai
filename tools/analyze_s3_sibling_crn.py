#!/usr/bin/env python3
"""Analyze raw fixed-action Searcher3 sibling CRN diagnostic rows."""
import argparse, csv, json, math, random, statistics
from collections import defaultdict, Counter


def quantile(xs, q):
    ys = sorted(xs)
    if not ys: return math.nan
    p = (len(ys) - 1) * q; lo = int(p); hi = min(lo + 1, len(ys) - 1)
    return ys[lo] if hi == lo else ys[lo] + (ys[hi] - ys[lo]) * (p - lo)


def sign(x, tol=1e-12): return 1 if x > tol else (-1 if x < -tol else 0)


def analyze(rows, boot=2000, seed=20260824):
    samples = defaultdict(list); invalid = Counter(); meta = {}
    for r in rows:
        state, action, k, rep, mode = int(r['state_id']), int(r['action_id']), int(r['K']), int(r['replicate']), r['sampling_mode']
        key = state, action, k, rep, mode
        meta[state, action] = r.get('action_desc', str(action))
        if int(r['valid']): samples[key].append(float(r['value']))
        else: invalid[key] += 1
    refs = {}
    for (state, action, k, rep, mode), vals in samples.items():
        if mode == 'reference' and len(vals) == 128: refs[state, action] = statistics.fmean(vals)
    budgets = sorted({k for *_, k, _, mode in samples if mode in ('crn', 'independent')})
    report = {'invalid_attempts': sum(invalid.values()), 'reference_actions': len(refs), 'budgets': {}}
    rng = random.Random(seed)
    for k in budgets:
        states = sorted({s for s, _, kk, _, m in samples if kk == k and m in ('crn', 'independent')})
        pair_records = []
        best = Counter(); modal_scores = defaultdict(list); shifts = []
        for state in states:
            actions = sorted({a for s, a, kk, _, m in samples if s == state and kk == k and m == 'crn'})
            if any((state, a) not in refs for a in actions): continue
            ref_best = max(actions, key=lambda a: (refs[state, a], -a))
            batch_q = {m: {} for m in ('independent', 'crn')}
            for mode in batch_q:
                choices = []
                reps = sorted({rep for s, aa, kk, rep, m in samples
                               if s == state and aa in actions and kk == k and m == mode})
                for rep in reps:
                    q = {}
                    for a in actions:
                        vals = samples.get((state, a, k, rep, mode), [])
                        if len(vals) == k: q[a] = statistics.fmean(vals)
                    if len(q) == len(actions):
                        batch_q[mode][rep] = q
                        choice = max(actions, key=lambda a: (q[a], -a)); choices.append(choice)
                        best[mode, 'n'] += 1; best[mode, 'ok'] += choice == ref_best
                if choices:
                    modal_scores[mode].append(max(Counter(choices).values()) / len(choices))
            for i, a in enumerate(actions):
                for b in actions[i + 1:]:
                    ds = {}
                    for mode in batch_q:
                        ds[mode] = [q[a] - q[b] for _, q in sorted(batch_q[mode].items())]
                    if min(map(len, ds.values())) < 2: continue
                    vi = statistics.variance(ds['independent']); vc = statistics.variance(ds['crn'])
                    rec = {'state': state, 'a': a, 'b': b, 'vi': vi, 'vc': vc,
                           'ratio': None if vi <= 1e-12 else vc / vi}
                    refsign = sign(refs[state, a] - refs[state, b])
                    for mode in ds:
                        rec[mode + '_sign_n'] = len(ds[mode])
                        rec[mode + '_sign_err'] = sum(sign(x) != refsign for x in ds[mode])
                    pair_records.append(rec)
                    if vi > 1e-12:
                        shifts.append((statistics.fmean(ds['crn']) - statistics.fmean(ds['independent'])) / math.sqrt(vi))
        ratios = [r['ratio'] for r in pair_records if r['ratio'] is not None and math.isfinite(r['ratio'])]
        boots = []
        if ratios:
            for _ in range(boot): boots.append(statistics.median(rng.choices(ratios, k=len(ratios))))
        def err(mode):
            n = sum(r[mode + '_sign_n'] for r in pair_records); e = sum(r[mode + '_sign_err'] for r in pair_records)
            return {'errors': e, 'n': n, 'rate': e / n if n else math.nan}
        def agreement(mode):
            n = best[mode, 'n']; return best[mode, 'ok'] / n if n else math.nan
        ai, ac = agreement('independent'), agreement('crn')
        report['budgets'][str(k)] = {
            'usable_pairs': len(pair_records), 'degenerate_independent_pairs': sum(r['ratio'] is None for r in pair_records),
            'variance_ratio': {'median': statistics.median(ratios) if ratios else math.nan,
                               'q1': quantile(ratios, .25), 'q3': quantile(ratios, .75),
                               'fraction_below_1': sum(x < 1 for x in ratios) / len(ratios) if ratios else math.nan,
                               'bootstrap95': [quantile(boots, .025), quantile(boots, .975)]},
            'sign_error': {'independent': err('independent'), 'crn': err('crn')},
            'best_action_agreement': {'independent': ai, 'crn': ac, 'difference_pp': 100 * (ac - ai)},
            'best_action_stability': {m: statistics.fmean(modal_scores[m]) if modal_scores[m] else math.nan for m in ('independent', 'crn')},
            'standardized_mean_shift': statistics.fmean(shifts) if shifts else math.nan,
        }
    return report


def self_test():
    rows = []
    for mode in ('independent', 'crn'):
        for rep in range(32):
            for action in (0, 1):
                for sample in range(4):
                    noise = (rep - 15.5) * (1 if mode == 'independent' else .25)
                    rows.append({'state_id':'1','action_id':str(action),'K':'4','replicate':str(rep),
                                 'sampling_mode':mode,'valid':'1','value':str(10-action+noise*(1 if action==0 else -1))})
    for action in (0, 1):
        for sample in range(128):
            rows.append({'state_id':'1','action_id':str(action),'K':'128','replicate':'0',
                         'sampling_mode':'reference','valid':'1','value':str(10-action)})
    out = analyze(rows, boot=50)
    assert out['budgets']['4']['variance_ratio']['median'] < .1
    print('analyze_s3_sibling_crn self-test PASS')


def main():
    p = argparse.ArgumentParser(); p.add_argument('csv', nargs='?'); p.add_argument('--output')
    p.add_argument('--bootstrap', type=int, default=2000); p.add_argument('--self-test', action='store_true')
    a = p.parse_args()
    if a.self_test: self_test(); return
    if not a.csv: p.error('csv is required')
    with open(a.csv, newline='') as f: result = analyze(csv.DictReader(f), a.bootstrap)
    text = json.dumps(result, indent=2, sort_keys=True, allow_nan=True)
    if a.output:
        with open(a.output, 'w') as f: f.write(text + '\n')
    else: print(text)


if __name__ == '__main__': main()
