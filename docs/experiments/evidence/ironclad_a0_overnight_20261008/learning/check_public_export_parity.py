#!/usr/bin/env python3
"""Native export parity on exactly the already-authorized 64 TRAIN fixture rows."""
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import numpy as np
import xgboost as xgb
ROOT=Path(__file__).resolve().parents[5]
sys.path.insert(0,str(ROOT))
from tools.vwin_refresh_contract import MAP_PREFIX
from tools.vwin_refresh_dataset import source_split
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
E=ROOT/'docs/experiments/evidence/ironclad_a0_overnight_20261008'
B=ROOT/'build/overnight_20261008/binaries/reviewed-736d1ff7/one_combat'
OUT=ROOT/'build/overnight_20261008/learning/native-e1-parity-736d-v2'

def main():
    OUT.mkdir(exist_ok=False)
    assert sha(B)=='3f69f5fd251ac699580bca8eb8da707282c77bc5263732f10e83f8e2670aba2d'
    original=json.loads((E/'learning/export_receipt.json').read_text())
    assert original['fixture_split']=='TRAIN'
    manifest=Path(original['fixture_manifest'])
    assert sha(manifest)==original['fixture_manifest_sha256']
    m=json.loads(manifest.read_text()); seeds=m['seedSpec']
    assert {source_split(s) for s in range(seeds['start'],seeds['start']+seeds['count'])}=={'TRAIN'}
    table=Path(original['fixture_table']); assert sha(table)==original['fixture_table_sha256']
    names=m['stateFeatures']['header'].split(','); offset=len(MAP_PREFIX)
    with table.open(newline='') as f:
        reader=csv.reader(f); header=next(reader); assert header[offset:offset+len(names)]==names
        rows=[]
        for row in reader:
            rows.append(row[offset:offset+len(names)])
            if len(rows)==64: break
    fixture=OUT/'train64.tierb.csv'
    with fixture.open('x',newline='') as f:
        w=csv.writer(f,lineterminator='\n'); w.writerow(['chosen']+names+['won'])
        for row in rows: w.writerow([0]+row+[0])
    full=np.asarray(rows,dtype=np.float32)
    profiles=json.loads((E/'fair_profiles.json').read_text())
    env=dict(profiles['common'],**profiles['arms']['Fprod'],
             STS_EXECUTABLE_GIT_SHA='736d1ff7e61725d9c6a50326064b2e3060ce6ae4')
    results=[]
    for model in original['exports']:
        native=Path(model['native_path']); assert sha(native)==model['native_sha256']
        ubj=Path(model['path']); assert sha(ubj)==model['sha256']
        cmd=[str(B),'winnettest',str(native),str(fixture),'64']
        proc=subprocess.run(cmd,cwd=ROOT,env=env,capture_output=True,text=True)
        log=OUT/(model['arm']+'.log'); log.write_text(proc.stdout+proc.stderr)
        proc.check_returncode()
        parsed=[(int(i),float(v)) for i,v in re.findall(r'^([0-9]+),([0-9.eE+-]+)$',proc.stdout,re.M)]
        assert [i for i,v in parsed]==list(range(64))
        booster=xgb.Booster(params={'nthread':1}); booster.load_model(ubj)
        predicted=booster.inplace_predict(full[:,[names.index(n) for n in booster.feature_names]])
        error=float(np.max(np.abs(predicted-np.array([v for i,v in parsed]))))
        assert error<1e-5,error
        results.append({'arm':model['arm'],'model_sha256':sha(ubj),'native_sha256':sha(native),
                        'native_xgboost_max_abs_error':error,'rows':64,'tolerance':1e-5,
                        'command':cmd,'log':str(log),'log_sha256':sha(log),'status':'PASS'})
    result={'schema':'overnight_native_export_parity_v1','source_sha':env['STS_EXECUTABLE_GIT_SHA'],
            'binary':str(B),'binary_sha256':sha(B),'script_sha256':sha(__file__),
            'fixture':str(fixture),'fixture_sha256':sha(fixture),'fixture_split':'TRAIN',
            'fixture_source':str(table),'fixture_source_sha256':sha(table),'test_rows_opened':False,
            'environment':env,'results':results,'qualification':'EXPORT_PARITY_ONLY; no gameplay qualification'}
    receipt=OUT/'receipt.json'; receipt.write_text(json.dumps(result,indent=2)+'\n')
    (E/'learning/native_export_parity_receipt.json').open('x').write(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'receipt':str(receipt),'receipt_sha256':sha(receipt),'results':results},indent=2))

if __name__=='__main__': main()
