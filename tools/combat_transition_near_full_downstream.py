#!/usr/bin/env python3
"""Full-union downstream refit with exact hidden potion-trace marginalization."""
import argparse
import copy
import json
from pathlib import Path
import numpy as np
import torch
from tools import combat_transition_composed as c,combat_transition_composed_evaluate as e
from tools import combat_transition_potion_trajectory as t,combat_transition_potion_trajectory_evaluate as trajectory
from tools import combat_transition_gold as gold,combat_transition_gold_proc_budget as budget
from tools import combat_transition_sparse_events as native,combat_transition_sparse_evaluate as sparse

RECIPE=dict(seed=20260912,epochs=12,batch=512,lr=.001,weightDecay=.0001,clip=1.,
            selection='earliest strict minimum original VALIDATION normalized joint downstream NLL',
            population='entire final union original TRAIN survivors with observed downstream targets',
            features='existing HP state64; HP3; clearing bits5; exact native effects and escape condition',
            evidence='development using original source-grouped TEST; no fresh confirmation')
EVENT_CONDITIONS=('omamoriChargesOver2','darkstone','daggerCopies','upgradedDaggerCopies','writhingEncounter','escaped','upgradeRoute','colorlessConsumed')
RECIPE['nativeConditions']=dict(event=list(EVENT_CONDITIONS),relic=['escaped'],gold='native eligible kill budget decreases by one for escape')


def event_net(warm):
    net=sparse.net();net.load_state_dict(warm)
    old=net.context[0];new=torch.nn.Linear(80,64)
    with torch.no_grad():new.weight.zero_();new.weight[:,:77].copy_(old.weight);new.bias.copy_(old.bias)
    net.context[0]=new
    return net


def relic_net(warm):
    class Conditioned(torch.nn.Module):
        def __init__(self):
            super().__init__();self.delta=copy.deepcopy(warm.delta);self.mask=copy.deepcopy(warm.mask);self.shared=copy.deepcopy(warm.shared);self.heads=copy.deepcopy(warm.heads)
            old=self.shared[0];new=torch.nn.Linear(90,64)
            with torch.no_grad():new.weight.zero_();new.weight[:,:89].copy_(old.weight);new.bias.copy_(old.bias)
            self.shared[0]=new
        def forward(self,z,delta,fraction,mask,escaped):
            x=self.shared(torch.cat((z.detach(),self.delta(delta),fraction[:,None],self.mask(mask),escaped[:,None]),-1))
            return {name:head(x) for name,head in self.heads.items()}
    return Conditioned()


def load_upstream(parent,device='cuda'):
    m=c.FrozenModels(device);bindings={}
    for component,encoder,heads in [('survival',m.survival_net.encoder,[m.survival_net.survival]),('maxHP',m.max_net.encoder,[m.max_net.max_hp_delta]),('HP',m.hp_net.encoder,[m.hp_net.delta_embedding,m.hp_net.hp]),('potion',m.potion_encoder.encoder,[])]:
        folder=parent/('full-union-'+component+'-v1');meta=json.loads((folder/'fit.json').read_text())
        if c.base.sha256(folder/'component.pt')!=meta['artifactSha256']:raise ValueError('refit checkpoint differs')
        payload=torch.load(folder/'component.pt',map_location=device,weights_only=False);encoder.load_state_dict(payload['encoderStateDict'])
        if component=='potion':m.potion_net=t.new_decoder(len(m.delta_values),m.potion_net);heads=[m.potion_net]
        for head,state in zip(heads,payload['headStateDicts']):head.load_state_dict(state)
        bindings[component]=meta['artifactSha256']
    m.to(device);return m,bindings


def prepare(parent,output,sha):
    sparse.frozen(sha)
    if output.exists():raise ValueError('refusing overwrite')
    cache,graphs,meta=trajectory.load(parent/'potion-trajectory-v2');m,bindings=load_upstream(parent);arrays,spec=c.base._load_prepared(e.PREPARED);c.base._prepare_target_indices(arrays,spec)
    rawfolder=parent/'full-union-downstream-labels-v1';rawmeta=json.loads((rawfolder/'preparation.json').read_text())
    if c.base.sha256(rawfolder/'labels.npz')!=rawmeta['labelsSha256'] or c.base.sha256(rawfolder/'affected_rows.jsonl')!=rawmeta['rawSha256']:raise ValueError('native label binding differs')
    with np.load(rawfolder/'labels.npz') as raw:labels={k:raw[k] for k in raw.files}
    output.mkdir(parents=True);torch.set_num_threads(4);z=np.zeros((len(cache['ids']),64),np.float32);zp=np.zeros_like(z)
    with torch.inference_mode():
        for start in range(0,len(z),512):
            ids=np.arange(start,min(start+512,len(z)));inputs=c.base._torch_inputs(arrays,cache['ids'][ids],'cuda',torch,trim_padding=True)
            z[ids]=m.hp_encoding(inputs).cpu().numpy();zp[ids]=m.fp32_encoding(m.potion_encoder.encoder,inputs).cpu().numpy()
            if start%51200==0:print('final union downstream encoding',start,len(z),flush=True)
    traces=np.zeros(len(z),np.int64);posteriors={};error=0.
    for i in np.flatnonzero(cache['win']):
        mask=int(cache['mask'][i]);_,used=t.consume(cache['potions'][i],mask);flags=sum(1<<bit for bit,p in enumerate(t.EFFECT_IDS) if p in used);traces[i]=mask+32*flags
    with torch.inference_mode():
        special=np.asarray(sorted(graphs),np.int64)
        for start in range(0,len(special),128):
            ids=special[start:start+128];owners=np.concatenate([np.full(len(graphs[i].inventories),j) for j,i in enumerate(ids)]);rows=ids[owners]
            lp=t.log_probabilities(m.potion_net,zp[rows],np.concatenate([graphs[i].inventories for i in ids]),cache['capacity'][rows],cache['delta'][rows],cache['trueHp'][rows]/cache['trueMax'][rows],cache['boss'][rows]);offset=0
            for i in ids:
                graph=graphs[i];p=lp[offset:offset+len(graph.inventories)];posterior,total=t.trace_posterior(p,graph);offset+=len(graph.inventories);error=max(error,abs(total-float(t.target_log_probability(p,graph,False).exp())))
                traces[i]=posterior.argmax()
                if (posterior>0).sum()>1:posteriors[int(i)]=posterior
    if error>1e-6:raise ValueError('exact posterior mismatch')
    np.savez_compressed(output/'cache.npz',z=z,potionZ=zp,traces=traces,**labels)
    np.savez_compressed(output/'ambiguous_traces.npz',ids=np.asarray(list(posteriors),np.int64),posterior=np.asarray(list(posteriors.values())))
    records=[]
    for line in (rawfolder/'affected_rows.jsonl').open():
        record=json.loads(line);i=record['index'];pre,post,pi=record['pre'],record['post'],record['pi'];escaped=bool(labels['escaped'][i]);writhing=bool(labels['writhing'][i])
        adjusted=native.writhing_posts(pre)[native.writhing_target(pre,post)] if writhing else pre
        deltas=tuple(x['delta'] for x in native.ritual_changes(adjusted,post));record['daggerTarget']=deltas;record['writhingTarget']=native.writhing_target(pre,post) if writhing else 0
        trace_options=np.flatnonzero(posteriors[i]>0) if i in posteriors else [traces[i]];trace_data=[]
        daggers=[card for card in pre['deck'] if card['id']==c.base._CARD_IDS['RITUAL_DAGGER']]
        for trace in trace_options:
            mask=int(trace)&31;flags=int(trace)>>5;consumed=tuple(p for bit,p in enumerate(t.EFFECT_IDS) if flags&(1<<bit));_,mechanical=gold.mechanics(pi,pre,mask,consumed)
            mechanical[gold.MECHANICAL_FIELDS.index('eligibleKillCap')]-=int(escaped)
            dagger_posts=native.ritual_posts(pre,pi,mask,consumed,escaped)
            try:posts=budget.joint_gold_posts(pre,pi,mask,deltas,consumed,escaped)
            except ValueError:posts=()
            if not posts or deltas not in dagger_posts:continue
            pair=(post['gold'],post['stolenGold'])
            if pair not in posts:continue
            om=next((r['data'] for r in pre['relics'] if r['id']==c.base._RELIC_IDS['OMAMORI']),0);darkstone=any(r['id']==c.base._RELIC_IDS['DARKSTONE_PERIAPT'] for r in pre['relics'])
            features=[om/2,int(darkstone),len(daggers),sum(int(d['upgraded']) for d in daggers),int(writhing),int(escaped),float(mechanical[9]),int(bool(flags&1))]
            trace_data.append(dict(trace=int(trace),weight=float(posteriors[i][trace]) if i in posteriors else 1.,mechanical=mechanical.tolist(),features=features,posts=posts,goldTarget=posts.index(pair),daggerPosts=dagger_posts,daggerTarget=dagger_posts.index(deltas),daggerCandidates=[[[card['misc']/100,int(card['upgraded']),delta/20] for card,delta in zip(daggers,amounts)] for amounts in dagger_posts]))
        if not trace_data:raise ValueError(f'joint native target absent at {i}')
        record['traces']=trace_data;records.append(record)
    with (output/'affected_rows.jsonl').open('x') as stream:
        for record in records:stream.write(json.dumps(record)+'\n')
    receipt=dict(sourceSha=sha,recipe=RECIPE,hashes=meta['hashes'],upstreamBindings=bindings,rawLabels=rawmeta,rows=len(z),ambiguousRows=len(posteriors),maxIndependentPosteriorError=error,cacheSha256=c.base.sha256(output/'cache.npz'),ambiguousSha256=c.base.sha256(output/'ambiguous_traces.npz'),recordsSha256=c.base.sha256(output/'affected_rows.jsonl'),supportChanged=False)
    c.base.json_dump(output/'preparation.json',receipt);print(json.dumps(receipt),flush=True)


def load(parent,folder):
    meta=json.loads((folder/'preparation.json').read_text())
    for name,key in [('cache.npz','cacheSha256'),('ambiguous_traces.npz','ambiguousSha256'),('affected_rows.jsonl','recordsSha256')]:
        if c.base.sha256(folder/name)!=meta[key]:raise ValueError('downstream cache differs')
    cache,graphs,upstream=trajectory.load(parent/'potion-trajectory-v2')
    if meta['hashes']!=upstream['hashes']:raise ValueError('data binding differs')
    with np.load(folder/'cache.npz') as raw:cache.update({k:raw[k] for k in raw.files if k!='ids'})
    with np.load(folder/'ambiguous_traces.npz') as raw:ambiguous={int(i):p for i,p in zip(raw['ids'],raw['posterior'])}
    records={r['index']:r for r in map(json.loads,(folder/'affected_rows.jsonl').open())}
    return cache,ambiguous,records,meta


def models(parent):
    m=c.FrozenModels('cpu');gold_net=gold.new_decoder(torch)
    path=parent/'shared-gold-v1'/'gold.pt';receipt=json.loads((path.parent/'fit.json').read_text())
    if c.base.sha256(path)!=receipt['artifactSha256']:raise ValueError('gold warm binding differs')
    gold_net.load_state_dict(torch.load(path,map_location='cpu',weights_only=False)['stateDict'])
    nets=dict(relic=relic_net(m.relic_net),gold=gold_net)
    for name in ('writhing','ritual'):
        path=parent/(name+'-v1')/'event.pt';receipt=json.loads((path.parent/'fit.json').read_text())
        if c.base.sha256(path)!=receipt['artifactSha256']:raise ValueError('event warm binding differs')
        nets[name]=event_net(torch.load(path,map_location='cpu',weights_only=False)['stateDict'])
    return torch.nn.ModuleDict(nets)


def losses(nets,cache,ambiguous,records,ids,ending=None,maximum=None,allow_zero=False,return_details=False):
    ending=cache['trueHp'][ids] if ending is None else ending;maximum=cache['trueMax'][ids] if maximum is None else maximum
    owners=[];traces=[];weights=[];data=[]
    for owner,i in enumerate(ids):
        if i in records:
            options=records[i]['traces']
        elif i in ambiguous:options=[dict(trace=int(trace),weight=float(ambiguous[i][trace])) for trace in np.flatnonzero(ambiguous[i]>0)]
        else:options=[dict(trace=int(cache['traces'][i]),weight=1.)]
        for option in options:owners.append(owner);traces.append(option['trace']);weights.append(option['weight']);data.append(option)
    owners=np.asarray(owners,np.int64);rows=ids[owners];traces=np.asarray(traces,np.int64);masks=traces&31
    device=next(nets.parameters()).device
    def tensor(value):return torch.as_tensor(value,device=device)
    signed=ending[owners]-cache['preHp'][rows]-c.CLASSES[0];fraction=ending[owners]/maximum[owners]
    outputs=nets['relic'](tensor(cache['z'][rows]),tensor(signed),tensor(fraction.astype(np.float32)),tensor(masks),tensor(cache['escaped'][rows].astype(np.float32)))
    logmass=tensor(np.zeros(len(rows),np.float32))
    component_logs={};component_probabilities={}
    for j,name in enumerate(c.TRAINED_GROUPS):
        probabilities=torch.softmax(outputs[name],-1)
        lp=torch.log(probabilities);compatible=tensor(cache['compatible_'+name][rows]);observed=tensor(cache['observed'][rows,j])
        value=torch.logsumexp(lp.masked_fill(~compatible,-torch.inf),-1)*observed
        logmass=logmass+value;component_logs[name]=value;component_probabilities[name]=probabilities
    hp=np.stack(((ending[owners]-cache['preHp'][rows])/160,fraction,(maximum[owners]-cache['preMax'][rows])/10),-1).astype(np.float32)
    bits=c.potion.BITS[masks].astype(np.float32)
    event_log={}
    for mechanism,active in [('writhing',cache['writhing'][rows]),('ritual',cache['dagger'][rows])]:
        selected=np.flatnonzero(active);value=logmass.new_zeros(len(rows))
        if len(selected):
            features=np.asarray([data[i]['features'] for i in selected],np.float32)
            if mechanism=='writhing':
                candidates=np.broadcast_to(np.asarray([[[0,0,0]],[[1,0,1]]],np.float32),(len(selected),2,1,3)).copy()
                candidates[:,1,0,1]=features[:,0]>0;candidates[:,1,0,2]=features[:,0]==0
                legal=np.ones((len(selected),2),bool);tied=(features[:,1]>0)&(features[:,0]==0)&(maximum[owners[selected]]-cache['preMax'][rows[selected]]<6);legal[tied,1]=False
                target=np.asarray([records[rows[i]]['writhingTarget'] for i in selected],np.int64)
            else:
                width=max(len(data[i]['daggerCandidates']) for i in selected);cards=max(len(data[i]['daggerCandidates'][0]) for i in selected);candidates=np.zeros((len(selected),width,cards,3),np.float32);legal=np.zeros((len(selected),width),bool);target=[]
                for j,i in enumerate(selected):
                    raw=np.asarray(data[i]['daggerCandidates'],np.float32);candidates[j,:len(raw)]=raw;legal[j,:len(raw)]=True;target.append(data[i]['daggerTarget'])
            lp=nets[mechanism](tensor(cache['z'][rows[selected]]),tensor(hp[selected]),tensor(bits[selected]),tensor(features),tensor(candidates),tensor(legal))
            value=value.index_copy(0,tensor(selected),lp[torch.arange(len(selected),device=device),tensor(np.asarray(target))])
        logmass=logmass+value;event_log[mechanism]=value
    selected=np.asarray([i for i,d in enumerate(data) if 'posts' in d],np.int64);gold_log=logmass.new_zeros(len(rows))
    if len(selected):
        width=max(len(data[i]['posts']) for i in selected);candidate=np.zeros((len(selected),width,6),np.float32);legal=np.zeros((len(selected),width),bool)
        for j,i in enumerate(selected):
            posts=data[i]['posts'];candidate[j,:len(posts)]=gold.candidate_features(posts,records[rows[i]]['pre']['gold']);legal[j,:len(posts)]=True
        mechanical=np.asarray([data[i]['mechanical'] for i in selected],np.float32);target=np.asarray([data[i]['goldTarget'] for i in selected],np.int64)
        lp=nets['gold'](tensor(cache['z'][rows[selected]]),tensor(mechanical),tensor(hp[selected]),tensor(bits[selected]),tensor(candidate),tensor(legal))
        gold_log=gold_log.index_copy(0,tensor(selected),lp[torch.arange(len(selected),device=device),tensor(target)])
    logmass=logmass+gold_log
    mass=logmass.new_zeros(len(ids)).index_add(0,tensor(owners),tensor(np.asarray(weights,np.float32))*logmass.exp())
    count=cache['observed'][ids].sum(-1)+cache['writhing'][ids]+cache['dagger'][ids]+np.asarray([i in records for i in ids])
    if not torch.isfinite(mass).all() or (mass<0).any() or ((mass<=0).any() and not allow_zero):raise ValueError('zero/nonfinite exact downstream joint target mass')
    if return_details:
        return dict(owners=owners,weights=np.asarray(weights,np.float32),component_logs=component_logs,
                    component_probabilities=component_probabilities,event_logs=event_log,gold_log=gold_log,
                    joint_log=logmass,counts=count)
    return -mass.log()/tensor(count.clip(min=1).astype(np.float32))


def fit(parent,folder,sha):
    sparse.frozen(sha)
    if (folder/'downstream.pt').exists():raise ValueError('refusing overwrite')
    cache,ambiguous,records,meta=load(parent,folder);torch.set_num_threads(4);nets=models(parent).cuda().requires_grad_(True);parameters=list(nets.parameters());opt=torch.optim.AdamW(parameters,lr=RECIPE['lr'],weight_decay=RECIPE['weightDecay'])
    eligible=cache['win']&(cache['observed'].any(-1)|cache['writhing']|cache['dagger']|np.isin(np.arange(len(cache['ids'])),list(records)))
    train=np.flatnonzero(eligible&(cache['split']==0));val=np.flatnonzero(eligible&(cache['split']==1));test=np.flatnonzero(eligible&(cache['split']==2));rng=np.random.default_rng(RECIPE['seed']);history=[];best=float('inf')
    def score(ids):
        nets.eval()
        with torch.inference_mode():return float(torch.cat([losses(nets,cache,ambiguous,records,ids[start:start+512]) for start in range(0,len(ids),512)]).mean())
    original=score(val)
    for epoch in range(1,RECIPE['epochs']+1):
        nets.train();order=rng.permutation(train)
        for start in range(0,len(order),512):
            sub=order[start:start+512];opt.zero_grad();loss=losses(nets,cache,ambiguous,records,sub).mean();loss.backward();torch.nn.utils.clip_grad_norm_(parameters,RECIPE['clip']);opt.step()
        value=score(val);history.append(dict(epoch=epoch,validationNll=value));print(json.dumps(history[-1]),flush=True)
        if value<best:best=value;selected=epoch;state=copy.deepcopy(nets.state_dict())
    nets.load_state_dict(state);result=dict(sourceSha=sha,preparation=meta,recipe=RECIPE,trainRows=len(train),validationRows=len(val),testRows=len(test),selectedEpoch=selected,originalValidationNll=original,history=history,testNll=score(test),supportChanged=False)
    torch.save(dict(stateDict=state,metadata=result),folder/'downstream.pt');result['artifactSha256']=c.base.sha256(folder/'downstream.pt');c.base.json_dump(folder/'fit.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','fit']);p.add_argument('--parent',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--source-sha',required=True);a=p.parse_args();globals()[a.command](a.parent,a.output_dir,a.source_sha)
