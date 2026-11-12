#!/usr/bin/env python3
"""Learned budget step B0 (offline): run-value currency V(post-fight state) = P(Heart kill | state after a won fight).

Input: ../gumbel_wholerun_trace_20261109/results/battles.csv.gz (§775's 2,048 traced games, arms D and G16).
Label: the seed's game (same arm) kills the Heart (a won THE_HEART battle). Rows: won fights of Acts 1-3 (a lost
fight has V = 0 by definition). Features after the fight: act, floor, room, hp_post, maxhp_post, hp share, deck_pre,
potions_post, gold_pre. Models: logistic (hp share, hp, maxhp, act dummies) and monotone gradient boosting (HP
monotone increasing), 5 folds by seed, fit per arm and pooled. Reports cross-fitted log loss / Brier against the
act x room base rate, calibration by decile, and dV/dHP: the Heart-probability value of +1 HP and of a death
(V(alive) - 0) by act and room, i.e. how many HP one death is worth.
usage: python3 -I currency.py battles.csv.gz out.json
"""
import csv, gzip, json, sys, collections
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, brier_score_loss

rows = list(csv.DictReader(gzip.open(sys.argv[1], 'rt')))
heart = {(r['seed'], r['arm']): 0 for r in rows}
for r in rows:
    if r['encounter'] == 'THE_HEART' and r['won'] == '1':
        heart[(r['seed'], r['arm'])] = 1
B = [r for r in rows if r['won'] == '1' and int(r['act']) <= 3]
ROOMS = ['NORMAL', 'ELITE', 'BOSS']
room = lambda r: r['room'] if r['room'] in ROOMS else 'NORMAL'


def X_of(rs, hp_delta=0):
    X = []
    for r in rs:
        hp = min(int(r['hp_post']) + hp_delta, int(r['maxhp_post']))
        mx = int(r['maxhp_post'])
        a = int(r['act'])
        X.append([a, int(r['floor']), ROOMS.index(room(r)), hp, mx, hp / mx, int(r['deck_pre']),
                  int(r['potions_post']), int(r['gold_pre'])])
    return np.array(X, float)


MONO = [0, 0, 0, 1, 0, 1, 0, 0, 0]
out = {'n_won_fights': len(B), 'heart_rate': {a: float(np.mean([v for (s, aa), v in heart.items() if aa == a]))
                                              for a in ('D', 'G16')}}
seeds = sorted({r['seed'] for r in B})
fold_of = {s: i % 5 for i, s in enumerate(np.random.default_rng(20261112).permutation(seeds))}

for arm in ('G16', 'D', 'pooled'):
    rs = [r for r in B if arm == 'pooled' or r['arm'] == arm]
    X = X_of(rs)
    if arm == 'pooled':
        X = np.c_[X, [r['arm'] == 'G16' for r in rs]]
    y = np.array([heart[(r['seed'], r['arm'])] for r in rs])
    f = np.array([fold_of[r['seed']] for r in rs])
    base = np.zeros(len(rs)); pg = np.zeros(len(rs)); pl = np.zeros(len(rs))
    keys = [(int(r['act']), room(r)) for r in rs]
    for k in range(5):
        tr, te = f != k, f == k
        rate = collections.defaultdict(list)
        for i in np.where(tr)[0]:
            rate[keys[i]].append(y[i])
        base[te] = [np.mean(rate[keys[i]]) for i in np.where(te)[0]]
        g = HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05, max_iter=300, min_samples_leaf=100,
                                           monotonic_cst=MONO + ([0] if arm == 'pooled' else []), random_state=0)
        g.fit(X[tr], y[tr]); pg[te] = g.predict_proba(X[te])[:, 1]
        lr = LogisticRegression(max_iter=2000, C=1.0)
        Z = lambda M: np.c_[M[:, 5], M[:, 3] / 100, M[:, 4] / 100, M[:, 0] == 2, M[:, 0] == 3, M[:, 1] / 50]
        lr.fit(Z(X[tr]), y[tr]); pl[te] = lr.predict_proba(Z(X[te]))[:, 1]
    res = dict(n=len(rs), runs=len({r['seed'] for r in rs}))
    for name, p in (('act_room_base', base), ('logistic', pl), ('gbm_monotone', pg)):
        p = np.clip(p, 1e-4, 1 - 1e-4)
        res[name] = dict(logloss=round(float(log_loss(y, p)), 4), brier=round(float(brier_score_loss(y, p)), 4))
    # calibration of the gbm by decile
    q = np.quantile(pg, np.linspace(0, 1, 11))
    res['gbm_calibration'] = [[round(float(pg[(pg >= q[i]) & (pg <= q[i + 1])].mean()), 3),
                               round(float(y[(pg >= q[i]) & (pg <= q[i + 1])].mean()), 3)] for i in range(10)]
    # full-data fit for the exchange rates
    g = HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05, max_iter=300, min_samples_leaf=100,
                                       monotonic_cst=MONO + ([0] if arm == 'pooled' else []), random_state=0).fit(X, y)
    def V(rs_, d=0):
        M = X_of(rs_, d)
        if arm == 'pooled':
            M = np.c_[M, [r['arm'] == 'G16' for r in rs_]]
        return g.predict_proba(M)[:, 1]
    xr = {}
    for a in (1, 2, 3):
        for rm in ROOMS:
            sub = [r for r in rs if int(r['act']) == a and room(r) == rm]
            if len(sub) < 200:
                continue
            v0 = V(sub); v5 = V(sub, 5); vm5 = V(sub, -5)
            per_hp = float((v5 - vm5).mean() / 10)
            xr[f'A{a} {rm}'] = dict(n=len(sub), V_mean=round(float(v0.mean()), 4),
                                    dV_per_HP_pp=round(100 * per_hp, 3),
                                    death_in_HP=round(float(v0.mean()) / per_hp, 1) if per_hp > 0 else None)
    res['exchange'] = xr
    out[arm] = res

print(json.dumps(out, indent=1))
open(sys.argv[2], 'w').write(json.dumps(out, indent=1) + '\n')
