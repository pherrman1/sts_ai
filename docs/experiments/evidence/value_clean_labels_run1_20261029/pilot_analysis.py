#!/usr/bin/env python3
"""Stage-3 pilot checks (README "Analysis"). Descriptive, no gate; test-run once on the 32 pilot games + 60 other units
before this commit; the test changed nothing in the definitions).
usage: pilot_analysis.py UNITS_DIR OUT.json     UNITS_DIR = verify_campaign.py --extract output (out/units/<id>/...)

Provisional V_{k+1} (only for this check, not a deliverable): a GBM on the first state of act k+1 of every non-pilot
base game (act 4: base + forks), label = the real Heart kill, s0 features without screen/selector/offer blocks.
Per act k (roots in act k, top-3 actions, 64 act-end rollouts each, shared streams across siblings):
  label value of a rollout = 0 after a death, V_{k+1}(end record) otherwise; act 4 = the rollout's own terminal result.
  - ratio = mean within-(root, action) variance / mean p(1-p)      (stage 0's definition)
  - sib   = mean variance of paired sibling differences / mean (p_a(1-p_a) + p_b(1-p_b))
  - se    = median standard error of a 64-rollout label
  - death level: rollout death share in act k from the act's first searched root vs the real death share in act k
  - coverage (act 3): act-4 entry records reached by rollouts vs real act-4 entries (HP fraction, provisional V_A4)."""
import sys, os, json, gzip, glob, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'outcome_divergence_pairs_20261025'))
import s0  # noqa: E402
DROP = set()
for b in ('screen', 'select', 'offered'):
    o, n = s0.OFF[b]; DROP.update(range(o, o + n))
PILOT = set(range(111387000, 111387032))


def rows(p):
    with gzip.open(p, 'rt') as f:
        return [json.loads(l) for l in f if l.strip()]


def feat(record, act, floor):
    cols, vals = s0.features({'record': record, 'act': act, 'floor': floor})
    x = np.zeros(s0.N_FEAT + 1, np.float32)
    for c, v in zip(cols, vals):
        if c not in DROP: x[c] = v
    fo = record['obs.fixed_observation']; x[-1] = fo[0] / max(fo[1], 1)
    return x


def main(units, out):
    import xgboost as xgb
    entries = {k: ([], [], []) for k in (2, 3, 4)}   # X, y, seed
    real_death = collections.Counter(); real_reach = collections.Counter()
    for d in sorted(glob.glob(os.path.join(units, '*'))):
        if not os.path.isdir(d): continue
        for g in sorted(glob.glob(os.path.join(d, '*.jsonl.gz'))):
            b = os.path.basename(g)
            if b.endswith('.ctm.jsonl.gz') or b.endswith('.price.jsonl.gz'): continue
            rs = rows(g); o = [r for r in rs if r.get('type') == 'outcome'][-1]
            seed = [r for r in rs if r.get('type') == 'header'][0]['seed']
            first = {}
            for r in rs:
                if r.get('type') == 'state' and r['act'] not in first: first[r['act']] = r
            if b.startswith('base-'):
                for k in first: real_reach[k] += 1
                if not o['heartKilled'] and o['finalHp'] <= 0: real_death[o['finalAct']] += 1
            if seed in PILOT: continue
            for k in (2, 3, 4):
                if k in first and (k == 4 or b.startswith('base-')):
                    e = first[k]; X, y, s = entries[k]
                    X.append(feat(e['record'], e['act'], e['floor'])); y.append(float(o['heartKilled'])); s.append(seed)
    V = {}
    info = {'provisional_V': {}}
    for k, (X, y, s) in entries.items():
        X, y = np.array(X), np.array(y)
        prm = {'objective': 'binary:logistic', 'eval_metric': 'logloss', 'tree_method': 'hist', 'eta': 0.05, 'subsample': 0.8,
               'colsample_bytree': 0.5, 'lambda': 5, 'max_depth': 3, 'min_child_weight': 10, 'seed': 29, 'nthread': 4}
        V[k] = xgb.train(prm, xgb.DMatrix(X, label=y), 300)
        info['provisional_V'][k] = {'n': int(len(y)), 'kill_rate': float(y.mean())}
    vcache = {}

    def value(rec, k):
        key = json.dumps(rec, sort_keys=True)
        if key not in vcache:
            vcache[key] = float(V[k].predict(xgb.DMatrix(feat(rec, k, rec['obs.fixed_observation'][3])[None]))[0])
        return vcache[key]
    agg = collections.defaultdict(lambda: collections.defaultdict(list))
    cov_roll, cov_real = [], []
    roll_death = collections.defaultdict(list)
    complete = {'games': 0, 'rows': 0, 'errors': 0, 'rows_by_act': collections.Counter(), 'missing_record': 0}
    for p in sorted(glob.glob(os.path.join(units, '*', 'base-*.price.jsonl.gz'))):
        complete['games'] += 1; seen_act = set()
        for r in rows(p):
            complete['rows'] += 1; complete['rows_by_act'][r['act']] += 1
            pr = r['price']
            if 'error' in pr or 'priceError' in r: complete['errors'] += 1; continue
            k = r['act']; per_action = []
            for a in pr['actions']:
                vals, dead = [], []
                for e in a['actEnd']:
                    if 'error' in e: continue
                    if k == 4:
                        vals.append(float(e['value'])); dead.append(e['value'] == 0); continue
                    rec = e.get('endRecord')
                    if rec is None:
                        dead.append(True); vals.append(0.0)
                    else:
                        if rec['obs.act'] != k + 1: complete['missing_record'] += 1
                        dead.append(False); vals.append(value(rec, k + 1))
                        if k == 3: cov_roll.append((rec['obs.fixed_observation'][0] / max(rec['obs.fixed_observation'][1], 1), vals[-1]))
                per_action.append(np.array(vals))
                if k not in seen_act and a is pr['actions'][0]: roll_death[k].append(float(np.mean(dead)))
            seen_act.add(k)
            for v in per_action:
                pbar = v.mean()
                if 0 < pbar < 1:
                    for g in ('all', f'act{k}'):
                        agg[g]['v'].append(v.var()); agg[g]['b'].append(pbar * (1 - pbar)); agg[g]['se'].append(v.std(ddof=1) / np.sqrt(len(v)))
            if len(per_action) >= 2 and len(per_action[0]) == len(per_action[1]):
                a, b = per_action[0], per_action[1]
                for g in ('all', f'act{k}'):
                    agg[g]['dv'].append((a - b).var()); agg[g]['db'].append(a.mean() * (1 - a.mean()) + b.mean() * (1 - b.mean()))
    X4, _, s4 = entries[4]
    for x in X4: cov_real.append(x[-1])
    res = {'info': info, 'completeness': {**complete, 'rows_by_act': dict(complete['rows_by_act'])}, 'acts': {}}
    for g, d in sorted(agg.items()):
        res['acts'][g] = {'n': len(d['v']), 'ratio': float(np.mean(d['v']) / np.mean(d['b'])),
                          'sib': float(np.mean(d['dv']) / np.mean(d['db'])) if d['dv'] else None,
                          'se_median': float(np.median(d['se']))}
    res['death_level'] = {f'act{k}': {'rollout_from_first_root': float(np.mean(roll_death[k])) if roll_death[k] else None,
                                       'real_base_games': real_death[k] / real_reach[k] if real_reach[k] else None,
                                       'n_real': real_reach[k]} for k in (1, 2, 3, 4)}
    hp_roll = np.array([h for h, _ in cov_roll]); v_roll = np.array([v for _, v in cov_roll]); hp_real = np.array(cov_real)
    q = [0.05, 0.25, 0.5, 0.75, 0.95]
    res['coverage_act4_entry'] = {'rollout_n': int(len(hp_roll)), 'real_n': int(len(hp_real)),
                                  'hp_frac_rollout_q': np.quantile(hp_roll, q).tolist() if len(hp_roll) else None,
                                  'hp_frac_real_q': np.quantile(hp_real, q).tolist(),
                                  'V_A4_rollout_mean': float(v_roll.mean()) if len(v_roll) else None}
    json.dump(res, open(out, 'w'), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
