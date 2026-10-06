#!/usr/bin/env python3
"""Export the frozen #379 S1 three-seed ensemble to a plain-text native format.

Also writes a VALIDATION parity input (base461 + public screen + option keys)
with the Python ensemble probability for each row, for the native self-test.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT)]
import numpy as np
import torch
from screen_leaf_model_379 import build_model, encode_state, pack_encoded, verify_feature_names
from train_screen_leaf_379 import predict

ORDER = ['mean', 'scale', 'ids.weight', 'kinds.weight', 'roles.weight', 'effects.weight', 'sources.weight',
         'targets.weight', 'events.weight', 'screens.weight', 'card_encoder.0.weight', 'card_encoder.0.bias',
         'group_encoder.0.weight', 'group_encoder.0.bias', 'entity_encoder.0.weight', 'entity_encoder.0.bias',
         'action_encoder.0.weight', 'action_encoder.0.bias', 'trunk.0.weight', 'trunk.0.bias',
         'trunk.3.weight', 'trunk.3.bias', 'head.weight', 'head.bias']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--training', type=Path, required=True)
    p.add_argument('--arm', default='S1')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--parity-output', type=Path)
    p.add_argument('--parity-rows', type=int, default=1024)
    a = p.parse_args()
    result = json.loads((a.training / 'result.json').read_text())
    prereg = json.loads((a.training / 'preregistered.json').read_text())
    dataset = json.loads((a.training / 'dataset.json').read_text())
    names = verify_feature_names(dataset['feature_names'])
    from screen_leaf_data_379 import DecisionCorpus, HEADER_SHA
    corpus = DecisionCorpus()
    first = corpus.components[0]
    header = json.loads(Path(first['manifest']).read_text())['stateFeatures']['header']
    if hashlib.sha256(header.encode()).hexdigest() != HEADER_SHA:
        raise ValueError('rich header identity differs')
    full = header.split(',')
    indices = [full.index(n) for n in names]
    norm = np.load(a.training / 'normalization.npz')
    models, seeds = [], []
    lines = ['screen-leaf-native-v1', f'arm {a.arm}', 'mask ' + ' '.join(prereg['replacement_candidates']),
             'indices ' + ' '.join(map(str, indices))]
    for seed in prereg['recipe']['seeds']:
        record = result['arms'][a.arm]['individual'][seed]
        path = a.training / f'{a.arm}-seed{seed}.pt'
        if digest(path) != record['checkpoint_sha256']:
            raise ValueError('checkpoint changed')
        state = torch.load(path, map_location='cpu', weights_only=True)
        model = build_model(a.arm, {'mean': norm['mean'], 'scale': norm['scale']})
        model.load_state_dict(state, strict=True); model.eval(); models.append(model)
        lines.append(f'seed {seed} {record["checkpoint_sha256"]}')
        for name in ORDER:
            t = state[name].detach().cpu().numpy().astype(np.float64)
            lines.append(f'{name} {t.ndim} ' + ' '.join(map(str, t.shape)) + ' ' +
                         ' '.join(repr(float(x)) for x in t.ravel()))
    a.output.write_text('\n'.join(lines) + '\nend\n')
    print(a.output, digest(a.output))
    if a.parity_output:
        rows = []
        for row in corpus.iter_rows('VALIDATION'):
            rows.append(row)
        # Deterministic family-stratified selection, all screens represented.
        per = max(1, a.parity_rows // 4)
        chosen = []
        for screen in prereg['replacement_candidates']:
            family = [r for r in rows if r['screen'] == screen]
            step = max(1, len(family) // per)
            chosen += family[::step][:per]
        encoded = [encode_state(r['base461'], r['screenContents'], r['optionKeys']) for r in chosen]
        cache = pack_encoded(encoded)
        probability = np.mean([predict(m, cache) for m in models], axis=0, dtype=np.float64)
        with a.parity_output.open('w') as stream:
            for r, value in zip(chosen, probability):
                stream.write(json.dumps({'base': [float(x) for x in r['base461']], 'screenContents': r['screenContents'],
                                         'candidateKeys': r['optionKeys'], 'python': float(value)}) + '\n')
        print(a.parity_output, len(chosen))


if __name__ == '__main__':
    main()
