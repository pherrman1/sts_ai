#!/usr/bin/env python3
"""Stage 5b: backward fit V_A3 -> V_A2 -> V_A1 on all captured games, gate on the FRESH capture-2 TEST.
Written and committed before the capture-2 data is read (README).  Same label definitions, encoder (full_feats.py),
V_A4 anchor (#915 va4_model) and gate as ../value_clean_labels_stage4_20261030/stage5_full.py, with three changes:
  1. splits: capture-2 seeds (111384032-111385023) by seed % 4 (3 TEST, 2 VALIDATION, else TRAIN); the already read
     pilot + stage-4 games are TRAIN (seed % 4 != 2) or VALIDATION (== 2) and never enter the gate.
  2. level calibration on real run-1 map states of VALIDATION games (not used to fit the GBM; stage 5 calibrated on
     TRAIN games the model had seen -> slope 1.6, overconfident on TEST).
  3. stronger regularisation against memorising single games: colsample 0.3, min_child_weight in {20, 200}.
Memory: one pass over the price files per act; act-end values are scored inside the workers.
usage: stage5b.py RUN1_UNITS STAGE4_UNITS CAPTURE2_UNITS OUT_DIR [WORKERS]"""
import sys, os, json, collections, pickle
import multiprocessing as mp
import numpy as np
import scipy.sparse as sp
HERE = os.path.dirname(os.path.abspath(__file__))
S4 = os.path.join(HERE, '..', 'value_clean_labels_stage4_20261030')
sys.path.insert(0, S4)
sys.path.insert(0, os.path.join(HERE, '..', 'value_a4_improve_20261030', 'tools'))
import full_feats as FF  # noqa: E402
import stage5_fit as S5  # noqa: E402
import stage5_full as SF  # noqa: E402
R, F = S5.R, S5.F
C2 = range(*map(int, os.environ.get('STAGE5B_C2', '111384032:111385024').split(':')))   # env only for plumbing tests


def split(seed):
    if int(seed) in C2: return S5.split(seed)
    return 'validation' if int(seed) % 4 == 2 else 'train'


class VCal:
    def __init__(self, booster, it, a, b): self.raw, self.it, self.a, self.b = booster.save_raw('ubj'), it, a, b; self.bst = None

    def __call__(self, Z):
        import xgboost as xgb
        if self.bst is None: self.bst = xgb.Booster(); self.bst.load_model(bytearray(self.raw))
        # trained on CSR, where XGBoost reads absent entries as MISSING; a dense 0 would take the other branch.
        # Fix after the first run (results commit discloses it): (b)-(d) used dense input, which scored nonsense.
        if not sp.issparse(Z): Z = sp.csr_matrix(Z)
        p = self.bst.predict(xgb.DMatrix(Z), iteration_range=(0, self.it + 1))
        return 1 / (1 + np.exp(-(self.a + self.b * S5.logit(p))))

    def __getstate__(self): return {'raw': self.raw, 'it': self.it, 'a': self.a, 'b': self.b}

    def __setstate__(self, d): self.__dict__.update(d); self.bst = None


_V = None


def _init(v):
    global _V
    _V = v


def per_game(arg):
    """one captured game, act k -> start rows of act k, rollout values, TEST map roots."""
    seed, pr, g, k = arg
    qs = {}
    if split(seed) == 'test' and int(seed) in C2:
        for r in S5.rows(g):
            if r.get('type') == 'decision' and r.get('searched') and r.get('root'):
                qs[r['decisionIndex']] = {c['key']: c['q'] for c in r['root'].get('candidates', []) if c.get('visits', 0) > 0}
    starts, roll, ends, roots = [], [], [], []   # roll: (start id, end index or -1 for death)
    for r in S5.rows(pr):
        if r['act'] != k or 'error' in r['price'] or 'priceError' in r: continue
        acts = []
        for a in r['price']['actions']:
            sid = {}
            for e in a['actEnd']:
                if 'error' in e or e.get('start') is None: continue
                if e['start'] not in sid:
                    sid[e['start']] = len(starts); starts.append(SF.enc(a['starts'][e['start']]))
                er = e.get('endRecord')
                if er is None or er['obs.act'] != k + 1: roll.append((sid[e['start']], -1))
                else: roll.append((sid[e['start']], len(ends))); ends.append(er)
            acts.append((a['key'], list(sid.values())))
        if qs and r['screen'] == 5 and len(acts) >= 2:
            roots.append((acts, qs.get(r['decisionIndex'], {})))
    if k == 3:
        import va4_model
        if not hasattr(per_game, 'va4'): per_game.va4 = va4_model.load()
        ev = per_game.va4.predict([{'act': 4, 'floor': x['obs.fixed_observation'][3], 'record': x} for x in ends]) if ends else []
    else:
        ev = _V(SF.csr([SF.enc(x) for x in ends])) if ends else []
    ev = np.asarray(ev, np.float64)
    lab = collections.defaultdict(list)
    for sid, ei in roll: lab[sid].append(ev[ei] if ei >= 0 else 0.0)
    ids = sorted(lab)
    X = SF.csr(starts)[ids] if ids else None
    pos = {s: i for i, s in enumerate(ids)}
    roots = [([(key, [pos[i] for i in sids if i in pos]) for key, sids in acts], q) for acts, q in roots]
    return dict(seed=seed, X=X, y=np.array([np.mean(lab[i]) for i in ids]), w=np.array([len(lab[i]) for i in ids], float),
                rolls=[lab[i] for i in ids], roots=roots)


def gbm(X, y, w, tr, va):
    import xgboost as xgb
    m = ['0'] * FF.N_FULL; m[FF.HP_COL] = '1'; m[FF.FRAC_COL] = '1'; mc = '(' + ','.join(m) + ')'
    best = None
    for depth in (3, 4, 6):
        for mcw in (20, 200):
            prm = {'objective': 'binary:logistic', 'eval_metric': 'logloss', 'tree_method': 'hist', 'eta': 0.05, 'subsample': 0.8,
                   'colsample_bytree': 0.3, 'lambda': 5, 'max_depth': depth, 'min_child_weight': mcw, 'seed': 29, 'nthread': 4,
                   'monotone_constraints': mc}
            b = xgb.train(prm, xgb.DMatrix(X[tr], label=y[tr], weight=w[tr]), 3000,
                          evals=[(xgb.DMatrix(X[va], label=y[va], weight=w[va]), 'v')], early_stopping_rounds=100, verbose_eval=False)
            p = b.predict(xgb.DMatrix(X[va]), iteration_range=(0, b.best_iteration + 1))
            v = float((R.wbce(p, y[va]) * w[va]).sum() / w[va].sum())
            if best is None or v < best[0]: best = (v, depth, mcw, b, b.best_iteration)
    v, depth, mcw, b, it = best
    return b, int(it), {'val_bce': v, 'depth': depth, 'mcw': mcw, 'iters': int(it)}


def main(run1_units, stage4_units, cap2_units, out, workers=4):
    from sklearn.linear_model import LogisticRegression
    import xgboost as xgb
    os.makedirs(out, exist_ok=True)
    cap = {}
    for u in (run1_units, stage4_units, cap2_units):
        for s, (pr, g) in S5.games(u).items():
            if pr: cap[s] = (pr, g)
    Pool = mp.get_context('spawn').Pool   # fork after xgboost threads hangs
    with Pool(int(workers)) as pool:
        real = [x for r in pool.map(SF.real_game, [(s, g) for s, (_, g) in sorted(S5.games(run1_units).items())], chunksize=4) for x in r]
    res = {'info': {'captured_games': len(cap), 'capture2_games': sum(1 for s in cap if s in C2), 'real_map_states': len(real),
                    'encoder_columns': FF.N_FULL}, 'acts': {}}
    V = None
    for k in (3, 2, 1):
        with Pool(int(workers), initializer=_init, initargs=(V,)) as pool:
            G = [g for g in pool.map(per_game, [(s, pr, g, k) for s, (pr, g) in sorted(cap.items())], chunksize=1) if g['X'] is not None]
        Xk = sp.vstack([g['X'] for g in G]).tocsr(); yk = np.concatenate([g['y'] for g in G]); wk = np.concatenate([g['w'] for g in G])
        spk = np.concatenate([[split(g['seed'])] * len(g['y']) for g in G])
        tr = spk == 'train'; va = spk == 'validation'
        b, it, info = gbm(Xk, yk, wk, tr, va)
        info['examples'] = {t: int((spk == t).sum()) for t in ('train', 'validation', 'test')}
        del Xk
        raw = lambda Z: b.predict(xgb.DMatrix(Z), iteration_range=(0, it + 1))
        rc = [x for x in real if x[1] == k and split(x[0]) == 'validation']
        Xr = SF.csr([x[2] for x in rc]); yr = np.array([x[3] for x in rc], float)
        if len(set(yr)) == 2: cal = LogisticRegression(C=1e6).fit(S5.logit(raw(Xr))[:, None], yr)
        else: cal = LogisticRegression(C=1e6).fit(np.array([[-1.0], [1.0]]), np.array([0, 1]))   # tiny plumbing tests only
        info['calibration'] = {'a': float(cal.intercept_[0]), 'b': float(cal.coef_[0][0]), 'n': len(yr), 'games': len({x[0] for x in rc}),
                               'raw_mean': float(raw(Xr).mean()), 'real_mean': float(yr.mean())}
        V = VCal(b, it, float(cal.intercept_[0]), float(cal.coef_[0][0]))
        pickle.dump(V, open(os.path.join(out, f'V_A{k}.pkl'), 'wb'))
        # (a) concordance at fresh TEST map roots
        dv, dq, ps = [], [], []
        for g in G:
            for acts, q in g['roots']:
                pv, lab = {}, {}
                for key, ii in acts:
                    if not ii: continue
                    w = g['w'][ii]; pv[key] = float((V(g['X'][ii]) * w).sum() / w.sum())
                    lab[key] = float(np.mean([x for i in ii for x in g['rolls'][i]]))
                keys = [x for x in lab if x in q]
                for i in range(len(keys)):
                    for j in range(i + 1, len(keys)):
                        a, c = keys[i], keys[j]; t = np.sign(lab[a] - lab[c])
                        if t == 0: continue
                        sc = lambda d: 0.5 if d == 0 else float(np.sign(d) == t)
                        dv.append(sc(pv[a] - pv[c])); dq.append(sc(q[a] - q[c])); ps.append(g['seed'])
        dv, dq, ps = np.array(dv), np.array(dq), np.array(ps)
        conc = {'pairs': int(len(dv)), 'diff': -1.0, 'ci': [-1.0, -1.0]}
        if len(dv):
            conc.update(V=float(dv.mean()), X2B_M0_search=float(dq.mean()), diff=float((dv - dq).mean()), ci=F.boot(ps, dv - dq))
        # (b)-(d) real run-1 map states of fresh TEST games
        rt = [x for x in real if x[1] == k and x[0] in C2 and split(x[0]) == 'test' and x[4] is not None]
        real_loss, hp_inv, up_n, up_bad = {'n': 0, 'diff': 1.0}, -1, 0, 0
        if rt:
            Xt = SF.csr([x[2] for x in rt]).toarray(); yt = np.array([x[3] for x in rt], float); qt = np.clip([x[4] for x in rt], 1e-4, 1 - 1e-4)
            pv = V(Xt); d = R.wbce(pv, yt) - R.wbce(qt, yt)
            real_loss = {'n': int(len(yt)), 'V': float(R.wbce(pv, yt).mean()), 'X2B_M0_search': float(R.wbce(qt, yt).mean()),
                         'diff': float(d.mean()), 'ci': F.boot(np.array([x[0] for x in rt]), d)}
            Xh = Xt.copy(); Xh[:, FF.HP_COL] = np.maximum(Xh[:, FF.HP_COL] - 5, 0); Xh[:, FF.FRAC_COL] = Xh[:, FF.HP_COL] / np.maximum(Xt[:, FF.MAXHP_COL], 1)
            hp_inv = int((V(Xh) > pv + 1e-9).sum())
            up_n = up_bad = 0
            for i in range(len(Xt)):
                cards = [c for c in range(FF.NC) if Xt[i, FF.DECK0 + c] > Xt[i, FF.UP0 + c]]
                if not cards: continue
                Z = np.repeat(Xt[i:i + 1], len(cards), 0)
                for j, c in enumerate(cards): Z[j, FF.UP0 + c] += 1
                up_n += len(cards); up_bad += int((V(Z) < pv[i] - 0.005).sum())
        res['acts'][k] = {'model': info, 'concordance': conc, 'real_loss': real_loss, 'hp_inversions': hp_inv,
                          'upgrade_wrong_way': {'pairs': up_n, 'share': up_bad / max(up_n, 1)}}
        print(k, json.dumps(res['acts'][k]), flush=True)
        del G
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
    main(*sys.argv[1:6])
