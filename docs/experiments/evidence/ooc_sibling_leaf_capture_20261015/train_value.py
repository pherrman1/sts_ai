"""Small value net on captured sibling leaves: target T = mean of the repeat rollout3 evaluations.
Inputs: heart1 record of the leaf (deck, relics, potions, offers, fixed observation, map rooms ahead, screen)
plus optionally X2-B. Validation: held-out seeds (seed % MOD == MOD-1). Scores the val leaves with the within-parent
signal analysis of sib_signal.py (disattenuated corr with E[rollout3]) next to r0 / x2b / heart1.
usage: train_value.py OUT.json [--x2b] [--epochs N] FILES..."""
import argparse, json, math, random, sys, os, collections
import torch, torch.nn as nn
sys.path.insert(0, os.path.dirname(__file__))
from sib_signal import analyse
ap = argparse.ArgumentParser(); ap.add_argument('out'); ap.add_argument('files', nargs='+')
ap.add_argument('--x2b', action='store_true'); ap.add_argument('--epochs', type=int, default=30)
ap.add_argument('--mod', type=int, default=4); ap.add_argument('--within', action='store_true'); ap.add_argument('--target', default='T')
a = ap.parse_args(); torch.manual_seed(0); random.seed(0); torch.set_num_threads(4)

def feats(rec, row):
    fo = rec['obs.fixed_observation']; y0 = rec['obs.mapY']
    ahead = [0.0] * 8
    for y, t in zip(rec['obs.map.ys'], rec['obs.map.roomTypes']):
        if y > y0 and 0 <= t < 8: ahead[t] += 1
    dense = [x / 100 for x in fo] + [v / 20 for v in ahead] + [y0 / 15, row['act'] / 3, row['floor'] / 50,
             len(rec['obs.deck.cards']) / 30, sum(rec['obs.deck.upgrades']) / 10, len(rec['fixed_actions']) / 5,
             len(rec['paths_offered']) / 7]
    scr = [0.0] * 9; scr[min(rec['screen_state'], 8)] = 1
    sel = [0.0] * 16; sel[min(rec['select_screen_type'], 15)] = 1
    deck = [c * 2 + u for c, u in zip(rec['obs.deck.cards'], rec['obs.deck.upgrades'])]
    off = [c * 2 + u for c, u in zip(rec['cards_offered.cards'], rec['cards_offered.upgrades'])]
    return dense + scr + sel, deck, rec['obs.relics.relics'], rec['obs.potions'], off, rec['relics_offered'], rec['potions_offered']

rows = []
for p in a.files:
    for line in open(p):
        r = json.loads(line); e = r.get('extra', {})
        reps = [x['value'] for x in e.get('repeats', []) if 'value' in x]
        ann = e.get('annotation', {})
        if len(reps) < 2 or len(reps) != len(e['repeats']) or 'record' not in ann or 'x2b' not in e: continue
        m = sum(reps) / len(reps); se = (sum((x - m) ** 2 for x in reps) / (len(reps) - 1) / len(reps)) ** 0.5
        l5 = [x['value'] for x in e.get('long5', []) if 'value' in x]
        c = {'T': m, 'Tse': se, 'r0': r['value'], 'x2b': e['x2b'], 'heart1': ann['value']}
        if l5: c['l5'] = sum(l5) / len(l5)
        rows.append({'key': (r['seed'], r['decision'], r['parent']), 'action': r['action'], 'screen': r['parentScreen'],
                     'depth': r['depth'], 'c': c, 'f': feats(ann['record'], r), 'seed': r['seed']})
train = [r for r in rows if r['seed'] % a.mod != a.mod - 1]; val = [r for r in rows if r['seed'] % a.mod == a.mod - 1]
print(f"rows {len(rows)} train {len(train)} val {len(val)}", flush=True)
ND = len(rows[0]['f'][0]) + (1 if a.x2b else 0)

class Net(nn.Module):
    def __init__(s, d=64):
        super().__init__()
        s.deck = nn.EmbeddingBag(1024, d, mode='sum'); s.rel = nn.EmbeddingBag(256, d, mode='sum')
        s.pot = nn.EmbeddingBag(64, d, mode='sum'); s.off = nn.EmbeddingBag(1024, d, mode='sum')
        s.roff = nn.EmbeddingBag(256, d, mode='sum'); s.poff = nn.EmbeddingBag(64, d, mode='sum')
        s.mlp = nn.Sequential(nn.Linear(ND + 6 * d, 256), nn.ReLU(), nn.Linear(256, 256), nn.ReLU(), nn.Linear(256, 1))
    def forward(s, dense, bags):
        parts = [dense] + [m(i, o) for m, (i, o) in zip([s.deck, s.rel, s.pot, s.off, s.roff, s.poff], bags)]
        return s.mlp(torch.cat(parts, 1)).squeeze(1)

def batch(rs):
    dense = torch.tensor([r['f'][0] + ([math.log(max(r['c']['x2b'], 1e-4) / max(1 - r['c']['x2b'], 1e-4))] if a.x2b else []) for r in rs])
    bags = []
    for j in range(1, 7):
        idx, offs = [], []
        for r in rs: offs.append(len(idx)); idx += r['f'][j]
        bags.append((torch.tensor(idx, dtype=torch.long), torch.tensor(offs, dtype=torch.long)))
    return dense, bags, torch.tensor([r['c'][a.target] for r in rs])

net = Net(); opt = torch.optim.AdamW(net.parameters(), 1e-3, weight_decay=1e-4)
vb = batch(val)
def predict(rs):
    net.eval(); out = []
    with torch.no_grad():
        for i in range(0, len(rs), 4096):
            d, b, _ = batch(rs[i:i + 4096]); out += torch.sigmoid(net(d, b)).tolist()
    net.train(); return out
best = None
groups = collections.defaultdict(list)
for r in train: groups[r['key']].append(r)
glist = [g for g in groups.values() if len(g) >= 2]
for ep in range(a.epochs):
    tot = 0
    if a.within:
        random.shuffle(glist); chunk = []
        for gi, g in enumerate(glist):
            chunk.append(g)
            if sum(len(x) for x in chunk) < 512 and gi + 1 < len(glist): continue
            rs = [r for x in chunk for r in x]; d, b, y = batch(rs); p = torch.sigmoid(net(d, b))
            gid = torch.tensor([k for k, x in enumerate(chunk) for _ in x])
            n = torch.bincount(gid).float()
            pm = torch.zeros(len(chunk)).index_add_(0, gid, p) / n; ym = torch.zeros(len(chunk)).index_add_(0, gid, y) / n
            loss = (((p - pm[gid]) - (y - ym[gid])) ** 2).mean() + 0.1 * ((p - y) ** 2).mean()
            opt.zero_grad(); loss.backward(); opt.step(); tot += loss.item() * len(y); chunk = []
    else:
      random.shuffle(train)
      for i in range(0, len(train), 256):
        d, b, y = batch(train[i:i + 256]); p = torch.sigmoid(net(d, b))
        loss = ((p - y) ** 2).mean(); opt.zero_grad(); loss.backward(); opt.step(); tot += loss.item() * len(y)
    pv = predict(val); vm = sum((p - r['c'][a.target]) ** 2 for p, r in zip(pv, val)) / len(val)
    for p, r in zip(pv, val): r['c']['net'] = p
    res = analyse(val, ['r0', 'x2b', 'heart1', 'net'])
    print(f"ep {ep+1} train mse {tot/len(train):.5f} val mse {vm:.5f} | corrE r0 {res['r0']['corrWithExpected']:.3f} x2b {res['x2b']['corrWithExpected']:.3f} heart1 {res['heart1']['corrWithExpected']:.3f} net {res['net']['corrWithExpected']:.3f}", flush=True)
    score = -res['net']['corrWithExpected']
    if best is None or score < best[0]:
        best = (score, ep + 1, res, {s: analyse([r for r in val if r['screen'] == s], ['r0', 'x2b', 'heart1', 'net']) for s in sorted({r['screen'] for r in val})})
        torch.save(net.state_dict(), a.out + '.pt')
json.dump({'args': vars(a), 'rows': len(rows), 'train': len(train), 'val': len(val), 'bestValCorr': -best[0], 'bestEpoch': best[1],
           'all': best[2], 'byParentScreen': {str(k): v for k, v in best[3].items()}}, open(a.out, 'w'), indent=1)
