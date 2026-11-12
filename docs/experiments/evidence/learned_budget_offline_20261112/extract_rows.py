#!/usr/bin/env python3
# learned_budget_offline_20261112: per-fight row export. Copy of ../gumbel_mb_budget_20261108/analyze.py whose
# rows() also keeps entry-state features and per-copy losses/CPU; main() writes {info, rows} to argv[4] and stops.
# usage: python3 -I extract_rows.py <gumbel-mb-budget units> <gumbel-budget units> <teacher-check units> rows.json
"""Max backup at 32k/64k under the Gumbel root (PREREG.md): gsh16+flat32000+mb4 and gsh16+flat64000+mb4 against the
Gumbel budget run's arms (§772) and stage 1's gsh16+flat16000 (§770) on the same Baalorlord elite and boss states
and copy seeds.

usage: python3 -I analyze.py <units_dir> <budget_units_dir> <stage1_units_dir> [out.json]

units_dir holds this campaign's unit tars or their extracted contents (`F-<run>-a<act>-<set>[-<sel>].fights.json`,
SET g32mb / g64mb; a unit with a selection plays only some arm fights and copies, STS_EXPERT_FIGHTS_ARM_COPIES);
budget_units_dir the Gumbel budget run's (../gumbel_budget_20261108); stage1_units_dir the teacher check's
(../teacher_check_20261108). Tars are read in place. Adapted from ../gumbel_budget_20261108/analyze.py: same fight
selection, drops, HP-lost definition (entry HP - exit HP, 0 on a loss, floor-51 exits inverted for the Act-4 heal),
side value = mean over the 4 copies, run-clustered bootstrap with 10,000 resamples and seed 20261108.

Copies are merged per (run, floor, copy) across units. Production copies from this campaign (every copy is played in
at least one unit; copy 0 in several, since the main line needs it) must agree wherever a copy appears twice
(`prod_conflicts`). Reproduction: a fight reproduces if every production copy here equals stage 1's copy with the
same index in won, exitHp, exitMaxHp, turns, decisions, simulations and potionsUsed. Units whose .done line has
rc != 0 are excluded; a fight missing any copy of any side is dropped (`missing_side`).
"""
import collections, json, os, random, re, statistics as st, sys, tarfile

G32MB, G64MB = 'gsh16+flat32000+mb4', 'gsh16+flat64000+mb4'
G32, G64, G16MB, G16 = 'gsh16+flat32000', 'gsh16+flat64000', 'gsh16+flat16000+mb4', 'gsh16+flat16000'
NEW = (G32MB, G64MB)
BUDGET = (G32, G64, G16MB)
ARMS = NEW + BUDGET + (G16,)
PRIMARY_A = ((G32MB, G32), (G64MB, G64))      # max backup at 32k and 64k, 97.5% CIs (Bonferroni over two)
PRIMARY_B = ((G32MB, G16MB), (G64MB, G16MB))  # budget on top of max backup, 97.5% CIs (Bonferroni over two)
LEVEL = 0.975
SECONDARY = ((G64MB, G32MB), (G32MB, G16), (G64MB, G16))
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


def rows(new_dir, budget_dir, old_dir, info):
    tallies = {k: collections.Counter() for k in ('new', 'budget', 'stage1')}
    new, budget, old = load(new_dir, tallies['new']), load(budget_dir, tallies['budget']), load(old_dir, tallies['stage1'])
    for k, t in tallies.items():
        info[f'{k}_units_rc'] = {str(a): b for a, b in sorted(t.items(), key=str)}
    info['units_rc0'] = len(new)
    S = collections.defaultdict(lambda: collections.defaultdict(dict))   # (run, floor) -> side -> {copy: record}
    F = {}
    conflicts = collections.Counter()

    def put(key, side, r, conflict_kind):
        have = S[key][side].get(r['r'])
        if have is not None and copy_sig(have) != copy_sig(r):
            conflicts[conflict_kind] += 1
        S[key][side].setdefault(r['r'], r)

    for tag, x in new.items():
        run = x['runFile'][:-5]
        for f in arm_fights(x):
            key = (run, f['floor'])
            F.setdefault(key, f)
            for r in f['replicates']:
                put(key, 'prod', r, 'prod')
            for a in NEW:
                for r in f['arms'].get(a, []):
                    put(key, a, r, 'arm')
    for tag, x in budget.items():
        run = x['runFile'][:-5]
        for f in arm_fights(x):
            key = (run, f['floor'])
            for r in f['replicates'][:K]:
                put(key, 'prodB', r, 'budget_prod')
            for a in BUDGET:
                for r in f['arms'].get(a, []):
                    put(key, a, r, 'budget_arm')
    old_keys = set()
    for tag, x in old.items():
        run = x['runFile'][:-5]
        for f in arm_fights(x):
            key = (run, f['floor'])
            old_keys.add(key)
            F.setdefault(key, f)
            for r in f['replicates'][:K]:
                put(key, 'prod1', r, 'stage1_prod')
            for r in f['arms'][G16]:
                put(key, G16, r, 'stage1_arm')
    info['conflicts'] = {k: conflicts[k] for k in ('prod', 'arm', 'budget_prod', 'budget_arm', 'stage1_prod', 'stage1_arm')}
    dropped = collections.Counter()
    repro = collections.Counter()
    R = []
    for key in sorted(S):
        s = S[key]
        f = F[key]
        if s.get('prod') and s.get('prod1'):
            same = all(r in s['prod1'] and copy_sig(c) == copy_sig(s['prod1'][r]) for r, c in s['prod'].items())
            repro['same' if same else 'differ'] += 1
            repro['copies'] += len(s['prod'])
        sides = {k: s.get(k, {}) for k in ('prod', 'prod1') + ARMS}
        if any(sorted(v) != list(range(K)) for v in sides.values()):
            dropped['missing_side'] += 1
            continue
        sides = {k: [v[r] for r in range(K)] for k, v in sides.items()}
        if not all(r['valid'] for v in sides.values() for r in v):
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
                   hp=f['hp'], maxHp=f['maxHp'], deck=f['deck'], upgrades=f.get('upgrades',0), nrelics=len(f.get('relics',[])),
                   npot=len(f.get('potions',[])), relics=f.get('relics',[]), potions=f.get('potions',[]),
                   expert=f['hp'] - (0 if e['died'] else max(0, e['exitHp'] - fruit)))
        for k, v in sides.items():
            row[k] = st.mean(loss(r) for r in v)
            row[k + '_death'] = st.mean(not r['won'] for r in v)
            row[k + '_potions'] = st.mean(len(r['potionsUsed']) for r in v)
            row[k + '_cpu'] = st.mean(r['cpu'] for r in v)
            row[k + '_copies'] = [loss(r) for r in v]
            row[k + '_cpucopies'] = [r['cpu'] for r in v]
            row[k + '_sims'] = sum(r['simulations'] for r in v)
            row[k + '_decisions'] = sum(r['decisions'] for r in v)
        R.append(row)
    n = repro['same'] + repro['differ']
    info['reproduction'] = dict(fights_compared=n, identical=repro['same'], differ=repro['differ'],
                                copies_compared=repro['copies'], share=round(repro['same'] / n, 4) if n else None,
                                stage1_fights_without_new_prod=sum(1 for k in old_keys if not S[k].get('prod')))
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


def contrast(out, R, a, b, level=None):
    k = f'{a}_minus_{b}'
    out[k] = round(st.mean(r[a] - r[b] for r in R), 2)
    out[k + '_ci'] = boot(R, lambda r: r[a] - r[b])
    if level:
        out[k + '_ci975'] = boot(R, lambda r: r[a] - r[b], level=level)
        out[k + '_death'] = round(st.mean(r[a + '_death'] - r[b + '_death'] for r in R), 4)
        out[k + '_death_ci'] = boot(R, lambda r: r[a + '_death'] - r[b + '_death'])


def summary(R):
    if not R:
        return None
    out = dict(n=len(R), runs=len({r['run'] for r in R}), expert=round(st.mean(r['expert'] for r in R), 2))
    for k in ('prod',) + ARMS:
        out[k] = {m: round(st.mean(r[k + m] for r in R), 3) for m in ('', '_death', '_potions', '_cpu')}
    for a, b in PRIMARY_A + PRIMARY_B:
        contrast(out, R, a, b, LEVEL)
    for a, b in SECONDARY:
        contrast(out, R, a, b)
    for a in ARMS:
        contrast(out, R, a, 'prod')
    # CPU ratios: every arm against this campaign's production copies (g16 against stage 1's production).
    for a in NEW + BUDGET:
        out[a + '_cpu_ratio'] = round(sum(r[a + '_cpu'] for r in R) / max(1e-9, sum(r['prod_cpu'] for r in R)), 2)
    out[G16 + '_cpu_ratio'] = round(sum(r[G16 + '_cpu'] for r in R) / max(1e-9, sum(r['prod1_cpu'] for r in R)), 2)
    for k in ('prod',) + ARMS:
        out[k + '_sims_per_decision'] = round(sum(r[k + '_sims'] for r in R) / max(1, sum(r[k + '_decisions'] for r in R)))
    out['best_arm'] = min(ARMS, key=lambda a: out[a][''])
    out['prod_minus_expert_ci'] = boot(R, lambda r: r['prod'] - r['expert'])
    return out


def decide(p, repro_share, pairs, win_label, null_label):
    if repro_share is None or repro_share < 0.99:
        return 'NOT_PAIRED (production did not reproduce stage 1; see PREREG)'
    ci = {(a, b): p[f'{a}_minus_{b}_ci975'] for a, b in pairs}
    win = [ab for ab in pairs if ci[ab] and ci[ab][1] < 0]
    if win:
        best = min(win, key=lambda ab: p[f'{ab[0]}_minus_{ab[1]}'])
        return f'{win_label} ({best[0]} vs {best[1]})'
    if all(ci[ab] and ci[ab][0] > THRESH for ab in pairs):
        return null_label
    return 'INCONCLUSIVE'


def main():
    info = {}
    R = rows(sys.argv[1], sys.argv[2], sys.argv[3], info)
    json.dump(dict(info=info, rows=R), open(sys.argv[4], 'w'))
    print(info); return
    p = summary(R)
    share = info['reproduction']['share']
    res = dict(**info, fights=len(R), primary=p,
               decision_max_backup=decide(p, share, PRIMARY_A, 'MB_HELPS_AT_HIGH_BUDGET', 'MB_NO_GAIN_AT_HIGH_BUDGET')
               if p else None,
               decision_budget=decide(p, share, PRIMARY_B, 'MORE_SIMS_HELP_WITH_MB', 'NO_GAIN_BEYOND_16K_WITH_MB')
               if p else None,
               by_act={a: summary([r for r in R if r['act'] == a]) for a in (1, 2, 3)},
               by_room={m: summary([r for r in R if r['room'] == m]) for m in ('E', 'B')},
               by_act_room={f'{a}{m}': summary([r for r in R if r['act'] == a and r['room'] == m])
                            for a in (1, 2, 3) for m in ('E', 'B')},
               by_encounter={e: summary([r for r in R if r['enc'] == e])
                             for e in sorted({r['enc'] for r in R}) if sum(r['enc'] == e for r in R) >= 20})
    s = json.dumps(res, indent=1)
    print(s)
    if len(sys.argv) > 4:
        open(sys.argv[4], 'w').write(s + '\n')


if __name__ == '__main__':
    main()
