#!/usr/bin/env python3
"""Build units.txt for the max-backup-at-32k/64k check (PREREG.md) from the Gumbel budget run's measured costs.

usage: python3 -I make_units.py <gumbel_budget_units_dir> units.txt units_projection.tsv

One unit per (run, act, arm set) as in ../gumbel_budget_20261108 (576 (run, act) pairs x {g32mb, g64mb}), except that
a unit whose projected wall time exceeds SPLIT_UNIT_S is split: every copy of an arm fight whose projected arm CPU
exceeds SPLIT_COPY_S becomes its own unit (SEL `<floor>:<copy>`, STS_EXPERT_FIGHTS_ARM_COPIES), and the rest of the
unit's arm fights and copies stay in one unit (SEL listing them; omitted if nothing is left).

Projection, per unit of the budget run (g32mb from the g32f16 unit's gsh16+flat32000 arm, g64mb from the g64 unit):
measured wall minus the measured CPU of the arms it does not play, with the arm's CPU scaled by MB_CPU (max backup's
measured CPU ratio at 16k, 3.32 / 3.15). A split unit is projected as the unit's wall minus every arm-fight copy
(production and arm) plus production's copy 0 of every arm fight (the main line) and the selected copies. The order is
longest projected first.
"""
import collections, json, os, re, sys, tarfile

MB_CPU = 3.32 / 3.15
SPLIT_UNIT_S = 1.25 * 3600
SPLIT_COPY_S = 20 * 60
SOURCE = {'g32mb': ('g32f16', 'gsh16+flat32000'), 'g64mb': ('g64', 'gsh16+flat64000')}


def units(d):
    """{(run, act, set): (wall, fights json)} for the budget run's rc-0 units (tars read in place)."""
    out = {}
    for n in sorted(os.listdir(d)):
        if not n.endswith('.tar'):
            continue
        with tarfile.open(os.path.join(d, n)) as t:
            done = fights = None
            for m in t.getmembers():
                if m.isfile() and re.search(r'/F-[^/]+\.done$', m.name):
                    done = t.extractfile(m).read().decode()
                elif m.isfile() and m.name.endswith('.fights.json'):
                    fights = json.loads(t.extractfile(m).read())
        m = re.search(r'tag=F-(\d+)-a(\d)-(\S+) rc=(\d+) .*wall=(\d+)', done or '')
        if not m or m.group(4) != '0' or fights is None:
            raise SystemExit(f'{n}: no rc-0 .done line or no fights')
        out[(m.group(1), int(m.group(2)), m.group(3))] = (int(m.group(5)), fights)
    return out


def main():
    U = units(sys.argv[1])
    lines = []
    for (run, act, src), (wall, x) in sorted(U.items()):
        for s, (want, arm) in SOURCE.items():
            if src != want:
                continue
            fights = [f for f in x['fights'] if 'arms' in f]
            prod = {f['floor']: {r['r']: r['cpu'] for r in f['replicates']} for f in fights}
            cost = {f['floor']: {r['r']: r['cpu'] * MB_CPU for r in f['arms'][arm]} for f in fights}
            other = sum(r['cpu'] for f in fights for a, reps in f['arms'].items() if a != arm for r in reps)
            measured = sum(r['cpu'] for f in fights for r in f['arms'][arm])
            whole = wall - other - measured + sum(c for fl in cost.values() for c in fl.values())
            if whole <= SPLIT_UNIT_S:
                lines.append((whole, f'{run} {act} {s}'))
                continue
            base = wall - other - measured - sum(c for fl in prod.values() for c in fl.values()) \
                + sum(fl.get(0, 0) for fl in prod.values())
            split = [(fl, r) for fl in sorted(cost) for r in sorted(cost[fl]) if cost[fl][r] > SPLIT_COPY_S]
            for fl, r in split:
                lines.append((base + (prod[fl][r] if r else 0) + cost[fl][r], f'{run} {act} {s} {fl}:{r}'))
            rest, rest_cost = [], base
            for fl in sorted(cost):
                keep = [r for r in sorted(cost[fl]) if (fl, r) not in split]
                if not keep:
                    continue
                rest.append(str(fl) if len(keep) == len(cost[fl]) else ','.join(f'{fl}:{r}' for r in keep))
                rest_cost += sum(cost[fl][r] + (prod[fl][r] if r else 0) for r in keep)
            if rest:
                lines.append((rest_cost, f'{run} {act} {s} ' + ','.join(rest)))
    lines.sort(key=lambda t: (-t[0], t[1]))
    with open(sys.argv[2], 'w') as f:
        f.writelines(l + '\n' for _, l in lines)
    with open(sys.argv[3], 'w') as f:
        f.write('unit\tprojected_s\n')
        f.writelines(f'{l}\t{c:.0f}\n' for c, l in lines)
    by = collections.Counter(l.split()[2] for _, l in lines)
    print(f'{len(lines)} units ({dict(by)}), {sum(c for c, _ in lines) / 3600:.1f} projected lane-h, '
          f'longest {lines[0][0] / 3600:.2f} h ({lines[0][1]}), split units {sum(len(l.split()) == 4 for _, l in lines)}')


if __name__ == '__main__':
    main()
