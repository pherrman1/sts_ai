#!/usr/bin/env python3
"""#418 Stage 0 analysis: production CTM scored on both teacher arms.
Seed-level paired bootstrap (2000 reps, rng seed 418). Prints JSON + text."""
import csv, glob, json, math, random, sys
from collections import defaultdict
D = sys.argv[1] if len(sys.argv) > 1 else '/mnt/project-files/ctm-stage0/analysis/scores'
arms = {'exact10k': [], 'learned': []}
for f in glob.glob(D + '/*.csv'):
    arm = 'exact10k' if f.endswith('-exact10k.csv') else 'learned'
    arms[arm] += list(csv.DictReader(open(f)))
EPS = 1e-6
def fight(r):
    out = int(r['combat_outcome']) if r['combat_outcome'] else None
    if r['scored'] != '1' or out not in (1, 2): return None
    pd = min(max(float(r['p_death']), EPS), 1 - EPS)
    died = 1 if out == 2 else 0
    f = dict(seed=int(r['source_seed']), act=int(r['act']), room=r['room_class'], died=died,
             pd=pd, nll=-(math.log(pd) if died else math.log(1 - pd)), bias=died - pd)
    if not died:
        lp = float(r['log_p_post_hp'])
        f['hpnll'] = -max(lp, math.log(EPS)); f['hp_zero'] = lp == -math.inf
        f['hpbias'] = float(r['expected_win_hp']) - int(r['post_hp'])
    return f
F = {a: [x for x in map(fight, rows) if x] for a, rows in arms.items()}
census = {a: dict(rows=len(rows), scored=sum(r['scored'] == '1' for r in rows),
                  escapes=sum(r['combat_outcome'] == '0' for r in rows),
                  unsupported=dict(sorted(((k, sum(r['support_reason'] == k for r in rows))
                      for k in {r['support_reason'] for r in rows if r['scored'] != '1'})))) for a, rows in arms.items()}
seeds = sorted({x['seed'] for a in F for x in F[a]})
by = {a: defaultdict(list) for a in F}
for a in F:
    for x in F[a]: by[a][x['seed']].append(x)
def stat(fs, key, sel=lambda x: True):
    v = [x[key] for x in fs if sel(x) and key in x]
    return (sum(v) / len(v)) if v else float('nan'), len(v)
def boot(fn, reps=2000):
    rng = random.Random(418); vals = []
    for _ in range(reps):
        s = [rng.choice(seeds) for _ in seeds]
        v = fn({a: [x for sd in s for x in by[a][sd]] for a in F})
        if not math.isnan(v): vals.append(v)
    vals.sort(); return vals[int(.025 * len(vals))], vals[int(.975 * len(vals)) - 1]
def est(key, arm, sel=lambda x: True):
    pt, n = stat(F[arm], key, sel); lo, hi = boot(lambda G: stat(G[arm], key, sel)[0])
    return dict(mean=pt, ci=[lo, hi], n=n)
def delta(key, sel=lambda x: True):
    f = lambda G: stat(G['learned'], key, sel)[0] - stat(G['exact10k'], key, sel)[0]
    lo, hi = boot(f); return dict(mean=f(F), ci=[lo, hi])
R = dict(census=census, n_seeds=len(seeds))
for a in F:
    R[a] = dict(fights=len(F[a]), deaths=sum(x['died'] for x in F[a]),
                survival_nll=est('nll', a), survival_bias=est('bias', a),
                hp_nll=est('hpnll', a), hp_bias=est('hpbias', a),
                hp_zero_prob=sum(x.get('hp_zero', False) for x in F[a]),
                boss_survival_bias=est('bias', a, lambda x: x['room'] == 'BOSS'),
                boss_hp_bias=est('hpbias', a, lambda x: x['room'] == 'BOSS'))
    cells = {}
    for room in ('NORMAL', 'ELITE', 'BOSS'):
        for act in (1, 2, 3, 4):
            sel = lambda x, r=room, c=act: x['room'] == r and x['act'] == c
            n = sum(map(sel, F[a]))
            if n: cells[f'{room}_act{act}'] = dict(n=n, deaths=sum(x['died'] for x in F[a] if sel(x)),
                    pred_deaths=round(sum(x['pd'] for x in F[a] if sel(x)), 2),
                    survival_bias=est('bias', a, sel), hp_bias=est('hpbias', a, sel))
    R[a]['cells'] = cells
    bins = defaultdict(lambda: [0, 0, 0.0])
    for x in F[a]:
        if x['room'] != 'BOSS': continue
        b = min(int((1 - x['pd']) * 10), 9); bins[b][0] += 1; bins[b][1] += 1 - x['died']; bins[b][2] += 1 - x['pd']
    R[a]['boss_reliability'] = {f'{b/10:.1f}-{(b+1)/10:.1f}': dict(n=v[0], won=v[1], pred_won=round(v[2], 2)) for b, v in sorted(bins.items())}
R['delta_learned_minus_exact'] = dict(survival_nll=delta('nll'), hp_nll=delta('hpnll'),
                                      survival_bias=delta('bias'), hp_bias=delta('hpbias'))
d = R['delta_learned_minus_exact']; b = R['learned']['boss_survival_bias']['ci'][1]
R['decision'] = dict(survival_nll_ok=d['survival_nll']['ci'][1] < .01, hp_nll_ok=d['hp_nll']['ci'][1] < .05,
                     boss_bias_ok=b < .05)
R['decision']['path'] = 'A' if all(R['decision'].values()) else 'B'
R['decision']['boss_optimistic_both_arms'] = all(R[a]['boss_survival_bias']['ci'][0] > 0 for a in F)
json.dump(R, open("results.json", "w"), indent=1)
print(json.dumps(R, indent=1))
