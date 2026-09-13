#!/usr/bin/env python3
"""Native RAW counter constraints; inferred outcomes never determine support."""
from __future__ import annotations
import argparse
import json
from collections import Counter
from pathlib import Path
import numpy as np
try:
    from tools import combat_transition_surrogate as base
except ModuleNotFoundError:
    import combat_transition_surrogate as base

CYCLIC = {'HAPPY_FLOWER': 3, 'INCENSE_BURNER': 6, 'INK_BOTTLE': 10,
          'INSERTER': 2, 'NUNCHAKU': 10, 'PEN_NIB': 10, 'SUNDIAL': 3}
COPY_COUNTERS = {'BURNING_BLOOD', 'BLACK_BLOOD', 'MEAT_ON_THE_BONE'}
NAMES = {v: k for k, v in base.MUTABLE_RELIC_NAMES.items()}
if set(NAMES.values()) != set(CYCLIC) | COPY_COUNTERS | {'NEOWS_LAMENT', 'LIZARD_TAIL', 'OMAMORI'}:
    raise RuntimeError('native write-back set changed; repeat legality audit')

def legal_posts(relic_id: int, pre: int, encounter: int | None = None, mark_of_bloom: bool = False) -> frozenset[int]:
    """Conservative native reachable domain. Unknown/invalid states require Silver.

    Omamori can decrement only in Writhing Mass (globally excluded). Lizard
    Tail cannot recharge. Neow's Lament decrements once per RAW exit, even death.
    Healing relic cases never write their data; arbitrary saved data copies.
    """
    if not np.isfinite(pre) or pre != int(pre):
        raise ValueError('SILVER_REQUIRED noninteger counter')
    name = NAMES.get(int(relic_id))
    if name in CYCLIC:
        period = CYCLIC[name]
        if not 0 <= pre < period:
            raise ValueError(f'SILVER_REQUIRED {name} pre={pre}')
        return frozenset(range(period))
    if name == 'NEOWS_LAMENT':
        if not 0 <= pre <= 3:
            raise ValueError(f'SILVER_REQUIRED {name} pre={pre}')
        return frozenset([max(0, pre - 1)])
    if name == 'LIZARD_TAIL':
        if pre not in (0, 1):
            raise ValueError(f'SILVER_REQUIRED {name} pre={pre}')
        return frozenset([pre]) if mark_of_bloom else frozenset(range(pre + 1))
    if name == 'OMAMORI':
        if not 0 <= pre <= 2 or encounter is None:
            raise ValueError(f'SILVER_REQUIRED {name} pre={pre} encounter={encounter}')
        writhing = base._ENCOUNTER_IDS['WRITHING_MASS']
        return frozenset([pre, max(0, pre - 1)]) if encounter == writhing else frozenset([pre])
    if name in COPY_COUNTERS:
        return frozenset([pre])
    raise ValueError(f'SILVER_REQUIRED unaudited relic={relic_id}')

def constrained_logp(logits, deltas, relic_id, pre, encounter=None, mark_of_bloom=False):
    logits = np.asarray(logits, dtype=np.float64)
    deltas = np.asarray(deltas)
    if logits.shape != deltas.shape or not np.isfinite(logits).all():
        raise ValueError('invalid relic logits')
    allowed = np.isin(pre + deltas, list(legal_posts(relic_id, pre, encounter, mark_of_bloom)))
    masked = np.where(allowed, logits, -np.inf)
    maximum = masked.max()
    if not np.isfinite(maximum):
        raise ValueError('no legal relic class')
    return masked - maximum - np.log(np.exp(masked - maximum).sum())

def audit(corpus: Path):
    counts, fallback, contradictions = Counter(), Counter(), []
    rows = supported = 0
    for row in base.iter_rows(corpus):
        rows += 1
        pi = row['predictorInput']
        pre, post = row['transition']['pre'], row['transition']['post']
        if not base.supported_for_surrogate(pi, pre):
            continue
        supported += 1
        after = {r['id']: r['data'] for r in post['relics']}
        visible = {int(r['relicId']): int(r['data']) for r in pi['relics']}
        for relic in pre['relics']:
            rid, data = relic['id'], relic['data']
            if rid not in NAMES:
                if after[rid] != data:
                    contradictions.append({'source': row['sourceSeed'], 'fight': row['fightIdx'], 'id': rid, 'pre': data, 'post': after[rid], 'rule': 'unaudited counter mutated'})
                continue
            name = NAMES[rid]
            counts[name] += 1
            if visible.get(rid) != data:
                fallback[name + '_predictor_counter_mismatch'] += 1
                continue
            try:
                allowed = legal_posts(rid, data, pi['globals']['encounter'], any(int(r['relicId']) == base._RELIC_IDS['MARK_OF_THE_BLOOM'] for r in pi['relics']))
            except ValueError:
                fallback[name] += 1
                continue
            if after[rid] not in allowed:
                contradictions.append({'source': row['sourceSeed'], 'fight': row['fightIdx'], 'id': rid, 'name': name, 'pre': data, 'post': after[rid], 'allowed': sorted(allowed)})
        if rows % 100000 == 0:
            print(f'audit {rows}', flush=True)
    return {'rows': rows, 'supportedRows': supported, 'tokensByRelic': dict(counts), 'futureSilverRequired': dict(fallback), 'contradictionCount': len(contradictions), 'contradictions': contradictions}

def historical_metrics(arrays, spec, predictions):
    ids = np.flatnonzero(arrays['supported'] & (arrays['split_id'] == 2))
    win = arrays['y_win'][ids] == 1
    ids = ids[win]
    logits = predictions['relicLogits'][win]
    deltas = np.asarray(spec['relicDeltaValues'])
    records = {name: [] for name in NAMES.values()}
    row_nll_before = np.zeros(len(ids)); row_nll_after = np.zeros(len(ids))
    row_exact_before = np.ones(len(ids), dtype=bool); row_exact_after = np.ones(len(ids), dtype=bool)
    row_legal_mass = np.ones(len(ids))
    for local, row in enumerate(ids):
        for token in np.flatnonzero(arrays['y_relic_mask'][row]):
            rid, pre = map(int, arrays['relics'][row, token, :2])
            legacy = np.isin(deltas, spec['relicDeltaValuesById'][str(rid)])
            x = np.where(legacy, logits[local, token].astype(float), -np.inf)
            x -= np.max(x)
            before = x - np.log(np.exp(x).sum())
            encounter = int(arrays['global_categories'][row, list(base.GLOBAL_CATEGORY_COUNTS).index('encounter')])
            bloom = bool(np.any((arrays['relics'][row, :, 0] == base._RELIC_IDS['MARK_OF_THE_BLOOM']) & arrays['relic_mask'][row]))
            legal = np.isin(pre + deltas, list(legal_posts(rid, pre, encounter, bloom)))
            after = np.where(legal, before, -np.inf)
            after -= np.log(np.exp(after).sum())
            target = int(arrays['y_relic_delta'][row, token])
            where = np.flatnonzero(deltas == target)
            if len(where) != 1 or not np.isfinite(after[where[0]]):
                raise ValueError('observed relic target did not survive')
            bm, am = int(deltas[before.argmax()]), int(deltas[after.argmax()])
            row_nll_before[local] -= before[where[0]]
            row_nll_after[local] -= after[where[0]]
            row_exact_before[local] &= bm == target
            row_exact_after[local] &= am == target
            row_legal_mass[local] *= np.exp(before[legal]).sum()
            records[NAMES[rid]].append([np.exp(before[~legal]).sum(), not legal[before.argmax()], -before[where[0]], -after[where[0]], bm == target, am == target, target != 0, abs(bm-target), abs(am-target)])
    def summarize(values):
        if not values:
            return {'tokens': 0}
        a = np.asarray(values, dtype=float)
        changed = a[:, 6] == 1
        return {'tokens': len(a), 'illegalMassMean': float(a[:, 0].mean()), 'modeInvalidBefore': int(a[:, 1].sum()), 'modeInvalidAfter': 0, 'illegalMassAfter': 0.0,
                'nllBefore': float(a[:, 2].mean()), 'nllAfter': float(a[:, 3].mean()), 'exactBefore': float(a[:, 4].mean()), 'exactAfter': float(a[:, 5].mean()),
                'changedTokens': int(changed.sum()), 'changedExactBefore': float(a[changed, 4].mean()) if changed.any() else None,
                'changedExactAfter': float(a[changed, 5].mean()) if changed.any() else None,
                'changedMaeBefore': float(a[changed, 7].mean()) if changed.any() else None, 'changedMaeAfter': float(a[changed, 8].mean()) if changed.any() else None}
    return {'evaluation': 'reused global TEST engineering correction; no fitting',
            'vector': {'victories': len(ids), 'jointNllBefore': float(row_nll_before.mean()), 'jointNllAfter': float(row_nll_after.mean()), 'exactBefore': float(row_exact_before.mean()), 'exactAfter': float(row_exact_after.mean()), 'illegalMassMeanBefore': float((1-row_legal_mass).mean()), 'illegalMassAfter': 0.0},
            'overall': summarize([v for group in records.values() for v in group]),
            'byRelic': {name: summarize(values) for name, values in records.items()}}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--corpus', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = audit(Path(args.corpus))
    Path(args.output).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'contradictions'}))
    if result['contradictionCount'] or result['futureSilverRequired']:
        raise SystemExit('STAGE_0_GATE_FAILED')
