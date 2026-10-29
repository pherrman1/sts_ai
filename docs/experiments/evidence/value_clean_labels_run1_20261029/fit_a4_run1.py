#!/usr/bin/env python3
"""Run-1 V_A4 refit (README "Analysis"; written before the run's data was read).
usage: fit_a4_run1.py STAGE2_A4.pkl RUN1_A4.pkl OUT_DIR
RUN1_A4.pkl = ../value_clean_labels_20261029/tools/extract_a4.py over /mnt/project-files/value-clean-labels-run1.

Entries: stage-2 entries (one outcome each) + run-1 entries (base game + forks from the same Act-4 entry; the entry
record and the CTM's S&S row come from the base game). Label = mean Heart kill over the entry's games, weight = games.
Models: G / GC as in stage 2 (fit_a4.py), trained on TRAIN of both sources, picked on VALIDATION.
TEST = run-1 entries with seed % 4 = 3 (s0.split_of), scored per game (weighted BCE).
Also: the same fit with run-1 entries labelled by the base game only (isolates the extra labels), and the label noise
(within-entry outcome variance over p(1-p))."""
import sys, os, json, math, pickle, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'value_clean_labels_20261029', 'tools'))
import fit_a4 as F  # noqa: E402  (also puts s0 on the path)
s0 = F.s0
RUN1 = 'value-clean-labels-run1'


def entries(stage2, run1):
    out = []
    for r in stage2:
        if r['campaign'] in F.CAMPS and r['strong'] and r['reachedA4']:
            out.append(dict(src='stage2', seed=r['seed'], entry=r['entry'], ctm=r.get('ctm_a4', []), kills=[r['heartKilled']]))
    by = collections.defaultdict(dict)
    for r in run1:
        if r['campaign'] == RUN1:
            by[r['seed']][r['game']] = r
    bad = 0
    for seed, games in sorted(by.items()):
        base = games.get(f'base-{seed}')
        if base is None or not base['reachedA4']:
            continue
        forks = [g for k, g in games.items() if k.startswith('fork-')]
        if not base['strong'] or any(not g['strong'] or not g['reachedA4'] or g['entry']['record'] != base['entry']['record'] for g in forks):
            bad += 1; continue
        out.append(dict(src='run1', seed=seed, entry=base['entry'], ctm=base.get('ctm_a4', []),
                        kills=[base['heartKilled']] + [g['heartKilled'] for g in forks]))
    return out, bad


def design(es, model):
    X = np.zeros((len(es), s0.N_FEAT + 1), np.float32); c = np.full(len(es), np.nan)
    for i, e in enumerate(es):
        cols, vals = s0.features(e['entry']); X[i, cols] = vals
        fo = e['entry']['record']['obs.fixed_observation']; X[i, -1] = fo[0] / max(fo[1], 1)
        ss = [q for q in e['ctm'] if q['roomClass'] == 'ELITE' and q['predictorInput']['globals']['encounter'] == F.SS]
        if ss:
            p = ss[0]['predictorInput']
            c[i] = (1 - F.tree_pred(model, F.ctm_feats(p, 0))) * (1 - F.tree_pred(model, F.ctm_feats(p, 1)))
    return X, c


def wbce(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6); return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def fit(X, y, w, tr, va, tag, info):
    import xgboost as xgb
    best = None
    for depth in (2, 3, 4):
        for mcw in (5, 20):
            prm = {'objective': 'binary:logistic', 'eval_metric': 'logloss', 'tree_method': 'hist', 'eta': 0.03, 'subsample': 0.8,
                   'colsample_bytree': 0.5, 'lambda': 5, 'max_depth': depth, 'min_child_weight': mcw, 'seed': 29, 'nthread': 4}
            b = xgb.train(prm, xgb.DMatrix(X[tr], label=y[tr], weight=w[tr]), 3000,
                          evals=[(xgb.DMatrix(X[va], label=y[va], weight=w[va]), 'v')], early_stopping_rounds=100, verbose_eval=False)
            p = b.predict(xgb.DMatrix(X), iteration_range=(0, b.best_iteration + 1))
            v = float((wbce(p[va], y[va]) * w[va]).sum() / w[va].sum())
            if best is None or v < best[0]: best = (v, depth, mcw, int(b.best_iteration), p)
    info[tag] = {'val_bce': best[0], 'depth': best[1], 'mcw': best[2], 'iters': best[3]}
    return best[4]


def main(p2, p1, out):
    from sklearn.linear_model import LogisticRegression
    os.makedirs(out, exist_ok=True)
    es, bad = entries(pickle.load(open(p2, 'rb')), pickle.load(open(p1, 'rb')))
    model = F.load_trees(os.path.join(F.REPO, 'models/candidates/ctm_act4_survival_trees.txt'))
    X, c = design(es, model)
    n = np.array([len(e['kills']) for e in es], float)
    y5 = np.array([np.mean(e['kills']) for e in es]); y1 = np.array([float(e['kills'][0]) for e in es])
    seed = np.array([e['seed'] for e in es]); run1 = np.array([e['src'] == 'run1' for e in es])
    split = np.array([s0.split_of(int(s)) for s in seed])
    tr, va = split == 'train', split == 'validation'; te = (split == 'test') & run1
    info = {'entries': {'stage2': int((~run1).sum()), 'run1': int(run1.sum()), 'run1_rejected': bad},
            'run1_games_per_entry': dict(collections.Counter(n[run1].astype(int).tolist())),
            'run1_test_entries': int(te.sum()), 'run1_kill_rate': float((y5[run1] * n[run1]).sum() / n[run1].sum())}
    # label noise: unbiased within-entry variance over the Bernoulli variance at the pooled rate
    m = run1 & (n >= 2); pbar = float((y5[m] * n[m]).sum() / n[m].sum())
    within = float(np.mean(n[m] / (n[m] - 1) * y5[m] * (1 - y5[m])))
    info['label_noise'] = {'entries': int(m.sum()), 'pooled_p': pbar, 'within_var': within, 'ratio_to_bernoulli': within / (pbar * (1 - pbar))}
    cf = np.where(np.isnan(c), np.nanmean(c[tr]), c)
    lc = np.log(np.clip(cf, 1e-4, 1 - 1e-4) / (1 - np.clip(cf, 1e-4, 1 - 1e-4)))
    info['ctm_missing'] = int(np.isnan(c).sum())
    # CTM recalibration on TRAIN games (per-game weights)
    Xg = np.repeat(lc[tr, None], 2, 0); yg = np.r_[np.ones(tr.sum()), np.zeros(tr.sum())]
    wg = np.r_[y5[tr] * n[tr], (1 - y5[tr]) * n[tr]]
    rec = LogisticRegression(C=1e6).fit(Xg, yg, sample_weight=wg); c_cal = rec.predict_proba(lc[:, None])[:, 1]
    XC = np.hstack([X, lc[:, None]])
    w1 = np.where(run1, 1.0, n)  # base-only labels: one game per entry
    preds = {}
    for lab, y, w in (('5', y5, n), ('1', y1, w1)):
        g = fit(X, y, w, tr, va, f'G_{lab}', info); gc = fit(XC, y, w, tr, va, f'GC_{lab}', info)
        pick = 'G' if info[f'G_{lab}']['val_bce'] <= info[f'GC_{lab}']['val_bce'] else 'GC'
        info[f'picked_{lab}'] = pick
        preds[f'G_{lab}'], preds[f'GC_{lab}'], preds[f'picked_{lab}'] = g, gc, (g if pick == 'G' else gc)
    preds['CTM_recal'] = c_cal; preds['CTM_raw'] = cf
    preds['const'] = np.full(len(y5), float((y5[tr] * n[tr]).sum() / n[tr].sum()))
    # ---- TEST: run-1 entries, every game of the entry scored (opened once) ----
    wt = n[te]; res = {}
    def per_entry(p): return wbce(p[te], y5[te]) * wt  # summed BCE over the entry's games
    for k, p in preds.items():
        res[k] = {'bce': float(per_entry(p).sum() / wt.sum()), 'auc_entries': float(F.auc(p[te], (y5[te] >= 0.5).astype(float)))}
    def diff(a, b):
        d = (per_entry(preds[a]) - per_entry(preds[b])) / wt.mean()
        return {'mean': float(d.mean()), 'ci': F.boot(seed[te], d)}
    res['picked_5_minus_CTM_recal'] = diff('picked_5', 'CTM_recal')
    res['picked_5_minus_picked_1'] = diff('picked_5', 'picked_1')
    res['gate'] = {'PASS': res['picked_5_minus_CTM_recal']['ci'][1] < 0}
    json.dump({'info': info, 'test': res}, open(os.path.join(out, 'result.json'), 'w'), indent=1)
    print(json.dumps({'info': info, 'test': res}, indent=1))


if __name__ == '__main__':
    main(*sys.argv[1:4])
