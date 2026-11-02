import sys; sys.path.insert(0, sys.argv[0].rsplit('/',1)[0]); from common import *
G=load(*sys.argv[1:]); N=len(G)
first=[];second=[]; cont1=[];cont2=[]
for g in G:
    bs=[f for f in g['fights'] if f['act']==3 and f['room']=='BOSS']
    if bs:
        first.append((bs[0]['hp']/bs[0]['maxhp'], bs[0]['post']<=0, ENC[bs[0]['enc']], len(bs[0]['pots'])))
        if bs[0]['post']>0: cont1.append(g['o']['kill'])
    if len(bs)>1:
        second.append((bs[1]['hp']/bs[1]['maxhp'], bs[1]['post']<=0, ENC[bs[1]['enc']], len(bs[1]['pots']), bs[0]['hp']-bs[0]['post']))
        if bs[1]['post']>0: cont2.append(g['o']['kill'])
f=np.array([(a,b,d) for a,b,c,d in first]); s=np.array([(a,b,d,e) for a,b,c,d,e in second])
print(f'act3 boss 1: n={len(f)} death={f[:,1].mean()*100:.1f}% entryHP={f[:,0].mean()*100:.0f}% pots={f[:,2].mean():.2f}  P(kill|survived)={np.mean(cont1):.3f}')
print(f'act3 boss 2: n={len(s)} death={s[:,1].mean()*100:.1f}% entryHP={s[:,0].mean()*100:.0f}% pots={s[:,2].mean():.2f} boss1 HP loss={s[:,3].mean():.1f}  P(kill|survived)={np.mean(cont2):.3f}')
print('boss1 enc death:', {e:(round(np.mean([b for a,b,c,d in first if c==e])*100,1), sum(1 for x in first if x[2]==e)) for e in set(x[2] for x in first)})
print('boss2 enc death:', {e:(round(np.mean([b for a,b,c,d,_ in second if c==e])*100,1), sum(1 for x in second if x[2]==e)) for e in set(x[2] for x in second)})
# Ruby: pre-boss campfire recall and HP
rub=collections.Counter(); first_recall=collections.Counter(); earlier_ok=0; lowrec=0
for g in G:
    R=rests(g); bs=[f for f in g['fights'] if f['act']==3 and f['room']=='BOSS']
    rec=[r for r in R if r['c']=='recall']
    if rec:
        r=rec[0]; pre = bs and bs[0]['floor']-r['floor']<=2
        first_recall[(r['act'], 'preboss' if pre else 'earlier')]+=1
        if pre and r['hp']/r['maxhp']<0.6:
            lowrec+=1
            # did run pass an earlier act-3 campfire with HP>=60%?
            if any(x['act']==3 and x['floor']<r['floor'] and x['hp']/x['maxhp']>=0.6 for x in R): earlier_ok+=1
print('first Ruby recall site:', dict(first_recall), f'runs={N}')
print(f'pre-boss recall at <60% HP: {lowrec} ({lowrec/N*100:.1f}% of runs); of these passed an earlier act-3 campfire at >=60%: {earlier_ok}')
