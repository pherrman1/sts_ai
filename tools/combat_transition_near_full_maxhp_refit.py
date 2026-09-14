#!/usr/bin/env python3
"""Affected maxHP repair with audited native Writhing/Darkstone coarse target."""
import argparse,copy,json
from pathlib import Path
import numpy as np
import torch
from tools import combat_transition_composed as c,combat_transition_composed_evaluate as e
from tools import combat_transition_near_full_downstream as d
from tools import combat_transition_sparse_evaluate as sparse

RECIPE=dict(seed=20260912,epochs=12,batch=512,headLr=.001,encoderLr=.0001,weightDecay=.0001,clip=1.,selection='earliest strict minimum original VALIDATION maxHP NLL plus audited native partition NLL',population='entire final-union original TRAIN survivors',auxiliary='one coarse native target on Writhing/Darkstone without charged Omamori or available Fruit Juice: implant iff maxHP delta >=6; coefficient one, not tuned',scope='existing maxHP architecture; all other learned components fixed',evidence='bounded development repair motivated by reused TEST, not untouched confirmation')


def fit(parent,output,sha,train_encoder=False):
    sparse.frozen(sha)
    if output.exists():raise ValueError('refusing overwrite')
    cache,ambiguous,records,meta=d.load(parent,parent/'full-union-downstream-v1');m,bindings=d.load_upstream(parent);arrays,spec=c.base._load_prepared(e.PREPARED);c.base._prepare_target_indices(arrays,spec);torch.set_num_threads(4);torch.manual_seed(RECIPE['seed'])
    selected=np.zeros(len(cache['ids']),bool);implant=np.zeros(len(selected),bool)
    for i,r in records.items():
        pre,pi,post=r['pre'],r['pi'],r['post']
        if pi['globals']['encounter']!=c.base.WRITHING_MASS_ID or not any(x['id']==c.base._RELIC_IDS['DARKSTONE_PERIAPT'] for x in pre['relics']) or c.base._POTION_IDS['FRUIT_JUICE'] in pre['potions'] or any(x['id']==c.base._RELIC_IDS['OMAMORI'] and x['data']>0 for x in pre['relics']):continue
        event=bool(r['writhingTarget'])
        if event!=(post['maxHp']-pre['maxHp']>=6):raise ValueError('native coarse partition target contradiction')
        selected[i]=True;implant[i]=event
    active=cache['win'];train=np.flatnonzero(active&(cache['split']==0));val=np.flatnonzero(active&(cache['split']==1));test=np.flatnonzero(active&(cache['split']==2));encoder=m.max_net.encoder;head=m.max_net.max_hp_delta;encoder.requires_grad_(train_encoder);head.requires_grad_(True)
    z=np.zeros((len(selected),64),np.float32)
    if not train_encoder:
        with torch.inference_mode():
            ids=np.flatnonzero(active)
            for start in range(0,len(ids),512):
                sub=ids[start:start+512];inputs=c.base._torch_inputs(arrays,cache['ids'][sub],'cuda',torch,trim_padding=True);z[sub]=m.fp32_encoding(encoder,inputs).cpu().numpy()
    parameters=list(head.parameters())+(list(encoder.parameters()) if train_encoder else []);groups=[dict(params=head.parameters(),lr=RECIPE['headLr'])]
    if train_encoder:groups.append(dict(params=encoder.parameters(),lr=RECIPE['encoderLr']))
    opt=torch.optim.AdamW(groups,weight_decay=RECIPE['weightDecay']);high=torch.as_tensor(m.delta_values>=6,device='cuda')
    def losses(ids,auxiliary=True):
        if train_encoder:
            inputs=c.base._torch_inputs(arrays,cache['ids'][ids],'cuda',torch,trim_padding=True);encoding=m.fp32_encoding(encoder,inputs)
        else:encoding=torch.as_tensor(z[ids],device='cuda')
        lp=torch.log_softmax(head(encoding),-1);target=torch.as_tensor(cache['delta'][ids],device='cuda');loss=-lp[torch.arange(len(ids),device='cuda'),target]
        if auxiliary:
            truth=torch.as_tensor(implant[ids],device='cuda');partition=torch.logsumexp(lp.masked_fill(high[None]!=truth[:,None],-torch.inf),-1);loss=loss-torch.as_tensor(selected[ids],device='cuda')*partition
        return loss
    def mode(training):head.train(training);encoder.train(training and train_encoder)
    def score(ids,auxiliary=True):
        mode(False)
        with torch.inference_mode():return float(torch.cat([losses(ids[start:start+512],auxiliary) for start in range(0,len(ids),512)]).mean())
    original=score(val);rng=np.random.default_rng(RECIPE['seed']);best=float('inf');history=[]
    for epoch in range(1,RECIPE['epochs']+1):
        mode(True);order=rng.permutation(train)
        for start in range(0,len(order),512):
            sub=order[start:start+512];opt.zero_grad();loss=losses(sub).mean();loss.backward();torch.nn.utils.clip_grad_norm_(parameters,RECIPE['clip']);opt.step()
        nll=score(val);history.append(dict(epoch=epoch,validationJointNativeNll=nll));print(json.dumps(history[-1]),flush=True)
        if nll<best:best=nll;epoch_selected=epoch;encoder_state=copy.deepcopy(encoder.state_dict());head_state=copy.deepcopy(head.state_dict())
    encoder.load_state_dict(encoder_state);head.load_state_dict(head_state)
    result=dict(sourceSha=sha,component='maxHP',recipe=RECIPE,trainEncoder=train_encoder,hashes=meta['hashes'],warmBindings=bindings,trainRows=len(train),validationRows=len(val),testRows=len(test),nativePartitionRows={name:int((selected&(cache['split']==i)).sum()) for i,name in enumerate(('train','validation','test'))},nativePartitionContradictions=0,history=history,selectedEpoch=epoch_selected,originalValidationJointNll=original,validationJointNll=best,validationNll=score(val,False),testNll=score(test,False),supportChanged=False)
    output.mkdir();torch.save(dict(encoderStateDict=encoder_state,headStateDicts=[head_state],metadata=result),output/'component.pt');result['artifactSha256']=c.base.sha256(output/'component.pt');c.base.json_dump(output/'fit.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--source-sha',required=True);p.add_argument('--train-encoder',action='store_true');a=p.parse_args();fit(a.parent,a.output,a.source_sha,a.train_encoder)
