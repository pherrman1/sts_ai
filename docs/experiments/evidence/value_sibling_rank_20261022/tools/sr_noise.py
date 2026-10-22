"""Noise-aware sibling concordance on round-2 VALIDATION (value-head research, 2026-10-22; exploratory).

usage: sr_noise.py R2 OUT.json NAME=WORKDIR ...   (WORKDIR holds r2-NAME-out.jsonl from value_leaf_check.py check)

Rows are read in value_leaf_check.load_round2's order (same acceptance), keeping each row's 64 rollout values.
- Label noise: each row's target is a 64-rollout mean; its predicted SE is sd(rollouts) / 8. Rows of one action
  with identical X2-B value are the same public state; their between-row variance calibrates an inflation factor f
  (observed / predicted variance), because hidden state (RNG counters) varies between captures.
- Per group, action target = mean of its rows, SE^2 = f^2 * mean(SE_row^2) / rows. A pair's label order is wrong with
  probability p = Phi(-|dt| / sqrt(SE_i^2 + SE_j^2)).
- Metrics per evaluator (aggregated as §577: per-source mean of group means, then over sources):
  conc (all pairs, = §577) and conc on pairs with |dt| >= 1 and 2 pair-SEs; plus the noise-corrected concordance
  sum(agree - p) / sum(1 - 2p), pooled over all groups with each group's pairs weighted 1 / pairs (a perfect evaluator
  scores 1 if the noise model holds).
- Ceiling: expected §577 concordance of a perfect evaluator, sum(1 - p) / pairs per group, same aggregation.
"""
import glob, json, math, os, sys
from collections import defaultdict
import numpy as np

dr2, out = sys.argv[1:3]
heads = dict(a.split('=', 1) for a in sys.argv[3:])
rows = []
for split in ('train', 'validation'):
    for path in sorted(glob.glob(f'{dr2}/{split}/seed-*.sib.jsonl')):
        seed = int(path.split('seed-')[-1].split('.')[0])
        last = json.loads(open(path.replace('.sib.jsonl', '.states.jsonl')).readlines()[-1])
        if last.get('type') != 'outcome' or not last.get('complete') or not last.get('integrityPassed'):
            continue
        accepted, bad = [], set()
        for raw in map(json.loads, open(path)):
            e, group = raw.get('extra', {}), (seed, raw['decision'], raw['parent'])
            reps = e.get('repeats', [])
            if (len(reps) != 64 or 'record' not in e or 'x2b' not in e or e.get('rolloutPolicy') != 'heart1'
                    or e.get('recordSchema') != 'heart1-public-record-v2'):
                bad.add(group)
                continue
            v = np.array([r['value'] for r in reps], dtype=float)
            accepted.append({'seed': seed, 'split': split, 'group': group, 'action': raw['action'],
                             'target': float(v.mean()), 'se2': float(v.var() / 64), 'x2b': float(e['x2b'])})
        rows += [r for r in accepted if r['group'] not in bad]
sig = lambda z: 1 / (1 + np.exp(-z))
for name, work in heads.items():
    vals = [json.loads(line)['value'] for line in open(f'{work}/r2-{name}-out.jsonl')]
    assert len(vals) == len(rows), (name, len(vals), len(rows))
    for r, v in zip(rows, vals):
        r[name] = float(sig(v))
        r[name + '@0.15'] = float(sig(0.85 * math.log(min(max(r['x2b'], 1e-7), 1 - 1e-7) / (1 - min(max(r['x2b'], 1e-7), 1 - 1e-7))) + 0.15 * v))

groups = defaultdict(list)
for i, r in enumerate(rows):
    groups[r['group']].append(i)
groups = [g for g in groups.values() if len({rows[i]['action'] for i in g}) >= 2]

# inflation factor from same-state rows (same group, action and X2-B value)
obs, pred = [], []
for g in groups:
    same = defaultdict(list)
    for i in g:
        same[(rows[i]['action'], rows[i]['x2b'])].append(i)
    for ids in same.values():
        if len(ids) >= 2:
            t = np.array([rows[i]['target'] for i in ids])
            obs.append(t.var(ddof=1)); pred.append(np.mean([rows[i]['se2'] for i in ids]))
f2 = float(np.mean(obs) / np.mean(pred))
print(f"same-state sets {len(obs)}: observed between-row var {np.mean(obs):.6f}, predicted {np.mean(pred):.6f}, f = {math.sqrt(f2):.3f}")

Phi = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
keys = ['x2b', *heads, *[h + '@0.15' for h in heads]]


def metrics(gs):
    per = defaultdict(lambda: defaultdict(list)); num = defaultdict(float); den = 0.0
    for ids in gs:
        acts = defaultdict(list)
        for i in ids:
            acts[rows[i]['action']].append(i)
        A = list(acts.values())
        t = [np.mean([rows[i]['target'] for i in a]) for a in A]
        se2 = [f2 * np.mean([rows[i]['se2'] for i in a]) / len(a) for a in A]
        pairs = [(x, y, abs(t[x] - t[y]), math.sqrt(se2[x] + se2[y])) for x in range(len(A)) for y in range(x)
                 if abs(t[x] - t[y]) > 1e-8]
        if not pairs:
            continue
        src = per[rows[ids[0]]['seed']]
        pf = [Phi(-d / s) if s > 0 else 0.0 for _, _, d, s in pairs]
        src['ceiling'].append(float(np.mean([1 - p for p in pf])))
        for k in keys:
            p = [np.mean([rows[i][k] for i in a]) for a in A]
            agree = [.5 if p[x] == p[y] else float((p[x] - p[y]) * (t[x] - t[y]) > 0) for x, y, _, _ in pairs]
            src[k + ':conc'].append(float(np.mean(agree)))
            for z in (1, 2):
                sel = [a for a, (_, _, d, s) in zip(agree, pairs) if d >= z * s]
                if sel:
                    src[f'{k}:conc{z}se'].append(float(np.mean(sel)))
            num[k] += (sum(agree) - sum(pf)) / len(pairs)
        den += sum(1 - 2 * q for q in pf) / len(pairs)
    agg = defaultdict(list)
    for d in per.values():
        for m, v in d.items():
            agg[m].append(float(np.mean(v)))
    out = {m: {'mean': float(np.mean(v)), 'sources': len(v)} for m, v in sorted(agg.items())}
    for k in keys:
        out[k + ':corrected'] = {'mean': num[k] / den, 'sources': len(per)}
    return out


res = {'inflation_f': math.sqrt(f2)}
for split in ('validation',):
    gs = [g for g in groups if rows[g[0]]['split'] == split]
    m = metrics(gs)
    res[split] = m
    print(f"{split}: {len(gs)} groups; ceiling (perfect evaluator, all pairs) {m['ceiling']['mean']:.4f}")
    for k in keys:
        print(f"  {k:14s} conc {m[k + ':conc']['mean']:.4f}  |dt|>=1SE {m[k + ':conc1se']['mean']:.4f} "
              f"({m[k + ':conc1se']['sources']} src)  >=2SE {m[k + ':conc2se']['mean']:.4f} "
              f"({m[k + ':conc2se']['sources']} src)  corrected {m[k + ':corrected']['mean']:.4f}")
json.dump(res, open(out, 'w'), indent=1)
