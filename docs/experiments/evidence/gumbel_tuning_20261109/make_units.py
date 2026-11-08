#!/usr/bin/env python3
"""Packages and units of the Gumbel tuning experiment (PREREG.md) from the scout run.

usage: python3 -I make_units.py <scout_units_dir> <stage> [out_dir]
  stage: screen (stage 1), combine (stage 2) or confirm (stage 3); combine and confirm also need ARMS_<stage> in
  sets_<stage>.arms (one arm id per line, ids from arms.tsv) next to this script.
Writes packages.tsv (always), and for the stage units_<stage>.txt, sets_<stage>.tsv and units_<stage>_projection.tsv
into out_dir (default: next to this script).

Scout: one `SEED 3 scout` unit per seed: the production main line through act 3 and production (arm `prod`) on
copies 0-3 of every elite (E) and boss (B) fight of acts 1-3, the arm fights.

Packages, by seed order over the scouted D0 seeds: screening = the first seeds whose arm fights reach 1,200, its
design subset = the first seeds of it whose arm fights reach 300, combination = the next seeds to 600, confirmation =
the next seeds to 1,200. A seed whose scout unit is not rc 0 is skipped (listed as 'failed').

Units: one per (seed, act with arm fights, arm set[, copy selection]). Projected cost of one arm on one copy of a
fight = production's mean CPU per copy there (the scout's prod arm) x SIMS x decisions / simulations of those copies
(the arm searches a flat SIMS per decision, production fewer with the learned stop) x OVERHEAD (larger trees cost
more per simulation; the smoke measured 0.95-1.64x, mean 1.26x). The main line of a unit through act a costs the scout's main-line copies through act a
plus that share of the scout's time outside fights. Arms are packed into sets so that a unit stays under CAP; an act
whose single-arm cost exceeds the room left is split by copy selection (each fight whose four arm copies exceed half
of it one unit per copy, `<floor>:<copy>`; the other fights together).
"""
import collections, json, math, os, re, sys, tarfile

SIMS = 16000
OVERHEAD = 1.5
FALLBACK_RATIO = 3.32   # §772's Gumbel 16k + mb4 over production, for a fight without production simulations
CAP = 50 * 60
K = 4
TARGETS = (('screen', 1200), ('combine', 600), ('confirm', 1200))
DESIGN_FIGHTS = 300
HERE = os.path.dirname(os.path.abspath(__file__))
PREFIX = {'screen': 'scr', 'combine': 'cmb', 'confirm': 'cnf'}   # arm set ids, unique across the stages


def scout(d):
    """{seed: (rc, wall, fights json)} from the scout units' .done and .fights.json (tars read in place)."""
    done, fights = {}, {}
    for root, _, fs in os.walk(d):
        for n in sorted(fs):
            p = os.path.join(root, n)
            items = []
            if n.endswith('.tar'):
                with tarfile.open(p) as t:
                    for m in t.getmembers():
                        if m.isfile() and (m.name.endswith('.done') or m.name.endswith('.fights.json')):
                            items.append((os.path.basename(m.name), t.extractfile(m).read().decode()))
            elif n.endswith('.done') or n.endswith('.fights.json'):
                items.append((n, open(p).read()))
            for name, text in items:
                m = re.match(r'S-(\d+)-a3-scout\.(done|fights\.json)$', name)
                if not m:
                    continue
                if m.group(2) == 'done':
                    x = re.search(r'rc=(\d+) .*wall=(\d+)', text)
                    done[int(m.group(1))] = (int(x.group(1)), int(x.group(2)))
                else:
                    fights[int(m.group(1))] = json.loads(text)
    out = {}
    for seed, (rc, wall) in done.items():
        out[seed] = (rc if seed in fights or rc else 99, wall, fights.get(seed))
    return out


def arm_fights(x):
    return [f for f in x['fights'] if f['room'] in ('E', 'B') and f['act'] <= 3]


def arm_copy_cpu(f):
    """Projected CPU of one arm on one copy of a scouted fight from the scout's `prod` arm copies (else the main
    line's copy 0): production's mean CPU per copy x SIMS x decisions / simulations x OVERHEAD."""
    reps = f.get('arms', {}).get('prod') or f['replicates'][:1]
    cpu = sum(r['cpu'] for r in reps) / len(reps)
    sims, dec = sum(r['simulations'] for r in reps), sum(r['decisions'] for r in reps)
    ratio = SIMS * dec / sims if sims > 0 else FALLBACK_RATIO
    return cpu * ratio * OVERHEAD


def packages(S):
    rows, it = [], iter(TARGETS)
    stage, target = next(it)
    count = design = 0
    for seed in sorted(S):
        rc, wall, x = S[seed]
        if rc != 0:
            rows.append((seed, 'failed', 0))
            continue
        if stage is None:
            break
        n = len(arm_fights(x))
        tag = stage
        if stage == 'screen' and design < DESIGN_FIGHTS:
            tag = 'screen_design'
            design += n
        rows.append((seed, tag, n))
        count += n
        if count >= target:
            stage, target = next(it, (None, None))
            count = 0
    if stage is not None:
        raise SystemExit(f'not enough scouted seeds: stage {stage} has {count} of {target} arm fights')
    return rows


def arm_ids():
    ids = []
    with open(os.path.join(HERE, 'arms.tsv')) as f:
        for line in f:
            if line.startswith('#') or line.startswith('arm\t'):
                continue
            ids.append(line.split('\t')[0])
    return ids


def main():
    S = scout(sys.argv[1])
    stage = sys.argv[2]
    out = sys.argv[3] if len(sys.argv) > 3 else HERE
    P = packages(S)
    with open(os.path.join(out, 'packages.tsv'), 'w') as f:
        f.write('seed\tpackage\tarm_fights\n')
        f.writelines(f'{s}\t{p}\t{n}\n' for s, p, n in P)
    ids = arm_ids()
    if stage == 'screen':
        want = {'screen_design': [i for i in ids if i.startswith('d')] + ['ctl', 'gnr'], 'screen': ['ctl', 'gnr']}
    else:
        with open(os.path.join(HERE, f'sets_{stage}.arms')) as f:
            arms = [l.strip() for l in f if l.strip() and not l.startswith('#')]
        unknown = [a for a in arms if a not in ids]
        if unknown:
            raise SystemExit(f'unknown arms {unknown}')
        want = {stage: arms}
    sets, lines = {}, []

    def set_id(arms):
        key = ','.join(arms)
        if key not in sets:
            sets[key] = f'{PREFIX[stage]}{len(sets) + 1:03d}'
        return sets[key]

    for seed, pkg, _ in P:
        if pkg not in want:
            continue
        rc, wall, x = S[seed]
        arms = want[pkg]
        by_act = collections.defaultdict(list)
        for fgt in arm_fights(x):
            by_act[fgt['act']].append(fgt)
        all_cpu = sum(r['cpu'] for f in x['fights'] for r in f['replicates'] + f.get('arms', {}).get('prod', []))
        ooc = max(0.0, x['sec'] - all_cpu)   # the scout's time outside fights
        for act, fs in sorted(by_act.items()):
            upto = [f for f in x['fights'] if f['act'] <= act]
            main = ooc * len(upto) / max(1, len(x['fights'])) + sum(r['cpu'] for f in upto for r in f['replicates'])
            budget = max(CAP - main, 60)
            copy_cost = {fgt['floor']: arm_copy_cpu(fgt) for fgt in fs}
            whole = sum(K * c for c in copy_cost.values())
            if whole <= budget:
                sels = [('', whole)]
            else:
                long_ = [fl for fl, c in copy_cost.items() if K * c > budget / 2]
                sels = [(f'{fl}:{r}', copy_cost[fl]) for fl in sorted(long_) for r in range(K)]
                rest = [fl for fl in sorted(copy_cost) if fl not in long_]
                if rest:
                    sels.append((','.join(map(str, rest)), sum(K * copy_cost[fl] for fl in rest)))
            for sel, cost in sels:
                per = max(1, int(budget // cost)) if cost > 0 else len(arms)
                groups = math.ceil(len(arms) / per)
                size = math.ceil(len(arms) / groups)
                for g in range(groups):
                    chunk = arms[g * size:(g + 1) * size]
                    if not chunk:
                        continue
                    proj = main + cost * len(chunk)
                    lines.append((proj, f'{seed} {act} {set_id(chunk)}' + (f' {sel}' if sel else '')))
    lines.sort(key=lambda t: (-t[0], t[1]))
    with open(os.path.join(out, f'units_{stage}.txt'), 'w') as f:
        f.write(f'# SEED ACT SET [SEL]: {len(lines)} units of stage {stage} (make_units.py)\n')
        f.writelines(l + '\n' for _, l in lines)
    with open(os.path.join(out, f'sets_{stage}.tsv'), 'w') as f:
        f.writelines(f'{v}\t{k}\n' for k, v in sets.items())
    with open(os.path.join(out, f'units_{stage}_projection.tsv'), 'w') as f:
        f.write('unit\tprojected_s\n')
        f.writelines(f'{l}\t{c:.0f}\n' for c, l in lines)
    tally = collections.Counter(p for _, p, _ in P)
    fights = collections.Counter()
    for _, p, n in P:
        fights[p] += n
    print(f'packages {dict(tally)}, arm fights {dict(fights)}')
    print(f'{len(lines)} units, {len(sets)} arm sets, {sum(c for c, _ in lines) / 3600:.1f} projected lane-h, '
          f'longest {lines[0][0] / 3600:.2f} h ({lines[0][1]})' if lines else 'no units')


if __name__ == '__main__':
    main()
