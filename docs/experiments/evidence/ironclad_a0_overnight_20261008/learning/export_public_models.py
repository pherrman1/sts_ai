#!/usr/bin/env python3
"""Export fixed existing E1 seed-zero candidates; no training or TEST access."""
from pathlib import Path
import csv
import hashlib
import json
import sys

import numpy as np
import xgboost as xgb

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from export_win_model import export_booster
from tools.analysis.vwin_tree_utils import load_trees, predict_rows
from tools.vwin_refresh_contract import MAP_PREFIX
from tools.vwin_refresh_dataset import source_split

SOURCE = Path('/home/philippherrmann/Documents/sts/artifacts/vwin-refresh-334')
E1 = SOURCE / 'e1-focal-20261007-36b5b14f'
INDEX = SOURCE / 'a2a-scale-1024-extra512-8175c9dc-20261002/corpus-mixed-1024.json'
INDEX_SHA = 'ae56f9633ce8da8a72e341978d707c9f145c1f1b6479afa438067af5570dfa00'
HIDDEN = {'nextEliteId', 'nextFight0', 'nextFight1', 'nextFight2'}

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=False)
    assert sha(INDEX) == INDEX_SHA
    index = json.loads(INDEX.read_text())
    # Component metadata only until a TRAIN component is identified. TEST rows
    # are never opened, even for export equivalence checks.
    for item in index['components']:
        manifest = (INDEX.parent / item['manifest']).resolve()
        assert sha(manifest) == item['sha256']
        doc = json.loads(manifest.read_text())
        spec = doc['seedSpec']
        splits = {source_split(s) for s in range(spec['start'], spec['start'] + spec['count'])}
        assert len(splits) == 1
        if splits != {'TRAIN'}:
            continue
        table = Path(str(manifest).removesuffix('.manifest.json') + '.map.csv')
        assert sha(table) == doc['outputs']['map.csv']
        with table.open(newline='') as f:
            reader = csv.reader(f)
            header = next(reader)
            feature_names = doc['stateFeatures']['header'].split(',')
            offset = len(MAP_PREFIX)
            assert header[offset:offset + len(feature_names)] == feature_names
            rows = []
            for row in reader:
                rows.append([float(v) for v in row[offset:offset + len(feature_names)]])
                if len(rows) == 64:
                    break
        break
    else:
        raise RuntimeError('No TRAIN component found')
    full = np.asarray(rows, dtype=np.float32)
    receipt = {'schema': 'overnight_public_e1_exports_v1', 'test_rows_opened': False,
               'corpus_index': str(INDEX), 'corpus_index_sha256': INDEX_SHA,
               'fixture_manifest': str(manifest), 'fixture_manifest_sha256': sha(manifest),
               'fixture_table': str(table), 'fixture_table_sha256': sha(table),
               'fixture_rows': len(rows), 'fixture_split': 'TRAIN',
               'numpy': np.__version__, 'xgboost': xgb.__version__,
               'exports': [], 'inventory': []}
    for model in sorted(E1.glob('*/model.ubj')):
        booster = xgb.Booster(params={'nthread': 1})
        booster.load_model(model)
        meta = json.loads((model.parent / 'predictor.json').read_text())
        names = meta['feature_names']
        assert names == booster.feature_names and len(names) == 457
        assert not (set(names) & HIDDEN)
        X = full[:, [feature_names.index(n) for n in names]]
        predictions = booster.inplace_predict(X)
        assert np.isfinite(predictions).all()
        record = {'arm': model.parent.name, 'path': str(model), 'sha256': sha(model),
                  'predictor_sha256': sha(model.parent / 'predictor.json'),
                  'features': len(names), 'trees': len(booster.get_dump()),
                  'load_and_predict': 'PASS'}
        receipt['inventory'].append(record)
        if model.parent.name not in ('P0-s0', 'F2-s0'):
            continue
        native = out / (model.parent.name + '.trees.txt')
        exported = export_booster(booster, native)
        feats, trees, logistic, _, margin = load_trees(native)
        compact = predict_rows(X, trees, logistic, margin)
        error = float(np.max(np.abs(compact - predictions)))
        assert error < 1e-5, error
        receipt['exports'].append(dict(record, native_path=str(native), native_sha256=sha(native),
             python_compact_max_abs_error=error, parity_tolerance=1e-5,
             native_binary_parity='PENDING', logistic=exported['logistic'],
             information_boundary='No four hidden future queues; latent pity counters retained as in E1',
             qualification='UNQUALIFIED_CURRENT_SOURCE; historical privileged-continuation labels'))
    (out / 'export_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'output': str(out), 'loaded': len(receipt['inventory']),
                      'exports': receipt['exports']}, indent=2))

if __name__ == '__main__':
    main()
