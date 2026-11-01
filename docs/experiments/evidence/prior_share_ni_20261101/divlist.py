"""Predicted first divergence of the prior-share arm (STS_OOC_MCTS_PRIOR_SHARE_STOP=H) from the 1,024 control.
usage: divlist.py A_UNITS_DIR B_SHARE H OUT_JSON
  A_UNITS_DIR  /mnt/project-files/value-chooser-ab/units  (§727 arm A, 4,096 map sims)
  B_SHARE      /mnt/project-files/map-sims-sprt            (§741 arm B, 1,024 map sims; played on 716 seeds)
Control record R(s) = §741 B record where B was played, else §727 A record (§741 verified B == A there: 64/64
sentinels, 652/652 prefixes). At every searched map root of R with checkpoints 128/256/512/1024 the 1,024 search is
the 1,024 checkpoint (§741 README); the prior-share arm plays the S_prior pick (budget_stop.py: stop at the first
k in 128/256/512 where the visits_q_id pick is the prior argmax and holds >= H of the visits, else the 1,024 pick).
The arm diverges at the first root where that pick differs from the 1,024 pick."""
import gzip, hashlib, json, os, sys, tarfile
AU, BS, H, OUT = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
def pick(a):
    a = [x for x in a if not x.get("pruned")] or a
    return sorted(a, key=lambda x: (-x["visits"], -x["q"], x["id"]))[0]["id"]
B = {}
for n in sorted(os.listdir(os.path.join(BS, 'units'))):
    if n.endswith('.tar'):
        s = int(n.split('_')[0]); assert s not in B, s; B[s] = os.path.join(BS, 'units', n)
res = {}
for n in sorted(os.listdir(AU)):
    if not n.endswith('.tar'): continue
    s = int(n.split('.')[0])
    if s in B:
        with tarfile.open(B[s]) as tf:
            m = [x for x in tf.getmembers() if x.name.endswith(f'/B-{s}.jsonl.gz')]; assert len(m) == 1, (s, m)
            raw = tf.extractfile(m[0]).read(); src = 'B741'
    else:
        with tarfile.open(os.path.join(AU, n)) as tf:
            raw = tf.extractfile(f"out/units/{s}/A-{s}.jsonl.gz").read(); src = 'A727'
    rows = [json.loads(l) for l in gzip.decompress(raw).decode().splitlines() if l.strip()]
    out = [r for r in rows if r.get('type') == 'outcome'][0]
    e = dict(source=src, heartKilled=bool(out.get('heartKilled')), complete=bool(out.get('complete')), diverges=False,
             mapRoots=0, stoppedRoots=0, simsControl=0, simsArm=0, jsonlSha256=hashlib.sha256(raw).hexdigest())
    for r in rows:
        ro = r.get('root')
        if not (r.get('type') == 'decision' and r.get('searched') and r.get('screen') == 5 and ro and ro.get('attempts')):
            continue
        cps = {c['simulations']: c['actions'] for c in ro.get('checkpoints', [])}
        if not all(k in cps for k in (128, 256, 512, 1024)): continue
        e['mapRoots'] += 1
        p1024 = pick(cps[1024])
        parg = max(ro['candidates'], key=lambda c: (c['prior'], -c['id']))['id']
        used, p = 1024, p1024
        for k in (128, 256, 512):
            tot = sum(x['visits'] for x in cps[k]); top = max(x['visits'] for x in cps[k])
            if pick(cps[k]) == parg and top >= H * tot: used, p = k, pick(cps[k]); break
        if not e['diverges']:
            e['simsControl'] += 1024; e['simsArm'] += used; e['stoppedRoots'] += used < 1024
            if p != p1024:
                key = {c['id']: c['key'] for c in ro['candidates']}
                e.update(diverges=True, decisionIndex=r['decisionIndex'], act=r['act'], floor=r['floor'],
                         controlKey=key[p1024], predictedKey=key[p], stopAt=used)
    res[s] = e
json.dump(res, open(OUT, 'w'), indent=0, sort_keys=True)
d = [k for k, v in res.items() if v['diverges']]
sc = sum(v['simsControl'] for v in res.values()); sa = sum(v['simsArm'] for v in res.values())
print(len(res), 'games', len(d), 'diverge;', 'map sims arm/control up to divergence', round(sa / sc, 4),
      'B741 sources', sum(v['source'] == 'B741' for v in res.values()))
