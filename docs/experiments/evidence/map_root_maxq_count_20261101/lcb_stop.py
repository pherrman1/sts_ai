#!/usr/bin/env python3
"""LCB pick at 1,024 map sims with an LCB/UCB separation stop, offline from logged checkpoints (no seeds).
usage: lcb_stop.py ARM UNITS_DIR OUT_JSON
At checkpoints 128/256/512 (a k-sim search's tree, §737), stop when LCB of the LCB-best child exceeds the UCB of every
other child with >= 1 visit (c = 1.96, sigma per act from calibrate.py: 0.105/0.158/0.180); else run to 1,024 and
pick by LCB. Reports sims per root vs 1,024, and agreement of the stopped pick with LCB@1024 and with visits@1024.
"""
import gzip, json, math, os, sys, tarfile, collections
ARM, UNITS, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
STABLE = sys.argv[4] if len(sys.argv) > 4 else ''  # 'agree': stop at k1 when LCB pick at k0 == at k1 == visits pick at k1
SIG = {1: 0.105, 2: 0.158, 3: 0.180}; C = 1.96
def vpick(acts):
    acts = [a for a in acts if not a.get('pruned')] or acts
    return sorted(acts, key=lambda a: (-a['visits'], -a['q'], a['id']))[0]['id']
def lcbpick(acts, s):
    el = [a for a in ([a for a in acts if not a.get('pruned')] or acts) if a['visits'] >= 1]
    return max(el, key=lambda a: a['q'] - C * s / math.sqrt(a['visits']))
def separated(acts, s):
    el = [a for a in ([a for a in acts if not a.get('pruned')] or acts) if a['visits'] >= 1]
    b = lcbpick(el, s); lb = b['q'] - C * s / math.sqrt(b['visits'])
    return all(a['q'] + C * s / math.sqrt(a['visits']) < lb for a in el if a['id'] != b['id']), b['id']
st = collections.Counter(); sims = 0; roots = 0; stopk = collections.Counter()
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
        if 1024 not in cps: continue
        s = SIG[min(r['act'], 3)]; roots += 1
        l1024 = lcbpick(cps[1024], s)['id']; v1024 = vpick(cps[1024])
        used, pick = 1024, l1024
        if STABLE:
            p = {k: lcbpick(cps[k], s)['id'] for k in (128, 256, 512) if k in cps}
            for k0, k1 in ((128, 256), (256, 512)):
                if k0 in p and k1 in p and p[k0] == p[k1] == (vpick(cps[k1]) if STABLE == 'visits' else p[k1]) and (STABLE != 'agree' or p[k1] == vpick(cps[k1])):
                    used, pick = k1, p[k1]; break
        else:
          for k in (128, 256, 512):
            if k in cps:
                ok, b = separated(cps[k], s)
                if ok: used, pick = k, b; break
        stopk[used] += 1; sims += used
        st['agree_lcb1024'] += pick == l1024; st['agree_visits1024'] += pick == v1024; st['lcb1024_eq_visits1024'] += l1024 == v1024
        st['final_pick_eq_visits4096'] += pick == ro['selectedId']
res = dict(arm=ARM, roots=roots, mean_sims=sims / roots, sims_ratio_vs_1024=sims / roots / 1024,
           stop_at={str(k): v / roots for k, v in sorted(stopk.items())}, **{k: v / roots for k, v in st.items()})
json.dump(res, open(OUT, 'w'), indent=1); print(json.dumps(res, indent=1))
