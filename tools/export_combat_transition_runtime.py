#!/usr/bin/env python3
"""Export the six hash-locked #174 models; no fitting or inference service."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import combat_transition_composed as composed
from tools.combat_predictor_input_contract import FIELD_SCHEMA, FIELD_SCHEMA_HASH

MAGIC = b'COMBAT_TRANSITION_RUNTIME_V1\0'
VERSION = 1
PROBABILITY_TOLERANCE = 1e-4


def runtime_payload():
    # FrozenModels verifies ALL identities before deserializing any checkpoint.
    m = composed.FrozenModels('cpu')
    nets = dict(survival=m.survival_net, max_hp=m.max_net, hp=m.hp_net,
                potion_encoder=m.potion_encoder, potion=m.potion_net, relic=m.relic_net)
    tensors = {}
    # Preserve torch Linear [out,in], embedding [category,width], and Q/K/V order.
    for group, net in nets.items():
        for name, value in sorted(net.state_dict().items()):
            if group == 'hp' and name == 'classes':
                continue  # int64 domain is metadata, never converted to a float tensor
            if not value.is_floating_point():
                raise ValueError(f'unexpected nonfloat buffer {group}.{name}')
            array = value.detach().cpu().float().contiguous().numpy().astype('<f4')
            if not composed.np.isfinite(array).all():
                raise ValueError('nonfinite source tensor')
            tensors[f'{group}.{name}'] = array
    metadata = dict(schema='COMBAT_TRANSITION_RUNTIME_V1', version=VERSION,
                    predictorSchema=composed.base.PREDICTOR_SCHEMA if hasattr(composed.base,'PREDICTOR_SCHEMA') else 'combat_predictor_input_v1',
                    predictorFieldSchema=FIELD_SCHEMA, predictorHash=FIELD_SCHEMA_HASH,
                    width=64, layers=2, heads=4, feedForward=128,
                    cardCount=composed.base.CARD_COUNT, relicCount=composed.base.RELIC_COUNT,
                    potionCount=composed.base.POTION_COUNT,
                    globalCategoryCounts=list(composed.base.GLOBAL_CATEGORY_COUNTS.values()),
                    continuousFields=list(composed.base.CONTINUOUS_GLOBAL_FIELDS),
                    maxHpClasses=m.delta_values.tolist(), hpClasses=m.classes.tolist(),
                    domain=m.domain, sources=m.hashes,
                    probabilityTolerance=PROBABILITY_TOLERANCE,
                    tensors={k:list(v.shape) for k,v in tensors.items()})
    return metadata, tensors


def export(path):
    metadata, tensors = runtime_payload()
    header = json.dumps(metadata, sort_keys=True, separators=(',',':')).encode()
    # Exclusive create prevents accidentally replacing a frozen export.
    with Path(path).open('xb') as stream:
        stream.write(MAGIC)
        stream.write(struct.pack('<II', VERSION, len(header)))
        stream.write(header)
        for name in sorted(tensors):
            stream.write(tensors[name].tobytes(order='C'))
    p=Path(path)
    return dict(path=str(p.resolve()), sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                bytes=p.stat().st_size, sources=metadata['sources'])


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    print(json.dumps(export(args.output),indent=2))
