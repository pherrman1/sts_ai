"""Value-gate check (c): simulated label-noise ceiling of the §577 sibling concordance on §644's common-seed
VALIDATION (ooc_sibling_crn_capture_20261022, 80 sources, 5,587 groups), offline, no seeds.

usage: sibling_ceiling.py EXTRACT ROWS_DIR SCALE_JSON OUT.json
EXTRACT: verify_campaign-style dir with out/units/<seed>/S-<seed>.sib.jsonl.gz (the 80 VALIDATION tars);
ROWS_DIR: `crn_analyze.py rows EXTRACT ROWS_DIR` output; SCALE_JSON: §715's results/scale.json (head concordances).

#644's analytic ceiling (0.80-0.87) plugs the OBSERVED sibling gaps into Phi(-|d|/se), and noise inflates observed
gaps, so it is optimistic. Here the true action values are estimated by shrinking each root's observed centred action
values toward the root mean (positive-part James-Stein per root: lambda = 1 - noise SS / observed SS, noise from the
32 common-seed repeat columns; and a pooled lambda per scope), then labels are re-simulated as truth + the mean of 32
repeat-residual columns resampled with replacement (keeps the common-seed correlation and the skew). The ceiling is
the mean §577 concordance of the truth against simulated labels (per root, per source, then over sources), 20
simulations. Variants: naive (truth = observed means; reproduces the analytic number), hidden-state term sigma_h^2 /
k_a per action (README: 0.00005 VALIDATION, 0.00009 TRAIN). Labels: raw targets and M0 targets (A20 default M0 on
non-terminal repeat endpoints, as §715).
Truth estimates: js = posterior-mean shrinkage lambda (too smooth: understates true gaps, so a LOW ceiling); vm =
variance-matched scaling sqrt(lambda), whose centred SS equals observed SS minus noise SS (method of moments, the
central estimate); naive = observed (HIGH). _pooled uses one lambda per scope (map / non-map). The hidden variants add
the hidden-state term to every action, which overstates the noise of deterministic siblings (README), so they are low.
"""
import gzip, json, math, sys
from collections import defaultdict
from pathlib import Path
import numpy as np

A_ = (-2.5384, -2.9227, -3.6523, -3.6334); B_ = 1.0535  # ADR-0057 M0, as sr_scale_eval.py
def m0(v, term, floor):
    if term: return v
    a = 1 if floor <= 16 else 2 if floor <= 33 else 3 if floor <= 50 else 4
    x = min(max(v, 1e-7), 1 - 1e-7); return 1 / (1 + math.exp(-(A_[a - 1] + B_ * math.log(x / (1 - x)))))

extract, rows_dir, scale_json, out = sys.argv[1:5]
rows = [json.loads(l) for l in open(Path(rows_dir) / 'rows.jsonl')]
# per-repeat M0 values, matched as sr_scale_eval.m0_targets (seed, decision, parent, action, raw repeat values)
want = defaultdict(list)
for i, r in enumerate(rows): want[(r['seed'], r['group'][1], r['group'][2], r['action'])].append(i)
m0rep = [None] * len(rows)
for seed in sorted({r['seed'] for r in rows}):
    for raw in map(json.loads, gzip.open(Path(extract) / 'out/units' / str(seed) / f'S-{seed}.sib.jsonl.gz', 'rt')):
        ids = want.get((seed, raw['decision'], raw['parent'], raw['action']))
        if not ids: continue
        reps = raw.get('extra', {}).get('repeats', []); vals = [float(v['value']) for v in reps]
        for i in ids:
            if m0rep[i] is None and rows[i]['repeats'] == vals:
                m0rep[i] = [m0(float(v['value']), v['terminal'], v['endFloor']) for v in reps]; break
assert all(x is not None for x in m0rep), sum(x is None for x in m0rep)

groups = defaultdict(list)
for i, r in enumerate(rows): groups[tuple(r['group'])].append(i)
G = []
for key, ids in groups.items():
    acts = defaultdict(list)
    for i in ids: acts[rows[i]['action']].append(i)
    if len(acts) < 2: continue
    seed = rows[ids[0]]['seed']; screen = rows[ids[0]]['screen']
    Vr = np.array([np.mean([rows[i]['repeats'] for i in a], 0) for a in acts.values()])
    Vm = np.array([np.mean([m0rep[i] for i in a], 0) for a in acts.values()])
    k = np.array([len(a) for a in acts.values()])
    G.append(dict(seed=seed, map=screen == 5, Vr=Vr, Vm=Vm, k=k))
print('groups', len(G), 'map', sum(g['map'] for g in G), flush=True)

def conc(mu, t):
    num, den = 0.0, 0
    for x in range(len(t)):
        for y in range(x):
            if abs(t[x] - t[y]) <= 1e-8: continue
            den += 1; num += .5 if mu[x] == mu[y] else float((mu[x] - mu[y]) * (t[x] - t[y]) > 0)
    return num / den if den else None

def lam_js(V):
    t = V.mean(1); tc = t - t.mean(); E = V - t[:, None]; R = V.shape[1]
    Ec = E - E.mean(0, keepdims=True)  # centred across actions per repeat (the part that moves differences)
    noise = (Ec ** 2).sum() / (R - 1) / R; obs = (tc ** 2).sum()
    return t, tc, E, noise, obs

rng = np.random.default_rng(20261101); S = 20
res = {}
for lab in ('Vr', 'Vm'):
    stats = [lam_js(g[lab]) for g in G]
    pooled = {}
    for scope in ('map', 'nonmap'):
        idx = [i for i, g in enumerate(G) if g['map'] == (scope == 'map')]
        pooled[scope] = max(0.0, 1 - sum(stats[i][3] for i in idx) / sum(stats[i][4] for i in idx))
    VARS = (('naive', 0), ('js', 0), ('pooled', 0), ('js_hidden_val', 5e-5), ('js_hidden_train', 9e-5),
            ('vm', 0), ('vm_pooled', 0), ('vm_hidden_val', 5e-5), ('vm_hidden_train', 9e-5))
    for variant, s2h in VARS:
        per = defaultdict(lambda: defaultdict(list))
        for gi, (g, (t, tc, E, noise, obs)) in enumerate(zip(G, stats)):
            sc_ = 'map' if g['map'] else 'nonmap'
            if variant == 'naive': lam = 1.0
            elif variant == 'pooled': lam = pooled[sc_]
            elif variant == 'vm_pooled': lam = math.sqrt(pooled[sc_])
            elif variant.startswith('vm'): lam = math.sqrt(max(0.0, 1 - noise / obs)) if obs > 0 else 0.0
            else: lam = max(0.0, 1 - noise / obs) if obs > 0 else 0.0
            mu = t.mean() + lam * tc; R = E.shape[1]; cs = []
            for _ in range(S):
                cols = rng.integers(0, R, R); ts = mu + E[:, cols].mean(1)
                if s2h: ts = ts + rng.normal(0, np.sqrt(s2h / g['k']))
                c = conc(mu, ts)
                if c is not None: cs.append(c)
            if cs:
                for scope in ('all', 'map' if g['map'] else 'nonmap'): per[scope][g['seed']].append(np.mean(cs))
        for scope in ('all', 'map', 'nonmap'):
            src = [np.mean(v) for v in per[scope].values()]
            res.setdefault(f'{scope}:{"target" if lab == "Vr" else "target_m0"}', {})[variant] = {'ceiling': float(np.mean(src)), 'sources': len(src)}
    res[f'pooled_lambda:{lab}'] = pooled
    res[f'js_lambda_mean:{lab}'] = float(np.mean([max(0.0, 1 - s[3] / s[4]) if s[4] > 0 else 0 for s in stats]))
# best head / blend per scope and label set from §715
sc = json.load(open(scale_json))
for key in [k for k in res if ':' in k and not k.startswith(('pooled', 'js_'))]:
    heads = sc[key]; best = max(heads, key=lambda h: heads[h]['conc'])
    res[key]['best_evaluator'] = {'name': best, 'conc': heads[best]['conc']}
    res[key]['x2b_m0'] = heads['x2b_m0']['conc']
    for v in [x for x in res[key] if isinstance(res[key][x], dict) and 'ceiling' in res[key][x]]:
        res[key][v]['gap_best'] = res[key][v]['ceiling'] - heads[best]['conc']
print(json.dumps(res, indent=1))
json.dump(res, open(out, 'w'), indent=1)
