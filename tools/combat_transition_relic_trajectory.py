#!/usr/bin/env python3
"""Frozen partial-label relic-residue experiment. External artifacts only."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import numpy as np
from tools import combat_transition_surrogate as base
from tools import combat_transition_hp_targets as hp
from tools import combat_transition_stochastic_hp as stochastic
from tools import combat_transition_potion_decoder as potion
from tools import combat_transition_frozen_composition as frozen
from tools import combat_transition_relic_legality as relic

HEADS = tuple(relic.HEAD_CLASSES)
HP_HASH = 'a667a3cfa7d7eca3cb07b46f50321e443c75e8a58f7627becb1fd69bf90f08c9'
POTION_HASH = '8e04bcd5265fb11b8fa91b4553a84690915f437e7b3afee0b93358e312de3ad6'
ENCODER_HASH = '2085010f1aeef7a7957cdc45c851b2424d640037fd0fa981eb7ae7274190f6ef'
RECIPE = dict(schema='relic_trajectory_v1', seeds=[20260912,20260913,20260914],
              epochs=10, optimizer='AdamW', lr=1e-3, weightDecay=1e-4,
              batch=2048, clip=1., precision='fp32', hpSeedConvention=20260912,
              features='frozen HP state64 + signedHP embedding16 + ending fraction1 + mask embedding8',
              decoder='89/64 ReLU; 6/10/10/3/2 independent trajectory heads',
              loss='partial-label logsumexp; mean observed heads per row then mean rows',
              prior='TRAIN-only class biases; same loss and fixed optimization',
              bootstrapReps=1000, bootstrapSeed=20260914, samplesPerRow=16,
              samplingSeed=20260915, calibrationBins=10,
              exposureThreshold=.1, exposureAggregation='mean normalized row mixture-minus-teacher NLL on informative rows',
              decision='qualify iff paired NLL CI upper<0, ancestral OK, zero validity counts; reject iff CI lower>0 or invalidity; otherwise inconclusive')


def new_decoder(torch, classes, seed, prior=False):
    torch.manual_seed(seed)
    class Decoder(torch.nn.Module):
        def __init__(self):
            super().__init__()
            if prior:
                self.bias = torch.nn.ParameterDict({g:torch.nn.Parameter(torch.zeros(k)) for g,k in relic.HEAD_CLASSES.items()})
            else:
                self.delta = torch.nn.Embedding(classes,16)
                self.mask = torch.nn.Embedding(32,8)
                self.shared = torch.nn.Sequential(torch.nn.Linear(89,64),torch.nn.ReLU())
                self.heads = torch.nn.ModuleDict({g:torch.nn.Linear(64,k) for g,k in relic.HEAD_CLASSES.items()})
        def forward(self,z,delta,fraction,mask):
            if prior:
                return {g:b.expand(len(z),-1) for g,b in self.bias.items()}
            x=self.shared(torch.cat((z.detach(),self.delta(delta),fraction[:,None],self.mask(mask)),-1))
            return {g:h(x) for g,h in self.heads.items()}
    return Decoder()


def constraint_nll(torch, logits, compatible):
    logp=torch.log_softmax(logits,-1)
    if not bool(compatible.any(-1).all()):
        raise ValueError('empty compatible set')
    return -torch.logsumexp(logp.masked_fill(~compatible,-torch.inf),-1)


def partial_loss(torch, logits, compatible, observed):
    values=torch.stack([constraint_nll(torch,logits[g],compatible[g]) for g in HEADS],-1)
    return ((values*observed).sum(-1)/observed.sum(-1).clamp_min(1)).mean()


def classify(ci, gap, validity):
    if any(validity.values()) or ci[0]>0:
        return 'RELIC_TRAJECTORY_REJECTED'
    if ci[1]<0 and gap<=RECIPE['exposureThreshold']:
        return 'RELIC_TRAJECTORY_QUALIFIED'
    return 'RELIC_TRAJECTORY_INCONCLUSIVE'


def mixture_nll(logmass):
    maximum=np.max(logmass,axis=0)
    return -(maximum+np.log(np.exp(logmass-maximum).mean(0)))


def sample_supported_relics(torch, model, predictor_input, pre, z, signed_delta,
                            ending_hp, maximum, mask, classes, trained_heads,
                            victory, hp_supported, rng):
    """Offline fail-closed adapter; None delegates to the existing fallback.

    Upstream outcomes must already be sampled. No C++ integration or additional
    encoder forward is performed here. Unsupervised active heads are excluded.
    """
    if not victory or not hp_supported or not base.supported_for_surrogate(predictor_input, pre) or not frozen.potion_consumption_only(predictor_input):
        return None
    if maximum <= 0 or not 1 <= ending_hp <= maximum or ending_hp != pre['curHp']+signed_delta:
        return None
    where=np.flatnonzero(np.asarray(classes)==signed_delta)
    if len(where)!=1: return None
    bloom=any(x['relicId']==base._RELIC_IDS['MARK_OF_THE_BLOOM'] for x in predictor_input['relics'])
    encounter=predictor_input['globals']['encounter']
    try:
        potion.decode_masks(np.asarray([pre['potions']]),np.asarray([pre['potionCapacity']]),np.asarray([mask]))
        for entry in pre['relics']:
            name=relic.NAMES.get(entry['id'])
            if name is None: continue
            allowed=relic.legal_posts(entry['id'],entry['data'],encounter,bloom)
            group=relic.TRAJECTORY[name][0] if name in relic.TRAJECTORY else 'lizard' if name=='LIZARD_TAIL' and len(allowed)>1 else None
            if group is not None and group not in trained_heads: return None
    except ValueError:
        return None
    device=next(model.parameters()).device
    with torch.inference_mode():
        logits=model(torch.as_tensor(np.asarray(z,dtype=np.float32)[None],device=device),torch.as_tensor(where,device=device),torch.as_tensor([ending_hp/maximum],device=device,dtype=torch.float32),torch.as_tensor([mask],device=device,dtype=torch.long))
        residues={g:int(rng.choice(relic.HEAD_CLASSES[g],p=torch.softmax(v[0],-1).cpu().numpy().astype(float)/torch.softmax(v[0],-1).cpu().numpy().astype(float).sum())) for g,v in logits.items()}
    return relic.reconstruct(pre['relics'],residues,encounter,bloom)


def log_constraints(logp, compatible, observed):
    out=[]
    for j,g in enumerate(HEADS):
        x=np.where(compatible[g],logp[g],-np.inf)
        m=x.max(-1)
        out.append(-(m+np.log(np.exp(x-m[:,None]).sum(-1)))*observed[:,j])
    return np.stack(out,-1)


def inputs(torch, cache, ids, device, sampled=None):
    delta,fraction,mask=(cache['deltaClass'][ids],cache['fraction'][ids],cache['potionMask'][ids]) if sampled is None else sampled
    return tuple(torch.as_tensor(v,device=device) for v in (cache['z'][ids],delta,fraction,mask))


def predict(torch, model, cache, ids, sampled=None):
    outputs={g:[] for g in HEADS}; model.eval()
    with torch.inference_mode():
        for start in range(0,len(ids),RECIPE['batch']):
            sub=ids[start:start+RECIPE['batch']]
            conditions=None if sampled is None else tuple(v[start:start+len(sub)] for v in sampled)
            logits=model(*inputs(torch,cache,sub,next(model.parameters()).device,conditions))
            for g in HEADS: outputs[g].append(torch.log_softmax(logits[g],-1).cpu().numpy().astype(float))
    return {g:np.concatenate(v) for g,v in outputs.items()}


def prepare(args):
    import torch
    output=Path(args.output_dir); output.mkdir(parents=True,exist_ok=True)
    if (output/'cache.npz').exists(): raise ValueError('refusing to overwrite cache')
    arrays,train,holdout,pre,post,maximum,delta,_,_,metadata=hp.load(Path(args.prepared_dir))
    corpus=Path(args.corpus)
    if base.sha256(corpus)!=hp.attention.EXPECTED_CORPUS_SHA256: raise ValueError('corpus hash differs')
    for path,digest in [(Path(args.hp_checkpoint),HP_HASH),(Path(args.potion_dir)/'joint.pt',POTION_HASH),(Path(args.potion_dir)/'encoder.pt',ENCODER_HASH)]:
        if base.sha256(path)!=digest: raise ValueError(f'upstream hash differs: {path}')
    n=len(pre); certified=np.zeros(n,bool); observed=np.zeros((n,len(HEADS)),bool)
    compatible={g:np.ones((n,k),bool) for g,k in relic.HEAD_CLASSES.items()}
    relic_pre=np.zeros_like(arrays['relics'][:,:,1],dtype=np.int64); relic_post=relic_pre.copy()
    active=np.zeros(n,bool); both=np.zeros(n,bool); counts={'corpusRows':0,'globalSupported':0,'contradictoryConstraints':0,'unreachableTargets':0,'nativeReconstructionMismatches':0,'unsupportedMutableMutations':0}
    encounter_index=list(base.GLOBAL_CATEGORY_COUNTS).index('encounter')
    for i,row in enumerate(base.iter_rows(corpus)):
        if i>=n or (row['sourceSeed'],row['fightIdx'])!=(arrays['sourceSeed'][i],arrays['fightIdx'][i]): raise ValueError('corpus alignment differs')
        counts['corpusRows']+=1; pi=row['predictorInput']; before=row['transition']['pre']; after=row['transition']['post']
        supported=base.supported_for_surrogate(pi,before)
        if supported!=bool(arrays['supported'][i]): raise ValueError('support differs')
        certified[i]=frozen.potion_consumption_only(pi)
        if not supported: continue
        counts['globalSupported']+=1
        if not np.array_equal(arrays['potions'][i,:,1],before['potions']) or not np.array_equal(arrays['y_potions'][i],after['potions']): raise ValueError('potion alignment differs')
        if certified[i]: potion.encode_masks(np.asarray([before['potions']]),np.asarray([after['potions']]),np.asarray([before['potionCapacity']]))
        bloom=any(x['relicId']==base._RELIC_IDS['MARK_OF_THE_BLOOM'] for x in pi['relics'])
        visible=[(x['relicId'],x['data']) for x in pi['relics']]
        if visible!=[(x['id'],x['data']) for x in before['relics']]: raise ValueError('predictor relic counters differ')
        constraints=relic.trajectory_constraints(before['relics'],after['relics'],pi['globals']['encounter'],bloom)
        for j,g in enumerate(HEADS):
            if g in constraints:
                compatible[g][i]=np.isin(np.arange(relic.HEAD_CLASSES[g]),list(constraints[g])); observed[i,j]=True
        active[i]=any(x['id']==base._RELIC_IDS['LIZARD_TAIL'] and x['data']==1 for x in before['relics'])
        both[i]='lizard' in constraints
        for t,(a,b) in enumerate(zip(before['relics'],after['relics'])): relic_pre[i,t]=a['data']; relic_post[i,t]=b['data']
        if i and i%100000==0: print(f'structural audit {i}',flush=True)
    if counts['corpusRows']!=n: raise ValueError('corpus length differs')
    train=train[certified[train]]; holdout=holdout[certified[holdout]]
    ids=np.concatenate((train,holdout)); hp_checkpoint=torch.load(args.hp_checkpoint,map_location='cpu',weights_only=False)
    classes=hp_checkpoint['state_dict']['classes'].numpy()
    expected,domain=stochastic.freeze_domain(pre,arrays['preMaxHp'],metadata['deltaValues'],arrays['supported'])
    if not np.array_equal(classes,expected) or domain!=hp_checkpoint['metadata']['domain']: raise ValueError('HP domain differs')
    stochastic.check_targets(classes,pre[ids],maximum[ids],post[ids])
    cache=dict(train=train,holdout=holdout,source=arrays['sourceSeed'],preHp=pre,maxHp=maximum,
               deltaClass=(post-pre-classes[0]).astype(np.int64),fraction=(post/maximum).astype(np.float32),
               observed=observed,activeLizard=active,bothLizard=both,relicPre=relic_pre,relicPost=relic_post,
               relicIds=arrays['relics'][:,:,0].astype(np.int64),relicMask=arrays['relic_mask'],
               encounter=arrays['global_categories'][:,encounter_index],
               bloom=np.any((arrays['relics'][:,:,0]==base._RELIC_IDS['MARK_OF_THE_BLOOM']) & arrays['relic_mask'],-1),
               prePotions=arrays['potions'][:,:,1].astype(np.int64),capacity=arrays['potionCapacity'].astype(np.int64),
               maxDelta=delta.astype(np.int64),classes=classes,
               act=arrays['globals_continuous'][:,base.CONTINUOUS_GLOBAL_FIELDS.index('act')],
               room=arrays['global_categories'][:,list(base.GLOBAL_CATEGORY_COUNTS).index('roomClass')])
    cache.update({f'compatible_{g}':v for g,v in compatible.items()})
    cache['potionMask']=np.zeros(n,np.int64)
    cache['potionMask'][ids]=potion.encode_masks(cache['prePotions'][ids],arrays['y_potions'][ids],cache['capacity'][ids])
    torch.set_num_threads(4); torch.backends.mha.set_fastpath_enabled(False)
    mean=arrays['globals_continuous'][train].mean(0); std=arrays['globals_continuous'][train].std(0)
    model=stochastic.new_model(torch,mean,std,len(metadata['deltaValues']),classes,20260912)
    model.load_state_dict(hp_checkpoint['state_dict']); model.cuda().eval().requires_grad_(False)
    potion_encoder=hp.attention.AttentionPointControlNet(torch,mean,std).net
    potion_encoder.load_state_dict(torch.load(Path(args.potion_dir)/'encoder.pt',map_location='cpu',weights_only=False)['stateDict'])
    potion_encoder.cuda().eval().requires_grad_(False)
    cache['z']=np.zeros((n,64),np.float32); cache['potionZ']=np.zeros((n,64),np.float32)
    cache['hpProbability']=np.zeros((len(holdout),len(classes)),np.float32)
    before=hp.state_hash(model)
    with torch.inference_mode():
        for start in range(0,len(ids),RECIPE['batch']):
            sub=ids[start:start+RECIPE['batch']]; tensors=base._torch_inputs(arrays,sub,'cuda',torch,trim_padding=True)
            # Match qualified HP's AMP encoder evaluation, then cache FP32.
            with torch.autocast('cuda',dtype=torch.float16): z=model.encoder(*tensors)
            cache['z'][sub]=z.float().cpu().numpy()
            cache['potionZ'][sub]=potion_encoder.encoder(*tensors).cpu().numpy()
            if start% (RECIPE['batch']*20)==0: print(f'cache {start}/{len(ids)}',flush=True)
        for start in range(0,len(holdout),RECIPE['batch']):
            sub=holdout[start:start+RECIPE['batch']]
            with torch.autocast('cuda',dtype=torch.float16):
                logits=model(base._torch_inputs(arrays,sub,'cuda',torch,trim_padding=True),torch.as_tensor(delta[sub],device='cuda'),torch.as_tensor(pre[sub],device='cuda'),torch.as_tensor(maximum[sub],device='cuda'))
            cache['hpProbability'][start:start+len(sub)]=torch.softmax(logits,-1).cpu().numpy()
    if before!=hp.state_hash(model) or any(p.grad is not None for p in model.parameters()): raise ValueError('HP encoder changed')
    metadata.pop('normalization')
    metadata.update(counts={part:dict(rows=len(sub),sources=len(np.unique(cache['source'][sub])),supervision={g:int(observed[sub,j].sum()) for j,g in enumerate(HEADS)},activeLizard=int(active[sub].sum()),bothLegalLizard=int(both[sub].sum())) for part,sub in [('train',train),('holdout',holdout)]},
                    structuralAudit=counts,hpCheckpointSha256=HP_HASH,potionCheckpointSha256=POTION_HASH,potionEncoderSha256=ENCODER_HASH,
                    hpDomain=domain,encoderFrozen=True,encoderUnchanged=True)
    np.savez_compressed(output/'cache.npz',**cache)
    metadata['cacheSha256']=base.sha256(output/'cache.npz')
    base.json_dump(output/'preflight.json',metadata)
    base.json_dump(output/'recipe.json',dict(RECIPE,baselineSha=args.baseline_sha))
    print(json.dumps(metadata['counts']),flush=True)


def reconstruction_metrics(cache,ids,modes):
    truth=cache['relicPost'][ids]; predicted=cache['relicPre'][ids].copy(); native=predicted.copy(); validity=dict(illegalRelicSamples=0,sameGroupConsistencyViolations=0,unsupportedMutableMutations=0,deterministicNativeMismatches=0)
    for local,row in enumerate(ids):
        tokens=np.flatnonzero(cache['relicMask'][row]); entries=[dict(id=int(cache['relicIds'][row,t]),data=int(cache['relicPre'][row,t])) for t in tokens]
        kwargs=dict(encounter=int(cache['encounter'][row]),mark_of_bloom=bool(cache['bloom'][row]))
        result=relic.reconstruct(entries,{g:int(modes[g][local]) for g in HEADS},**kwargs)
        for t,a,b in zip(tokens,entries,result):
            predicted[local,t]=b['data']; name=relic.NAMES.get(a['id'])
            if name is not None:
                allowed=relic.legal_posts(a['id'],a['data'],**kwargs)
                if b['data'] not in allowed: validity['illegalRelicSamples']+=1
                if len(allowed)==1:
                    native[local,t]=next(iter(allowed))
                    validity['deterministicNativeMismatches']+=int(b['data']!=next(iter(allowed)))
                elif name in relic.TRAJECTORY:
                    group,_=relic.TRAJECTORY[name]
                    validity['sameGroupConsistencyViolations']+=int((b['data']-a['data'])%relic.CYCLIC[name]!=int(modes[group][local])%relic.CYCLIC[name])
            elif b['data']!=a['data']: validity['unsupportedMutableMutations']+=1
    mask=cache['relicMask'][ids]; changed=(truth!=cache['relicPre'][ids]) & mask
    learned=np.isin(cache['relicIds'][ids], [base._RELIC_IDS[n] for n in relic.TRAJECTORY]+[base._RELIC_IDS['LIZARD_TAIL']])
    changed_rows=np.any(changed & learned,-1)
    def metric(pred,tokenmask=mask):
        error=np.abs(pred-truth); exact=np.all((error==0)|~tokenmask,-1)
        def avg(v,m): return float(v[m].mean()) if m.any() else None
        return dict(rows=len(ids),tokens=int(tokenmask.sum()),changedTokens=int((changed & tokenmask).sum()),
                    fullVectorExact=float(exact.mean()),changedVectorRows=int(changed_rows.sum()),fullVectorExactChanged=avg(exact,changed_rows),
                    tokenExact=avg(error==0,tokenmask),changedTokenExact=avg(error==0,changed & tokenmask),
                    tokenMae=avg(error,tokenmask),changedTokenMae=avg(error,changed & tokenmask))
    return dict(decoder=metric(predicted),nativeCopyThrough=metric(native),byRelic={name:dict(decoder=metric(predicted,mask & (cache['relicIds'][ids]==base._RELIC_IDS[name])),nativeCopyThrough=metric(native,mask & (cache['relicIds'][ids]==base._RELIC_IDS[name]))) for name in list(relic.TRAJECTORY)+['LIZARD_TAIL']}),validity,predicted


def head_metrics(logp,compatible,observed):
    scores=log_constraints(logp,compatible,observed); result={}
    for j,g in enumerate(HEADS):
        selected=observed[:,j]; p=np.exp(logp[g]); mode=p.argmax(-1); correct=compatible[g][np.arange(len(p)),mode]; confidence=p.max(-1)
        bins=[]
        for b in range(RECIPE['calibrationBins']):
            m=selected & (confidence>=b/10) & ((confidence<(b+1)/10) if b<9 else (confidence<=1+1e-6))
            bins.append(dict(rows=int(m.sum()),confidence=float(confidence[m].mean()) if m.any() else None,modeCompatibility=float(correct[m].mean()) if m.any() else None))
        exact=selected & (compatible[g].sum(-1)==1)
        result[g]=dict(rows=int(selected.sum()),exactLabelRows=int(exact.sum()),nll=float(scores[selected,j].mean()) if selected.any() else None,
                       exactLabelNll=float(scores[exact,j].mean()) if exact.any() else None,modeCompatibility=float(correct[selected].mean()) if selected.any() else None,
                       calibration=dict(convention='mode probability versus compatible-set correctness; partial labels do not identify full-class calibration',bins=bins))
        if g=='lizard': result[g]['brier']=float(np.sum((p[exact]-compatible[g][exact])**2,-1).mean()) if exact.any() else None
    return result


def slices(cache,ids,teacher,ancestral,sampled_hp,sampled_masks):
    observed=cache['observed'][ids].sum(-1); true_loss=cache['preHp'][ids]-(cache['preHp'][ids]+cache['deltaClass'][ids]+cache['classes'][0]); masks={}
    for act in (1,2,3): masks[f'act:{act}']=cache['act'][ids]==act
    # Canonical room enum IDs, rather than guessed numeric values.
    for name in ('NORMAL','ELITE','BOSS','EVENT'):
        key={'NORMAL':'MONSTER','ELITE':'ELITE','BOSS':'BOSS','EVENT':'EVENT'}[name]
        room_ids=base._enum_values(base._ROOT / 'include/constants/Rooms.h','Room')
        masks[f'room:{name}']=cache['room'][ids]==room_ids[key]
    for low,high in [(-np.inf,0),(0,1),(1,10),(10,30),(30,np.inf)]:
        masks[f'trueHpLoss:[{low},{high})']=(true_loss>=low)&(true_loss<high)
    for key,m in [('potionChanged',cache['potionMask'][ids]!=0),('potionUnchanged',cache['potionMask'][ids]==0),('zeroConsumption',cache['potionMask'][ids]==0),('nonzeroConsumption',cache['potionMask'][ids]!=0),('oneGroup',observed==1),('multipleGroups',observed>1)]: masks[key]=m
    result={k:dict(rows=int(m.sum()),teacherNll=float(teacher[m].mean()) if m.any() else None,ancestralNll=float(ancestral[m].mean()) if m.any() else None) for k,m in masks.items()}
    # Draw-conditional slices are explicitly distinguished from row mixture NLL.
    result['sampledHpLoss']={}
    loss=cache['preHp'][ids][None,:]-sampled_hp
    for low,high in [(-np.inf,0),(0,1),(1,10),(10,30),(30,np.inf)]:
        m=(loss>=low)&(loss<high)
        result['sampledHpLoss'][f'[{low},{high})']=dict(draws=int(m.sum()),rows=int(m.any(0).sum()),teacherNll=float(np.broadcast_to(teacher,loss.shape)[m].mean()) if m.any() else None,ancestralMixtureRowNll=float(np.broadcast_to(ancestral,loss.shape)[m].mean()) if m.any() else None)
    result['sampledPotionConsumption']={str(value):dict(draws=int((sampled_masks==value).sum())) for value in np.unique(sampled_masks)}
    return result


def fit(args):
    import torch
    output=Path(args.output_dir); current=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if current!=args.reviewed_sha or subprocess.check_output(['git','status','--porcelain'],text=True).strip(): raise ValueError('requires clean independently reviewed SHA')
    if list(output.glob('relic-*.pt')) or (output/'results.json').exists(): raise ValueError('refusing repeated fit')
    metadata=json.loads((output/'preflight.json').read_text())
    if base.sha256(output/'cache.npz')!=metadata['cacheSha256']: raise ValueError('cache differs')
    if json.loads((output/'recipe.json').read_text())!=dict(RECIPE,baselineSha=args.baseline_sha): raise ValueError('recipe differs')
    if base.sha256(Path(args.hp_checkpoint))!=HP_HASH or base.sha256(Path(args.potion_dir)/'joint.pt')!=POTION_HASH: raise ValueError('upstream differs')
    with np.load(output/'cache.npz') as raw: cache={k:raw[k] for k in raw.files}
    train=cache['train']; ids=cache['holdout']; classes=cache['classes']; compatible={g:cache[f'compatible_{g}'] for g in HEADS}
    torch.set_num_threads(4); device='cuda' if torch.cuda.is_available() else 'cpu'; audits=[]
    for seed in RECIPE['seeds']:
        for prior in (False,True):
            model=new_decoder(torch,len(classes),seed,prior).to(device); initial=hp.state_hash(model)
            optimizer=torch.optim.AdamW(model.parameters(),lr=RECIPE['lr'],weight_decay=RECIPE['weightDecay']); rng=np.random.default_rng(seed); digest=hashlib.sha256(); history=[]
            for epoch in range(RECIPE['epochs']):
                model.train(); total=0.
                for sub in base._batches(train,RECIPE['batch'],rng):
                    digest.update(sub.tobytes()); optimizer.zero_grad(set_to_none=True)
                    logits=model(*inputs(torch,cache,sub,device))
                    loss=partial_loss(torch,logits,{g:torch.as_tensor(compatible[g][sub],device=device) for g in HEADS},torch.as_tensor(cache['observed'][sub],device=device))
                    if not torch.isfinite(loss): raise ValueError('nonfinite loss')
                    loss.backward(); norm=torch.nn.utils.clip_grad_norm_(model.parameters(),RECIPE['clip'])
                    if not torch.isfinite(norm): raise ValueError('nonfinite gradient')
                    optimizer.step(); total+=float(loss.detach())*len(sub)
                history.append(total/len(train)); print(json.dumps(dict(seed=seed,prior=prior,epoch=epoch+1,loss=history[-1])),flush=True)
            audit=dict(seed=seed,prior=prior,initialization=initial,batchOrder=digest.hexdigest(),trainLoss=history); audits.append(audit)
            torch.save(dict(state_dict=base._safe_state_dict(model),audit=audit,reviewedSha=current),output/f'relic-{seed}-{int(prior)}.pt')
    # Every fixed fit is complete before any HOLDOUT scoring.
    results={}; raw=dict(rowIds=ids,source=cache['source'][ids]); differences=[]; gaps=[]; all_validity={k:0 for k in ('illegalRelicSamples','sameGroupConsistencyViolations','unsupportedMutableMutations','deterministicNativeMismatches')}
    pc=potion.new_decoder('joint',len(json.loads((output/'preflight.json').read_text())['deltaValues'])).to(device)
    pc.load_state_dict(torch.load(Path(args.potion_dir)/'joint.pt',map_location='cpu',weights_only=False)); pc.eval().requires_grad_(False)
    for seed in RECIPE['seeds']:
        models=[]
        for prior in (False,True):
            m=new_decoder(torch,len(classes),seed,prior).to(device); m.load_state_dict(torch.load(output/f'relic-{seed}-{int(prior)}.pt',map_location='cpu',weights_only=False)['state_dict']); models.append(m)
        model,prior=models; selected={g:compatible[g][ids] for g in HEADS}; obs=cache['observed'][ids]
        teacher=predict(torch,model,cache,ids); bias=predict(torch,prior,cache,ids)
        perhead=log_constraints(teacher,selected,obs); tnll=perhead.sum(-1); bnll=log_constraints(bias,selected,obs).sum(-1); differences.append(tnll-bnll)
        modes={g:x.argmax(-1) for g,x in teacher.items()}; reconstructed,validity,counters=reconstruction_metrics(cache,ids,modes)
        raw[f'{seed}-teacherNll']=tnll; raw[f'{seed}-priorNll']=bnll; raw[f'{seed}-modeCounters']=counters
        for g in HEADS: raw[f'{seed}-teacher-{g}']=teacher[g]
        results[str(seed)]=dict(teacherNll=float(tnll.mean()),priorNll=float(bnll.mean()),pairedDifference=float((tnll-bnll).mean()),reconstructed=reconstructed,heads=head_metrics(teacher,selected,obs))
        # Freeze teacher-forced outputs before ancestral exposure qualification.
        base.json_dump(output/f'teacher-{seed}.json',results[str(seed)])
        rng=np.random.default_rng(RECIPE['samplingSeed']+seed); sampled_hp,_=stochastic.sample_hp(cache['hpProbability'],classes,cache['preHp'][ids],cache['maxHp'][ids],rng,16)
        drawmass=[]; sampled_masks=[]; sample_counters=[]
        for draw in range(16):
            fraction=(sampled_hp[:,draw]/cache['maxHp'][ids]).astype(np.float32); maskparts=[]
            with torch.inference_mode():
                for start in range(0,len(ids),RECIPE['batch']):
                    sub=ids[start:start+RECIPE['batch']]
                    values=(cache['potionZ'][sub],cache['prePotions'][sub],cache['capacity'][sub],cache['maxDelta'][sub],fraction[start:start+len(sub)])
                    logp=pc(*(torch.as_tensor(v,device=device) for v in values)).cpu().numpy()
                    p=np.exp(logp.astype(float)); p/=p.sum(-1,keepdims=True)
                    maskparts.extend(rng.choice(32,p=v) for v in p)
            mask=np.asarray(maskparts,np.int64); sampled_masks.append(mask)
            potion.decode_masks(cache['prePotions'][ids],cache['capacity'][ids],mask)
            conditions=((sampled_hp[:,draw]-cache['preHp'][ids]-classes[0]).astype(np.int64),fraction,mask)
            ancestral=predict(torch,model,cache,ids,conditions); drawmass.append(-log_constraints(ancestral,selected,obs).sum(-1))
            residues={g:np.asarray([rng.choice(relic.HEAD_CLASSES[g],p=np.exp(p)/np.exp(p).sum()) for p in ancestral[g]]) for g in HEADS}
            _,v,sample=reconstruction_metrics(cache,ids,residues); sample_counters.append(sample)
            for k,value in v.items(): validity[k]+=value
        ancestral_nll=mixture_nll(np.stack(drawmass)); informative=obs.sum(-1)>0
        gap=float(((ancestral_nll-tnll)[informative]/obs.sum(-1)[informative]).mean()); gaps.append(gap)
        results[str(seed)].update(ancestralMixtureNll=float(ancestral_nll.mean()),normalizedExposureGap=gap,ancestralClassification='ANCESTRAL_EXPOSURE_GAP' if gap>.1 else 'ANCESTRAL_OK',samplingValidity=validity,
                                 slices=slices(cache,ids,tnll,ancestral_nll,sampled_hp.T,np.stack(sampled_masks)))
        raw[f'{seed}-ancestralNll']=ancestral_nll; raw[f'{seed}-drawLogMass']=np.stack(drawmass); raw[f'{seed}-sampleHp']=sampled_hp; raw[f'{seed}-samplePotionMasks']=np.stack(sampled_masks); raw[f'{seed}-sampleCounters']=np.stack(sample_counters)
        for k,v in validity.items(): all_validity[k]+=v
        print(json.dumps(dict(seed=seed,primary=results[str(seed)]['pairedDifference'],exposure=gap,validity=validity)),flush=True)
    bootstrap=hp.bootstrap(cache['source'][ids],np.stack(differences).mean(0)); gap=float(np.mean(gaps))
    torch.set_num_threads(1); model.cpu().eval(); single=inputs(torch,cache,ids[:1],'cpu'); times=[]
    with torch.inference_mode():
        for _ in range(10): model(*single)
        for _ in range(100):
            start=time.perf_counter(); model(*single); times.append((time.perf_counter()-start)*1000)
    evidence=dict(baselineSha=args.baseline_sha,reviewedExecutionSha=current,recipe=RECIPE,provenance=metadata,trainingAudits=audits,metrics=results,
                  bootstrap=bootstrap,ancestralNormalizedExposureGap=gap,ancestralClassification='ANCESTRAL_EXPOSURE_GAP' if gap>.1 else 'ANCESTRAL_OK',validity=all_validity,
                  parameterCount=sum(p.numel() for p in model.parameters()),cpuLatency=dict(batch=1,threads=1,warmups=10,draws=100,meanMs=float(np.mean(times)),p95Ms=float(np.quantile(times,.95))),
                  classification=classify(bootstrap['ci95'],gap,all_validity),upstreamComponentsUnchanged=True)
    np.savez_compressed(output/'predictions.npz',**raw); base.json_dump(output/'results.json',evidence)
    base.json_dump(output/'artifact-hashes.json',{p.name:base.sha256(p) for p in output.iterdir() if p.suffix in ('.json','.pt','.npz') and p.name!='artifact-hashes.json'})
    print(json.dumps(dict(classification=evidence['classification'],bootstrap=bootstrap,exposure=gap)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('command',choices=['prepare','fit'])
    parser.add_argument('--prepared-dir',default='/tmp/sts-phase2-attention-audit-20260913')
    parser.add_argument('--corpus',default='/home/philippherrmann/sts_sweep/runs/combat-transition-runtime-25k/combat-transition-25k.jsonl')
    parser.add_argument('--hp-checkpoint',default='/home/philippherrmann/sts_sweep/runs/stochastic-hp-20260914/20260912.pt')
    parser.add_argument('--potion-dir',default='/home/philippherrmann/sts_sweep/runs/joint-potion-mask-20260913')
    parser.add_argument('--output-dir',required=True); parser.add_argument('--baseline-sha',required=True); parser.add_argument('--reviewed-sha')
    args=parser.parse_args(); (prepare if args.command=='prepare' else fit)(args)
