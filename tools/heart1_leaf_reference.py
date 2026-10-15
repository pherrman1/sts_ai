"""Frozen §490 CPU value-net reference on fresh records; no fitting.

Architecture and transforms mirror evidence/ooc_sibling_leaf_capture_20261015/train_value.py.
The old validation-selected checkpoint remains exploratory and keys-off trained.
"""
import math
import torch
from torch import nn


class Reference(nn.Module):
    def __init__(self,n_dense):
        super().__init__()
        self.deck=nn.EmbeddingBag(1024,64,mode='sum');self.rel=nn.EmbeddingBag(256,64,mode='sum')
        self.pot=nn.EmbeddingBag(64,64,mode='sum');self.off=nn.EmbeddingBag(1024,64,mode='sum')
        self.roff=nn.EmbeddingBag(256,64,mode='sum');self.poff=nn.EmbeddingBag(64,64,mode='sum')
        self.mlp=nn.Sequential(nn.Linear(n_dense+384,256),nn.ReLU(),nn.Linear(256,256),nn.ReLU(),nn.Linear(256,1))
    def forward(self,dense,bags):
        parts=[dense]+[m(i,o) for m,(i,o) in zip([self.deck,self.rel,self.pot,self.off,self.roff,self.poff],bags)]
        return self.mlp(torch.cat(parts,1)).squeeze(1)


def old_features(rec,row):
    fo=rec['obs.fixed_observation'];y0=rec['obs.mapY'];ahead=[0.]*8
    for y,t in zip(rec['obs.map.ys'],rec['obs.map.roomTypes']):
        if y>y0 and 0<=t<8:ahead[t]+=1
    dense=[x/100 for x in fo]+[v/20 for v in ahead]+[y0/15,row['act']/3,row['floor']/50,
        len(rec['obs.deck.cards'])/30,sum(rec['obs.deck.upgrades'])/10,len(rec['fixed_actions'])/5,len(rec['paths_offered'])/7]
    scr=[0.]*9;scr[min(rec['screen_state'],8)]=1
    sel=[0.]*16;sel[min(rec['select_screen_type'],15)]=1
    dense+=scr+sel+[math.log(max(row['x2b'],1e-4)/max(1-row['x2b'],1e-4))]
    bags=[[c*2+u for c,u in zip(rec['obs.deck.cards'],rec['obs.deck.upgrades'])],rec['obs.relics.relics'],rec['obs.potions'],
        [c*2+u for c,u in zip(rec['cards_offered.cards'],rec['cards_offered.upgrades'])],rec['relics_offered'],rec['potions_offered']]
    return dense,bags


def predict_reference(checkpoint,rows):
    state=torch.load(checkpoint,map_location='cpu',weights_only=True)
    model=Reference(state['mlp.0.weight'].shape[1]-384);model.load_state_dict(state);model.eval()
    out=[]
    with torch.no_grad():
        for at in range(0,len(rows),256):
            features=[old_features(r['record'],r) for r in rows[at:at+256]]
            dense=torch.tensor([f[0] for f in features]);bags=[]
            for j in range(6):
                ids=[];offsets=[]
                for _,b in features:offsets.append(len(ids));ids+=b[j]
                bags.append((torch.tensor(ids,dtype=torch.long),torch.tensor(offsets,dtype=torch.long)))
            out+=torch.sigmoid(model(dense,bags)).tolist()
    return out
