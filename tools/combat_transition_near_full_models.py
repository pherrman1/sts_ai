"""Verified explicit component selection for frozen near-full inference."""
import json
from pathlib import Path
import torch
from tools import combat_transition_composed as c
from tools import combat_transition_near_full_downstream as d


def load(parent,device='cuda',downstream='full-union-downstream-v1',maxhp='full-union-maxHP-v1'):
    parent=Path(parent);m,bindings=d.load_upstream(parent,device)
    if maxhp!='full-union-maxHP-v1':
        folder=parent/maxhp;receipt=json.loads((folder/'fit.json').read_text());path=folder/'component.pt'
        if c.base.sha256(path)!=receipt['artifactSha256']:raise ValueError('selected maxHP checkpoint differs')
        payload=torch.load(path,map_location=device,weights_only=False);m.max_net.encoder.load_state_dict(payload['encoderStateDict']);m.max_net.max_hp_delta.load_state_dict(payload['headStateDicts'][0]);bindings['maxHP']=receipt['artifactSha256']
    folder=parent/downstream;receipt=json.loads((folder/'fit.json').read_text());path=folder/'downstream.pt'
    if c.base.sha256(path)!=receipt['artifactSha256']:raise ValueError('selected downstream checkpoint differs')
    for name in ('survival','HP','potion'):
        if receipt['preparation']['upstreamBindings'][name]!=bindings[name]:raise ValueError('downstream encoding checkpoint differs')
    nets=d.models(parent).to(device).eval().requires_grad_(False);nets.load_state_dict(torch.load(path,map_location=device,weights_only=False)['stateDict']);bindings['downstream']=receipt['artifactSha256'];m.to(device)
    return m,nets,bindings
