"""Gold2 per-decision breakdown: heuristic (chosen) vs V4 Q argmax, by decision type."""
import re, sys, json, numpy as np, pandas as pd
REPO='/home/user/sts_ai'; G='/root/gold/'
def enum_strings(path, marker):
    s=open(path).read(); i=s.index(marker); j=s.index('};',i); return re.findall(r'"([^"]*)"',s[i:j])
CARDS=enum_strings(REPO+'/include/constants/Cards.h','cardEnumStrings[]')
RELICS=enum_strings(REPO+'/include/constants/Relics.h','relicEnumNames[]')
EVENTS=enum_strings(REPO+'/include/constants/Events.h','eventIdStrings[]')
POTS=enum_strings(REPO+'/include/constants/Potions.h','potionEnumNames') if 'potionEnumNames' in open(REPO+'/include/constants/Potions.h').read() else []
ROOMS=['SHOP','REST','EVENT','ELITE','MONSTER','TREASURE','BOSS','BOSS_TREASURE','NONE','INVALID']
REST=['REST','SMITH','RECALL','LIFT','TOKE','DIG','SKIP']
SCR={1:'EVENT',2:'REWARDS',3:'BOSS_RELIC',4:'UPGRADE',5:'MAP',6:'TREASURE',7:'REST',8:'SHOP'}
nm=lambda L,i: L[i] if 0<=i<len(L) else str(i)
def desc(r):
    s=SCR.get(r.screen,str(r.screen)); t=int(r.actionType); c1,c2,k1=int(r.c1),int(r.c2),int(r.cand1)
    if s=='REWARDS':
        if t==0: return 'skip card' if c2==5 else 'take '+nm(CARDS,k1)
        return ['card','gold','key','potion','relic','remove','skip'][t] if 0<=t<7 else str(t)
    if s=='SHOP':
        return {0:'buy card '+nm(CARDS,k1),3:'buy potion',4:'buy relic '+nm(RELICS,k1),5:'remove',6:'leave'}.get(t,str(t))
    if s=='MAP': return nm(ROOMS,int(r.cand3))
    if s=='REST': return nm(REST,c1)
    if s=='EVENT': return f'{nm(EVENTS,k1)} opt{c1}'
    if s=='BOSS_RELIC': return 'skip' if k1<0 else nm(RELICS,k1)
    if s=='UPGRADE': return nm(CARDS,k1)
    if s=='TREASURE': return 'open' if c1==0 else f'opt{c1}'
    return f'{t}/{c1}'
def coarse(s, d):
    if s=='REWARDS': return 'skip card' if d=='skip card' else ('take card' if d.startswith('take') else d)
    if s=='SHOP': return d.split(' ')[0]+(' '+d.split(' ')[1] if d.startswith('buy') else '')
    if s=='EVENT': return d.split(' opt')[0]
    if s in('UPGRADE','BOSS_RELIC'): return 'pick'
    return d
