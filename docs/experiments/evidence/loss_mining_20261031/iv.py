import sys; sys.path.insert(0, sys.argv[0].rsplit('/',1)[0]); from common import *
import pandas as pd, statsmodels.formula.api as smf
G=load(*sys.argv[1:])
rows=[]
for g in G:
    st=g['states']; fs=g['fights']
    for act in (1,2,3):
        bs=[f for f in fs if f['act']==act and f['room']=='BOSS']
        if not bs: continue
        b=bs[0]
        offers=0; seen=set()
        for s in st:
            if s['act']==act and s['screen']==2 and s['potions_offered'] and s['floor']<b['floor'] and s['floor'] not in seen:
                seen.add(s['floor']); offers+=len(s['potions_offered'])
        nf=sum(1 for f in fs if f['act']==act and f['floor']<b['floor'])
        ne=sum(1 for f in fs if f['act']==act and f['floor']<b['floor'] and f['room']=='ELITE')
        st0=next(s for s in st if s['act']==act)
        rows.append(dict(seed=g['seed'],act=act,boss=ENC[b['enc']],offers=offers,nf=nf,ne=ne,pots=len(b['pots']),hp=b['hp'],maxhp=b['maxhp'],
                         death=int(b['post']<=0), hp0=st0['hp'], deck0=st0['deckn'], pots0=len(st0['pots'])))
D=pd.DataFrame(rows)
for act in (1,2,3):
    d=D[D.act==act]
    fs=smf.ols('pots ~ offers + nf + ne + hp0 + deck0 + pots0 + C(boss)',d).fit(cov_type='HC1')
    rf=smf.ols('death ~ offers + nf + ne + hp0 + deck0 + pots0 + C(boss)',d).fit(cov_type='HC1')
    hpm=smf.ols('hp ~ offers + nf + ne + hp0 + deck0 + pots0 + C(boss)',d).fit(cov_type='HC1')
    iv=rf.params.offers/fs.params.offers
    se=abs(iv)*np.sqrt((rf.bse.offers/rf.params.offers)**2+(fs.bse.offers/fs.params.offers)**2)
    print(f'act{act} n={len(d)}: first stage potions per offer {fs.params.offers:+.3f} (F~{(fs.params.offers/fs.bse.offers)**2:.0f}); reduced form death per offer {rf.params.offers*100:+.2f}pp ± {rf.bse.offers*100:.2f}; HP per offer {hpm.params.offers:+.2f}; Wald IV death per potion {iv*100:+.1f}pp ± {se*100:.1f} (ignores HP channel)')
