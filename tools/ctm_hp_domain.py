"""Declared HP domain and warm-start expansion for the #418 CTM retrain.

The production HP head predicts signed post-combat HP deltas over classes
-160..143 (304), frozen from the old corpus by `stochastic_hp.freeze_domain`.
A retrain whose envelope reaches max HP ~220 needs a wider, declared domain:

    min = 1 - preCurHpRange[1]                              (HP 1 from the highest pre HP)
    max = preMaxHpRange[1] - 1 + max(maxHpDeltaValues)      (full heal at the highest max HP)

`expand` widens the production HP and relic warm starts to that domain. Old
classes keep their rows. New HP-head rows get zero weights and a large negative
bias, so a widened model scores every old class as before until it is refit.
New relic-delta embedding rows copy the nearest old edge row. The C++ runtime
recomputes the domain SHA256 the same way (combat_transition_runtime.cpp).

    python tools/ctm_hp_domain.py declare --pre-cur-max 220 --pre-max-max 220
    python tools/ctm_hp_domain.py expand --hp HP.pt --relic RELIC.pt \\
        --pre-cur-max 220 --pre-max-max 220 --out DIR
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

PRODUCTION_DELTA_VALUES = [0, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
PRODUCTION_PRE_MAX_RANGE = [24, 172]
NEW_CLASS_BIAS = -30.0
DECLARED_RULE = '[1-preCurHpRange[1],preMaxHpRange[1]-1+max(maxHpDeltaValues)]'


def domain_sha256(domain: dict) -> str:
    """The `stochastic_hp.freeze_domain` hash: sorted compact JSON without `sha256`."""
    body = {k: v for k, v in domain.items() if k != 'sha256'}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def declared_domain(pre_cur_max: int, pre_max_max: int, pre_max_min: int = PRODUCTION_PRE_MAX_RANGE[0],
                    delta_values=PRODUCTION_DELTA_VALUES) -> dict:
    if not 1 <= pre_cur_max <= pre_max_max or not 1 <= pre_max_min <= pre_max_max:
        raise ValueError('invalid declared HP envelope')
    low, high = 1 - pre_cur_max, pre_max_max - 1 + max(delta_values)
    domain = dict(min=low, max=high, classes=high - low + 1, envelope='declared retrain envelope',
                  preCurHpRange=[1, int(pre_cur_max)], preMaxHpRange=[int(pre_max_min), int(pre_max_max)],
                  maxHpDeltaValues=[int(d) for d in delta_values], rule=DECLARED_RULE)
    domain['sha256'] = domain_sha256(domain)
    return domain


def _row_map(old_classes, new_classes):
    old, new = np.asarray(old_classes, np.int64), np.asarray(new_classes, np.int64)
    if not np.array_equal(old, np.arange(old[0], old[-1] + 1)) or not np.array_equal(new, np.arange(new[0], new[-1] + 1)):
        raise ValueError('HP classes must be contiguous')
    if new[0] > old[0] or new[-1] < old[-1]:
        raise ValueError('declared domain must contain the warm-start classes')
    return int(old[0] - new[0])


def expand_hp_state(state: dict, new_classes) -> dict:
    """Widen an `stochastic_hp.new_model` state dict (head `hp.2`, buffer `classes`)."""
    import torch
    old = state['classes'].cpu().numpy()
    offset = _row_map(old, new_classes)
    out = dict(state)
    weight, bias = state['hp.2.weight'], state['hp.2.bias']
    wide_w = torch.zeros((len(new_classes), weight.shape[1]), dtype=weight.dtype)
    wide_b = torch.full((len(new_classes),), NEW_CLASS_BIAS, dtype=bias.dtype)
    wide_w[offset:offset + len(old)] = weight
    wide_b[offset:offset + len(old)] = bias
    out['hp.2.weight'], out['hp.2.bias'] = wide_w, wide_b
    out['classes'] = torch.as_tensor(np.asarray(new_classes), dtype=state['classes'].dtype)
    return out


def expand_relic_state(state: dict, old_classes, new_classes) -> dict:
    """Widen a `relic_trajectory.new_decoder` state dict (embedding `delta`)."""
    import torch
    offset = _row_map(old_classes, new_classes)
    old = state['delta.weight']
    count = len(old_classes)
    index = np.clip(np.arange(len(new_classes)) - offset, 0, count - 1)
    out = dict(state)
    out['delta.weight'] = old[torch.as_tensor(index)].clone()
    return out


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expand(hp_path: Path, relic_path: Path, domain: dict, out: Path) -> dict:
    import torch
    if out.exists():
        raise ValueError(f'refusing to overwrite {out}')
    hp = torch.load(hp_path, map_location='cpu', weights_only=False)
    relic = torch.load(relic_path, map_location='cpu', weights_only=False)
    old_classes = hp['state_dict']['classes'].cpu().numpy()
    if hp['metadata']['domain']['maxHpDeltaValues'] != domain['maxHpDeltaValues']:
        raise ValueError('declared domain changes the maxHP delta classes')
    if relic['state_dict']['delta.weight'].shape[0] != len(old_classes):
        raise ValueError('relic warm start does not match the HP classes')
    new_classes = np.arange(domain['min'], domain['max'] + 1, dtype=np.int64)
    out.mkdir(parents=True)
    hp_out = dict(hp, state_dict=expand_hp_state(hp['state_dict'], new_classes),
                  metadata=dict(hp['metadata'], domain=domain))
    relic_out = dict(relic, state_dict=expand_relic_state(relic['state_dict'], old_classes, new_classes))
    torch.save(hp_out, out / 'hp.pt')
    torch.save(relic_out, out / 'relic.pt')
    (out / 'domain.json').write_text(json.dumps(domain, indent=2, sort_keys=True) + '\n')
    receipt = dict(schema='ctm_hp_domain_expansion_v1', domain=domain, newClassBias=NEW_CLASS_BIAS,
                   inputs={'hp': sha256(hp_path), 'relic': sha256(relic_path)},
                   outputs={'hp': sha256(out / 'hp.pt'), 'relic': sha256(out / 'relic.pt')},
                   pins={'combat_transition_composed.HP_CLASS_RANGE': [domain['min'], domain['max']]})
    (out / 'receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('declare', 'expand'):
        p = sub.add_parser(name)
        p.add_argument('--pre-cur-max', type=int, required=True)
        p.add_argument('--pre-max-max', type=int, required=True)
        if name == 'expand':
            p.add_argument('--hp', type=Path, required=True)
            p.add_argument('--relic', type=Path, required=True)
            p.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    domain = declared_domain(args.pre_cur_max, args.pre_max_max)
    result = domain if args.command == 'declare' else expand(args.hp, args.relic, domain, args.out)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
