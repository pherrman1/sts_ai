#!/usr/bin/env python3
"""Speed options at map roots relative to the 1,024-sim visits pick, offline from logged checkpoints (no seeds).
usage: budget_stop.py ARM UNITS_DIR OUT_JSON
- fixed budget k in 128/256/512: pick at k (visits_q_id) != pick at 1,024;
- stability stop S(k0,k1): stop at k1 when the visits pick at k0 equals the pick at k1 (else continue to the next
  pair, finally 1,024); pairs (128,256),(256,512). Also S_prior: stop at k when the pick at k is the prior argmax
  and holds >= share h of visits (h = 0.9, 0.95).
Reports mean sims / 1,024 and disagreement with the 1,024 pick (and with the 4,096 pick, the old default).
"""
import gzip, json, os, sys, tarfile, collections
ARM, UNITS, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
def vp(acts):
    acts = [a for a in acts if not a.get('pruned')] or acts
    return sorted(acts, key=lambda a: (-a['visits'], -a['q'], a['id']))[0]['id']
S = collections.defaultdict(lambda: [0, 0, 0]); roots = 0
def add(name, used, pick, p1024, p4096):
    s = S[name]; s[0] += used; s[1] += pick != p1024; s[2] += pick != p4096
for name in sorted(os.listdir(UNITS)):
    if not name.endswith('.tar'): continue
    seed = name.split('.')[0]
    with tarfile.open(os.path.join(UNITS, name)) as tf:
        try: m = tf.getmember(f'out/units/{seed}/{ARM}-{seed}.jsonl.gz')
        except KeyError: continue
        rows = [json.loads(l) for l in gzip.decompress(tf.extractfile(m).read()).decode().splitlines() if l.strip()]
    out = [r for r in rows if r.get('type') == 'outcome']
    if not out or not out[0].get('complete'): continue
    for r in rows:
        if r.get('type') != 'decision' or not r.get('searched') or r.get('screen') != 5: continue
        ro = r['root']
        if ro.get('singleton') or not ro.get('attempts') or ro.get('aborted') or ro['completedSimulations'] != 4096: continue
        cps = {c['simulations']: c['actions'] for c in ro.get('checkpoints', [])}
        if not all(k in cps for k in (128, 256, 512, 1024)): continue
        roots += 1; p = {k: vp(cps[k]) for k in (128, 256, 512, 1024)}; p4 = ro['selectedId']
        parg = max(ro['candidates'], key=lambda c: (c['prior'], -c['id']))['id']
        add('fixed1024', 1024, p[1024], p[1024], p4)
        for k in (128, 256, 512): add(f'fixed{k}', k, p[k], p[1024], p4)
        used, pick = 1024, p[1024]
        for k0, k1 in ((128, 256), (256, 512)):
            if p[k0] == p[k1]: used, pick = k1, p[k1]; break
        add('stable', used, pick, p[1024], p4)
        for h in (0.9, 0.95):
            used, pick = 1024, p[1024]
            for k in (128, 256, 512):
                tot = sum(a['visits'] for a in cps[k]); top = max(a['visits'] for a in cps[k])
                if p[k] == parg and top >= h * tot: used, pick = k, p[k]; break
            add(f'prior_share{h}', used, pick, p[1024], p4)
res = {'arm': ARM, 'roots': roots}
for k, (u, d1, d4) in S.items():
    res[k] = dict(sims_vs_1024=u / roots / 1024, differs_from_1024=d1 / roots, differs_from_4096=d4 / roots)
json.dump(res, open(OUT, 'w'), indent=1); print(json.dumps(res, indent=1))
