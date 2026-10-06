#!/usr/bin/env python3
"""Screen-aware OOC leaf v2: all seven DECISION screen families.

Extends the #379 typed public encoder (tools/screen_leaf_model_379.py) with
event and selector screens and keeps rewards. Trains the S1 arm (shared
encoder, one head per screen) on the frozen #334 TRAIN split with early
stopping on VALIDATION, then exports the native ensemble. Research only.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT)]
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
import numpy as np
import screen_leaf_data_379 as data379
import screen_leaf_model_379 as m379
from screen_leaf_model_379 import need, exact, integer, boolean, card, card_text, entity, group_array, EncodedState

SCREENS = ('boss_relic', 'rest', 'shop', 'treasure', 'rewards', 'event', 'selector')
ROLES = dict(m379.ROLES, neow_offer=9, event=10, selector_type=11, selector_card=12)
TARGETS = 9  # 0..5 from v1, 6 event option, 7 selector card, 8 selector candidate
CONTEXT_SCALE = [100., 5., 1., 1., 4., 5., 5.]  # remove cost, capacity, emerald, sapphire, chest, required, completed
RECIPE = dict(m379.RECIPE, seeds=[0, 1, 2])


def parse_option(key):
    m = re.fullmatch(r'ooc:v1:effect=(\d+):source=(\d+):(.*)', key)
    need(m is not None, 'semantic key schema mismatch')
    effect, source, tail = integer(int(m[1]), 0, 29), integer(int(m[2]), 0, 9), m[3]
    row = [effect, source, 0, 0, 0, 0, 0, -1, 0, 0, 0, 0, 0, -1]
    e = re.fullmatch(r'event=(\d+):option=(-?\d+)', tail)
    if e:
        row[2] = 6; row[12] = integer(int(e[1]), 0, 127); row[13] = integer(int(e[2]), -1, 127)
        return tuple(row), ()
    s = re.fullmatch(r'selector=(\d+):required=(\d+):completed=(\d+):(.*)', tail)
    if s:
        rest = s[4]
        c = re.fullmatch(r'candidate=(\d+),(-?\d+),([01]):occurrence=(\d+)', rest)
        if c:
            row[2:7] = [8, 1, integer(int(c[1]), 1, 511), integer(int(c[2])), int(c[3])]
            row[8] = integer(int(c[4]), 0, 65535)
        else:
            inner, _ = m379.parse_option(f'ooc:v1:effect={effect}:source={source}:' + rest)
            row = list(inner); row[2] = 7
        row[12] = integer(int(s[1]), 0, 127); row[13] = integer(int(s[3]), 0, 127)
        return tuple(row), ()
    return m379.parse_option(key)


def encode_state(base461, c, optionKeys):
    screen = c.get('screen')
    if screen in m379.SCREENS:
        # v1 encoder for the five original schemas; recompute rows with the v2 parser (identical there).
        state = m379.encode_state(base461, c, optionKeys)
        return EncodedState(state.base, SCREENS.index(screen), np.r_[state.context, 0., 0.].astype(np.float32),
                            state.entities, state.groups, state.group_counts, state.actions,
                            state.action_groups, state.action_group_counts)
    base = np.asarray(base461, dtype=np.float32)
    need(base.shape == (461,) and np.isfinite(base).all(), 'invalid base461 numeric input')
    need(screen in SCREENS, 'unsupported screen')
    context = [0.] * 7
    entities = []

    def add(role, kind, ident=0, misc=0, upgrade=0, price=0, slot=-1, present=1):
        entities.append((ROLES[role], m379.KINDS[kind], integer(ident, 0, 511), misc, upgrade, price, slot, present))

    if screen == 'event':
        need(set(c) <= {'screen', 'screenState', 'eventId', 'optionIds', 'neowOffers'}, 'event schema fields mismatch')
        add('event', 'none', integer(c['eventId'], 0, 127))
        for offer in c.get('neowOffers', []):
            exact(offer, ('bonusId', 'drawbackId'))
            add('neow_offer', 'none', integer(offer['bonusId'], 0, 511), misc=integer(offer['drawbackId'], 0, 511))
    else:
        exact(c, ('screen', 'screenState', 'cards', 'completedPicks', 'requiredPicks', 'selectorType', 'selectorTypeId'))
        add('selector_type', 'none', integer(c['selectorTypeId'], 0, 511))
        context[5] = integer(c['requiredPicks'], 0, 64); context[6] = integer(c['completedPicks'], 0, 64)
        for item in c['cards']:
            exact(item, ('card', 'deckIndex'))
            ident, misc, upgraded = card(item['card'])
            add('selector_card', 'card', ident, misc, upgraded, slot=integer(item['deckIndex'], -1, 4096))
    need(isinstance(optionKeys, (list, tuple)) and len(set(optionKeys)) == len(optionKeys), 'invalid option set')
    parsed = sorted(parse_option(k) for k in optionKeys)
    ag, agc = group_array([group for _, group in parsed])
    g, gc = group_array([])
    return EncodedState(base.copy(), SCREENS.index(screen), np.asarray(context, dtype=np.float32),
                        np.asarray(sorted(entities), dtype=np.float32).reshape(-1, 8), g, gc,
                        np.asarray([row for row, _ in parsed], dtype=np.float32).reshape(-1, 14), ag, agc)


def iter_rows(split):
    old = data379.PROVISIONAL_MASK
    data379.PROVISIONAL_MASK = SCREENS  # loader guards the frozen #379 mask; v2 covers every family
    try:
        yield from data379.DecisionCorpus().iter_rows(split, screens=SCREENS)
    finally:
        data379.PROVISIONAL_MASK = old


def load_split(split, cache):
    if cache.exists():
        z = np.load(cache, allow_pickle=False)
        packed = {k: z[k] for k in z.files if k not in ('labels', 'screens', 'sources')}
        return packed, z['labels'], z['screens'], z['sources']
    states, labels, screens, sources = [], [], [], []
    for row in iter_rows(split):
        states.append(encode_state(row['base461'], row['screenContents'], row['optionKeys']))
        labels.append(row['label']); screens.append(SCREENS.index(row['screen']))
        sources.append(row['identity']['sourceSeed'])
    packed = m379.pack_encoded(states)
    np.savez(cache, labels=np.asarray(labels, np.float32), screens=np.asarray(screens),
             sources=np.asarray(sources), **packed)
    return packed, np.asarray(labels, np.float32), np.asarray(screens), np.asarray(sources)


def build_model(normalization):
    import torch
    from torch import nn
    mean, scale = np.asarray(normalization['mean']), np.asarray(normalization['scale'])

    class ScreenModelV2(nn.Module):
        def __init__(self):
            super().__init__()
            self.register_buffer('mean', torch.tensor(mean, dtype=torch.float32))
            self.register_buffer('scale', torch.tensor(scale, dtype=torch.float32))
            self.ids = nn.Embedding(512, 8); self.kinds = nn.Embedding(6, 4)
            self.roles = nn.Embedding(len(ROLES), 4); self.effects = nn.Embedding(30, 4)
            self.sources = nn.Embedding(10, 3); self.targets = nn.Embedding(TARGETS, 3); self.events = nn.Embedding(128, 4)
            self.screens = nn.Embedding(len(SCREENS), 4)
            self.card_encoder = nn.Sequential(nn.Linear(10, 16), nn.GELU())
            self.group_encoder = nn.Sequential(nn.Linear(17, 16), nn.GELU())
            self.entity_encoder = nn.Sequential(nn.Linear(21, 16), nn.GELU())
            self.action_encoder = nn.Sequential(nn.Linear(50, 16), nn.GELU())
            self.trunk = nn.Sequential(nn.Linear(461 + 4 + 7 + 51, 64), nn.GELU(), nn.Dropout(.1), nn.Linear(64, 32), nn.GELU())
            self.head = nn.Linear(32, len(SCREENS))
        pool = staticmethod(lambda values, mask: torch.cat(((values * mask.unsqueeze(-1)).sum(-2) / mask.sum(-1, keepdim=True).clamp(min=1),
                                                             mask.sum(-1, keepdim=True).to(values.dtype) / 100.), -1))

        def groups_encoded(self, cards, counts):
            mask = torch.arange(4, device=cards.device) < counts.unsqueeze(-1)
            features = torch.cat((self.ids(cards[..., 0].long()), cards[..., 1:2] / 100., cards[..., 2:3]), -1)
            return self.group_encoder(self.pool(self.card_encoder(features), mask))

        def forward(self, b):
            e, a = b['entities'], b['actions']
            en = e[..., 3:] / e.new_tensor([100., 1., 100., 10., 1.])
            ev = self.entity_encoder(torch.cat((self.roles(e[..., 0].long()), self.kinds(e[..., 1].long()), self.ids(e[..., 2].long()), en), -1))
            av = self.action_encoder(torch.cat((self.effects(a[..., 0].long()), self.sources(a[..., 1].long()),
                self.targets(a[..., 2].long()), self.kinds(a[..., 3].long()), self.ids(a[..., 4].long()),
                a[..., 5:12] / a.new_tensor([100., 1., 3., 10., 100., 10., 1.]),
                self.events(a[..., 12].long()), a[..., 13:14] / 10.,
                self.groups_encoded(b['action_groups'], b['action_group_counts'])), -1))
            gv = self.groups_encoded(b['groups'], b['group_counts'])
            features = torch.cat(((b['base'] - self.mean) / self.scale, self.screens(b['screen']),
                b['context'] / b['context'].new_tensor(CONTEXT_SCALE),
                self.pool(ev, b['entities_mask']), self.pool(av, b['actions_mask']), self.pool(gv, b['groups_mask'])), -1)
            return self.head(self.trunk(features)).gather(1, b['screen'].unsqueeze(1)).squeeze(1)
    return ScreenModelV2()


def predict(model, cache, device, batch=8192):
    import torch
    model.eval(); out = []
    with torch.no_grad():
        for s in range(0, len(cache['base']), batch):
            out.append(torch.sigmoid(model(m379.cached_batch(cache, np.arange(s, min(s + batch, len(cache['base']))), device=device))).cpu().numpy())
    return np.concatenate(out)


def train(output, cache_root, device):
    import torch
    torch.use_deterministic_algorithms(True); torch.set_num_threads(4)
    output.mkdir(parents=True, exist_ok=False); cache_root.mkdir(parents=True, exist_ok=True)
    tr, y, tr_screens, _ = load_split('TRAIN', cache_root / 'TRAIN.npz')
    va, vy, va_screens, va_sources = load_split('VALIDATION', cache_root / 'VALIDATION.npz')
    print(json.dumps({'train_rows': len(y), 'validation_rows': len(vy)}), flush=True)
    norm = m379.fit_train_normalization(tr['base'], split='TRAIN')
    np.savez(output / 'normalization.npz', **norm)
    loss_fn = torch.nn.BCEWithLogitsLoss(); predictions = []
    for seed in RECIPE['seeds']:
        torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)
        model = build_model(norm).to(device)
        opt = torch.optim.AdamW(model.parameters(), lr=RECIPE['lr'], weight_decay=RECIPE['weight_decay'])
        gen = torch.Generator().manual_seed(seed); best, best_epoch, best_state = float('inf'), 0, None
        for epoch in range(1, RECIPE['max_epochs'] + 1):
            model.train(); order = torch.randperm(len(y), generator=gen).numpy()
            for off in range(0, len(order), RECIPE['batch_size']):
                ids = order[off:off + RECIPE['batch_size']]; opt.zero_grad(set_to_none=True)
                loss = loss_fn(model(m379.cached_batch(tr, ids, device=device)), torch.as_tensor(y[ids], device=device))
                loss.backward(); opt.step()
            p = np.clip(predict(model, va, device), 1e-7, 1 - 1e-7)
            score = float(-(vy * np.log(p) + (1 - vy) * np.log1p(-p)).mean())
            print(json.dumps({'seed': seed, 'epoch': epoch, 'validation_nll': score}), flush=True)
            if score < best:
                best, best_epoch = score, epoch
                best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            if epoch - best_epoch >= RECIPE['patience']: break
        torch.save(best_state, output / f'S1v2-seed{seed}.pt')
        model.load_state_dict(best_state); predictions.append(predict(model, va, device))
    mean = np.mean(predictions, axis=0, dtype=np.float64)
    np.save(output / 'S1v2-ensemble-validation.npy', mean)
    clip = np.clip(mean, 1e-7, 1 - 1e-7); nll = -(vy * np.log(clip) + (1 - vy) * np.log1p(-clip))
    report = {'overall_nll': float(nll.mean()), 'by_screen': {s: float(nll[va_screens == i].mean()) for i, s in enumerate(SCREENS)},
              'rows_by_screen': {s: int((va_screens == i).sum()) for i, s in enumerate(SCREENS)}}
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n'); print(json.dumps(report), flush=True)


ORDER = ['mean', 'scale', 'ids.weight', 'kinds.weight', 'roles.weight', 'effects.weight', 'sources.weight',
         'targets.weight', 'events.weight', 'screens.weight', 'card_encoder.0.weight', 'card_encoder.0.bias',
         'group_encoder.0.weight', 'group_encoder.0.bias', 'entity_encoder.0.weight', 'entity_encoder.0.bias',
         'action_encoder.0.weight', 'action_encoder.0.bias', 'trunk.0.weight', 'trunk.0.bias',
         'trunk.3.weight', 'trunk.3.bias', 'head.weight', 'head.bias']


def export(output, model_path, parity_path, parity_rows):
    import hashlib
    import torch
    full = json.loads(Path(data379.DecisionCorpus().components[0]['manifest']).read_text())['stateFeatures']['header'].split(',')
    names = data379.DecisionCorpus().feature_names
    lines = ['screen-leaf-native-v2', 'arm S1', 'screens ' + ' '.join(SCREENS),
             'indices ' + ' '.join(str(full.index(n)) for n in names)]
    states = []
    for seed in RECIPE['seeds']:
        path = output / f'S1v2-seed{seed}.pt'; state = torch.load(path, map_location='cpu', weights_only=True); states.append(state)
        lines.append(f'seed {seed} {hashlib.sha256(path.read_bytes()).hexdigest()}')
        for name in ORDER:
            t = state[name].numpy().astype(np.float64)
            lines.append(f'{name} {t.ndim} ' + ' '.join(map(str, t.shape)) + ' ' + ' '.join(repr(float(x)) for x in t.ravel()))
    model_path.write_text('\n'.join(lines) + '\nend\n')
    norm = np.load(output / 'normalization.npz')
    models = []
    for state in states:
        m = build_model({'mean': norm['mean'], 'scale': norm['scale']}); m.load_state_dict(state); models.append(m)
    by_screen = {s: [] for s in SCREENS}
    for row in iter_rows('VALIDATION'):
        bucket = by_screen[row['screen']]
        if len(bucket) < parity_rows // len(SCREENS): bucket.append(row)
        if all(len(v) >= parity_rows // len(SCREENS) for v in by_screen.values()): break
    rows = [r for v in by_screen.values() for r in v]
    cache = m379.pack_encoded([encode_state(r['base461'], r['screenContents'], r['optionKeys']) for r in rows])
    p = np.mean([predict(m, cache, 'cpu') for m in models], axis=0, dtype=np.float64)
    with parity_path.open('w') as f:
        for r, v in zip(rows, p):
            f.write(json.dumps({'base': r['base461'], 'screenContents': r['screenContents'],
                                'candidateKeys': r['optionKeys'], 'python': float(v)}) + '\n')
    print(model_path, len(rows))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    t = sub.add_parser('train'); t.add_argument('--output', type=Path, required=True)
    t.add_argument('--cache-root', type=Path, required=True); t.add_argument('--device', default='cuda')
    e = sub.add_parser('export'); e.add_argument('--output', type=Path, required=True)
    e.add_argument('--model', type=Path, required=True); e.add_argument('--parity', type=Path, required=True)
    e.add_argument('--parity-rows', type=int, default=1400)
    a = ap.parse_args()
    if a.cmd == 'train': train(a.output.resolve(), a.cache_root.resolve(), a.device)
    else: export(a.output.resolve(), a.model.resolve(), a.parity.resolve(), a.parity_rows)
