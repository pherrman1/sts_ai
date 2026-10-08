#!/usr/bin/env python3
"""Freeze the reviewed GEN2 contract without running any source trajectory."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[5]
EVIDENCE = ROOT / 'docs/experiments/evidence/ironclad_a0_overnight_20261008'
OUT = EVIDENCE / 'learning/gen2_canary_736d'
SOURCE = '736d1ff7e61725d9c6a50326064b2e3060ce6ae4'
BINARY_HASH = '3f69f5fd251ac699580bca8eb8da707282c77bc5263732f10e83f8e2670aba2d'
BINARY = ROOT / 'build/overnight_20261008/binaries/reviewed-736d1ff7/one_combat'
sha = lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    if OUT.exists(): raise RuntimeError('refusing existing GEN2 freeze directory')
    if sha(BINARY) != BINARY_HASH: raise RuntimeError('reviewed binary hash changed')
    profiles = json.loads((EVIDENCE/'fair_profiles.json').read_text())
    env = dict(profiles['common']); env.update(profiles['arms']['Fprod'])
    env['STS_EXECUTABLE_GIT_SHA'] = SOURCE
    OUT.mkdir()
    policy_path, teacher_path = OUT/'policy.json', OUT/'teacher.json'
    command = [str(BINARY),'vwinrefreshpolicyspec',str(policy_path)]
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    (OUT/'policy.log').write_text(result.stdout+result.stderr)
    policy = json.loads(policy_path.read_text())
    assert policy['parameters']['native_ooc_public_futures'] == 8
    assert policy['parameters']['stop_after_act'] == 3
    maker = ROOT/'docs/experiments/evidence/ooc_cf_pilot_20261007/make_teacher.py'
    subprocess.run([sys.executable,str(maker),SOURCE,str(BINARY),str(policy_path),str(teacher_path)],
                   cwd=ROOT,env=env,check=True)
    teacher = json.loads(teacher_path.read_text())
    teacher['teacher_id'] = 'silver-fair-public8-learnedstop-v4-a3-gen2-736d1ff7'
    teacher['environment'] = env
    teacher['search_configuration']['final_boss_binary'] = False
    teacher_path.write_text(json.dumps(teacher,indent=2)+'\n')
    artifacts = {a['path']:a['sha256'] for a in teacher['model_artifacts']}
    for p,h in artifacts.items(): assert sha(ROOT/p)==h, p
    stop_path = 'src/sim/search/NativeSilverStopModel.cpp'
    artifacts[stop_path] = sha(ROOT/stop_path)
    freeze = {'schema':'overnight_gen2_canary_v1','status':'FROZEN_NOT_LAUNCHED',
              'root':str(ROOT),'source_sha':SOURCE,'binary':str(BINARY),'binary_sha256':BINARY_HASH,
              'teacher':str(teacher_path),'teacher_sha256':sha(teacher_path),
              'policy_sha256':sha(policy_path),'artifacts':artifacts,
              'source_seeds':list(range(610084000,610084004)),'futures':4,
              'states_per_seed':2,'types':['CARD_REWARD','BOSS_RELIC'],
              'selection_k':[0,1],'evaluation_k':[2,3],'frozen_epoch':time.time(),
              'max_concurrent_source_processes':4,'campaign_max_game_processes':6,
              'timeout_seconds_per_source':1800,
              'source_and_branch_budget_policy':'learned_stop (configured native backend; nominal sims argument 10000)',
              'gates':{'source_trajectory_valid':True,'all_retained_sibling_branches_valid':True,
                       'all_present_fatal_quarantine_counters_zero':True,'runtime_budget_profile_required':True,
                       'selected_action_saved_and_hashed_before_eval_outcomes':True},
              'policy_command':command,'maker_sha256':sha(maker),'freeze_script_sha256':sha(__file__)}
    (OUT/'freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    print(json.dumps({'freeze':str(OUT/'freeze.json'),'freeze_sha256':sha(OUT/'freeze.json'),
                      'teacher_sha256':sha(teacher_path),'policy_sha256':sha(policy_path)},indent=2))

if __name__=='__main__': main()
