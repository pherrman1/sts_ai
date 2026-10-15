#!/usr/bin/env python3
"""Freeze corrected GEN2 contract and cost canary; never execute source seeds."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[5]
EVIDENCE = ROOT / 'docs/experiments/evidence/ironclad_a0_overnight_20261008'
OUT = EVIDENCE / 'learning/gen2_canary_3ed9'
PROTOCOL = EVIDENCE / 'protocols/corrected_canary.json'
SOURCE = '3ed91ab3491a4cdc1a7de687b2ad87dcc7774fc0'
BINARY_HASH = '27a78efd3f5da731897d36dd9b50a622d2ace4f54dae69dfc157bf6712b027c7'
SEEDS = list(range(610084000, 610084004))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def main():
    require(not OUT.exists(), 'refusing existing corrected GEN2 freeze directory')
    contract = json.loads(PROTOCOL.read_text())
    require(contract['source_sha'] == SOURCE and contract['binary_sha256'] == BINARY_HASH,
            'corrected producer identity mismatch')
    require(Path(contract['root']).resolve() == ROOT, 'wrong corrected worktree')
    binary = Path(contract['binary'])
    require(sha(binary) == BINARY_HASH, 'corrected immutable binary hash changed')
    for path, digest in contract['artifacts'].items():
        require(sha(ROOT / path) == digest, 'corrected artifact changed: ' + path)
    allocation = json.loads((EVIDENCE / 'seeds.json').read_text())
    require(set(SEEDS) <= set(allocation['counterfactual_reserved']), 'sources not CF-reserved')
    env = dict(contract['profiles']['common'])
    env.update(contract['profiles']['arms']['Fprod'])
    env['STS_EXECUTABLE_GIT_SHA'] = SOURCE
    require(env['STS_OOC_PUBLIC_FUTURES'] == '8' and env['STS_OOC_SKIP_OPTIONAL_RECALL'] == '1'
            and env['STS_SILVER_FINAL_BOSS_BINARY'] == '0', 'wrong corrected Fprod profile')
    OUT.mkdir()
    policy_path, teacher_path = OUT / 'policy.json', OUT / 'teacher.json'
    command = [str(binary), 'vwinrefreshpolicyspec', str(policy_path)]
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    (OUT / 'policy.log').write_text(result.stdout + result.stderr)
    require(result.returncode == 0, 'native policy specification failed')
    policy = json.loads(policy_path.read_text())
    require(policy['parameters']['native_ooc_public_futures'] == 8, 'public futures not serialized')
    require(policy['parameters']['stop_after_act'] == 3, 'Act-3 cutoff not serialized')
    require(policy['flags'].get('skip_optional_recall') is True, 'Recall repair not serialized')
    require('[native OOC optional Ruby Recall excluded when keys off and another action is legal]'
            in result.stdout, 'Recall startup banner absent')
    maker = ROOT / 'docs/experiments/evidence/ooc_cf_pilot_20261007/make_teacher.py'
    subprocess.run([sys.executable, str(maker), SOURCE, str(binary), str(policy_path), str(teacher_path)],
                   cwd=ROOT, env=env, check=True)
    teacher = json.loads(teacher_path.read_text())
    teacher['teacher_id'] = 'silver-fair-public8-recall1-learnedstop-v4-a3-gen2-3ed91ab3'
    teacher['environment'] = env
    teacher['search_configuration']['final_boss_binary'] = False
    require(teacher['ooc_policy'] == policy, 'teacher/native effective policy differs')
    teacher_path.write_text(json.dumps(teacher, indent=2) + '\n')
    artifacts = {a['path']: a['sha256'] for a in teacher['model_artifacts']}
    for path, digest in artifacts.items():
        require(sha(ROOT / path) == digest, 'teacher artifact changed: ' + path)
        require(contract['artifacts'].get(path) == digest, 'teacher artifact not in corrected custody: ' + path)
    stop_path = 'src/sim/search/NativeSilverStopModel.cpp'
    artifacts[stop_path] = contract['artifacts'][stop_path]
    freeze = {
        'schema': 'overnight_gen2_canary_v1', 'status': 'FROZEN_NOT_LAUNCHED',
        'root': str(ROOT), 'source_sha': SOURCE, 'binary': str(binary), 'binary_sha256': BINARY_HASH,
        'corrected_runtime_protocol': str(PROTOCOL), 'corrected_runtime_protocol_sha256': sha(PROTOCOL),
        'teacher': str(teacher_path), 'teacher_sha256': sha(teacher_path),
        'policy': str(policy_path), 'policy_sha256': sha(policy_path), 'environment': env,
        'artifacts': artifacts, 'source_seeds': SEEDS, 'futures': 4, 'future_start': 0,
        'states_per_seed': 2, 'types': ['CARD_REWARD', 'BOSS_RELIC'],
        'selection_k': [0, 1], 'evaluation_k': [2, 3], 'frozen_epoch': time.time(),
        'max_concurrent_source_processes': 2, 'campaign_max_game_processes': 6,
        'capacity_at_authorization': '3 development workers + 1 targeted REST worker + at most 2 GEN2 workers',
        'timeout_seconds_per_source': 1800, 'maximum_source_runs': 4, 'maximum_sibling_branches': 192,
        'source_and_branch_budget_policy': 'learned_stop (configured native backend; nominal sims argument 10000)',
        'gates': {'source_trajectory_valid': True, 'all_retained_sibling_branches_valid': True,
                  'all_present_fatal_quarantine_counters_zero': True, 'runtime_budget_profile_required': True,
                  'runtime_optional_recall_banner_required': True,
                  'selected_action_saved_and_hashed_before_eval_outcomes': True},
        'scope': 'contract and cost canary; report every allocated case; no training or population-strength claim',
        'policy_command': command, 'policy_command_exit_code': result.returncode,
        'maker_sha256': sha(maker), 'freeze_script_sha256': sha(__file__)
    }
    (OUT / 'freeze.json').write_text(json.dumps(freeze, indent=2) + '\n')
    print(json.dumps({'freeze': str(OUT / 'freeze.json'), 'freeze_sha256': sha(OUT / 'freeze.json'),
                      'teacher_sha256': sha(teacher_path), 'policy_sha256': sha(policy_path),
                      'source_runs_executed': 0}, indent=2))


if __name__ == '__main__':
    main()
