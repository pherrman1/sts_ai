#!/usr/bin/env python3
"""compare.py OFF.jsonl[.gz] ON.jsonl[.gz] H
Applies budget_stop.py's S_prior rule (h = H, checks 128/256/512, else 1,024) to every full 1,024-sim map root of the
flag-off record and checks the flag-on record of the same seed decision by decision: the ON root must stop exactly at
the predicted simulation count and play the predicted pick. Stops at the first decision whose played key differs
(the games diverge there); that root must be one where the offline pick differs from the 1,024 pick."""
import gzip, json, sys
def rows(p):
    op = gzip.open if p.endswith('.gz') else open
    with op(p, 'rt') as f:
        return [json.loads(l) for l in f if l.strip()]
def vp(acts):
    acts = [a for a in acts if not a.get('pruned')] or acts
    return sorted(acts, key=lambda a: (-a['visits'], -a['q'], a['id']))[0]['id']
off, on, h = rows(sys.argv[1]), rows(sys.argv[2]), float(sys.argv[3])
offd = [r for r in off if r.get('type') == 'decision']; ond = [r for r in on if r.get('type') == 'decision']
n = stopped = mism = full = 0; sims_off = sims_on = 0; diverged = None
for a, b in zip(offd, ond):
    assert a['decisionIndex'] == b['decisionIndex'], (a['decisionIndex'], b['decisionIndex'])
    ro = a.get('root')
    pred = None
    if a.get('searched') and a.get('screen') == 5 and ro and not ro.get('singleton') and not ro.get('aborted') \
            and ro.get('fullBudget') and ro['completedSimulations'] == 1024:
        cps = {c['simulations']: c['actions'] for c in ro['checkpoints']}
        parg = max(ro['candidates'], key=lambda c: (c['prior'], -c['id']))['id']
        used, pick = 1024, vp(cps[1024])
        for k in (128, 256, 512):
            tot = sum(x['visits'] for x in cps[k]); top = max(x['visits'] for x in cps[k])
            if vp(cps[k]) == parg and top >= h * tot: used, pick = k, vp(cps[k]); break
        assert vp(cps[1024]) == ro['selectedId']
        pred = (used, pick)
        rb = b['root']
        got = (rb['completedSimulations'], rb['selectedId'])
        full += 1; sims_off += 1024; sims_on += got[0]
        ok = got == pred and bool(rb.get('earlyStopPriorShare')) == (used < 1024) and rb.get('priorShareStop') == h
        if used < 1024: stopped += 1
        if not ok:
            mism += 1; print('MISMATCH', a['decisionIndex'], 'pred', pred, 'got', got, rb.get('earlyStopPriorShare'))
    elif a.get('root') is not None or b.get('root') is not None:
        # every other searched root must be untouched by the flag
        ra, rb = a.get('root') or {}, b.get('root') or {}
        strip = lambda r: {k: v for k, v in r.items() if k not in ('priorShareStop', 'earlyStopPriorShare')}
        if strip(ra) != strip(rb):
            mism += 1; print('OTHER ROOT CHANGED', a['decisionIndex'], a.get('screen'))
    n += 1
    if a.get('selectedKey') != b.get('selectedKey'):
        diverged = dict(decision=a['decisionIndex'], off=a.get('selectedKey'), on=b.get('selectedKey'),
                        predicted_differs=pred is not None and pred[1] != ro['selectedId'])
        break
print(json.dumps(dict(h=h, decisions_compared=n, full_map_roots=full, predicted_stops=stopped, mismatches=mism,
                      sims_on_over_off=(sims_on / sims_off if sims_off else None), diverged=diverged,
                      off_decisions=len(offd), on_decisions=len(ond))))
