#!/usr/bin/env python3
"""Offline check of a heart1-format net's value head as an OOC MCTS leaf value (gen 1b, §TBD).

Scores sibling leaves that earlier campaigns captured with 64 rollout3 repeats each, and compares the net's value
head with X2-B at the same leaf, one scheduled rollout3, and student_sel's untrained value head:

  - sibling ranking: §494 group concordance and regret against the 64-rollout mean (tools/outcome_head_sibling_check.py);
  - observed outcome: AUC and BCE of each leaf value against the source run's Heart kill (round 2 only).

  check <one_combat> <out.json> <work dir> <§494 extracted dir> <round-2 extracted dir> NAME=weights.bin ...

`<§494 extracted dir>`: the §494 TRAIN+VALIDATION sources (seed-*/seed-*.sib.jsonl, TEST excluded).
`<round-2 extracted dir>`: train/ and validation/ of the §503 deliveries (seed-*.sib.jsonl and seed-*.states.jsonl;
CONFIRM stays sealed). The capture records carry no obs.act; the leaf row's act is inserted, as the native encoder
does. They carry no obs.deck.misc (Ritual Dagger, Genetic Algorithm), and Wing Boots' counter is the relic data,
not the #638 charges.
"""
import glob
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from outcome_head_sibling_check import BOOTSTRAP_SEED, group_metrics, load_siblings, paired_bootstrap  # noqa: E402


def load_round2(root, sink):
    """Round-2 sibling rows with the same acceptance as load_siblings, plus each source's Heart-kill label.
    Records (with obs.act) go to `sink` in row order instead of staying in memory."""
    rows, n_sources = [], 0
    for split in ('train', 'validation'):
        for path in sorted(glob.glob(f'{root}/{split}/seed-*.sib.jsonl')):
            seed = int(path.split('seed-')[-1].split('.')[0])
            last = json.loads(open(path.replace('.sib.jsonl', '.states.jsonl')).readlines()[-1])
            if last.get('type') != 'outcome' or not last.get('complete') or not last.get('integrityPassed'):
                continue
            n_sources += 1
            accepted, bad = [], set()
            for raw in map(json.loads, open(path)):
                e, group = raw.get('extra', {}), (seed, raw['decision'], raw['parent'])
                reps = e.get('repeats', [])
                if (len(reps) != 64 or 'record' not in e or 'x2b' not in e or e.get('rolloutPolicy') != 'heart1'
                        or e.get('recordSchema') != 'heart1-public-record-v2'):
                    bad.add(group)
                    continue
                accepted.append({'seed': seed, 'split': split, 'group': group, 'action': raw['action'],
                                 'act': raw['act'], 'screen': raw['parentScreen'],
                                 'target': float(np.mean([v['value'] for v in reps])), 'x2b': float(e['x2b']),
                                 'r0': float(raw['value']), 'record': e['record'], 'heart': int(bool(last['heartKilled']))})
            for r in accepted:
                if r['group'] not in bad:
                    sink.write(json.dumps({**r.pop('record'), 'obs.act': r['act']}) + '\n')
                    rows.append(r)
    return rows, n_sources


def groups_of(rows):
    groups = defaultdict(list)
    for i, r in enumerate(rows):
        groups[r['group']].append(i)
    return [g for g in groups.values() if len({rows[i]['action'] for i in g}) >= 2]


def auc(y, p):
    y, p = np.asarray(y), np.asarray(p, dtype=np.float64)
    _, inverse, counts = np.unique(p, return_inverse=True, return_counts=True)
    ranks = (np.cumsum(counts) - (counts - 1) / 2)[inverse]  # average ranks over ties
    pos = y == 1
    return float((ranks[pos].sum() - pos.sum() * (pos.sum() + 1) / 2) / (pos.sum() * (~pos).sum()))


def bce(y, p):
    p = np.clip(np.asarray(p, dtype=np.float64), 1e-6, 1 - 1e-6)
    return float(-np.mean(np.asarray(y) * np.log(p) + (1 - np.asarray(y)) * np.log(1 - p)))


def outcome_metrics(rows, keys, n=2000):
    """Leaf-level AUC/BCE vs the source's Heart kill; source bootstrap for AUC differences against x2b."""
    y = np.array([r['heart'] for r in rows])
    out = {'leaves': len(rows), 'baseRate': float(y.mean()), 'constantBce': bce(y, np.full(len(y), y.mean()))}
    for k in keys:
        p = np.array([r[k] for r in rows])
        out[k] = {'auc': auc(y, p), 'bce': bce(y, p), 'mean': float(p.mean())}
    by_seed = defaultdict(list)
    for i, r in enumerate(rows):
        by_seed[r['seed']].append(i)
    seeds = sorted(by_seed)
    members = [np.array(by_seed[s]) for s in seeds]
    values = {k: np.array([r[k] for r in rows]) for k in keys}
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    draws = {k: [] for k in keys if k != 'x2b'}
    for _ in range(n):
        idx = np.concatenate([members[j] for j in rng.integers(0, len(seeds), len(seeds))])
        yy = y[idx]
        base = auc(yy, values['x2b'][idx])
        for k in draws:
            draws[k].append(auc(yy, values[k][idx]) - base)
    for k, d in draws.items():
        out[k]['aucMinusX2b'] = {'mean': out[k]['auc'] - out['x2b']['auc'],
                                 'ci95': [float(np.quantile(d, .025)), float(np.quantile(d, .975))]}
    return out


def sibling_report(rows, groups, keys, nets):
    rep = {'rows': len(rows), 'groups': len(groups), 'all': {k: group_metrics(rows, groups, k)[0] for k in keys}}
    for k in nets:
        rep[f'{k}MinusX2b'] = paired_bootstrap(rows, groups, k, 'x2b')
        rep[f'{k}MinusR0'] = paired_bootstrap(rows, groups, k, 'r0')
    for field in ('act', 'screen'):
        buckets = defaultdict(list)
        for g in groups:
            buckets[rows[g[0]][field]].append(g)
        rep['by' + field.capitalize()] = {str(b): {'groups': len(sel), **{k: group_metrics(rows, sel, k)[0]['concordance']
                                                                           for k in keys}}
                                          for b, sel in sorted(buckets.items())}
    t = np.array([r['target'] for r in rows])
    rep['rowPearsonWithTarget'] = {k: float(np.corrcoef(t, [r[k] for r in rows])[0, 1]) for k in keys}
    return rep


def annotate(binary, nets, rows, inp, work, tag):
    """sigmoid(value head) of each net on the records in `inp` (one per row, same order)."""
    for name, weights in nets.items():
        out = Path(work) / f'{tag}-{name}-out.jsonl'
        subprocess.run([binary, 'heart1score', weights, str(inp), str(out)], check=True, capture_output=True)
        values = [json.loads(line)['value'] for line in open(out)]
        if len(values) != len(rows):
            raise ValueError('heart1score row count mismatch')
        for r, v in zip(rows, values):
            r[name] = float(1 / (1 + np.exp(-v)))


def check(binary, out, work, d494, dr2, *net_args):
    nets = dict(a.split('=', 1) for a in net_args)
    keys = (*nets, 'x2b', 'r0')
    Path(work).mkdir(parents=True, exist_ok=True)
    report = {'nets': nets, 'bootstrap': {'resamples': 2000, 'rng': BOOTSTRAP_SEED, 'unit': 'source seed'}}
    rows, groups = load_siblings(d494)
    inp = Path(work) / 's494-in.jsonl'
    with open(inp, 'w') as sink:
        for r in rows:
            sink.write(json.dumps({**r.pop('record'), 'obs.act': r['act']}) + '\n')
    annotate(binary, nets, rows, inp, work, 's494')
    report['s494'] = sibling_report(rows, groups, keys, nets)
    inp = Path(work) / 'r2-in.jsonl'
    with open(inp, 'w') as sink:
        rows, n_sources = load_round2(dr2, sink)
    annotate(binary, nets, rows, inp, work, 'r2')
    groups = groups_of(rows)
    report['round2'] = {'sources': n_sources, 'siblings': sibling_report(rows, groups, keys, nets),
                        'outcome': outcome_metrics(rows, (*nets, 'x2b', 'r0', 'target'))}
    for act in sorted({r['act'] for r in rows}):
        sel = [r for r in rows if r['act'] == act]
        y = np.array([r['heart'] for r in sel])
        report['round2'].setdefault('outcomeByAct', {})[str(act)] = {
            'leaves': len(sel), 'baseRate': float(y.mean()),
            **{k: auc(y, [r[k] for r in sel]) for k in (*nets, 'x2b', 'target')}} if 0 < y.sum() < len(y) else {'leaves': len(sel)}
    Path(out).write_text(json.dumps(report, indent=1) + '\n')
    return report


if __name__ == '__main__':
    if sys.argv[1] != 'check':
        raise SystemExit(__doc__)
    check(*sys.argv[2:])
