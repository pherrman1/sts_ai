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
    if sum(old)!=413799:raise ValueError('previous #179 support count changed')
    prehp=arrays['globals_continuous'][ids,c.base.CONTINUOUS_GLOBAL_FIELDS.index('curHp')].astype(np.int64)
    premax=arrays['preMaxHp'][ids].astype(np.int64);postmax=arrays['y_post_max_hp'][ids].astype(np.int64);posthp=arrays['y_post_hp'][ids].astype(np.int64)
    slots=arrays['potions'][ids,:,1].astype(np.int64);capacity=arrays['potionCapacity'][ids].astype(np.int64)
    mask=((slots!=arrays['y_potions'][ids])*(1<<np.arange(5))).sum(-1).astype(np.int64)
    cache=dict(ids=ids,source=arrays['sourceSeed'][ids],split=arrays['split_id'][ids],win=arrays['y_win'][ids]==1,
               preHp=prehp,preMax=premax,trueHp=posthp,trueMax=postmax,delta=arrays['delta_index'][ids].astype(np.int64),
               potions=slots,capacity=capacity,mask=mask,boss=np.asarray(boss),old=np.asarray(old),z=np.zeros((len(ids),64),np.float32))
    alive=cache['win'];normal=np.asarray([str(i) not in graphs for i in range(len(ids))])&alive
    if np.any(cache['delta'][alive]<0) or np.any((posthp[alive]-prehp[alive]<-160)|(posthp[alive]-prehp[alive]>143)):raise ValueError('target outside existing HP/maxHP class domain')
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


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','fit']);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--source-sha',required=True);a=p.parse_args();(prepare if a.command=='prepare' else fit)(a.output_dir,a.source_sha)
