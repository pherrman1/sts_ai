#!/usr/bin/env python3
"""Fixed-recipe existing upstream stack refit on the entire candidate union."""
import argparse
import copy
import json
from pathlib import Path
import numpy as np
import torch
from tools import combat_transition_composed as c,combat_transition_composed_evaluate as e
from tools import combat_transition_potion_trajectory as t,combat_transition_potion_trajectory_evaluate as trajectory
from tools import combat_transition_sparse_evaluate as sparse

RECIPE=dict(seed=20260912,epochs=12,batch=512,encoderLr=.0001,headLr=.001,weightDecay=.0001,clip=1.,
            selection='earliest strict minimum original VALIDATION NLL',population='entire provisional final union; original source-grouped TRAIN',
            scope='existing survival, maxHP, HP and potion encoder/head architectures; shared 64-action native trajectory extension',
            evidence='engineering development; original TEST reused, not untouched confirmation')


def run(folder,output,component,sha,smoke_check=False):
    sparse.frozen(sha)
    if output.exists():raise ValueError('refusing overwrite')
    cache,graphs,meta=trajectory.load(folder);arrays,spec=c.base._load_prepared(e.PREPARED);c.base._prepare_target_indices(arrays,spec)
    torch.set_num_threads(4);torch.manual_seed(RECIPE['seed']);m=c.FrozenModels('cuda');bindings={}
    if component=='maxHP':
        path=folder.parent/'maxhp-encoder-v1'/'maxhp-head.pt';receipt=json.loads((path.parent/'fit.json').read_text())
        if c.base.sha256(path)!=receipt['artifactSha256']:raise ValueError('maxHP warm start differs')
        payload=torch.load(path,map_location='cuda',weights_only=False);m.max_net.encoder.load_state_dict(payload['encoderStateDict']);m.max_net.max_hp_delta.load_state_dict(payload['stateDict']);bindings['maxHP']=receipt['artifactSha256']
    if component=='potion':
        receipt=json.loads((folder/'fit.json').read_text())
        if c.base.sha256(folder/'trajectory.pt')!=receipt['artifactSha256']:raise ValueError('trajectory warm start differs')
        m.potion_net=t.new_decoder(len(m.delta_values),m.potion_net);m.potion_net.load_state_dict(torch.load(folder/'trajectory.pt',map_location='cuda',weights_only=False)['stateDict']);bindings['potion']=receipt['artifactSha256']
    encoder={'survival':m.survival_net.encoder,'maxHP':m.max_net.encoder,'HP':m.hp_net.encoder,'potion':m.potion_encoder.encoder}[component]
    heads={'survival':[m.survival_net.survival],'maxHP':[m.max_net.max_hp_delta],'HP':[m.hp_net.delta_embedding,m.hp_net.hp],'potion':[m.potion_net]}[component]
    encoder.requires_grad_(True)
    head_parameters=[]
    for head in heads:head.requires_grad_(True);head_parameters.extend(head.parameters())
    parameters=list(encoder.parameters())+head_parameters
    opt=torch.optim.AdamW([dict(params=encoder.parameters(),lr=RECIPE['encoderLr']),dict(params=head_parameters,lr=RECIPE['headLr'])],weight_decay=RECIPE['weightDecay'])
    eligible=np.ones(len(cache['ids']),bool) if component=='survival' else cache['win']
    train=np.flatnonzero(eligible&(cache['split']==0));val=np.flatnonzero(eligible&(cache['split']==1));test=np.flatnonzero(eligible&(cache['split']==2))
    def losses(ids):
        inputs=c.base._torch_inputs(arrays,cache['ids'][ids],'cuda',torch,trim_padding=True)
        if component=='HP':
            z=m.hp_encoding(inputs);d=torch.as_tensor(cache['delta'][ids],device='cuda')
            with torch.autocast('cuda',dtype=torch.float16):logits=m.hp_net.hp(torch.cat((z,m.hp_net.delta_embedding(d)),-1)).float()
            legal=c.hp.legal_support(c.CLASSES,cache['preHp'][ids],cache['trueMax'][ids])
            target=cache['trueHp'][ids]-cache['preHp'][ids]-c.CLASSES[0]
            return torch.nn.functional.cross_entropy(logits.masked_fill(~torch.as_tensor(legal,device='cuda'),-torch.inf),torch.as_tensor(target,device='cuda'),reduction='none')
        z=m.fp32_encoding(encoder,inputs)
        if component=='survival':return torch.nn.functional.binary_cross_entropy_with_logits(m.survival_net.survival(z).flatten(),torch.as_tensor(cache['win'][ids],device='cuda',dtype=torch.float32),reduction='none')
        if component=='maxHP':return torch.nn.functional.cross_entropy(m.max_net.max_hp_delta(z),torch.as_tensor(cache['delta'][ids],device='cuda'),reduction='none')
        return trajectory.losses(m.potion_net,cache,graphs,ids,z=z)
    def mode(training):
        encoder.train(training)
        for head in heads:head.train(training)
    def score(ids):
        mode(False)
        with torch.inference_mode():return float(torch.cat([losses(ids[start:start+512]) for start in range(0,len(ids),512)]).mean())
    if smoke_check:
        mode(True);sample=train[:32];loss=losses(sample).mean();loss.backward()
        grads=[p.grad for p in parameters if p.grad is not None]
        if not torch.isfinite(loss) or not grads or not all(torch.isfinite(g).all() for g in grads):raise ValueError('nonfinite/missing refit gradient')
        if not any(p.grad is not None and p.grad.abs().sum()>0 for p in encoder.parameters()):raise ValueError('encoder gradient missing')
        print(json.dumps(dict(component=component,smokeCheck='PASS',rows=len(sample),loss=float(loss.detach()),encoderGradient=True)),flush=True);return
    original=score(val);rng=np.random.default_rng(RECIPE['seed']);scaler=torch.amp.GradScaler('cuda',enabled=component=='HP');best=float('inf');history=[]
    for epoch in range(1,RECIPE['epochs']+1):
        mode(True);order=rng.permutation(train)
        for start in range(0,len(order),512):
            ids=order[start:start+512];opt.zero_grad();loss=losses(ids).mean()
            if not torch.isfinite(loss):raise ValueError('nonfinite training loss')
            scaler.scale(loss).backward();scaler.unscale_(opt);torch.nn.utils.clip_grad_norm_(parameters,RECIPE['clip']);scaler.step(opt);scaler.update()
        value=score(val);history.append(dict(epoch=epoch,validationNll=value));print(json.dumps(dict(component=component,**history[-1])),flush=True)
        if value<best:best=value;selected=epoch;state=copy.deepcopy(encoder.state_dict());head_states=[copy.deepcopy(head.state_dict()) for head in heads]
    encoder.load_state_dict(state)
    for head,head_state in zip(heads,head_states):head.load_state_dict(head_state)
    result=dict(sourceSha=sha,component=component,recipe=RECIPE,hashes=meta['hashes'],preparationCacheSha256=meta['cacheSha256'],warmBindings=bindings,trainRows=len(train),validationRows=len(val),testRows=len(test),originalValidationNll=original,selectedEpoch=selected,history=history,testNll=score(test),supportChanged=False)
    output.mkdir(parents=True);torch.save(dict(encoderStateDict=state,headStateDicts=head_states,metadata=result),output/'component.pt');result['artifactSha256']=c.base.sha256(output/'component.pt');c.base.json_dump(output/'fit.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--trajectory-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--component',choices=['survival','maxHP','HP','potion'],required=True);p.add_argument('--source-sha',required=True);p.add_argument('--smoke-check',action='store_true');a=p.parse_args();run(a.trajectory_dir,a.output_dir,a.component,a.source_sha,a.smoke_check)
