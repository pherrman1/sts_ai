import sys, os, json, gzip, glob, pickle
def rd(p):
    if not os.path.exists(p): return []
    with gzip.open(p,'rt') as f: return [json.loads(x) for x in f if x.strip()]
def potions(lst): return [p for p in lst if p not in (0,1)]
def game(gpath, cpath, seed, arm):
    rows=rd(gpath); ctm=rd(cpath)
    out=[r for r in rows if r.get('type')=='outcome']
    if not out or not out[-1].get('complete'): return None
    o=out[-1]
    fights=[]
    for c in ctm:
        t=c['transition']; pre=t['pre']; post=t['post']
        fights.append(dict(idx=c['fightIdx'],act=c['act'],floor=c['floor'],enc=c['encounter'],room=c['roomClass'],
            hp=pre['curHp'],maxhp=pre['maxHp'],post=post['curHp'],postmax=post['maxHp'],res=t['combatOutcome'],
            pots=potions(pre['potions']),postpots=potions(post['potions']),cap=pre['potionCapacity'],
            deck=[(d['id'],d['upgraded']) for d in pre['deck']],relics=[r['id'] for r in pre['relics']],gold=pre['gold'],
            burning=c['predictorInput']['globals'].get('isBurningElite')))
    states=[]; 
    for r in rows:
        if r.get('type')!='state': continue
        rec=r['record']; fo=rec['obs.fixed_observation']
        states.append(dict(i=r['index'],act=r['act'],floor=r['floor'],screen=r['screen'],hp=fo[0],maxhp=fo[1],gold=fo[2],
            ups=sum(rec['obs.deck.upgrades']),keys=fo[7:10],deckn=len(rec['obs.deck.cards']),deck=rec['obs.deck.cards'],pots=potions(rec['obs.potions']),
            relics=rec['obs.relics.relics'],mapx=rec['obs.mapX'],mapy=rec['obs.mapY'],
            roomtypes=rec['obs.map.roomTypes'] if r['screen']==5 else None,xs=rec['obs.map.xs'] if r['screen']==5 else None,
            ys=rec['obs.map.ys'] if r['screen']==5 else None,paths=rec.get('paths_offered'),
            cards_offered=rec.get('cards_offered.cards'),relics_offered=rec.get('relics_offered'),potions_offered=rec.get('potions_offered'),cap=len(rec['obs.potions'])))
    decs=[]
    for r in rows:
        if r.get('type')!='decision': continue
        d=dict(si=r['stateIndex'],by=r['by'],searched=r['searched'])
        if r.get('root'):
            rt=r['root']; d.update(q=rt.get('rootMeanQ'),sel=r.get('selectedKey'),screen=r.get('screen'),
                cands=[(c['key'],c['prior'],c['q'],c['visits']) for c in rt.get('candidates',[])])
        decs.append(d)
    return dict(seed=seed,arm=arm,o=dict(kill=o['heartKilled'],act=o['finalAct'],floor=o['finalFloor'],hp=o['finalHp']),
                fights=fights,states=states,decs=decs)
def main(root, pattern, arm, outp):
    games=[]
    for g in sorted(glob.glob(os.path.join(root,pattern))):
        if '.ctm.' in g or '.price.' in g or '.chooser.' in g: continue
        seed=int(os.path.basename(g).split('-')[1].split('.')[0])
        x=game(g, g.replace('.jsonl.gz','.ctm.jsonl.gz'), seed, arm)
        if x: games.append(x)
    pickle.dump(games, open(outp,'wb')); print(arm, len(games))
if __name__=='__main__': main(*sys.argv[1:])
