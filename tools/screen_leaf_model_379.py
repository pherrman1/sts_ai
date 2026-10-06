"""Provisional #379 typed public-state encoder and matched S1/S2 torch arms.

No data IO, training loop or TEST access. Input is ONLY base461, public screen
contents and the complete public option set. Identity, label, chosen action and
replay/RNG fields are deliberately not accepted. Reward encoding is implemented
for schema tests but rewards is excluded from the provisional replacement mask.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import re
import numpy as np

SCREENS = ('boss_relic', 'rest', 'shop', 'treasure', 'rewards')
PROVISIONAL_MASK = SCREENS[:4]
SCREEN_IDS = {'boss_relic': 3, 'rest': 7, 'shop': 8, 'treasure': 6, 'rewards': 2}
BASE_ORDER_SHA256 = '7fb54594d218a086c36874c27410873830231244ad4341c949c88a41a929033b'
RECIPE = {'widths': [64, 32], 'activation': 'GELU', 'dropout': .1,
          'optimizer': 'AdamW', 'lr': 1e-4, 'weight_decay': 1e-3,
          'batch_size': 8192, 'max_epochs': 60, 'patience': 8, 'seeds': [0, 1, 2]}
CONTRACT = 'screen-leaf-typed-public-v1'
BASE_INDEX = {'gold': 4, 'potionCount': 10, 'potionCapacity': 11, 'r64': 322}
SHOP_DISCARD_RULE = 'current-main-public-full-belt-affordable-offer-without-Sozu-v1'
# Entity roles distinguish independently observable collections, never row IDs.
ROLES = {'shop_card': 0, 'shop_relic': 1, 'shop_potion': 2, 'buyable_relic': 3,
         'held_potion': 4, 'boss_relic': 5, 'reward_relic': 6, 'reward_potion': 7,
         'reward_gold': 8}
KINDS = {'none': 0, 'card': 1, 'relic': 2, 'potion': 3, 'gold': 4, 'key': 5}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def exact(value, names):
    need(isinstance(value, dict) and set(value) == set(names), 'public schema fields mismatch')


def integer(x, lo=-32768, hi=2147483647):
    need(type(x) is int and lo <= x <= hi, 'invalid public integer')
    return x


def boolean(x):
    need(type(x) is bool, 'invalid public boolean')
    return int(x)


def verify_feature_names(names):
    names = list(names)
    need(len(names) == 461 and len(set(names)) == 461, 'base461 width/duplicates')
    need(hashlib.sha256(json.dumps(names, separators=(',', ':')).encode()).hexdigest()
         == BASE_ORDER_SHA256, 'X2-B base feature ordering differs')
    need(all(names[index] == name for name, index in BASE_INDEX.items()), 'public legality feature identity differs')
    return tuple(names)


def card(value):
    exact(value, ('id', 'upgraded', 'misc'))
    return (integer(value['id'], 1, 511), integer(value['misc']), boolean(value['upgraded']))


def card_text(text):
    need(re.fullmatch(r'\d+,-?\d+,[01]', text) is not None, 'invalid semantic card')
    a, b, c = map(int, text.split(','))
    return (integer(a, 1, 511), integer(b), integer(c, 0, 1))


def entity(text):
    parts = text.split(',')
    if parts == ['none']:
        return (0, 0, 0, 0)
    need(parts[0] in KINDS, 'unknown semantic entity')
    if parts[0] == 'card':
        a, b, c = card_text(','.join(parts[1:])); return (1, a, b, c)
    need(len(parts) == 2 and re.fullmatch(r'\d+', parts[1]), 'invalid semantic entity')
    value = int(parts[1])
    if parts[0] == 'gold':
        return (4, 0, integer(value, 0), 0)  # numeric quantity, not categorical ID
    return (KINDS[parts[0]], integer(value, 0, 511), 0, 0)


def parse_option(key):
    """Decode only public targets emitted for the five supported screen schemas.

    All token text is parsed/validated then discarded. No string hashing or
    vocabulary fitted on outcomes. Target group structure stays attached to its
    action. Event and selector targets fail closed in this provisional encoder.
    """
    need(isinstance(key, str), 'option key must be string')
    m = re.fullmatch(r'ooc:v1:effect=(\d+):source=(\d+):(.*)', key)
    need(m is not None, 'semantic key schema mismatch')
    effect, source = integer(int(m[1]), 0, 29), integer(int(m[2]), 0, 9)
    tail = m[3]
    # effect,source,target-kind,entity-kind,entity-id,misc,upgrade,bottle,
    # occurrence,price,group-occurrence,sapphire-paired,event-id,event-option
    row = [effect, source, 0, 0, 0, 0, 0, -1, 0, 0, 0, 0, 0, -1]
    group = []
    if tail == 'none':
        return tuple(row), tuple(group)
    m = re.fullmatch(r'card=(\d+):misc=(-?\d+):upgraded=([01]):bottle=(-?\d+):occurrence=(\d+)', tail)
    if m:
        row[2:9] = [1, 1, integer(int(m[1]), 1, 511), integer(int(m[2])), int(m[3]),
                    integer(int(m[4]), -1, 2), integer(int(m[5]), 0, 65535)]
        return tuple(row), tuple(group)
    m = re.fullmatch(r'transaction:event=(\d+):option=(-?\d+):cost=(\d+):(card=.*)', tail)
    if m:
        original, group = parse_option(f'ooc:v1:effect={effect}:source={source}:' + m[4])
        row = list(original); row[2] = 5
        row[12] = integer(int(m[1]), 0, 127); row[13] = integer(int(m[2]), -1, 127)
        row[9] = integer(int(m[3]), 0)
        return tuple(row), group
    m = re.fullmatch(r'shop=(.*):price=(-?\d+):occurrence=(\d+)', tail)
    if m:
        row[2] = 2; row[3:7] = entity(m[1]); row[9] = integer(int(m[2]), -1)
        row[8] = integer(int(m[3]), 0, 65535)
        return tuple(row), tuple(group)
    m = re.fullmatch(r'relic=(\d+):occurrence=(\d+)', tail)
    if m:
        row[2:5] = [3, 2, integer(int(m[1]), 0, 511)]
        row[8] = integer(int(m[2]), 0, 65535)
        return tuple(row), tuple(group)
    m = re.fullmatch(r'reward=(.*):group=\[(.*)\]:groupOccurrence=(\d+):occurrence=(\d+):sapphirePaired=([01])', tail)
    if m:
        row[2] = 4; row[3:7] = entity(m[1])
        if m[2]:
            need(m[2].endswith(';'), 'noncanonical reward group')
            group = sorted(card_text(x) for x in m[2][:-1].split(';'))
        need(len(group) <= 4, 'reward group exceeds native capacity')
        row[10] = integer(int(m[3]), 0, 65535); row[8] = integer(int(m[4]), 0, 65535)
        row[11] = int(m[5]); return tuple(row), tuple(group)
    raise ValueError('unsupported public option target')


def canonical_shop_options(base, contents, option_keys):
    """Reconcile frozen pre-discard and current legal public option sets.

    Uses only gold, potion count/capacity, public Sozu ownership (r64), visible
    potion offers and held potions. Existing non-discard actions are untouched.
    Historical empty discard set is augmented; a supplied nonempty discard set
    must already match the complete current set, otherwise fail closed.
    """
    values = {name: float(base[index]) for name, index in BASE_INDEX.items()}
    need(all(v.is_integer() and v >= 0 for v in values.values()), 'invalid public shop legality values')
    capacity, count = int(values['potionCapacity']), int(values['potionCount'])
    need(capacity == contents['ownedPotionCapacity'] and 0 <= count <= capacity <= 5,
         'shop/base potion capacity differs')
    expected = set()
    affordable = any(p['price'] >= 0 and p['price'] <= values['gold'] for p in contents['potionSlots'])
    if capacity and count >= capacity and not values['r64'] and affordable:
        occurrences = {}
        for potion in contents['ownedPotions']:
            if potion in (0, 1):
                continue  # INVALID, EMPTY_POTION_SLOT, exactly as native enumeration.
            occurrence = occurrences.get(potion, 0); occurrences[potion] = occurrence + 1
            expected.add(f'ooc:v1:effect=29:source=3:reward=potion,{potion}:group=[]:'
                         f'groupOccurrence=0:occurrence={occurrence}:sapphirePaired=0')
    provided = {k for k in option_keys if parse_option(k)[0][0] == 29}
    need(not provided or provided == expected, 'partial/invalid provided shop discard set')
    return sorted(set(option_keys) | expected)


@dataclass(frozen=True)
class EncodedState:
    base: np.ndarray
    screen: int
    context: np.ndarray
    entities: np.ndarray
    groups: np.ndarray
    group_counts: np.ndarray
    actions: np.ndarray
    action_groups: np.ndarray
    action_group_counts: np.ndarray


def group_array(groups):
    out = np.zeros((len(groups), 4, 3), dtype=np.float32)
    counts = np.array([len(g) for g in groups], dtype=np.int64)
    need(all(0 <= n <= 4 for n in counts), 'invalid card group size')
    for i, group in enumerate(groups):
        if group:
            out[i, :len(group)] = group
    return out, counts


def encode_state(base461, screenContents, optionKeys):
    base = np.asarray(base461, dtype=np.float32)
    need(base.shape == (461,) and np.isfinite(base).all(), 'invalid base461 numeric input')
    c = screenContents
    need(isinstance(c, dict) and c.get('screen') in SCREENS, 'unsupported screen')
    screen = c['screen']
    need(c.get('screenState') == SCREEN_IDS[screen], 'screen ID differs')
    need(isinstance(optionKeys, (list, tuple)) and all(isinstance(k, str) for k in optionKeys), 'invalid option set')
    need(len(set(optionKeys)) == len(optionKeys), 'duplicate option key')
    parsed = sorted(parse_option(k) for k in optionKeys)
    allowed_sources = {'boss_relic': {9}, 'rest': {0, 1, 2}, 'shop': {3, 4}, 'treasure': {8}, 'rewards': {7}}
    need(all(row[1] in allowed_sources[screen] for row, _ in parsed), 'option source differs from screen')
    context = [0., 0., 0., 0., 0.]  # remove cost, capacity, emerald, sapphire, chest size
    entities, groups = [], []

    def add(role, kind, ident=0, misc=0, upgrade=0, price=0, slot=-1, present=1):
        # role, kind, ID, misc, upgrade, price, slot, present
        entities.append((ROLES[role], KINDS[kind], integer(ident, 0, 511), misc, upgrade, price, slot, present))

    if screen == 'boss_relic':
        exact(c, ('screen', 'screenState', 'relics'))
        for value in c['relics']: add('boss_relic', 'relic', integer(value, 0, 511))
    elif screen in ('rest', 'treasure'):
        exact(c, ('screen', 'screenState', 'availableOptions') + (('chestSize',) if screen == 'treasure' else ()))
        visible = []
        for item in c['availableOptions']:
            exact(item, ('key', 'effect', 'source'))
            row, _ = parse_option(item['key'])
            need(row[:2] == (item['effect'], item['source']), 'option metadata differs')
            visible.append(item['key'])
        need(sorted(visible) == sorted(optionKeys), 'visible option set differs')
        if screen == 'treasure': context[4] = integer(c['chestSize'], 0, 8)
    elif screen == 'shop':
        exact(c, ('screen', 'screenState', 'cards', 'relics', 'potionSlots', 'removeCost',
                  'policyBuyableRelics', 'ownedPotionCapacity', 'ownedPotions'))
        context[0] = integer(c['removeCost'], -1); context[1] = integer(c['ownedPotionCapacity'], 0, 5)
        need(len(c['ownedPotions']) == context[1], 'held potion capacity differs')
        for value in c['ownedPotions']: add('held_potion', 'potion', integer(value, 0, 511))
        for field, role, kind, size in (('cards', 'shop_card', 'card', 7), ('relics', 'shop_relic', 'relic', 3),
                                         ('potionSlots', 'shop_potion', 'potion', 3)):
            need(len(c[field]) == size, 'shop slot count differs')
            seen = set()
            for item in c[field]:
                exact(item, ('slot', 'id', 'price') + (('card',) if kind == 'card' else ()))
                slot = integer(item['slot'], 0, size - 1); need(slot not in seen, 'duplicate shop slot'); seen.add(slot)
                price = integer(item['price'], -1)
                if price < 0:
                    need(item['id'] is None and (kind != 'card' or item['card'] is None), 'sold slot leaks entity')
                    add(role, kind, price=price, slot=slot, present=0)
                elif kind == 'card':
                    ident, misc, upgraded = card(item['card']); need(item['id'] == ident, 'card identity differs')
                    add(role, kind, ident, misc, upgraded, price, slot)
                else: add(role, kind, integer(item['id'], 0, 511), price=price, slot=slot)
        for item in c['policyBuyableRelics']:
            exact(item, ('id', 'price', 'key')); need(item['key'] in optionKeys, 'buyable relic absent from options')
            row, _ = parse_option(item['key'])
            need(row[0] == 23 and row[2:5] == (2, 2, item['id']) and row[9] == item['price'], 'buyable relic key differs')
            add('buyable_relic', 'relic', integer(item['id'], 0, 511), price=integer(item['price'], 0))
    else:
        exact(c, ('screen', 'screenState', 'gold', 'cardRewards', 'relics', 'potions', 'emeraldKey', 'sapphireKey'))
        context[2], context[3] = boolean(c['emeraldKey']), boolean(c['sapphireKey'])
        for value in c['gold']: add('reward_gold', 'gold', misc=integer(value, 0))
        for value in c['relics']: add('reward_relic', 'relic', integer(value, 0, 511))
        for value in c['potions']: add('reward_potion', 'potion', integer(value, 0, 511))
        group_ids = []
        for item in c['cardRewards']:
            exact(item, ('group', 'cards')); group_ids.append(integer(item['group'], 0, 4))
            groups.append(tuple(sorted(card(x) for x in item['cards'])))
        need(sorted(group_ids) == list(range(len(group_ids))), 'reward group identity differs')
        groups.sort()  # whole groups form a multiset, never flattened into one card pool
    if screen == 'shop':
        optionKeys = canonical_shop_options(base, c, optionKeys)
        parsed = sorted(parse_option(k) for k in optionKeys)
    g, gc = group_array(groups)
    ag, agc = group_array([group for _, group in parsed])
    return EncodedState(base.copy(), SCREENS.index(screen), np.asarray(context, dtype=np.float32),
                        np.asarray(sorted(entities), dtype=np.float32).reshape(-1, 8), g, gc,
                        np.asarray([row for row, _ in parsed], dtype=np.float32).reshape(-1, 14), ag, agc)


def fit_train_normalization(base, *, split):
    need(split == 'TRAIN', 'normalization requires TRAIN only')
    x = np.asarray(base, dtype=np.float64)
    need(x.ndim == 2 and x.shape[1] == 461 and len(x) > 0 and np.isfinite(x).all(), 'invalid normalization data')
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale < 1e-8] = 1.
    return {'mean': mean.astype(np.float32), 'scale': scale.astype(np.float32)}


def pack_encoded(states):
    """Flat numeric cache; no object arrays, labels, identities or chosen fields."""
    states = list(states); need(bool(states), 'empty encoded cache')
    out = {'base': np.stack([s.base for s in states]), 'screen': np.array([s.screen for s in states], dtype=np.int64),
           'context': np.stack([s.context for s in states])}
    for name in ('entities', 'groups', 'actions'):
        lengths = np.array([len(getattr(s, name)) for s in states], dtype=np.int64)
        out[name + '_offsets'] = np.r_[0, lengths.cumsum()]
        out[name] = np.concatenate([getattr(s, name) for s in states])
    out['group_counts'] = np.concatenate([s.group_counts for s in states])
    out['action_groups'] = np.concatenate([s.action_groups for s in states])
    out['action_group_counts'] = np.concatenate([s.action_group_counts for s in states])
    return out


def cached_batch(cache, indices, *, device='cpu'):
    import torch
    indices = np.asarray(indices, dtype=np.int64)
    need(indices.ndim == 1 and len(indices) > 0 and (indices >= 0).all() and (indices < len(cache['base'])).all(), 'empty/invalid batch indices')
    out = {k: torch.as_tensor(cache[k][indices], device=device) for k in ('base', 'screen', 'context')}
    for name in ('entities', 'groups', 'actions'):
        offsets = cache[name + '_offsets']; lengths = offsets[indices + 1] - offsets[indices]
        width = max(1, int(lengths.max()))
        values = np.zeros((len(indices), width) + cache[name].shape[1:], dtype=np.float32)
        mask = np.arange(width)[None, :] < lengths[:, None]
        auxiliary = ('group_counts',) if name == 'groups' else ('action_groups', 'action_group_counts') if name == 'actions' else ()
        aux = {key: np.zeros((len(indices), width) + cache[key].shape[1:], dtype=cache[key].dtype) for key in auxiliary}
        for i, row in enumerate(indices):
            sl = slice(offsets[row], offsets[row + 1]); n = lengths[i]
            values[i, :n] = cache[name][sl]
            for key in auxiliary: aux[key][i, :n] = cache[key][sl]
        out[name] = torch.as_tensor(values, device=device); out[name + '_mask'] = torch.as_tensor(mask, device=device)
        out.update({key: torch.as_tensor(value, device=device) for key, value in aux.items()})
    return out


def collate_encoded(states, *, device='cpu'):
    states = list(states)
    return cached_batch(pack_encoded(states), np.arange(len(states)), device=device)


def build_model(arm, normalization, *, replacement_mask=PROVISIONAL_MASK):
    """S1/S2 differ only in final head count; identical initialized encoder shape.

    A head is Linear(32,1). S1 selects by screen; S2 shares one. Both arms expose
    screen embedding to the same trunk and output BCE logits (no clipping).
    """
    import torch
    from torch import nn
    need(arm in ('S1', 'S2'), 'unknown arm')
    need(tuple(replacement_mask) and set(replacement_mask) <= set(PROVISIONAL_MASK), 'unqualified replacement mask')
    mean, scale = np.asarray(normalization['mean']), np.asarray(normalization['scale'])
    need(mean.shape == scale.shape == (461,) and np.isfinite(mean).all() and np.isfinite(scale).all() and (scale > 0).all(), 'invalid normalization')

    class ScreenModel(nn.Module):
        def __init__(self):
            super().__init__(); self.arm = arm; self.replacement_mask = tuple(replacement_mask)
            self.register_buffer('mean', torch.tensor(mean, dtype=torch.float32))
            self.register_buffer('scale', torch.tensor(scale, dtype=torch.float32))
            self.ids = nn.Embedding(512, 8); self.kinds = nn.Embedding(6, 4)
            self.roles = nn.Embedding(9, 4); self.effects = nn.Embedding(30, 4)
            self.sources = nn.Embedding(10, 3); self.targets = nn.Embedding(6, 3); self.events = nn.Embedding(128, 4)
            self.screens = nn.Embedding(len(SCREENS), 4)
            self.card_encoder = nn.Sequential(nn.Linear(10, 16), nn.GELU())
            self.group_encoder = nn.Sequential(nn.Linear(17, 16), nn.GELU())
            self.entity_encoder = nn.Sequential(nn.Linear(21, 16), nn.GELU())
            self.action_encoder = nn.Sequential(nn.Linear(50, 16), nn.GELU())
            self.trunk = nn.Sequential(nn.Linear(521, 64), nn.GELU(), nn.Dropout(.1), nn.Linear(64, 32), nn.GELU())
            self.head = nn.Linear(32, len(replacement_mask) if arm == 'S1' else 1)
            self.register_buffer('head_index', torch.tensor([replacement_mask.index(s) if s in replacement_mask else -1 for s in SCREENS]))

        @staticmethod
        def pool(values, mask):
            n = mask.sum(-1, keepdim=True)
            summed = (values * mask.unsqueeze(-1)).sum(-2)
            return torch.cat((summed / n.clamp(min=1), n.to(values.dtype) / 100.), -1)

        def groups_encoded(self, cards, counts):
            mask = torch.arange(4, device=cards.device) < counts.unsqueeze(-1)
            features = torch.cat((self.ids(cards[..., 0].long()), cards[..., 1:2] / 100., cards[..., 2:3]), -1)
            return self.group_encoder(self.pool(self.card_encoder(features), mask))

        def forward(self, b):
            head_index = self.head_index[b['screen']]
            if torch.any(head_index < 0):
                raise ValueError('screen outside frozen replacement mask')
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
                b['context'] / b['context'].new_tensor([100., 5., 1., 1., 4.]),
                self.pool(ev, b['entities_mask']), self.pool(av, b['actions_mask']), self.pool(gv, b['groups_mask'])), -1)
            logits = self.head(self.trunk(features))
            return logits.gather(1, head_index.unsqueeze(1)).squeeze(1) if self.arm == 'S1' else logits.squeeze(1)
    return ScreenModel()
