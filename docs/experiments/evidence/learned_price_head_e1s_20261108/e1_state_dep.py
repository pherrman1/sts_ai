#!/usr/bin/env python3
"""E1-S (PLAN.md on the share, sha256 8956c001...): does E1's luck HP price depend on the fight-start state?
usage: e1_state_dep.py ANALYZE_PY E1_UNITS_DIR OUT.json
Reuses analyze.py (E1, f29d1695) for loading, the luck components and the column layout."""
import collections, importlib.util, json, math, sys
import numpy as np

spec = importlib.util.spec_from_file_location('e1analyze', sys.argv[1])
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)
E1_DIR, OUT = sys.argv[2], sys.argv[3]
ATT, ROOMS = A.ATT, A.ROOMS
FEATS = ('hpfrac', 'floor', 'potions', 'maxhp')


def ols_cov(X, y):
    XtXi = np.linalg.pinv(X.T @ X)
    b = XtXi @ X.T @ y
    e = y - X @ b
    n, p = X.shape
    V = XtXi @ ((X * (e ** 2)[:, None]).T @ X) @ XtXi * n / (n - p)
    return b, V, e


def chi2_sf_4(x):            # survival function of chi-square with 4 df
    return math.exp(-x / 2) * (1 + x / 2)


units, bad = A.load_units(E1_DIR, 'le-', 16, lambda u: A.E1_FIRST <= u <= A.E1_LAST, first_ok=True)
src, luck = {}, {}
for rows in units.values():
    for r in rows:
        if r['kind'] == 'source':
            src[r['seed']] = r
        elif r['kind'] == 'luck':
            luck[(r['seed'], r['fightIndex'])] = r
seeds = sorted(src)


def replay_ok(r):
    x = r['replays'][0]
    return 'error' not in x and x['healthFailures'] == 0


vary = collections.Counter()
for r in luck.values():
    if replay_ok(r):
        for name, x, z in zip(r['relics'], r['real']['fields']['relicData'], r['replays'][0]['fields']['relicData']):
            vary[name] += x != z
counters = sorted(n for n, c in vary.items() if c >= 50)
comps = ['s', 'h', 'k', 'mhp', 'gold', 'upg', 'misc'] + [f'r:{c}' for c in counters]


def yvec(end, names):
    s = 1.0 if end['won'] else 0.0
    f = end['fields']
    rel = dict(zip(names, f['relicData']))
    return np.array([s, s * f['hp'], s * f['potionCount'], s * f['maxHp'], s * f['gold'], s * f['upgrades'],
                     s * f['misc']] + [s * rel.get(c, 0) for c in counters], float)


# ---- fights of acts 1-3 N/E/B with raw start features
fights = []      # (seed, fi, act, room, u, raw features)
for (seed, fi) in sorted(luck):
    r = luck[(seed, fi)]
    if not replay_ok(r) or r['act'] > 3 or r['room'] not in ROOMS:
        continue
    st = r['start']
    raw = [st['hp'] / st['maxHp'], float(r['floor']), float(st['potionCount']), float(st['maxHp'])]
    fights.append((seed, fi, r['act'], r['room'], yvec(r['real'], r['relics']) - yvec(r['replays'][0], r['relics']),
                   raw))
# standardise within act
Z = {}
for act in (1, 2, 3):
    idx = [i for i, f in enumerate(fights) if f[2] == act]
    M = np.array([fights[i][5] for i in idx])
    mu, sd = M.mean(0), M.std(0)
    for j, i in enumerate(idx):
        Z[i] = (M[j] - mu) / np.where(sd > 0, sd, 1)
rng = np.random.default_rng(20261108)
P = {i: rng.standard_normal(4) for i in range(len(fights))}          # placebo features, fixed fight order
# HP-fraction terciles within act (descriptive)
TER = {}
for act in (1, 2, 3):
    idx = [i for i, f in enumerate(fights) if f[2] == act]
    v = np.array([fights[i][5][0] for i in idx])
    # deviation from PLAN: equal-size groups by rank (ties by fight order); a value split leaves the top act-3
    # tercile empty because more than a third of act-3 fights start at full HP
    order = np.argsort(v, kind='stable')
    for rank, j in enumerate(order):
        TER[idx[j]] = min(2, 3 * rank // len(idx))

# ---- per-seed luck sums, as analyze.py, plus the interaction columns
G = collections.defaultdict(lambda: collections.defaultdict(float))
for (seed, fi), r in luck.items():
    if not replay_ok(r):
        continue
    u = yvec(r['real'], r['relics']) - yvec(r['replays'][0], r['relics'])
    act, room = r['act'], r['room']
    if act <= 3:
        for c, x in zip(comps, u):
            G[seed][f'{c}_c'] += x
        if room in ROOMS:
            for c, x in zip(comps, u):
                G[seed][f'{c}_a{act}'] += x
                G[seed][f'{c}_a123'] += x
                G[seed][f'{c}_a{act}_{room}'] += x
        else:
            for c, x in zip(comps, u):
                G[seed][f'{c}_ev'] += x
    else:
        grp = 'heart' if r['encounter'] == 'THE_HEART' else 'ss'
        for c, x in zip(comps, u):
            G[seed][f'{c}_{grp}'] += x
for i, (seed, fi, act, room, u, raw) in enumerate(fights):
    for k in range(4):
        G[seed][f'hz{k}'] += u[1] * Z[i][k]
        G[seed][f'sz{k}'] += u[0] * Z[i][k]
        G[seed][f'hz{k}_a{act}'] += u[1] * Z[i][k]
        G[seed][f'sz{k}_a{act}'] += u[0] * Z[i][k]
        G[seed][f'hp{k}'] += u[1] * P[i][k]
        G[seed][f'sp{k}'] += u[0] * P[i][k]
    G[seed][f'h_a{act}_t{TER[i]}'] += u[1]

controls = [f'{c}_c' for c in comps if c not in ('s', 'h', 'k')]
ev = ['s_ev', 'h_ev', 'k_ev']
act4 = ['s_ss', 'h_ss', 'k_ss', 's_heart']
base = ['s_a1', 's_a2', 's_a3', 'k_a1', 'k_a2', 'k_a3']
par = [f'h_a{a}_{r}' for a in (1, 2, 3) for r in ROOMS]
y = np.array([float(src[s]['heartKill']) for s in seeds])


def fit(cols):
    X = np.column_stack([np.ones(len(seeds))] + [np.array([G[s].get(c, 0.0) for s in seeds]) for c in cols])
    b, V, e = ols_cov(X, y)
    return {c: i + 1 for i, c in enumerate(cols)}, b, V


def coef(cols, names):
    pos, b, V = fit(cols)
    ix = [pos[n] for n in names]
    return np.array([ATT * b[i] for i in ix]), ATT ** 2 * V[np.ix_(ix, ix)]


def wald(g, V):
    W = float(g @ np.linalg.pinv(V) @ g)
    return W, chi2_sf_4(W)


out = {'plan_sha256': '8956c0017f662462e3d08b4a8130b4ebc7ea138e1b01822c2ea820c95bd248d8', 'seeds': len(seeds),
       'units': len(units), 'bad_units': bad, 'fights_a123_NEB': len(fights), 'features': FEATS}
bb, Vb = coef(base + ['h_a123'] + controls + ev + act4, ['h_a123'])
beta_bar = float(bb[0])
out['beta_bar_pp'] = 100 * beta_bar
out['beta_bar_se_pp'] = 100 * math.sqrt(Vb[0, 0])

hz, sz = [f'hz{k}' for k in range(4)], [f'sz{k}' for k in range(4)]
g, Vg = coef(base + par + hz + sz + controls + ev + act4, hz)
W, p = wald(g, Vg)
se = np.sqrt(np.diag(Vg))
out['primary'] = {'gamma_pp': dict(zip(FEATS, (100 * g).tolist())), 'gamma_se_pp': dict(zip(FEATS, (100 * se).tolist())),
                  'gamma_rel': dict(zip(FEATS, (g / beta_bar).tolist())), 'wald': W, 'p': p}
C = np.corrcoef(np.array([Z[i] for i in range(len(fights))]).T)
out['full_hp_share_by_act'] = {a: float(np.mean([fights[i][5][0] >= 1.0 for i in range(len(fights)) if fights[i][2] == a])) for a in (1, 2, 3)}
out['primary']['implied_sd_rel'] = float(math.sqrt(max(g @ C @ g, 0)) / beta_bar)
big = bool(np.max(np.abs(g)) >= 0.2 * beta_bar)
out['decision'] = 'STATE_DEPENDENT' if (p < 0.01 and big) else 'NOT_SHOWN'

hp_, sp_ = [f'hp{k}' for k in range(4)], [f'sp{k}' for k in range(4)]
gp, Vp = coef(base + par + hp_ + sp_ + controls + ev + act4, hp_)
Wp, pp = wald(gp, Vp)
out['placebo'] = {'gamma_pp': (100 * gp).tolist(), 'gamma_se_pp': (100 * np.sqrt(np.diag(Vp))).tolist(), 'wald': Wp, 'p': pp}
if pp < 0.01:
    out['decision'] = 'VOID (placebo p < 0.01)'

out['per_act'] = {}
for a in (1, 2, 3):
    hza, sza = [f'hz{k}_a{a}' for k in range(4)], [f'sz{k}_a{a}' for k in range(4)]
    ga, Va = coef(base + par + hza + sza + controls + ev + act4, hza)
    Wa, pa = wald(ga, Va)
    out['per_act'][a] = {'gamma_pp': dict(zip(FEATS, (100 * ga).tolist())),
                         'gamma_se_pp': dict(zip(FEATS, (100 * np.sqrt(np.diag(Va))).tolist())), 'wald': Wa, 'p': pa}

ter = [f'h_a{a}_t{t}' for a in (1, 2, 3) for t in (0, 1, 2)]
gt, Vt = coef(base + ter + controls + ev + act4, ter)
out['hpfrac_terciles'] = {c: [100 * float(x), 100 * math.sqrt(max(Vt[i, i], 0))] for i, (c, x) in enumerate(zip(ter, gt))}

gr, Vr = coef(base + par + controls + ev + act4, par)
out['per_act_room'] = {c: [100 * float(x), 100 * math.sqrt(max(Vr[i, i], 0))] for i, (c, x) in enumerate(zip(par, gr))}
boss = {}
for a in (1, 2, 3):
    iN, iB = par.index(f'h_a{a}_NORMAL'), par.index(f'h_a{a}_BOSS')
    d = gr[iB] - 0.25 * gr[iN]
    vd = Vr[iB, iB] + 0.0625 * Vr[iN, iN] - 0.5 * Vr[iB, iN]
    boss[a] = {'boss_pp': 100 * float(gr[iB]), 'quarter_normal_pp': 25 * float(gr[iN]),
               'diff_pp': 100 * float(d), 'diff_se_pp': 100 * math.sqrt(max(vd, 0))}
out['boss_vs_quarter_normal'] = boss
json.dump(out, open(OUT, 'w'), indent=1)
print(json.dumps({k: out[k] for k in ('decision', 'seeds', 'fights_a123_NEB', 'beta_bar_pp', 'primary', 'placebo')},
                 indent=1))
