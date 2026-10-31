#!/usr/bin/env python3
"""Post-hoc, exploratory (Philipp 10-31 "Wieso bewerten wir nicht z.b. card decision?"): stage 5b's V_A1-3 at
non-map decisions of the capture-2 TEST games (second look at TEST, disclosed). Per price row with >= 2 labelled
actions: pairwise concordance with the rollout labels (same labels as stage5b) for V (mean V over the action's start
records) and for the production policy prior (heart1/student_sel, `prior` in the price row), by act and screen.
Screens: 1 event, 2 combat rewards, 3 boss relic, 4 card select (upgrade/remove), 6 chest, 7 campfire, 8 shop.
usage: nonmap_eval.py CAPTURE2_UNITS STAGE5B_OUT OUT_JSON [WORKERS]"""
import sys, os, json, pickle, collections
import multiprocessing as mp
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stage5b as B  # noqa: E402
S5, SF, F = B.S5, B.SF, B.F
VCal = B.VCal   # V_A*.pkl were pickled from stage5b run as __main__


def game(arg):
    seed, pr, k = arg
    starts, roll, ends, rows = [], [], [], []
    for r in S5.rows(pr):
        if r['act'] != k or r['screen'] == 5 or 'error' in r['price'] or 'priceError' in r: continue
        acts = []
        for a in r['price']['actions']:
            sid = {}
            for e in a['actEnd']:
                if 'error' in e or e.get('start') is None: continue
                if e['start'] not in sid:
                    sid[e['start']] = len(starts); starts.append(SF.enc(a['starts'][e['start']]))
                er = e.get('endRecord')
                if er is None or er['obs.act'] != k + 1: roll.append((sid[e['start']], -1))
                else: roll.append((sid[e['start']], len(ends))); ends.append(er)
            if sid: acts.append((a['key'], float(a.get('prior', 0.0)), list(sid.values())))
        if len(acts) >= 2: rows.append((r['screen'], acts))
    if not rows: return seed, []
    if k == 3:
        import va4_model
        if not hasattr(game, 'va4'): game.va4 = va4_model.load()
        ev = game.va4.predict([{'act': 4, 'floor': x['obs.fixed_observation'][3], 'record': x} for x in ends]) if ends else []
    else:
        ev = B._V(SF.csr([SF.enc(x) for x in ends])) if ends else []
    ev = np.asarray(ev, np.float64)
    lab = collections.defaultdict(list)
    for sid, ei in roll: lab[sid].append(ev[ei] if ei >= 0 else 0.0)
    vs = game.vk(SF.csr(starts))
    out = []
    for screen, acts in rows:
        a = [(key, pri, float(np.mean([vs[i] for i in ii])), float(np.mean([x for i in ii for x in lab[i]])),
              sum(len(lab[i]) for i in ii)) for key, pri, ii in acts]
        out.append((screen, a))
    return seed, out


def _init(vnext, vk):
    B._init(vnext); game.vk = vk


def main(cap2, s5b, out, workers=4):
    G = {s: pr for s, (pr, g) in S5.games(cap2).items() if pr and int(s) in B.C2 and B.split(s) == 'test'}
    if os.environ.get('NM_LIMIT'): G = dict(sorted(G.items())[:int(os.environ['NM_LIMIT'])])   # plumbing tests only
    res = {'games': len(G), 'acts': {}}
    for k in (1, 2, 3):
        vk = pickle.load(open(os.path.join(s5b, f'V_A{k}.pkl'), 'rb'))
        vn = pickle.load(open(os.path.join(s5b, f'V_A{k + 1}.pkl'), 'rb')) if k < 3 else None
        with mp.get_context('spawn').Pool(int(workers), initializer=_init, initargs=(vn, vk)) as pool:
            R = pool.map(game, [(s, pr, k) for s, pr in sorted(G.items())], chunksize=1)
        per = collections.defaultdict(lambda: ([], [], []))
        for seed, rows in R:
            for screen, a in rows:
                for i in range(len(a)):
                    for j in range(i + 1, len(a)):
                        t = np.sign(a[i][3] - a[j][3])
                        if t == 0: continue
                        sc = lambda d: 0.5 if d == 0 else float(np.sign(d) == t)
                        for key in (screen, 'all'):
                            per[key][0].append(sc(a[i][2] - a[j][2])); per[key][1].append(sc(a[i][1] - a[j][1])); per[key][2].append(seed)
        res['acts'][k] = {}
        for key, (dv, dp, ps) in sorted(per.items(), key=lambda x: str(x[0])):
            dv, dp, ps = np.array(dv), np.array(dp), np.array(ps)
            res['acts'][k][str(key)] = {'pairs': int(len(dv)), 'V': float(dv.mean()), 'policy_prior': float(dp.mean()),
                                        'diff': float((dv - dp).mean()), 'ci': F.boot(ps, dv - dp)}
        print(k, json.dumps(res['acts'][k]), flush=True)
    json.dump(res, open(out, 'w'), indent=1)


if __name__ == '__main__':
    main(*sys.argv[1:5])
