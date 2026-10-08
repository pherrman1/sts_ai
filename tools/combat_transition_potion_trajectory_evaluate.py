#!/usr/bin/env python3
"""Source-bound shared potion trajectory fit on the provisional final union."""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import numpy as np
import torch
from tools import combat_transition_composed as c,combat_transition_composed_evaluate as e
from tools import combat_transition_sparse_evaluate as sparse
from tools import combat_transition_near_full_support as support
from tools import combat_transition_potion_trajectory as t
from tools import ctm_pins as _pins

RECIPE=dict(seed=20260912,epochs=12,batch=512,lr=.001,weightDecay=.0001,gradientClip=1.,
            selection='earliest strict minimum original VALIDATION conditional trajectory NLL',
            training='shared inventory-conditioned joint-mask decoder only; original TRAIN survivors',
            encoder='frozen historical potion encoder',rng='planner-owned fresh sts::Random(seed); reused through recursive generation; advanced state retained',
            target='exact native generation-body prior times all compatible consumption-order probabilities',
            partition='original source-grouped engineering TEST; reused development evidence, not pristine holdout')
RECIPE['actions']='64 native categories: five clearing bits plus trigger USE/DISCARD bit; ordinary masks retain one category'
ENCOUNTER_NAMES={v:k for k,v in c.base._ENCOUNTER_IDS.items()}


def graph_json(graph):
    return dict(inventories=graph.inventories.tolist(),edges=graph.edges,target_edges=graph.target_edges,generation_log_prior=graph.generation_log_prior,rounds=graph.rounds)


def graph_load(raw):
    return t.Graph(np.asarray(raw['inventories'],np.int64),tuple(map(tuple,raw['edges'])),tuple(map(tuple,raw['target_edges'])),raw['generation_log_prior'],raw['rounds'])


def prepare(folder,sha):
    sparse.frozen(sha)
    if folder.exists():raise ValueError('refusing overwrite')
    hashes=e.verify_data();arrays,spec=c.base._load_prepared(e.PREPARED);c.base._prepare_target_indices(arrays,spec)
    m=c.FrozenModels('cpu');ids=[];graphs={};records=[];tables={};reasons=Counter();counts=Counter();boss=[];old=[]
    with support.candidate_contract() as (original,certified):
        for index,row in enumerate(c.base.iter_rows(e.CORPUS)):
            if (int(arrays['sourceSeed'][index]),int(arrays['fightIdx'][index]))!=(row['sourceSeed'],row['fightIdx']):raise ValueError('row identity differs')
            pre,post,pi=row['transition']['pre'],row['transition']['post'],row['predictorInput']
            failures=c.full_support_reasons(pre,pi,m);reasons.update(failures)
            labels=['all',('train','validation','test')[int(arrays['split_id'][index])]]
            for label in labels:
                table=tables.setdefault(label,Counter());table['rows']+=1;table['supported']+=not bool(failures)
            if failures:continue
            local=len(ids);ids.append(index);old.append(not original(pi,pre) and certified(pi))
            encounter=ENCOUNTER_NAMES[pi['globals']['encounter']]
            is_boss=encounter in t.BOSSES;boss.append(is_boss)
            win=row['transition']['combatOutcome']==c.base.WIN
            if win and any(p in (t.BREW,t.SMOKE) for p in pre['potions']):
                state=dict(pre['combatRng'][4]);generated=[];target=post['combatRng'][4]
                while state['counter']<target['counter']:generated.append(t.brew.draw_native(state))
                if state!=target:raise ValueError('native teacher generation RNG mismatch')
                try:graph=t.target_graph(pre,post,generated,is_boss)
                except ValueError as error:raise ValueError(f'index={index}, source={row["sourceSeed"]}, fight={row["fightIdx"]}, encounter={encounter}, pre={pre["potions"]}, post={post["potions"]}, generated={generated}: {error}') from error
                graphs[str(local)]=graph_json(graph)
                records.append(dict(index=index,local=local,source=row['sourceSeed'],fight=row['fightIdx'],pre=pre,post=post,pi=pi,generated=generated))
                counts['specialSurvivors']+=1;counts['brewGenerationRounds']+=graph.rounds;counts['escapeRows']+=post['smokeBombUsed']
            if index%100000==0:print('final candidate census',index,flush=True)
    ids=np.asarray(ids,np.int64)
    # The #179 production support count; a retrain on a new corpus pins null (recorded only).
    previous=_pins.value('combat_transition_potion_trajectory_evaluate.PREVIOUS_SUPPORT_ROWS',413799)
    if previous is not None and sum(old)!=previous:raise ValueError('previous #179 support count changed')
    prehp=arrays['globals_continuous'][ids,c.base.CONTINUOUS_GLOBAL_FIELDS.index('curHp')].astype(np.int64)
    premax=arrays['preMaxHp'][ids].astype(np.int64);postmax=arrays['y_post_max_hp'][ids].astype(np.int64);posthp=arrays['y_post_hp'][ids].astype(np.int64)
    slots=arrays['potions'][ids,:,1].astype(np.int64);capacity=arrays['potionCapacity'][ids].astype(np.int64)
    mask=((slots!=arrays['y_potions'][ids])*(1<<np.arange(5))).sum(-1).astype(np.int64)
    cache=dict(ids=ids,source=arrays['sourceSeed'][ids],split=arrays['split_id'][ids],win=arrays['y_win'][ids]==1,
               preHp=prehp,preMax=premax,trueHp=posthp,trueMax=postmax,delta=arrays['delta_index'][ids].astype(np.int64),
               potions=slots,capacity=capacity,mask=mask,boss=np.asarray(boss),old=np.asarray(old),z=np.zeros((len(ids),64),np.float32))
    alive=cache['win'];normal=np.asarray([str(i) not in graphs for i in range(len(ids))])&alive
    if np.any(cache['delta'][alive]<0) or np.any((posthp[alive]-prehp[alive]<c.CLASSES[0])|(posthp[alive]-prehp[alive]>c.CLASSES[-1])):raise ValueError('target outside existing HP/maxHP class domain')
    if np.any((arrays['y_potions'][ids[normal]]!=slots[normal])&(arrays['y_potions'][ids[normal]]!=1)):raise ValueError('unexplained normal potion creation')
    torch.set_num_threads(4);m.to('cuda')
    with torch.inference_mode():
        for start in range(0,len(ids),512):
            sub=np.arange(start,min(start+512,len(ids)));inputs=c.base._torch_inputs(arrays,ids[sub],'cuda',torch,trim_padding=True)
            cache['z'][sub]=m.fp32_encoding(m.potion_encoder.encoder,inputs).cpu().numpy()
            if start%51200==0:print('trajectory frozen encoding',start,len(ids),flush=True)
    folder.mkdir(parents=True);np.savez_compressed(folder/'cache.npz',**cache)
    c.base.json_dump(folder/'graphs.json',graphs)
    with (folder/'special_rows.jsonl').open('w') as out:
        for record in records:out.write(json.dumps(record)+'\n')
    meta=dict(sourceSha=sha,hashes=hashes,recipe=RECIPE,counts=counts,census=tables,residualReasons=reasons,
              countsBySplit={name:dict(rows=int((cache['split']==i).sum()),survivors=int((alive&(cache['split']==i)).sum()),previousQualified=int((cache['old']&(cache['split']==i)).sum())) for i,name in enumerate(('train','validation','test'))},
              cacheSha256=c.base.sha256(folder/'cache.npz'),graphsSha256=c.base.sha256(folder/'graphs.json'),specialRowsSha256=c.base.sha256(folder/'special_rows.jsonl'),supportChanged=False)
    c.base.json_dump(folder/'preparation.json',meta);print(json.dumps(meta),flush=True)


def load(folder):
    meta=json.loads((folder/'preparation.json').read_text())
    if meta['hashes']!=e.verify_data():raise ValueError('frozen source data differs')
    for file,key in [('cache.npz','cacheSha256'),('graphs.json','graphsSha256'),('special_rows.jsonl','specialRowsSha256')]:
        if c.base.sha256(folder/file)!=meta[key]:raise ValueError('cache differs')
    with np.load(folder/'cache.npz') as raw:cache={k:raw[k] for k in raw.files}
    graphs={int(i):graph_load(v) for i,v in json.loads((folder/'graphs.json').read_text()).items()}
    return cache,graphs,meta


def row_graphs(cache,graphs,ids):
    return [graphs[i] if i in graphs else t.Graph(cache['potions'][i:i+1],(),((0,int(cache['mask'][i])),),0.,0) for i in ids]


def losses(net,cache,graphs,ids,delta=None,hp=None,z=None,include_generation=False):
    d=cache['delta'][ids] if delta is None else delta
    fraction=cache['trueHp'][ids]/cache['trueMax'][ids] if hp is None else hp
    return -t.batch_target_log_probabilities(net,row_graphs(cache,graphs,ids),cache['z'][ids] if z is None else z,
                                            cache['capacity'][ids],d,fraction,cache['boss'][ids],include_generation)


def fit(folder,sha):
    sparse.frozen(sha)
    if (folder/'trajectory.pt').exists():raise ValueError('refusing overwrite')
    cache,graphs,meta=load(folder);torch.set_num_threads(4);m=c.FrozenModels('cuda');net=t.new_decoder(len(m.delta_values),m.potion_net).requires_grad_(True)
    torch.manual_seed(RECIPE['seed']);opt=torch.optim.AdamW(net.parameters(),lr=RECIPE['lr'],weight_decay=RECIPE['weightDecay']);rng=np.random.default_rng(RECIPE['seed'])
    train=np.flatnonzero(cache['win']&(cache['split']==0));val=np.flatnonzero(cache['win']&(cache['split']==1));test=np.flatnonzero(cache['win']&(cache['split']==2));best=float('inf');history=[]
    def score(ids):
        with torch.inference_mode():return float(torch.cat([losses(net,cache,graphs,ids[s:s+512]) for s in range(0,len(ids),512)]).mean())
    original=score(val)
    for epoch in range(1,RECIPE['epochs']+1):
        net.train();order=rng.permutation(train)
        for start in range(0,len(order),512):
            sub=order[start:start+512];opt.zero_grad();loss=losses(net,cache,graphs,sub).mean();loss.backward();torch.nn.utils.clip_grad_norm_(net.parameters(),1);opt.step()
        net.eval();nll=score(val);history.append(dict(epoch=epoch,validationConditionalNll=nll));print(json.dumps(history[-1]),flush=True)
        if nll<best:best=nll;selected=epoch;state=copy.deepcopy(net.state_dict())
    net.load_state_dict(state);result=dict(sourceSha=sha,preparation=meta,recipe=RECIPE,history=history,selectedEpoch=selected,originalValidationNll=original,testConditionalNll=score(test),trainRows=len(train),validationRows=len(val),testRows=len(test),supportChanged=False)
    torch.save(dict(stateDict=state,metadata=meta,recipe=RECIPE),folder/'trajectory.pt');result['artifactSha256']=c.base.sha256(folder/'trajectory.pt');c.base.json_dump(folder/'fit.json',result);print(json.dumps(result),flush=True)


def diagnose(folder,sha):
    sparse.frozen(sha)
    if (folder/'diagnostics.json').exists():raise ValueError('refusing overwrite')
    cache,graphs,meta=load(folder);fitmeta=json.loads((folder/'fit.json').read_text())
    if c.base.sha256(folder/'trajectory.pt')!=fitmeta['artifactSha256']:raise ValueError('checkpoint differs')
    torch.set_num_threads(4);m=c.FrozenModels('cuda');net=t.new_decoder(len(m.delta_values),m.potion_net).eval().requires_grad_(False)
    net.load_state_dict(torch.load(folder/'trajectory.pt',map_location='cuda',weights_only=False)['stateDict'])
    repaired=folder.parent/'maxhp-encoder-v1'/'maxhp-head.pt'
    repairmeta=json.loads((repaired.parent/'fit.json').read_text())
    if c.base.sha256(repaired)!=repairmeta['artifactSha256']:raise ValueError('maxHP repair differs')
    payload=torch.load(repaired,map_location='cuda',weights_only=False)
    m.max_net.max_hp_delta.load_state_dict(payload['stateDict']);m.max_net.encoder.load_state_dict(payload['encoderStateDict'])
    arrays,spec=c.base._load_prepared(e.PREPARED);c.base._prepare_target_indices(arrays,spec)
    test=np.flatnonzero(cache['win']&(cache['split']==2));z=np.zeros((len(test),64),np.float32);pd=np.zeros((len(test),len(m.delta_values)),np.float64)
    teacher=np.empty(len(test));mass=np.empty((32,len(test)),np.float64)
    with torch.inference_mode():
        for start in range(0,len(test),512):
            sub=test[start:start+512];inputs=c.base._torch_inputs(arrays,cache['ids'][sub],'cuda',torch,trim_padding=True)
            z[start:start+len(sub)]=m.hp_encoding(inputs).cpu().numpy()
            pd[start:start+len(sub)]=e.probabilities(m.max_net.max_hp_delta(m.fp32_encoding(m.max_net.encoder,inputs)))
            teacher[start:start+len(sub)]=losses(net,cache,graphs,sub).cpu().numpy()
        rng=np.random.default_rng(20260920)
        for draw in range(32):
            for start in range(0,len(test),512):
                sub=test[start:start+512];d=e.draw_categories(pd[start:start+len(sub)],rng)
                maximum=cache['preMax'][sub]+m.delta_values[d]
                hp=e.hp_prob(m,z[start:start+len(sub)],d,cache['preHp'][sub],maximum)
                ending=cache['preHp'][sub]+c.CLASSES[e.draw_categories(hp,rng)]
                mass[draw,start:start+len(sub)]=(-losses(net,cache,graphs,sub,delta=d,hp=ending/maximum)).exp().cpu().numpy()
            print('full union potion exposure',draw+1,flush=True)
    mixture=e.nll(mass.mean(0));gap=mixture-teacher
    special=np.asarray([i in graphs for i in test]);recursive=np.asarray([i in graphs and graphs[i].rounds>1 for i in test]);brew=np.any(cache['potions'][test]==t.BREW,-1);smoke=np.any(cache['potions'][test]==t.SMOKE,-1)
    slices={}
    for name,selected in dict(entireFinalUnion=np.ones(len(test),bool),previous179=cache['old'][test],recovered=~cache['old'][test],special=special,brew=brew,smoke=smoke,recursiveBrew=recursive).items():
        if selected.any():slices[name]=dict(rows=int(selected.sum()),conditionalTeacherNll=float(teacher[selected].mean()),exposure=e.source_gap_bootstrap(cache['source'][test[selected]],gap[selected]),zeroExactMassRows=int((mass.mean(0)[selected]<=0).sum()),gate=bool(np.isfinite(gap[selected]).all() and gap[selected].mean()<=.1))
    np.savez_compressed(folder/'diagnostic_rows.npz',ids=cache['ids'][test],source=cache['source'][test],teacherNll=teacher,mixtureNll=mixture,exposureGap=gap)
    result=dict(sourceSha=sha,modelSha256=fitmeta['artifactSha256'],maxHpSha256=repairmeta['artifactSha256'],slices=slices,draws=32,upstream='repaired maxHP encoder/head and original HP encoder/head',classification='POTION_TRAJECTORY_DEVELOPMENT_PASS' if all(s['gate'] for s in slices.values()) else 'POTION_TRAJECTORY_DEVELOPMENT_FAIL',supportChanged=False,scope='potion component development exposure; not full-stack/native/runtime qualification',partition=RECIPE['partition'])
    c.base.json_dump(folder/'diagnostics.json',result);print(json.dumps(result),flush=True)


def posterior(folder,sha):
    sparse.frozen(sha)
    if (folder/'trace_posteriors.npz').exists():raise ValueError('refusing overwrite')
    cache,graphs,meta=load(folder);fitmeta=json.loads((folder/'fit.json').read_text())
    if c.base.sha256(folder/'trajectory.pt')!=fitmeta['artifactSha256']:raise ValueError('checkpoint differs')
    torch.set_num_threads(4);m=c.FrozenModels('cuda');net=t.new_decoder(len(m.delta_values),m.potion_net).eval().requires_grad_(False)
    net.load_state_dict(torch.load(folder/'trajectory.pt',map_location='cuda',weights_only=False)['stateDict'])
    ids=np.asarray(sorted(graphs),np.int64);posteriors=np.zeros((len(ids),256),np.float64);max_error=0.
    with torch.inference_mode():
        for start in range(0,len(ids),128):
            sub=ids[start:start+128];owners=np.concatenate([np.full(len(graphs[i].inventories),row) for row,i in enumerate(sub)])
            inventories=np.concatenate([graphs[i].inventories for i in sub]);rows=sub[owners]
            lp=t.log_probabilities(net,cache['z'][rows],inventories,cache['capacity'][rows],cache['delta'][rows],cache['trueHp'][rows]/cache['trueMax'][rows],cache['boss'][rows])
            offset=0
            for row,i in enumerate(sub):
                graph=graphs[i];p=lp[offset:offset+len(graph.inventories)];posteriors[start+row],total=t.trace_posterior(p,graph)
                scalar=float(t.target_log_probability(p,graph,False).exp());max_error=max(max_error,abs(total-scalar));offset+=len(graph.inventories)
            if start%1024==0:print('exact potion effect posteriors',start,len(ids),flush=True)
    if max_error>1e-6:raise ValueError('posterior marginal differs from independent target DAG')
    np.savez_compressed(folder/'trace_posteriors.npz',ids=ids,posterior=posteriors)
    result=dict(sourceSha=sha,modelSha256=fitmeta['artifactSha256'],specialSurvivors=len(ids),maxIndependentMarginalError=max_error,multipleTraceRows=int(((posteriors>0).sum(-1)>1).sum()),artifactSha256=c.base.sha256(folder/'trace_posteriors.npz'),supportChanged=False)
    c.base.json_dump(folder/'trace_posteriors.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','fit','diagnose','posterior']);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--source-sha',required=True);a=p.parse_args();globals()[a.command](a.output_dir,a.source_sha)
