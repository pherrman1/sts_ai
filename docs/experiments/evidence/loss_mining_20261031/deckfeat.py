import sys; sys.path.insert(0, sys.argv[0].rsplit('/',1)[0]); from common import *
import pandas as pd, statsmodels.formula.api as smf
G=load(*sys.argv[1:])
AOE={'CLEAVE','WHIRLWIND','THUNDERCLAP','IMMOLATE','REAPER'}
rows=[]
for g in G:
    for fi in g['fights']:
        if fi['room'] not in ('BOSS','ELITE') and ENC[fi['enc']]!='THE_HEART': continue
        names=[CARD[c] for c,u in fi['deck']]
        rows.append(dict(seed=g['seed'],enc=ENC[fi['enc']],act=fi['act'],hp=fi['hp'],pots=len(fi['pots']),deck=len(names),
            power=sum(CTYPE[c]=='POWER' for c,u in fi['deck']),aoe=sum(n in AOE for n in names),
            attack=sum(CTYPE[c]=='ATTACK' for c,u in fi['deck']),basic=sum(n in ('STRIKE_RED','DEFEND_RED') for n in names),
            ups=sum(u for c,u in fi['deck']),death=int(fi['post']<=0)))
D=pd.DataFrame(rows)
for e in ['THE_HEART','AWAKENED_ONE','COLLECTOR','TIME_EATER','DONU_AND_DECA','AUTOMATON','CHAMP','HEXAGHOST','SLIME_BOSS','THE_GUARDIAN','GREMLIN_LEADER','SLAVERS','BOOK_OF_STABBING','REPTOMANCER','GIANT_HEAD','THREE_SENTRIES','GREMLIN_NOB','LAGAVULIN']:
    d=D[D.enc==e]
    out=[f'{e:17s} n={len(d):5d} death={d.death.mean()*100:4.1f}%  mean power={d.power.mean():.1f} aoe={d.aoe.mean():.2f} deck={d.deck.mean():.0f}']
    for feat in ('power','aoe','deck','basic'):
        try:
            m=smf.logit(f'death ~ hp + pots + {feat}',d).fit(disp=0)
            out.append(f'{feat}: OR {np.exp(m.params[feat]):.2f} (z {m.params[feat]/m.bse[feat]:+.1f})')
        except Exception as ex: out.append(f'{feat}: -')
    print(' | '.join(out))
