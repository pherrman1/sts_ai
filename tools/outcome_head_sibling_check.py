#!/usr/bin/env python3
"""Offline check of the §498 observed-outcome head as an OOC MCTS leaf ranker (§502).

The head (docs/experiments/evidence/heart_outcome_value_20261017/head.json) reads the
64-d pooled value-head input of the frozen Arm C student. `one_combat heart1score`
exports that vector, so no torch is needed.

  parity   <one_combat> <studentc.bin> <validation dir> <work dir>
           score §497 VALIDATION states and compare per-source mean probability with
           the §498 result.json (states: supported real-driver boundaries).
  siblings <one_combat> <studentc.bin> <§494 extracted sources dir> <work dir> [head.json ...]
           score every §494 sibling leaf and compare each head with X2-B and the single
           scheduled rollout3 on the §494 group metrics (64-rollout mean targets).

A head file has head.json's keys (mean, scale, layers.0.*, layers.2.*). Its input is
the 64 pooled values, the 37-value §501 public block (heart_outcome_dev_compare.public_block)
alone, or pooled followed by the public block (101), normalized after concatenation.
"""
import glob
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = REPO / 'docs/experiments/evidence/heart_outcome_value_20261017'
TRAIN_END, VALIDATION_END = 110164040, 110164048  # §494 split: 40 TRAIN, 8 VALIDATION, 16 TEST
BOOTSTRAP_SEED = 20261017


def load_head(path=EVIDENCE / 'head.json'):
    h = json.loads(Path(path).read_text())
    return {k: np.array(v, dtype=np.float64) for k, v in h.items()}


EMPTY_POTION = 1


def public_block(record, act):
    """Copy of tools/heart_outcome_dev_compare.py public_block (§501), without torch."""
    fo = record['obs.fixed_observation']
    if not (len(fo) == 10 and 1 <= act <= 4 and 0 <= fo[4] < 10 and 0 <= record['screen_state'] < 10):
        raise ValueError('public block vocabulary')
    hp, max_hp, gold, floor = fo[0], fo[1], fo[2], fo[3]
    row = [hp/100, max_hp/100, hp/max(max_hp, 1), gold/500, floor/55, float(fo[7]), float(fo[8]), float(fo[9])]
    row += [float(fo[4] == i) for i in range(10)] + [float(act == i) for i in range(1, 5)]
    row += [float(record['screen_state'] == i) for i in range(10)]
    potions = record['obs.potions']
    row += [len(record['obs.deck.cards'])/30, sum(u > 0 for u in record['obs.deck.upgrades'])/10,
            len(record['obs.relics.relics'])/20, sum(p != EMPTY_POTION for p in potions)/3, len(potions)/3]
    if len(row) != 37:
        raise ValueError('public block width')
    return row


def head_prob(head, pooled, public=None):
    x = np.atleast_2d(np.asarray(pooled, dtype=np.float64))
    if len(head['mean']) == 64 + 37:
        x = np.concatenate([x, np.asarray(public, dtype=np.float64)], axis=1)
    elif len(head['mean']) == 37:
        x = np.asarray(public, dtype=np.float64)
    elif len(head['mean']) != 64:
        raise ValueError('unsupported head input width')
    x = (x - head['mean']) / head['scale']
    z = np.maximum(x @ head['layers.0.weight'].T + head['layers.0.bias'], 0) @ head['layers.2.weight'].T
    return 1 / (1 + np.exp(-(z[:, 0] + head['layers.2.bias'][0])))


def score(binary, weights, records, work, tag):
    inp, out = Path(work) / f'{tag}-in.jsonl', Path(work) / f'{tag}-out.jsonl'
    inp.write_text(''.join(json.dumps(r) + '\n' for r in records))
    subprocess.run([binary, 'heart1score', weights, str(inp), str(out)], check=True, capture_output=True)
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    if len(rows) != len(records):
        raise ValueError('heart1score row count mismatch')
    return rows


def parity(binary, weights, valdir, work):
    head = load_head()
    reference = json.loads((EVIDENCE / 'result.json').read_text())['validation']['perSource']
    out = []
    for path in sorted(glob.glob(f'{valdir}/seed-*.states.jsonl')):
        seed = path.split('seed-')[-1].split('.')[0]
        states = [json.loads(line) for line in open(path)][1:-1]
        records = [s['record'] for s in states if s.get('supported')]
        p = head_prob(head, [r['pooled'] for r in score(binary, weights, records, work, seed)])
        ref = reference[seed]['meanProbability']
        out.append({'seed': int(seed), 'states': len(records), 'native': float(p.mean()), 'reference': ref,
                    'absDiff': abs(float(p.mean()) - ref)})
    return {'sources': out, 'maxAbsDiff': max(o['absDiff'] for o in out)}


def load_siblings(root):
    """Same acceptance as tools/heart_rollout_distill.py validate_rows for an Arm C capture."""
    rows = []
    for path in sorted(glob.glob(f'{root}/seed-*/seed-*.sib.jsonl')):
        seed = int(path.split('seed-')[-1].split('.')[0])
        if seed >= VALIDATION_END:
            raise ValueError('TEST source present; §494 TEST stays excluded')
        accepted, bad = [], set()
        for raw in map(json.loads, open(path)):
            e, group = raw.get('extra', {}), (seed, raw['decision'], raw['parent'])
            reps = e.get('repeats', [])
            if (len(reps) != 64 or 'record' not in e or 'x2b' not in e or e.get('rolloutPolicy') != 'heart1'
                    or e.get('recordSchema') != 'heart1-public-record-v2'):
                bad.add(group)
                continue
            accepted.append({'seed': seed, 'group': group, 'action': raw['action'], 'act': raw['act'],
                             'screen': raw['parentScreen'], 'target': float(np.mean([v['value'] for v in reps])),
                             'x2b': float(e['x2b']), 'r0': float(raw['value']), 'record': e['record']})
        rows += [r for r in accepted if r['group'] not in bad]
    groups = defaultdict(list)
    for i, r in enumerate(rows):
        groups[r['group']].append(i)
    return rows, [g for g in groups.values() if len({rows[i]['action'] for i in g}) >= 2]


def group_metrics(rows, groups, key):
    """Per-source mean of §494's group regret and pairwise concordance, then mean over sources."""
    per = defaultdict(lambda: defaultdict(list))
    for ids in groups:
        actions = defaultdict(list)
        for i in ids:
            actions[rows[i]['action']].append(i)
        t = np.array([np.mean([rows[i]['target'] for i in g]) for g in actions.values()])
        p = np.array([np.mean([rows[i][key] for i in g]) for g in actions.values()])
        source = per[rows[ids[0]]['seed']]
        source['regret'].append(float(t.max() - t[p.argmax()]))
        pairs = [.5 if p[i] == p[j] else float((p[i] - p[j]) * (t[i] - t[j]) > 0)
                 for i in range(len(t)) for j in range(i) if abs(t[i] - t[j]) > 1e-8]
        if pairs:
            source['concordance'].append(float(np.mean(pairs)))
    per = {k: {m: float(np.mean(v)) for m, v in d.items()} for k, d in per.items()}
    fill = {'concordance': .5, 'regret': 0.}
    agg = {m: float(np.mean([d.get(m, fill[m]) for d in per.values()])) for m in fill}
    return agg, per


def paired_bootstrap(rows, groups, a, b, n=2000):
    _, pa = group_metrics(rows, groups, a)
    _, pb = group_metrics(rows, groups, b)
    keys, fill = sorted(set(pa) & set(pb)), {'concordance': .5, 'regret': 0.}
    rng, out = np.random.default_rng(BOOTSTRAP_SEED), {}
    for m in fill:
        d = np.array([pa[k].get(m, fill[m]) - pb[k].get(m, fill[m]) for k in keys])
        s = d[rng.integers(0, len(d), (n, len(d)))].mean(1)
        out[m] = {'mean': float(d.mean()), 'ci95': [float(np.quantile(s, .025)), float(np.quantile(s, .975))]}
    return out


def siblings(binary, weights, root, work, *head_files):
    rows, groups = load_siblings(root)
    scored = score(binary, weights, [r['record'] for r in rows], work, 'siblings')
    pooled, public = [s['pooled'] for s in scored], [public_block(r['record'], r['act']) for r in rows]
    for r, s in zip(rows, scored):
        r['studentValue'] = float(s['value'])
    heads = {'head': EVIDENCE / 'head.json', **{Path(f).stem: f for f in head_files}}
    for name, path in heads.items():
        for r, p in zip(rows, head_prob(load_head(path), pooled, public)):
            r[name] = float(p)
    keys = (*heads, 'x2b', 'r0', 'studentValue')
    report = {'rows': len(rows), 'groups': len(groups), 'heads': {k: str(v) for k, v in heads.items()},
              'splits': {}, 'byAct': {}, 'byScreen': {}}
    for name, keep in (('train', lambda s: s < TRAIN_END), ('validation', lambda s: TRAIN_END <= s < VALIDATION_END),
                       ('trainValidation', lambda s: True)):
        sel = [g for g in groups if keep(rows[g[0]]['seed'])]
        report['splits'][name] = {'groups': len(sel), **{k: group_metrics(rows, sel, k)[0] for k in keys},
                                  **{f'{h}MinusX2b': paired_bootstrap(rows, sel, h, 'x2b') for h in heads},
                                  **{f'{h}MinusR0': paired_bootstrap(rows, sel, h, 'r0') for h in heads}}
    for field, out in (('act', report['byAct']), ('screen', report['byScreen'])):
        buckets = defaultdict(list)
        for g in groups:
            buckets[rows[g[0]][field]].append(g)
        for k, sel in sorted(buckets.items()):
            out[str(k)] = {'groups': len(sel), **{m: group_metrics(rows, sel, m)[0]['concordance'] for m in keys[:-1]}}
    t = np.array([r['target'] for r in rows])
    report['rowPearsonWithTarget'] = {k: float(np.corrcoef(t, [r[k] for r in rows])[0, 1]) for k in keys}
    return report


if __name__ == '__main__':
    command, args = sys.argv[1], sys.argv[2:]
    print(json.dumps({'parity': parity, 'siblings': siblings}[command](*args), indent=1))
