#!/usr/bin/env python3
"""E1-R of the learned price head: potion prices from reward luck (PREREG.md; written before any E1-R row existed).
usage: analyze.py E1R_UNITS_DIR E1_UNITS_DIR OUT.json
E1R_UNITS_DIR holds this campaign's unit tars (<first seed>.wNN.tar, 16 source seeds each, `lr-*.jsonl.gz`);
E1_UNITS_DIR E1's (read only, for G1). A unit counts when result.txt says rc=0 and its JSONL has all 16 source rows;
per unit id the first tar that counts is used (every attempt replays the same deterministic runs).

Every logged roll r (a won normal, elite or act 1-2 boss fight, or act 4's elite) has a known drop chance p_r, so
u_r = dropped_r - p_r is a luck draw. Given a drop, the type is drawn independently of the drop chance state, so
f_r = dropped_r * (fairy_r - q) (q = Fairy share of all drops) is a second, independent draw; its coefficient is the
value of a Fairy drop minus that of any other drop. Game-level OLS of
heartKill on the per-game sums, HC1 SEs. potionChance resets at every act transition, so a drop at the act 1-2 boss
reward or at act 4's elite reward changes no later drop chance; a mid-act drop lowers the next chances (-10 instead
of +10, decaying by 0.8 per roll) and its coefficient is attenuated (descriptive only)."""
import collections, gzip, io, json, math, os, re, sys, tarfile
import numpy as np

FIRST, LAST = 111780000, 111788191
G1_FIELDS = ('valid', 'won', 'heartKill', 'floor', 'fightEnds', 'eligible', 'ineligible', 'ppo')
MIN_TYPE_DROPS = 500
BETA_HP_E1 = 0.155          # E1's pooled luck HP price (pp per HP, §764), for HP units (descriptive)


def load_units(units_dir, prefix, n_source=16):
    units, bad = {}, {}
    for name in sorted(os.listdir(units_dir)):
        m = re.fullmatch(r'(\d+)\.w\d+\.tar', name)
        if not m or not FIRST <= int(m.group(1)) <= LAST or m.group(1) in units:
            continue
        uid = m.group(1)
        with tarfile.open(os.path.join(units_dir, name)) as t:
            files = {x.name: x for x in t.getmembers() if x.isfile()}
            res = [n for n in files if n.endswith(f'/{uid}/result.txt')]
            jl = [n for n in files if n.endswith('.jsonl.gz') and f'/{uid}/' in n
                  and os.path.basename(n).startswith(prefix)]
            if len(res) != 1 or len(jl) != 1:
                bad[uid] = 'missing result or jsonl'
                continue
            rc = re.search(r'rc=(\d+)', t.extractfile(files[res[0]]).read().decode())
            if not rc or rc.group(1) != '0':
                bad[uid] = 'rc ' + (rc.group(1) if rc else '?')
                continue
            rows = [json.loads(l) for l in gzip.open(io.BytesIO(t.extractfile(files[jl[0]]).read()), 'rt')]
        src = [r for r in rows if r['kind'] == 'source']
        if len(src) != n_source:
            bad[uid] = 'source rows'
            continue
        units[uid] = src
        bad.pop(uid, None)
    return units, bad


def src_key(r):
    return {**{k: r.get(k) for k in G1_FIELDS}, 'silverSimulations': r['cost']['silverSimulations']}


def ols(X, y):
    XtXi = np.linalg.pinv(X.T @ X)
    b = XtXi @ X.T @ y
    e = y - X @ b
    n, p = X.shape
    V = XtXi @ ((X * (e ** 2)[:, None]).T @ X) @ XtXi * n / (n - p)
    return b, V


def roll_class(x):
    if x['room'] == 'BOSS':
        return 'boss'
    if x['act'] == 4:
        return 'ss'
    return f"mid_a{x['act']}"


def analyse(games, e1_src=None):
    """games: {seed: source row with 'rewards'}; e1_src: {seed: E1 source row} or None. Returns the result dict."""
    out = {'games': len(games)}
    if e1_src is not None:
        both = sorted(set(games) & set(e1_src))
        out['G1_seeds'] = len(both)
        out['G1_mismatch'] = [s for s in both if src_key(games[s]) != src_key(e1_src[s])]
    rolls = [(s, x) for s, g in games.items() for x in g['rewards']['rolls']]
    out['rolls'] = len(rolls)
    out['G2_inconsistent'] = sum(g['rewards']['inconsistent'] for g in games.values())
    drops = [x for _, x in rolls if x['dropped']]
    out['drops'] = len(drops)
    types = collections.Counter(x['potion'] for x in drops)
    q = {t: c / len(drops) for t, c in types.items()}
    qF = q.get('FAIRY_POTION', 0.0)
    out['fairy_share'] = qF
    big = sorted(t for t, c in types.items() if c >= MIN_TYPE_DROPS)
    # remaining rolls in the same act after each roll (descriptive blizzard check)
    later = {}
    by_game_act = collections.defaultdict(list)
    for s, x in rolls:
        by_game_act[(s, x['act'])].append(x['fightIndex'])
    for (s, act), idx in by_game_act.items():
        idx = sorted(idx)
        for k, fi in enumerate(idx):
            later[(s, fi)] = len(idx) - 1 - k

    def bucket(k):
        return '0' if k == 0 else '1-2' if k <= 2 else '3-5' if k <= 5 else '6+'

    G = collections.defaultdict(lambda: collections.defaultdict(float))
    for s, x in rolls:
        p = x['chance'] / 100.0
        d = 1.0 if x['dropped'] else 0.0
        u = d - p
        c = roll_class(x)
        G[s][f'u_{c}'] += u
        fairy = 1.0 if x.get('potion') == 'FAIRY_POTION' else 0.0
        G[s]['f_fairy'] += d * (fairy - qF)
        for t in big:
            G[s][f't_{t}'] += d * ((1.0 if x.get('potion') == t else 0.0) - q[t])
        full = x['potionCount'] >= x['potionCapacity']
        G[s][f'u_{c}_{"full" if full else "free"}'] += u
        if c.startswith('mid'):
            G[s][f'u_mid_k{bucket(later[(s, x["fightIndex"])])}'] += u
    seeds = sorted(games)
    y = np.array([float(games[s]['heartKill']) for s in seeds])
    out['heart_rate'] = float(y.mean())

    def fit(cols):
        X = np.column_stack([np.ones(len(seeds))] + [np.array([G[s].get(c, 0.0) for s in seeds]) for c in cols])
        b, V = ols(X, y)
        return {c: (100 * float(b[i + 1]), 100 * math.sqrt(max(V[i + 1, i + 1], 0.0))) for i, c in enumerate(cols)}

    level = ['u_boss', 'u_ss', 'u_mid_a1', 'u_mid_a2', 'u_mid_a3']
    prim = fit(level + ['f_fairy'])
    out['primary'] = {'boss_pp': prim['u_boss'], 'fairy_minus_other_pp': prim['f_fairy']}
    lo = lambda v: (v[0] - 1.96 * v[1], v[0] + 1.96 * v[1])
    out['primary']['boss_ci95'] = lo(prim['u_boss'])
    out['primary']['fairy_ci95'] = lo(prim['f_fairy'])
    ok_b = out['primary']['boss_ci95'][0] > 0 or out['primary']['boss_ci95'][1] < 0
    ok_f = out['primary']['fairy_ci95'][0] > 0 or out['primary']['fairy_ci95'][1] < 0
    out['decision'] = 'USABLE' if ok_b and ok_f else ('PARTIAL' if ok_b or ok_f else 'UNRESOLVED')
    if out['G2_inconsistent'] > 0.001 * max(out['rolls'], 1):
        out['decision'] = 'VOID (rolls disagree with the engine)'
    out['levels'] = {k: prim[k] for k in level}
    out['boss_hp_units'] = prim['u_boss'][0] / BETA_HP_E1
    for s, x in rolls:
        if x['room'] == 'BOSS':
            G[s][f'u_boss_a{x["act"]}'] += x['dropped'] - x['chance'] / 100.0
    out['boss_by_act'] = fit(['u_boss_a1', 'u_boss_a2', 'u_ss', 'u_mid_a1', 'u_mid_a2', 'u_mid_a3', 'f_fairy'])
    out['mid_by_later_rolls'] = fit(['u_boss', 'u_ss'] + [f'u_mid_k{b}' for b in ('0', '1-2', '3-5', '6+')] + ['f_fairy'])
    out['slots'] = fit(['u_boss_free', 'u_boss_full', 'u_ss_free', 'u_ss_full', 'u_mid_a1', 'u_mid_a2', 'u_mid_a3',
                        'f_fairy'])
    # per type (own fit each): value of a drop of type t minus a drop of any other type
    out['types'] = {t: {'drops': types[t], 'share': q[t], 'minus_rest_pp': fit(level + [f't_{t}'])[f't_{t}']}
                    for t in big}
    out['type_counts'] = dict(types.most_common())
    out['rolls_by_class'] = dict(collections.Counter(roll_class(x) for _, x in rolls))
    return out


def main(e1r_dir, e1_dir, out_path):
    units, bad = load_units(e1r_dir, 'lr-')
    games = {r['seed']: r for rows in units.values() for r in rows}
    for g in games.values():
        assert 'rewards' in g, 'source row without rewards log'
    e1_units, _ = load_units(e1_dir, 'le-')
    e1_src = {r['seed']: r for rows in e1_units.values() for r in rows}
    out = analyse(games, e1_src)
    out['units'] = len(units)
    out['bad_units'] = bad
    json.dump(out, open(out_path, 'w'), indent=1)
    print(json.dumps({k: out[k] for k in ('decision', 'games', 'units', 'rolls', 'drops', 'G1_seeds', 'primary')},
                     indent=1))
    print('G1 mismatches:', len(out['G1_mismatch']), 'G2 inconsistent:', out['G2_inconsistent'])


if __name__ == '__main__':
    main(*sys.argv[1:4])
