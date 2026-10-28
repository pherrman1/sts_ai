"""Sibling-difference noise and bias from campfire-price-v1 rows (leaf = search's own rollout3 + M0 leaf;
actEnd = rollout to the act's end valued by M0; stream r shared by all actions within each kind).
usage: price_bias.py OUT.json FILE.price.jsonl...  (pairs: prior top-1 vs top-2 and top-3)"""
import json, math, sys
import numpy as np
SCREEN = {1: 'EVENT', 2: 'CARD_REWARD', 3: 'BOSS_RELIC', 4: 'CARD_SELECT', 5: 'MAP', 6: 'TREASURE', 7: 'REST', 8: 'SHOP'}
GAPS = (0.01, 0.02, 0.05, 0.10)

def vals(lst):
    return np.array([x['value'] if 'value' in x else np.nan for x in lst], dtype=float)

pairs = []
for path in sys.argv[2:]:
    for line in open(path):
        try: row = json.loads(line)
        except json.JSONDecodeError: continue
        price = row.get('price') or {}
        acts = [a for a in price.get('actions', []) if a.get('leaf') and a.get('actEnd')]
        if len(acts) < 2: continue
        acts = sorted(acts, key=lambda a: -a['prior'])[:3]
        L = [vals(a['leaf']) for a in acts]; R = [vals(a['actEnd']) for a in acts]
        if any(np.isnan(x).any() for x in L + R): continue
        n = len(L[0])
        for j in range(1, len(acts)):
            dl, dr = L[0] - L[j], R[0] - R[j]
            pairs.append(dict(seed=row['seed'], decisionIndex=row['decisionIndex'], floor=row['floor'], act=row['act'],
                screen=SCREEN.get(row.get('screen', 7)), rank=j, n=n, keys=[acts[0]['key'], acts[j]['key']],
                priors=[acts[0]['prior'], acts[j]['prior']], labels=[acts[0].get('label'), acts[j].get('label')],
                dLeaf=dl.mean(), sdLeafP=dl.std(ddof=1), sdLeafU=math.sqrt(L[0].var(ddof=1) + L[j].var(ddof=1)),
                dRef=dr.mean(), sdRefP=dr.std(ddof=1), sdRefU=math.sqrt(R[0].var(ddof=1) + R[j].var(ddof=1)),
                revLeaf=float(np.mean(np.sign(dl) != np.sign(dl.mean()))) if dl.mean() else float('nan'),
                same=bool(np.allclose(dl, dr)),
                refAhead=float(np.median([x['endFloor'] for a in (acts[0], acts[j]) for x in a['actEnd']])
                               - np.median([x['endFloor'] for a in (acts[0], acts[j]) for x in a['leaf']]))))

def summ(ps, label, out):
    if not ps: return
    a = lambda k: np.array([p[k] for p in ps], dtype=float)
    n = a('n')
    dL, dR = a('dLeaf'), a('dRef')
    seL, seR = a('sdLeafP') / np.sqrt(n), a('sdRefP') / np.sqrt(n)
    e = dL - dR; se_e = np.sqrt(seL ** 2 + seR ** 2)
    bias = e.mean(); bias_se = e.std(ddof=1) / math.sqrt(len(e)) if len(e) > 1 else float('nan')
    # seed-cluster bootstrap (roots of one game are correlated)
    seeds = np.array([p['seed'] for p in ps]); us = np.unique(seeds); idx = [np.where(seeds == u)[0] for u in us]
    rng = np.random.default_rng(881); bs = []
    for _ in range(2000):
        pick = np.concatenate([idx[k] for k in rng.integers(0, len(us), len(us))]); bs.append(e[pick].mean())
    bias_ci = [float(np.quantile(bs, .025)), float(np.quantile(bs, .975))]
    # pair-level bias spread beyond noise
    var_b = max((e ** 2).mean() - bias ** 2 - (se_e ** 2).mean(), 0)
    both = (np.abs(dL) > 2 * seL) & (np.abs(dR) > 2 * seR)
    dis = np.sign(dL) != np.sign(dR)
    var_true_ref = max(dR.var() - (seR ** 2).mean(), 0)
    slope = np.cov(dL, dR)[0, 1] / var_true_ref if var_true_ref > 0 else float('nan')
    rmsP = math.sqrt((a('sdLeafP') ** 2).mean()); rmsU = math.sqrt((a('sdLeafU') ** 2).mean())
    snr = np.abs(dL) / np.where(a('sdLeafP') > 0, a('sdLeafP'), np.nan)
    s = dict(label=label, roots=len({(p['seed'], p['decisionIndex']) for p in ps}), seeds=len({p['seed'] for p in ps}), pairs=len(ps),
        leafSd1Paired=rmsP, leafSd1Unpaired=rmsU, crnVarRatio=(a('sdLeafP') ** 2).sum() / (a('sdLeafU') ** 2).sum(),
        refSd1Paired=math.sqrt((a('sdRefP') ** 2).mean()), revLeaf=float(np.nanmean(a('revLeaf'))), snrMedian=float(np.nanmedian(snr)),
        nForGapPaired={f'{int(g*100)}pp': (1.96 * rmsP / g) ** 2 for g in GAPS}, nForGapUnpaired={f'{int(g*100)}pp': (1.96 * rmsU / g) ** 2 for g in GAPS},
        medAbsDLeaf=float(np.median(np.abs(dL))), medAbsDRef=float(np.median(np.abs(dR))), medSeLeaf=float(np.median(seL)), medSeRef=float(np.median(seR)),
        bias=bias, biasSe=bias_se, biasCi95Seed=bias_ci, meanAbsErr=float(np.abs(e).mean()), meanAbsErrNoiseOnly=float(np.sqrt(2 / math.pi) * np.sqrt((se_e ** 2).mean())),
        biasSpreadSd=math.sqrt(var_b), slopeLeafOnRef=slope, rankDisagreeAll=float(dis.mean()), resolvedBoth=int(both.sum()),
        rankDisagreeResolved=float(dis[both].mean()) if both.any() else float('nan'), identical=float(a('same').mean()))
    out.append(s)
    print(f"{label:12s} seeds {s['seeds']:3d} roots {s['roots']:4d} pairs {s['pairs']:4d} | leaf sd1 P {rmsP*100:.1f} U {rmsU*100:.1f}pp CRN {s['crnVarRatio']:.2f} "
          f"| ref sd1 P {s['refSd1Paired']*100:.1f} | med|D| leaf {s['medAbsDLeaf']*100:.2f} ref {s['medAbsDRef']*100:.2f} (SE {s['medSeLeaf']*100:.2f}/{s['medSeRef']*100:.2f}) "
          f"| bias {bias*100:+.2f} [{bias_ci[0]*100:+.2f},{bias_ci[1]*100:+.2f}]pp spread {s['biasSpreadSd']*100:.2f} | MAE {s['meanAbsErr']*100:.2f} (noise-only {s['meanAbsErrNoiseOnly']*100:.2f}) "
          f"| slope {slope:.2f} | disagree all {s['rankDisagreeAll']:.2f} resolved {s['rankDisagreeResolved']:.2f} (n {s['resolvedBoth']}) | identical {s['identical']:.2f}")

import os
if os.environ.get('DEEP'):
    pairs = [p for p in pairs if p['refAhead'] >= float(os.environ['DEEP'])]
    print(f'== pairs whose act-end reference ends >= {os.environ["DEEP"]} floors beyond the leaf ==')
out = []
summ(pairs, 'pooled', out)
for sc in ('CARD_REWARD', 'MAP', 'REST', 'SHOP', 'EVENT', 'BOSS_RELIC', 'TREASURE', 'CARD_SELECT'):
    summ([p for p in pairs if p['screen'] == sc], sc, out)
for act in (1, 2, 3, 4):
    summ([p for p in pairs if p['act'] == act], f'act{act}', out)
json.dump({'summary': out, 'pairs': pairs}, open(sys.argv[1], 'w'))
