#!/usr/bin/env python3
"""Extract the fixed public-only pilot inputs after exact-run custody checks."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

E = Path(__file__).resolve().parent
ROOT = E.parents[3]
PREVIOUS = E.parent / 'combat_infinity_public_20261023'
DECISIONS = [1, 2, 3, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20]
BASELINE = 'e41dcef5b734b5187d9552c1e41b9f8b6b5ef1cd'
BINARY = 'build/linux-gcc-release-ccache/combat_infinity_oracle'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def generate():
    spec = importlib.util.spec_from_file_location('provenance_audit', PREVIOUS / 'inspect_provenance.py')
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    custody = audit.audit(audit.ARCHIVE)
    assert custody == json.loads((PREVIOUS / 'provenance-inventory.json').read_text())
    assert custody['proposed_first16_decisions'] == DECISIONS
    # Exact reviewed executable/source/CMake custody; no build or binary execution.
    for line in (PREVIOUS / 'sha256.txt').read_text().splitlines():
        expected, path = line.split(maxsplit=1)
        assert sha((ROOT / path).read_bytes()) == expected, path
    source = Path(custody['checked_artifacts']['public']['path'])
    records = [json.loads(x) for x in source.read_text().splitlines()]
    selected = [x for x in records if x['decision'] in DECISIONS]
    assert [x['decision'] for x in selected] == DECISIONS
    inputs, joins = [], []
    for index, row in enumerate(selected):
        wire = json.loads(json.dumps(row['public_wire']))
        s = wire['state']
        assert s['inputState'] == 1 and not s['intentsHidden']
        assert not s['fullDrawOrderObserved'] and not s['drawPile']['fullOrderObserved']
        # Public facts only. Never pass the historical seed/RNG as teacher input.
        s['isolatedSearchSeed'] = 0
        s['observedGeneration'] = 0
        item = {'public_wire': wire, 'oracle_no_prismatic_shard': True}
        inputs.append(item)
        joins.append({'index': index, 'batch': index // 4, 'batch_root_index': index % 4,
                      'source_decision': row['decision'], 'turn': row['turn'],
                      'source_public_envelope_sha256': sha(json.dumps(row['public_wire'], sort_keys=True).encode()),
                      'input_sha256': sha(json.dumps(item, sort_keys=True).encode()),
                      'proof_receipt_sha256': custody['receipt_sha256'],
                      'proof_trace_line_1based': custody['trace_line_1based']})
    outputs = {}
    for batch in range(4):
        outputs[f'inputs-{batch}.jsonl'] = ''.join(json.dumps(x, sort_keys=True) + '\n' for x in inputs[batch*4:batch*4+4])
    manifest = {'schema': 'infinity_natural_pilot_protocol_v1', 'baseline_sha': BASELINE,
                'reviewed_adapter_sha': '40d10995a57e5159a2b5d9d48917aa4280635237',
                'binary': BINARY, 'binary_sha256': sha((ROOT / BINARY).read_bytes()),
                'capture_producer_sha': custody['source_sha'], 'receipt_sha256': custody['receipt_sha256'],
                'source_public_sha256': custody['checked_artifacts']['public']['sha256'],
                'source_trace_sha256': custody['checked_artifacts']['trace']['sha256'],
                'source_seed_for_join_only': custody['seed'], 'ascension': 0,
                'K': 4, 'roots': 16, 'max_worlds': 64, 'batches': 4, 'wall_seconds_per_batch': 30,
                'caps_per_world': {'depth': 24, 'nodes': 2000, 'candidates': 16, 'periods': 128,
                                   'actions_per_candidate': 1024, 'total_replay_actions': 4096},
                'input_files_sha256': {name: sha(body.encode()) for name, body in outputs.items()},
                'selection': joins}
    outputs['manifest.json'] = json.dumps(manifest, indent=2) + '\n'
    return outputs

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    for name, content in generate().items():
        if args.check:
            assert (E / name).read_bytes() == content.encode(), name
        else:
            assert not (E / name).exists(), 'do not overwrite a frozen input: ' + name
            (E / name).write_text(content)
    print('PASS custody, fixed16 selection, public-only inputs, reviewed executable; no worlds executed')
