#!/usr/bin/env python3
import importlib.util,json
from pathlib import Path
H=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('base_runner',H/'run_confirmation.py'); base=importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
P=json.loads((H/'additional-plan.json').read_text())
def main():
 base.frozen_hashes()
 for arm in P['arms']: base.execute(arm,'canary_'+arm['id'],1,P['excluded_canaries'][arm['id']])
 (H/'additional-canaries-passed.json').write_text(json.dumps({'all_passed':True,'arms':[a['id'] for a in P['arms']]},indent=2)+'\n')
 for arm in P['arms']: base.execute(arm,'official_'+arm['id'],32,12003000)
 print('ADDITIONAL_ARMS_COMPLETE',flush=True)
if __name__=='__main__':main()
