#!/usr/bin/env python3
"""Export the explicitly selected, qualified Smoke-excluded near-full stack."""
import argparse,json,struct,hashlib
from pathlib import Path
from tools import export_combat_transition_runtime as old,combat_transition_near_full_models as models
from tools import combat_transition_composed as c,combat_transition_near_full_support as support

def export(parent,qualification,validity,output):
    gate=json.loads(qualification.read_text());raw=json.loads(validity.read_text());census=json.loads((parent/'final-support-census-v1.json').read_text())
    if gate['classification']!='FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_PASS' or not gate['finalSupport'] or not raw['finalSupport']:raise ValueError('final supported cohort not qualified')
    if any(not v['gate'] or v['zeroExactMassRows'] for component in gate['components'].values() for v in component.values()):raise ValueError('slice exposure gate failed')
    if any(raw['violations'].values()) or raw['counts']['downstreamAfterDeath'] or raw['counts']['draws']!=32*census['groups']['TEST']['counts']['supported']:raise ValueError('whole final support validity failed')
    if c.base.sha256(qualification.with_suffix('.npz'))!=gate['rowEvidenceSha256']:raise ValueError('exposure rows differ')
    m,nets,bindings=models.load(parent,'cpu')
    if bindings!=gate['bindings'] or bindings!=raw['bindings']:raise ValueError('qualification checkpoint mismatch')
    metadata,_=old.runtime_payload();tensors={}
    groups=dict(survival=m.survival_net,max_hp=m.max_net,hp=m.hp_net,potion_encoder=m.potion_encoder,potion=m.potion_net,**{name:nets[name] for name in ('relic','gold','writhing','ritual')})
    for group,net in groups.items():
        for name,value in sorted(net.state_dict().items()):
            if group=='hp' and name=='classes':continue
            if not value.is_floating_point():raise ValueError('unexpected integer weight')
            array=value.detach().cpu().float().contiguous().numpy().astype('<f4')
            if not c.np.isfinite(array).all():raise ValueError('nonfinite weight')
            tensors[group+'.'+name]=array
    metadata.update(schema='COMBAT_TRANSITION_RUNTIME_V2',version=2,sources=bindings,supportExclusions=list(support.FINAL_EXCLUSIONS),supportCensus=census['groups'],qualification=dict(exposureSha256=c.base.sha256(qualification),validitySha256=c.base.sha256(validity),classification=gate['classification'],independentHoldout=False),tensors={k:list(v.shape) for k,v in tensors.items()})
    header=json.dumps(metadata,sort_keys=True,separators=(',',':')).encode()
    with output.open('xb') as stream:
        stream.write(b'COMBAT_TRANSITION_RUNTIME_V2\0');stream.write(struct.pack('<II',2,len(header)));stream.write(header)
        for name in sorted(tensors):stream.write(tensors[name].tobytes(order='C'))
    receipt=dict(path=str(output.resolve()),sha256=c.base.sha256(output),bytes=output.stat().st_size,sources=bindings,qualification=metadata['qualification'],supportCensus=census['groups'],sourceSha=c.base.subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip() if hasattr(c.base,'subprocess') else None)
    print(json.dumps(receipt),flush=True);return receipt
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--qualification',type=Path,required=True);p.add_argument('--validity',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();export(a.parent,a.qualification,a.validity,a.output)
