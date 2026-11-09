#!/usr/bin/env python3
"""Gumbel tuning experiment (PREREG.md): analysis of one stage.

usage: python3 -I analyze.py <stage> <scout_dir> <units_dir> [out.json]
  stage: screen, combine or confirm. scout_dir holds the scout units (S-<seed>-a3-scout.*), units_dir the stage's
  units (S-<seed>-a<act>-<set>[-<sel>].*); tars are read in place, extracted files work too. packages.tsv,
  arms.tsv and sets_*.tsv come from next to this script.

Definitions as ../gumbel_mb_budget_20261108/analyze.py: HP lost by a copy = entry HP - exit HP, 0 exit HP on a
loss, the second Act-3 boss (floor 51) exit inverted for the Act-4 heal; a fight's value for an arm = mean over its
4 copies; intervals = seed-clustered bootstrap (10,000 resamples, seed 20261109). Copies are merged per (seed,
floor, arm, copy) across units and must agree where a copy appears twice (`conflicts`). Reproduction: every unit's
production copy 0 of a fight equals the scout's copy 0 there (won, exitHp, exitMaxHp, turns, decisions, simulations,
potionsUsed) and the unit's fights up to its act are the scout's (floor and encounter). Gate: the share of compared
copy-0 fights that equal the scout's (a fight the scout lacks counts as differing) and the share of units with the
scout's fights must both be >= 99%; otherwise `reproduction_gate.verdict` is NOT_PAIRED and every verdict below is
NOT_PAIRED (the descriptive one kept as `descriptive_verdict`). Units whose .done line has rc != 0 are excluded; a fight missing any copy of any arm its package plays is dropped (`missing_arm`), as is a
fight with an invalid copy.

screen: main effect of each design factor = mean over fights of (mean of the 16 design arms at the factor's high
level - mean of the 16 at its low level), 95% interval; a factor is ACTIVE when the interval excludes 0 (better
level = the sign). Two-factor interactions are reported by alias group (resolution IV: groups of aliased pairs).
Curvature = mean of the 32 design arms - control; the control sits at an end of noise (C, +1) and halving (D, -1),
so this raw value also holds -1/2 main(C) + 1/2 main(D), and `adjusted` adds back 1/2 x main effect x control level
for every factor where the control is not at 0. gnr - control on every screening fight (design subset included),
95%: GNR_HELPS / GNR_HURTS / GNR_INCONCLUSIVE. Each design arm - control on the design fights, and control -
production (the scout's `prod` arm on the same copy seeds) on every screening fight (secondary).
combine and confirm: every arm - control (combine 95%; confirm 97.5%, PREREG's pairs). confirm labels each pair:
hi < 0 TUNED_TEACHER_BETTER, lo > 0 TUNED_TEACHER_WORSE, lo > -0.3 NO_TUNING_GAIN, otherwise INCONCLUSIVE.
"""
import collections, itertools, json, os, random, re, statistics as st, sys, tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
K = 4
COPY_KEYS = ('won', 'exitHp', 'exitMaxHp', 'turns', 'decisions', 'simulations', 'potionsUsed')
SEED = 20261109
REPS = 10000
GATE = 0.99
NO_GAIN = -0.3


def before_act4_heal(exit_hp, max_hp):
    for h in range(exit_hp, -1, -1):
        if h + int((max_hp - h) * 0.75 + 0.5) == exit_hp:
            return h
    return exit_hp


def files(d):
    for root, _, fs in os.walk(d):
        for n in sorted(fs):
            p = os.path.join(root, n)
            if n.endswith('.tar'):
                with tarfile.open(p) as t:
                    for m in t.getmembers():
                        if m.isfile() and (m.name.endswith('.fights.json') or m.name.endswith('.done')):
                            yield os.path.basename(m.name), t.extractfile(m).read().decode()
            elif n.endswith('.fights.json') or n.endswith('.done'):
                yield n, open(p).read()


def load(d, tally):
    done, fights = {}, {}
    for name, text in files(d):
        m = re.match(r'(S-\d+-a\d-[a-z0-9]+(?:-[0-9_-]+)?)\.(done|fights\.json)$', name)
        if not m:
            continue
        if m.group(2) == 'done':
            rc = re.search(r'rc=(\d+)', text)
            done[m.group(1)] = int(rc.group(1)) if rc else -1
        else:
            fights[m.group(1)] = json.loads(text)
    out = {}
    for tag, rc in done.items():
        tally[rc] += 1
        if rc == 0 and tag in fights:
            out[tag] = fights[tag]
        elif rc == 0:
            tally['rc0_without_fights'] += 1
    return out


def read_tsv(name):
    rows = []
    with open(os.path.join(HERE, name)) as f:
        for line in f:
            if line.startswith('#'):
                continue
            rows.append(line.rstrip('\n').split('\t'))
    return rows


def boot(rows, fn, level=0.95):
    g = collections.defaultdict(list)
    for r in rows:
        g[r['seed']].append(fn(r))
    groups = list(g.values())
    if len(groups) < 5:
        return None
    rng = random.Random(SEED)
    ms = []
    for _ in range(REPS):
        s = [v for _ in groups for v in rng.choice(groups)]
        ms.append(sum(s) / len(s))
    ms.sort()
    tail = (1 - level) / 2
    return [round(ms[int(tail * REPS)], 3), round(ms[int((1 - tail) * REPS) - 1], 3)]


def sig(c):
    return tuple(json.dumps(c.get(k), sort_keys=True) for k in COPY_KEYS)


def mark_not_paired(x):
    """Below the reproduction gate every verdict becomes NOT_PAIRED; the descriptive one is kept."""
    if isinstance(x, dict):
        if 'verdict' in x:
            x['descriptive_verdict'], x['verdict'] = x['verdict'], 'NOT_PAIRED'
        for v in x.values():
            mark_not_paired(v)
    elif isinstance(x, list):
        for v in x:
            mark_not_paired(v)


def main():
    stage, scout_dir, units_dir = sys.argv[1:4]
    out_p = sys.argv[4] if len(sys.argv) > 4 else None
    arms_rows = read_tsv('arms.tsv')
    header = arms_rows[0]
    factors = header[1:-1]
    arm_level = {r[0]: dict(zip(factors, map(int, r[1:-1]))) for r in arms_rows[1:]}
    token_arm = {r[-1]: r[0] for r in arms_rows[1:]}
    pkg = {int(s): p for s, p, _ in read_tsv('packages.tsv')[1:]}
    design = sorted(a for a in arm_level if a.startswith('d'))
    if stage == 'screen':
        need = {'screen_design': design + ['ctl', 'gnr'], 'screen': ['ctl', 'gnr']}
    else:
        want = [l.strip() for l in open(os.path.join(HERE, f'sets_{stage}.arms')) if l.strip() and l[0] != '#']
        need = {stage: want}
    info = {'stage': stage}
    tally_s, tally_u = collections.Counter(), collections.Counter()
    scout = {int(re.match(r'S-(\d+)', t).group(1)): x for t, x in load(scout_dir, tally_s).items()}
    units = load(units_dir, tally_u)
    info['scout_units'] = dict(tally_s)
    info['units'] = {str(k): v for k, v in tally_u.items()}
    copies = collections.defaultdict(dict)   # (seed, floor) -> arm -> r -> copy
    entry = {}
    conflicts = collections.Counter()
    repro = collections.Counter()
    for tag, x in units.items():
        m = re.match(r'S-(\d+)-a(\d)-', tag)
        seed, act = int(m.group(1)), int(m.group(2))
        sc = scout.get(seed)
        mine = [(f['floor'], f['encounter']) for f in x['fights'] if f['act'] <= act]
        theirs = [(f['floor'], f['encounter']) for f in (sc['fights'] if sc else []) if f['act'] <= act]
        repro['units_same_fights' if mine == theirs else 'units_other_fights'] += 1
        sf = {f['floor']: f for f in (sc['fights'] if sc else [])}
        for f in x['fights']:
            key = (seed, f['floor'])
            c0 = next((r for r in f['replicates'] if r['r'] == 0), None)
            s0 = next((r for r in sf[f['floor']]['replicates'] if r['r'] == 0), None) if f['floor'] in sf else None
            if c0 is not None and s0 is not None:
                repro['copy0_same' if sig(c0) == sig(s0) else 'copy0_differ'] += 1
            elif c0 is not None:
                repro['copy0_no_scout'] += 1
            if 'arms' not in f:
                continue
            entry.setdefault(key, f)
            for token, reps in f['arms'].items():
                arm = token_arm.get(token)
                if arm is None:
                    conflicts['unknown_arm'] += 1
                    continue
                for r in reps:
                    old = copies[key].get(arm, {}).get(r['r'])
                    if old is not None and sig(old) != sig(r):
                        conflicts['copy'] += 1
                    copies[key].setdefault(arm, {})[r['r']] = r
    # Production on the arm copy seeds: the scout's `prod` arm (a reference, not part of any package's arms).
    for seed, x in scout.items():
        for f in x['fights']:
            for r in f.get('arms', {}).get('prod', []):
                copies[(seed, f['floor'])].setdefault('prod', {})[r['r']] = r
            if 'arms' in f:
                entry.setdefault((seed, f['floor']), f)
    info['conflicts'] = dict(conflicts)
    info['reproduction'] = dict(repro)
    n_copy0 = repro['copy0_same'] + repro['copy0_differ'] + repro['copy0_no_scout']
    n_units = repro['units_same_fights'] + repro['units_other_fights']
    rate_copy0 = repro['copy0_same'] / n_copy0 if n_copy0 else None
    rate_units = repro['units_same_fights'] / n_units if n_units else None
    paired = rate_copy0 is not None and rate_units is not None and rate_copy0 >= GATE and rate_units >= GATE
    info['reproduction_gate'] = dict(copy0_rate=None if rate_copy0 is None else round(rate_copy0, 4),
                                     units_rate=None if rate_units is None else round(rate_units, 4),
                                     threshold=GATE, paired=paired, verdict='PAIRED' if paired else 'NOT_PAIRED')
    rows, dropped = [], collections.Counter()
    for seed in sorted(scout):
        p = pkg.get(seed)
        if p not in need:
            continue
        for f in scout[seed]['fights']:
            if f['room'] not in ('E', 'B') or f['act'] > 3:
                continue
            key = (seed, f['floor'])
            got = copies.get(key, {})
            if any(sorted(got.get(a, {})) != list(range(K)) for a in need[p]):
                dropped['missing_arm'] += 1
                continue
            if not all(got[a][r]['valid'] for a in need[p] for r in range(K)):
                dropped['invalid_copy'] += 1
                continue
            final = f['act'] == 3 and f['floor'] == 51
            hp = entry[key]['hp']
            loss = lambda c: hp - ((before_act4_heal(c['exitHp'], c['exitMaxHp']) if final else c['exitHp'])
                                   if c['won'] else 0)
            row = dict(seed=seed, package=p, act=f['act'], room=f['room'], enc=f['encounter'], floor=f['floor'])
            have_prod = sorted(got.get('prod', {})) == list(range(K)) and all(c['valid'] for c in got['prod'].values())
            for a in need[p] + (['prod'] if have_prod else []):
                v = [got[a][r] for r in range(K)]
                row[a] = st.mean(loss(c) for c in v)
                row[a + '_death'] = st.mean(not c['won'] for c in v)
                row[a + '_cpu'] = st.mean(c['cpu'] for c in v)
            rows.append(row)
    info['dropped'] = dict(dropped)
    info['fights'] = dict(collections.Counter(r['package'] for r in rows))
    res = {}
    if stage == 'screen':
        D = [r for r in rows if r['package'] == 'screen_design']
        letters = factors

        def effect(cols):
            hi = [a for a in design if all_level(a, cols) > 0]
            lo = [a for a in design if all_level(a, cols) < 0]
            return lambda r: st.mean(r[a] for a in hi) - st.mean(r[a] for a in lo)

        def all_level(a, cols):
            x = 1
            for c in cols:
                x *= arm_level[a][c]
            return x

        mains = {}
        for c in letters:
            fn = effect((c,))
            ci = boot(D, fn)
            m = round(st.mean(fn(r) for r in D), 3) if D else None
            verdict = 'INACTIVE' if ci is None or ci[0] <= 0 <= ci[1] else ('HIGH_BETTER' if ci[1] < 0 else 'LOW_BETTER')
            mains[c] = dict(high_minus_low=m, ci95=ci, verdict=verdict)
        res['main_effects'] = mains
        groups = collections.defaultdict(list)
        for a, b in itertools.combinations(letters, 2):
            groups[tuple(all_level(x, (a, b)) for x in design)].append(a + b)
        res['interactions'] = []
        for col, pairs in groups.items():
            fn = effect(tuple(pairs[0]))
            res['interactions'].append(dict(alias_group=pairs, estimate=round(st.mean(fn(r) for r in D), 3) if D else None,
                                            ci95=boot(D, fn)))
        curv = lambda r: st.mean(r[a] for a in design) - r['ctl']
        at_end = {c: arm_level['ctl'][c] for c in letters if arm_level['ctl'][c] != 0}
        ends = {c: effect((c,)) for c in at_end}
        curv_adj = lambda r: curv(r) + sum(0.5 * l * ends[c](r) for c, l in at_end.items())
        res['curvature'] = dict(design_mean_minus_ctl=round(st.mean(curv(r) for r in D), 3) if D else None,
                                ci95=boot(D, curv), control_at_end=at_end,
                                adjusted=round(st.mean(curv_adj(r) for r in D), 3) if D else None,
                                adjusted_ci95=boot(D, curv_adj))
        res['design_vs_ctl'] = {a: dict(diff=round(st.mean(r[a] - r['ctl'] for r in D), 3) if D else None,
                                        ci95=boot(D, lambda r, a=a: r[a] - r['ctl'])) for a in design}
        g = lambda r: r['gnr'] - r['ctl']
        ci = boot(rows, g)
        res['gnr_minus_ctl'] = dict(diff=round(st.mean(g(r) for r in rows), 3) if rows else None, ci95=ci,
                                    n=len(rows), verdict='GNR_INCONCLUSIVE' if ci is None or ci[0] <= 0 <= ci[1]
                                    else ('GNR_HELPS' if ci[1] < 0 else 'GNR_HURTS'))
        P = [r for r in rows if 'prod' in r]
        res['ctl_minus_prod'] = dict(diff=round(st.mean(r['ctl'] - r['prod'] for r in P), 3) if P else None,
                                     ci95=boot(P, lambda r: r['ctl'] - r['prod']), n=len(P))
        on = lambda a: D if a.startswith('d') else rows
        res['means'] = {a: round(st.mean(r[a] for r in on(a)), 3) for a in design + ['ctl', 'gnr'] if on(a)}
        res['cpu_per_copy_s'] = {a: round(st.mean(r[a + '_cpu'] for r in on(a)), 1)
                                 for a in design + ['ctl', 'gnr'] if on(a)}
    else:
        level = 0.975 if stage == 'confirm' else 0.95
        arms = need[stage]
        ctl = [a for a in arms if a.startswith('ctl')]
        res['vs_ctl'] = {}
        for a in arms:
            if a in ctl:
                continue
            base = 'ctl64' if a.endswith('64') and 'ctl64' in arms else 'ctl'
            fn = lambda r, a=a, base=base: r[a] - r[base]
            ci = boot(rows, fn, level)
            res['vs_ctl'][a] = dict(control=base, diff=round(st.mean(fn(r) for r in rows), 3) if rows else None,
                                    ci=ci, level=level)
            if stage == 'confirm':
                res['vs_ctl'][a]['verdict'] = ('INCONCLUSIVE' if ci is None else 'TUNED_TEACHER_BETTER' if ci[1] < 0
                                               else 'TUNED_TEACHER_WORSE' if ci[0] > 0
                                               else 'NO_TUNING_GAIN' if ci[0] > NO_GAIN else 'INCONCLUSIVE')
        res['means'] = {a: round(st.mean(r[a] for r in rows), 3) for a in arms} if rows else {}
    if not paired:
        mark_not_paired(res)
    info['result'] = res
    text = json.dumps(info, indent=1)
    if out_p:
        with open(out_p, 'w') as f:
            f.write(text + '\n')
    print(text)


if __name__ == '__main__':
    main()
