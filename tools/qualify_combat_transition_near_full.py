#!/usr/bin/env python3
"""Captured-state native probability, complete RAW and planner-stream parity."""
import argparse,copy,hashlib,json,subprocess
from collections import Counter
from pathlib import Path
import numpy as np
import torch
from tools import combat_transition_composed as c,combat_transition_near_full_models as models
from tools import combat_transition_near_full_support as support,combat_transition_near_full_sampler as s
from tools import combat_transition_potion_trajectory as t,combat_transition_gold as gold

class Tape:
    def __init__(self,words):self.words=words;self.used=0;self.bit_generator=self
    def random_raw(self):
        if self.used>=len(self.words):raise ValueError('planner tape exhausted')
        word=int(self.words[self.used]);self.used+=1;return word
    def random(self):return min(self.random_raw()/2**64,np.nextafter(1.,0.))
    def choice(self,n,p):
        p=np.asarray(p,float);return min(int(np.searchsorted(np.cumsum(p/p.sum()),self.random(),side='right')),n-1)


def fixtures(parent,output):
    if output.exists():raise ValueError('refusing fixture overwrite')
    rows=list(map(json.loads,(parent/'full-union-test-states-v1.jsonl').open()));allowed=[r for r in rows if not support.final_exclusions(r['pi'],r['pre'])];selected={}
    predicates={ 'previous179':lambda r:r['old'],'death':lambda r:r['outcome']==c.base.DEATH,'gold':lambda r:any(card['cardId']==c.base._CARD_IDS['HAND_OF_GREED'] for card in r['pi']['cards']),'looter':lambda r:gold.encounter_name(r['pi']['globals']['encounter'])=='LOOTER','twoThieves':lambda r:gold.encounter_name(r['pi']['globals']['encounter'])=='TWO_THIEVES','ritual':lambda r:any(card['id']==c.base._CARD_IDS['RITUAL_DAGGER'] for card in r['pre']['deck']),'ritualPlus':lambda r:any(card['id']==c.base._CARD_IDS['RITUAL_DAGGER'] and card['upgraded'] for card in r['pre']['deck']),'writhing':lambda r:r['pi']['globals']['encounter']==c.base.WRITHING_MASS_ID,'writhingOmamori':lambda r:r['pi']['globals']['encounter']==c.base.WRITHING_MASS_ID and any(v['id']==c.base._RELIC_IDS['OMAMORI'] and v['data']>0 for v in r['pre']['relics']),'writhingDarkstone':lambda r:r['pi']['globals']['encounter']==c.base.WRITHING_MASS_ID and any(v['id']==c.base._RELIC_IDS['DARKSTONE_PERIAPT'] for v in r['pre']['relics']),'brew':lambda r:t.BREW in r['pre']['potions'],'brewSozu':lambda r:t.BREW in r['pre']['potions'] and any(v['id']==c.base._RELIC_IDS['SOZU'] for v in r['pre']['relics'])}
    for label,fn in predicates.items():
        row=next((r for r in allowed if fn(r)),None)
        if row is not None:selected[row['index']]=copy.deepcopy(row)
    audit=json.loads((parent/'brew-native-label-audit-v1.json').read_text());recursive={r['index'] for r in audit['recursiveExamples']}
    for r in allowed:
        if r['index'] in recursive:selected[r['index']]=copy.deepcopy(r)
    for label in support.FINAL_EXCLUSIONS:
        row=next(r for r in rows if label in support.final_exclusions(r['pi'],r['pre']));selected[row['index']]=copy.deepcopy(row)
    result=[]
    for r in selected.values():
        r['predictorInput']=r.pop('pi');r.update(delta=0,ending=min(r['pre']['curHp'],r['pre']['maxHp']),maximum=r['pre']['maxHp'],mask=0,consumed=[],escaped=False,dagger=[0 for card in r['pre']['deck'] if card['id']==c.base._CARD_IDS['RITUAL_DAGGER']],draws=256 if t.BREW in r['pre']['potions'] else 32);result.append(r)
    output.write_text(''.join(json.dumps(r)+'\n' for r in result));return result


def qualify(parent,artifact,probe,fixture,output):
    if output.exists():raise ValueError('refusing qualification overwrite')
    rows=fixtures(parent,fixture);torch.set_num_threads(1);m,nets,bindings=models.load(parent,'cpu');sampler=s.NearFullSampler(parent,device='cpu');assert sampler.bindings==bindings
    run=subprocess.run([str(probe.resolve()),str(artifact.resolve()),str(fixture.resolve()),'near-full'],capture_output=True,text=True,check=True);output.with_suffix('.native.jsonl').write_text(run.stdout);native=list(map(json.loads,run.stdout.splitlines()));assert len(rows)==len(native);errors=Counter();counts=Counter();checks=0
    def compare(name,a,b):
        a=np.asarray(a,float);b=np.asarray(b,float)
        if a.shape!=b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():raise ValueError('shape/nonfinite '+name)
        errors[name]=max(errors[name],float(np.max(abs(a-b))))
    original_trace=t.sample
    traced=[]
    def trace(*args,**kwargs):
        result=original_trace(*args,**kwargs);traced.append(result);return result
    t.sample=trace
    with torch.inference_mode():
        for row,n in zip(rows,native):
            pre,pi=row['pre'],row['predictorInput'];why=support.final_reasons(pi,pre,m)
            if n['supported']!=(not why):raise ValueError('runtime support parity')
            if why:counts['failClosedFixtures']+=1;continue
            checks+=1;inputs=m.encode_visible(pi);z=m.hp_encoding(inputs);zp=m.fp32_encoding(m.potion_encoder.encoder,inputs).cpu().numpy();d=row['delta'];ending=row['ending'];maximum=row['maximum'];mask=row['mask'];consumed=row['consumed'];esc=row['escaped'];diag=n['diagnostics'];raw_z=z.cpu().numpy()[0]
            compare('survival',[m.survival(inputs)],[n['survival']]);compare('maxHP',m.max_hp(inputs),n['maxHp']);compare('hp',m.hp_distribution(z,d,pre['curHp'],maximum),n['hp']);compare('hpEncoding',raw_z,diag['hpEncoding']);compare('potionEncoding',zp[0],diag['potionEncoding'])
            lp=t.log_probabilities(m.potion_net,zp,[pre['potions']],[pre['potionCapacity']],[d],[ending/maximum],[gold.encounter_name(pi['globals']['encounter']) in t.BOSSES]);compare('potion',lp[0].exp().cpu().numpy(),diag['potion'])
            hp,bits,mechanical,features=s.conditions(pre,pi,ending,maximum,mask,consumed,esc)
            for name,value in [('hpConditions',hp),('bits',bits),('mechanical',mechanical),('eventConditions',features)]:compare(name,value,diag[name])
            relic=nets['relic'](z,torch.tensor([ending-pre['curHp']+160]),torch.tensor([ending/maximum]),torch.tensor([mask]),torch.tensor([float(esc)]))
            for group in c.TRAINED_GROUPS:compare('relic_'+group,torch.softmax(relic[group],-1)[0].numpy(),diag['relic'][group])
            if 'writhing' in diag:_,prob=s.writhing_probabilities(nets['writhing'],raw_z,pre,pi,ending,maximum,mask,consumed,esc);compare('writhing',prob,diag['writhing'])
            candidates,prob=s.ritual_probabilities(nets['ritual'],raw_z,pre,pi,ending,maximum,mask,consumed,esc)
            if list(map(list,candidates))!=diag['ritualCandidates']:raise ValueError('native Dagger candidate parity')
            compare('ritual',prob,diag['ritual']);posts,prob=s.gold_probabilities(nets['gold'],raw_z,pre,pi,ending,maximum,mask,consumed,esc,row['dagger'])
            if list(map(list,posts))!=diag['goldCandidates']:raise ValueError('native gold candidate parity')
            compare('gold',prob,diag['gold'])
            for sample in n['samples']:
                traced.clear();tape=Tape(sample['words']);expected=sampler.sample_transition(pre,pi,tape);outcome={'DEATH':1,'VICTORY':2,'ESCAPE':3}[expected.outcome]
                if outcome!=sample['outcome']:raise ValueError(f'sampled outcome differs at row{row["index"]}')
                if outcome!=1 and expected.post_state!=sample['rawPost']:raise ValueError(f'complete sampled RAW differs at row{row["index"]}: '+str([k for k in expected.post_state if expected.post_state[k]!=sample['rawPost'][k]]))
                if tape.used!=sample['wordsUsed']:raise ValueError('planner advanced stream mismatch')
                counts['samples']+=1;counts[expected.outcome]+=1
                if outcome==1:
                    if tape.used!=1 or sample['rawPost']['curHp'] or sample['rawPost']['deck']:raise ValueError('death short circuit')
                else:
                    if traced and traced[-1]['brewUses']>sum(v==t.BREW for v in pre['potions']):counts['recursiveBrew']+=1
                    if expected.post_state['combatRng'][4]!=pre['combatRng'][4]:counts['advancedHypotheticalPotionRng']+=1
                    if expected.post_state['potionCount']!=sum(v>1 for v in expected.post_state['potions']):raise ValueError('potion count')
    t.sample=original_trace
    passed=max(errors.values())<=1e-4 and counts['recursiveBrew']>0 and counts['ESCAPE']>0 and counts['advancedHypotheticalPotionRng']>0
    result=dict(modelSha256=c.base.sha256(artifact),fixtureSha256=c.base.sha256(fixture),sources=bindings,fixtures=len(rows),supportedFixtures=checks,counts=counts,maxAbsoluteErrors=errors,probabilityTolerance=1e-4,completeRawStateParity=True,advancedPlannerStreamParity=True,preparedReferenceParity=True,classification='NEAR_FULL_NATIVE_PARITY_'+('PASS' if passed else 'FAIL'))
    c.base.json_dump(output,result);print(json.dumps(result),flush=True)
    if not passed:raise ValueError('native parity gate failed')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--artifact',type=Path,required=True);p.add_argument('--probe',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();qualify(a.parent,a.artifact,a.probe,a.fixture,a.output)
