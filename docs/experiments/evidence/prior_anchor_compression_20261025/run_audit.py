"""Run the bounded native audit in an explicit, recorded environment."""
import argparse,json,os,pathlib,subprocess,time,hashlib
p=argparse.ArgumentParser();p.add_argument('binary',type=pathlib.Path);p.add_argument('output',type=pathlib.Path);p.add_argument('--values',action='store_true');a=p.parse_args()
root=pathlib.Path(__file__).resolve().parents[4]
prior=pathlib.Path('/home/philippherrmann/.local/share/sts-ai/live-runtime/current/models/arm_c_student.bin').resolve()
env={'HOME':os.environ['HOME'],'PATH':os.environ['PATH'],'OMP_NUM_THREADS':'1','OMP_DYNAMIC':'FALSE',
 'STS_FAIR':'1','STS_COLLECT_KEYS':'1','STS_OOC_MCTS':'1','STS_OOC_MCTS_PRIOR':'heart1full',
 'STS_OOC_MCTS_LEAF_POLICY':'heart1','STS_OOC_MCTS_LEAF_VALUE':'native','STS_OOC_MCTS_LEAF_COMBATS':'3',
 'STS_OOC_MCTS_TARGET_PRIOR':'1','STS_OOC_MCTS_TREE_RULES':'1','STS_OOC_MCTS_UNSUPPORTED_SILVER_SIMS':'500',
 'STS_OOC_HEART1':str(prior),'STS_OOC_HEART1_WING_BOOTS_COUNTER':'1',
 'STS_OOC_STRATEGIC_TOK_NN':'selfplay/models/ooc_strategic_tok_final.native',
 'STS_OOC_STRATEGIC_REST':'1','STS_OOC_STRATEGIC_EVENT':'1','STS_OOC_STRATEGIC_SHOP':'1',
 'STS_OOC_STRATEGIC_TREASURE':'1','STS_OOC_STRATEGIC_BOSS_RELIC':'1','STS_OOC_STRATEGIC_MARGIN':'1.0',
 'STS_EXECUTABLE_GIT_SHA':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()}
output=a.output.resolve();binary=a.binary.resolve()
if output.exists() or output.is_symlink():raise SystemExit('refuse output reuse')
command=['bash','tools/seed_guard.sh',str(binary),'ooccompressionaudit',str(pathlib.Path(__file__).resolve().parent/'inputs.jsonl'),str(output)]+(['--values'] if a.values else [])
metadata={'command':command,'env':env,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
 'prior_sha256':hashlib.sha256(prior.read_bytes()).hexdigest(),'source_sha':env['STS_EXECUTABLE_GIT_SHA'],
 'values':a.values,'timeout_seconds':1200}
output.with_suffix('.launch.json').write_text(json.dumps(metadata,indent=2)+'\n')
start=time.monotonic()
with output.with_suffix('.stdout.log').open('w') as stdout,output.with_suffix('.stderr.log').open('w') as stderr:
 r=subprocess.run(command,cwd=root,env=env,stdout=stdout,stderr=stderr,timeout=1200)
metadata.update(exit_code=r.returncode,wall_seconds=time.monotonic()-start)
output.with_suffix('.receipt.json').write_text(json.dumps(metadata,indent=2)+'\n')
print(json.dumps({k:metadata[k] for k in ['exit_code','wall_seconds','values']}))
raise SystemExit(r.returncode)
