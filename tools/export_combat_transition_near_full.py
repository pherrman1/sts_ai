#!/usr/bin/env python3
"""Export the explicitly selected, qualified Smoke-excluded near-full stack."""
import argparse,json,struct,hashlib,subprocess
from pathlib import Path
from tools import export_combat_transition_runtime as old,combat_transition_near_full_models as models
from tools import combat_transition_composed as c,combat_transition_near_full_support as support
from tools import combat_transition_near_full_exposure as exposure

PASS='FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_PASS';FAIL='FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_FAIL';PASS_BY_OVERRIDE=PASS+'_BY_OVERRIDE'

def failing_entries(gate):
    """Gated `component.cohort` entries whose mean exposure gap misses the threshold."""
    return sorted(f'{component}.{cohort}' for component,entries in gate['components'].items() for cohort,v in entries.items() if not v.get('diagnosticOnly') and not v['gate'])

def exposure_override(qualification,gate,override_path):
    """Accept a FAIL exposure report only through a recorded override (as ctm_retrain_pins downstream_override).

    The override binds the exact exposure report and names exactly its failing gated entries, its approval,
    reason and evidence. Zero-mass rows and the whole-support validity checks are never waived."""
    override=json.loads(override_path.read_text())
    if override.get('schema')!='ctm_gate_override_v1' or override.get('stage')!='final-support-exposure':raise ValueError('override is not a ctm_gate_override_v1 for the final-support-exposure stage')
    if override.get('exposureSha256')!=c.base.sha256(qualification):raise ValueError('override does not bind this exposure report')
    failures=failing_entries(gate)
    if gate['classification']!=FAIL or not failures:raise ValueError('override applies only to a FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_FAIL report')
    if override.get('waivedEntries')!=failures:raise ValueError(f'override must name exactly the failing gated entries {failures}')
    if not all(isinstance(override.get(k),str) and override[k].strip() for k in ('approval','reason')):raise ValueError('override must name its approval and reason')
    if not isinstance(override.get('evidence'),dict) or not override['evidence']:raise ValueError('override must carry its evidence')
    return c.base.sha256(override_path),failures

def export(parent,qualification,validity,output,override=None):
    gate=json.loads(qualification.read_text());raw=json.loads(validity.read_text());census=json.loads((parent/'final-support-census-v1.json').read_text())
    if not gate['finalSupport'] or not raw['finalSupport']:raise ValueError('final supported cohort not qualified')
    if override is None:
        if gate['classification']!=PASS:raise ValueError('final supported cohort not qualified')
        waived=[];recorded=dict(classification=gate['classification'])
    else:
        override_sha,waived=exposure_override(qualification,gate,override);recorded=dict(classification=PASS_BY_OVERRIDE,overrideSha256=override_sha,waivedEntries=waived)
    if any(v['zeroExactMassRows'] for v in exposure.gated_entries(gate)) or failing_entries(gate)!=waived:raise ValueError('slice exposure gate failed')
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
    metadata.update(schema='COMBAT_TRANSITION_RUNTIME_V2',version=2,sources=bindings,supportExclusions=list(support.FINAL_EXCLUSIONS),supportCensus=census['groups'],qualification=dict(exposureSha256=c.base.sha256(qualification),validitySha256=c.base.sha256(validity),independentHoldout=False,**recorded),tensors={k:list(v.shape) for k,v in tensors.items()})
    header=json.dumps(metadata,sort_keys=True,separators=(',',':')).encode()
    with output.open('xb') as stream:
        stream.write(b'COMBAT_TRANSITION_RUNTIME_V2\0');stream.write(struct.pack('<II',2,len(header)));stream.write(header)
        for name in sorted(tensors):stream.write(tensors[name].tobytes(order='C'))
    receipt=dict(path=str(output.resolve()),sha256=c.base.sha256(output),bytes=output.stat().st_size,sources=bindings,qualification=metadata['qualification'],supportCensus=census['groups'],sourceSha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip())
    print(json.dumps(receipt),flush=True);return receipt
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--qualification',type=Path,required=True);p.add_argument('--validity',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--exposure-override',type=Path,help='ctm_gate_override_v1 JSON accepting a FAIL exposure report');a=p.parse_args();export(a.parent,a.qualification,a.validity,a.output,a.exposure_override)
