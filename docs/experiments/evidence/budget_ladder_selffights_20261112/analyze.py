#!/usr/bin/env python3
"""Learned budget step B (PREREG.md): per-fight budget ladder 1k-16k on our own H4 states (selffights).

usage: python3 -I analyze.py UNITS_DIR CURRENCY_JSON OUT_JSON [CLAIMS_TXT]
       python3 -I analyze.py --selftest

UNITS_DIR holds the unit tars (or their extracted contents): `L-<seed>-a<act>.fights.json` and `.done`. CURRENCY_JSON
is §794's ../learned_budget_offline_20261112/results/currency.json (frozen). Only rc-0 units count; a fight of a
unit's own act needs all 4 copies of all 5 arms (else `missing_side`, dropped and listed).

Per copy: HP lost = entry HP - exit HP (entry HP on a loss; floor-51 exits inverted for the Act-4 heal), death, CPU.
Currency (primary): Heart-pp loss per copy = 100 * V_mean(act, room) on a death, else w * dV/dHP(act, room) * HP lost
(w = 0.25 for Act 1-2 bosses, 1 otherwise; '?' fights use NORMAL), from CURRENCY_JSON's pooled exchange table. Side
value = mean of the 4 copies.

Uniform frontier: the lower convex hull of the 5 uniform arms (mean CPU per fight, mean loss). A policy picks one
arm per fight (cross-fitted, 5 folds by seed, fold seed 20261112): predicted loss per arm + lambda * predicted CPU per
arm, lambda found by bisection so the predicted total CPU equals the target. Policies (pre-registered):
  P1 room  : act x room table (12 cells) of mean loss and mean log-CPU per arm (shrunk to the arm mean, k = 20)
  P2 enc   : encounter table, same shrinkage
  P3 state : ridge per arm on entry features (act, room, floor, HP, max HP, HP share, deck, upgrades, relic and potion
             counts, encounter one-hot); CPU by the same ridge on log CPU
Targets: the CPU of uniform 4k and of uniform 8k. Contrast per fight: policy loss - frontier loss at the policy's
realized total CPU (linear interpolation between the two hull points around it, applied per fight). Run-clustered
bootstrap (10,000, seed 20261112) with 6 contrasts -> 99.17% two-sided CIs (Bonferroni, alpha 0.05).
Per-run effect = per-fight contrast x mean arm fights per run (Acts 1-3).
Decision: GAIN if some contrast has CI upper < 0 and per-run point <= -0.3 pp Heart; else NOT_SHOWN.
HP-currency results, uniform curves by act x room and the split-half reliability are co-reported.
"""
import collections, json, math, os, random, re, sys, tarfile
import numpy as np

ARMS = ['gsh16+flat1000+mb4', 'gsh16+flat2000+mb4', 'gsh16+flat4000+mb4', 'gsh16+flat8000+mb4', 'gsh16+flat16000+mb4']
LAB = ['1k', '2k', '4k', '8k', '16k']
K = 4
LEVEL = 1 - 0.05 / 6
ROOMS = {'M': 'NORMAL', '?': 'NORMAL', 'E': 'ELITE', 'B': 'BOSS'}
SEED0 = 20261112


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


def load_rows(d, info):
    done, fights = {}, {}
    for n, s in files(d):
        if n.endswith('.done'):
            m = re.search(r'tag=(\S+) rc=(\d+)', s)
            if m:
                done[m.group(1)] = int(m.group(2))
        else:
            fights[n[:-len('.fights.json')]] = json.loads(s)
    info['units_rc'] = dict(collections.Counter(str(v) for v in done.values()))
    info['units_without_done'] = sorted(t for t in fights if t not in done)
    rows, dropped = [], []
    for tag, x in sorted(fights.items()):
        if done.get(tag) != 0 or x.get('schema') != 'self-fights-v1':
            continue
        seed, act = re.match(r'L-(\d+)-a(\d)$', tag).groups()
        act = int(act)
        for f in x['fights']:
            if f['act'] != act or 'arms' not in f:
                continue
            arms = f['arms']
            if any(len(arms.get(a, [])) != K or sorted(r['r'] for r in arms[a]) != list(range(K)) for a in ARMS) \
                    or not all(r['valid'] for a in ARMS for r in arms[a]):
                dropped.append([tag, f['floor'], 'missing_side'])
                continue
            final = f['act'] == 3 and f['floor'] == 51

            def loss(r):
                if not r['won']:
                    return f['hp']
                e = before_act4_heal(r['exitHp'], r['exitMaxHp']) if final else r['exitHp']
                return f['hp'] - e
            row = dict(seed=seed, act=f['act'], room=f['room'], enc=f['encounter'], floor=f['floor'], hp=f['hp'],
                       maxHp=f['maxHp'], deck=f['deck'], upgrades=f.get('upgrades', 0),
                       nrelics=len(f.get('relics', [])), npot=len(f.get('potions', [])))
            for a, lab in zip(ARMS, LAB):
                cs = sorted(arms[a], key=lambda r: r['r'])
                row[lab + '_hp'] = [loss(r) for r in cs]
                row[lab + '_death'] = [0 if r['won'] else 1 for r in cs]
                row[lab + '_cpu'] = [r['cpu'] for r in cs]
            rows.append(row)
    info['dropped'] = dropped
    return rows


def heart_loss(row, lab, C):
    x = C[f"A{row['act']} {ROOMS.get(row['room'], 'NORMAL')}"]
    w = 0.25 if (row['room'] == 'B' and row['act'] < 3) else 1.0
    return [100 * x['V_mean'] if d else w * x['dV_per_HP_pp'] * h for h, d in zip(row[lab + '_hp'], row[lab + '_death'])]


def cluster_boot(vals, groups, level, reps=10000, seed=SEED0):
    g = collections.defaultdict(float); c = collections.Counter()
    for v, s in zip(vals, groups):
        g[s] += v; c[s] += 1
    keys = list(g); sums = np.array([g[k] for k in keys]); cnts = np.array([c[k] for k in keys])
    rg = np.random.default_rng(seed)
    ix = rg.integers(0, len(keys), (reps, len(keys)))
    ms = sums[ix].sum(1) / cnts[ix].sum(1)
    t = (1 - level) / 2
    return [round(float(np.quantile(ms, t)), 4), round(float(np.quantile(ms, 1 - t)), 4)]


def hull(points):
    """lower convex hull (cpu increasing, loss decreasing) of [(cpu, loss, index)]"""
    pts = sorted(points)
    h = []
    for p in pts:
        while len(h) >= 2 and (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0]) >= (p[1] - h[-2][1]) * (h[-1][0] - h[-2][0]):
            h.pop()
        if not h or p[1] < h[-1][1]:
            h.append(p)
    return h


def features(rows, encs):
    X = []
    for r in rows:
        X.append([r['act'] == 2, r['act'] == 3, r['room'] == 'E', r['room'] == 'B', r['room'] == '?', r['floor'] / 50,
                  r['hp'] / 100, r['maxHp'] / 100, r['hp'] / max(1, r['maxHp']), r['deck'] / 30, r['upgrades'] / 10,
                  r['nrelics'] / 10, r['npot'] / 3] + [r['enc'] == e for e in encs])
    return np.array(X, float)


def ridge_fit_predict(Xtr, ytr, Xte, alpha=3.0):
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
    A = (Xtr - mu) / sd; B = (Xte - mu) / sd
    A1 = np.c_[np.ones(len(A)), A]; B1 = np.c_[np.ones(len(B)), B]
    I = np.eye(A1.shape[1]); I[0, 0] = 0
    w = np.linalg.solve(A1.T @ A1 + alpha * len(A) / 100 * I, A1.T @ ytr)
    return B1 @ w


def table_predict(keys_tr, y_tr, keys_te, k=20):
    m = y_tr.mean()
    s = collections.defaultdict(float); n = collections.Counter()
    for kk, v in zip(keys_tr, y_tr):
        s[kk] += v; n[kk] += 1
    return np.array([(s[kk] + k * m) / (n[kk] + k) for kk in keys_te])


def analyse(rows, loss_of, info_prefix=''):
    N = len(rows)
    L = np.array([[np.mean(loss_of(r, lab)) for lab in LAB] for r in rows])          # N x 5
    Cc = np.array([[np.mean(r[lab + '_cpu']) for lab in LAB] for r in rows])          # N x 5
    seeds = [r['seed'] for r in rows]
    us = sorted(set(seeds))
    perm = np.random.default_rng(SEED0).permutation(len(us))
    fold_of = {s: int(perm[i]) % 5 for i, s in enumerate(us)}
    fold = np.array([fold_of[s] for s in seeds])
    fights_per_run = N / len(us)
    out = dict(fights=N, runs=len(us), fights_per_run=round(fights_per_run, 2))
    out['uniform'] = {lab: dict(loss=round(float(L[:, j].mean()), 4), cpu=round(float(Cc[:, j].mean()), 3))
                      for j, lab in enumerate(LAB)}
    H = hull([(float(Cc[:, j].mean()), float(L[:, j].mean()), j) for j in range(5)])
    out['hull'] = [LAB[p[2]] for p in H]
    # split-half reliability of the 1k -> 16k gain
    a = np.array([np.mean([loss_of(r, '1k')[c] - loss_of(r, '16k')[c] for c in (0, 1)]) for r in rows])
    b = np.array([np.mean([loss_of(r, '1k')[c] - loss_of(r, '16k')[c] for c in (2, 3)]) for r in rows])
    out['split_half_r_1k_16k'] = round(float(np.corrcoef(a, b)[0, 1]), 3)
    encs = sorted({r['enc'] for r in rows})
    X = features(rows, encs)
    keys = {'room': [(r['act'], r['room']) for r in rows], 'enc': [r['enc'] for r in rows]}
    logC = np.log(np.maximum(1e-4, Cc))
    PL, PC = {}, {}
    for name in ('room', 'enc', 'state'):
        pl = np.zeros_like(L); pc = np.zeros_like(Cc)
        for k in range(5):
            tr, te = fold != k, fold == k
            for j in range(5):
                if name == 'state':
                    pl[te, j] = ridge_fit_predict(X[tr], L[tr, j], X[te])
                    pc[te, j] = np.exp(ridge_fit_predict(X[tr], logC[tr, j], X[te]))
                else:
                    kt = [keys[name][i] for i in np.where(tr)[0]]; ke = [keys[name][i] for i in np.where(te)[0]]
                    pl[te, j] = table_predict(kt, L[tr, j], ke)
                    pc[te, j] = np.exp(table_predict(kt, logC[tr, j], ke))
        PL[name], PC[name] = pl, pc
    res = {}
    for name in ('room', 'enc', 'state'):
        for tlab in ('4k', '8k'):
            target = Cc[:, LAB.index(tlab)].sum()
            lo, hi = 0.0, 1e3
            for _ in range(80):
                lam = math.sqrt(lo * hi) if lo > 0 else hi / 2
                ch = np.argmin(PL[name] + lam * PC[name], 1)
                if PC[name][np.arange(N), ch].sum() > target:
                    lo = lam
                else:
                    hi = lam
                if hi - lo < 1e-9:
                    break
            ch = np.argmin(PL[name] + hi * PC[name], 1)
            lp = L[np.arange(N), ch]; cp = Cc[np.arange(N), ch]
            spent = cp.mean()
            # frontier at the policy's realized CPU: interpolate between hull points (per fight, same weights)
            hc = [p[0] for p in H]; hj = [p[2] for p in H]
            if spent <= hc[0]:
                front = L[:, hj[0]]
            elif spent >= hc[-1]:
                front = L[:, hj[-1]]
            else:
                i = max(t for t in range(len(hc)) if hc[t] <= spent)
                w = (spent - hc[i]) / (hc[i + 1] - hc[i])
                front = (1 - w) * L[:, hj[i]] + w * L[:, hj[i + 1]]
            d = lp - front
            ci = cluster_boot(d, seeds, LEVEL)
            res[f'{name}@{tlab}'] = dict(
                cpu_ratio_vs_uniform=round(float(spent / Cc[:, LAB.index(tlab)].mean()), 3),
                choice_share={LAB[j]: round(float((ch == j).mean()), 3) for j in range(5)},
                policy=round(float(lp.mean()), 4), frontier=round(float(front.mean()), 4),
                diff_per_fight=round(float(d.mean()), 4), ci_per_fight=ci,
                diff_per_run=round(float(d.mean() * fights_per_run), 3),
                ci_per_run=[round(c * fights_per_run, 3) for c in ci])
    out['policies'] = res
    # uniform curves by act x room
    cells = collections.defaultdict(list)
    for i, r in enumerate(rows):
        cells[f"A{r['act']}{r['room']}"].append(i)
    out['by_act_room'] = {c: dict(n=len(ix), loss={lab: round(float(L[ix, j].mean()), 3) for j, lab in enumerate(LAB)},
                                  cpu={lab: round(float(Cc[ix, j].mean()), 2) for j, lab in enumerate(LAB)})
                          for c, ix in sorted(cells.items())}
    return out


def decide(p):
    best = None
    for k, v in p['policies'].items():
        if v['ci_per_fight'][1] < 0 and v['diff_per_run'] <= -0.3:
            if best is None or v['diff_per_run'] < p['policies'][best]['diff_per_run']:
                best = k
    return f'GAIN ({best})' if best else 'NOT_SHOWN'


def main(units, currency, outp, claims=None):
    info = {}
    rows = load_rows(units, info)
    C = json.load(open(currency))['pooled']['exchange']
    heart = analyse(rows, lambda r, lab: heart_loss(r, lab, C))
    hp = analyse(rows, lambda r, lab: r[lab + '_hp'])
    out = dict(info=info, decision=decide(heart), heart_pp=heart, hp=hp)
    s = json.dumps(out, indent=1)
    print(s)
    open(outp, 'w').write(s + '\n')


def selftest():
    """Synthetic fights: loss falls with budget; cost doubles per step; in rooms 'E' the gain is 4x and the cost is
    1/10, so a room/encounter policy must beat the frontier (GAIN); with no heterogeneity it must say NOT_SHOWN."""
    import tempfile
    for hetero, want in ((True, 'GAIN'), (False, 'NOT_SHOWN')):
        rnd = random.Random(1)
        d = tempfile.mkdtemp()
        for s in range(120):
            for act in (1, 2, 3):
                fights = []
                for fl in range(1, 13):
                    room = 'E' if fl % 4 == 0 else 'M'
                    enc = 'Elite' + room if room == 'E' else 'Hall%d' % (fl % 3)
                    g = 4.0 if (hetero and room == 'E') else 1.0
                    cs = 0.1 if (hetero and room == 'E') else 1.0
                    arms = {}
                    for j, a in enumerate(ARMS):
                        base = 20 - g * 3 * math.log2(1 + j)
                        arms[a] = [dict(r=c, valid=True, won=True, exitHp=70 - max(0, min(60, int(base + rnd.gauss(0, 4)))),
                                        exitMaxHp=80, cpu=cs * (2 ** j) * (1 + rnd.random() * 0.1)) for c in range(K)]
                    fights.append(dict(act=act, floor=fl + 17 * (act - 1), room=room, encounter=enc, hp=70, maxHp=80,
                                       deck=15, relics=[], potions=[], arms=arms))
                tag = f'L-{111970000 + s}-a{act}'
                json.dump(dict(schema='self-fights-v1', fights=fights), open(os.path.join(d, tag + '.fights.json'), 'w'))
                open(os.path.join(d, tag + '.done'), 'w').write(f'tag={tag} rc=0\n')
        C = {f'A{a} {r}': dict(V_mean=0.5, dV_per_HP_pp=0.4) for a in (1, 2, 3) for r in ('NORMAL', 'ELITE', 'BOSS')}
        cp = os.path.join(d, 'cur.json'); json.dump(dict(pooled=dict(exchange=C)), open(cp, 'w'))
        info = {}
        rows = load_rows(d, info)
        got = decide(analyse(rows, lambda r, lab: heart_loss(r, lab, C)))
        print('selftest hetero=%s -> %s (want %s), fights %d, dropped %d' % (hetero, got, want, len(rows), len(info['dropped'])))
        assert got.startswith(want), got
    print('SELFTEST OK')


if __name__ == '__main__':
    if sys.argv[1:] == ['--selftest']:
        selftest()
    else:
        main(*sys.argv[1:])
