"""Sibling-ranking round (gen2/value-sr/PLAN.md): gate metrics of value heads on the §577 sibling data.

usage: sr_eval.py R2 S494 OUT.json NAME=WORKDIR ...
WORKDIR holds r2-NAME-out.jsonl and s494-NAME-out.jsonl from `value_leaf_check.py check` (raw value logits, rows in
load_round2 / load_siblings order). Per head: concordance and regret of the head alone on round-2 VALIDATION
(primary), on the TRAIN holdout sources (seed % 8 == 6, never trained on by the SR arms), on the other TRAIN sources
and on §494, with paired source-bootstrap CIs on VALIDATION against X2-B and against the first head (the control);
the blend sigmoid((1 - w) logit(X2-B) + w logit(head)) with w chosen on the TRAIN holdout; outcome AUC on VALIDATION.
"""
import json, os, sys
import numpy as np
from pathlib import Path
REPO = Path(__file__).resolve().parents[5]
sys.path[:0] = [str(REPO / 'tools' / 'heart1'), str(REPO / 'tools')]
from value_leaf_check import load_round2, groups_of, outcome_metrics
from outcome_head_sibling_check import load_siblings, group_metrics, paired_bootstrap

dr2, d494, out = sys.argv[1:4]
heads = dict(a.split('=', 1) for a in sys.argv[4:])
control = next(iter(heads))
W = [0.05, 0.1, 0.15, 0.2, 0.25, 0.33, 0.5, 0.67]
lg = lambda p: np.log(p / (1 - p))
sig = lambda z: 1 / (1 + np.exp(-z))


def attach(rows, tag):
    for name, work in heads.items():
        vals = [json.loads(line)['value'] for line in open(f'{work}/{tag}-{name}-out.jsonl')]
        assert len(vals) == len(rows), (name, tag)
        for r, v in zip(rows, vals):
            r[name] = float(sig(v))
            for w in W:
                r[f'{name}@{w}'] = float(sig((1 - w) * lg(np.clip(r['x2b'], 1e-7, 1 - 1e-7)) + w * v))


r494, g494 = load_siblings(d494)
for r in r494: r.pop('record', None)
attach(r494, 's494')
with open(os.devnull, 'w') as sink: r2, _ = load_round2(dr2, sink)
attach(r2, 'r2')
g2 = groups_of(r2)
split = lambda g: r2[g[0]]['split']
gva = [g for g in g2 if split(g) == 'validation']
gho = [g for g in g2 if split(g) == 'train' and r2[g[0]]['seed'] % 8 == 6]
gtr = [g for g in g2 if split(g) == 'train' and r2[g[0]]['seed'] % 8 != 6]
rva = [r for r in r2 if r['split'] == 'validation']
conc = lambda rows, gs, k: group_metrics(rows, gs, k)[0]
ci = lambda d: f"{d['concordance']['mean']:+.4f} [{d['concordance']['ci95'][0]:+.4f}, {d['concordance']['ci95'][1]:+.4f}]"

res = {'groups': {'validation': len(gva), 'trainHoldout': len(gho), 'trainRest': len(gtr), 's494': len(g494)},
       'x2b': {'validation': conc(r2, gva, 'x2b'), 'trainHoldout': conc(r2, gho, 'x2b'), 'trainRest': conc(r2, gtr, 'x2b'),
               's494': conc(r494, g494, 'x2b')}}
print(f"groups VALIDATION {len(gva)} TRAIN holdout {len(gho)} TRAIN rest {len(gtr)} s494 {len(g494)}")
print(f"{'x2b':10s} val {res['x2b']['validation']['concordance']:.4f} hold {res['x2b']['trainHoldout']['concordance']:.4f} "
      f"rest {res['x2b']['trainRest']['concordance']:.4f} s494 {res['x2b']['s494']['concordance']:.4f}")
for name in heads:
    w = max(W, key=lambda w: conc(r2, gho, f'{name}@{w}')['concordance'])
    k = f'{name}@{w}'
    ov = outcome_metrics(rva, (name, 'x2b'))
    res[name] = {'validation': conc(r2, gva, name), 'trainHoldout': conc(r2, gho, name), 'trainRest': conc(r2, gtr, name),
                 's494': conc(r494, g494, name), 'valMinusX2b': paired_bootstrap(r2, gva, name, 'x2b'),
                 'valMinusControl': paired_bootstrap(r2, gva, name, control) if name != control else None,
                 'outcomeVal': ov[name], 'x2bOutcomeVal': ov['x2b'],
                 'blend': {'w': w, 'trainHoldout': conc(r2, gho, k), 'validation': conc(r2, gva, k), 's494': conc(r494, g494, k),
                           'valMinusX2b': paired_bootstrap(r2, gva, k, 'x2b')}}
    h = res[name]
    print(f"{name:10s} val {h['validation']['concordance']:.4f} hold {h['trainHoldout']['concordance']:.4f} "
          f"rest {h['trainRest']['concordance']:.4f} s494 {h['s494']['concordance']:.4f} | val-x2b {ci(h['valMinusX2b'])}"
          + (f" val-{control} {ci(h['valMinusControl'])}" if h['valMinusControl'] else '')
          + f" | AUC val {ov[name]['auc']:.3f} (x2b {ov['x2b']['auc']:.3f})"
          + f" | blend w{w}: val {h['blend']['validation']['concordance']:.4f} s494 {h['blend']['s494']['concordance']:.4f}"
          f" val-x2b {ci(h['blend']['valMinusX2b'])}", flush=True)
Path(out).write_text(json.dumps(res, indent=1) + '\n')
