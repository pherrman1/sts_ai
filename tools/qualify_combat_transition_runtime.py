#!/usr/bin/env python3
"""Fixed captured-state CPU parity and validity; no gameplay seeds or fitting."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools import combat_transition_composed as c
from tools.export_combat_transition_runtime import PROBABILITY_TOLERANCE


def fixtures(source, output):
    models=c.FrozenModels();rows=[];seen=set();buckets=set()
    source=Path(source)
    receipt=json.loads(source.with_name('preflight.json').read_text())
    with source.open('rb') as stream:
        actual=hashlib.file_digest(stream,'sha256').hexdigest()
    if actual!=receipt['savedTestRowsSha256']:raise ValueError('captured TEST fixture provenance mismatch')
    data=[json.loads(line) for line in Path(source).open()]
    # Cover all act/room strata, then special outcomes and counter-bearing rows.
    predicates=[]
    for act in (1,2,3):
        for room in (3,4,6):
            predicates.append((f'act{act}_room{room}',lambda r,a=act,t=room:r['predictorInput']['globals']['act']==a and r['predictorInput']['globals']['roomClass']==t))
    predicates += [('healing',lambda r:r['win'] and r['post']['curHp']>r['pre']['curHp']),('loss',lambda r:r['win'] and r['post']['curHp']<r['pre']['curHp']),('unchanged',lambda r:r['win'] and r['post']['curHp']==r['pre']['curHp']),('maxhp',lambda r:r['win'] and r['post']['maxHp']!=r['pre']['maxHp']),('potion_use',lambda r:r['win'] and r['post']['potions']!=r['pre']['potions']),('potion_no_use',lambda r:r['win'] and r['post']['potions']==r['pre']['potions']),('multiple_groups',lambda r:len({c.relic.TRAJECTORY[c.relic.NAMES[x['id']]][0] for x in r['pre']['relics'] if x['id'] in c.relic.NAMES and c.relic.NAMES[x['id']] in c.relic.TRAJECTORY})>=2)]
    for label,predicate in predicates:
        for r in data:
            if r['index'] in seen or not predicate(r):continue
            if c.full_support_reasons(r['pre'],r['predictorInput'],models):continue
            if any(x['id']==c.base._RELIC_IDS['INSERTER'] for x in r['pre']['relics']):continue
            seen.add(r['index']);r=copy.deepcopy(r);r['fixtureLabel']=label
            if r['win']:
                r['delta']=models.delta_values.tolist().index(r['post']['maxHp']-r['pre']['maxHp'])
                r['hpClass']=r['post']['curHp']-r['pre']['curHp']+160;r['fraction']=r['post']['curHp']/r['post']['maxHp']
                r['mask']=sum(1<<i for i in range(5) if r['pre']['potions'][i]!=r['post']['potions'][i])
            rows.append(r);buckets.add(label);break
        else:raise ValueError(f'no supported fixture for {label}')
    # Captured fixture mutations test conservative fallback before any learned draw.
    negative=[]
    for label in ('hp_envelope','bad_misc','bad_potion_rng','smoke','entropic','active_lizard','inserter'):
        r=copy.deepcopy(rows[0]);r['fixtureLabel']='fallback_'+label
        if label=='hp_envelope':r['pre']['maxHp']=r['predictorInput']['globals']['maxHp']=173
        elif label in ('bad_misc','bad_potion_rng'):
            i=2 if label=='bad_misc' else 4;r['pre']['combatRng'][i]['seed0']=r['pre']['combatRng'][i]['seed1']=0
        elif label in ('smoke','entropic'):
            pid=c.base._POTION_IDS['SMOKE_BOMB' if label=='smoke' else 'ENTROPIC_BREW']
            r['pre']['potions'][0]=r['predictorInput']['potions'][0]['potionId']=pid
            count=sum(x>1 for x in r['pre']['potions']);r['pre']['potionCount']=r['predictorInput']['globals']['potionCount']=count
        else:
            rid=c.base._RELIC_IDS['LIZARD_TAIL' if label=='active_lizard' else 'INSERTER']
            data=1 if label=='active_lizard' else 0
            r['pre']['relics'].append(dict(id=rid,data=data));r['predictorInput']['relics'].append(dict(relicId=rid,data=data,orderIndex=len(r['predictorInput']['relics'])))
        negative.append(r)
    rows.extend(negative)
    Path(output).write_text(''.join(json.dumps(r)+'\n' for r in rows))
    return rows


def qualify(model, probe, fixturePath, output, smoke=False):
    rows=[json.loads(line) for line in Path(fixturePath).open()]
    models=c.FrozenModels();models.torch.set_num_threads(1)
    command=[str(Path(probe).resolve()),str(Path(model).resolve()),str(Path(fixturePath).resolve())]
    if smoke:command.append('smoke')
    run=subprocess.run(command,text=True,capture_output=True,check=True)
    Path(output).with_suffix('.native.jsonl').write_text(run.stdout)
    native=[json.loads(line) for line in run.stdout.splitlines()]
    if len(native)!=len(rows):raise ValueError('native fixture count')
    errors={g:0. for g in ('survival','max_hp','hp','potion','relic_turns','relic_attacks','relic_cards','relic_shuffles')};masks=True;support=True
    with models.torch.inference_mode():
        for r,n in zip(rows,native):
            reasons=c.full_support_reasons(r['pre'],r['predictorInput'],models)
            # Explicit conservative runtime exclusion required by the handoff.
            if any(x['id']==c.base._RELIC_IDS['INSERTER'] for x in r['pre']['relics']):reasons=['unsupported_inserter']
            support &= n['supported']==(not reasons)
            if reasons:continue
            inputs=models.encode_visible(r['predictorInput']);z=models.hp_encoding(inputs)
            delta=r.get('delta',0);fraction=np.float32(r.get('fraction',.5));hpClass=r.get('hpClass',160);mask=r.get('mask',0)
            expected=dict(survival=models.survival(inputs),max_hp=models.max_hp(inputs),hp=models.hp_distribution(z,delta,r['pre']['curHp'],r['pre']['maxHp']+int(models.delta_values[delta])),potion=models.potion_distribution(inputs,r['pre'],delta,fraction))
            expected.update({'relic_'+g:p for g,p in models.relic_distribution(z,hpClass,fraction,mask).items()})
            for g,p in expected.items():
                q=n['relic'][g.removeprefix('relic_')] if g.startswith('relic_') else n[g]
                p=np.asarray(p,dtype=float);q=np.asarray(q,dtype=float)
                if p.shape!=q.shape or not np.isfinite(q).all():raise ValueError('domain/nonfinite '+g)
                errors[g]=max(errors[g],float(np.max(np.abs(p-q))))
                if g=='hp':
                    legal=c.hp.legal_support(models.classes,np.asarray([r['pre']['curHp']]),np.asarray([r['pre']['maxHp']+int(models.delta_values[delta])]))[0]
                    masks &= np.array_equal(legal,np.asarray(n['hpLegal'])) and bool(np.all(q[~legal]==0))
                elif g=='potion':
                    legal=c.potion.legal_masks(np.asarray([r['pre']['potions']]),np.asarray([r['pre']['potionCapacity']]))[0]
                    masks &= np.array_equal(legal,np.asarray(n['potionLegal'])) and bool(np.all(q[~legal]==0))
    report=dict(tolerance=PROBABILITY_TOLERANCE,fixtures=len(rows),fixtureSha256=hashlib.sha256(Path(fixturePath).read_bytes()).hexdigest(),modelSha256=hashlib.sha256(Path(model).read_bytes()).hexdigest(),maxAbsoluteErrors=errors,supportParity=support,legalMasksIdentical=masks,finite=True,passParity=support and masks and max(errors.values())<=PROBABILITY_TOLERANCE)
    if smoke:
        invalid={};components={};componentRows=0;deaths=victories=0;deathTime=victoryTime=supportTime=0
        for n in native:
            if 'smoke' not in n:continue
            componentRows+=1
            for k,v in n.get('componentsNs',{}).items():components[k]=components.get(k,0)+v
            s=n['smoke'];deaths+=s['death'];victories+=s['victory'];deathTime+=s['death_ns']*s['death'];victoryTime+=s['victory_ns']*s['victory'];supportTime+=s['support_ns']*s['draws']
            for k,v in s['invalid'].items():invalid[k]=invalid.get(k,0)+v
        report['componentNs']={k:v/componentRows for k,v in components.items()}
        report['smoke']=dict(deaths=deaths,victories=victories,invalid=invalid,supportNs=supportTime/(deaths+victories),deathNs=deathTime/deaths if deaths else None,victoryNs=victoryTime/victories if victories else None)
    Path(output).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    if not report['passParity']:raise SystemExit('NATIVE_PROBABILITY_PARITY_FAILED')
    if smoke and any(report['smoke']['invalid'].values()):raise SystemExit('NATIVE_SAMPLING_SMOKE_FAILED')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='mode',required=True)
    prepare=sub.add_parser('fixtures');prepare.add_argument('--source',required=True);prepare.add_argument('--output',required=True)
    run=sub.add_parser('parity');run.add_argument('--model',required=True);run.add_argument('--probe',required=True);run.add_argument('--fixtures',required=True);run.add_argument('--output',required=True);run.add_argument('--smoke',action='store_true')
    a=parser.parse_args()
    if a.mode=='fixtures':print('fixtures',len(fixtures(a.source,a.output)))
    else:qualify(a.model,a.probe,a.fixtures,a.output,a.smoke)
