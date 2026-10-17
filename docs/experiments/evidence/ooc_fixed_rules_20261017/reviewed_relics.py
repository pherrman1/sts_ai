import json, sys, glob, collections as C
root = sys.argv[1]
REV = {'BOTTLED_FLAME','BOTTLED_LIGHTNING','BOTTLED_TORNADO','DEAD_BRANCH','TUNGSTEN_ROD','UNCEASING_TOP','JUZU_BRACELET'}
other = []; mdisc = C.Counter(); mdiscEx = []
screen = C.Counter()
for f in sorted(glob.glob(root + '/*/seed-*.trace.jsonl')):
    evs = [json.loads(l) for l in open(f)]
    # group consecutive REWARDS screens by floor
    cur = None
    for e in evs:
        if e.get('kind') != 'ooc': continue
        pre, post, off = e['pre'], e['post'], e.get('offer', {})
        if pre['screen'] == 'REWARDS':
            k = (pre['floor'], pre['room'])
            if cur is None or cur[0] != k:
                if cur: screen.update(cur[1])
                offered = set(off.get('relics') or []) & REV
                cur = [k, C.Counter(), offered, set(pre['relics'])]
            if cur[2]:
                pass
            if post['screen'] != 'REWARDS' or (post['floor'], post['room']) != k:
                for r in cur[2]:
                    cur[1][(r, 'taken' if r in post['relics'] else 'left')] += 1
                screen.update(cur[1]); cur = None
        pp, qp = C.Counter(pre['potions']), C.Counter(post['potions'])
        if e['by'] == 'tree_rule' and post['gold'] == pre['gold'] and not (qp - pp) and not (pp - qp) and post['screen'] == pre['screen']:
            other.append((e['seed'], pre['floor'], off, pre['relics'][-1:], post['relics'][-1:], pre['deck'] == post['deck']))
        if e['by'] == 'mcts' and pre['screen'] == 'REWARDS' and (pp - qp) and not (qp - pp):
            for p in pp - qp: mdisc[p] += 1
            if len(mdiscEx) < 8: mdiscEx.append((e['seed'], pre['floor'], pre['potions'], off.get('potions')))
print(sorted(screen.items()))
print('other', len(other)); [print(x) for x in other[:6]]
print('mcts discards on rewards', mdisc.most_common()); [print(x) for x in mdiscEx]
