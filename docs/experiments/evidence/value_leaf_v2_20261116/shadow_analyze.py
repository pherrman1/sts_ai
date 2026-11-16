"""Shadow-mode leaves: the Q head's value of the edge into a tree leaf vs that leaf's playout value."""
import collections, glob, json, sys
import numpy as np
T = {0: 'CARD', 1: 'POTION', 2: 'SELECT1', 3: 'SELECTM', 4: 'END_TURN'}
rows = []
for p in sys.argv[1:]:
    for l in open(p):
        try:
            r = json.loads(l)
        except ValueError:
            continue
        r['u'] = p
        rows.append(r)
print('leaves', len(rows))
q = np.array([r['q'] for r in rows]); v = np.array([r['v'] for r in rows])
out = {}
def lvl(mask, name):
    d = v[mask] - q[mask]
    out[name] = dict(n=int(mask.sum()), v_minus_q=round(float(d.mean()), 2), sd=round(float(d.std()), 1),
                     v_mean=round(float(v[mask].mean()), 1), q_mean=round(float(q[mask].mean()), 1))
lvl(np.ones(len(rows), bool), 'all')
for t, name in T.items():
    m = np.array([r['t'] == t for r in rows])
    if m.any(): lvl(m, 'type_' + name)
for e in sorted({r['enc'] for r in rows}):
    lvl(np.array([r['enc'] == e for r in rows]), 'enc_' + e)
# within parent: demeaned over the parent's logged leaves (need >= 2 distinct edges)
G = collections.defaultdict(list)
for i, r in enumerate(rows):
    G[(r['u'], r['s'], r['p'])].append(i)
qd, vd, td = [], [], []
pairs = agree = 0
for idx in G.values():
    if len({rows[i]['e'] for i in idx}) < 2:
        continue
    qq = q[idx]; vv = v[idx]
    qd += list(qq - qq.mean()); vd += list(vv - vv.mean()); td += [rows[i]['t'] for i in idx]
    for a in range(len(idx)):
        for b in range(a + 1, len(idx)):
            if rows[idx[a]]['e'] == rows[idx[b]]['e'] or abs(vv[a] - vv[b]) < 2:
                continue
            pairs += 1; agree += (qq[a] - qq[b]) * (vv[a] - vv[b]) > 0
qd, vd = np.array(qd), np.array(vd)
slope = float((qd * vd).sum() / (qd * qd).sum())
out['within_parent'] = dict(leaves=len(qd), slope_v_on_q=round(slope, 3), corr=round(float(np.corrcoef(qd, vd)[0, 1]), 3),
                            sd_q=round(float(qd.std()), 2), sd_v=round(float(vd.std()), 2),
                            pair_order_agree=round(agree / max(1, pairs), 3), pairs=pairs)
td = np.array(td)
for t, name in T.items():
    m = td == t
    if m.sum() > 50:
        out['within_parent_' + name] = dict(n=int(m.sum()), mean_qd=round(float(qd[m].mean()), 2), mean_vd=round(float(vd[m].mean()), 2))
print(json.dumps(out, indent=1))
