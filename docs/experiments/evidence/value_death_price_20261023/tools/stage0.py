#!/usr/bin/env python3
"""Stage 0 of the value-head research plan: the death price of the OOC MCTS leaf on today's stack.

usage: stage0.py EXTRACT OUT.json [--boot N] [--jobs N]
  EXTRACT = an extracted common-seed sibling capture (§644, /mnt/project-files/ooc-sibling-crn/units/*.tar):
  out/units/<seed>/S-<seed>.{jsonl.gz,sib.jsonl.gz,done}. No game seeds are used.

A rollout3 leaf returns 0 on a death, 1 on a Heart kill and X2-B otherwise. Between two children with death rates d
and surviving mean L, dQ ~ (1 - d) dL - L dd: the search prices a death at L, the surviving level. If the Heart
probability of a state with X2-B value x is p = sigmoid(a_act + b logit x), then in X2-B units the calibrated price of
a death is p / (dp/dx) = x (1 - x) / (b (1 - p)). Setting the death value inside the search to
c_act(k) = xbar - k xbar (1 - xbar) / (b (1 - pbar)) charges k times the calibrated price and keeps X2-B's scale for
everything else (k = xbar / price gives back today's c = 0).

1. calibration: per searched root, the X2-B of the executed action's capture rows (mean over its chance outcomes),
   labelled with the source run's Heart kill; logistic fit with one intercept per act and a common slope b on
   logit X2-B, roots weighted equally; 95 % intervals from a source bootstrap.
2. level: per act (of the rollout's end floor), the mean X2-B of surviving rollout ends and the death rate.
3. price: per act, xbar, pbar = sigmoid(a_act + b logit xbar), price, over-pricing factor xbar / price, c_act(1),
   c_act(2).
4. death rate: per searched root, the executed action's rollout death share against the real run dying by the
   rollouts' median surviving end floor. A ratio real / rollout above 1 means the rollouts under-predict death, which
   offsets part of the over-pricing (the effective factor is over-pricing / ratio).
5. flips: every root with >= 2 captured actions. Each repeat value of a death (terminal, value 0) at end floor f is
   replaced by c_act(f)(k) (acts 1-3; act 4 keeps 0); an action's value is the mean over its rows and 32 repeats.
   (a) best action by mean value: does it change? (b) PUCT proxy: with Q fixed at those values, the root's priors
   and its completed simulations, the continuous PUCT allocation (water filling,
   Q_a + c P_a sqrt(N - 1) / (1 + n_a) = lambda for every visited action) picks the most-visited action; a flip is a
   change of that pick. The proxy ignores the deeper tree and the noise of the live estimates; its agreement with the
   action the search actually played is reported as a check.
6. relevance: share of searched roots whose prior top is below 0.95 / 0.99, and where the search overrode the prior.
"""
import gzip
import json
import math
import sys
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

import numpy as np

CPUCT = 1.5
R = 32


def act_of_floor(f):
    return 1 if f <= 16 else 2 if f <= 33 else 3 if f <= 50 else 4


ACT_OF_FLOOR = np.array([act_of_floor(f) for f in range(80)], dtype=np.int8)


def logit(x):
    x = min(max(x, 1e-6), 1 - 1e-6)
    return math.log(x / (1 - x))


def sigmoid(z):
    return 1 / (1 + math.exp(-z))


def load_unit(unit):
    """One source, reduced to arrays: per searched root its candidates and, per captured child row, the X2-B and
    the 32 repeat values, terminal flags and end floors."""
    seed = int(unit.name)
    done = (unit / f'S-{seed}.done').read_text()
    last = None
    decisions = {}
    with gzip.open(unit / f'S-{seed}.jsonl.gz', 'rt') as f:
        for line in f:
            d = json.loads(line)
            last = d
            if d.get('type') != 'decision' or not d.get('searched') or not d.get('root'):
                continue
            root = d['root']
            if root.get('aborted') or root.get('singleton'):
                continue
            decisions[d['decisionIndex']] = {
                'act': d['act'], 'floor': d['floor'], 'screen': d['screen'], 'selKey': d['selectedKey'],
                'sims': root['completedSimulations'], 'full': bool(root.get('fullBudget')),
                'cands': {c['key']: (c['prior'], c['q'], c['visits']) for c in root['candidates']}}
    if ' rc=0 ' not in done or not last or last.get('type') != 'outcome' or not last.get('complete') \
            or not last.get('integrityPassed'):
        return None
    rows = defaultdict(lambda: ([], [], [], [], []))
    with gzip.open(unit / f'S-{seed}.sib.jsonl.gz', 'rt') as f:
        for line in f:
            raw = json.loads(line)
            if raw.get('depth') != 1 or raw.get('decision') not in decisions:
                continue
            reps = raw.get('extra', {}).get('repeats', [])
            x2b = raw.get('extra', {}).get('x2b')
            if len(reps) != R or any('value' not in r for r in reps) or not isinstance(x2b, (int, float)):
                continue
            k, x, v, t, e = rows[raw['decision']]
            k.append(raw['actionKey'])
            x.append(float(x2b))
            v.append([r['value'] for r in reps])
            t.append([bool(r.get('terminal')) for r in reps])
            e.append([r['endFloor'] for r in reps])
    for di, (k, x, v, t, e) in rows.items():
        decisions[di]['rows'] = {'keys': k, 'x2b': np.array(x, dtype=np.float64),
                                 'V': np.array(v, dtype=np.float32), 'T': np.array(t, dtype=bool),
                                 'F': np.array(e, dtype=np.int16)}
    return {'seed': seed, 'heart': int(bool(last.get('heartKilled'))), 'finalFloor': last.get('finalFloor'),
            'decisions': {di: d for di, d in decisions.items() if 'rows' in d}, 'searched': len(decisions),
            'allDecisions': decisions}


def load(extract, jobs):
    units = sorted(Path(extract, 'out', 'units').iterdir())
    with Pool(jobs) as pool:
        loaded = pool.map(load_unit, units, chunksize=4)
    return [s for s in loaded if s is not None], len(units)


def fit_calibration(points, acts=(1, 2, 3, 4), iters=50):
    """IRLS for logit p = a_act + b z; points: (act, z, y). Returns {act: a}, b."""
    X = np.array([[1.0 if a == k else 0.0 for k in acts] + [z] for a, z, _ in points])
    y = np.array([y for _, _, y in points], dtype=float)
    w = np.zeros(X.shape[1])
    for _ in range(iters):
        eta = X @ w
        p = 1 / (1 + np.exp(-eta))
        W = p * (1 - p) + 1e-9
        H = X.T @ (X * W[:, None]) + 1e-6 * np.eye(X.shape[1])
        step = np.linalg.solve(H, X.T @ (y - p))
        w += step
        if np.max(np.abs(step)) < 1e-10:
            break
    return {k: float(w[i]) for i, k in enumerate(acts)}, float(w[-1])


def taken_rows(d):
    rows = d['rows']
    return [i for i, k in enumerate(rows['keys']) if k == d['selKey']]


def calibration_points(sources):
    pts = []
    for s in sources:
        for d in s['decisions'].values():
            idx = taken_rows(d)
            if not idx:
                continue
            x = float(d['rows']['x2b'][idx].mean())
            pts.append((d['act'], logit(x), s['heart'], s['seed'], x))
    return pts


def levels(sources):
    surv_sum, surv_n, deaths, total = defaultdict(float), defaultdict(int), defaultdict(int), defaultdict(int)
    for s in sources:
        for d in s['decisions'].values():
            V, T, F = d['rows']['V'], d['rows']['T'], d['rows']['F']
            A = ACT_OF_FLOOR[np.clip(F, 0, 79)]
            dead = T & (V == 0)
            alive = ~T
            for a in (1, 2, 3, 4):
                m = A == a
                total[a] += int(m.sum())
                deaths[a] += int((dead & m).sum())
                surv_n[a] += int((alive & m).sum())
                surv_sum[a] += float(V[alive & m].astype(np.float64).sum())
    return {a: {'xbar': surv_sum[a] / surv_n[a] if surv_n[a] else None, 'survivors': surv_n[a],
                'deathShare': deaths[a] / total[a] if total[a] else None, 'repeats': total[a]}
            for a in sorted(total) if total[a]}


def prices(cal, lev):
    a_act, b = cal
    out = {}
    for act in (1, 2, 3):
        xbar = lev[act]['xbar']
        pbar = sigmoid(a_act[act] + b * logit(xbar))
        price = xbar * (1 - xbar) / (b * (1 - pbar))
        out[act] = {'xbar': xbar, 'pbar': pbar, 'price': price, 'overpricing': xbar / price,
                    'c1': xbar - price, 'c2': xbar - 2 * price}
    return out


def death_rates(sources):
    """Per searched root: the executed action's rollout death share and the real run's death by the rollouts'
    median surviving end floor (max end floor when no repeat survives)."""
    pts = []
    for s in sources:
        died = not s['heart']
        for d in s['decisions'].values():
            idx = taken_rows(d)
            if not idx:
                continue
            V, T, F = d['rows']['V'][idx], d['rows']['T'][idx], d['rows']['F'][idx]
            dead = T & (V == 0)
            horizon = int(np.median(F[~T])) if (~T).any() else int(F.max())
            real = died and s['finalFloor'] is not None and d['floor'] <= s['finalFloor'] <= horizon
            pts.append((d['act'], float(dead.mean()), int(real), s['seed']))
    return pts


def summarize_death_rates(pts):
    out = {}
    for act in (1, 2, 3, 4):
        sub = [p for p in pts if p[0] == act]
        if not sub:
            continue
        pred = float(np.mean([p[1] for p in sub]))
        real = float(np.mean([p[2] for p in sub]))
        out[act] = {'roots': len(sub), 'rolloutDeath': pred, 'realDeath': real,
                    'ratio': real / pred if pred > 0 else None}
    return out


def puct_pick(P, Q, N):
    """Continuous PUCT allocation with fixed Q: n_a = max(0, c P_a s / (lam - Q_a) - 1), sum n_a = N."""
    s = math.sqrt(max(N - 1, 1))
    P, Q = np.asarray(P), np.asarray(Q)
    lo, hi = Q.max() + 1e-12, Q.max() + CPUCT * P.max() * s + 1.0

    def total(lam):
        return np.maximum(0.0, CPUCT * P * s / (lam - Q) - 1).sum()
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if total(mid) > N:
            lo = mid
        else:
            hi = mid
    n = np.maximum(0.0, CPUCT * P * s / (hi - Q) - 1)
    return int(np.argmax(n))


def m0_values(rows, cal):
    """M0: every rollout end in calibrated Heart-probability units. Death 0, Heart kill 1, a surviving end with
    X2-B x in act a: sigmoid(a_act + b logit x)."""
    a_act, b = cal
    intercept = np.array([a_act.get(min(max(a, 1), 4), 0.0) for a in range(5)])
    V = rows['V'].astype(np.float64)
    x = np.clip(V, 1e-6, 1 - 1e-6)
    p = 1 / (1 + np.exp(-(intercept[ACT_OF_FLOOR[np.clip(rows['F'], 0, 79)]] + b * np.log(x / (1 - x)))))
    return np.where(rows['T'], V, p)


def root_actions(d, death_values, cal=None):
    rows = d['rows']
    V = rows['V'].astype(np.float64)
    dead = rows['T'] & (rows['V'] == 0)
    if cal is not None:
        V = m0_values(rows, cal)
    elif death_values is not None:
        V = np.where(dead, death_values[ACT_OF_FLOOR[np.clip(rows['F'], 0, 79)]], V)
    per_row = V.mean(axis=1)
    per_row_death = dead.mean(axis=1)
    groups = defaultdict(list)
    for i, k in enumerate(rows['keys']):
        groups[k].append(i)
    keys = sorted(groups)
    q = [float(per_row[groups[k]].mean()) for k in keys]
    death = [float(per_row_death[groups[k]].mean()) for k in keys]
    return keys, q, death


def flips(sources, death_values, cal=None, null_slope=None):
    """null_slope: per act, the slope of Heart probability on today's rollout value if today's death price were
    right (death 0 maps to 0, the surviving level xbar to pbar): pbar / xbar. With cal (M0, values already in
    probability units), the predicted change per source is the sum of q1 differences over flipped roots under M0's
    own calibration, and the sum of null_slope x q0 differences under the null."""
    dv = np.zeros(5)
    for act, c in (death_values or {}).items():
        dv[act] = c
    res = defaultdict(lambda: defaultdict(float))
    examples = []
    for s in sources:
        for di, d in s['decisions'].items():
            keys0, q0, death0 = root_actions(d, None)
            if len(keys0) < 2:
                continue
            _, q1, _ = root_actions(d, dv, cal)
            P = [d['cands'].get(k, (0.0,))[0] for k in keys0]
            if sum(P) <= 0:
                continue
            m0, m1 = int(np.argmax(q0)), int(np.argmax(q1))
            p0, p1 = puct_pick(P, q0, d['sims']), puct_pick(P, q1, d['sims'])
            prior_top = max(c[0] for c in d['cands'].values())
            tags = ('all', f"act{d['act']}", 'full' if d['full'] else 'fast',
                    'priorTop<0.95' if prior_top < 0.95 else 'priorTop>=0.95')
            for t in tags:
                r = res[t]
                r['roots'] += 1
                r['meanFlip'] += m0 != m1
                r['puctFlip'] += p0 != p1
                r['proxyMatchesPlayed'] += keys0[p0] == d['selKey']
                if p0 != p1:
                    r['flipDeathDelta'] += death0[p1] - death0[p0]
                    r['flipToRiskier'] += death0[p1] > death0[p0]
                    if cal is not None:
                        r['gainOwn'] += q1[p1] - q1[p0]
                        r['gainNull'] += null_slope[d['act']] * (q0[p1] - q0[p0])
            if p0 != p1 and len(examples) < 40:
                examples.append({'seed': s['seed'], 'decision': di, 'act': d['act'], 'floor': d['floor'],
                                 'screen': d['screen'], 'from': keys0[p0], 'to': keys0[p1],
                                 'deathFrom': death0[p0], 'deathTo': death0[p1], 'qFrom': q0[p0], 'qTo': q0[p1],
                                 'played': d['selKey']})
    out = {}
    for t, r in res.items():
        n = r['roots']
        f = r['puctFlip']
        out[t] = {'roots': int(n), 'bestByMeanFlipShare': r['meanFlip'] / n, 'puctFlipShare': f / n,
                  'proxyMatchesPlayed': r['proxyMatchesPlayed'] / n,
                  'puctFlipsToRiskier': r['flipToRiskier'] / f if f else None,
                  'puctFlipMeanDeathDelta': r['flipDeathDelta'] / f if f else None}
        if cal is not None:
            n_sources = len(sources)
            out[t]['predictedHeartPerRunOwn'] = r['gainOwn'] / n_sources
            out[t]['predictedHeartPerRunNull'] = r['gainNull'] / n_sources
    return out, examples


def relevance(sources):
    c = defaultdict(int)
    for s in sources:
        for d in s['allDecisions'].values():
            top_key, top = max(d['cands'].items(), key=lambda kv: kv[1][0])
            c['searched'] += 1
            c['priorTop<0.95'] += top[0] < 0.95
            c['priorTop<0.99'] += top[0] < 0.99
            c['override'] += d['selKey'] != top_key
            c['full'] += d['full']
    n = c['searched']
    return {k: (v / n if k != 'searched' else v) for k, v in c.items()}


def main():
    extract, out = sys.argv[1], sys.argv[2]
    boot = int(sys.argv[sys.argv.index('--boot') + 1]) if '--boot' in sys.argv else 200
    jobs = int(sys.argv[sys.argv.index('--jobs') + 1]) if '--jobs' in sys.argv else 4
    sources, units = load(extract, jobs)
    pts = calibration_points(sources)
    cal = fit_calibration([(a, z, y) for a, z, y, _, _ in pts])
    lev = levels(sources)
    pr = prices(cal, lev)
    dr = death_rates(sources)
    drs = summarize_death_rates(dr)
    # source bootstrap of the calibration, the prices and the death-rate ratios
    rng = np.random.default_rng(20261023)
    by_seed, dr_by_seed = defaultdict(list), defaultdict(list)
    for p in pts:
        by_seed[p[3]].append(p)
    for p in dr:
        dr_by_seed[p[3]].append(p)
    seeds = sorted({s['seed'] for s in sources})
    bs = defaultdict(list)
    for _ in range(boot):
        pick = rng.choice(len(seeds), len(seeds))
        sample = [p for i in pick for p in by_seed[seeds[i]]]
        a_b, b_b = fit_calibration([(a, z, y) for a, z, y, _, _ in sample])
        bs['b'].append(b_b)
        for act, v in prices((a_b, b_b), lev).items():
            bs[f'overpricing{act}'].append(v['overpricing'])
            bs[f'c1_{act}'].append(v['c1'])
        for act, v in summarize_death_rates([p for i in pick for p in dr_by_seed[seeds[i]]]).items():
            if v['ratio'] is not None:
                bs[f'deathRatio{act}'].append(v['ratio'])
    ci = {k: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] for k, v in bs.items()}
    by_act = defaultdict(lambda: [0, 0, []])
    for a, _, y, _, x in pts:
        by_act[a][0] += 1
        by_act[a][1] += y
        by_act[a][2].append(x)
    observed = {a: {'roots': n, 'heartRate': h / n, 'meanX2bTaken': float(np.mean(xs))}
                for a, (n, h, xs) in sorted(by_act.items())}
    result = {'units': units, 'sources': len(sources), 'heartKills': sum(s['heart'] for s in sources),
              'calibration': {'intercepts': cal[0], 'slope': cal[1], 'points': len(pts)},
              'observedByAct': observed, 'levels': lev, 'prices': pr, 'deathRates': drs, 'bootstrap95': ci,
              'relevance': relevance(sources)}
    for k in (1, 2):
        dv = {act: pr[act][f'c{k}'] for act in (1, 2, 3)}
        f, ex = flips(sources, dv)
        result[f'flips_k{k}'] = {'deathValues': dv, 'byTag': f, 'examples': ex[:12]}
    # M0: the calibration applied to every surviving rollout end (death 0, kill 1). The null slope keeps today's
    # pricing: pbar / xbar per act (act 4: 1, its rollouts mostly end in a kill or a death).
    null = {act: pr[act]['pbar'] / pr[act]['xbar'] for act in (1, 2, 3)}
    null[4] = 1.0
    f, ex = flips(sources, None, cal, null)
    result['flips_m0'] = {'calibration': {'intercepts': cal[0], 'slope': cal[1]}, 'nullSlope': null, 'byTag': f,
                          'examples': ex[:12]}
    with open(out, 'w') as fh:
        json.dump(result, fh, indent=1)
    print(json.dumps({k: v for k, v in result.items() if not k.startswith('flips')}, indent=1))
    for k in (1, 2):
        print(f'k={k}', json.dumps(result[f'flips_k{k}']['deathValues']))
        for t, v in sorted(result[f'flips_k{k}']['byTag'].items()):
            print(' ', t, json.dumps(v))
    print('M0', json.dumps(result['flips_m0']['nullSlope']))
    for t, v in sorted(result['flips_m0']['byTag'].items()):
        print(' ', t, json.dumps(v))


if __name__ == '__main__':
    main()
