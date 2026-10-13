#!/usr/bin/env python3
"""§444 offline qualification of the X2-B public (P0) margin-average export.

    python3 docs/experiments/evidence/vwin_x2b_public_444_20261012/x2b_public_444.py prepare OUTDIR
    one_combat winnettest models/candidates/v_win_x2b_public_trees.txt OUTDIR/parity.csv 100000 > OUTDIR/native.txt
    python3 docs/experiments/evidence/vwin_x2b_public_444_20261012/x2b_public_444.py report OUTDIR

VALIDATION only (sealed #334 VALIDATION rich cache, 141,566 MAP rows, 155
sources). TEST is never opened. No game seeds are driven.
"""
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.analysis.vwin_tree_utils import load_trees, predict_rows  # noqa: E402
from tools.vwin_refresh_evaluation import clustered_delta, predictive_metrics  # noqa: E402

A = Path('/home/philippherrmann/Documents/sts/artifacts/vwin-refresh-334')
E1 = A / 'e1-focal-20261007-36b5b14f'
X2 = A / 'a3-final1024-x2b-finalist-20261003-49c28d80/tune/X2'
CACHE = A / 'a4-mlp-structured-screen-20261003'
INDEX = A / 'a2a-scale-1024-extra512-8175c9dc-20261002/corpus-mixed-1024.json'
MODEL = ROOT / 'models/candidates/v_win_x2b_public_trees.txt'
EXPECTED = {
    E1 / 'P0-s0/model.ubj': 'ed8d95dcb93469cd4383d072c29ab5c21d268193f70e0348ab2f2a7c8f1d9de5',
    E1 / 'P0-s1/model.ubj': '227a110ea579657f9f843f0f7197977c7ad25863efb5c9b6491024b1acc13410',
    E1 / 'P0-s2/model.ubj': 'e74b7740065742caf06c50abf0dff4dfe8080de78a70d57eb73c66f1f7e35e9c',
    E1 / 'validation-predictions.npz': '8a1ec54fbf5a14db48d25f9eee5bfa31035732eb73052b592517658b7d1d5633',
    X2 / 'model.ubj': '99dbac6b5b082c46fe07242d2d15d8ccc6818041cb851efa79d6b423cdcb52dd',
    INDEX: 'ae56f9633ce8da8a72e341978d707c9f145c1f1b6479afa438067af5570dfa00',
    CACHE / 'cache-seal.json': '7b4ed6e19615b1d7746297be31c649ed2189c443f56d02a316c91f34ba26a019',
}
HIDDEN = ('nextEliteId', 'nextFight0', 'nextFight1', 'nextFight2')
REPS = 2000


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 23), b''):
            h.update(b)
    return h.hexdigest()


def load():
    for path, digest in EXPECTED.items():
        assert sha(path) == digest, path
    seal = json.loads((CACHE / 'cache-seal.json').read_text())
    for name in ('val-rich-X.npy', 'val-source.npy', 'val-y.npy', 'rich-feature-names.json', 'val-metadata.jsonl'):
        assert sha(CACHE / name) == seal['files'][name], name
    assert seal['index_sha256'] == EXPECTED[INDEX]
    x = np.load(CACHE / 'val-rich-X.npy', mmap_mode='r')
    s, y = np.load(CACHE / 'val-source.npy'), np.load(CACHE / 'val-y.npy')
    names = json.loads((CACHE / 'rich-feature-names.json').read_text())
    meta = [json.loads(line) for line in (CACHE / 'val-metadata.jsonl').open()]
    z = np.load(E1 / 'validation-predictions.npz')
    assert len(y) == 141566 and len(set(s)) == 155
    assert (s == z['seed']).all() and (y == z['y']).all()
    assert [m['rowIdx'] for m in meta] == z['row'].tolist()
    assert [m['branchId'] for m in meta] == z['branch'].tolist()
    for seed in set(s.tolist()):
        v = int(hashlib.sha256(f'vwin-refresh-334-v1:{seed}'.encode()).hexdigest()[:8], 16) / 2**32
        assert .70 <= v < .85, seed  # VALIDATION only
    return x, s, y, names, meta, z


def boosters():
    import xgboost as xgb
    out = []
    for k in range(3):
        b = xgb.Booster()
        b.load_model(str(E1 / f'P0-s{k}/model.ubj'))
        b.set_param({'nthread': 2})
        out.append(b)
    assert all(b.feature_names == out[0].feature_names for b in out)
    assert not set(out[0].feature_names) & set(HIDDEN) and len(out[0].feature_names) == 457
    return out


def file_predict(x, names):
    feats, trees, logistic, _, base_margin = load_trees(MODEL)
    cols = [names.index(n) for n in feats]
    out = np.empty(len(x))
    for a in range(0, len(x), 20000):
        out[a:a + 20000] = predict_rows(np.asarray(x[a:a + 20000])[:, cols], trees, logistic, base_margin)
    return out, feats, len(trees)


def prepare(outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    x, s, _, names, meta, _ = load()
    # Same deterministic selection as §379 (x2b_validation.py): 7 evenly spaced
    # rows per source, round-robin to 1,024, plus nine full HP sweeps.
    groups = [np.flatnonzero(s == seed) for seed in sorted(set(s))]
    choices = [g[np.linspace(0, len(g) - 1, 7, dtype=int)] for g in groups]
    idx = np.array([int(g[k]) for k in range(7) for g in choices][:1024])
    rows = np.array(x[idx])
    sweep, hp, mh = [], names.index('curHp'), names.index('maxHp')
    for act in (1, 2, 3):
        seen = set()
        for i in idx:
            if int(meta[i]['act']) != act or int(s[i]) in seen:
                continue
            seen.add(int(s[i]))
            for h in range(1, int(x[i, mh]) + 1):
                row = np.array(x[i])
                row[hp] = h
                sweep.append(row)
            if len(seen) == 3:
                break
    allrows = np.concatenate([rows, np.array(sweep)])
    with (outdir / 'parity.csv').open('w') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['chosen', *names, 'won'])
        w.writerows([1, *r, 0] for r in allrows)
    import xgboost as xgb
    bs = boosters()
    dm = xgb.DMatrix(allrows[:, [names.index(n) for n in bs[0].feature_names]], feature_names=bs[0].feature_names)
    margin = np.mean([b.predict(dm, output_margin=True) for b in bs], axis=0)
    file_pred, _, _ = file_predict(allrows, names)
    np.save(outdir / 'python-xgb-margin-mean.npy', 1 / (1 + np.exp(-margin.astype(np.float64))))
    np.save(outdir / 'python-tree-file.npy', file_pred)
    inputs = dict(map_rows=len(idx), hp_sweep_rows=len(sweep), source_count=len(set(s[idx].tolist())),
                  acts=sorted({int(meta[i]['act']) for i in idx}), indices=idx.tolist(),
                  csv_sha256=sha(outdir / 'parity.csv'), TEST_accessed=False)
    (outdir / 'parity-inputs.json').write_text(json.dumps(inputs, indent=1) + '\n')
    print({k: v for k, v in inputs.items() if k != 'indices'})


def report(outdir):
    x, s, y, names, _, z = load()
    model_sha = sha(MODEL)
    text = MODEL.read_text()
    hidden_lines = sum(1 for line in text.splitlines() if re.search('nextEliteId|nextFight', line))
    # Native parity.
    native_out = (outdir / 'native.txt').read_text()
    native = np.array([float(v) for _, v in re.findall(r'^(\d+),([0-9.eE+-]+)$', native_out, re.M)])
    py_file = np.load(outdir / 'python-tree-file.npy')
    py_xgb = np.load(outdir / 'python-xgb-margin-mean.npy')
    assert len(native) == len(py_file) == len(py_xgb)
    d = np.abs(native - py_xgb)
    parity = dict(rows=len(native), map_rows=1024, hp_sweep_rows=len(native) - 1024,
                  native_vs_xgb_margin_mean=dict(max=float(d.max()), mean=float(d.mean()),
                                                 p99=float(np.quantile(d, .99)), worst_row=int(d.argmax()),
                                                 python=float(py_xgb[d.argmax()]), native=float(native[d.argmax()])),
                  native_vs_python_tree_file_max=float(np.abs(native - py_file).max()),
                  python_tree_file_vs_xgb_max=float(np.abs(py_file - py_xgb).max()),
                  gate=1e-5, passed=bool(d.max() < 1e-5))
    # Full VALIDATION metrics.
    export, feats, ntrees = file_predict(x, names)
    import xgboost as xgb
    bs = boosters()
    cols = [names.index(n) for n in bs[0].feature_names]
    margins, probs = [], []
    for k, b in enumerate(bs):
        m = np.concatenate([b.predict(xgb.DMatrix(np.asarray(x[a:a + 20000])[:, cols], feature_names=bs[0].feature_names),
                                      output_margin=True) for a in range(0, len(x), 20000)]).astype(np.float64)
        margins.append(m)
        probs.append(1 / (1 + np.exp(-m)))
    xgb_margin_mean = 1 / (1 + np.exp(-np.mean(margins, axis=0)))
    prob_mean = np.mean(probs, axis=0)
    x2b = z['X2B'].astype(np.float64)
    p0_npz = z['P0'].astype(np.float64)
    checks = dict(export_vs_xgb_margin_mean_max=float(np.abs(export - xgb_margin_mean).max()),
                  prob_mean_recomputed_vs_e1_npz_P0_max=float(np.abs(prob_mean - p0_npz).max()),
                  export_vs_prob_mean_max=float(np.abs(export - prob_mean).max()),
                  export_vs_prob_mean_mean=float(np.abs(export - prob_mean).mean()))
    strip = lambda m: {k: m[k] for k in ('n', 'nll', 'brier', 'roc_auc', 'ece')}
    arms = {'export_margin_mean': export, 'P0_prob_mean_e1': p0_npz, 'X2B_frozen': x2b}
    metrics = {k: strip(predictive_metrics(y, p)) for k, p in arms.items()}
    deltas = {}
    for k in ('export_margin_mean', 'P0_prob_mean_e1'):
        r = clustered_delta(y, x2b, arms[k], s, REPS)
        deltas[f'{k}_minus_X2B'] = {m: r[m] for m in ('nll', 'brier')}
    r = clustered_delta(y, p0_npz, export, s, REPS)
    deltas['export_margin_mean_minus_P0_prob_mean'] = {m: r[m] for m in ('nll', 'brier')}
    out = dict(schema='vwin_x2b_public_444_v1', model=str(MODEL.relative_to(ROOT)), model_sha256=model_sha,
               tree_count=ntrees, used_features=len(feats), public_features=457,
               hidden_future_lines_in_file=hidden_lines,
               inputs={str(p): h for p, h in EXPECTED.items()}, validation_rows=int(len(y)),
               validation_sources=int(len(set(s.tolist()))), bootstrap=dict(reps=REPS, seed=0, cluster='sourceSeed'),
               TEST_accessed=False, game_seeds_driven=0, parity=parity, consistency=checks,
               metrics=metrics, paired_deltas=deltas)
    (outdir / 'report.json').write_text(json.dumps(out, indent=1, default=float) + '\n')
    print(json.dumps(out, indent=1, default=float))


if __name__ == '__main__':
    {'prepare': prepare, 'report': report}[sys.argv[1]](Path(sys.argv[2]))
