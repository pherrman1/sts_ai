import pickle, sys, collections, numpy as np
sys.path.insert(0, sys.argv[0].rsplit('/',1)[0]); from names import *
G=[]
for f in sys.argv[1:]: G+=pickle.load(open(f,'rb'))
print('games',len(G))
rows=[]
for g in G:
    for fi in g['fights']:
        if fi['room'] in ('BOSS',) or ENC[fi['enc']] in ('THE_HEART','SHIELD_AND_SPEAR'):
            rows.append((ENC[fi['enc']], fi['hp'], fi['maxhp'], fi['post']<=0, len(fi['pots']), len(fi['postpots']), len(fi['deck']), fi['act']))
by=collections.defaultdict(list)
for r in rows: by[r[0]].append(r)
print(f"{'boss':16s} {'n':>5s} {'death':>6s} | death rate by entry HP%: <40  40-60 60-80 80+ | mean HP% died/surv | died w/ potions left | pots at entry died/surv")
for b,rs in sorted(by.items(), key=lambda x:-sum(r[3] for r in x[1])):
    a=np.array([[r[1]/r[2], r[3], r[4], r[5]] for r in rs],float)
    bins=[(0,.4),(.4,.6),(.6,.8),(.8,1.01)]
    s=' '.join(f"{a[(a[:,0]>=lo)&(a[:,0]<hi),1].mean()*100:4.0f}%({int(((a[:,0]>=lo)&(a[:,0]<hi)).sum()):3d})" if ((a[:,0]>=lo)&(a[:,0]<hi)).sum() else '   -     ' for lo,hi in bins)
    d=a[:,1]==1
    print(f"{b:16s} {len(a):5d} {a[:,1].mean()*100:5.1f}% | {s} | {a[d,0].mean()*100:3.0f}/{a[~d,0].mean()*100:3.0f} | {(a[d,3]>0).mean()*100 if d.any() else 0:4.0f}% | {a[d,2].mean() if d.any() else 0:.2f}/{a[~d,2].mean():.2f}")
