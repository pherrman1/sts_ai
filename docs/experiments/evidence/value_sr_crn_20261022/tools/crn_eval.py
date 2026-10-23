"""SR-CRN round (gen2/value-sr-crn/PLAN.md): gate metrics of value heads on the common-seed sibling capture.

usage: crn_eval.py ONE_COMBAT OUT_DIR OUT.json CONTROL=weights.bin NAME=weights.bin ...
OUT_DIR is the output of `crn_analyze.py rows` (§644: rows.jsonl, records.jsonl). Head values are cached there per
weights stem (crn_analyze.head_values), so weight files need distinct stems. CONTROL is SR_w1 seed 0. The run on
2026-10-22 used the copy on the data branch (gen2/value-sr-crn/tools/), which differs only in how it finds the
repository.

Per head:
- the capture's VALIDATION (seed % 4 == 3): concordance and regret of the head alone, with paired source-bootstrap CIs
  against X2-B and against the control;
- the TRAIN holdout (seed % 8 == 6, never trained on): the head alone, and the blend
  sigmoid((1 - w) logit X2-B + w logit head) for each w in W;
- the holdout's best w on VALIDATION, against X2-B and against the control's blend chosen the same way.
Gate (head alone, VALIDATION; the bars are checked separately): PASS if it reaches X2-B, IMPROVED if it beats the
control with the paired CI above 0, FAIL otherwise.
"""
import json
import math
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get('STS_REPO') or Path(__file__).resolve().parents[5])  # docs/experiments/evidence/<e>/tools/
sys.path.insert(0, str(REPO / 'docs/experiments/evidence/ooc_sibling_crn_capture_20261022/tools'))
import crn_analyze as ca  # noqa: E402

W = [0.05, 0.1, 0.15, 0.2, 0.25, 0.3]


def lg(p):
    p = min(max(p, 1e-7), 1 - 1e-7)
    return math.log(p / (1 - p))


def main(binary, out_dir, out, *specs):
    rows = ca.load_rows(out_dir)
    heads = dict(s.split('=', 1) for s in specs)
    control = next(iter(heads))
    for name, weights in heads.items():
        vals = ca.head_values(binary, out_dir, weights)
        if len(vals) != len(rows):
            raise ValueError(f'heart1score row count mismatch for {name}')
        for r, v in zip(rows, vals):
            r[name] = 1 / (1 + math.exp(-v))
            for w in W:
                r[f'{name}@{w}'] = 1 / (1 + math.exp(-((1 - w) * lg(r['x2b']) + w * v)))
    groups = ca.groups_of(rows)
    val = [g for g in groups if rows[g[0]]['split'] == 'validation']
    hold = [g for g in groups if rows[g[0]]['split'] == 'train' and rows[g[0]]['seed'] % 8 == 6]
    rep = {'heads': heads, 'control': control, 'W': W,
           'validation': {'groups': len(val), 'sources': len({rows[g[0]]['seed'] for g in val})},
           'holdout': {'groups': len(hold), 'sources': len({rows[g[0]]['seed'] for g in hold})},
           'x2b': {'validation': ca.group_metrics(rows, val, 'x2b')[0],
                   'holdout': ca.group_metrics(rows, hold, 'x2b')[0]}}
    x2b = rep['x2b']['validation']['concordance']
    for name in heads:
        h = {'validation': ca.group_metrics(rows, val, name)[0], 'holdout': ca.group_metrics(rows, hold, name)[0],
             'minusX2b': ca.paired_bootstrap(rows, val, name, 'x2b'),
             'blendHoldout': {str(w): ca.group_metrics(rows, hold, f'{name}@{w}')[0]['concordance'] for w in W}}
        h['blendW'] = max(W, key=lambda w: h['blendHoldout'][str(w)])
        h['blendValidation'] = ca.group_metrics(rows, val, f"{name}@{h['blendW']}")[0]
        h['blendMinusX2b'] = ca.paired_bootstrap(rows, val, f"{name}@{h['blendW']}", 'x2b')
        if name != control:
            h['minusControl'] = ca.paired_bootstrap(rows, val, name, control)
            h['blendMinusControlBlend'] = ca.paired_bootstrap(rows, val, f"{name}@{h['blendW']}",
                                                              f"{control}@{rep[control]['blendW']}")
            h['gate'] = ('PASS' if h['validation']['concordance'] >= x2b else
                         'IMPROVED' if h['minusControl']['concordance']['ci95'][0] > 0 else 'FAIL')
        rep[name] = h
    Path(out).write_text(json.dumps(rep, indent=1) + '\n')
    ci = lambda d: f"{d['mean']:+.4f} [{d['ci95'][0]:+.4f}, {d['ci95'][1]:+.4f}]"
    print(f"VALIDATION {rep['validation']}, holdout {rep['holdout']}; X2-B {x2b:.4f} "
          f"(holdout {rep['x2b']['holdout']['concordance']:.4f})")
    for name in heads:
        h = rep[name]
        print(f"{name:12s} conc {h['validation']['concordance']:.4f} regret {h['validation']['regret']:.4f} "
              f"- X2-B {ci(h['minusX2b']['concordance'])}"
              + (f" - {control} {ci(h['minusControl']['concordance'])} gate {h['gate']}" if name != control else ''))
        print(f"{'':12s} holdout {h['holdout']['concordance']:.4f}; blend w {h['blendW']} (holdout "
              f"{h['blendHoldout'][str(h['blendW'])]:.4f}) VALIDATION {h['blendValidation']['concordance']:.4f} "
              f"- X2-B {ci(h['blendMinusX2b']['concordance'])}"
              + (f" - control blend {ci(h['blendMinusControlBlend']['concordance'])}" if name != control else ''))
    return rep


if __name__ == '__main__':
    if len(sys.argv) < 5:
        sys.exit(__doc__)
    main(*sys.argv[1:])
