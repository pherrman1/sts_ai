"""Malformed native artifacts must fail loudly; no real artifact dependency."""
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.combat_predictor_input_contract import FIELD_SCHEMA, FIELD_SCHEMA_HASH

MAGIC=b'COMBAT_TRANSITION_RUNTIME_V1\0'
# Minimal prefix reaches predictor/dimension rejection without allocating tensors.
header=dict(schema='COMBAT_TRANSITION_RUNTIME_V1',version=1,
            predictorSchema='combat_predictor_input_v1',predictorHash='wrong',predictorFieldSchema='wrong')
with tempfile.TemporaryDirectory() as directory:
    directory=Path(directory);fixture=directory/'empty.jsonl';fixture.write_text('')
    encoded=json.dumps(header).encode()
    cases={'wrong_magic':b'X'*len(MAGIC),'wrong_version':MAGIC+struct.pack('<I',2),
           'truncated_header':MAGIC+struct.pack('<II',1,100)+b'{',
           'incompatible_predictor':MAGIC+struct.pack('<II',1,len(encoded))+encoded}
    header.update(predictorHash=FIELD_SCHEMA_HASH,predictorFieldSchema=FIELD_SCHEMA,width=63,layers=2,heads=4,feedForward=128)
    encoded=json.dumps(header).encode();cases['wrong_dimensions']=MAGIC+struct.pack('<II',1,len(encoded))+encoded
    for name,payload in cases.items():
        model=directory/(name+'.native');model.write_bytes(payload)
        result=subprocess.run([sys.argv[1],str(model),str(fixture)],text=True,capture_output=True)
        if result.returncode==0 or not result.stderr.strip():raise RuntimeError('silently accepted '+name)
        print(name,'PASS',result.stderr.strip())
    control=Path(__file__).resolve().parents[1]/'selfplay/models/combat_transition_near_full_except_smoke_v2.native'
    original=control.read_bytes();magic=b'COMBAT_TRANSITION_RUNTIME_V2\0'
    version,length=struct.unpack_from('<II',original,len(magic));offset=len(magic)+8
    control_header=json.loads(original[offset:offset+length]);body=original[offset+length:]
    selection=dict(architecture='deepset64_linear_strongWd',
        checkpointSha256='3689593db85974f13b6313c495e7fde4ec4b4fa7d87f3442c8604a47f5e0f05b',
        controlSha256='e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd',qualified=False)
    for case in ('width96','wrong_checkpoint','wrong_control','claims_qualification','missing_field','wrong_source','attention_tensor_graph'):
        altered=json.loads(json.dumps(control_header));altered['experimentalSurvival']=dict(selection)
        altered['sources']['survival']=selection['checkpointSha256']
        if case=='width96':altered['experimentalSurvival']['architecture']='deepset96'
        elif case=='wrong_checkpoint':altered['experimentalSurvival']['checkpointSha256']='0'*64
        elif case=='wrong_control':altered['experimentalSurvival']['controlSha256']='0'*64
        elif case=='claims_qualification':altered['experimentalSurvival']['qualified']=True
        elif case=='missing_field':del altered['experimentalSurvival']['qualified']
        elif case=='wrong_source':altered['sources']['survival']='0'*64
        encoded=json.dumps(altered).encode();model=directory/(case+'.native')
        model.write_bytes(magic+struct.pack('<II',version,len(encoded))+encoded+body)
        result=subprocess.run([sys.argv[1],str(model),str(fixture)],text=True,capture_output=True)
        if result.returncode==0 or not result.stderr.strip():raise RuntimeError('silently accepted '+case)
        print(case,'PASS',result.stderr.strip())
