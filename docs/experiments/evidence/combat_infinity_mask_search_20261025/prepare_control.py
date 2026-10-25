#!/usr/bin/env python3
"""Reuse successful manifest-unset qualification as mask00000; no game execution."""
import gzip
import json
from build_runtime import HERE,write,sha
from search_logic import control_result

def main():
    receipt=json.loads((HERE/'parity.json').read_text());assert receipt['qualification_result']=='FLAG_OFF_PARITY_PASS'
    trace=[json.loads(line) for line in gzip.decompress((HERE/'parity.trace.jsonl.gz').read_bytes()).splitlines()]
    manifest=json.loads((HERE/'manifests/00000.json').read_text());assert all(not e['enabled'] for e in manifest['interventions'])
    result=control_result(manifest,trace)
    data=dict(receipt,mask='00000',numeric_mask=0,qualification_reused=True,manifest_unset=True,mask_manifest_sha256=sha(HERE/'manifests/00000.json'),raw_archive_prefix='../parity',status='VALID')
    (HERE/'runs').mkdir(exist_ok=True);(HERE/'results').mkdir(exist_ok=True)
    with (HERE/'runs/00000.receipt.json').open('x') as f:f.write(json.dumps(data,indent=2)+'\n')
    write(HERE/'results/00000.json',{'status':'VALID','receipt_sha256':sha(HERE/'runs/00000.receipt.json'),'measurement':result})
    print('PASS parity reused as mask00000; target-entry only, no later outcome score')
if __name__=='__main__':main()
