#!/usr/bin/env python3
"""Launch only the frozen masks2..31 after valid mask1 canary; four workers."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
from pathlib import Path
import subprocess
from build_runtime import HERE,REPO,RUNTIME,write,sha

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--reviewed-sha',required=True);args=parser.parse_args()
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()==args.reviewed_sha
    canary=json.loads((HERE/'runs/00001.receipt.json').read_text());assert canary['status']=='VALID' and canary['canary_prefix_pass'] and canary['reviewed_sha']==args.reviewed_sha
    frozen=json.loads((HERE/'FREEZE.json').read_text());assert frozen['workers']==4 and frozen['masks']==list(range(32))
    latch=RUNTIME/'batch-started.json';assert not latch.exists()
    write(latch,{'reviewed_sha':args.reviewed_sha,'freeze_sha256':sha(HERE/'FREEZE.json'),'masks':list(range(2,32)),'workers':4})
    def run(mask):
        with (RUNTIME/f'runner-{mask:05b}.log').open('x') as out:
            return mask,subprocess.run(['python3',str(HERE/'run_mask.py'),str(mask),'--reviewed-sha',args.reviewed_sha],cwd=REPO,stdout=out,stderr=subprocess.STDOUT).returncode
    completed=[];failed=[]
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures={executor.submit(run,m):m for m in range(2,32)}
        for future in as_completed(futures):
            if future.cancelled():continue
            mask,returncode=future.result();completed.append(mask)
            if returncode:
                failed.append(mask)
                for pending in futures:pending.cancel() # running masks finish; never retry
            write(RUNTIME/'batch-progress.json',{'completed':sorted(completed),'failed':failed,'planned':list(range(2,32)),'workers':4})
            print(f'mask {mask:05b}: returncode {returncode}',flush=True)
    write(HERE/'batch.json',{'completed':sorted(completed),'failed':failed,'expected_masks':list(range(2,32)),'workers':4,'no_retries':True})
    return 0 if not failed and len(completed)==30 else 1
if __name__=='__main__':raise SystemExit(main())
