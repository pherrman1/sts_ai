#!/usr/bin/env python3
"""Arm C value head and trunk fine-tune on observed Heart outcomes (development only).

Student C (`student-c-68fe88be.pt`, the Arm C prior) was distilled on heart1's policy
logits only; its value head was never trained. This tool trains value head and trunk on
§497 Heart win/loss labels, with an auxiliary pairwise ranking loss on the §494 sibling
leaves' 64-rollout means and a KL guard that keeps the policy head near the original.

  cache --out DIR       encode §497 TRAIN/VALIDATION states and §494 TRAIN/VALIDATION
                        leaves into fixed-size memmaps (no fitting, no TEST reader)
  fit --cache DIR --arm ARM --out DIR
                        one pre-registered arm (ARMS); select on VALIDATION visitation BCE

TEST/CONFIRM data have no reader here: §497 TEST is not in heart_outcome_value.SPLITS and
§494 sources at or above 110164048 are refused.
"""
import argparse
from collections import defaultdict
import json
import math
import os
from pathlib import Path
import sys
import time

import numpy as np
import torch
from torch.nn import functional as F

import heart_outcome_value as value
from heart_outcome_collect import sha, write
from outcome_head_sibling_check import group_metrics

REPO = Path(__file__).resolve().parents[1]
SIBLING_TRAIN_END, SIBLING_VALIDATION_END = 110164040, 110164048  # §494 40/8/16 split
SIBLING_MANIFEST = '5a45c78f948e946e4ae85dc2ffe721b61850065b1b3dcde76e8a0d2d69249e36'
# Arm name -> sibling ranking weight. Policy KL weight, schedule and seed are shared.
ARMS = {'outcome': 0.0, 'rank05': 0.5, 'rank2': 2.0}
KL_WEIGHT, LR, WEIGHT_DECAY = 1.0, 3e-4, .01
STEPS, EVERY, BATCH, SIBLING_LEAVES, ENCODE = 2000, 100, 512, 256, 512
INIT = 0


def collate(network, records):
    return network.collate_fn([{**value.trim_record(r), 'chosen_idx': 0, 'outcome': 0.} for r in records])


def flat(obj, prefix=''):
    for k, v in obj.items():
        if isinstance(v, dict):
            yield from flat(v, prefix + k + '.')
        elif isinstance(v, torch.Tensor):
            yield prefix + k, v


def unflat(arrays, ids, device):
    out = {}
    for key, a in arrays.items():
        node, parts = out, key.split('.')
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = torch.from_numpy(np.ascontiguousarray(a[ids])).to(device)
    return out


class Store:
    """Fixed-size collated tensors in one memmap per key (silverbot pads to fixed maxima)."""

    def __init__(self, root, n=None, template=None):
        self.root = Path(root)
        if template is None:
            spec = json.loads((self.root/'spec.json').read_text())
            self.n = spec['n']
            self.arrays = {k: np.memmap(self.root/f'{k}.bin', dtype=d, mode='r', shape=tuple(s))
                           for k, (d, s) in spec['keys'].items()}
            return
        self.root.mkdir(parents=True, exist_ok=False)
        self.n, spec = n, {}
        for key, t in flat(template):
            dtype = str(t.numpy().dtype)
            spec[key] = (dtype, [n, *t.shape[1:]])
        write(self.root/'spec.json', {'n': n, 'keys': spec})
        self.arrays = {k: np.memmap(self.root/f'{k}.bin', dtype=d, mode='w+', shape=tuple(s))
                       for k, (d, s) in spec.items()}

    def put(self, offset, batch):
        for key, t in flat(batch):
            self.arrays[key][offset:offset+len(t)] = t.numpy()

    def close(self):
        for a in self.arrays.values():
            a.flush()


def load_siblings(root):
    """§494 TRAIN+VALIDATION leaves, same acceptance as outcome_head_sibling_check.load_siblings."""
    root = Path(root)
    manifest = json.loads((root/'corpus-manifest.json').read_text())
    value.require(sha(root/'corpus-manifest.json') == SIBLING_MANIFEST, '§494 corpus manifest changed')
    rows = []
    for seed in range(110164000, SIBLING_VALIDATION_END):
        path = root/f'seed-{seed}.sib.jsonl'
        value.require(sha(path) == manifest['sources'][str(seed)]['captureSha256'], f'§494 capture changed: {seed}')
        accepted, bad = [], set()
        for raw in map(json.loads, path.open()):
            e, group = raw.get('extra', {}), (seed, raw['decision'], raw['parent'])
            reps = e.get('repeats', [])
            if (len(reps) != 64 or 'record' not in e or 'x2b' not in e or e.get('rolloutPolicy') != 'heart1'
                    or e.get('recordSchema') != 'heart1-public-record-v2'):
                bad.add(group)
                continue
            accepted.append({'seed': seed, 'group': list(group), 'action': raw['action'], 'act': raw['act'],
                             'screen': raw['parentScreen'], 'target': float(np.mean([v['value'] for v in reps])),
                             'x2b': float(e['x2b']), 'r0': float(raw['value']), 'record': e['record']})
        rows += [r for r in accepted if tuple(r['group']) not in bad]
    return rows


def sibling_groups(rows, train):
    groups = defaultdict(list)
    for i, r in enumerate(rows):
        if (r['seed'] < SIBLING_TRAIN_END) == train:
            groups[tuple(r['group'])].append(i)
    return [g for g in groups.values() if len({rows[i]['action'] for i in g}) >= 2]


def encode_cache(args):
    out = Path(args.out)
    value.require(not out.exists(), 'cache output exists')
    network, _ = value.load_net(args, 'cpu')
    manifest, custody = value.audit_inputs(args)
    started = time.monotonic()
    meta = {}
    for split in value.SPLITS:
        n = sum(r['states'] for r in manifest if r['split'] == split)
        meta[split], chunk, store = [], [], None
        def flush():
            nonlocal store
            batch = collate(network, [r['record'] for r in chunk])
            store = store or Store(out/split, n, batch)
            store.put(len(meta[split]), batch)
            meta[split].extend({k: v for k, v in r.items() if k != 'record'} | {'choices': value.has_choices(r['record'])}
                               for r in chunk)
            chunk.clear()
        for row in value.read_sources(args, manifest, split):  # streamed: RAM holds one chunk
            chunk.append(row)
            if len(chunk) == ENCODE:
                flush()
        if chunk:
            flush()
        value.require(len(meta[split]) == n, 'state count')
        store.close()
        print('encoded', split, n, round(time.monotonic()-started, 1), flush=True)
    leaves = load_siblings(args.siblings)
    store = None
    for i in range(0, len(leaves), ENCODE):
        batch = collate(network, [r['record'] for r in leaves[i:i+ENCODE]])
        store = store or Store(out/'siblings', len(leaves), batch)
        store.put(i, batch)
    store.close()
    meta['siblings'] = [{k: v for k, v in r.items() if k != 'record'} for r in leaves]
    write(out/'meta.json', meta)
    write(out/'cache.json', {'schema': 'arm-c-value-finetune-cache-v1', 'custody': custody,
        'siblingManifestSha256': SIBLING_MANIFEST, 'checkpointSha256': sha(args.checkpoint),
        'metaSha256': sha(out/'meta.json'), 'counts': {k: len(v) for k, v in meta.items()},
        'seconds': time.monotonic()-started})


def rank_loss(v, target, groups):
    """Pairwise logistic loss on value logits for sibling leaves, weighted by |target gap|."""
    i, j, w = [], [], []
    for g in groups:
        for a in range(len(g)):
            for b in range(a):
                gap = target[g[a]] - target[g[b]]
                if abs(gap) > 1e-8:
                    i.append(g[a] if gap > 0 else g[b]); j.append(g[b] if gap > 0 else g[a]); w.append(abs(gap))
    if not i:
        return v.sum() * 0
    w = torch.tensor(w, device=v.device)
    return (F.softplus(-(v[i] - v[j])) * w).sum() / w.sum()


def policy_kl(new, old, reduce=True):
    """KL(original || fine-tuned) over legal choices; rows with fewer than two choices carry none."""
    valid = torch.isfinite(old)
    rows = valid.sum(1) > 1
    if not rows.any():
        return new.sum() * 0 if reduce else (0., 0)
    lo = torch.log_softmax(old[rows].masked_fill(~valid[rows], -1e9), 1)
    ln = torch.log_softmax(new[rows].masked_fill(~valid[rows], -1e9), 1)
    kl = (lo.exp() * (lo - ln)).masked_fill(~valid[rows], 0).sum(1)
    return kl.mean() if reduce else (float(kl.sum()), int(rows.sum()))


def forward(net, store, ids, device):
    logits, v, _ = net(unflat(store.arrays, ids, device), return_pooled=True)
    return logits, v


def evaluate(net, ref, stores, meta, device):
    net.eval()
    out = {}
    with torch.inference_mode():
        vl, agree, kl_sum, kl_rows = [], [], 0., 0
        n = stores['validation'].n
        for i in range(0, n, ENCODE):
            ids = np.arange(i, min(i+ENCODE, n))
            logits, v = forward(net, stores['validation'], ids, device)
            old, _ = forward(ref, stores['validation'], ids, device)
            vl.append(v.double().cpu())
            has = torch.isfinite(old).any(1)
            agree.append((logits.argmax(1) == old.argmax(1))[has].cpu())
            a, b = policy_kl(logits, old, reduce=False); kl_sum += a; kl_rows += b
        z = torch.cat(vl).numpy()
        y = np.array([r['label'] for r in meta['validation']], dtype=float)
        p = 1 / (1 + np.exp(-z))
        out['validation'] = {k: v for k, v in value.metric(y, p, np.ones(len(y)), z).items() if k != 'calibration'}
        out['policyTop1Agreement'] = float(torch.cat(agree).float().mean())
        out['policyKl'] = kl_sum / max(kl_rows, 1)
        leaves = meta['siblings']
        sv = []
        for i in range(0, stores['siblings'].n, ENCODE):
            ids = np.arange(i, min(i+ENCODE, stores['siblings'].n))
            sv.append(forward(net, stores['siblings'], ids, device)[1].double().cpu())
        sv = torch.cat(sv).numpy()
        rows = [{**r, 'model': float(s)} for r, s in zip(leaves, sv)]
        for name, train in (('siblingValidation', False), ('siblingTrain', True)):
            groups = sibling_groups(rows, train)
            out[name] = {'groups': len(groups), 'model': group_metrics(rows, groups, 'model')[0],
                         'x2b': group_metrics(rows, groups, 'x2b')[0], 'r0': group_metrics(rows, groups, 'r0')[0]}
    net.train()
    return out


def fit(args):
    arm, out, cache = args.arm, Path(args.out), Path(args.cache)
    value.require(arm in ARMS, 'unknown arm')
    out.mkdir(parents=True, exist_ok=False)
    value.require(os.environ.get('CUBLAS_WORKSPACE_CONFIG') == ':4096:8', 'CUBLAS configuration required')
    torch.set_num_threads(2); torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
    info = json.loads((cache/'cache.json').read_text())
    value.require(sha(cache/'meta.json') == info['metaSha256'] and sha(args.checkpoint) == info['checkpointSha256'],
                  'cache/checkpoint identity')
    meta = json.loads((cache/'meta.json').read_text())
    stores = {k: Store(cache/k) for k in ('train', 'validation', 'siblings')}
    device = 'cuda'
    _, ref = value.load_net(args, device)
    _, net = value.load_net(args, device)
    net.requires_grad_(True).train()
    labels = torch.tensor([r['label'] for r in meta['train']], dtype=torch.float32)
    rate = float(labels.mean())
    with torch.no_grad():
        net.value_head.bias.fill_(math.log(rate / (1-rate)))
    target = [r['target'] for r in meta['siblings']]
    train_groups = sibling_groups(meta['siblings'], True)
    weight = ARMS[arm]
    gen = torch.Generator().manual_seed(INIT); torch.manual_seed(INIT)
    opt = torch.optim.AdamW(net.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    write(out/'fit-started.json', {'arm': arm, 'rankWeight': weight, 'klWeight': KL_WEIGHT, 'lr': LR,
        'weightDecay': WEIGHT_DECAY, 'steps': STEPS, 'batch': BATCH, 'siblingLeaves': SIBLING_LEAVES,
        'init': INIT, 'trainRate': rate, 'cacheSha256': sha(cache/'cache.json'), 'toolSha256': sha(Path(__file__))})
    history, best, started = [], None, time.monotonic()
    record = {'step': 0, **evaluate(net, ref, stores, meta, device)}
    history.append(record); print(json.dumps(record), flush=True)
    order, cursor = torch.randperm(len(train_groups), generator=gen).tolist(), 0
    for step in range(1, STEPS+1):
        ids = np.sort(torch.randint(len(labels), (BATCH,), generator=gen).numpy())
        logits, v = forward(net, stores['train'], ids, device)
        with torch.no_grad():
            old, _ = forward(ref, stores['train'], ids, device)
        loss = F.binary_cross_entropy_with_logits(v, labels[ids].to(device)) + KL_WEIGHT * policy_kl(logits, old)
        rank = torch.zeros((), device=device)
        if weight:
            chosen = []
            while sum(map(len, chosen)) < SIBLING_LEAVES:
                if cursor == len(order):
                    order, cursor = torch.randperm(len(train_groups), generator=gen).tolist(), 0
                chosen.append(train_groups[order[cursor]]); cursor += 1
            leaf_ids = np.array([i for g in chosen for i in g])
            local, k = [], 0
            for g in chosen:
                local.append(list(range(k, k+len(g)))); k += len(g)
            _, sv = forward(net, stores['siblings'], leaf_ids, device)
            rank = rank_loss(sv, [target[i] for i in leaf_ids], local)
            loss = loss + weight * rank
        value.require(torch.isfinite(loss).item(), 'nonfinite loss')
        opt.zero_grad(set_to_none=True); loss.backward(); opt.step()
        if step % EVERY == 0:
            record = {'step': step, 'loss': float(loss), 'rank': float(rank), **evaluate(net, ref, stores, meta, device),
                      'seconds': time.monotonic()-started}
            history.append(record); print(json.dumps(record), flush=True)
            if best is None or record['validation']['bce'] < best['validation']['bce']:
                best = record
                torch.save({k: v.detach().cpu() for k, v in net.state_dict().items()}, out/'selected.pt')
    write(out/'history.json', history)
    write(out/'result.json', {'schema': 'arm-c-value-finetune-result-v1', 'arm': arm, 'selected': best,
        'step0': history[0], 'selectedSha256': sha(out/'selected.pt'), 'seconds': time.monotonic()-started,
        'selection': 'minimum VALIDATION visitation BCE over steps 100..2000', 'testRead': False})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('cache', 'fit'))
    p.add_argument('--import-root', type=Path, required=True)
    p.add_argument('--checkpoint', type=Path, required=True)
    p.add_argument('--silverbot', type=Path, required=True)
    p.add_argument('--siblings', type=Path)
    p.add_argument('--cache', type=Path)
    p.add_argument('--arm')
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    encode_cache(args) if args.command == 'cache' else fit(args)


if __name__ == '__main__':
    main()
