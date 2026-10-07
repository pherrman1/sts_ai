#!/usr/bin/env python3
"""Offline qualification of the fixed composed sampler; never fits any model."""
from __future__ import annotations
import argparse
import copy
from collections import Counter
import json
from pathlib import Path
import subprocess
import time
import numpy as np
import torch
from tools import combat_transition_composed as c
from tools import ctm_pins as _pins

PREPARED=Path(_pins.value('combat_transition_composed_evaluate.PREPARED','/tmp/sts-phase2-attention-audit-20260913'))
CORPUS=Path(_pins.value('combat_transition_composed_evaluate.CORPUS',str(c.RUNS/'combat-transition-runtime-25k/combat-transition-25k.jsonl')))
SPLIT=Path(_pins.value('combat_transition_composed_evaluate.SPLIT',str(c.RUNS/'combat-transition-model-v1/split_manifest.json')))
# Frozen prepared representation hashes, established before this experiment.
PREPARED_HASHES={k:v for k,v in c.frozen.EXPECTED_HASHES.items() if not k.endswith('.pt')}
VALIDITY_KEYS=('hpBelow1','hpAboveSampledMaxHp','invalidMaxHpClassOrState','invalidPotionTransition',
               'potionCreationSwapSubstitution','illegalRelicCounter','crossRelicResidueInconsistency',
               'unsupportedMutableRelicMutation','deterministicNativeMismatch','invalidInheritedRngReconstruction',
               'downstreamModelInvokedAfterDeath')


def snapshot():
    return subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()


def verify_data():
    hashes=c.verify_hashes()
    for path,expected in [(CORPUS,c.RECIPE['corpusSha256']),(SPLIT,c.RECIPE['splitSha256']),
                          *[(PREPARED/k,v) for k,v in PREPARED_HASHES.items()]]:
        digest=c.base.sha256(path)
        if digest!=expected: raise ValueError(f'frozen data hash differs: {path}')
        hashes[str(path)]=digest
    prepared_manifest=json.loads((PREPARED/'prepared_manifest.json').read_text())
    corpus_manifest=Path(prepared_manifest['corpusManifest'])
    if c.base.sha256(corpus_manifest)!=prepared_manifest['corpusManifestSha256']: raise ValueError('corpus manifest mismatch')
    hashes[str(corpus_manifest)]=prepared_manifest['corpusManifestSha256']
    return hashes


def prepare(output):
    output.mkdir(parents=True,exist_ok=False)
    hashes=verify_data()
    arrays,spec=c.base._load_prepared(PREPARED)
    c.base._prepare_target_indices(arrays,spec)
    arrays["preHp"]=arrays["globals_continuous"][:,c.base.CONTINUOUS_GLOBAL_FIELDS.index("curHp")].astype(np.int64)
    models=c.FrozenModels('cpu')
    classes,domain=c.hp.freeze_domain(arrays['preHp'],arrays['preMaxHp'],spec['maxHpDeltaValues'],arrays['supported'])
    if not np.array_equal(classes,models.classes) or domain!=models.domain:
        raise ValueError('HP pre-state/domain provenance differs')
    split=json.loads(SPLIT.read_text())
    membership={int(s):i for i,k in enumerate(('train','validation','test')) for s in split['members'][k]}
    if len(membership)!=sum(map(len,split['members'].values())): raise ValueError('source overlap')
    total=len(arrays['y_win']); supported=np.zeros(total,bool)
    tables={}; reasons=Counter(); rows=[]; sources=set(); n=0
    with (output/'test_rows.jsonl').open('w') as saved:
        for i,row in enumerate(c.base.iter_rows(CORPUS)):
            if i>=total: raise ValueError('too many corpus rows')
            pre=row['transition']['pre']; post=row['transition']['post']; pi=row['predictorInput']
            source=int(row['sourceSeed']); sources.add(source)
            if (source,int(row['fightIdx']))!=(int(arrays['sourceSeed'][i]),int(arrays['fightIdx'][i])) or membership.get(source)!=arrays['split_id'][i]:
                raise ValueError('corpus/source split alignment differs')
            if c.base.supported_for_surrogate(pi,pre)!=bool(arrays['supported'][i]): raise ValueError('global support mismatch')
            support_reasons=c.full_support_reasons(pre,pi,models)
            supported[i]=not support_reasons
            reasons.update(support_reasons)
            labels=['all',f"act:{pi['globals']['act']}",f"room:{pi['globals']['roomClass']}",f"split:{int(arrays['split_id'][i])}"]
            if arrays['split_id'][i]==2: labels.extend([f"test:act:{pi['globals']['act']}",f"test:room:{pi['globals']['roomClass']}"])
            for label in labels:
                t=tables.setdefault(label,Counter()); t['rows']+=1; t['supported']+=int(supported[i])
            if supported[i]:
                if pre['combatRng'][4]!=post['combatRng'][4] or c.native_rng.replay_misc(pre['combatRng'][2],models.encounter_names[pi['globals']['encounter']])!=post['combatRng'][2]:
                    raise ValueError('inherited native RNG corpus contradiction')
                if row['transition']['combatOutcome']==c.base.WIN:
                    if c.base._copy_through_violations(pre,post): raise ValueError('copy-through corpus contradiction')
                    c.potion.encode_masks(np.asarray([pre['potions']]),np.asarray([post['potions']]),np.asarray([pre['potionCapacity']]))
                    c.relic.trajectory_constraints(pre['relics'],post['relics'],pi['globals']['encounter'],any(x['id']==c.base._RELIC_IDS['MARK_OF_THE_BLOOM'] for x in pre['relics']))
            if arrays['split_id'][i]==2:
                encoded=c.visible_arrays(pi)
                for key in c.INPUT_KEYS:
                    if not np.array_equal(encoded[key][0],arrays[key][i]): raise ValueError(f'visible prepared mismatch {key}')
                if not np.array_equal(post['potions'],arrays['y_potions'][i]): raise ValueError('potion target mismatch')
                if bool(arrays['y_win'][i])!=(row['transition']['combatOutcome']==c.base.WIN) or post['curHp']!=arrays['y_post_hp'][i] or post['maxHp']!=arrays['y_post_max_hp'][i]: raise ValueError('outcome/HP target mismatch')
                saved.write(json.dumps(dict(index=i,source=source,pre=pre,predictorInput=pi,post=post,win=row['transition']['combatOutcome']==c.base.WIN,supported=bool(supported[i])))+'\n')
                rows.append(i)
            n+=1
            if n%100000==0: print(f'audit {n}/{total}',flush=True)
    if n!=total or sources!=set(membership): raise ValueError('corpus source/row count differs')
    np.save(output/'full_support.npy',supported)
    report={k:dict(v,rate=v['supported']/v['rows'],fallback=v['rows']-v['supported']) for k,v in tables.items()}
    c.base.json_dump(output/'preflight.json',dict(hashes=hashes,counts=report,reasons=dict(reasons),testRows=len(rows),testSources=len(split['members']['test']),domain=domain,corpusContradictions=0,baseline=c.BASELINE,savedTestRowsSha256=c.base.sha256(output/'test_rows.jsonl'),fullSupportSha256=c.base.sha256(output/'full_support.npy')))
    c.base.json_dump(output/'recipe.json',c.RECIPE)
    print(json.dumps(report),flush=True)


def batches(n,size=2048):
    for start in range(0,n,size): yield np.arange(start,min(n,start+size))


def probabilities(logits): return torch.softmax(logits.float(),-1).cpu().numpy().astype(float)


def hp_prob(m,z,delta,pre,maximum):
    features=torch.cat((torch.as_tensor(z,device=m.device),m.hp_net.delta_embedding(torch.as_tensor(delta,device=m.device))),-1)
    with torch.autocast('cuda',dtype=torch.float16,enabled=str(m.device).startswith('cuda')):
        logits=m.hp_net.hp(features).float()
    legal=c.hp.legal_support(m.classes,pre,maximum)
    return probabilities(logits.masked_fill(~torch.as_tensor(legal,device=m.device),-torch.inf))


def exact_hp_target_probabilities(models,z,delta_prob,pre,pre_max,target_class):
    """Evaluate the HP head only for every frozen maxHP class, using cached z."""
    n=len(pre); classes=len(models.delta_values)
    target=np.asarray(target_class)
    if target.shape!=(n,) or np.any(target!=target.astype(np.int64)) or np.any((target<0)|(target>=len(models.classes))):
        raise ValueError('invalid exact HP target class')
    target=target.astype(np.int64)
    conditional=np.empty((n,classes),dtype=np.float64)
    with torch.inference_mode():
        for d in range(classes):
            for b in batches(n):
                probability=hp_prob(models,z[b],np.full(len(b),d,dtype=np.int64),pre[b],pre_max[b]+models.delta_values[d])
                conditional[b,d]=probability[np.arange(len(b)),target[b]]
    return c.exact_hp_marginal(delta_prob,conditional),conditional


def potion_prob(m,z,pre,capacity,delta,fraction):
    values=(z,pre,capacity,delta,fraction.astype(np.float32))
    logp=m.potion_net(*(torch.as_tensor(v,device=m.device) for v in values))
    return logp.exp().cpu().numpy().astype(float)


def relic_prob(m,z,signed_class,fraction,mask):
    values=(z,signed_class,fraction.astype(np.float32),mask)
    logits=m.relic_net(*(torch.as_tensor(v,device=m.device) for v in values))
    return {g:probabilities(v) for g,v in logits.items() if g in c.TRAINED_GROUPS}


def draw_categories(p,rng):
    if np.any(p<0) or not np.isfinite(p).all() or not np.allclose(p.sum(-1),1,atol=1e-6): raise ValueError('invalid probability')
    cdf=p.cumsum(-1); cdf/=cdf[:,-1:]
    return np.sum(rng.random(len(p))[:,None]>=cdf,axis=-1)


def constraint_probability(p,compatible):
    result=np.ones(len(next(iter(p.values()))))
    for g in c.TRAINED_GROUPS: result*=np.sum(p[g]*compatible[g],-1)
    return result


def nll(p):
    with np.errstate(divide='ignore'): return -np.log(p)


def mean(values): return float(np.mean(values)) if len(values) else None


def complete_batch(models, arrays, ids, prehp, premax, slots, capacity, rng):
    """Ancestral batch counterpart, for already-certified immutable pre-states.

    Survival runs first. Only sampled survivors enter ANY downstream encoder
    or head. Encodings are local to this draw; relics reuse this draw's HP z.
    Labels and observed outcomes are not inputs.
    """
    m=models
    inputs=c.base._torch_inputs(arrays,ids,m.device,torch,trim_padding=True)
    pwin=torch.sigmoid(m.survival_net.survival(m.fp32_encoding(m.survival_net.encoder,inputs))).squeeze(-1).cpu().numpy()
    alive=rng.random(len(ids))<pwin
    chosen=np.flatnonzero(alive)
    counts=dict(survivalRows=len(ids),maxHpRows=0,hpEncoderRows=0,hpHeadRows=0,potionEncoderRows=0,potionDecoderRows=0,relicDecoderRows=0)
    row_calls=np.zeros((len(ids),len(counts)),np.int64); row_calls[:,0]=1
    if not len(chosen): return dict(alive=alive,chosen=chosen,counts=counts,rowCalls=row_calls)
    inputs=c.base._torch_inputs(arrays,ids[chosen],m.device,torch,trim_padding=True)
    pd=probabilities(m.max_net.max_hp_delta(m.fp32_encoding(m.max_net.encoder,inputs))); counts['maxHpRows']=len(chosen); row_calls[chosen,1]=1
    delta=draw_categories(pd,rng); maximum=premax[chosen]+m.delta_values[delta]
    if np.any(maximum<=0): raise ValueError('invalid sampled maxHP state')
    z=m.hp_encoding(inputs).cpu().numpy(); counts['hpEncoderRows']=len(chosen); row_calls[chosen,2]=1
    ph=hp_prob(m,z,delta,prehp[chosen],maximum); counts['hpHeadRows']=len(chosen); row_calls[chosen,3]=1
    signed=draw_categories(ph,rng); ending=prehp[chosen]+c.CLASSES[signed]; fraction=ending/maximum
    if np.any((ending<1)|(ending>maximum)): raise ValueError('invalid sampled HP')
    potion_z=m.fp32_encoding(m.potion_encoder.encoder,inputs).cpu().numpy(); counts['potionEncoderRows']=len(chosen); row_calls[chosen,4]=1
    pp=potion_prob(m,potion_z,slots[chosen],capacity[chosen],delta,fraction); counts['potionDecoderRows']=len(chosen); row_calls[chosen,5]=1
    mask=draw_categories(pp,rng)
    rp=relic_prob(m,z,signed,fraction,mask); counts['relicDecoderRows']=len(chosen); row_calls[chosen,6]=1
    residues={g:draw_categories(v,rng) for g,v in rp.items()}
    return dict(alive=alive,chosen=chosen,counts=counts,rowCalls=row_calls,delta=delta,maximum=maximum,ending=ending,mask=mask,residues=residues)


def validity_key(reason):
    if 'maxHP' in reason: return 'invalidMaxHpClassOrState'
    if 'HP' in reason: return 'hpBelow1' if 'below' in reason else 'hpAboveSampledMaxHp'
    if 'potion creation' in reason or 'swap' in reason: return 'potionCreationSwapSubstitution'
    if 'potion' in reason or 'mask' in reason: return 'invalidPotionTransition'
    if 'RNG' in reason: return 'invalidInheritedRngReconstruction'
    if 'residue' in reason: return 'crossRelicResidueInconsistency'
    if 'relic' in reason: return 'illegalRelicCounter'
    return 'deterministicNativeMismatch'


def source_gap_bootstrap(sources,differences):
    # Extended-real +inf gaps are explicit rejection evidence. Inclusive
    # empirical quantiles avoid inf-inf interpolation producing a NaN CI.
    if np.isfinite(differences).all():
        return c.frozen.paired_bootstrap(sources,{'gap':differences},c.RECIPE['bootstrapReps'],c.RECIPE['bootstrapSeed'])['gap']
    unique,inverse=np.unique(sources,return_inverse=True)
    counts=np.bincount(inverse).astype(float)
    sums=np.bincount(inverse,weights=differences,minlength=len(unique))
    rng=np.random.default_rng(c.RECIPE['bootstrapSeed']); draws=[]
    for _ in range(c.RECIPE['bootstrapReps']):
        sub=rng.integers(0,len(unique),len(unique)); draws.append(sums[sub].sum()/counts[sub].sum())
    return dict(mean=mean(differences),sourceBootstrap95=np.quantile(draws,[.025,.975],method='inverted_cdf').tolist(),
                sources=len(unique),rows=len(sources),repetitions=c.RECIPE['bootstrapReps'])


def run_evaluation(output,reviewed_sha):
    if (output/'results.json').exists():
        raise ValueError('refusing repeated evaluation; prior evidence preserved')
    try:
        return evaluate(output,reviewed_sha)
    except (ValueError,FileNotFoundError) as error:
        # A provenance/support/native failure is an explicit frozen rejection,
        # not a license to widen support, resample, tune or hide the failure.
        partial={}
        for name in ('preflight','component_reproduction','exposure'):
            path=output/(name+'.json')
            if path.exists(): partial[name]=json.loads(path.read_text())
        report=dict(classification='COMPOSED_TRANSITION_INCONCLUSIVE' if 'ambiguous' in str(error) else 'COMPOSED_TRANSITION_REJECTED',baseline=c.BASELINE,reviewedSha=reviewed_sha,
                    failure=str(error),partialEvidence=partial,
                    hardValidity={validity_key(str(error)):1} if 'sampled' in str(error) else None,
                    unevaluated='remaining validity counters, distributions and latency unavailable after contract failure',
                    nextAction='targeted repair of the identified artifact/support/native contract; no model tuning')
        output.mkdir(parents=True,exist_ok=True); c.base.json_dump(output/'results.json',report)
        print(json.dumps(report),flush=True)
        raise


def evaluate(output,reviewed_sha):
    if snapshot()!=reviewed_sha or subprocess.check_output(['git','status','--porcelain'],text=True).strip():
        raise ValueError('evaluation requires clean independently reviewed SHA')
    preflight=json.loads((output/'preflight.json').read_text())
    if c.base.sha256(output/'test_rows.jsonl')!=preflight['savedTestRowsSha256'] or c.base.sha256(output/'full_support.npy')!=preflight['fullSupportSha256']: raise ValueError('prepared support/TEST handoff mismatch')
    if verify_data()!=preflight['hashes'] or json.loads((output/'recipe.json').read_text())!=c.RECIPE:
        raise ValueError('frozen preflight changed')
    if (output/'results.json').exists(): raise ValueError('refusing repeated evaluation')
    torch.set_num_threads(4)
    arrays,spec=c.base._load_prepared(PREPARED); c.base._prepare_target_indices(arrays,spec)
    arrays["preHp"]=arrays["globals_continuous"][:,c.base.CONTINUOUS_GLOBAL_FIELDS.index("curHp")].astype(np.int64)
    rows=[json.loads(s) for s in (output/'test_rows.jsonl').read_text().splitlines()]
    ids=np.asarray([r['index'] for r in rows]); full=np.asarray([r['supported'] for r in rows]); win=np.asarray([r['win'] for r in rows])
    for r in rows:
        i=r['index']
        if r['win']!=bool(arrays['y_win'][i]) or r['post']['curHp']!=arrays['y_post_hp'][i] or r['post']['maxHp']!=arrays['y_post_max_hp'][i]: raise ValueError('original TEST observed target alignment mismatch')
    m=c.FrozenModels('cuda' if torch.cuda.is_available() else 'cpu')
    n=len(ids); local=np.flatnonzero(full); victories=np.flatnonzero(full & win)
    prehp=arrays['preHp'][ids]; premax=arrays['preMaxHp'][ids]; actualhp=arrays['y_post_hp'][ids]
    slots=arrays['potions'][ids,:,1].astype(np.int64); capacity=arrays['potionCapacity'][ids].astype(np.int64)
    true_delta=arrays['delta_index'][ids].astype(np.int64)
    true_max=premax+np.asarray(spec['maxHpDeltaValues'])[true_delta]
    true_class=(actualhp-prehp-c.CLASSES[0]).astype(np.int64)
    # Constraints are evaluation labels only; never handed to either sampler.
    compatible={g:np.ones((n,k),bool) for g,k in c.relic.HEAD_CLASSES.items() if g in c.TRAINED_GROUPS}
    observed=np.zeros(n,np.int64); true_mask=np.zeros(n,np.int64)
    truth_counters=np.zeros((n,64),np.int64); counter_mask=np.zeros((n,64),bool)
    for i,r in enumerate(rows):
        for j,x in enumerate(r['post']['relics']): truth_counters[i,j]=x['data']; counter_mask[i,j]=True
        if not full[i] or not win[i]: continue
        true_mask[i]=int(c.potion.encode_masks(slots[i:i+1],np.asarray([r['post']['potions']]),capacity[i:i+1])[0])
        bloom=any(x['id']==c.base._RELIC_IDS['MARK_OF_THE_BLOOM'] for x in r['pre']['relics'])
        constraints=c.relic.trajectory_constraints(r['pre']['relics'],r['post']['relics'],r['predictorInput']['globals']['encounter'],bloom)
        for g,v in constraints.items():
            if g not in compatible: raise ValueError('unqualified observed group on full support')
            compatible[g][i]=np.isin(np.arange(c.relic.HEAD_CLASSES[g]),list(v)); observed[i]+=1
    cache=dict(pwin=np.zeros(n),pdelta=np.zeros((n,len(m.delta_values))),z=np.zeros((n,64),np.float32),potion_z=np.zeros((n,64),np.float32))
    # Historical encoders retain independent normalization; no refit or stats estimation.
    with torch.inference_mode():
        for sub in batches(n,512):
            inputs=c.base._torch_inputs(arrays,ids[sub],m.device,torch,trim_padding=True)
            cache['pwin'][sub]=torch.sigmoid(m.survival_net.survival(m.fp32_encoding(m.survival_net.encoder,inputs))).squeeze(-1).cpu().numpy()
            cache['pdelta'][sub]=probabilities(m.max_net.max_hp_delta(m.fp32_encoding(m.max_net.encoder,inputs)))
            cache['z'][sub]=m.hp_encoding(inputs).cpu().numpy()
            cache['potion_z'][sub]=m.fp32_encoding(m.potion_encoder.encoder,inputs).cpu().numpy()
            if sub[0]%5120==0: print(f'encode {sub[0]}/{n}',flush=True)
    # Reproduce survival on its historical globally supported original TEST rows.
    global_local=np.flatnonzero(arrays['supported'][ids])
    reproduction=dict(survival=c.base._binary_metrics(win[global_local].astype(int),cache['pwin'][global_local]))
    historical=json.loads((c.RUNS/'frozen-survival-potion-20260913/attention_ablation_evidence.json').read_text())
    differences={k:reproduction['survival'][k]-historical['test']['pointControl']['survival'][k] for k in ('brier','logloss','auc')}
    # Existing historical reproduction convention (1e-5), not a new scientific gate.
    if any(abs(v)>1e-5 for v in differences.values()): raise ValueError(f'unexplained survival regression: {differences}')
    with np.load(c.RUNS/'frozen-survival-potion-20260913/frozen_predictions.npz') as raw:
        max_diff=float(np.max(np.abs(raw['pDelta']-cache['pdelta'][global_local])))
        if max_diff>1e-5: raise ValueError(f'maxHP historical probability regression: {max_diff}')
    reproduction['historicalDifferences']=dict(survival=differences,maxHpProbabilityMaxAbs=max_diff)
    hp_teacher=np.zeros(n); potion_teacher=np.zeros(n); relic_teacher=np.zeros(n); max_teacher=np.zeros(n)
    hp_score_parts={}; hp_row_scores={}; potion_mode_exact=np.zeros(n,bool); relic_mode=np.zeros((n,64),np.int64); potion_exact=[]
    with torch.inference_mode():
        for b in batches(len(victories)):
            sub=victories[b]; max_teacher[sub]=nll(cache['pdelta'][sub,true_delta[sub]])
            p=hp_prob(m,cache['z'][sub],true_delta[sub],prehp[sub],true_max[sub]); hp_teacher[sub]=nll(p[np.arange(len(sub)),true_class[sub]])
            scores=c.hp.row_scores(p,c.CLASSES,prehp[sub],true_max[sub],actualhp[sub],hp_teacher[sub])
            for k,v in scores.items():
                hp_score_parts.setdefault(k,[]).append(v)
                hp_row_scores.setdefault(k,np.zeros(n))[sub]=v
            pp=potion_prob(m,cache['potion_z'][sub],slots[sub],capacity[sub],true_delta[sub],actualhp[sub]/true_max[sub])
            potion_teacher[sub]=nll(pp[np.arange(len(sub)),true_mask[sub]]); potion_mode_exact[sub]=pp.argmax(-1)==true_mask[sub]; potion_exact.extend(potion_mode_exact[sub])
            rp=relic_prob(m,cache['z'][sub],true_class[sub],actualhp[sub]/true_max[sub],true_mask[sub])
            relic_teacher[sub]=nll(constraint_probability(rp,{g:v[sub] for g,v in compatible.items()}))
            for i,j in enumerate(sub):
                r=rows[j]; bloom=any(x['id']==c.base._RELIC_IDS['MARK_OF_THE_BLOOM'] for x in r['pre']['relics'])
                pred=c.relic.reconstruct(r['pre']['relics'],{g:int(v[i].argmax()) for g,v in rp.items()},r['predictorInput']['globals']['encounter'],bloom)
                relic_mode[j,:len(pred)]=[x['data'] for x in pred]
    reproduction.update(partition='full-support original reused engineering TEST victories for downstream heads',rows=len(victories),
                        maxHp=dict(nll=mean(max_teacher[victories]),modeAccuracy=mean(cache['pdelta'][victories].argmax(-1)==true_delta[victories])),
                        signedHp=c.hp.summarize({k:np.concatenate(v) for k,v in hp_score_parts.items()}),
                        potion=dict(jointMaskNll=mean(potion_teacher[victories]),modeExact=mean(potion_exact)),
                        relic=dict(constraintNll=mean(relic_teacher[victories]),reconstructed=counter_metrics(rows,victories,relic_mode[victories,None,:],truth_counters,counter_mask)))
    c.base.json_dump(output/'component_reproduction.json',reproduction)
    np.savez_compressed(output/'row_metrics.npz',rows=ids,source=arrays['sourceSeed'][ids],supported=full,win=win,
                        pwin=cache['pwin'],maxNll=max_teacher,maxModeExact=cache['pdelta'].argmax(-1)==true_delta,
                        potionNll=potion_teacher,potionModeExact=potion_mode_exact,relicNll=relic_teacher,
                        relicModeExact=np.all((relic_mode==truth_counters)|~counter_mask,axis=-1),
                        observedGroups=observed,**{'hp_'+k:v for k,v in hp_row_scores.items()})
    print('component reproduction passed',flush=True)
    # B: all observed victories, 32 draws of sampled maxHP -> HP -> potion -> relic.
    rng=np.random.default_rng(c.RECIPE['samplingSeed']); mass={k:[] for k in ('hp','potion','relic')}
    exposure_raw={}
    with torch.inference_mode():
        for draw in range(c.RECIPE['draws']):
            targets={k:np.zeros(len(victories)) for k in mass}
            sample_hp=np.zeros(len(victories),np.int64); sample_mask=np.zeros(len(victories),np.int64); sample_delta=np.zeros(len(victories),np.int64)
            for b in batches(len(victories)):
                sub=victories[b]; d=draw_categories(cache['pdelta'][sub],rng); maximum=premax[sub]+m.delta_values[d]
                p=hp_prob(m,cache['z'][sub],d,prehp[sub],maximum); targets['hp'][b]=p[np.arange(len(sub)),true_class[sub]]
                signed=draw_categories(p,rng); ending=prehp[sub]+c.CLASSES[signed]; fraction=ending/maximum
                pp=potion_prob(m,cache['potion_z'][sub],slots[sub],capacity[sub],d,fraction); targets['potion'][b]=pp[np.arange(len(sub)),true_mask[sub]]
                mask=draw_categories(pp,rng); rp=relic_prob(m,cache['z'][sub],signed,fraction,mask)
                targets['relic'][b]=constraint_probability(rp,{g:v[sub] for g,v in compatible.items()})
                sample_hp[b]=ending; sample_mask[b]=mask; sample_delta[b]=d
            for k in mass: mass[k].append(targets[k])
            exposure_raw[f'draw{draw}-hp']=sample_hp; exposure_raw[f'draw{draw}-mask']=sample_mask; exposure_raw[f'draw{draw}-maxClass']=sample_delta
            print(f'exposure {draw+1}/32',flush=True)
    informative=observed[victories]>0
    gaps={}; mixtures={}
    for k,teacher in [('hp',hp_teacher),('potion',potion_teacher),('relic',relic_teacher)]:
        stacked=np.stack(mass[k]); mixtures[k]=c.mixture_nll_from_probabilities(stacked) # average probability BEFORE log
        diff=mixtures[k]-teacher[victories]
        selected=np.ones(len(victories),bool)
        if k=='relic': selected=informative; diff=diff[selected]/observed[victories][selected]
        if np.any(np.isnan(diff)) or np.any(np.isneginf(diff)): raise ValueError(f'ambiguous {k} exposure gap')
        gaps[k]=source_gap_bootstrap(arrays['sourceSeed'][ids[victories[selected]]],diff)
        gaps[k]['zeroMixtureProbabilityRows']=int(np.sum(stacked.mean(0)==0))
        gaps[k].update(teacherNll=mean(teacher[victories]),mixtureNll=mean(mixtures[k]),decision='MATERIAL_EXPOSURE_DEGRADATION' if gaps[k]['mean']>.1 else 'EXPOSURE_OK')
        exposure_raw[k+'-drawMass']=stacked; exposure_raw[k+'-teacherNll']=teacher[victories]; exposure_raw[k+'-mixtureNll']=mixtures[k]
    hp_monte_carlo=copy.deepcopy(gaps['hp'])
    hp_monte_carlo['decision']='DIAGNOSTIC_ONLY_NOT_USED_FOR_QUALIFICATION'
    marginal,hp_conditional=exact_hp_target_probabilities(m,cache['z'][victories],cache['pdelta'][victories],prehp[victories],premax[victories],true_class[victories])
    exact_nll=nll(marginal)
    gaps['hp']=source_gap_bootstrap(arrays['sourceSeed'][ids[victories]],exact_nll-hp_teacher[victories])
    gaps['hp'].update(teacherNll=mean(hp_teacher[victories]),mixtureNll=mean(exact_nll),estimator='exact weighted marginal over all maxHP classes',zeroMixtureProbabilityRows=int(np.sum(marginal==0)),decision='MATERIAL_EXPOSURE_DEGRADATION' if gaps['hp']['mean']>.1 else 'EXPOSURE_OK')
    exposure_raw.update(hpExactMarginalProbability=marginal,hpExactConditionalTargetProbability=hp_conditional,hpExactNll=exact_nll,maxHpProbability=cache['pdelta'][victories],hpStateEncoding=cache['z'][victories])
    c.base.json_dump(output/'hp_monte_carlo_diagnostic.json',hp_monte_carlo)
    np.savez_compressed(output/'exposure.npz',rows=ids[victories],**exposure_raw)
    c.base.json_dump(output/'exposure.json',gaps)
    # C: batch counterpart of the same staged sampler; only sampled survivors
    # enter downstream model forwards. Shared native assembly validates each state.
    rng=np.random.default_rng(c.RECIPE['samplingSeed']+1); draws=c.RECIPE['draws']
    survived=np.zeros((len(local),draws),bool); sampled_hp=np.zeros((len(local),draws),np.int64)
    sampled_max=sampled_hp.copy(); sampled_mask=sampled_hp.copy(); counters=np.zeros((len(local),draws,64),np.int64)
    exact_core=np.zeros_like(survived); exact_complete=np.zeros_like(survived)
    validity=dict.fromkeys(VALIDITY_KEYS,0); downstream_counts=Counter(); sample_failures=[]
    row_validity=np.zeros((len(local),len(VALIDITY_KEYS)),np.int64); call_receipts=[]
    with torch.inference_mode():
        for draw in range(draws):
            for b in batches(len(local),512):
                sub_all=local[b]
                sample=complete_batch(m,arrays,ids[sub_all],prehp[sub_all],premax[sub_all],slots[sub_all],capacity[sub_all],rng)
                survived[b,draw]=sample['alive']; downstream_counts.update(sample['counts'])
                call_receipts.append(dict(draw=draw,rows=ids[sub_all].tolist(),alive=sample['alive'].tolist(),counts=sample['counts'],rowCalls=sample['rowCalls'].tolist()))
                if not np.array_equal(sample['rowCalls'].sum(0),list(sample['counts'].values())): raise ValueError('model call receipt mismatch')
                row_validity[b,VALIDITY_KEYS.index('downstreamModelInvokedAfterDeath')]+=sample['rowCalls'][:,1:].sum(1)*(~sample['alive'])
                if not len(sample['chosen']): continue
                pos=b[sample['chosen']]; sub=local[pos]
                d=sample['delta']; maximum=sample['maximum']; ending=sample['ending']; masks=sample['mask']; residues=sample['residues']
                for i,j in enumerate(sub):
                    r=rows[j]; group={g:int(v[i]) for g,v in residues.items()}
                    before=np.asarray([validity[k] for k in VALIDITY_KEYS])
                    # A failed assertion is a hard qualification rejection, never
                    # clipping or silently converting a sampled invalidity to fallback.
                    try:
                        post=c.assemble_victory(r['pre'],r['predictorInput'],int(maximum[i]),int(ending[i]),int(masks[i]),group,m.encounter_names)
                    except ValueError as error:
                        key=validity_key(str(error)); validity[key]+=1
                        sample_failures.append(dict(rowIndex=r['index'],draw=draw,error=str(error),maximum=int(maximum[i]),hp=int(ending[i]),mask=int(masks[i]),residues=group))
                        row_validity[pos[i]]+=np.asarray([validity[k] for k in VALIDITY_KEYS])-before
                        continue
                    pred=[x['data'] for x in post['relics']]; counters[pos[i],draw,:len(pred)]=pred
                    for token,(a,z) in enumerate(zip(r['pre']['relics'],post['relics'])):
                        name=c.relic.NAMES.get(a['id'])
                        if name is None:
                            validity['unsupportedMutableRelicMutation']+=int(a!=z); continue
                        bloom=any(x['id']==c.base._RELIC_IDS['MARK_OF_THE_BLOOM'] for x in r['pre']['relics'])
                        allowed=c.relic.legal_posts(a['id'],a['data'],r['predictorInput']['globals']['encounter'],bloom)
                        validity['illegalRelicCounter']+=int(z['data'] not in allowed)
                        if len(allowed)==1: validity['deterministicNativeMismatch']+=int(z['data']!=next(iter(allowed)))
                        if name in c.relic.TRAJECTORY:
                            g=c.relic.TRAJECTORY[name][0]
                            validity['crossRelicResidueInconsistency']+=int((z['data']-a['data'])%c.relic.CYCLIC[name]!=group[g]%c.relic.CYCLIC[name])
                    row_validity[pos[i]]+=np.asarray([validity[k] for k in VALIDITY_KEYS])-before
                    truth=r['post']
                    exact_core[pos[i],draw]=all(post[k]==truth[k] for k in ('curHp','maxHp','potions','relics'))
                    exact_complete[pos[i],draw]=all(post[k]==truth[k] for k in c.base.PERSISTENT_KEYS) and post['oocContinuationRng']==dict(miscRng=truth['combatRng'][2],potionRng=truth['combatRng'][4])
                sampled_hp[pos,draw]=ending; sampled_max[pos,draw]=maximum; sampled_mask[pos,draw]=masks
            print(f'complete {draw+1}/32 alive={int(survived[:,draw].sum())}',flush=True)
    validity['hpBelow1']=int(np.sum(survived & (sampled_hp<1)))
    validity['hpAboveSampledMaxHp']=int(np.sum(survived & (sampled_hp>sampled_max)))
    validity['invalidMaxHpClassOrState']=int(np.sum(survived & ((sampled_max<=0)|~np.isin(sampled_max-premax[local,None],m.delta_values))))
    validity['downstreamModelInvokedAfterDeath']=int(row_validity[:,VALIDITY_KEYS.index('downstreamModelInvokedAfterDeath')].sum())
    row_validity[:,VALIDITY_KEYS.index('hpBelow1')]=np.sum(survived & (sampled_hp<1),axis=1)
    row_validity[:,VALIDITY_KEYS.index('hpAboveSampledMaxHp')]=np.sum(survived & (sampled_hp>sampled_max),axis=1)
    row_validity[:,VALIDITY_KEYS.index('invalidMaxHpClassOrState')]=np.sum(survived & ((sampled_max<=0)|~np.isin(sampled_max-premax[local,None],m.delta_values)),axis=1)
    if not np.array_equal(row_validity.sum(0),[validity[k] for k in VALIDITY_KEYS]): raise ValueError('row validity accounting differs')
    np.savez_compressed(output/'row_validity.npz',rows=ids[local],keys=np.asarray(VALIDITY_KEYS),counts=row_validity)
    c.base.json_dump(output/'model_call_receipts.json',call_receipts)
    np.savez_compressed(output/'complete_draws.npz',rows=ids[local],survived=survived,hp=sampled_hp,maxHp=sampled_max,potionMask=sampled_mask,relicCounters=counters,exactCore=exact_core,exactComplete=exact_complete)
    diag=diagnostics(rows,local,win,cache,true_delta,true_mask,actualhp,premax,survived,sampled_hp,sampled_max,sampled_mask,counters,truth_counters,counter_mask,exact_core,exact_complete)
    outcome=c.frozen.outcome_nll(win[local].astype(int),cache['pwin'][local]); components=dict(outcome=mean(outcome))
    for name,loss in [('maxHp',max_teacher),('hp',hp_teacher),('potion',potion_teacher),('relic',relic_teacher)]:
        components[name]=float(loss[local].sum()/len(local))
    joint=dict(meanTotalNll=sum(components.values()),contributionsPerFullSupportRow=components,
               convention='death: outcome only; victory: observed teacher-forced factorization, partial relic constraint mass')
    m.to('cpu'); torch.set_num_threads(1)
    latency=measure_latency(m,rows[int(victories[0])])
    classification=c.classify({k:v['mean'] for k,v in gaps.items()},validity)
    result=dict(classification=classification,
                baseline=c.BASELINE,reviewedSha=reviewed_sha,recipe=c.RECIPE,provenance=preflight,
                fullSupportTestRows=len(local),fullSupportTestVictories=len(victories),completeDraws=len(local)*draws,
                componentReproduction=reproduction,exposure=gaps,hpMonteCarloDiagnostic=hp_monte_carlo,hardValidity=validity,actualModelRowCalls=dict(downstream_counts),diagnostics=diag,
                factorizedJointNll=joint,cpuLatency=latency,artifactsUnchanged=c.verify_hashes()==m.hashes,
                nextAction='targeted repair of '+', '.join(k for k,v in gaps.items() if v['mean']>.1) if classification.endswith('REJECTED') else 'native runtime adapter / OOC MCTS integration')
    c.base.json_dump(output/'sample_failures.json',sample_failures)
    result['sampleFailureCount']=len(sample_failures)
    c.base.json_dump(output/'results.json',result)
    print(json.dumps(dict(classification=result['classification'],exposure=gaps,validity=validity,latency=latency)),flush=True)


def correct_hp_exposure(source,output,reviewed_sha):
    """Recompute only analytical HP exposure/bootstrap; reuse all other evidence."""
    if snapshot()!=reviewed_sha or subprocess.check_output(['git','status','--porcelain'],text=True).strip():
        raise ValueError('HP correction requires clean independently reviewed SHA')
    if output.exists(): raise ValueError('refusing to overwrite HP correction evidence')
    preflight=json.loads((source/'preflight.json').read_text())
    if verify_data()!=preflight['hashes']: raise ValueError('frozen provenance differs')
    receipts=json.loads((source/'artifact-hashes.json').read_text())
    inputs=('results.json','exposure.npz','recipe.json','preflight.json','test_rows.jsonl','full_support.npy','component_reproduction.json')
    source_hashes={name:c.base.sha256(source/name) for name in inputs}
    if any(source_hashes[name]!=receipts[name] for name in inputs): raise ValueError('source evidence receipt mismatch')
    if source_hashes['test_rows.jsonl']!=preflight['savedTestRowsSha256'] or source_hashes['full_support.npy']!=preflight['fullSupportSha256']:
        raise ValueError('source TEST/support handoff differs')
    source_recipe=json.loads((source/'recipe.json').read_text())
    original_recipe={k:v for k,v in c.RECIPE.items() if k not in ('hpExposureEstimator','hpMonteCarloRole')}
    if source_recipe not in (original_recipe,c.RECIPE): raise ValueError('source recipe differs beyond HP estimator')
    old=json.loads((source/'results.json').read_text())
    arrays,spec=c.base._load_prepared(PREPARED); c.base._prepare_target_indices(arrays,spec)
    ids=np.flatnonzero(arrays['split_id']==2)
    full=np.load(source/'full_support.npy')
    victories=np.flatnonzero(full[ids] & (arrays['y_win'][ids]==1))
    row_ids=ids[victories]
    with np.load(source/'exposure.npz') as raw:
        if not np.array_equal(row_ids,raw['rows']): raise ValueError('exact HP row membership differs')
        teacher=raw['hp-teacherNll'].copy()
        monte_carlo_zero=int(np.sum(raw['hp-drawMass'].mean(0)==0))
    if len(row_ids)!=old['fullSupportTestVictories'] or len(ids)!=preflight['testRows']: raise ValueError('original TEST counts differ')
    pre=arrays['globals_continuous'][row_ids,c.base.CONTINUOUS_GLOBAL_FIELDS.index('curHp')].astype(np.int64)
    pre_max=arrays['preMaxHp'][row_ids].astype(np.int64)
    actual=arrays['y_post_hp'][row_ids].astype(np.int64)
    true_delta=arrays['delta_index'][row_ids].astype(np.int64)
    target=(actual-pre-c.CLASSES[0]).astype(np.int64)
    torch.set_num_threads(4); m=c.FrozenModels('cuda' if torch.cuda.is_available() else 'cpu')
    if len(m.delta_values)!=11 or not np.array_equal(m.delta_values,spec['maxHpDeltaValues']): raise ValueError('frozen 11-class maxHP domain differs')
    # Original A/B encodings were not persisted. Rebuild the same TEST batches
    # (512, same padding/arithmetic), without survival/potion/relic forwards.
    z=np.empty((len(ids),64),np.float32); delta_prob=np.empty((len(ids),11),np.float64)
    with torch.inference_mode():
        for b in batches(len(ids),512):
            tensors=c.base._torch_inputs(arrays,ids[b],m.device,torch,trim_padding=True)
            z[b]=m.hp_encoding(tensors).cpu().numpy()
            delta_prob[b]=probabilities(m.max_net.max_hp_delta(m.fp32_encoding(m.max_net.encoder,tensors)))
            if b[0]%5120==0: print(f'rebuild HP/maxHP input cache {b[0]}/{len(ids)}',flush=True)
    z=z[victories]; delta_prob=delta_prob[victories]
    reproduced=np.empty(len(row_ids))
    with torch.inference_mode():
        for b in batches(len(row_ids)):
            p=hp_prob(m,z[b],true_delta[b],pre[b],pre_max[b]+m.delta_values[true_delta[b]])
            reproduced[b]=nll(p[np.arange(len(b)),target[b]])
    teacher_max_difference=float(np.max(np.abs(reproduced-teacher)))
    if not np.isfinite(reproduced).all() or teacher_max_difference>1e-5: raise ValueError('HP teacher reproduction differs')
    print(f'teacher reproduction max NLL difference {teacher_max_difference}',flush=True)
    marginal,conditional=exact_hp_target_probabilities(m,z,delta_prob,pre,pre_max,target)
    exact_nll=nll(marginal); difference=exact_nll-teacher
    if not np.isfinite(difference).all(): raise ValueError('ambiguous nonfinite exact HP marginal despite finite teacher')
    hp=source_gap_bootstrap(arrays['sourceSeed'][row_ids],difference)
    hp.update(teacherNll=mean(teacher),mixtureNll=mean(exact_nll),estimator='exact weighted marginal over all 11 maxHP classes',
              zeroMixtureProbabilityRows=int(np.sum(marginal==0)),decision='MATERIAL_EXPOSURE_DEGRADATION' if hp['mean']>.1 else 'EXPOSURE_OK')
    result=copy.deepcopy(old)
    diagnostic=copy.deepcopy(old['exposure']['hp']); diagnostic['decision']='DIAGNOSTIC_ONLY_NOT_USED_FOR_QUALIFICATION'
    result['hpMonteCarloDiagnostic']=diagnostic; result['exposure']['hp']=hp
    result['originalComposedExecutionSha']=old['reviewedSha']; result['reviewedSha']=reviewed_sha; result['recipe']=c.RECIPE
    result['classification']=c.classify({k:v['mean'] for k,v in result['exposure'].items()},result['hardValidity'],provenance=old['artifactsUnchanged'])
    result['nextAction']='native runtime adapter / OOC MCTS integration' if result['classification']=='COMPOSED_TRANSITION_QUALIFIED' else 'report genuine exact HP composition exposure; no model changes in this correction'
    unchanged=('componentReproduction','hardValidity','actualModelRowCalls','diagnostics','factorizedJointNll','cpuLatency','provenance','completeDraws','sampleFailureCount')
    if any(result[k]!=old[k] for k in unchanged) or any(result['exposure'][k]!=old['exposure'][k] for k in ('potion','relic')):
        raise ValueError('HP correction changed unrelated evidence')
    if c.verify_hashes()!=m.hashes: raise ValueError('frozen artifacts changed')
    result['hpMetricCorrection']=dict(sourceDirectory=str(source),sourceHashes=source_hashes,originalReviewedSha=old['reviewedSha'],
        correctionReviewedSha=reviewed_sha,teacherMaxNllDifference=teacher_max_difference,maxHpClasses=m.delta_values.tolist(),
        empirical32DrawZeroRows=monte_carlo_zero,cacheRebuilt='same original TEST 512-row batches, frozen HP/maxHP encoders only',
        unchangedEvidence=list(unchanged)+['potion exposure','relic exposure'],newSampling=False,newGameplaySeeds=False,training=False)
    output.mkdir(parents=True)
    np.savez_compressed(output/'hp_exact_cache.npz',rows=row_ids,source=arrays['sourceSeed'][row_ids],z=z,maxHpProbability=delta_prob,
                        preHp=pre,preMaxHp=pre_max,targetClass=target,trueDeltaClass=true_delta,teacherNll=teacher,
                        conditionalTargetProbability=conditional,marginalProbability=marginal,exactNll=exact_nll,gap=difference)
    c.base.json_dump(output/'results.json',result)
    c.base.json_dump(output/'recipe.json',c.RECIPE)
    c.base.json_dump(output/'artifact-hashes.json',{p.name:c.base.sha256(p) for p in output.iterdir() if p.is_file()})
    print(json.dumps(dict(classification=result['classification'],hp=hp,empirical32DrawZeroRows=monte_carlo_zero)),flush=True)


def counter_metrics(rows,ids,samples,truth,mask,alive=None):
    if alive is None: alive=np.ones(samples.shape[:2],bool)
    target=truth[ids,None,:]; tokenmask=mask[ids,None,:]&alive[:,:,None]
    pre=np.zeros_like(truth[ids])
    relic_ids=np.full_like(pre,-1)
    for i,j in enumerate(ids):
        for t,x in enumerate(rows[j]['pre']['relics']): pre[i,t]=x['data']; relic_ids[i,t]=x['id']
    changed=(target!=pre[:,None,:]) & tokenmask
    errors=np.abs(samples-target)
    def summary(selected):
        changes=changed & selected; active=tokenmask & selected
        exact=np.all((samples==target)|~(mask[ids,None,:]&selected),axis=-1)
        carrier=alive & (mask[ids,None,:]&selected).any(-1)
        return dict(fullVectorExact=mean(exact[carrier]),tokenExact=mean((errors==0)[active]),changedTokenExact=mean((errors==0)[changes]),
                    changedTokenMae=mean(errors[changes]),tokens=int(active.sum()),changedTokens=int(changes.sum()))
    result=summary(np.ones_like(tokenmask))
    result['perRelic']={name:summary(relic_ids[:,None,:]==c.base._RELIC_IDS[name]) for name in (*c.relic.TRAJECTORY,'LIZARD_TAIL',*c.relic.COPY_COUNTERS,'NEOWS_LAMENT','OMAMORI')}
    return result


def empirical_hp(samples,actual,alive):
    # Condition on sampled victories for HP diagnostics; sampled deaths are
    # terminal, have no post HP, and must not be assigned HP=0 in this score.
    scores=[]; intervals={str(level):[] for level in (50,80,95)}
    for p,t,a in zip(samples,actual,alive):
        x=p[a].astype(float)
        if not len(x): continue
        crps=np.abs(x-t).mean()-.5*np.abs(x[:,None]-x[None,:]).mean()
        scores.append((crps,abs(x.mean()-t)))
        for level in (50,80,95):
            alpha=(1-level/100)/2; low,high=np.quantile(x,[alpha,1-alpha],method='inverted_cdf')
            intervals[str(level)].append((low<=t<=high,high-low))
    return dict(rowsWithSampledVictory=len(scores),rowsWithoutSampledVictory=int(np.sum(~alive.any(-1))),
                empiricalPostHpCrps=mean(np.asarray(scores)[:,0]),sampleMeanPostHpMae=mean(np.asarray(scores)[:,1]),
                intervals={k:dict(coverage=mean(np.asarray(v)[:,0]),width=mean(np.asarray(v)[:,1])) for k,v in intervals.items()},
                convention='observed victory rows; empirical distribution conditional on sampled victory')


def diagnostics(rows,local,win,cache,true_delta,true_mask,actualhp,premax,alive,hp,maxhp,masks,counters,truth_counters,counter_mask,core,complete):
    victories=win[local]; a=alive[victories]; sub=local[victories]
    outcome=c.base._binary_metrics(win[local].astype(int),cache['pwin'][local])
    outcome.update(observedDeathRate=mean(~win[local]),meanPredictedDeathProbability=mean(1-cache['pwin'][local]),sampledDeathRate=mean(~alive))
    maxdiag=dict(nll=mean(nll(cache['pdelta'][sub,true_delta[sub]])),modeAccuracy=mean(cache['pdelta'][sub].argmax(-1)==true_delta[sub]),
                 sampledChangeFrequency=mean((maxhp[victories]!=premax[sub,None])[a]),observedChangeFrequency=mean(true_delta[sub]!=0))
    observedmask=np.broadcast_to(true_mask[sub,None],a.shape); matches=(masks[victories]==observedmask)&a
    consumed=c.potion.BITS[masks[victories]].sum(-1)
    potiondiag=dict(noChangeFrequency=mean((masks[victories]==0)[a]),observedNoChangeFrequency=mean(true_mask[sub]==0),
                    consumedCountDistribution={str(k):mean((consumed==k)[a]) for k in range(6)},
                    observedConsumedCountDistribution={str(k):mean(c.potion.BITS[true_mask[sub]].sum(-1)==k) for k in range(6)},
                    empiricalObservedMaskProbability=mean(matches.sum(-1)[a.any(-1)]/a.sum(-1)[a.any(-1)]),
                    exactObservedMaskSampleFrequency=mean((masks[victories]==observedmask)[a]))
    relicdiag=counter_metrics(rows,sub,counters[victories],truth_counters,counter_mask,a)
    return dict(outcome=outcome,maxHp=maxdiag,hp=empirical_hp(hp[victories],actualhp[sub],a),potions=potiondiag,relics=relicdiag,
                persistentState=dict(exactHpMaxHpPotionsRelicsSampleFrequency=mean(core[victories][a]),exactCompleteModeledPersistentStateSampleFrequency=mean(complete[victories][a]),
                                     unconditionalCoreFrequency=mean(core[victories]),unconditionalCompleteFrequency=mean(complete[victories]),
                                     convention='conditional frequencies among sampled victories on observed victory rows; unconditional includes sampled deaths as nonmatches'))


def measure_latency(models,row):
    sampler=c.ComposedSampler(models); result={}
    for path in ('death','victory','mixed'):
        rng=np.random.default_rng(c.RECIPE['samplingSeed']); times=[]; deaths=0
        class PathRng:
            def random(self):
                if path=='death': return 1.
                if path=='victory': return 0.
                return rng.random()
            def choice(self,*args,**kwargs): return rng.choice(*args,**kwargs)
        controlled=PathRng()
        # Survival forward is always executed. The controlled branch RNG merely
        # makes the two conditional latency paths measurable without selection.
        for _ in range(10): sampler.sample_transition(row['pre'],row['predictorInput'],controlled)
        for _ in range(100):
            start=time.perf_counter(); sample=sampler.sample_transition(row['pre'],row['predictorInput'],controlled)
            times.append((time.perf_counter()-start)*1000); deaths+=sample.outcome=='DEATH'
            if sample.outcome=='FULL_SURROGATE_FALLBACK': raise ValueError('latency row unsupported')
        result[path]=dict(meanMs=mean(times),medianMs=float(np.median(times)),p95Ms=float(np.quantile(times,.95)),draws=100,deathDraws=deaths)
    return dict(device='cpu',threads=1,batch=1,warmups=10,paths=result,
                boundary='full support gate, visible encoding, survival; on victory maxHP encoder/head, HP encoder/head/sample, potion encoder/decoder/sample, relic decoder/sample with reused HP state, native reconstruction, exact RNG continuation, persistent assembly/validation',
                branchConvention='death/victory force branch uniform after real survival forward; mixed uses model survival sampling',
                stateSource=row['source'],stateFightIndex=row['index'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('command',choices=('prepare','evaluate','correct-hp'))
    p.add_argument('--output-dir',type=Path,required=True); p.add_argument('--reviewed-sha'); p.add_argument('--source-dir',type=Path)
    args=p.parse_args()
    if args.command=='prepare': prepare(args.output_dir)
    elif args.command=='correct-hp':
        if args.source_dir is None: p.error('correct-hp requires --source-dir')
        correct_hp_exposure(args.source_dir,args.output_dir,args.reviewed_sha)
    else: run_evaluation(args.output_dir,args.reviewed_sha)
