#!/usr/bin/env python3
"""Stage 5: backward fit V_A4 -> V_A3 -> V_A2 -> V_A1 + per-act level calibration + gate (README "Analysis").
Written and committed before the stage-4 capture was read; plumbing test-run once on the 32 run-1 pilot games only
(stage-4 dir empty): runs end to end, numbers meaningless at that size (act 2 stopped at 0 trees).
First full run was OOM-killed in act 1 (start records kept in memory); fix = keep feature vectors instead of records,
no change to any definition. Acts 3 and 2 of that run are reproduced by the rerun.
usage: stage5_fit.py RUN1_UNITS STAGE4_UNITS STAGE2_A4.pkl RUN1_A4.pkl OUT_DIR
  RUN1_UNITS / STAGE4_UNITS = verify_campaign.py --extract dirs (out/units/<id>/...).

V_A4: §720's G model family (GBM on the public entry record, run-1 entries labelled by their 5-game mean), fit on
TRAIN, early stopping on VALIDATION; no CTM feature, because act-end records have no S&S row.
V_k, k = 3, 2, 1: one example per (captured root, top-3 action, start state) on TRAIN/VALIDATION seeds:
  label = mean over that start's act-end rollouts of (0 after a death, V_{k+1}^cal(end record) otherwise),
  weight = rollouts; GBM on s0 features + HP fraction, monotone increasing in current HP and HP fraction.
  Level: V_k^cal = logistic(a + b logit V_k), fit on run-1 base-game states of act k (TRAIN seeds) vs the real kill.
Gate on TEST seeds (seed % 4 = 3), acts 1-3:
  (a) map-root concordance: pairs of priced actions with different labels (label = TEST rollouts scored with
      V_{k+1}^cal); V_k^cal(start) vs the production search's candidate q (rollout3 + X2-B + M0). PASS: diff >= +0.02,
      bootstrap CI (by seed) > 0.
  (b) real log loss at run-1 searched map roots: V_k^cal(state) vs the selected candidate's q. PASS: mean diff <= 0.
  (c) HP inversions at those states (HP -5 must not raise V): PASS 0.
  (d) one-card upgrades at those states that lower V by >= 0.5 pp: PASS share < 29.7 % (§705, all card ids here).
"""
import sys, os, json, gzip, glob, math, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'value_clean_labels_run1_20261029'))  # also reaches pilot_analysis
import fit_a4_run1 as R  # noqa: E402
import pilot_analysis as PA  # noqa: E402
F, s0 = R.F, R.s0
HP_COL, MAXHP_COL, FRAC_COL = s0.OFF['fixed'][0], s0.OFF['fixed'][0] + 1, s0.N_FEAT
DECK0, UP0 = s0.OFF['deck'][0], s0.OFF['deckUp'][0]


def rows(p):
    with gzip.open(p, 'rt') as f:
        return [json.loads(l) for l in f if l.strip()]


def feat_record(rec, act=None, floor=None):
    # pilot features (s0 without screen/selector/offer blocks) + HP fraction, for every act incl. V_A4
    fo = rec['obs.fixed_observation']
    return PA.feat(rec, rec['obs.act'] if act is None else act, fo[3] if floor is None else floor)


def split(seed): return s0.split_of(int(seed))


def logit(p): p = np.clip(p, 1e-4, 1 - 1e-4); return np.log(p / (1 - p))


def gbm(X, y, w, tr, va, mono=False):
    import xgboost as xgb
    best = None
    mc = None
    if mono:
        m = [0] * X.shape[1]; m[HP_COL] = 1; m[FRAC_COL] = 1; mc = '(' + ','.join(map(str, m)) + ')'
    for depth in (3, 4, 6):
        for mcw in (5, 20):
            prm = {'objective': 'binary:logistic', 'eval_metric': 'logloss', 'tree_method': 'hist', 'eta': 0.05, 'subsample': 0.8,
                   'colsample_bytree': 0.5, 'lambda': 5, 'max_depth': depth, 'min_child_weight': mcw, 'seed': 29, 'nthread': 4}
            if mc: prm['monotone_constraints'] = mc
            b = xgb.train(prm, xgb.DMatrix(X[tr], label=y[tr], weight=w[tr]), 3000,
                          evals=[(xgb.DMatrix(X[va], label=y[va], weight=w[va]), 'v')], early_stopping_rounds=100, verbose_eval=False)
            p = b.predict(xgb.DMatrix(X[va]), iteration_range=(0, b.best_iteration + 1))
            v = float((R.wbce(p, y[va]) * w[va]).sum() / w[va].sum())
            if best is None or v < best[0]: best = (v, depth, mcw, b, b.best_iteration)
    v, depth, mcw, b, it = best
    pred = lambda Z: b.predict(xgb.DMatrix(Z), iteration_range=(0, it + 1))
    return pred, {'val_bce': v, 'depth': depth, 'mcw': mcw, 'iters': int(it)}


def games(units):
    """seed -> (price path or None, game rows path) for base games."""
    out = {}
    for d in sorted(glob.glob(os.path.join(units, '*'))):
        for g in glob.glob(os.path.join(d, 'base-*.jsonl.gz')):
            if g.endswith('.ctm.jsonl.gz') or g.endswith('.price.jsonl.gz'): continue
            seed = int(os.path.basename(g)[5:-9]); pr = g[:-9] + '.price.jsonl.gz'
            out[seed] = (pr if os.path.exists(pr) else None, g)
    return out


def main(run1_units, stage4_units, p2, p1, out):
    import pickle
    os.makedirs(out, exist_ok=True)
    res = {'info': {}, 'acts': {}}
    # ---- V_A4 (real outcomes) ----
    es, _ = R.entries(pickle.load(open(p2, 'rb')), pickle.load(open(p1, 'rb')))
    X4 = np.array([feat_record(e['entry']['record'], e['entry']['act'], e['entry']['floor']) for e in es])
    n4 = np.array([len(e['kills']) for e in es], float); y4 = np.array([np.mean(e['kills']) for e in es])
    sp4 = np.array([split(e['seed']) for e in es])
    V = {}
    pred4, res['info']['V_A4'] = gbm(X4, y4, n4, sp4 == 'train', sp4 == 'validation')
    V[4] = pred4
    # ---- captured games: run-1 pilot units + stage-4 units ----
    cap = {}
    for u in (run1_units, stage4_units):
        for s, (pr, g) in games(u).items():
            if pr: cap[s] = (pr, g)
    run1 = games(run1_units)
    res['info']['captured_games'] = len(cap)
    # real states per act (run-1 base games) for calibration and the real-loss gate
    real = {k: [] for k in (1, 2, 3)}
    for s, (_, g) in run1.items():
        rs = rows(g); o = [r for r in rs if r.get('type') == 'outcome'][-1]
        st = {r['index']: r for r in rs if r.get('type') == 'state'}
        dec = {r['stateIndex']: r for r in rs if r.get('type') == 'decision'}
        for i, r in st.items():
            if r['act'] in real and r['screen'] == 5:   # map states only (where V_k is used)
                d = dec.get(i); q = None
                if d and d.get('searched') and r['screen'] == 5 and d.get('root'):
                    sel = d['root'].get('selectedId')
                    for c in d['root'].get('candidates', []):
                        if c['id'] == sel and c.get('visits', 0) > 0: q = c['q']
                real[r['act']].append((s, r['record'], r['act'], r['floor'], float(o['heartKilled']), q, r['screen']))
    Vcal = {4: V[4]}
    for k in (3, 2, 1):
        ex, test_roots = [], []
        for s, (pr, g) in sorted(cap.items()):
            qs = {}
            for r in rows(g):
                if r.get('type') == 'decision' and r.get('searched') and r.get('root'):
                    qs[r['decisionIndex']] = {c['key']: c['q'] for c in r['root'].get('candidates', []) if c.get('visits', 0) > 0}
            for r in rows(pr):
                if r['act'] != k or 'error' in r['price'] or 'priceError' in r: continue
                acts = []
                for a in r['price']['actions']:
                    ends = [e for e in a['actEnd'] if 'error' not in e]
                    recs = [e['endRecord'] for e in ends if e.get('endRecord') is not None and e['endRecord']['obs.act'] == k + 1]
                    vals = np.zeros(len(ends))
                    if recs:
                        pv = Vcal[k + 1](np.array([feat_record(x) for x in recs]))
                        j = 0
                        for i, e in enumerate(ends):
                            if e.get('endRecord') is not None and e['endRecord']['obs.act'] == k + 1: vals[i] = pv[j]; j += 1
                    starts = collections.defaultdict(list)
                    for e, v in zip(ends, vals):
                        if e.get('start') is not None: starts[e['start']].append(v)
                    for si, vs in starts.items():
                        ex.append((s, feat_record(a['starts'][si]), float(np.mean(vs)), len(vs)))  # features, not records (memory)
                    acts.append((a['key'], float(vals.mean()) if len(vals) else None,
                                 [(feat_record(a['starts'][si]), len(vs)) for si, vs in starts.items()]))
                if split(s) == 'test' and r['screen'] == 5 and len(acts) >= 2:
                    test_roots.append((s, acts, qs.get(r['decisionIndex'], {})))
        Xk = np.array([e[1] for e in ex]); yk = np.array([e[2] for e in ex]); wk = np.array([e[3] for e in ex], float)
        spk = np.array([split(e[0]) for e in ex])
        predk, info = gbm(Xk, yk, wk, spk == 'train', spk == 'validation', mono=True)
        info['examples'] = {t: int((spk == t).sum()) for t in ('train', 'validation', 'test')}
        # level calibration on run-1 real states of act k (TRAIN seeds)
        rk = [x for x in real[k] if split(x[0]) == 'train']
        Xr = np.array([feat_record(x[1], x[2], x[3]) for x in rk]); yr = np.array([x[4] for x in rk])
        from sklearn.linear_model import LogisticRegression
        cal = LogisticRegression(C=1e6).fit(logit(predk(Xr))[:, None], yr)
        info['calibration'] = {'a': float(cal.intercept_[0]), 'b': float(cal.coef_[0][0]), 'n': len(yr),
                               'raw_mean': float(predk(Xr).mean()), 'real_mean': float(yr.mean())}
        Vcal[k] = (lambda pk, c: (lambda Z: c.predict_proba(logit(pk(Z))[:, None])[:, 1]))(predk, cal)
        # ---- gate (a): concordance at TEST map roots ----
        dv, dq, pair_seed = [], [], []
        for s, acts, q in test_roots:
            pv = {}
            for key, lab, sts in acts:
                if lab is None or not sts: continue
                w = np.array([c for _, c in sts], float)
                pv[key] = float((Vcal[k](np.array([x for x, _ in sts])) * w).sum() / w.sum())
            labs = {key: lab for key, lab, _ in acts if lab is not None}
            keys = [x for x in labs if x in pv and x in q]
            for i in range(len(keys)):
                for j in range(i + 1, len(keys)):
                    a, b = keys[i], keys[j]
                    t = np.sign(labs[a] - labs[b])
                    if t == 0: continue
                    sc = lambda d: 0.5 if d == 0 else float(np.sign(d) == t)
                    dv.append(sc(pv[a] - pv[b])); dq.append(sc(q[a] - q[b])); pair_seed.append(s)
        dv, dq, pair_seed = np.array(dv), np.array(dq), np.array(pair_seed)
        conc = {'pairs': int(len(dv)), 'V': float(dv.mean()) if len(dv) else None, 'X2B_M0_search': float(dq.mean()) if len(dq) else None}
        if len(dv): conc['diff'] = float((dv - dq).mean()); conc['ci'] = F.boot(pair_seed, dv - dq)
        # ---- gate (b)-(d) on run-1 TEST searched map roots of act k ----
        rt = [x for x in real[k] if split(x[0]) == 'test' and x[5] is not None]
        Xt = np.array([feat_record(x[1], x[2], x[3]) for x in rt]); yt = np.array([x[4] for x in rt]); qt = np.array([x[5] for x in rt])
        st_seed = np.array([x[0] for x in rt]); pv = Vcal[k](Xt)
        d = R.wbce(pv, yt) - R.wbce(np.clip(qt, 1e-4, 1 - 1e-4), yt)
        real_loss = {'n': int(len(yt)), 'V': float(R.wbce(pv, yt).mean()), 'X2B_M0_search': float(R.wbce(np.clip(qt, 1e-4, 1 - 1e-4), yt).mean()),
                     'diff': float(d.mean()), 'ci': F.boot(st_seed, d)}
        Xh = Xt.copy(); Xh[:, HP_COL] = np.maximum(Xh[:, HP_COL] - 5, 0); Xh[:, FRAC_COL] = Xh[:, HP_COL] / np.maximum(Xt[:, MAXHP_COL], 1)
        hp_inv = int((Vcal[k](Xh) > pv + 1e-9).sum())
        up_n = up_bad = 0
        for i in range(len(Xt)):
            cards = [c for c in range(s0.N_CARDS) if Xt[i, DECK0 + c] > Xt[i, UP0 + c]]
            if not cards: continue
            Z = np.repeat(Xt[i:i + 1], len(cards), 0)
            for j, c in enumerate(cards): Z[j, UP0 + c] += 1
            pz = Vcal[k](Z); up_n += len(cards); up_bad += int((pz < pv[i] - 0.005).sum())
        res['acts'][k] = {'model': info, 'concordance': conc, 'real_loss': real_loss, 'hp_inversions': hp_inv,
                          'upgrade_wrong_way': {'pairs': up_n, 'share': up_bad / max(up_n, 1)}}
        print(k, json.dumps(res['acts'][k]), flush=True)
    g = {}
    for k in (1, 2, 3):
        a = res['acts'][k]
        g[k] = {'a': a['concordance'].get('diff', -1) >= 0.02 and a['concordance'].get('ci', [0])[0] > 0,
                'b': a['real_loss']['diff'] <= 0, 'c': a['hp_inversions'] == 0, 'd': a['upgrade_wrong_way']['share'] < 0.297}
        g[k]['PASS'] = all(g[k].values())
    res['gate'] = g
    json.dump(res, open(os.path.join(out, 'result.json'), 'w'), indent=1, default=float)
    print(json.dumps(res['gate'], indent=1))


if __name__ == '__main__':
    main(*sys.argv[1:6])
