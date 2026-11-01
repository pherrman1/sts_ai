#!/usr/bin/env python3
"""Boss-fight logistic models and counterfactual levers (observational upper bounds).
usage: bossreg.py GAMES.pkl [GAMES.pkl ...]
Death at each act boss (A20 act 3 has two bosses; act 4 = the Heart) ~ boss + entry HP + max HP + potions + deck size
+ upgrades + curses + Strikes/Defends + relics + mean HP lost per hallway / elite fight earlier in the act.
Levers shift one entry variable and convert the change in fight death into Heart kills with
P(Heart kill | survived that fight), estimated from the same games."""
import sys; sys.path.insert(0, sys.argv[0].rsplit('/',1)[0]); from common import *
import pandas as pd, statsmodels.formula.api as smf
G=load(*sys.argv[1:]); N=len(G)
rows=[]
for g in G:
    fs=g['fights']; R=rests(g); nth=collections.Counter()
    for j,fi in enumerate(fs):
        if not isboss(fi) or ENC[fi['enc']]=='SHIELD_AND_SPEAR': continue
        k=nth[fi['act']]; nth[fi['act']]+=1
        hall=[f for f in fs[:j] if f['act']==fi['act'] and f['room']=='NORMAL']
        eli=[f for f in fs[:j] if f['act']==fi['act'] and f['room']=='ELITE']
        loss=lambda L: np.mean([f['hp']-f['post'] for f in L]) if L else np.nan
        ct=collections.Counter(CTYPE[c] for c,u in fi['deck'])
        pre=[r for r in R if fi['floor']-2<=r['floor']<fi['floor']]
        rec_low=int(k==0 and bool(pre) and pre[-1]['c']=='recall' and pre[-1]['hp']/pre[-1]['maxhp']<0.6)
        rows.append(dict(seed=g['seed'],boss=ENC[fi['enc']],act=fi['act'],nth=k,hp=fi['hp'],maxhp=fi['maxhp'],
            pots=len(fi['pots']),cap=fi['cap'],deck=len(fi['deck']),ups=sum(u for c,u in fi['deck']),curse=ct['CURSE'],
            relics=len(fi['relics']),hall_loss=loss(hall),elite_loss=loss(eli),
            basic=sum(1 for c,u in fi['deck'] if CARD[c] in ('STRIKE_RED','DEFEND_RED')),
            rec_low=rec_low,death=int(fi['post']<=0),kill=int(g['o']['kill'])))
D=pd.DataFrame(rows)
for c in ('hall_loss','elite_loss'): D[c]=D[c].fillna(D[c].mean())
cont={(a,k):D[(D.act==a)&(D.nth==k)&(D.death==0)].kill.mean() for a,k in D.groupby(['act','nth']).size().index}
print(f'games {N}; P(Heart kill | survived boss): ' + ', '.join(f'act{a}#{k+1} {v:.3f}' for (a,k),v in sorted(cont.items())))
F={a:('death ~ C(boss) + hp + maxhp + pots + deck + ups + curse + basic + relics + hall_loss + elite_loss' if a<4
      else 'death ~ hp + maxhp + pots + deck + ups + curse + basic + relics') for a in (1,2,3,4)}
M={}
for a in (1,2,3,4):
    d=D[D.act==a]
    M[a]=smf.logit(F[a],d).fit(disp=0)
    mc=smf.logit(F[a],d).fit(disp=0, cov_type='cluster', cov_kwds={'groups':d.seed})
    b,se=mc.params,mc.bse
    print(f'act{a} boss fights n={len(d)} deaths={d.death.sum()} ({d.death.mean()*100:.1f}%)')
    print('   ' + '  '.join(f'{k} {b[k]:+.4f}±{se[k]:.4f}' for k in ['hp','maxhp','pots','deck','ups','curse','basic','relics','hall_loss','elite_loss'] if k in b))
    print(f'   one potion = {b.pots/b.hp:.1f} HP of entry HP (coefficient ratio); mean d(death)/dHP {(M[a].predict(d)*(1-M[a].predict(d))*b.hp).mean()*100:+.2f} pp per HP')
def lever(name, act, mod, mask=None):
    d=D[D.act==act].copy()
    if mask is not None: d=d[mask(d)]
    p0=M[act].predict(d); p1=M[act].predict(mod(d.copy()))
    c=np.array([cont[(act,k)] for k in d.nth])
    print(f'  {name:45s} act{act}: fights {len(d):5d}, fight death {(p1-p0).mean()*100:+6.2f} pp, run Heart kill {((p0-p1)*c).sum()/N*100:+.2f} pp')
print('levers (observational upper bounds; confounded by deck strength):')
for a in (1,2,3,4):
    lever('+5 HP at boss entry', a, lambda d: d.assign(hp=np.minimum(d.hp+5, d.maxhp)))
    lever('+10 HP at boss entry', a, lambda d: d.assign(hp=np.minimum(d.hp+10, d.maxhp)))
    lever('+1 potion at boss entry if a slot is free', a, lambda d: d.assign(pots=np.minimum(d.pots+1, d.cap)))
lever('rest instead of pre-boss Ruby Recall at <60% HP', 3, lambda d: d.assign(hp=np.minimum(d.hp+(0.3*d.maxhp).round(), d.maxhp)), mask=lambda d: d.rec_low==1)
