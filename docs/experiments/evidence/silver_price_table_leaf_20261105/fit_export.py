#!/usr/bin/env python3
"""Refit §746's model A (all-feature Heart-entry GBM) on all §731 + §745 labels and export it for the native Silver
price-table leaf (STS_SILVER_PRICE_TABLE_LEAF, research, default off).
usage: fit_export.py [--parity-only] LABELS_ALL.csv VARIANTS_ALL_DIR OUT_DIR
LABELS_ALL.csv = ../heart_entry_perturb2_20261101/results/labels_all.csv (4,252 valid bases, both rounds).
VARIANTS_ALL_DIR = v0..v15.jsonl for N = 4,253 (line = global base): §731's variants.tar (lines 0-999) followed by
round 2's variants.tar (lines 1000-4252), as fit_all.py reads them.
Recipe: fit_all.py's model A at 100% of the data, code imported unchanged from §732's fit_value.py (Feat, gbm: grid
depth {2,3,4,6} x min child weight {5,20} by 4-fold CV grouped by source seed, then refit on all rows). There is no
outer fold here: the deployed model is trained on every labelled fight.
Writes OUT_DIR/model_a.ubj (XGBoost), model_a.trees (CompactTreeNet text; feature tokens f<i> index vocab.json),
model_a.vocab.json (feature names in column order, monotone constraints, provenance), model_a.parity.jsonl
(stored states with Python's feature row and margin, for the C++ parity test). --parity-only rewrites only the
parity file from a saved model_a.ubj."""
import sys, os, json, csv, hashlib, re
import numpy as np
import xgboost as xgb
import sklearn
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'heart_entry_value_20261101'))
import fit_value as V  # noqa
K = 16

def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()

def export_trees(booster, nfeat, path):
    """CompactTreeNet text, logistic: x < thr -> yes; nodes breadth-first so the last node is a leaf."""
    cfg = json.loads(booster.save_config())
    base_score = float(cfg['learner']['learner_model_param']['base_score'])
    dumps = booster.get_dump(dump_format='json')
    used = sorted({int(n[1:]) for d in dumps for n in re.findall(r'"split": "(f\d+)"', d)})
    pos = {f'f{i}': j for j, i in enumerate(used)}
    lines = [f'nfeat {len(used)}'] + [f'feat f{i}' for i in used] + ['logistic 1', f'base_score {base_score!r}',
                                                                      f'ntrees {len(dumps)}']
    for t, d in enumerate(dumps):
        tree = json.loads(d); order, queue = [], [tree]
        while queue:
            node = queue.pop(0); order.append(node); queue += node.get('children', [])
        index = {n['nodeid']: i for i, n in enumerate(order)}
        lines.append(f'tree {t} {len(order)}')
        for n in order:
            if 'leaf' in n: lines.append(f'L {n["leaf"]!r}')
            else:
                if n['missing'] != n['yes'] and n['missing'] != n['no']: raise ValueError('unexpected missing branch')
                lines.append(f'S {pos[n["split"]]} {float(n["split_condition"])!r} {index[n["yes"]]} {index[n["no"]]}')
    open(path, 'w').write('\n'.join(lines) + '\n')
    return base_score, len(dumps), len(used)

def write_parity(booster, S, X, path):
    """C++ parity rows: 256 stored states (seed 20261105) plus the control state of the first 32 bases, with
    Python's feature row (sparse: column index -> value) and margin."""
    rng = np.random.default_rng(20261105)
    pick = sorted(set(rng.choice(len(S), 256, replace=False).tolist()) | set(range(0, 32 * K, K)))
    margin = booster.predict(xgb.DMatrix(X[pick]), output_margin=True)
    with open(path, 'w') as f:
        for i, m in zip(pick, margin):
            x = {str(j): float(v) for j, v in enumerate(X[i]) if v != 0}
            f.write(json.dumps({'state': S[i], 'x': x, 'margin': float(m)}) + '\n')

def parity_only(labels, vdir, out):
    """Rewrite model_a.parity.jsonl from the saved model_a.ubj (same rows and features as the fit)."""
    rows = sorted(csv.DictReader(open(labels)), key=lambda r: (int(r['base']), int(r['variant'])))
    st = [[json.loads(l) for l in open(os.path.join(vdir, f'v{k}.jsonl'))] for k in range(K)]
    S = [st[int(r['variant'])][int(r['base'])] for r in rows]
    F = V.Feat(S); X = np.stack([F.row(s) for s in S])
    names = json.load(open(os.path.join(out, 'model_a.vocab.json')))['names']
    assert names == F.names, 'vocabulary differs from the fit'
    A = xgb.Booster(); A.load_model(os.path.join(out, 'model_a.ubj'))
    write_parity(A, S, X, os.path.join(out, 'model_a.parity.jsonl'))

def main(labels, vdir, out):
    rows = sorted(csv.DictReader(open(labels)), key=lambda r: (int(r['base']), int(r['variant'])))
    st = [[json.loads(l) for l in open(os.path.join(vdir, f'v{k}.jsonl'))] for k in range(K)]
    nb = len(rows) // K; assert len(rows) == nb * K
    S = [st[int(r['variant'])][int(r['base'])] for r in rows]
    F = V.Feat(S); X = np.stack([F.row(s) for s in S]); mono = F.mono(range(X.shape[1]))
    y = np.array([float(r['won']) for r in rows]); g = np.array([int(r['source_seed']) for r in rows])
    info = []
    A = V.gbm(X, y, g, mono, info)
    os.makedirs(out, exist_ok=True)
    A.save_model(os.path.join(out, 'model_a.ubj'))
    base_score, ntrees, nused = export_trees(A, X.shape[1], os.path.join(out, 'model_a.trees'))
    p = A.predict(xgb.DMatrix(X))
    meta = {'model': '§746 model A (all-feature Heart-entry GBM), refit on all labels',
            'names': F.names, 'monotone': mono, 'counters': sorted(V.COUNTERS),
            'hyper': info[0], 'n_rows': int(len(y)), 'n_bases': nb, 'n_source_seeds': int(len(np.unique(g))),
            'base_score': base_score, 'ntrees': ntrees, 'n_split_features': nused,
            'train_mean_y': float(y.mean()), 'train_mean_p': float(p.mean()), 'train_bce': float(V.bce(p, y).mean()),
            'labels': {'path': os.path.basename(labels), 'sha256': sha(labels)},
            'variants_sha256': {f'v{k}.jsonl': sha(os.path.join(vdir, f'v{k}.jsonl')) for k in range(K)},
            'versions': {'xgboost': xgb.__version__, 'sklearn': sklearn.__version__, 'numpy': np.__version__}}
    meta['trees_sha256'] = sha(os.path.join(out, 'model_a.trees'))
    json.dump(meta, open(os.path.join(out, 'model_a.vocab.json'), 'w'), indent=1)
    write_parity(A, S, X, os.path.join(out, 'model_a.parity.jsonl'))
    print(json.dumps({k: v for k, v in meta.items() if k not in ('names', 'monotone', 'variants_sha256')}, indent=1))

if __name__ == '__main__':
    if sys.argv[1] == '--parity-only': parity_only(*sys.argv[2:5])
    else: main(*sys.argv[1:4])
