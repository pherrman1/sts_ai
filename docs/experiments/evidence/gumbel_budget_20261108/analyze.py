#!/usr/bin/env python3
"""Gumbel budget check (PREREG.md): gsh16 at 32,000 and 64,000 simulations and flat 16,000 against stage 1's
gsh16+flat16000 (§770) on the same Baalorlord elite and boss states and copy seeds.

usage: python3 -I analyze.py <units_dir> <stage1_units_dir> [out.json]

units_dir holds this campaign's unit tars or their extracted contents (one `F-<run>-a<act>-<set>.fights.json` per
unit, SET g64 = gsh16+flat64000, SET g32f16 = flat16000 and gsh16+flat32000, SET g16mb = gsh16+flat16000+mb4);
stage1_units_dir holds the teacher check's (../teacher_check_20261108, `F-<run>.fights.json`). Tars are read in place. Adapted from
../teacher_check_20261108/analyze.py: same fight selection, drops, HP-lost definition (entry HP - exit HP, 0 on a loss,
floor-51 exits inverted for the Act-4 heal), side value = mean over the 4 copies, run-clustered bootstrap with 10,000
resamples and seed 20261108.

Per act-1-3 elite or boss fight (run, floor): production and the new arms come from this campaign (production is
played in full in both arm-set units; the two must agree), gsh16+flat16000 (`g16`) and production (`prod1`) from stage 1.
Reproduction: a fight reproduces if each of production's 4 copies here equals stage 1's in won, exitHp, exitMaxHp,
turns, decisions, simulations and potionsUsed. Units whose .done line has rc != 0 are excluded; a fight missing any
side is dropped (`missing_side`).
"""
import collections, io, json, os, random, re, statistics as st, sys, tarfile

MB = 'gsh16+flat16000+mb4'
NEW = ('flat16000', 'gsh16+flat32000', 'gsh16+flat64000', MB)
OLD = ('gsh16+flat16000', 'gsh16+flat4000', 'flat4000', 'rpl4')
G16 = 'gsh16+flat16000'
PRIMARY = ('gsh16+flat32000', 'gsh16+flat64000')   # each minus G16, 97.5% CI (two arms, Bonferroni)
LEVEL = 0.975
SECONDARY = (('flat16000', G16), ('gsh16+flat64000', 'gsh16+flat32000'), ('flat16000', 'prod'))
THRESH = -0.3
K = 4
FRUIT = {'Strawberry': 7, 'Pear': 10, 'Mango': 14}
COPY_KEYS = ('won', 'exitHp', 'exitMaxHp', 'turns', 'decisions', 'simulations', 'potionsUsed')


def before_act4_heal(exit_hp, max_hp):
    for h in range(exit_hp, -1, -1):
        if h + int((max_hp - h) * 0.75 + 0.5) == exit_hp:
            return h
    return exit_hp


def files(d):
    """(name, text) of every .fights.json and .done under d, inside tars too."""
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
    """{unit tag: fights json} for rc-0 units; tally[rc] counts .done lines."""
    done, fights = {}, {}
    for n, s in files(d):
        if n.endswith('.done'):
            m = re.search(r'tag=(\S+) rc=(\d+)', s)
            if m:
                done[m.group(1)] = int(m.group(2))
        else:
            x = json.loads(s)
            if x.get('schema') == 'expert-fights-v1':
                fights[n[:-len('.fights.json')]] = x
    for tag, rc in done.items():
        tally[rc] += 1
    tally['no_done_line'] += sum(t not in done for t in fights)
    return {t: x for t, x in fights.items() if done.get(t) == 0}


def arm_fights(x):
    for f in x['fights']:
        if f['room'] in ('E', 'B') and 'arms' in f:
            yield f


def copy_sig(r):
    return tuple(json.dumps(r.get(k), sort_keys=True) for k in COPY_KEYS)


def rows(new_dir, old_dir, info):
    tally_new, tally_old = collections.Counter(), collections.Counter()
    new, old = load(new_dir, tally_new), load(old_dir, tally_old)
    info['units_rc'] = {str(k): v for k, v in sorted(tally_new.items(), key=str)}
    info['stage1_units_rc'] = {str(k): v for k, v in sorted(tally_old.items(), key=str)}
    info['units_rc0'] = len(new)
    S = collections.defaultdict(dict)   # (run, floor) -> side -> (copies, fight record)
    prod_conflict = 0
    for tag, x in new.items():
        run = x['runFile'][:-5]
        for f in arm_fights(x):
            key = (run, f['floor'])
            S[key].setdefault('_f', f)
            prod = f['replicates'][:K]
            if 'prod' in S[key] and [copy_sig(r) for r in S[key]['prod']] != [copy_sig(r) for r in prod]:
                prod_conflict += 1
            S[key].setdefault('prod', prod)
            for a in NEW:
                if a in f['arms']:
                    S[key][a] = f['arms'][a]
    old_keys = set()
    for tag, x in old.items():
        run = x['runFile'][:-5]
        for f in arm_fights(x):
            key = (run, f['floor'])
            old_keys.add(key)
            S[key].setdefault('_f', f)
            S[key]['prod1'] = f['replicates'][:K]
            for a in OLD:
                S[key][a] = f['arms'][a]
    info['prod_conflicts_between_arm_sets'] = prod_conflict
    dropped = collections.Counter()
    repro = collections.Counter()
    R = []
    for key in sorted(S):
        s = S[key]
        f = s['_f']
        if 'prod' in s and 'prod1' in s:
            repro['same' if [copy_sig(r) for r in s['prod']] == [copy_sig(r) for r in s['prod1']] else 'differ'] += 1
        sides = {'prod': s.get('prod'), 'prod1': s.get('prod1'), **{a: s.get(a) for a in NEW + OLD}}
        if any(v is None for v in sides.values()):
            dropped['missing_side'] += 1
            continue
        if any(len(v) != K for v in sides.values()) or not all(r['valid'] for v in sides.values() for r in v):
            dropped['invalid_copy'] += 1
            continue
        e = f['expert']
        if e['exitHp'] is None:
            dropped['no_logged_exit_hp'] += 1
            continue
        if f['loggedFightsOnFloor'] > 1:
            dropped['two_fights_on_floor'] += 1
            continue
        final = f['act'] == 3 and f['floor'] == 51
        loss = lambda r: f['hp'] - ((before_act4_heal(r['exitHp'], r['exitMaxHp']) if final else r['exitHp'])
                                    if r['won'] else 0)
        fruit = sum(FRUIT.get(n, 0) for n in e['relicsObtained'])
        row = dict(run=key[0], act=f['act'], room=f['room'], enc=f['encounter'], floor=f['floor'],
                   expert=f['hp'] - (0 if e['died'] else max(0, e['exitHp'] - fruit)))
        for k, v in sides.items():
            row[k] = st.mean(loss(r) for r in v)
            row[k + '_death'] = st.mean(not r['won'] for r in v)
            row[k + '_potions'] = st.mean(len(r['potionsUsed']) for r in v)
            row[k + '_cpu'] = st.mean(r['cpu'] for r in v)
            row[k + '_sims'] = sum(r['simulations'] for r in v)
            row[k + '_decisions'] = sum(r['decisions'] for r in v)
        R.append(row)
    n = repro['same'] + repro['differ']
    info['reproduction'] = dict(fights_compared=n, identical=repro['same'], differ=repro['differ'],
                                share=round(repro['same'] / n, 4) if n else None,
                                stage1_fights_without_new_prod=sum(1 for k in old_keys if 'prod' not in S[k]))
    info['dropped'] = dict(dropped)
    return R


def boot(R, fn, reps=10000, seed=20261108, level=0.95):
    g = collections.defaultdict(list)
    for r in R:
        g[r['run']].append(fn(r))
    groups = list(g.values())
    if len(groups) < 5:
        return None
    rng = random.Random(seed)
    ms = []
    for _ in range(reps):
        s = [v for _ in groups for v in rng.choice(groups)]
        ms.append(sum(s) / len(s))
    ms.sort()
    tail = (1 - level) / 2
    return [round(ms[int(tail * reps)], 3), round(ms[int((1 - tail) * reps) - 1], 3)]


def summary(R):
    if not R:
        return None
    out = dict(n=len(R), runs=len({r['run'] for r in R}), expert=round(st.mean(r['expert'] for r in R), 2))
    for k in ('prod',) + NEW + (G16,):
        out[k] = {m: round(st.mean(r[k + m] for r in R), 3) for m in ('', '_death', '_potions', '_cpu')}
    for a in PRIMARY:
        out[f'{a}_minus_g16'] = round(st.mean(r[a] - r[G16] for r in R), 2)
        out[f'{a}_minus_g16_ci'] = boot(R, lambda r, a=a: r[a] - r[G16])
        out[f'{a}_minus_g16_ci975'] = boot(R, lambda r, a=a: r[a] - r[G16], level=LEVEL)
        out[f'{a}_minus_g16_death'] = round(st.mean(r[a + '_death'] - r[G16 + '_death'] for r in R), 4)
        out[f'{a}_minus_g16_death_ci'] = boot(R, lambda r, a=a: r[a + '_death'] - r[G16 + '_death'])
    # Separate pre-registered contrast: max backup under the Gumbel root at 16k, paired with mean-backup g16.
    out['mb_minus_g16'] = round(st.mean(r[MB] - r[G16] for r in R), 2)
    out['mb_minus_g16_ci'] = boot(R, lambda r: r[MB] - r[G16])
    out['mb_minus_g16_death'] = round(st.mean(r[MB + '_death'] - r[G16 + '_death'] for r in R), 4)
    out['mb_minus_g16_death_ci'] = boot(R, lambda r: r[MB + '_death'] - r[G16 + '_death'])
    for a, b in SECONDARY:
        out[f'{a}_minus_{b}'] = round(st.mean(r[a] - r[b] for r in R), 2)
        out[f'{a}_minus_{b}_ci'] = boot(R, lambda r, a=a, b=b: r[a] - r[b])
    for a in NEW + (G16,):
        out[f'{a}_minus_prod'] = round(st.mean(r[a] - r['prod'] for r in R), 2)
        out[f'{a}_minus_prod_ci'] = boot(R, lambda r, a=a: r[a] - r['prod'])
    # CPU ratios: new arms against this campaign's production, stage-1 arms against stage 1's production.
    for a in NEW:
        out[a + '_cpu_ratio'] = round(sum(r[a + '_cpu'] for r in R) / max(1e-9, sum(r['prod_cpu'] for r in R)), 2)
    out[G16 + '_cpu_ratio'] = round(sum(r[G16 + '_cpu'] for r in R) / max(1e-9, sum(r['prod1_cpu'] for r in R)), 2)
    for k in ('prod',) + NEW + (G16,):
        out[k + '_sims_per_decision'] = round(sum(r[k + '_sims'] for r in R) / max(1, sum(r[k + '_decisions'] for r in R)))
    out['prod_minus_expert_ci'] = boot(R, lambda r: r['prod'] - r['expert'])
    return out


def decision(p, repro_share):
    if repro_share is None or repro_share < 0.99:
        return 'NOT_PAIRED (production did not reproduce stage 1; see PREREG)'
    ci = {a: p[f'{a}_minus_g16_ci975'] for a in PRIMARY}
    win = [a for a in PRIMARY if ci[a] and ci[a][1] < 0]
    if win:
        return 'MORE_SIMS_HELP (' + min(win, key=lambda a: p[f'{a}_minus_g16']) + ')'
    if all(ci[a] and ci[a][0] > THRESH for a in PRIMARY):
        return 'NO_GAIN_BEYOND_16K'
    return 'INCONCLUSIVE'


def decision_mb(p, repro_share):
    if repro_share is None or repro_share < 0.99:
        return 'NOT_PAIRED'
    ci = p['mb_minus_g16_ci']
    if ci and ci[1] < 0:
        return 'MAX_BACKUP_HELPS'
    if ci and ci[0] > THRESH:
        return 'MAX_BACKUP_NO_GAIN'
    return 'INCONCLUSIVE'


def main():
    info = {}
    R = rows(sys.argv[1], sys.argv[2], info)
    p = summary(R)
    res = dict(**info, fights=len(R), primary=p,
               decision=decision(p, info['reproduction']['share']) if p else None,
               decision_max_backup=decision_mb(p, info['reproduction']['share']) if p else None,
               by_act={a: summary([r for r in R if r['act'] == a]) for a in (1, 2, 3)},
               by_room={m: summary([r for r in R if r['room'] == m]) for m in ('E', 'B')},
               by_act_room={f'{a}{m}': summary([r for r in R if r['act'] == a and r['room'] == m])
                            for a in (1, 2, 3) for m in ('E', 'B')},
               by_encounter={e: summary([r for r in R if r['enc'] == e])
                             for e in sorted({r['enc'] for r in R}) if sum(r['enc'] == e for r in R) >= 20})
    s = json.dumps(res, indent=1)
    print(s)
    if len(sys.argv) > 3:
        open(sys.argv[3], 'w').write(s + '\n')


if __name__ == '__main__':
    main()
