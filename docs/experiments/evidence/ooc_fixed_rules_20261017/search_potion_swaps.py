import json, sys, glob, collections as C, statistics as S
root, rk = sys.argv[1], sys.argv[2]
R = {l.split()[0]: int(l.split()[1]) for l in open(rk)}
loss = []; followed = C.Counter(); worstDisc = 0; byAct = C.Counter(); runsWith = set(); outcome = {}
for f in sorted(glob.glob(root + '/*/seed-*.trace.jsonl')):
    evs = [json.loads(l) for l in open(f) if '"ooc"' in l]
    for i, e in enumerate(evs):
        if e.get('kind') != 'ooc': continue
        pre, post, off = e['pre'], e['post'], e.get('offer', {})
        pp, qp = C.Counter(pre['potions']), C.Counter(post['potions'])
        if not (e['by'] == 'mcts' and pre['screen'] == 'REWARDS' and (pp - qp) and not (qp - pp)): continue
        d = list(pp - qp)[0]
        held = [p for p in pre['potions'] if p in R]
        if R[d] == min(R[p] for p in held): worstDisc += 1
        byAct[pre['act']] += 1; runsWith.add(e['seed'])
        # next event: what did it gain?
        g = None
        for e2 in evs[i+1:i+4]:
            gg = C.Counter(e2['post']['potions']) - C.Counter(e2['pre']['potions'])
            if gg: g = list(gg)[0]; break
            if e2['pre']['screen'] != 'REWARDS': break
        followed[g is not None] += 1
        if g: loss.append(R[d] - R[g])
print('n', sum(followed.values()), 'followed by take', followed, 'discarded the worst held', worstDisc, 'runs', len(runsWith), 'by act', sorted(byAct.items()))
print('rank loss (discarded - taken)/100: mean %.2f median %.2f, >0: %d, <=0: %d' % (S.mean(loss)/100, S.median(loss)/100, sum(x>0 for x in loss), sum(x<=0 for x in loss)))
