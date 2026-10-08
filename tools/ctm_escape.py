"""Escape capability for the #418 CTM retrain (PR7).

Production excludes combats that start with a Smoke Bomb, because the old
factorization drew the escape inside the potion trajectory, after HP, and the
relic exposure on Smoke rows failed (near_full_combat_support_2026-09-14/REPORT.md).
This capability draws the escape first and conditions the rest on it:

    survival -> maxHP -> escape (eligible rows) -> HP | escape -> potions | escape -> ...

* Escape head: a 1x64 logistic head on the artifact's HP encoding z. A row is
  eligible when it is not a boss fight and holds a Smoke Bomb in a usable slot.
* HP head: the escape bit is a new last input (72 -> 73). It is a zero-column warm
  start, so before fitting both bits score exactly as the base head.
* Potion trajectory: escape 0 forbids using a Smoke Bomb; escape 1 forbids
  stopping or discarding one, so the trajectory ends with its use
  (combat_transition_potion_trajectory.escape_condition).

The fit uses the native artifact's own z (`one_combat ctmescapefeatures`), so it
is the same for the Attention and the DeepSets artifacts:

    one_combat ctmescapefeatures ROWS.jsonl BASE.native FEATURES
    python tools/ctm_escape.py fit --artifact BASE.native --features FEATURES --out DIR
    python tools/ctm_escape.py extend --artifact BASE.native --checkpoint DIR/escape.pt --out NEW.native

`extend` writes a research-candidate artifact with metadata
capabilities={"escape": {"checkpointSha256": ...}} and without the smoke_bomb
exclusion; a ctm_research_candidate_v3 manifest must list the same capabilities.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from pathlib import Path

import numpy as np

MAGIC = b'COMBAT_TRANSITION_RUNTIME_V2\0'
SMOKE, BREW, EMPTY = 37, 17, 1
HP_TENSORS = ('hp.delta_embedding.weight', 'hp.hp.0.weight', 'hp.hp.0.bias', 'hp.hp.2.weight', 'hp.hp.2.bias')
ESCAPE_TENSORS = ('escape.escape.weight', 'escape.escape.bias')
EXCLUSIONS = ['smoke_bomb', 'pre_smoke_bomb_used', 'writhing_ritual_intersection']
L2_GRID = (1e-4, 1e-3, 1e-2, 1e-1)


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_artifact(path):
    data = Path(path).read_bytes()
    if not data.startswith(MAGIC):
        raise ValueError('not a V2 near-full artifact')
    version, length = struct.unpack_from('<II', data, len(MAGIC))
    offset = len(MAGIC) + 8
    metadata = json.loads(data[offset:offset + length])
    offset += length
    tensors = {}
    for name, shape in sorted(metadata['tensors'].items()):
        size = int(np.prod(shape))
        tensors[name] = np.frombuffer(data, '<f4', size, offset).reshape(shape).copy()
        offset += 4 * size
    if version != 2 or offset != len(data):
        raise ValueError('artifact layout differs')
    return metadata, tensors


def write_artifact(path, metadata, tensors):
    metadata = dict(metadata, tensors={name: list(value.shape) for name, value in tensors.items()})
    header = json.dumps(metadata, sort_keys=True, separators=(',', ':')).encode()
    with open(path, 'xb') as stream:
        stream.write(MAGIC + struct.pack('<II', 2, len(header)) + header)
        for name in sorted(tensors):
            array = np.ascontiguousarray(tensors[name], '<f4')
            if not np.isfinite(array).all():
                raise ValueError(f'nonfinite tensor {name}')
            stream.write(array.tobytes())


def eligible(potions, capacity, boss) -> bool:
    """CombatTransitionRuntime::escapeEligible."""
    return not boss and any(p == SMOKE for p in list(potions)[:int(capacity)])


# NumPy reference of the native heads, for parity tests.
def escape_probability(tensors, z):
    logit = np.asarray(z, np.float64) @ tensors['escape.escape.weight'][0].astype(np.float64) + float(tensors['escape.escape.bias'][0])
    return 1 / (1 + np.exp(-logit))


def hp_probabilities(tensors, classes, z, delta, pre, maximum, escaped):
    x = np.concatenate((np.asarray(z, np.float64), tensors['hp.delta_embedding.weight'][delta].astype(np.float64), [float(escaped)]))
    hidden = np.maximum(tensors['hp.hp.0.weight'].astype(np.float64) @ x + tensors['hp.hp.0.bias'], 0)
    logits = tensors['hp.hp.2.weight'].astype(np.float64) @ hidden + tensors['hp.hp.2.bias']
    post = pre + np.asarray(classes)
    logits[(post < 1) | (post > maximum)] = -np.inf
    p = np.exp(logits - logits.max())
    return p / p.sum()


def potion_legal(inventory, capacity, boss, escape):
    """Legal mask of the 64 potion actions (low 5 bits clear slots, +32 uses a trigger)."""
    legal = np.zeros(64, bool)
    for action in range(64):
        mask, use = action & 31, action >= 32
        chosen = [slot for slot in range(5) if mask & (1 << slot)]
        if any(slot >= capacity or inventory[slot] <= EMPTY for slot in chosen):
            continue
        triggers = sum(inventory[slot] in (BREW, SMOKE) for slot in chosen)
        smoke = any(inventory[slot] == SMOKE for slot in chosen)
        ok = triggers <= 1 and (not use or (triggers == 1 and not (boss and smoke)))
        if escape == 0:
            ok &= not (smoke and use)
        if escape == 1:
            ok &= mask != 0 and not (smoke and not use)
        legal[action] = ok
    return legal


class TorchEscape:
    """The fitted escape and HP heads, applied to an HP encoding."""

    def __init__(self, tensors, device='cpu'):
        import torch
        self.torch, self.device = torch, device
        self.t = {name: torch.as_tensor(np.asarray(tensors[name], np.float32), device=device)
                  for name in ESCAPE_TENSORS + HP_TENSORS}

    @classmethod
    def load(cls, path, device='cpu'):
        import torch
        return cls(torch.load(path, map_location='cpu', weights_only=False)['tensors'], device)

    def eligible(self, potions, capacity, boss):
        return eligible(potions, capacity, boss)

    def probability(self, z):
        z = self.torch.as_tensor(np.asarray(z.cpu() if hasattr(z, 'cpu') else z, np.float32), device=self.device).reshape(-1, 64)
        return self.torch.sigmoid(z @ self.t['escape.escape.weight'][0] + self.t['escape.escape.bias'][0]).cpu().numpy()

    def logits(self, z, delta, escaped):
        torch = self.torch
        z = torch.as_tensor(np.asarray(z.cpu() if hasattr(z, 'cpu') else z, np.float32), device=self.device).reshape(-1, 64)
        delta = torch.as_tensor(np.asarray(delta, np.int64).reshape(-1), device=self.device).expand(len(z))
        bit = torch.as_tensor(np.asarray(escaped, np.float32).reshape(-1), device=self.device).expand(len(z))
        x = torch.cat((z, self.t['hp.delta_embedding.weight'][delta], bit[:, None]), -1)
        hidden = torch.relu(x @ self.t['hp.hp.0.weight'].T + self.t['hp.hp.0.bias'])
        return hidden @ self.t['hp.hp.2.weight'].T + self.t['hp.hp.2.bias']

    def probabilities(self, z, delta, pre, maximum, escaped, classes):
        torch = self.torch
        logits = self.logits(z, delta, escaped)
        post = torch.as_tensor(np.asarray(pre).reshape(-1, 1) + np.asarray(classes)[None], device=self.device)
        legal = (post >= 1) & (post <= torch.as_tensor(np.asarray(maximum).reshape(-1, 1), device=self.device))
        return torch.softmax(logits.masked_fill(~legal, -torch.inf), -1).double().cpu().numpy()

    def hp_distribution(self, z, delta, pre, maximum, escaped, classes):
        return self.probabilities(z, delta, pre, maximum, escaped, classes)[0]


def load_features(prefix):
    with open(f'{prefix}.csv') as stream:
        rows = [r for r in csv.DictReader(stream) if r['supported'] == '1']
    z = np.fromfile(f'{prefix}.f32', '<f4').reshape(-1, 64)
    if len(z) != len(rows) or [int(r['z_row']) for r in rows] != list(range(len(rows))):
        raise ValueError('feature rows and encodings differ')
    columns = {k: np.asarray([int(r[k]) for r in rows], np.int64)
               for k in ('source_seed', 'delta_class', 'hp_class', 'pre_hp', 'post_max_hp', 'escaped', 'eligible')}
    return z, columns


def split_for_seed(seed):
    """combat_transition_model_experiment split: 0 TRAIN, 1 VALIDATION, 2 TEST."""
    raw = hashlib.sha256(f'combat-transition-model-v1:{int(seed)}'.encode()).digest()
    bucket = int.from_bytes(raw[:8], 'big') % 100
    return 0 if bucket < 80 else 1 if bucket < 90 else 2


def _binary(p, y):
    p = np.clip(np.asarray(p, np.float64), 1e-12, 1 - 1e-12)
    return dict(rows=int(len(y)), nll=float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))),
                brier=float(np.mean((p - y) ** 2)), meanProbability=float(p.mean()), rate=float(np.mean(y)))


def fit(artifact, features, out, mode='column', epochs=40, lr=1e-3, batch=4096, seed=20261008):
    import torch
    out = Path(out)
    if out.exists():
        raise ValueError(f'refusing to overwrite {out}')
    metadata, tensors = read_artifact(artifact)
    if metadata.get('capabilities'):
        raise ValueError('base artifact already has capabilities')
    classes = np.asarray(metadata['hpClasses'], np.int64)
    z, col = load_features(features)
    split = np.asarray([split_for_seed(s) for s in col['source_seed']])
    torch.manual_seed(seed)
    zt = torch.as_tensor(z)

    # Escape head: L2 logistic regression on eligible rows, L2 chosen on VALIDATION.
    y = col['escaped'].astype(np.float64)
    elig = col['eligible'] == 1
    train, val, test = (elig & (split == k) for k in (0, 1, 2))
    if not (y[train].any() and y[val].any()):
        raise ValueError('escape fit needs escapes in TRAIN and VALIDATION')
    base_rate = float(y[train].mean())
    candidates = []
    for l2 in L2_GRID:
        w = torch.zeros(64, dtype=torch.float64, requires_grad=True)
        b = torch.tensor(float(np.log(base_rate / (1 - base_rate))), dtype=torch.float64, requires_grad=True)
        x, target = zt[train].double(), torch.as_tensor(y[train])
        opt = torch.optim.LBFGS([w, b], max_iter=500, line_search_fn='strong_wolfe')

        def closure():
            opt.zero_grad()
            loss = torch.nn.functional.binary_cross_entropy_with_logits(x @ w + b, target) + l2 * (w * w).sum()
            loss.backward()
            return loss
        opt.step(closure)
        with torch.no_grad():
            p_val = torch.sigmoid(zt[val].double() @ w + b).numpy()
        candidates.append((_binary(p_val, y[val])['nll'], l2, w.detach().clone(), b.detach().clone()))
    _, l2, w, b = min(candidates, key=lambda c: c[0])
    with torch.no_grad():
        p_all = torch.sigmoid(zt.double() @ w + b).numpy()
    escape_report = {name: dict(model=_binary(p_all[m], y[m]), constant=_binary(np.full(m.sum(), base_rate), y[m]))
                     for name, m in (('TRAIN', train), ('VALIDATION', val), ('TEST', test))}

    # HP head with the escape bit: zero-column warm start. "column" fits only the new
    # column, so escape-bit-0 probabilities stay exactly the base head's.
    bit = torch.as_tensor(((col['escaped'] == 1) & elig).astype(np.float32))
    params = {name: torch.as_tensor(tensors[name]).clone() for name in HP_TENSORS}
    params['hp.hp.0.weight'] = torch.cat((params['hp.hp.0.weight'], torch.zeros(64, 1)), 1)
    trainable = ['hp.hp.0.weight'] if mode == 'column' else list(HP_TENSORS)
    for name in trainable:
        params[name].requires_grad_(True)
    column_mask = torch.zeros(64, 73)
    column_mask[:, 72] = 1
    if mode == 'column':
        params['hp.hp.0.weight'].register_hook(lambda g: g * column_mask)
    delta = torch.as_tensor(col['delta_class'])
    target = torch.as_tensor(col['hp_class'])
    post = torch.as_tensor(col['pre_hp'])[:, None] + torch.as_tensor(classes)[None]
    legal = (post >= 1) & (post <= torch.as_tensor(col['post_max_hp'])[:, None])

    def nll(index, p=params, escape_bit=None):
        e = bit[index] if escape_bit is None else escape_bit
        x = torch.cat((zt[index], p['hp.delta_embedding.weight'][delta[index]], e[:, None]), -1)
        h = torch.relu(x @ p['hp.hp.0.weight'].T + p['hp.hp.0.bias'])
        logits = (h @ p['hp.hp.2.weight'].T + p['hp.hp.2.bias']).masked_fill(~legal[index], -torch.inf)
        return -torch.log_softmax(logits, -1).gather(1, target[index][:, None])[:, 0]

    def score(index, p=params):
        with torch.no_grad():
            return float(torch.cat([nll(index[s:s + batch], p) for s in range(0, len(index), batch)]).mean())
    ids = {name: np.flatnonzero(split == k) for k, name in enumerate(('TRAIN', 'VALIDATION', 'TEST'))}
    escaped_ids = {name: v[col['escaped'][v] == 1] for name, v in ids.items()}
    before = {name: dict(all=score(v), escaped=score(escaped_ids[name]) if len(escaped_ids[name]) else None)
              for name, v in ids.items()}
    opt = torch.optim.Adam([params[n] for n in trainable], lr=lr)
    best = (score(ids['VALIDATION']), 0, {k: v.detach().clone() for k, v in params.items()})
    history = []
    rng = np.random.default_rng(seed)
    for epoch in range(1, epochs + 1):
        order = rng.permutation(ids['TRAIN'])
        for s in range(0, len(order), batch):
            opt.zero_grad()
            nll(order[s:s + batch]).mean().backward()
            opt.step()
        value = score(ids['VALIDATION'])
        history.append(dict(epoch=epoch, validationNll=value))
        if value < best[0]:
            best = (value, epoch, {k: v.detach().clone() for k, v in params.items()})
    chosen = best[2]
    after = {name: dict(all=score(v, chosen), escaped=score(escaped_ids[name], chosen) if len(escaped_ids[name]) else None)
             for name, v in ids.items()}

    out.mkdir(parents=True)
    fitted = {name: chosen[name].detach().numpy().astype(np.float32) for name in HP_TENSORS}
    fitted['escape.escape.weight'] = w.numpy().astype(np.float32)[None]
    fitted['escape.escape.bias'] = np.asarray([float(b)], np.float32)
    fit_metadata = dict(schema='ctm_escape_fit_v1', baseArtifactSha256=sha256(artifact),
                        featuresSha256={'f32': sha256(f'{features}.f32'), 'csv': sha256(f'{features}.csv')},
                        mode=mode, epochs=epochs, lr=lr, batch=batch, seed=seed, l2=l2, l2Grid=list(L2_GRID),
                        selectedEpoch=best[1], hpClasses=[int(classes[0]), int(classes[-1])])
    torch.save(dict(tensors=fitted, metadata=fit_metadata), out / 'escape.pt')
    unrepresentable = int(((col['escaped'] == 1) & ~elig).sum())
    receipt = dict(fit_metadata, checkpointSha256=sha256(out / 'escape.pt'),
                   rows={name: int(len(v)) for name, v in ids.items()},
                   eligibleRows={name: int(m.sum()) for name, m in (('TRAIN', train), ('VALIDATION', val), ('TEST', test))},
                   escapeRows={name: int(len(v)) for name, v in escaped_ids.items()},
                   unrepresentableEscapes=unrepresentable, escapeHead=escape_report,
                   hpNll=dict(before=before, after=after), history=history,
                   note='hpNll.before scores the base head with the bit ignored (zero column).')
    (out / 'fit.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    return receipt


def extend(artifact, checkpoint, out):
    import torch
    metadata, tensors = read_artifact(artifact)
    payload = torch.load(checkpoint, map_location='cpu', weights_only=False)
    if payload['metadata']['baseArtifactSha256'] != sha256(artifact):
        raise ValueError('escape fit was made on a different artifact')
    if 'researchCandidate' not in metadata:
        raise ValueError('only a research candidate may carry a capability')
    if metadata.get('capabilities') or metadata['supportExclusions'] != EXCLUSIONS:
        raise ValueError('base artifact already changes capabilities or exclusions')
    fitted = payload['tensors']
    for name in HP_TENSORS:
        expected = list(tensors[name].shape)
        if name == 'hp.hp.0.weight':
            expected[1] += 1
        if list(fitted[name].shape) != expected:
            raise ValueError(f'{name} shape differs')
    tensors.update({name: np.asarray(fitted[name], np.float32) for name in HP_TENSORS + ESCAPE_TENSORS})
    metadata = dict(metadata, capabilities={'escape': {'checkpointSha256': sha256(checkpoint)}},
                    supportExclusions=[r for r in EXCLUSIONS if r != 'smoke_bomb'])
    write_artifact(out, metadata, tensors)
    return dict(artifact=str(out), artifactSha256=sha256(out), baseArtifactSha256=sha256(artifact),
                capabilities=metadata['capabilities'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('fit')
    p.add_argument('--artifact', type=Path, required=True)
    p.add_argument('--features', type=Path, required=True, help='ctmescapefeatures OUT_PREFIX')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--mode', choices=('column', 'head'), default='column')
    p.add_argument('--epochs', type=int, default=40)
    p.add_argument('--lr', type=float, default=1e-3)
    p = sub.add_parser('extend')
    p.add_argument('--artifact', type=Path, required=True)
    p.add_argument('--checkpoint', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'fit':
        result = fit(args.artifact, args.features, args.out, args.mode, args.epochs, args.lr)
    else:
        result = extend(args.artifact, args.checkpoint, args.out)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
