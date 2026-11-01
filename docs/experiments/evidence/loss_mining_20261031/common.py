import pickle, sys, collections, numpy as np
sys.path.insert(0, __file__.rsplit('/',1)[0]); from names import *
def load(*fs):
    G=[]
    for f in fs: G+=pickle.load(open(f,'rb'))
    return G
def rests(g):
    st=g['states']; out=[]; seen=set()
    for k,s in enumerate(st):
        if s['screen']!=7 or s['floor'] in seen: continue
        seen.add(s['floor'])
        nx=next((t for t in st[k+1:] if t['floor']>s['floor']), None)
        if nx is None: nx=st[-1]
        if nx['keys'][0]>s['keys'][0]: c='recall'
        elif nx['hp']>s['hp'] and nx['hp']-s['hp']>=min(0.25*s['maxhp'], s['maxhp']-s['hp'])-1: c='rest'
        elif nx['ups']>s['ups']: c='smith'
        elif len(nx['relics'])>len(s['relics']): c='dig'
        elif nx['deckn']<s['deckn']: c='toke'
        elif nx['maxhp']>s['maxhp']: c='lift'
        else: c='other'
        out.append(dict(floor=s['floor'],act=s['act'],hp=s['hp'],maxhp=s['maxhp'],c=c,keys=s['keys']))
    return out
def isboss(fi): return fi['room']=='BOSS' or ENC[fi['enc']] in ('THE_HEART','SHIELD_AND_SPEAR')
def hpb(frac): return '<50' if frac<.5 else '50-70' if frac<.7 else '70-85' if frac<.85 else '85+'
