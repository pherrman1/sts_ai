#!/usr/bin/env python3
"""Check only six predeclared leads and their runtime custody; never run a seed."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

E=Path(__file__).resolve().parent
ROOT=E.parents[3]
PRIMARY=Path('/home/philippherrmann/Documents/sts/sts_lightspeed')
HEART=PRIMARY/'build/heart-outcome-round2-data-a8f6542e/heart-outcome-round2'
BUNDLE=PRIMARY/'build/heart-outcome-collection-20261016-v1/bundle'
DATA='43ad57f0e34e5bc34b7cb21c9fa8f8d5bb3039c1'
HEART_CODE='d8fd2a105a8d2a481b7639e26c683f75e382e3d4'
AZ_CODE='844bd9239c6621968f5095c6f84aba6de27bbf2f'
HEART_BINARY='0e17e0f22259afe21f35ba89a0413f2af7663cfae1312311f1ea8c71b00c2d52'
AZ_BINARY='23a09099a161fbc7a4b944924536064f6c9f84e28f2731e13c8751bf611a269c'
# Three requested leads plus three from the already-frozen census; no new census.
LEADS=[(111101032,'HEART',65,'cycle_pair'),(111143169,'AZ',8,'cycle_pair'),
       (111143224,'AZ',12,'cycle_pair'),(111101326,'HEART',134,'cycle_pair'),
       (111142899,'AZ',5,'sundial_draw'),(111101512,'HEART',52,'sundial_draw')]
AZ_UNITS={111143169:('111143169.w26.tar','d8a2cc051d916f6c8ed034d896c0bf14d13a8663db9e4a56430070bc53a12b8f'),
          111142899:('111142899.w12.tar','9ff0840dbb8516869b9810b9a5c7992a4c80ad455ac4efb2307483020bc590bb'),
          111143224:('111143224.w17.tar','4e8845b7a8df0584ebbbbc4d97e981e16920b00580d594e9a40cd7ecc24954f5')}

def sha(b):return hashlib.sha256(b).hexdigest()
def git(ref,path):return subprocess.check_output(['git','show',ref+':'+path],cwd=ROOT)
def fingerprint(record):
 fields={k:v for k,v in record.items() if k.startswith('obs.') or k in ('screen_state','select_screen_type')}
 return sha(json.dumps(fields,sort_keys=True).encode())
def artifact(path,expected):
 p=Path(path);actual=sha(p.read_bytes()) if p.is_file() else None
 return {'path':str(p),'expected_sha256':expected,'actual_sha256':actual,'present_and_matches':actual==expected}

def main():
 inventory=json.loads((E/'executable-inventory.json').read_text())
 for item in inventory:assert sha(Path(item['path']).read_bytes())==item['sha256']
 assert not any(r['sha256'] in (HEART_BINARY,AZ_BINARY) for r in inventory)
 bundle=json.loads((HEART/'campaign/bundle-manifest/bundle.json').read_text())
 index=json.loads((HEART/'DELIVERY-INDEX.json').read_text())
 heart_model_paths=['studentc.bin','models/v_rich_trees.txt','models/candidates/v_win_x2b_public_trees.txt',
 'selfplay/models/ooc_strategic_tok_final.native','selfplay/models/combat_transition_deepsets_pathb_r2_lizard.native',
 'selfplay/models/combat_transition_near_full_escape_pathb_r2.native',
 'selfplay/models/combat_transition_deepsets_pathb_a20_lizard.native','selfplay/models/combat_transition_near_full_escape_pathb_a20.native']
 heart_models=[artifact(BUNDLE/p,bundle['files'][p]) for p in heart_model_paths]
 assert all(x['present_and_matches'] for x in heart_models)
 routes=[]
 for code in (HEART_CODE,AZ_CODE,'fa8e9278fd7b7c6913b69ca53bede1485fa62fed'):
  paths=['apps/one_combat.cpp','apps/one_combat/run_driver.cpp','src/sim/search/NativeSilverBackend.cpp']
  text={p:git(code,p).decode() for p in paths}
  assert 'heartoutcomegen' in text[paths[0]] and 'STS_OOC_DECISION_TRACE' in text[paths[1]]
  assert all(x in text[paths[2]] for x in ('STS_SILVER_PUBLIC_TRACE','STS_SILVER_PUBLIC_TARGET','SEED:FLOOR'))
  routes.append({'producer_sha':code,'files_sha256':{p:sha(git(code,p)) for p in paths},
                 'paired_trace_parse_sites_verified':True})
 leads=[];archive_hashes={}
 for seed,family,checkpoint,kind in LEADS:
  row={'source_seed':seed,'ingredient_class':kind,'family':family,'binary_sha256':HEART_BINARY if family=='HEART' else AZ_BINARY,
       'producer_sha':HEART_CODE if family=='HEART' else AZ_CODE,
       'binary_available_in_declared_inventory':False,'locally_runnable_exact_source':False,
       'run_launched':False,'fidelity':'NOT_TESTED_MISSING_ARTIFACTS'}
  if family=='HEART':
   worker=(seed-111101000)%32;folder=f'w{worker:02d}';p=HEART/'deliveries'/folder/'train.tar.gz'
   expected=index['workers'][folder]['archives']['train.tar.gz']
   if str(p) not in archive_hashes:archive_hashes[str(p)]=sha(p.read_bytes())
   assert archive_hashes[str(p)]==expected
   with tarfile.open(p) as tar:
    prefix=f'train/seed-{seed}'
    receipt_bytes=tar.extractfile(prefix+'.receipt.json').read();receipt=json.loads(receipt_bytes)
    state_bytes=tar.extractfile(prefix+'.states.jsonl').read();trace_bytes=tar.extractfile(prefix+'.trace.jsonl').read()
    assert sha(state_bytes)==receipt['files'][f'seed-{seed}.states.jsonl']
    assert sha(trace_bytes)==receipt['files'][f'seed-{seed}.trace.jsonl']
    assert receipt['sourceSha']==HEART_CODE and receipt['binarySha256']==HEART_BINARY
    header=json.loads(state_bytes.splitlines()[0]);assert header['producerSha']==HEART_CODE and header['seed']==seed
    checkpoints=[]
    for line in state_bytes.splitlines()[1:]:
     r=json.loads(line)
     if r.get('type')=='state' and r['index'] in (0,checkpoint):
      checkpoints.append({'index':r['index'],'act':r['act'],'floor':r['floor'],'screen':r['screen'],
                          'public_observation_sha256':fingerprint(r['record']),
                          'deck_ids':r['record']['obs.deck.cards'],'deck_upgrades':r['record']['obs.deck.upgrades'],
                          'relic_ids':r['record']['obs.relics.relics'],'relic_counters':r['record']['obs.relics.relic_counters']})
    assert len(checkpoints)==2
    target=None
    for line in trace_bytes.splitlines():
     r=json.loads(line)
     if r.get('kind')!='battle':continue
     pre=r['pre'];names=Counter(x.replace('+','').replace(' ','').upper() for x in pre['deck'])
     match=(names['DROPKICK']+names['FLASHOFSTEEL']+names['FINESSE']>=2) if kind=='cycle_pair' else ('SUNDIAL' in pre['relics'])
     if match:
      target={'act':pre['act'],'floor':pre['floor'],'fight':r['fight'],'encounter':r['encounter'],
              'pre_deck':pre['deck'],'pre_relics':pre['relics'],'source_pre_sha256':sha(json.dumps(pre,sort_keys=True).encode()),
              'future_public_target_if_restored':f"{seed}:{pre['floor']}"};break
    row.update({'binary_identity_basis':'actual retained source receipt','source_archive':str(p),'source_archive_sha256':expected,
                'receipt_sha256':sha(receipt_bytes),'retained_states_sha256':sha(state_bytes),'retained_trace_sha256':sha(trace_bytes),
                'original_command':receipt['command'],'original_environment':receipt['environment'],
                'policy':receipt['policy'],'checkpoints':checkpoints,'first_ingredient_bearing_battle':target,
                'models':heart_models,'seed_semantics':'original unsigned game seed; no namespace conversion',
                'missing_artifacts':['frozen Heart executable '+HEART_BINARY]})
  else:
   path=f'gen3/rows_new/az-{seed}.capture.jsonl.gz';body=git(DATA,path)
   checksums=git(DATA,'gen3/rows_new.sha256').decode().splitlines()
   entries=[line for line in checksums if Path(line.split()[-1]).name=='az-'+str(seed)+'.capture.jsonl.gz']
   assert len(entries)==1 and entries[0].split()[0]==sha(body)
   rows=[json.loads(x) for x in gzip.decompress(body).splitlines()];r=rows[checkpoint];assert r['seed']==seed
   name,expected=AZ_UNITS[seed];raw=Path('/mnt/project-files/az-gen2-ab/units')/name
   assert not raw.exists()
   tar_list=ROOT/'docs/experiments/evidence/az_gen2_ab_20261021/tars.sha256'
   entries=[line for line in tar_list.read_text().splitlines() if Path(line.split()[-1]).name==name]
   assert len(entries)==1 and entries[0].split()[0]==expected
   student=artifact('/home/philippherrmann/h1distill/E_sel/E_d64_sel_xin/student_sel.bin','cf6bf7fb7c3147dcc5b106b1a946486e40bf27fee87c57bcc3262b5869d507c7')
   assert student['present_and_matches']
   tracked_models=[]
   for name in ('models/combat_policy_mlp_g7f_E.txt','models/candidates/ooc_learned_stop_trees.txt',
                'selfplay/models/ooc_strategic_tok_final.native',
                'selfplay/models/combat_transition_deepsets_pathb_r2_lizard_ritual_refit.native',
                'selfplay/models/combat_transition_near_full_escape_pathb_r2_ritual_refit.native',
                'selfplay/models/combat_transition_deepsets_pathb_a20_lizard.native',
                'selfplay/models/combat_transition_near_full_escape_pathb_a20.native',
                'models/candidates/ctm_act4_survival_trees.txt'):
    expected_model=sha(git(AZ_CODE,name));candidate=ROOT/name
    entry=artifact(candidate,expected_model)
    assert entry['present_and_matches'],name
    tracked_models.append(entry)
   row.update({'binary_identity_basis':'campaign freeze only; raw header/environment unavailable',
               'run_commit':'712d4def04a62f0ae3e769a3548a46bfa19d5ca0',
               'converted_data_commit':DATA,'converted_path':path,'converted_sha256':sha(body),
               'converted_public_checkpoint':{'row':checkpoint,'public_observation_sha256':fingerprint(r['record']),
                                              'deck_ids':r['record']['obs.deck.cards'],'relic_ids':r['record']['obs.relics.relics']},
               'raw_archive':str(raw),'raw_archive_expected_sha256':expected,'raw_header_available':False,
               'raw_archive_checksum_source':'docs/experiments/evidence/az_gen2_ab_20261021/tars.sha256',
               'expected_run_script_sha256':sha((ROOT/'docs/experiments/evidence/az_gen2_ab_20261021/run_unit.sh').read_bytes()),
               'student_model':student,'expected_tracked_models':tracked_models,'policy_arm':'gen2 A/B arm A; student_sel',
               'seed_semantics':'original game seed unchanged; A maps to az-SEED; B/E use different prefixes',
               'missing_artifacts':['frozen AZ executable '+AZ_BINARY,'hash-bound raw unit '+str(raw)]})
  leads.append(row)
 return {'schema':'infinity_paired_capture_preflight_v1','starting_sha':'fa8e9278fd7b7c6913b69ca53bede1485fa62fed',
         'conclusion':'BLOCKED_BY_REPLAY_ARTIFACTS','leads':leads,'routes':routes,
         'executables_checked':len(inventory),'unique_executable_hashes':len({r['sha256'] for r in inventory}),
         'runs_attempted':0,'ingredient_bearing_combats_reproduced':0,'public_roots_captured':0,
         'tier1_roots':None,'tier2_roots':None,'selected_roots':0,'annotated_worlds':0,'witnesses':[],
         'node_cap_rate':None,'fidelity_gate_passed':False,'new_schema_or_runtime_code':False,
         'scope_note':'Declared retained primary/app-worktree build/bundle paths only; not a global or cloud disk inventory'}

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
 text=json.dumps(main(),indent=2)+'\n';p=E/'PREFLIGHT.json'
 if args.check:assert p.read_bytes()==text.encode(),'preflight differs'
 else:
  assert not p.exists(),'preserve prior preflight';p.write_text(text)
 print('PASS six-lead artifact/custody/route preflight; BLOCKED_BY_REPLAY_ARTIFACTS; zero seed or oracle execution')
