#!/usr/bin/env python3
"""Freeze a deterministic, provenance-keyed Searcher3 CRN state manifest."""
import argparse, csv, hashlib
from collections import defaultdict


ELITE_ENCOUNTERS = frozenset({
    'GREMLIN_NOB',
    'LAGAVULIN',
    'THREE_SENTRIES',
    'GREMLIN_LEADER',
    'SLAVERS',
    'BOOK_OF_STABBING',
    'GIANT_HEAD',
    'NEMESIS',
    'REPTOMANCER',
})


def encounter_class(row):
    name = (row.get('encounterName') or row.get('encounter') or '').upper()
    if row.get('isBoss') == '1' or 'BOSS' in name:
        return 'boss'
    if name in ELITE_ENCOUNTERS:
        return 'elite'
    return 'ordinary'


def key(row):
    return (int(row['seed']), int(row['fightIdx']), int(row['decIdx']), int(row['obsHash']))


def select(rows, target):
    # Parent markers are the captured decision states; leaf rows are ignored.
    unique = {}
    for row in rows:
        if int(row.get('frontierType', 0)) != -1:
            continue
        unique[key(row)] = row
    groups = defaultdict(list)
    for row in unique.values():
        groups[(encounter_class(row), int(row.get('act') or 0), int(row['seed']))].append(row)
    for values in groups.values():
        values.sort(key=lambda r: (int(r['fightIdx']), int(r['decIdx']), int(r['obsHash'])))
    classes = ('boss', 'elite', 'ordinary')
    acts_by_class = {
        cls: sorted({act for group, act, seed in groups if group == cls})
        for cls in classes
    }
    act_cursor = {cls: 0 for cls in classes}
    seeds_by_class_act = {
        (cls, act): sorted({seed for group, group_act, seed in groups
                            if group == cls and group_act == act})
        for cls in classes for act in acts_by_class[cls]
    }
    seed_cursor = {(cls, act): 0 for cls in classes for act in acts_by_class[cls]}
    chosen = []
    while len(chosen) < target:
        made_progress = False
        for cls in classes:
            acts = acts_by_class[cls]
            if not acts:
                continue
            skipped_acts = 0
            while skipped_acts < len(acts):
                act = acts[act_cursor[cls]]
                seeds = seeds_by_class_act[(cls, act)]
                skipped_seeds = 0
                while skipped_seeds < len(seeds) and not groups[
                        (cls, act, seeds[seed_cursor[(cls, act)]])]:
                    seed_cursor[(cls, act)] = (seed_cursor[(cls, act)] + 1) % len(seeds)
                    skipped_seeds += 1
                if skipped_seeds < len(seeds):
                    break
                act_cursor[cls] = (act_cursor[cls] + 1) % len(acts)
                skipped_acts += 1
            if skipped_acts == len(acts):
                continue
            seed = seeds[seed_cursor[(cls, act)]]
            chosen.append(groups[(cls, act, seed)].pop(0))
            seed_cursor[(cls, act)] = (seed_cursor[(cls, act)] + 1) % len(seeds)
            act_cursor[cls] = (act_cursor[cls] + 1) % len(acts)
            made_progress = True
            if len(chosen) == target:
                break
        if not made_progress:
            break
    return chosen


def write_manifest(rows, output, source_csv, target):
    rule = ('round_robin encounter_class(boss,elite,ordinary), act within class, '
            'source_seed within act/class; sorted fightIdx,decIdx,obsHash')
    fields = ['source_seed', 'fight_idx', 'decision_idx', 'state_id', 'encounter',
              'floor', 'act', 'isBoss', 'binaryOffset', 'binarySize',
              'selection_rule', 'source_csv_sha256']
    digest = hashlib.sha256()
    with open(source_csv, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(block)
    with open(output, 'w', newline='') as f:
        out = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        out.writeheader()
        for r in rows:
            out.writerow({
                'source_seed': r['seed'], 'fight_idx': r['fightIdx'],
                'decision_idx': r['decIdx'], 'state_id': r['obsHash'],
                'encounter': r.get('encounterName', ''), 'floor': r.get('floor', ''),
                'act': r.get('act', ''), 'isBoss': r.get('isBoss', ''),
                'binaryOffset': r.get('binaryOffset', ''), 'binarySize': r.get('binarySize', ''),
                'selection_rule': rule, 'source_csv_sha256': digest.hexdigest()})


def self_test():
    for act, name in ((1, 'GREMLIN_NOB'), (2, 'SLAVERS'), (3, 'NEMESIS')):
        row = {'encounterName': name, 'isBoss': '0', 'act': str(act)}
        assert encounter_class(row) == 'elite'

    rows = []
    for seed, name, boss, act in (
        (0, 'SLIME_BOSS', '1', 1), (1, 'SLIME_BOSS', '1', 2),
        (2, 'GREMLIN_NOB', '0', 1), (3, 'SLAVERS', '0', 2),
        (4, 'CULTIST', '0', 1), (5, 'CULTIST', '0', 2),
    ):
        rows.append({'seed': str(seed), 'fightIdx': '0', 'decIdx': '0', 'obsHash': str(seed + 10),
                     'frontierType': '-1', 'encounterName': name, 'isBoss': boss,
                     'floor': '1', 'act': str(act), 'binaryOffset': '4', 'binarySize': '10'})
    chosen = select(rows, 6)
    assert [encounter_class(r) for r in chosen] == [
        'boss', 'elite', 'ordinary', 'boss', 'elite', 'ordinary']
    assert [int(r['seed']) for r in chosen] == [0, 2, 4, 1, 3, 5]
    assert [int(r['act']) for r in chosen] == [1, 1, 1, 2, 2, 2]
    assert len({key(r) for r in chosen}) == 6
    print('select_s3_crn_states self-test PASS')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('frontier_csv', nargs='?')
    p.add_argument('manifest_csv', nargs='?')
    p.add_argument('--states', type=int, default=32)
    p.add_argument('--self-test', action='store_true')
    args = p.parse_args()
    if args.self_test:
        self_test(); return
    if not args.frontier_csv or not args.manifest_csv:
        p.error('frontier_csv and manifest_csv are required')
    with open(args.frontier_csv, newline='') as f:
        rows = select(list(csv.DictReader(f)), args.states)
    if len(rows) < args.states:
        p.error(f'only {len(rows)} eligible parent states available; requested {args.states}')
    write_manifest(rows, args.manifest_csv, args.frontier_csv, args.states)
    print(f'wrote {len(rows)} states to {args.manifest_csv}')


if __name__ == '__main__':
    main()
