import json,glob,collections,csv,sys
D=sys.argv[1]
rows=[r for f in sorted([g for g in glob.glob(D+'/u-*.csv') if not g.endswith('.v4.csv')]) for r in csv.DictReader(open(f))]
n=len(rows); w=sum(int(r['won']) for r in rows)
print(f"runs {n} wins {w} ({100*w/n:.1f}%) mean floor {sum(int(r['floor']) for r in rows)/n:.2f} cpu/run {sum(float(r.get('sec') or r.get('wall') or 0) for r in rows)/n:.0f}s")
death=collections.Counter(); act=collections.Counter(); bosskind=collections.Counter()
by=collections.Counter(); scr_chain=collections.Counter(); notv4=collections.Counter(); v4rows=collections.Counter()
SC={1:'EVENT',2:'REWARDS',3:'BOSS_RELIC',4:'CARD_SELECT',5:'MAP',6:'TREASURE',7:'REST',8:'SHOP'}
for f in sorted(glob.glob(D+'/u-*.trace.jsonl')):
    base=f[:-len('.trace.jsonl')]
    v4=collections.defaultdict(int)
    try:
        for r in csv.DictReader(open(base+'.v4.csv')):
            v4[(int(r['seed']),int(r['floor']),SC[int(r['screen'])])]+=1
            v4rows[SC[int(r['screen'])]]+=1
    except FileNotFoundError: pass
    mk=set(); chain=collections.defaultdict(list); last=None
    for l in open(f):
        r=json.loads(l)
        if r['kind']=='battle':
            if not r['won']:
                room=r['pre']['room']; death[(r['pre']['act'],room,r['encounter'])]+=1
            continue
        s=r['pre']['screen']; by[(r['by'],s)]+=1
        if r['by']=='match_and_keep': mk.add((r['seed'],r['pre']['floor']))
        if r['by']!='chain': continue
        key=(r['seed'],r['pre']['floor'],s)
        kind=s
        if s=='REWARDS':
            o=r['offer']; pre,post=r['pre'],r['post']
            if o.get('gold'): kind='REWARDS:gold'
            elif o.get('relics'): kind='REWARDS:relic'
            elif o.get('potions') and len(pre['potions'])<pre['potionCapacity']: kind='REWARDS:potion'
            elif not o.get('cards'): kind='REWARDS:skip(no cards)'
            else: kind='REWARDS:card'
        elif s=='CARD_SELECT':
            kind='CARD_SELECT@'+(r['pre']['room'])
        elif s=='MAP' and r['pre']['y']==14: kind='MAP:boss node'
        chain[key].append(kind)
    for key,kinds in chain.items():
        seed,fl,s=key
        cand=[k for k in kinds if not k.startswith('REWARDS:') or k=='REWARDS:card']
        cand=[k for k in cand if k!='MAP:boss node']
        for k in kinds: scr_chain[k]+=1
        nv=v4.get(key,0)
        if s=='REWARDS' and (seed,fl) in mk: continue
        # V4 rows beyond candidate decisions are ignored; non-V4 = candidates - V4 rows
        miss=len(cand)-nv
        if miss>0:
            # attribute misses to the candidate kinds (last ones)
            for k in cand[-miss:]: notv4[k]+=1
for k in sorted(by): print('by',k,by[k])
print('chain decisions by kind:'); [print('  ',k,v) for k,v in sorted(scr_chain.items())]
print('V4 gate rows by screen:',dict(v4rows))
print('chain decisions with no matching V4 row:',dict(notv4))
print('deaths:'); [print('  ',k,v) for k,v in death.most_common()]
