#!/usr/bin/env python3
"""§443 Stage 0: production CTM at A20, ascension as is vs clamped to 0, against observed Silver outcomes.
usage: analyze.py SCORES_ASC20.csv SCORES_ASC0.csv OUT.json"""
import csv, json, math, sys, collections
import random

def load(path):
    out = {}
    for r in csv.DictReader(open(path)):
        out[(r['source_seed'], r['fight_idx'])] = r
    return out

a, b = load(sys.argv[1]), load(sys.argv[2])
keys = [k for k in a if k in b and a[k]['run_valid'] == '1' and a[k]['combat_outcome'] in ('1', '2')
        and a[k]['scored'] == '1' and b[k]['scored'] == '1']
support = {'rows': len(a), 'scored_asc20': sum(r['scored'] == '1' for r in a.values()),
           'scored_asc0': sum(r['scored'] == '1' for r in b.values()),
           'unsupported_reasons_asc0': collections.Counter(r['support_reason'] for r in b.values() if r['scored'] != '1')}

def stats(rows_by_key, ks):
    eps = 1e-6
    died = [rows_by_key[k]['combat_outcome'] == '2' for k in ks]
    pd = [min(max(float(rows_by_key[k]['p_death']), eps), 1 - eps) for k in ks]
    nll = sum(-math.log(p if d else 1 - p) for p, d in zip(pd, died)) / max(1, len(ks))
    win = [k for k, d in zip(ks, died) if not d]
    hp_err = [float(rows_by_key[k]['expected_win_hp']) - float(rows_by_key[k]['post_hp']) for k in win]
    lp = [float(rows_by_key[k]['log_p_post_hp']) for k in win if rows_by_key[k]['log_p_post_hp'] not in ('', '-inf')]
    ninf = sum(rows_by_key[k]['log_p_post_hp'] == '-inf' for k in win)
    return {'n': len(ks), 'observed_death': sum(died) / max(1, len(ks)), 'predicted_death': sum(pd) / max(1, len(ks)),
            'death_bias': (sum(pd) - sum(died)) / max(1, len(ks)),  # predicted - observed death rate
            'survival_nll': nll, 'win_hp_bias': sum(hp_err) / max(1, len(hp_err)),
            'win_hp_mae': sum(map(abs, hp_err)) / max(1, len(hp_err)),
            'hp_nll': -sum(lp) / max(1, len(lp)), 'hp_rows_neg_inf': ninf}

def boot_bias(rows_by_key, ks, reps=2000, seed=443):
    by = collections.defaultdict(list)
    for k in ks: by[k[0]].append(k)
    seeds = list(by); rng = random.Random(seed); vals = []
    for _ in range(reps):
        sample = [k for s in (rng.choice(seeds) for _ in seeds) for k in by[s]]
        vals.append(stats(rows_by_key, sample)['death_bias'])
    vals.sort(); return [vals[int(.025 * reps)], vals[int(.975 * reps)]]

groups = collections.defaultdict(list)
for k in keys:
    r = a[k]
    groups['all'].append(k)
    groups[f"act{r['act']}"].append(k)
    groups[r['room_class']].append(k)
out = {'support': support, 'groups': {}}
for g, ks in sorted(groups.items()):
    out['groups'][g] = {'asc20': stats(a, ks), 'asc0_clamped': stats(b, ks)}
out['death_bias_ci95'] = {'asc20': boot_bias(a, groups['all']), 'asc0_clamped': boot_bias(b, groups['all'])}
json.dump(out, open(sys.argv[3], 'w'), indent=1, default=dict)
for g, v in out['groups'].items():
    print(g, v['asc20']['n'], 'obs_death %.3f' % v['asc20']['observed_death'],
          '| asc20 pd %.3f nll %.3f hpbias %+.1f' % (v['asc20']['predicted_death'], v['asc20']['survival_nll'], v['asc20']['win_hp_bias']),
          '| asc0 pd %.3f nll %.3f hpbias %+.1f mae %.1f' % (v['asc0_clamped']['predicted_death'], v['asc0_clamped']['survival_nll'],
                                                        v['asc0_clamped']['win_hp_bias'], v['asc0_clamped']['win_hp_mae']))
print('bias CI', out['death_bias_ci95']); print(support)
