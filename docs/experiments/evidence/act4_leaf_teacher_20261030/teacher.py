#!/usr/bin/env python3
"""V_A4 teacher check: end-state prices at Act-4 entry (exploratory, offline).
usage: teacher.py STAGE2_A4.pkl RUN1_A4.pkl OUT_DIR
Refits run 1's G_5 and GC_5 (fit_a4_run1.py, same data, params and selection; models saved), then scores every run-1
base Act-4 entry as is and perturbed: HP -1/-3/-6/-12, max HP +5 (HP fixed), gold +-50, each held potion removed,
one empty slot filled with each potion type. The CTM S&S input of GC is perturbed the same way."""
import sys, os, json, copy, collections
import numpy as np
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
sys.path.insert(0, os.path.join(REPO, 'docs/experiments/evidence/value_clean_labels_run1_20261029'))
import fit_a4_run1 as R  # noqa
F, s0 = R.F, R.s0
import xgboost as xgb

MONO = None
def fit_b(X, y, w, tr, va):
    best = None
    for depth in (2, 3, 4):
        for mcw in (5, 20):
            prm = {'objective': 'binary:logistic', 'eval_metric': 'logloss', 'tree_method': 'hist', 'eta': 0.03, 'subsample': 0.8,
                   'colsample_bytree': 0.5, 'lambda': 5, 'max_depth': depth, 'min_child_weight': mcw, 'seed': 29, 'nthread': 4}
            if MONO is not None:
                mc = [0] * X.shape[1]
                for j, v in MONO.items():
                    if j < X.shape[1]: mc[j] = v
                prm['monotone_constraints'] = '(' + ','.join(map(str, mc)) + ')'
            b = xgb.train(prm, xgb.DMatrix(X[tr], label=y[tr], weight=w[tr]), 3000,
                          evals=[(xgb.DMatrix(X[va], label=y[va], weight=w[va]), 'v')], early_stopping_rounds=100, verbose_eval=False)
            p = b.predict(xgb.DMatrix(X[va]), iteration_range=(0, b.best_iteration + 1))
            v = float((R.wbce(p, y[va]) * w[va]).sum() / w[va].sum())
            if best is None or v < best[0]: best = (v, depth, mcw, b)
    return best

def main(p2, p1, out):
    os.makedirs(out, exist_ok=True)
    es, _ = R.entries(R.pickle.load(open(p2, 'rb')), R.pickle.load(open(p1, 'rb')))
    model = F.load_trees(os.path.join(REPO, 'models/candidates/ctm_act4_survival_trees.txt'))
    X, c = R.design(es, model)
    n = np.array([len(e['kills']) for e in es], float); y = np.array([np.mean(e['kills']) for e in es])
    seed = np.array([e['seed'] for e in es]); split = np.array([s0.split_of(int(s)) for s in seed])
    tr, va = split == 'train', split == 'validation'
    fill = np.nanmean(c[tr])
    def lc_of(cv):
        cv = np.where(np.isnan(cv), fill, cv); cv = np.clip(cv, 1e-4, 1 - 1e-4); return np.log(cv / (1 - cv))
    gB = fit_b(X, y, n, tr, va); gcB = fit_b(np.hstack([X, lc_of(c)[:, None]]), y, n, tr, va)
    info = {'G': {'val_bce': gB[0], 'depth': gB[1], 'mcw': gB[2], 'iters': int(gB[3].best_iteration)},
            'GC': {'val_bce': gcB[0], 'depth': gcB[1], 'mcw': gcB[2], 'iters': int(gcB[3].best_iteration)}}
    te = (split == 'test') & np.array([e['src'] == 'run1' for e in es])
    for nm, B, XX in (('G', gB[3], X), ('GC', gcB[3], np.hstack([X, lc_of(c)[:, None]]))):
        p = B.predict(xgb.DMatrix(XX[te]), iteration_range=(0, B.best_iteration + 1))
        info[nm]['test_bce'] = float((R.wbce(p, y[te]) * n[te]).sum() / n[te].sum())
    gB[3].save_model(os.path.join(out, 'G_5.ubj')); gcB[3].save_model(os.path.join(out, 'GC_5.ubj'))
    def score(elist):
        Xe, ce = R.design(elist, model)
        g = gB[3].predict(xgb.DMatrix(Xe), iteration_range=(0, gB[3].best_iteration + 1))
        gc = gcB[3].predict(xgb.DMatrix(np.hstack([Xe, lc_of(ce)[:, None]])), iteration_range=(0, gcB[3].best_iteration + 1))
        return {'G': g, 'GC': gc}
    base = [e for e in es if e['src'] == 'run1']
    def pert(e, hp=0, mhp=0, gold=0, drop=None, add=None):
        e = copy.deepcopy(e); r = e['entry']['record']; fo = r['obs.fixed_observation']
        fo[1] = fo[1] + mhp; fo[0] = max(1, min(fo[0] + hp, fo[1])); fo[2] = max(0, fo[2] + gold)
        dropid = None
        if drop is not None: dropid = r['obs.potions'][drop]; r['obs.potions'][drop] = 1
        if add is not None: r['obs.potions'][r['obs.potions'].index(1)] = add
        for q in e['ctm']:
            p = q['predictorInput']; g = p['globals']
            # the CTM row is the S&S fight start (later than the entry): apply the same deltas, not the entry values
            g['maxHp'] = g['maxHp'] + mhp; g['curHp'] = max(1, min(g['curHp'] + hp, g['maxHp'])); g['gold'] = max(0, g['gold'] + gold)
            if drop is not None:
                for x in p['potions']:
                    if x['potionId'] == dropid and x['slot'] < g['potionCapacity']:
                        x['potionId'] = 1; g['potionCount'] -= 1; break
            if add is not None:
                for x in sorted(p['potions'], key=lambda x: x['slot']):
                    if x['potionId'] == 1 and x['slot'] < g['potionCapacity']:
                        x['potionId'] = add; g['potionCount'] += 1; break
        return e
    # sanity: CTM potion list format
    q0 = [q for q in base[0]['ctm'] if q['roomClass'] == 'ELITE']
    info['ctm_potions_example'] = q0[0]['predictorInput']['potions'] if q0 else None
    v0 = score([pert(e) for e in base]); vraw = score(base)
    info['identity_max_abs'] = {k: float(np.abs(v0[k] - vraw[k]).max()) for k in v0}
    res = {'n_entries': len(base)}
    hp = {d: score([pert(e, hp=-d) for e in base]) for d in (1, 3, 6, 12)}
    res_hp = {}
    for k in ('G', 'GC'):
        slope = (v0[k] - hp[12][k]) / 12.0
        res_hp[k] = {'slope_per_entry_hp_median': float(np.median(slope)), 'slope_p10_p90': [float(x) for x in np.percentile(slope, [10, 90])],
                     'sign_right': {d: float(np.mean(hp[d][k] < v0[k])) for d in (1, 3, 6, 12)},
                     'strictly_lower_or_equal': {d: float(np.mean(hp[d][k] <= v0[k])) for d in (1, 3, 6, 12)},
                     'monotone_0_3_6_12': float(np.mean((hp[3][k] <= v0[k]) & (hp[6][k] <= hp[3][k]) & (hp[12][k] <= hp[6][k])))}
        res_hp[k]['slope_pos_share'] = float(np.mean(slope > 0))
    res['hp'] = res_hp
    m5 = score([pert(e, mhp=5) for e in base]); gp = score([pert(e, gold=50) for e in base]); gm = score([pert(e, gold=-50) for e in base])
    pots = collections.defaultdict(lambda: {'G': [], 'GC': []}); padd = collections.defaultdict(lambda: {'G': [], 'GC': []})
    for k in ('G', 'GC'):
        slope = np.maximum((v0[k] - hp[12][k]) / 12.0, 1e-4)
        res.setdefault('maxhp5', {})[k] = {'median_hp_eq_per_point': float(np.median((m5[k] - v0[k]) / slope / 5)), 'pos_share': float(np.mean(m5[k] > v0[k])),
                                          'median_dV_pp': float(np.median(m5[k] - v0[k]) * 100)}
        res.setdefault('gold50', {})[k] = {'median_hp_eq_per_gold_plus': float(np.median((gp[k] - v0[k]) / slope / 50)),
                                          'median_hp_eq_per_gold_minus': float(np.median((v0[k] - gm[k]) / slope / 50))}
    # potion removal
    idx = [(i, s) for i, e in enumerate(base) for s, v in enumerate(e['entry']['record']['obs.potions']) if v > 1]
    dr = score([pert(base[i], drop=s) for i, s in idx])
    for j, (i, s) in enumerate(idx):
        pid = base[i]['entry']['record']['obs.potions'][s]
        for k in ('G', 'GC'):
            slope = max((v0[k][i] - hp[12][k][i]) / 12.0, 1e-4)
            pots[pid][k].append(((v0[k][i] - dr[k][j]) * 100, (v0[k][i] - dr[k][j]) / slope))
    # potion addition to an empty slot, each type seen
    types = sorted({v for e in base for v in e['entry']['record']['obs.potions'] if v > 1})
    emp = [i for i, e in enumerate(base) if 1 in e['entry']['record']['obs.potions']]
    for t in types:
        ad = score([pert(base[i], add=t) for i in emp])
        for k in ('G', 'GC'):
            slope = np.maximum((v0[k][emp] - hp[12][k][emp]) / 12.0, 1e-4)
            padd[t][k] = [float(np.median((ad[k] - v0[k][emp]) * 100)), float(np.median((ad[k] - v0[k][emp]) / slope)), float(np.mean(ad[k] > v0[k][emp]))]
    res['potion_drop'] = {str(t): {k: {'n': len(v[k]), 'median_dV_pp': float(np.median([a for a, b in v[k]])), 'median_hp_eq': float(np.median([b for a, b in v[k]]))}
                                   for k in v} for t, v in sorted(pots.items())}
    alld = {k: [b for v in pots.values() for a, b in v[k]] for k in ('G', 'GC')}
    alldv = {k: [a for v in pots.values() for a, b in v[k]] for k in ('G', 'GC')}
    res['potion_drop_all'] = {k: {'n': len(alld[k]), 'median_hp_eq': float(np.median(alld[k])), 'median_dV_pp': float(np.median(alldv[k])),
                                  'pos_share': float(np.mean(np.array(alldv[k]) > 0))} for k in alld}
    res['potion_add'] = {str(t): padd[t] for t in types}
    res['v0_mean'] = {k: float(v0[k].mean()) for k in v0}
    json.dump({'info': info, 'res': res}, open(os.path.join(out, 'teacher.json'), 'w'), indent=1)
    print(json.dumps({'info': info, 'res': {k: v for k, v in res.items() if k not in ('potion_drop', 'potion_add')}}, indent=1))

if __name__ == '__main__':
    if len(sys.argv) > 4 and sys.argv[4] == 'mono':
        o = s0.OFF
        MONO = {o['fixed'][0] + 0: 1, o['fixed'][0] + 1: 1}  # cur HP, max HP
        for i in range(2, o['potion'][1]): MONO[o['potion'][0] + i] = 1  # each held potion type
        MONO[s0.N_FEAT] = 1  # hp fraction
        MONO[s0.N_FEAT + 1] = 1  # GC: CTM S&S survival logit
    main(*sys.argv[1:4])
