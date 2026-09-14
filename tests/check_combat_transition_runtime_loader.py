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
