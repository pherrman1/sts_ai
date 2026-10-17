import json, sys, glob, collections as C
root = sys.argv[1]
by = C.Counter(); sub = C.Counter(); relics = C.Counter(); disc = C.Counter(); discAct = C.Counter()
kept_over = C.Counter(); mctsRelic = C.Counter(); chestSkip=0; runs=0; fairyLost=[]
potTake=C.Counter(); noTakeFull=C.Counter()
for f in glob.glob(root + '/*/seed-*.trace.jsonl'):
    runs += 1
    for line in open(f):
        e = json.loads(line)
        if e.get('kind') != 'ooc': continue
        b = e['by']; by[b] += 1
        pre, post, off = e['pre'], e['post'], e.get('offer', {})
        if b in ('tree_rule', 'relic_rule', 'chest_rule', 'heart_key', 'mcts', 'chain', 'match_and_keep'):
            pp, qp = C.Counter(pre['potions']), C.Counter(post['potions'])
            lost = pp - qp; gained = qp - pp
            nr = set(post['relics']) - set(pre['relics'])
            if b == 'tree_rule':
                if post['gold'] > pre['gold']: sub['gold'] += 1
                elif lost and not gained: sub['potion_discard'] += 1
                elif gained: sub['potion_take'] += 1; potTake[tuple(gained)] += 1
                elif post['screen'] != pre['screen']: sub['leave'] += 1
                else: sub['other'] += 1
            if lost and not gained and b == 'tree_rule':
                for p in lost:
                    disc[p] += 1; discAct[(p, pre['act'])] += 1
                    if p == 'FAIRY_POTION': fairyLost.append((e['seed'], pre['act'], pre['floor'], pre['potions'], off.get('potions')))
            if b == 'relic_rule':
                for r in nr: relics[r] += 1
            if b == 'mcts' and pre['screen'] == 'REWARDS' and off.get('relics'):
                mctsRelic[(tuple(off['relics']), tuple(nr) if nr else 'none')] += 1
            if b == 'mcts' and pre['screen'] == 'REWARDS' and lost:
                sub['mcts_potion_discard'] += 1
            if pre['screen'] == 'REWARDS' and off.get('potions') and len(pre['potions'])>=pre['potionCapacity'] and 'EMPTY' not in str(pre['potions']):
                pass
print('runs', runs); print('by', by.most_common()); print('tree_rule sub', sub.most_common())
print('relic_rule took', relics.most_common(60))
print('mcts on relic screens', mctsRelic.most_common(30))
print('discarded by rule', disc.most_common()); print('fairy discards', len(fairyLost)); [print(x) for x in fairyLost[:40]]
