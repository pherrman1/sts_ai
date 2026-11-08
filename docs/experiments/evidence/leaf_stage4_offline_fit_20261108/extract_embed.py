#!/usr/bin/env python3
"""Leaf pilot interim training, step 1: unit tars -> per-copy meta + frozen net-0420 trunk embeddings.

usage: extract_embed.py SNAP_DIR NET.bin OUT_PREFIX
Unit validity as analyze.py: rc=0 and 8 source rows; the first tar per unit id. Only copy rows with a valid outcome.
Writes OUT_PREFIX.meta.jsonl (one line per copy, same order as the arrays) and OUT_PREFIX.npz with
pooled (N, 256) float32 (net-0420 value-head-normed mean over tokens, the input of its value head) and value (N,).
"""
import gzip, io, json, os, re, sys, tarfile, time
import numpy as np
import torch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..', 'tools', 'heart1'))
import ppo_model as pm  # noqa: E402

snap, net_path, out = sys.argv[1:4]
torch.set_num_threads(4)
net = pm.PolicyNet.from_bin(net_path).eval()


def family(v):
    return 'pot' if v.startswith('pot:') else v


metas, recs, seen = [], [], set()
n_units = 0
for name in sorted(os.listdir(snap)):
    m = re.fullmatch(r'(\d+)\.w\d+\.tar', name)
    if not m or m.group(1) in seen:
        continue
    uid = m.group(1); seen.add(uid)
    with tarfile.open(os.path.join(snap, name)) as t:
        files = {x.name: x for x in t.getmembers() if x.isfile()}
        res = [n for n in files if n.endswith(f'/{uid}/result.txt')]
        jl = [n for n in files if n.endswith('.jsonl.gz') and f'/{uid}/' in n]
        if len(res) != 1 or len(jl) != 1 or 'rc=0 ' not in t.extractfile(files[res[0]]).read().decode() + ' ':
            continue
        rows = [json.loads(l) for l in gzip.open(io.BytesIO(t.extractfile(files[jl[0]]).read()), 'rt')]
    if sum(r['kind'] == 'source' for r in rows) != 8:
        continue
    n_units += 1
    for r in rows:
        if r['kind'] != 'copy' or not r['outcome']['valid']:
            continue
        lf, st, oc = r['leaf'], r['state'], r['outcome']
        metas.append({
            'unit': int(uid), 'seed': r['seed'], 'fork': r['fork'], 'variant': r['variant'],
            'family': family(r['variant']), 'act': r['act'], 'floor': r['floor'], 'room': r['room'],
            'encounter': r['encounter'], 'fightIndex': r['fightIndex'],
            'y': float(oc['heartKill']), 'finalFloor': float(oc['finalFloor']),
            'hp': lf['hp'], 'maxHp': lf['maxHp'], 'gold': lf['gold'], 'potionCount': lf['potionCount'],
            'potionScore': lf['potionScore'], 'deathSave': lf['deathSave'], 'silverL': lf['silverL'],
            'fairy': lf['fairy'], 'lizardTail': lf['lizardTail'], 'incense': lf['incenseCounter'],
            'deck': len(st['deck']), 'relics': len(st['relicData']), 'potionCapacity': st['potionCapacity'],
            'cpuMs': r['cost']['cpuMs']})
        recs.append(r['heart1'])
print(f'units {n_units}, copies {len(metas)}', flush=True)

pooled = np.zeros((len(recs), net.dim), np.float32)
value = np.zeros(len(recs), np.float32)
t0 = time.time()
with torch.no_grad():
    for i in range(0, len(recs), 128):
        chunk = recs[i:i + 128]
        batch = pm.collate([pm.featurize(r, net.trim_map) for r in chunk])
        _, v, p = net.heads_out(net.trunk(batch), batch)
        pooled[i:i + len(chunk)] = p.float().numpy(); value[i:i + len(chunk)] = v.float().numpy()
        if i % 12800 == 0:
            print(f'{i}/{len(recs)} {time.time() - t0:.0f}s', flush=True)
np.savez(out + '.npz', pooled=pooled, value=value)
with open(out + '.meta.jsonl', 'w') as f:
    for mt in metas:
        f.write(json.dumps(mt) + '\n')
print(f'done {time.time() - t0:.0f}s', flush=True)
