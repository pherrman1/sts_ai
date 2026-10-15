#!/usr/bin/env python3
"""Seed-free remaining-support census and gold-stage evidence inventory."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path

from tools import combat_transition_composed as c


def trace_census(folder):
    path = folder / 'official/treatment.csv.mcts.csv.support.jsonl'
    trace = folder / 'official/treatment.csv.mcts.csv'
    summaries = [json.loads(line) for line in path.read_text().splitlines()]
    with trace.open() as stream:
        raw_rows = list(csv.DictReader(stream))
        rows = {int(r['seed']): r for r in raw_rows}
    expected = set(range(980000, 980064))
    if len(summaries) != 64 or len(raw_rows) != 64 or set(rows) != expected or {r['seed'] for r in summaries} != expected:
        raise ValueError('trace source accounting differs')
    counts = Counter()
    for summary in summaries:
        reasons = summary['reasons']
        if any(type(v) is not int or v < 0 for v in reasons.values()):
            raise ValueError('invalid abort count')
        if sum(reasons.values()) != int(rows[summary['seed']]['unsupportedCombats']):
            raise ValueError('abort reasons do not reconcile')
        counts.update(reasons)
    return dict(hashes={str(p): c.base.sha256(p) for p in (path, trace)},
                reasons=dict(counts.most_common()),
                unsupportedImaginedCombats=sum(int(r['unsupportedCombats']) for r in rows.values()),
                supportAbortedRoots=sum(int(r['mctsSupportAborts']) for r in rows.values()),
                stateReplayAvailable=False,
                limitation='Saved summaries contain one first-failure reason per aborted root, no imagined precombat states or joint reasons.')


def census(output, trace_folder):
    from tools import combat_transition_composed_evaluate as e
    if output.exists():
        raise ValueError('refusing to overwrite frozen census')
    hashes = e.verify_data()
    arrays, _ = c.base._load_prepared(e.PREPARED)
    models = c.FrozenModels('cpu')
    split = json.loads(e.SPLIT.read_text())
    membership = {int(s): i for i, k in enumerate(('train', 'validation', 'test')) for s in split['members'][k]}
    if len(membership) != sum(len(v) for v in split['members'].values()):
        raise ValueError('overlapping splits')
    groups = {name: dict(rows=0, unsupported=0, sources=set(), unsupportedSources=set(),
                         reasons=Counter(), combinations=Counter(), encounter=Counter(),
                         act=Counter(), room=Counter()) for name in ('all', 'TEST')}
    gold = {'all': Counter(), 'TEST': Counter()}
    gold_targets = {'all': Counter(), 'TEST': Counter()}
    other_mutations = Counter()
    for index, row in enumerate(c.base.iter_rows(e.CORPUS)):
        source = int(row['sourceSeed'])
        if index >= len(arrays['sourceSeed']) or (source, int(row['fightIdx'])) != (int(arrays['sourceSeed'][index]), int(arrays['fightIdx'][index])) or membership.get(source) != int(arrays['split_id'][index]):
            raise ValueError('prepared row/source/split mismatch')
        pre, post = row['transition']['pre'], row['transition']['post']
        pi = row['predictorInput']
        if c.base.supported_for_surrogate(pi, pre) != bool(arrays['supported'][index]):
            raise ValueError('prepared eligibility differs')
        reasons = sorted(set(c.full_support_reasons(pre, pi, models)))
        labels = ('all', 'TEST') if membership[source] == 2 else ('all',)
        gold_reason = lambda r: r.startswith('gold_mutating_') or r == 'pre_stolen_gold_nonzero'
        for label in labels:
            table = groups[label]
            table['rows'] += 1
            table['sources'].add(source)
            if reasons:
                table['unsupported'] += 1
                table['unsupportedSources'].add(source)
                table['reasons'].update(reasons)
                table['combinations']['+'.join(reasons)] += 1
                for name, field in (('encounter', 'encounter'), ('act', 'act'), ('room', 'roomClass')):
                    table[name][str(pi['globals'][field])] += 1
            if any(gold_reason(r) for r in reasons):
                gold[label]['excludedRows'] += 1
                if all(gold_reason(r) for r in reasons):
                    gold[label]['goldOnlyRows'] += 1
                    gold[label]['outcome:' + str(row['transition']['combatOutcome'])] += 1
                    target = (post['gold'] - pre['gold'], post['stolenGold'])
                    gold_targets[label][str(target)] += 1
                    gold[label]['goldChanged'] += target[0] != 0
                    gold[label]['stolenGoldChanged'] += post['stolenGold'] != pre['stolenGold']
        if reasons and all(gold_reason(r) for r in reasons) and row['transition']['combatOutcome'] == c.base.WIN:
            for field in c.base.COPY_THROUGH_KEYS:
                if field not in ('gold', 'stolenGold') and pre[field] != post[field]:
                    other_mutations[field] += 1
        if (index + 1) % 50000 == 0:
            print(f'census {index + 1}/510030', flush=True)
    if groups['all']['rows'] != 510030 or groups['all']['sources'] != set(membership):
        raise ValueError('incomplete corpus/source census')
    if groups['all']['unsupported'] != 96231 or groups['TEST']['rows'] != 51441 or groups['TEST']['unsupported'] != 9987:
        raise ValueError('baseline full support differs from #179')
    for table in groups.values():
        for name in ('sources', 'unsupportedSources'):
            table[name] = len(table[name])
        for name in ('reasons', 'combinations', 'encounter', 'act', 'room'):
            table[name] = dict(table[name].most_common())
        table['supported'] = table['rows'] - table['unsupported']
        table['supportPercent'] = 100 * table['supported'] / table['rows']
    result = dict(schema='remaining_combat_support_census_v1', baseline=e.snapshot(), hashes=hashes,
                  groups=groups, goldStageInventory=gold, goldJointTargets=gold_targets,
                  goldOnlyVictoryOtherCopyThroughMutations=other_mutations,
                  trace=trace_census(trace_folder), training=False, gameplay=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(groups=groups, gold=gold, otherMutations=other_mutations, trace=result['trace'])), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--trace-folder', type=Path, default=c.base._ROOT / 'docs/experiments/evidence/live_ooc_mcts_fresh64_10000_2026-09-14')
    args = parser.parse_args()
    census(args.output, args.trace_folder)
