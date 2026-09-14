#!/usr/bin/env python3
"""Freeze gold-only candidate slices without widening production support."""
import argparse
from collections import Counter
from contextlib import contextmanager
import json
from pathlib import Path
import numpy as np

from tools import combat_transition_composed as c


def is_gold_reason(reason):
    return reason.startswith('gold_mutating_') or reason == 'pre_stolen_gold_nonzero'


def branch_presence(arrays, card_id, upgraded):
    cards = arrays['cards']
    selected = ((cards[:, :, 0] == card_id) & (cards[:, :, 1] == upgraded)).any(1)
    return dict(cardId=card_id, upgraded=bool(upgraded), allCorpusRows=int(selected.sum()),
                sourceSeeds=arrays['sourceSeed'][selected].tolist(),
                fightIndices=arrays['fightIdx'][selected].tolist(),
                splitIds=arrays['split_id'][selected].tolist(),
                wins=arrays['y_win'][selected].tolist(),
                countsBySplit={k: int((selected & (arrays['split_id'] == i)).sum())
                               for i, k in enumerate(('train', 'validation', 'test'))})


def presence_only(output):
    from tools import combat_transition_composed_evaluate as e
    if output.exists():
        raise ValueError('refusing to overwrite branch presence')
    hashes = e.verify_data()
    with np.load(e.PREPARED / 'prepared.npz') as arrays:
        presence = branch_presence(arrays, c.base._CARD_IDS['TRANSMUTATION'], True)
    result = dict(schema='combat_gold_branch_presence_v1', baseline=e.snapshot(), hashes=hashes,
                  branch=presence, training=False, gameplay=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(presence), flush=True)


@contextmanager
def audit_without_gold_gate():
    """Reveal later gates on original visible inputs; restore even on failure."""
    original = c.base.supported_reasons
    c.base.supported_reasons = lambda pi, pre: [r for r in original(pi, pre) if not is_gold_reason(r)]
    try:
        yield
    finally:
        c.base.supported_reasons = original


def audit(output):
    from tools import combat_transition_composed_evaluate as e
    if output.exists():
        raise ValueError('refusing to overwrite gold audit')
    hashes = e.verify_data()
    split = json.loads(e.SPLIT.read_text())
    membership = {int(s): k for k, values in split['members'].items() for s in values}
    models = c.FrozenModels('cpu')
    tables = {}
    hidden = Counter()
    targets = {k: Counter() for k in split['members']}
    source_sets = {k: set() for k in split['members']}
    gold_only = 0
    for index, row in enumerate(c.base.iter_rows(e.CORPUS)):
        pre, post = row['transition']['pre'], row['transition']['post']
        pi = row['predictorInput']
        reasons = c.full_support_reasons(pre, pi, models)
        if not reasons or not all(is_gold_reason(r) for r in reasons):
            continue
        gold_only += 1
        with audit_without_gold_gate():
            later = c.full_support_reasons(pre, pi, models)
        hidden.update(later)
        if later:
            continue
        source = int(row['sourceSeed'])
        bucket = membership[source]
        source_sets[bucket].add(source)
        gain = post['gold'] - pre['gold']
        labels = ['all'] + reasons
        if pi['globals']['encounter'] in c.base.GOLD_MUTATING_ENCOUNTER_IDS:
            labels.append('encounter:' + models.encounter_names[pi['globals']['encounter']])
        for card in pi['cards']:
            if card['cardId'] in c.base.GOLD_MUTATING_CARD_IDS:
                labels.append('card:' + str(card['cardId']) + ':upgraded:' + str(card['upgraded']))
        for name in ('BLOODY_IDOL', 'ECTOPLASM'):
            if any(r['id'] == c.base._RELIC_IDS[name] for r in pre['relics']):
                labels.append('relic:' + name)
        for label in set(labels):
            table = tables.setdefault(label, {k: Counter() for k in split['members']})[bucket]
            table['rows'] += 1
            table['victories'] += row['transition']['combatOutcome'] == c.base.WIN
            table['deaths'] += row['transition']['combatOutcome'] == c.base.DEATH
            table['positiveDeltaGold'] += gain > 0
            table['negativeDeltaGold'] += gain < 0
            table['stolenGoldNonzero'] += post['stolenGold'] != 0
            table['preGoldBelow90'] += pre['gold'] < 90
        targets[bucket][str((gain, post['stolenGold']))] += 1
        if (index + 1) % 50000 == 0:
            print(f'gold audit corpus index {index + 1}', flush=True)
    if gold_only != 71367:
        raise ValueError('gold-only slice differs from frozen census')
    missing = sorted(set(targets['test']) - set(targets['train']))
    result = dict(schema='combat_gold_source_inventory_v1', baseline=e.snapshot(), hashes=hashes,
                  goldOnlyRows=gold_only, laterSupportReasons=dict(hidden), tables=tables,
                  uniqueCandidateSources={k: len(v) for k, v in source_sets.items()},
                  jointTargets=targets, testJointTargetsAbsentFromTrain=missing,
                  absentTrainTestRows=sum(targets['test'][k] for k in missing),
                  training=False, gameplay=False, supportChanged=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('hashes', 'jointTargets', 'tables')}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--presence-only', action='store_true')
    args = parser.parse_args()
    (presence_only if args.presence_only else audit)(args.output)
