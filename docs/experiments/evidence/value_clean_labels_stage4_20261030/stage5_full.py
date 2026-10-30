#!/usr/bin/env python3
"""Stage 5, second look (Philipp 14:44Z 10-30): stage5_fit.py's definitions and gate, but with the full public-record
encoder (full_feats.py: every record field) for V_A3..V_A1 and #915's drop-in V_A4 (va4_model) as the act-4 anchor.
The stage-4 TEST seeds were already read once by stage5_fit.py (acts 3 and 2, old s0 features); this run is a second
look at the same TEST and is labelled as such in the ledger.  A PASS here is confirmed on fresh replays before use.
usage: stage5_full.py RUN1_UNITS STAGE4_UNITS OUT_DIR [WORKERS]"""
import sys, os, json, gzip, glob, collections, pickle
from multiprocessing import Pool
import numpy as np
import scipy.sparse as sp
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'value_a4_improve_20261030', 'tools'))
import full_feats as FF  # noqa: E402
import stage5_fit as S5  # noqa: E402  (rows, games, split, logit, gbm settings)
R, F = S5.R, S5.F


def csr(rows):
    ip, ix, dv = [0], [], []
    for c, v in rows:
        ix += c; dv += v; ip.append(len(ix))
    return sp.csr_matrix((np.array(dv, np.float32), np.array(ix, np.int32), np.array(ip, np.int64)), shape=(len(rows), FF.N_FULL))


def enc(rec, act=None, floor=None):
    c, v = FF.enc(rec, act, floor); d = collections.defaultdict(float)
    for a, b in zip(c, v): d[a] += b
    return list(d.keys()), list(d.values())


def per_game(arg):
    """one captured game -> starts, rollouts, TEST map roots (features already encoded)."""
    seed, pr, g = arg
    import va4_model
    if not hasattr(per_game, 'va4'): per_game.va4 = va4_model.load()
    qs = {}
    for r in S5.rows(g):
        if r.get('type') == 'decision' and r.get('searched') and r.get('root'):
            qs[r['decisionIndex']] = {c['key']: c['q'] for c in r['root'].get('candidates', []) if c.get('visits', 0) > 0}
    starts, sact, roll, ends, a4 = [], [], [], [], []   # roll: (start id, kind, ref) kind 0 death, 1 end row, 2 V_A4 index
    roots = []
    for r in S5.rows(pr):
        k = r['act']
        if k not in (1, 2, 3) or 'error' in r['price'] or 'priceError' in r: continue
        acts = []
        for a in r['price']['actions']:
            sid = {}
            for e in a['actEnd']:
                if 'error' in e or e.get('start') is None: continue
                if e['start'] not in sid:
                    sid[e['start']] = len(starts); starts.append(enc(a['starts'][e['start']])); sact.append(k)
                er = e.get('endRecord')
                if er is None or er['obs.act'] != k + 1: roll.append((sid[e['start']], 0, -1))
                elif k == 3: roll.append((sid[e['start']], 2, len(a4))); a4.append(er)
                else: roll.append((sid[e['start']], 1, len(ends))); ends.append(enc(er))
            acts.append((a['key'], list(sid.values())))
        if S5.split(seed) == 'test' and r['screen'] == 5 and len(acts) >= 2:
            roots.append((k, acts, qs.get(r['decisionIndex'], {})))
    va4 = per_game.va4.predict([{'act': 4, 'floor': x['obs.fixed_observation'][3], 'record': x} for x in a4]) if a4 else np.zeros(0)
    return dict(seed=seed, startX=csr(starts), sact=np.array(sact, np.int8), roll=np.array(roll, np.int64).reshape(-1, 3),
                endX=csr(ends) if ends else None, va4=np.asarray(va4, np.float64), roots=roots)


def real_game(arg):
    """run-1 base game -> map states of acts 1-3 with features, real kill, selected candidate q."""
    seed, g = arg
    rs = S5.rows(g); o = [r for r in rs if r.get('type') == 'outcome'][-1]
    dec = {r['stateIndex']: r for r in rs if r.get('type') == 'decision'}
    out = []
    for r in rs:
        if r.get('type') != 'state' or r['act'] not in (1, 2, 3) or r['screen'] != 5: continue
        d = dec.get(r['index']); q = None
        if d and d.get('searched') and d.get('root'):
            for c in d['root'].get('candidates', []):
                if c['id'] == d['root'].get('selectedId') and c.get('visits', 0) > 0: q = c['q']
        out.append((seed, r['act'], enc(r['record'], r['act'], r['floor']), float(o['heartKilled']), q))
    return out


def gbm(X, y, w, tr, va):
    import xgboost as xgb
    m = ['0'] * FF.N_FULL; m[FF.HP_COL] = '1'; m[FF.FRAC_COL] = '1'; mc = '(' + ','.join(m) + ')'
    best = None
    for depth in (3, 4, 6):
        for mcw in (5, 20):
            prm = {'objective': 'binary:logistic', 'eval_metric': 'logloss', 'tree_method': 'hist', 'eta': 0.05, 'subsample': 0.8,
                   'colsample_bytree': 0.5, 'lambda': 5, 'max_depth': depth, 'min_child_weight': mcw, 'seed': 29, 'nthread': 4,
                   'monotone_constraints': mc}
            b = xgb.train(prm, xgb.DMatrix(X[tr], label=y[tr], weight=w[tr]), 3000,
                          evals=[(xgb.DMatrix(X[va], label=y[va], weight=w[va]), 'v')], early_stopping_rounds=100, verbose_eval=False)
            p = b.predict(xgb.DMatrix(X[va]), iteration_range=(0, b.best_iteration + 1))
            v = float((R.wbce(p, y[va]) * w[va]).sum() / w[va].sum())
            if best is None or v < best[0]: best = (v, depth, mcw, b, b.best_iteration)
    v, depth, mcw, b, it = best
    return (lambda Z: b.predict(xgb.DMatrix(Z), iteration_range=(0, it + 1))), {'val_bce': v, 'depth': depth, 'mcw': mcw, 'iters': int(it)}


def main(run1_units, stage4_units, out, workers=4):
    from sklearn.linear_model import LogisticRegression
    os.makedirs(out, exist_ok=True)
    cap = {}
    for u in (run1_units, stage4_units):
        for s, (pr, g) in S5.games(u).items():
            if pr: cap[s] = (pr, g)
    with Pool(int(workers)) as pool:
        G = pool.map(per_game, [(s, pr, g) for s, (pr, g) in sorted(cap.items())], chunksize=1)
        RG = pool.map(real_game, [(s, g) for s, (_, g) in sorted(S5.games(run1_units).items())], chunksize=4)
    real = [x for r in RG for x in r]
    res = {'info': {'captured_games': len(G), 'real_map_states': len(real), 'encoder_columns': FF.N_FULL,
                    'second_look': 'stage-4 TEST already read once by stage5_fit.py (acts 3, 2; s0 features)'}, 'acts': {}}
    Vcal = {}
    for k in (3, 2, 1):
        Xs, ys, ws, ss = [], [], [], []
        for gm in G:
            sel = np.where(gm['sact'] == k)[0]
            if not len(sel): continue
            v = np.zeros(len(gm['roll']))
            ro = gm['roll']
            if k == 3:
                m = ro[:, 1] == 2; v[m] = gm['va4'][ro[m, 2]]
            else:
                m = ro[:, 1] == 1
                if m.any(): v[m] = Vcal[k + 1](gm['endX'][ro[m, 2]])
            sm = collections.defaultdict(list)
            for (sid, _, _), x in zip(ro, v):
                if gm['sact'][sid] == k: sm[sid].append(x)
            gm['lab%d' % k] = sm
            ids = sorted(sm)
            Xs.append(gm['startX'][ids]); ys += [np.mean(sm[i]) for i in ids]; ws += [len(sm[i]) for i in ids]; ss += [gm['seed']] * len(ids)
        Xk = sp.vstack(Xs).tocsr(); yk = np.array(ys); wk = np.array(ws, float); spk = np.array([S5.split(s) for s in ss])
        predk, info = gbm(Xk, yk, wk, spk == 'train', spk == 'validation')
        info['examples'] = {t: int((spk == t).sum()) for t in ('train', 'validation', 'test')}
        del Xs, Xk
        rk = [x for x in real if x[1] == k and S5.split(x[0]) == 'train']
        Xr = csr([x[2] for x in rk]); yr = np.array([x[3] for x in rk], float)
        cal = LogisticRegression(C=1e6).fit(S5.logit(predk(Xr))[:, None], yr) if len(set(yr)) == 2 else None
        if cal is None:   # only in tiny plumbing tests
            cal = LogisticRegression(C=1e6).fit(np.array([[-1.0], [1.0]]), np.array([0, 1]))
        info['calibration'] = {'a': float(cal.intercept_[0]), 'b': float(cal.coef_[0][0]), 'n': len(yr),
                               'raw_mean': float(predk(Xr).mean()) if len(yr) else None, 'real_mean': float(yr.mean()) if len(yr) else None}
        Vcal[k] = (lambda pk, c: (lambda Z: c.predict_proba(S5.logit(pk(Z))[:, None])[:, 1]))(predk, cal)
        # (a) concordance at TEST map roots
        dv, dq, ps = [], [], []
        for gm in G:
            for kk, acts, q in gm['roots']:
                if kk != k: continue
                sm = gm['lab%d' % k]; pv, lab = {}, {}
                for key, sids in acts:
                    sids = [i for i in sids if i in sm]
                    if not sids: continue
                    w = np.array([len(sm[i]) for i in sids], float)
                    pv[key] = float((Vcal[k](gm['startX'][sids]) * w).sum() / w.sum())
                    lab[key] = float(np.mean([x for i in sids for x in sm[i]]))
                keys = [x for x in lab if x in q]
                for i in range(len(keys)):
                    for j in range(i + 1, len(keys)):
                        a, b = keys[i], keys[j]; t = np.sign(lab[a] - lab[b])
                        if t == 0: continue
                        sc = lambda d: 0.5 if d == 0 else float(np.sign(d) == t)
                        dv.append(sc(pv[a] - pv[b])); dq.append(sc(q[a] - q[b])); ps.append(gm['seed'])
        dv, dq, ps = np.array(dv), np.array(dq), np.array(ps)
        conc = {'pairs': int(len(dv)), 'diff': -1.0, 'ci': [-1.0, -1.0]}
        if len(dv):
            conc.update(V=float(dv.mean()), X2B_M0_search=float(dq.mean()), diff=float((dv - dq).mean()), ci=F.boot(ps, dv - dq))
        # (b)-(d) run-1 TEST searched map roots
        rt = [x for x in real if x[1] == k and S5.split(x[0]) == 'test' and x[4] is not None]
        real_loss, hp_inv, up_n, up_bad = {'n': 0, 'diff': 1.0}, -1, 0, 0
        if rt:
            Xt = csr([x[2] for x in rt]).toarray(); yt = np.array([x[3] for x in rt]); qt = np.clip([x[4] for x in rt], 1e-4, 1 - 1e-4)
            pv = Vcal[k](Xt); d = R.wbce(pv, yt) - R.wbce(qt, yt)
            real_loss = {'n': int(len(yt)), 'V': float(R.wbce(pv, yt).mean()), 'X2B_M0_search': float(R.wbce(qt, yt).mean()),
                         'diff': float(d.mean()), 'ci': F.boot(np.array([x[0] for x in rt]), d)}
            Xh = Xt.copy(); Xh[:, FF.HP_COL] = np.maximum(Xh[:, FF.HP_COL] - 5, 0); Xh[:, FF.FRAC_COL] = Xh[:, FF.HP_COL] / np.maximum(Xt[:, FF.MAXHP_COL], 1)
            hp_inv = int((Vcal[k](Xh) > pv + 1e-9).sum())
            up_n = up_bad = 0
            for i in range(len(Xt)):
                cards = [c for c in range(FF.NC) if Xt[i, FF.DECK0 + c] > Xt[i, FF.UP0 + c]]
                if not cards: continue
                Z = np.repeat(Xt[i:i + 1], len(cards), 0)
                for j, c in enumerate(cards): Z[j, FF.UP0 + c] += 1
                up_n += len(cards); up_bad += int((Vcal[k](Z) < pv[i] - 0.005).sum())
        res['acts'][k] = {'model': info, 'concordance': conc, 'real_loss': real_loss, 'hp_inversions': hp_inv,
                          'upgrade_wrong_way': {'pairs': up_n, 'share': up_bad / max(up_n, 1)}}
        print(k, json.dumps(res['acts'][k]), flush=True)
    g = {}
    for k in (1, 2, 3):
        a = res['acts'][k]
        g[k] = {'a': a['concordance']['diff'] >= 0.02 and a['concordance']['ci'][0] > 0, 'b': a['real_loss']['diff'] <= 0,
                'c': a['hp_inversions'] == 0, 'd': a['upgrade_wrong_way']['share'] < 0.297}
        g[k]['PASS'] = all(g[k].values())
    res['gate'] = g
    json.dump(res, open(os.path.join(out, 'result.json'), 'w'), indent=1, default=float)
    print(json.dumps(g, indent=1))


if __name__ == '__main__':
    main(*sys.argv[1:5])
