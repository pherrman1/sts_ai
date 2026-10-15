#!/usr/bin/env python3
"""Frozen expanded-support qualification using the existing composed evaluator."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import numpy as np
from tools import combat_transition_composed_evaluate as e
from tools import combat_transition_composed as c

BASELINE='74d31681b8ebd3beb5e85d6db9c1a164f9aeaf13'
HISTORICAL=c.RUNS/'composed-transition-20260914/qualification'
EVIDENCE=c.base._ROOT/'docs/experiments/evidence/composed_transition_2026-09-14.json'
EXPECTED={'OLD':32164,'RECOVERED':9290,'EXPANDED':41454}
TOLERANCE=1e-5


def old_card_ids():
    text=(c.base._ROOT/'include/constants/Cards.h').read_text()
    colors=re.findall(r'CardColor::([A-Z]+)',re.search(r'cardColors\[\]\s*=\s*\{(.*?)\};',text,re.S)[1])
    return {i for i,color in enumerate(colors) if color in ('RED','COLORLESS','CURSE')}


def old_certified(pi,audited):
    return (pi['globals']['characterClass']==c.base.IRONCLAD_ID
            and all(x['cardId'] in audited for x in pi['cards'])
            and all(x['potionId']!=c.base.ENTROPIC_BREW_ID for x in pi['potions']))


def partition_masks(rows,models):
    audited=old_card_ids(); old=[]; recovered=[]; expanded=[]; identities=set()
    for r in rows:
        identity=(r['index'],r['source'])
        if identity in identities: raise ValueError('duplicate TEST row identity')
        identities.add(identity)
        current=not c.full_support_reasons(r['pre'],r['predictorInput'],models)
        if current!=r['supported']: raise ValueError('current support differs from prepared handoff')
        certified=old_certified(r['predictorInput'],audited)
        # The pre-#178 predicate differed only in potion certification. If old
        # certification succeeded, all remaining full-support checks are identical.
        old.append(current and certified); recovered.append(current and not certified); expanded.append(current)
        pi=r['predictorInput']
        generator=any(x['cardId']==c.base._CARD_IDS['ALCHEMIZE'] for x in pi['cards'])
        brew=any(x['potionId']==c.base.ENTROPIC_BREW_ID for x in pi['potions'])
        if current and (generator or brew): raise ValueError('explicit generation inside support')
    masks={k:np.asarray(v,bool) for k,v in zip(EXPECTED,(old,recovered,expanded))}
    prove_partitions(masks,EXPECTED)
    return masks


def prove_partitions(masks,expected):
    if np.any(masks['OLD'] & masks['RECOVERED']) or not np.array_equal(masks['OLD'] | masks['RECOVERED'],masks['EXPANDED']):
        raise ValueError('support sets are not a disjoint union')
    if {k:int(v.sum()) for k,v in masks.items()}!=expected: raise ValueError('support partition counts differ')


def prepare(output):
    if output.exists(): raise ValueError('refusing to overwrite expanded evidence')
    output.mkdir(parents=True)
    e.prepare(output/'expanded')
    rows=[json.loads(s) for s in (output/'expanded/test_rows.jsonl').read_text().splitlines()]
    masks=partition_masks(rows,c.FrozenModels('cpu'))
    historical=json.loads(EVIDENCE.read_text())
    old_preflight=json.loads((HISTORICAL/'preflight.json').read_text())
    if c.base.sha256(HISTORICAL/'test_rows.jsonl')!=historical['provenance']['savedTestRowsSha256']:
        raise ValueError('historical TEST receipt differs')
    old_rows=[json.loads(s) for s in (HISTORICAL/'test_rows.jsonl').read_text().splitlines()]
    if [(r['index'],r['source']) for r in rows]!=[(r['index'],r['source']) for r in old_rows]: raise ValueError('historical TEST identities differ')
    if not np.array_equal(masks['OLD'],[r['supported'] for r in old_rows]): raise ValueError('old full predicate does not reproduce historical membership')
    if e.verify_data()!=old_preflight['hashes']: raise ValueError('historical frozen input hashes differ')
    ids=np.asarray([r['index'] for r in rows]); source=np.asarray([r['source'] for r in rows])
    np.savez_compressed(output/'partitions.npz',rows=ids,source=source,**masks)
    counts={k:dict(rows=int(v.sum()),sources=len(np.unique(source[v])),victories=sum(r['win'] for r,b in zip(rows,v) if b)) for k,v in masks.items()}
    proof=dict(counts=counts,disjoint=True,unionIdentity=True,historicalOldIdentity=True,
               rowIdentity='original corpus index paired with original sourceSeed; TEST order unchanged',
               explicitAlchemizeAndEntropicBrewExcluded=True,partitionsSha256=c.base.sha256(output/'partitions.npz'),
               historicalEvidenceSha256=c.base.sha256(EVIDENCE),baseline=BASELINE)
    c.base.json_dump(output/'partition_proof.json',proof)
    old_dir=output/'old'; old_dir.mkdir()
    old_full=np.load(output/'expanded/full_support.npy'); old_full[ids]=masks['OLD']
    np.save(old_dir/'full_support.npy',old_full)
    with (old_dir/'test_rows.jsonl').open('w') as f:
        for r,b in zip(rows,masks['OLD']):
            r=dict(r,supported=bool(b)); f.write(json.dumps(r)+'\n')
    preflight=json.loads((output/'expanded/preflight.json').read_text())
    preflight.update(savedTestRowsSha256=c.base.sha256(old_dir/'test_rows.jsonl'),fullSupportSha256=c.base.sha256(old_dir/'full_support.npy'),evaluationCohort='OLD historical TEST support; non-TEST support is not scored')
    c.base.json_dump(old_dir/'preflight.json',preflight)
    shutil.copyfile(output/'expanded/recipe.json',old_dir/'recipe.json')
    print(json.dumps(proof),flush=True)


def reproduce_old(output):
    current=json.loads((output/'old/results.json').read_text()); historical=json.loads(EVIDENCE.read_text())
    errors={}
    for group,keys in [('maxHp',('nll','modeAccuracy')),('signedHp',('nll','crps','expectedMae')),('potion',('jointMaskNll','modeExact')),('relic',('constraintNll',))]:
        for key in keys: errors[group+'.'+key]=current['componentReproduction'][group][key]-historical['componentReproduction'][group][key]
    errors['relic.fullVectorExact']=current['componentReproduction']['relic']['reconstructed']['fullVectorExact']-historical['componentReproduction']['relic']['reconstructed']['fullVectorExact']
    for key in ('brier','logloss','auc'): errors['historicalSurvival.'+key]=current['componentReproduction']['survival'][key]-historical['componentReproduction']['survival'][key]
    for key in ('hp','potion','relic'):
        for metric in ('mean','teacherNll','mixtureNll'): errors['exposure.'+key+'.'+metric]=current['exposure'][key][metric]-historical['exposure'][key][metric]
    with np.load(output/'old/exposure.npz') as raw, np.load(HISTORICAL/'exposure.npz') as original:
        if not np.array_equal(raw['rows'],original['rows']): raise ValueError('OLD exposure identities differ')
        for k in ('hp','potion','relic'): errors[k+'.teacherMaxAbs']=float(np.max(np.abs(raw[k+'-teacherNll']-original[k+'-teacherNll'])))
    passed=all(np.isfinite(v) and abs(v)<=TOLERANCE for v in errors.values())
    result=dict(passed=passed,tolerance=TOLERANCE,errors=errors,hardValidity=current['hardValidity'],historicalQualificationPreserved=True)
    c.base.json_dump(output/'old_reproduction.json',result)
    if not passed: raise ValueError('OLD does not reproduce; stop before EXPANDED scoring')
    return result


def component_metrics(raw,selected):
    victories=selected & raw['win']; informative=victories & (raw['observedGroups']>0)
    def avg(key): return e.mean(raw[key][victories])
    return dict(rows=int(selected.sum()),sources=len(np.unique(raw['source'][selected])),victories=int(victories.sum()),
                survival=c.base._binary_metrics(raw['win'][selected].astype(int),raw['pwin'][selected]),
                maxHp=dict(nll=avg('maxNll'),modeAccuracy=avg('maxModeExact')),
                signedHp={k:avg('hp_'+k) for k in ('nll','crps','expectedMae')},
                potion=dict(jointMaskNll=avg('potionNll'),modeExact=avg('potionModeExact')),
                relic=dict(constraintNll=avg('relicNll'),fullVectorModeExact=avg('relicModeExact'),informativeRows=int(informative.sum())))


def exposure_metrics(raw,metrics,selected):
    positions={int(v):i for i,v in enumerate(metrics['rows'])}; loc=np.asarray([positions[int(v)] for v in raw['rows']])
    cohort=selected[loc]; result={}
    for key in ('hp','potion','relic'):
        mask=cohort.copy(); groups=metrics['observedGroups'][loc]
        if key=='relic': mask &= groups>0
        if not mask.any():
            result[key]=dict(mean=None,sourceBootstrap95=None,rows=0,sources=0,decision='NO_INFORMATIVE_ROWS');continue
        mixture=raw['hpExactNll'] if key=='hp' else c.mixture_nll_from_probabilities(raw[key+'-drawMass'])
        teacher=raw[key+'-teacherNll']; differences=(mixture-teacher)[mask]
        if key=='relic': differences=differences/groups[mask]
        score=e.source_gap_bootstrap(metrics['source'][loc][mask],differences)
        score.update(teacherNll=e.mean(teacher[mask]),mixtureNll=e.mean(mixture[mask]),zeroMixtureProbabilityRows=int(np.isposinf(mixture[mask]).sum()),decision='MATERIAL_EXPOSURE_DEGRADATION' if score['mean']>.1 else 'EXPOSURE_OK')
        result[key]=score
    return result


def classify(exposures,validity,reproduction):
    cohorts=('RECOVERED','EXPANDED')
    values=[exposures.get(cohort,{}).get(component,{}).get('mean') for cohort in cohorts for component in ('hp','potion','relic')]
    counts=[validity.get(cohort,{}).get(key) for cohort in cohorts for key in e.VALIDITY_KEYS]
    if not reproduction or any(v is not None and not np.isnan(v) and v!=0 for v in counts) or any(v is not None and v>.1 for v in values):
        return 'EXPANDED_COMPOSED_TRANSITION_REJECTED'
    if any(v is None or not np.isfinite(v) for v in values+counts): return 'EXPANDED_COMPOSED_TRANSITION_INCONCLUSIVE'
    return 'EXPANDED_COMPOSED_TRANSITION_QUALIFIED'


def summarize(output,reviewed_sha):
    proof=json.loads((output/'partition_proof.json').read_text())
    if c.base.sha256(output/'partitions.npz')!=proof['partitionsSha256']: raise ValueError('partition receipt mismatch')
    reproduction=reproduce_old(output)
    with np.load(output/'partitions.npz') as p, np.load(output/'expanded/row_metrics.npz') as metrics, np.load(output/'expanded/exposure.npz') as exposure, np.load(output/'expanded/row_validity.npz') as valid, np.load(output/'expanded/complete_draws.npz') as complete:
        if not np.array_equal(p['rows'],metrics['rows']) or not np.array_equal(p['source'],metrics['source']): raise ValueError('metric identities differ')
        if not np.array_equal(metrics['supported'],p['EXPANDED']): raise ValueError('metric support differs')
        if not np.array_equal(exposure['rows'],p['rows'][p['EXPANDED'] & metrics['win']]): raise ValueError('exposure victory membership differs')
        expected_rows=p['rows'][p['EXPANDED']]
        if not np.array_equal(valid['rows'],expected_rows) or not np.array_equal(complete['rows'],expected_rows): raise ValueError('complete validity membership differs')
        if tuple(valid['keys'])!=e.VALIDITY_KEYS or valid['counts'].shape!=(len(expected_rows),len(e.VALIDITY_KEYS)): raise ValueError('validity dimensions differ')
        for key in ('survived','hp','maxHp','potionMask'):
            if complete[key].shape!=(len(expected_rows),c.RECIPE['draws']): raise ValueError('complete draw dimensions differ')
        actual_draws=int(complete['survived'].size)
        components={k:component_metrics(metrics,p[k]) for k in EXPECTED}
        exposures={k:exposure_metrics(exposure,metrics,p[k]) for k in EXPECTED}
        lookup={int(v):i for i,v in enumerate(p['rows'])}; vl=np.asarray([lookup[int(v)] for v in valid['rows']])
        validity={k:dict(zip(valid['keys'].tolist(),map(int,valid['counts'][p[k][vl]].sum(0)))) for k in EXPECTED}
        rows=[json.loads(s) for s in (output/'expanded/test_rows.jsonl').read_text().splitlines()]
        audited=old_card_ids(); names={v:k for k,v in c.base._CARD_IDS.items()}; slices={}; off_counts=[]; card_counts={}
        for r in rows:
            cards=[x['cardId'] for x in r['predictorInput']['cards'] if x['cardId'] not in audited]; off_counts.append(len(cards))
            for cid in set(cards): card_counts[cid]=card_counts.get(cid,0)+int(p['RECOVERED'][lookup[r['index']]])
        selectors={}
        for act in (1,2,3): selectors[f'act:{act}']=np.asarray([r['predictorInput']['globals']['act']==act for r in rows])
        for room in sorted({r['predictorInput']['globals']['roomClass'] for r in rows}): selectors['combat:'+{2:'event',3:'elite',4:'normal',6:'boss'}.get(room,str(room))]=np.asarray([r['predictorInput']['globals']['roomClass']==room for r in rows])
        off_counts=np.asarray(off_counts)
        for count in sorted(set(off_counts[p['RECOVERED']])): selectors[f'offColorCount:{count}']=off_counts==count
        selectors['offColorPresent']=off_counts>0; selectors['offColorAbsent']=off_counts==0
        for cid,count in sorted(card_counts.items(),key=lambda x:(-x[1],x[0]))[:15]:
            if count>=30: selectors['card:'+names[cid]]=np.asarray([any(x['cardId']==cid for x in r['predictorInput']['cards']) for r in rows])
        for label,mask in selectors.items():
            chosen=mask & p['RECOVERED']
            if chosen.any(): slices[label]=dict(components=component_metrics(metrics,chosen),exposure=exposure_metrics(exposure,metrics,chosen))
        expanded_result=json.loads((output/'expanded/results.json').read_text())
        if validity['EXPANDED']!=expanded_result['hardValidity']: raise ValueError('expanded validity differs from evaluator')
        result=dict(schema='expanded_composed_transition_qualification_v1',baseline=BASELINE,reviewedSha=reviewed_sha,
                    classification=classify(exposures,validity,reproduction['passed']),partitionProof=proof,componentMetrics=components,
                    exposure=exposures,hardValidity=validity,oldReproduction=reproduction,recoveredSlices=slices,
                    commonOffColorCards={names[k]:v for k,v in sorted(card_counts.items(),key=lambda x:-x[1])[:15]},
                    recipe=c.RECIPE,provenance=expanded_result['provenance'],completeDraws=actual_draws,
                    historicalQualification='174 remains qualification of original 62.526% subset',testReuse='engineering validation; not untouched holdout evidence',
                    knowledgeImpact='experiment evidence and maintained research status',training=False,gameplay=False,
                    artifactsUnchanged=expanded_result['artifactsUnchanged'])
    c.base.json_dump(output/'results.json',result)
    receipts={str(p.relative_to(output)):c.base.sha256(p) for p in output.rglob('*') if p.is_file() and p.name!='artifact-hashes.json'}
    c.base.json_dump(output/'artifact-hashes.json',receipts)
    print(json.dumps(dict(classification=result['classification'],counts=proof['counts'],exposure=exposures,validity=validity)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('command',choices=('prepare','evaluate','reproduce-old','summarize'))
    parser.add_argument('--output-dir',type=Path,required=True);parser.add_argument('--reviewed-sha')
    args=parser.parse_args()
    if args.command=='prepare': prepare(args.output_dir)
    elif args.command=='evaluate':
        if not args.reviewed_sha: parser.error('evaluate requires --reviewed-sha')
        if not e.torch.cuda.is_available(): raise ValueError('historical HP AMP scoring requires CUDA access')
        e.run_evaluation(args.output_dir/'old',args.reviewed_sha)
        reproduce_old(args.output_dir)
        e.run_evaluation(args.output_dir/'expanded',args.reviewed_sha)
        summarize(args.output_dir,args.reviewed_sha)
    elif args.command=='reproduce-old': reproduce_old(args.output_dir)
    else:
        if not args.reviewed_sha: parser.error('summarize requires --reviewed-sha')
        if e.snapshot()!=args.reviewed_sha: raise ValueError('summary SHA differs')
        summarize(args.output_dir,args.reviewed_sha)
