#!/usr/bin/env python3
"""Exact seed-free accounting of the final pre-state support predicate."""
import argparse,json,hashlib
from collections import Counter
from pathlib import Path
from tools import combat_transition_composed as c,combat_transition_composed_evaluate as e
from tools import combat_transition_near_full_support as s

def census(output):
    if output.exists():raise ValueError('refusing overwrite')
    hashes=e.verify_data();arrays,_=c.base._load_prepared(e.PREPARED);m=c.FrozenModels('cpu')
    counts={name:Counter() for name in ('all','TRAIN','VALIDATION','TEST')};reasons={name:Counter() for name in counts};digest={name:hashlib.sha256() for name in counts}
    for index,row in enumerate(c.base.iter_rows(e.CORPUS)):
        assert int(row['sourceSeed'])==int(arrays['sourceSeed'][index])
        pre=row['transition']['pre'];pi=row['predictorInput'];why=s.final_reasons(pi,pre,m);partition=('TRAIN','VALIDATION','TEST')[int(arrays['split_id'][index])]
        for name in ('all',partition):
            counts[name]['rows']+=1;counts[name]['unsupported' if why else 'supported']+=1;reasons[name].update(why)
            if not why:digest[name].update(f'{index}\n'.encode())
        if index%50000==0:print(index,flush=True)
    result=dict(hashes=hashes,exclusions=s.FINAL_EXCLUSIONS,groups={name:dict(counts=value,supportedPercent=100*value['supported']/value['rows'],reasons=reasons[name],supportedIndexSha256=digest[name].hexdigest()) for name,value in counts.items()},predicate='visible pre-state only; no post labels',runtimeChanged=False)
    c.base.json_dump(output,result);print(json.dumps(result),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();census(a.output)
