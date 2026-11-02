import re
import os
ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../../../include/constants/')
def enum(fn, name):
    t=open(ROOT+fn).read()
    i=t.index('enum class '+name); j=t.index('{',i); k=t.index('}',j)
    body=re.sub(r'//[^\n]*','',t[j+1:k])
    out=[]; v=-1
    for part in body.split(','):
        p=part.strip()
        if not p: continue
        if '=' in p:
            n,val=p.split('='); v=int(val.strip(),0); out.append((n.strip(),v))
        else:
            v+=1; out.append((p,v))
    return {v:n for n,v in out}
ENC=enum('MonsterEncounters.h','MonsterEncounter')
CARD=enum('Cards.h','CardId')
RELIC=enum('Relics.h','RelicId')
POT=enum('Potions.h','Potion')
ROOM=enum('Rooms.h','Room')
def _arr(fn, name, prefix):
    t=open(ROOT+fn).read(); i=t.index(name+'[] = {'); j=t.index('{',i); k=t.index('}',j)
    return [x.strip().replace(prefix,'') for x in t[j+1:k].split(',') if x.strip()]
CTYPE=_arr('Cards.h','cardTypes','CardType::')
CRAR=_arr('Cards.h','cardRarities','CardRarity::')
