"""#401 Stage 2: grouped retrain ablations on A20 plain runs (TRAIN fit, ES early stop, VAL report).
TEST seeds are never loaded into any fit or metric."""
import sys, json, time, numpy as np, xgboost as xgb
sys.path.insert(0, '/tmp/claude-0/a401/work')
from groups import group_of

target = sys.argv[1]  # floor | won
arms_sel = sys.argv[2].split(',') if len(sys.argv) > 2 else None
Z = np.load('/tmp/claude-0/a401/work/a20.npz')
names = list(Z['names']); sp = Z['splits']; seeds = Z['seeds']
b0 = [l.strip() for l in open('/tmp/claude-0/a401/work/feats_b0.txt')]
fm = [n for n in names if group_of(n) == 'forward_map']
X = Z['X']; y = Z[target]
tr, es, va = sp == 'TRAIN', sp == 'ES', sp == 'VAL'
groups = sorted({group_of(n) for n in b0})
hidden = {'future_encounters(hidden)', 'queue_counters', 'rng_counters(hidden)'}
arms = {'FULL': b0, '+forward_map': b0 + fm,
        'PUBLIC(-hidden)': [n for n in b0 if group_of(n) not in hidden],
        'PUBLIC+forward_map': [n for n in b0 if group_of(n) not in hidden] + fm}
for g in groups:
    arms['-' + g] = [n for n in b0 if group_of(n) != g]
arms['FULL#2'] = b0
arms['FULL#3'] = b0
arms['FULL#4'] = b0
arms['PUBLIC(-hidden future, -RNG; keep queue)'] = [n for n in b0 if group_of(n) not in ('future_encounters(hidden)', 'rng_counters(hidden)')]
# derived-feature test: cyclic in-combat relic counters reduced to presence
CYCLIC = ['r26', 'r30', 'r31', 'r44', 'r52', 'r68', 'r171']  # Happy Flower, Incense Burner, Ink Bottle, Nunchaku, Pen Nib, Sundial, Tiny Chest
arms['cyclic_relics->presence'] = b0
if arms_sel:
    arms = {k: v for k, v in arms.items() if k in arms_sel}
P = dict(eta=0.1, max_depth=6, subsample=0.8, colsample_bytree=0.5, min_child_weight=20,
         tree_method='hist', max_bin=256, nthread=4, seed=401)
if target == 'won':
    P.update(objective='binary:logistic', eval_metric='logloss')
else:
    P.update(objective='reg:squarederror', eval_metric='rmse')
out_path = f'/tmp/claude-0/a401/work/abl_{target}.jsonl'
done = set()
try:
    done = {json.loads(l)['arm'] for l in open(out_path)}
except FileNotFoundError:
    pass
for arm, fl in arms.items():
    if arm in done:
        continue
    idx = [names.index(n) for n in fl]
    t = time.time()
    Xa = X
    if arm == 'cyclic_relics->presence':
        Xa = X.copy()
        for c in CYCLIC:
            Xa[:, names.index(c)] = np.minimum(Xa[:, names.index(c)], 1)
    dtr = xgb.QuantileDMatrix(Xa[tr][:, idx], label=y[tr], max_bin=256)
    des = xgb.DMatrix(Xa[es][:, idx], label=y[es]); dva = xgb.DMatrix(Xa[va][:, idx])
    del Xa
    P['seed'] = 400 + int(arm[-1]) if arm[:-1].endswith('#') else 401
    b = xgb.train(P, dtr, num_boost_round=3000, evals=[(des, 'es')], early_stopping_rounds=50, verbose_eval=False)
    p = b.predict(dva, iteration_range=(0, b.best_iteration + 1))
    np.save(f'/tmp/claude-0/a401/work/pred_{target}_{arm}.npy', p.astype(np.float32))
    rec = dict(arm=arm, n_feats=len(fl), trees=b.best_iteration + 1, secs=round(time.time() - t, 1))
    with open(out_path, 'a') as f:
        f.write(json.dumps(rec) + '\n')
    print(rec, flush=True)
