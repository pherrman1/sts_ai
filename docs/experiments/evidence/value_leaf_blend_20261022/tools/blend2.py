"""Exploratory: leaf blend v = sigmoid((1 - w) * logit(x2b) + w * logit(head)) on the §577 data, aggregated exactly as
value_leaf_check (probability space, so w = 0 reproduces X2-B). Choose w on round-2 TRAIN by concordance; report
round-2 VALIDATION and §494 with source-bootstrap CIs vs X2-B, and outcome AUC vs X2-B (round-2 all / validation).
usage: blend2.py WORK S494 R2 HEAD"""
import json, os, sys
import numpy as np
from pathlib import Path
REPO = Path(__file__).resolve().parents[5]
sys.path[:0] = [str(REPO / 'tools' / 'heart1'), str(REPO / 'tools')]
from value_leaf_check import load_round2, groups_of, outcome_metrics
from outcome_head_sibling_check import load_siblings, group_metrics, paired_bootstrap

work, d494, dr2, head = sys.argv[1:5]
lg = lambda p: np.log(p / (1 - p))
sig = lambda z: 1 / (1 + np.exp(-z))
W = [0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.33, 0.5, 0.67, 1]

def attach(rows, tag):
    vals = [json.loads(l)['value'] for l in open(f'{work}/{tag}-{head}-out.jsonl')]
    assert len(vals) == len(rows)
    for r, v in zip(rows, vals):
        for w in W: r[f'w{w}'] = float(sig((1 - w) * lg(r['x2b']) + w * v))

r494, g494 = load_siblings(d494)
for r in r494: r.pop('record', None)
attach(r494, 's494')
with open(os.devnull, 'w') as sink: r2, _ = load_round2(dr2, sink)
attach(r2, 'r2')
g2 = groups_of(r2)
gtr = [g for g in g2 if r2[g[0]]['split'] == 'train']; gva = [g for g in g2 if r2[g[0]]['split'] == 'validation']
rva = [r for r in r2 if r['split'] == 'validation']
res = {}
for w in W:
    k = f'w{w}'
    res[k] = {'r2train': group_metrics(r2, gtr, k)[0], 'r2val': group_metrics(r2, gva, k)[0], 's494': group_metrics(r494, g494, k)[0]}
    print(f"{head} w {w:<5} conc r2tr {res[k]['r2train']['concordance']:.4f} r2va {res[k]['r2val']['concordance']:.4f} s494 {res[k]['s494']['concordance']:.4f} | regret r2va {res[k]['r2val']['regret']:.4f} s494 {res[k]['s494']['regret']:.4f}", flush=True)
best = max(W[1:], key=lambda w: res[f'w{w}']['r2train']['concordance'])
print('chosen on r2 train:', best, flush=True)
for w in sorted({best, 0.2, 0.33}):
    k = f'w{w}'
    pv = paired_bootstrap(r2, gva, k, 'x2b'); p4 = paired_bootstrap(r494, g494, k, 'x2b')
    ov = outcome_metrics(rva, (k, 'x2b')); oa = outcome_metrics(r2, (k, 'x2b'))
    res[k].update({'r2valMinusX2b': pv, 's494MinusX2b': p4, 'outcomeVal': ov[k], 'outcomeAll': oa[k], 'x2bOutcomeVal': ov['x2b'], 'x2bOutcomeAll': oa['x2b']})
    print(f"w {w}: r2va conc - x2b {pv['concordance']['mean']:+.4f} {np.round(pv['concordance']['ci95'], 4)} regret {pv['regret']['mean']:+.4f} {np.round(pv['regret']['ci95'], 4)}; "
          f"s494 conc - x2b {p4['concordance']['mean']:+.4f} {np.round(p4['concordance']['ci95'], 4)}; outcome AUC val {ov[k]['auc']:.3f} vs {ov['x2b']['auc']:.3f} "
          f"[{ov[k]['aucMinusX2b']['ci95'][0]:+.3f}, {ov[k]['aucMinusX2b']['ci95'][1]:+.3f}], all {oa[k]['auc']:.3f} vs {oa['x2b']['auc']:.3f} "
          f"[{oa[k]['aucMinusX2b']['ci95'][0]:+.3f}, {oa[k]['aucMinusX2b']['ci95'][1]:+.3f}]; mean leaf {oa[k]['mean']:.3f}", flush=True)
for act in sorted({r['act'] for r in r2}):
    gs = [g for g in gva if r2[g[0]]['act'] == act]
    print(f"act {act}: r2va groups {len(gs)} conc x2b {group_metrics(r2, gs, 'x2b')[0]['concordance']:.4f} w{best} {group_metrics(r2, gs, f'w{best}')[0]['concordance']:.4f} head {group_metrics(r2, gs, 'w1')[0]['concordance']:.4f}", flush=True)
json.dump(res, open(f'blend2-{head}.json', 'w'), indent=1)
