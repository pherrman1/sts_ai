#!/usr/bin/env python3
"""Boss-relic fork pilot (#856): roots of a source game and the fork-equals-source check.

  forks.py plan SOURCE.trace.jsonl              one ACT:CHOICE line per untaken option at each act-1/2 root
  forks.py check SOURCE.trace.jsonl FORK.trace.jsonl ACT:CHOICE
  forks.py roots SOURCE.trace.jsonl             the roots as JSON (act, offered relics, taken choice)

A trace path also opens PATH.gz when PATH is missing. CHOICE is 0-2 (the offered relic in screen order) or 3 (skip).
"""
import collections, gzip, json, os, sys

SKIP = 3


def rows(path):
    if not os.path.exists(path) and os.path.exists(path + '.gz'):
        path += '.gz'
    opener = gzip.open if path.endswith('.gz') else open
    with opener(path, 'rt') as f:
        return [json.loads(line) for line in f if line.strip()]


def is_root(row):
    return row.get('kind') == 'ooc' and row['pre']['screen'] == 'BOSS_RELIC' and row['pre']['act'] in (1, 2)


def taken(row):
    """Index of the relic the step took (3 = skip), from the relic multisets before and after."""
    offered = row['offer']['relics']
    gained = collections.Counter(row['post']['relics']) - collections.Counter(row['pre']['relics'])
    hits = [i for i, r in enumerate(offered) if gained[r] > 0]
    if len(hits) > 1:
        raise SystemExit(f"ambiguous boss-relic step at act {row['pre']['act']}: {offered} gained {dict(gained)}")
    return hits[0] if hits else SKIP


def roots(trace):
    out = []
    for i, row in enumerate(trace):
        if is_root(row):
            out.append({'index': i, 'act': row['pre']['act'], 'offered': row['offer']['relics'],
                        'taken': taken(row), 'by': row['by']})
    acts = [r['act'] for r in out]
    if len(acts) != len(set(acts)):
        raise SystemExit(f'more than one boss-relic root in an act: {acts}')
    return out


def plan(trace):
    for r in roots(trace):
        for choice in list(range(len(r['offered']))) + [SKIP]:
            if choice != r['taken']:
                print(f"{r['act']}:{choice}")


def check(source, fork, force):
    act, choice = (int(x) for x in force.split(':'))
    root = next((r for r in roots(source) if r['act'] == act), None)
    if root is None:
        raise SystemExit(f'source has no act-{act} boss-relic root')
    i = root['index']
    if len(fork) <= i or fork[:i] != source[:i]:
        n = next((k for k in range(min(i, len(fork))) if fork[k] != source[k]), min(i, len(fork)))
        raise SystemExit(f'fork differs from the source before its root (first different trace row {n} of {i})')
    f = fork[i]
    if not is_root(f) or f['by'] != 'forced_boss_relic' or f['pre'] != source[i]['pre'] \
            or f['offer'] != source[i]['offer']:
        raise SystemExit('fork row at the root is not the forced source root')
    if taken(f) != choice:
        raise SystemExit(f'fork took {taken(f)}, forced {choice}')
    print(json.dumps({'ok': True, 'act': act, 'choice': choice, 'sourceTaken': root['taken'], 'prefixRows': i}))


def main(argv):
    if len(argv) == 3 and argv[1] == 'plan':
        plan(rows(argv[2]))
    elif len(argv) == 3 and argv[1] == 'roots':
        print(json.dumps(roots(rows(argv[2]))))
    elif len(argv) == 5 and argv[1] == 'check':
        check(rows(argv[2]), rows(argv[3]), argv[4])
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main(sys.argv)
