#!/usr/bin/env python3
"""Source-frozen small Stage-2 heads; existing encoders/heads remain unchanged."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import numpy as np
import torch
from tools import combat_transition_composed as c
from tools import combat_transition_composed_evaluate as e
from tools import combat_transition_sparse_events as native

RECIPE=dict(seed=20260912,epochs=12,batch=512,lr=.001,weightDecay=.0001,draws=32,samplingSeed=20260920,
            selection='earliest strict minimum original VALIDATION NLL',training='new sparse scorer only; original TRAIN victories',
            exposure='32 upstream maxHP/HP draws; exact conditional potion-mask marginal',threshold=.1)


def net():
    torch.manual_seed(RECIPE['seed'])
    class Scorer(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.context=torch.nn.Sequential(torch.nn.Linear(64+3+5+5,64),torch.nn.ReLU(),torch.nn.Linear(64,32))
            self.event=torch.nn.Sequential(torch.nn.Linear(3,32),torch.nn.Tanh())
        def forward(self,z,hp,bits,features,candidates,legal):
            context=self.context(torch.cat((z.detach(),hp,bits,features),-1))
            # Shared per-card embedding: no separately fitted duplicate-card branch.
            embedded=self.event(candidates).sum(-2)
            logits=(embedded*context[:,None]).sum(-1)/np.sqrt(32)
            if not legal.any(-1).all():raise ValueError('empty native event support')
            return torch.log_softmax(logits.masked_fill(~legal,-torch.inf),-1)
    return Scorer()


def frozen(sha):
    if e.snapshot()!=sha or subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise ValueError('require frozen clean source SHA')


def prepare(folder,mechanism,sha):
    frozen(sha)
    if folder.exists():raise ValueError('refusing overwrite')
    hashes=e.verify_data();arrays,_=c.base._load_prepared(e.PREPARED);m=c.FrozenModels('cpu')
    records=[];excluded=0
    for index,row in enumerate(c.base.iter_rows(e.CORPUS)):
        pre,post,pi=row['transition']['pre'],row['transition']['post'],row['predictorInput']
        active=pi['globals']['encounter']==c.base.WRITHING_MASS_ID if mechanism=='writhing' else any(card['cardId']==c.base._CARD_IDS['RITUAL_DAGGER'] for card in pi['cards'])
        if not active:continue
        if any(p in (c.base._POTION_IDS['ENTROPIC_BREW'],c.base._POTION_IDS['SMOKE_BOMB']) for p in pre['potions']) or pre['smokeBombUsed']:
            excluded+=1;continue # Trajectory/outcome modeled in Stages 3/4, not consumption-only masks.
        win=row['transition']['combatOutcome']==c.base.WIN
        mask=int(c.potion.encode_masks(np.asarray([pre['potions']]),np.asarray([post['potions']]),np.asarray([pre['potionCapacity']]))[0]) if win else 0
        omamori=next((r['data'] for r in pre['relics'] if r['id']==c.base._RELIC_IDS['OMAMORI']),0)
        darkstone=any(r['id']==c.base._RELIC_IDS['DARKSTONE_PERIAPT'] for r in pre['relics'])
        daggers=[card for card in pre['deck'] if card['id']==c.base._CARD_IDS['RITUAL_DAGGER']]
        candidates=[]; bymask=[]; true=0
        if mechanism=='writhing':
            posts=native.writhing_posts(pre)
            candidates=[np.asarray([[event,int(bool(omamori) and event),int(not omamori and event)]],np.float32) for event in range(len(posts))]
            bymask=[tuple(range(len(posts)))]*32
            true=native.writhing_target(pre,post) if win else 0
        else:
            bymask=[native.ritual_posts(pre,pi,mask) for mask in range(32)]
            union=sorted(set().union(*map(set,bymask)))
            candidates=[np.asarray([[card['misc']/100,int(card['upgraded']),amount/20] for card,amount in zip(daggers,event)],np.float32) for event in union]
            if win:
                adjusted=pre
                if pi['globals']['encounter']==c.base.WRITHING_MASS_ID:adjusted=native.writhing_posts(pre)[native.writhing_target(pre,post)]
                changes=tuple(x['delta'] for x in native.ritual_changes(adjusted,post))
                if changes not in bymask[mask]:raise ValueError(f'native Ritual target missing at index={index}: {changes}')
                true=union.index(changes)
            bymask=[tuple(union.index(event) for event in events) for events in bymask]
        delta=post['maxHp']-pre['maxHp']; signed=post['curHp']-pre['curHp']
        if win and (delta not in m.delta_values or signed not in c.CLASSES):raise ValueError(f'upstream target domain at index={index}, delta={delta}, signed={signed}')
        records.append(dict(index=index,pre=pre,post=post,pi=pi,win=win,split=int(arrays['split_id'][index]),source=row['sourceSeed'],
                            mask=mask,target=true,candidates=candidates,byMask=bymask,features=[omamori/2,int(darkstone),len(daggers),sum(int(d['upgraded']) for d in daggers),int(mechanism=='writhing')]))
    n=len(records);width=max(len(r['candidates']) for r in records);cards=max(v.shape[0] for r in records for v in r['candidates'])
    cache=dict(ids=np.asarray([r['index'] for r in records]),win=np.asarray([r['win'] for r in records]),split=np.asarray([r['split'] for r in records]),source=np.asarray([r['source'] for r in records]),
               target=np.asarray([r['target'] for r in records]),mask=np.asarray([r['mask'] for r in records]),features=np.asarray([r['features'] for r in records],np.float32),
               preHp=np.asarray([r['pre']['curHp'] for r in records]),preMax=np.asarray([r['pre']['maxHp'] for r in records]),
               trueHp=np.asarray([r['post']['curHp'] for r in records]),trueMax=np.asarray([r['post']['maxHp'] for r in records]),
               potions=np.asarray([r['pre']['potions'] for r in records]),capacity=np.asarray([r['pre']['potionCapacity'] for r in records]),
               candidates=np.zeros((n,width,cards,3),np.float32),legal=np.zeros((n,32,width),bool))
    for i,r in enumerate(records):
        for j,candidate in enumerate(r['candidates']):cache['candidates'][i,j,:len(candidate)]=candidate
        for mask,events in enumerate(r['byMask']):cache['legal'][i,mask,list(events)]=True
    torch.set_num_threads(4);m.to('cuda');cache['z']=np.zeros((n,64),np.float32);cache['pDelta']=np.zeros((n,len(m.delta_values)),float);cache['potionZ']=np.zeros_like(cache['z'])
    with torch.inference_mode():
        for start in range(0,n,512):
            sub=np.arange(start,min(start+512,n)); inputs=c.base._torch_inputs(arrays,cache['ids'][sub],'cuda',torch,trim_padding=True)
            cache['z'][sub]=m.hp_encoding(inputs).cpu().numpy();cache['potionZ'][sub]=m.fp32_encoding(m.potion_encoder.encoder,inputs).cpu().numpy()
            cache['pDelta'][sub]=e.probabilities(m.max_net.max_hp_delta(m.fp32_encoding(m.max_net.encoder,inputs)))
    folder.mkdir(parents=True);np.savez_compressed(folder/'cache.npz',**cache)
    test=[dict(local=i,pre=r['pre'],post=r['post'],pi=r['pi']) for i,r in enumerate(records) if r['split']==2]
    (folder/'test_rows.json').write_text(json.dumps(test))
    metadata=dict(sourceSha=sha,mechanism=mechanism,hashes=hashes,recipe=RECIPE,rows=n,excludedUntilStages34=excluded,
                  counts={k:dict(rows=int((cache['split']==s).sum()),victories=int(((cache['split']==s)&cache['win']).sum())) for s,k in enumerate(('train','validation','test'))},
                  cacheSha256=c.base.sha256(folder/'cache.npz'),testRowsSha256=c.base.sha256(folder/'test_rows.json'))
    c.base.json_dump(folder/'preparation.json',metadata);print(json.dumps(metadata),flush=True)


def load(folder,sha):
    frozen(sha);meta=json.loads((folder/'preparation.json').read_text())
    if meta['sourceSha']!=sha or meta['hashes']!=e.verify_data() or meta['recipe']!=RECIPE or c.base.sha256(folder/'cache.npz')!=meta['cacheSha256'] or c.base.sha256(folder/'test_rows.json')!=meta['testRowsSha256']:raise ValueError('provenance differs')
    with np.load(folder/'cache.npz') as z:cache={k:z[k] for k in z.files}
    return cache,meta


def forward(model,cache,ids,mask=None,ending=None,maximum=None):
    mask=cache['mask'][ids] if mask is None else mask
    ending=cache['trueHp'][ids] if ending is None else ending;maximum=cache['trueMax'][ids] if maximum is None else maximum
    hp=np.stack(((ending-cache['preHp'][ids])/160,ending/maximum,(maximum-cache['preMax'][ids])/10),-1).astype(np.float32)
    legal=cache['legal'][ids,mask].copy()
    # Darkstone HP gain happens at Implant; disallow contradictory sampled event.
    if cache['features'][ids,4].all():
        tied=(cache['features'][ids,1]>0)&(cache['features'][ids,0]==0)&(maximum-cache['preMax'][ids]<6)
        legal[tied,1:]=False
    values=(cache['z'][ids],hp,c.potion.BITS[mask].astype(np.float32),cache['features'][ids],cache['candidates'][ids],legal)
    return model(*(torch.as_tensor(v,device='cuda') for v in values))


def fit(folder,sha):
    cache,meta=load(folder,sha)
    if (folder/'event.pt').exists():raise ValueError('refusing overwrite')
    torch.set_num_threads(4);model=net().cuda();opt=torch.optim.AdamW(model.parameters(),lr=RECIPE['lr'],weight_decay=RECIPE['weightDecay'])
    train=np.flatnonzero(cache['win']&(cache['split']==0));val=np.flatnonzero(cache['win']&(cache['split']==1));rng=np.random.default_rng(RECIPE['seed']);history=[];best=float('inf')
    def loss(ids):
        lp=forward(model,cache,ids);return -lp[torch.arange(len(ids),device='cuda'),torch.as_tensor(cache['target'][ids],device='cuda')]
    for epoch in range(RECIPE['epochs']):
        model.train();order=rng.permutation(train)
        for start in range(0,len(order),512):
            ids=order[start:start+512];opt.zero_grad();value=loss(ids).mean();value.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1);opt.step()
        model.eval()
        with torch.inference_mode():score=float(torch.cat([loss(val[s:s+512]) for s in range(0,len(val),512)]).mean())
        history.append(dict(epoch=epoch+1,validationNll=score));print(json.dumps(history[-1]),flush=True)
        if score<best:best=score;selected=epoch+1;state=copy.deepcopy(model.state_dict())
    torch.save(dict(stateDict=state,metadata=meta,history=history,selectedEpoch=selected),folder/'event.pt')
    c.base.json_dump(folder/'fit.json',dict(sourceSha=sha,history=history,selectedEpoch=selected,trainRows=len(train),validationRows=len(val),artifactSha256=c.base.sha256(folder/'event.pt')))


def diagnose(folder,sha):
    cache,meta=load(folder,sha)
    if (folder/'diagnostics.json').exists():raise ValueError('refusing overwrite')
    fitmeta=json.loads((folder/'fit.json').read_text())
    if c.base.sha256(folder/'event.pt')!=fitmeta['artifactSha256']:raise ValueError('checkpoint hash differs')
    payload=torch.load(folder/'event.pt',weights_only=False,map_location='cpu')
    if payload['metadata']!=meta:raise ValueError('checkpoint metadata differs')
    torch.set_num_threads(4);model=net().cuda().eval().requires_grad_(False);model.load_state_dict(payload['stateDict']);m=c.FrozenModels('cuda')
    test=np.flatnonzero(cache['win']&(cache['split']==2));teacher=np.empty(len(test));mass=np.empty((32,len(test)),float);p_all=[]
    with torch.inference_mode():
        for start in range(0,len(test),512):
            ids=test[start:start+512];p=forward(model,cache,ids).exp().cpu().numpy();p_all.append(p);teacher[start:start+len(ids)]=e.nll(p[np.arange(len(ids)),cache['target'][ids]])
        rng=np.random.default_rng(RECIPE['samplingSeed'])
        for draw in range(32):
            for start in range(0,len(test),512):
                ids=test[start:start+512];d=e.draw_categories(cache['pDelta'][ids],rng);maximum=cache['preMax'][ids]+m.delta_values[d]
                hp=e.hp_prob(m,cache['z'][ids],d,cache['preHp'][ids],maximum);ending=cache['preHp'][ids]+c.CLASSES[e.draw_categories(hp,rng)]
                pp=e.potion_prob(m,cache['potionZ'][ids],cache['potions'][ids],cache['capacity'][ids],d,ending/maximum);value=np.zeros(len(ids))
                for mask in range(32):
                    active=pp[:,mask]>0
                    if active.any():
                        p=forward(model,cache,ids[active],np.full(active.sum(),mask,np.int64),ending[active],maximum[active]).exp().cpu().numpy()
                        value[active]+=pp[active,mask]*p[np.arange(active.sum()),cache['target'][ids[active]]]
                mass[draw,start:start+len(ids)]=value
            print(meta['mechanism'],'exposure',draw+1,flush=True)
    mixture=e.nll(mass.mean(0));gap=mixture-teacher;p=np.concatenate(p_all);targets=cache['target'][test]
    gate=bool(np.isfinite(gap).all() and gap.mean()<=.1)
    result=dict(sourceSha=sha,mechanism=meta['mechanism'],classification='SPARSE_EVENT_EXPOSURE_PASS' if gate else 'SPARSE_EVENT_EXPOSURE_FAIL',eventExposureGate=gate,
                testVictories=len(test),jointNll=float(teacher.mean()),jointBrier=float((np.square(p).sum(-1)-2*p[np.arange(len(test)),targets]+1).mean()),modeExact=float((p.argmax(-1)==targets).mean()),
                exposure=e.source_gap_bootstrap(cache['source'][test],gap),zeroMixtureProbabilityRows=int((mass.mean(0)==0).sum()),
                hardValidity='pending complete sparse/gold/relic assembled draws',supportChanged=False,modelSha256=fitmeta['artifactSha256'])
    np.savez_compressed(folder/'diagnostic_rows.npz',ids=cache['ids'][test],teacherNll=teacher,mixtureNll=mixture,exposureGap=gap,source=cache['source'][test])
    c.base.json_dump(folder/'diagnostics.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=('prepare','fit','diagnose'));p.add_argument('--mechanism',choices=('writhing','ritual'));p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--source-sha',required=True);a=p.parse_args()
    if a.command=='prepare':prepare(a.output_dir,a.mechanism,a.source_sha)
    elif a.command=='fit':fit(a.output_dir,a.source_sha)
    else:diagnose(a.output_dir,a.source_sha)
