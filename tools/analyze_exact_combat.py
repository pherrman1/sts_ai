#!/usr/bin/env python3
"""Summarize exact_combat_solver JSONL output (research tooling).

usage: analyze_exact_combat.py OUT.jsonl [OUT2.jsonl ...] [--examples N]

Per config: searched roots, agreement with the exact optimum, regret in the
solver's objective (mean, per fight, share of roots with regret > 1 / > 5),
the same in expected end HP (0 on death) and win probability, and the largest
mistakes. Fights the solver gave up on are counted, not scored.
"""
import argparse
import collections
import json
import math
import random


def boot_ci(values, clusters, reps=2000, seed=20261021):
    """Seed-clustered bootstrap 95% CI of the mean."""
    by = collections.defaultdict(list)
    for v, c in zip(values, clusters):
        by[c].append(v)
    keys = list(by)
    if len(keys) < 2:
        return (float('nan'), float('nan'))
    rng = random.Random(seed)
    means = []
    for _ in range(reps):
        s = n = 0
        for _ in keys:
            vs = by[keys[rng.randrange(len(keys))]]
            s += sum(vs)
            n += len(vs)
        means.append(s / n if n else 0)
    means.sort()
    return means[int(0.025 * reps)], means[int(0.975 * reps) - 1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='+')
    ap.add_argument('--examples', type=int, default=8)
    args = ap.parse_args()
    rows = collections.defaultdict(list)
    fights = collections.defaultdict(list)
    for path in args.files:
        with open(path) as f:
            for line in f:
                r = json.loads(line)
                key = (r['config'], r.get('objective', 'silver'))
                (fights if r.get('summary') else rows)[key].append(r)
    for key in sorted(set(rows) | set(fights)):
        rs, fs = rows[key], fights[key]
        print(f"== config={key[0]} objective={key[1]}")
        done = [f for f in fs if not f.get('infeasible') and 'failure' not in f]
        print(f"fights {len(fs)}: solved {len(done)}, infeasible {sum(1 for f in fs if f.get('infeasible'))}, "
              f"failed {sum(1 for f in fs if 'failure' in f and not f.get('infeasible'))}; "
              f"Silver won {sum(1 for f in fs if f['outcome'] == 'win')}")
        ok = {f['seed'] for f in done}
        rs = [r for r in rs if r['seed'] in ok]
        if not rs:
            continue
        multi = [r for r in rs if len(r['actions']) > 1]
        seeds = [r['seed'] for r in multi]
        reg = [r['regret'] for r in multi]
        agree = [1.0 if r['optimal'] else 0.0 for r in multi]
        hp = [r['actions'][r['best']]['hp'] - r['actions'][r['chosen']]['hp'] for r in multi]
        win = [r['actions'][r['best']]['win'] - r['actions'][r['chosen']]['win'] for r in multi]
        lo, hi = boot_ci(agree, seeds)
        print(f"roots with >1 action: {len(multi)}; agreement {100 * sum(agree) / len(agree):.1f}% "
              f"[{100 * lo:.1f}, {100 * hi:.1f}]")
        lo, hi = boot_ci(reg, seeds)
        print(f"regret per root: mean {sum(reg) / len(reg):.3f} [{lo:.3f}, {hi:.3f}]; "
              f"> 1: {sum(1 for x in reg if x > 1)}, > 5: {sum(1 for x in reg if x > 5)}")
        per_fight = collections.defaultdict(float)
        for r in multi:
            per_fight[r['seed']] += r['regret']
        pf = list(per_fight.values())
        print(f"regret per fight (sum over its roots = V*(start) - V(Silver) in expectation): "
              f"mean {sum(pf) / len(pf):.3f}, max {max(pf):.3f}")
        lo, hi = boot_ci(hp, seeds)
        print(f"end-HP loss vs the optimum's action per root: mean {sum(hp) / len(hp):.3f} [{lo:.3f}, {hi:.3f}]; "
              f"per fight {sum(hp) / len(pf):.3f}")
        print(f"win-probability loss per fight: {100 * sum(win) / len(pf):.3f} pp")
        by_turn = collections.defaultdict(list)
        for r in multi:
            by_turn[min(r['turn'] + 1, 6)].append(r)
        print("by game turn (1-based): " + "; ".join(
            f"t{t}{'+' if t == 6 else ''} n={len(v)} agree {100 * sum(1 for r in v if r['optimal']) / len(v):.0f}% "
            f"regret {sum(r['regret'] for r in v) / len(v):.3f}" for t, v in sorted(by_turn.items())))
        by_enc = collections.defaultdict(list)
        for r in multi:
            by_enc[r['encounter']].append(r)
        print("by encounter: " + "; ".join(
            f"{e} n={len(v)} agree {100 * sum(1 for r in v if r['optimal']) / len(v):.0f}% "
            f"regret {sum(r['regret'] for r in v) / len(v):.3f}" for e, v in sorted(by_enc.items())))
        worst = sorted(multi, key=lambda r: -r['regret'])[:args.examples]
        for r in worst:
            a, b = r['actions'][r['chosen']], r['actions'][r['best']]
            print(f"  seed {r['seed']} {r['encounter']} game turn {r['turn'] + 1} hp {r['hp']} energy {r['energy']}: "
                  f"Silver '{a['label']}' q={a['q']:.2f} (visits {a['visits']}) vs best '{b['label']}' q={b['q']:.2f} "
                  f"(visits {b['visits']}); regret {r['regret']:.2f}, HP {a['hp']:.1f} vs {b['hp']:.1f}")
        print()


if __name__ == '__main__':
    main()
