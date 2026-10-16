"""Frozen local Heart leaf pilot. Called only after independent implementation review.

Usage: python run_heart_distill_pilot.py REPO DATA_ROOT REVIEWED_SHA STUDENT_C_NATIVE [--arm-c-rollout]
Creates an immutable run bundle, canaries, source-disjoint corpus, fit, then one-shot TEST.
Never replaces failed/partial units or extends frozen seeds/time limits.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from heart_rollout_distill import runtime_identity, validate_rows, verify_bundle, verify_tools


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v): Path(p).write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')


STUDENT_C_SHA256='eff2f74f57dc2f566bbd44be30988592503cc8db51e51ff1e70cd2dec4636509'


def study_config(arm_c_rollout=False):
    return {'leafPolicy':'heart1' if arm_c_rollout else 'v4',
            'sourceStart':110163000 if arm_c_rollout else 110161000,
            'canarySeeds':[110162994,110162995] if arm_c_rollout else [110159994,110159995],
            'sourceTimeoutSeconds':1200 if arm_c_rollout else 600,
            'cohortWallSeconds':21600 if arm_c_rollout else 14400,
            'protocol':'docs/experiments/evidence/arm_c_rollout_distill_20261016/PROTOCOL.md'
                       if arm_c_rollout else 'docs/experiments/evidence/heart_rollout_distill_20261016/PROTOCOL.md'}


def student_contract(text,support,seed,leaf_policy='v4'):
    expected='[heart1] loaded studentc.bin (dim 64, heads 4, hidden 256, layers 2, trim_map 1)'
    scored=support['heart1_prior_nodes'];fallback=support['heart1_prior_fallbacks']
    if any(type(v) is not int or v<0 for v in (scored,fallback,support['prior_leaf_steps'])):
        raise ValueError('invalid Arm C usage counters')
    share=scored/max(1,scored+fallback)
    if (expected not in text or ' prior=heart1 ' not in text or f' leaf_policy={leaf_policy}' not in text
            or support['seed']!=seed or scored<=0 or share<.9 or support['prior_leaf_steps']!=0):
        raise ValueError('Arm C tree prior / rollout runtime contract failed')
    result={'scored':scored,'fallback':fallback,'share':share,'priorLeafSteps':0,'shape':'64/4/256/2/trim1'}
    if leaf_policy=='heart1':
        steps=support['heart1_leaf_steps']; missed=support['heart1_leaf_fallbacks']
        if (any(type(v) is not int or v<0 for v in (steps,missed)) or steps<=0
                or steps/(steps+missed)<.9):
            raise ValueError('Arm C rollout use contract failed')
        result.update(rolloutSteps=steps,rolloutFallbacks=missed,rolloutShare=steps/(steps+missed))
    return result


def verify_canary_approval(root,freeze,freeze_sha,canary,canary_sha):
    approval=root/'canary-reviewed.json'
    review=json.loads(approval.read_text())
    if (review.get('verdict')!='PASS' or review.get('freezeSha256')!=freeze_sha
            or review.get('canarySha256')!=canary_sha or sha(root/'freeze.json')!=freeze_sha
            or sha(root/'canary.json')!=canary_sha):
        raise ValueError('canary review is not bound to this freeze/result')
    verify_bundle(root,freeze); verify_tools(freeze)
    if any(sha(root/name)!=digest for name,digest in canary['artifacts'].items()):
        raise ValueError('canary artifacts changed after review')
    return sha(approval)


def run(repo,root,reviewed,student_c,arm_c_rollout=False):
    study=study_config(arm_c_rollout)
    root.mkdir(parents=True,exist_ok=False); bundle=root/'run'; bundle.mkdir()
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()!=reviewed:
        raise ValueError('reviewed source is not HEAD')
    if subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True).strip():
        raise ValueError('source dirty before freeze')
    build_cmd=['cmake','--build','--preset','linux-gcc-release-ccache-build','--target','one_combat','-j2']
    build_start=time.time()
    with (root/'build.log').open('x') as log:
        built=subprocess.run(build_cmd,cwd=repo,stdout=log,stderr=subprocess.STDOUT,timeout=900)
    if built.returncode:raise RuntimeError('reviewed source build failed')
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()!=reviewed or subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True).strip():
        raise ValueError('source changed during build')
    binary=repo/'build/linux-gcc-release-ccache/one_combat'
    write(root/'build-receipt.json',{'reviewedSha':reviewed,'command':build_cmd,'returncode':0,
        'seconds':time.time()-build_start,'binarySha256':sha(binary),'logSha256':sha(root/'build.log')})
    shutil.copy2(binary,bundle/'one_combat')
    paths=subprocess.check_output(['git','ls-files','models','selfplay/models'],cwd=repo,text=True).splitlines()
    for rel in paths:
        dst=bundle/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(repo/rel,dst)
    scripts=['tools/heart_rollout_distill.py','tools/heart_record_encoder.py','tools/heart1_leaf_reference.py','tools/run_heart_distill_pilot.py','tools/seed_guard.sh']
    for rel in scripts: shutil.copy2(repo/rel,bundle/Path(rel).name)
    shutil.copy2(repo/study['protocol'],bundle/'PROTOCOL.md')
    shutil.copy2(repo/'docs/experiments/evidence/ooc_sibling_leaf_capture64_20261015/tv_within_x2b.json.pt',bundle/'opus490.pt')
    if sha(student_c)!=STUDENT_C_SHA256:raise ValueError('wrong Arm C native weights')
    shutil.copy2(student_c,bundle/'studentc.bin')
    if sha(bundle/'studentc.bin')!=STUDENT_C_SHA256:raise ValueError('Arm C copy identity mismatch')
    models={p:sha(bundle/p) for p in paths}
    models['studentc.bin']=sha(bundle/'studentc.bin')
    env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'HOME':os.environ['HOME'],
         'OMP_NUM_THREADS':'1','OMP_DYNAMIC':'FALSE','STS_EXECUTABLE_GIT_SHA':reviewed,
         'STS_FAIR':'1','STS_SILVER_SEARCH':'1','STS_SILVER_EXACT_ROOT_BUDGETS':'1',
         'STS_SILVER_ADAPTIVE':'0','STS_SILVER_LEARNED_STOP':'0','STS_SILVER_VNET_LEAF_DIRECT':'0',
         'STS_SILVER_REUSE_CAP_MODE':'allocated','STS_COLLECT_KEYS':'1','STS_STOP_AFTER_ACT':'0',
         'STS_OOC_STRATEGIC_TOK_NN':'selfplay/models/ooc_strategic_tok_final.native',
         'STS_OOC_STRATEGIC_REST':'1','STS_OOC_STRATEGIC_EVENT':'1','STS_OOC_STRATEGIC_SHOP':'1',
         'STS_OOC_STRATEGIC_TREASURE':'1','STS_OOC_STRATEGIC_BOSS_RELIC':'1','STS_OOC_STRATEGIC_MARGIN':'1.0',
         'STS_REST_WIN':'0','STS_OOC_PUBLIC_FUTURES':'8',
         'STS_OOC_MCTS':'1','STS_OOC_MCTS_SIMS':'512','STS_OOC_MCTS_LEAF_COMBATS':'3',
         'STS_OOC_MCTS_LEAF_VALUE':'native','STS_OOC_MCTS_LEAF_POLICY':study['leafPolicy'],'STS_OOC_MCTS_PRIOR':'heart1',
         'STS_OOC_HEART1':'studentc.bin',
         'STS_OOC_MCTS_TREE_RULES':'1','STS_OOC_MCTS_TEMPERATURE':'1','STS_OOC_MCTS_CPUCT':'1.5',
         'STS_OOC_MCTS_WIDEN_K':'4','STS_OOC_MCTS_WIDEN_ALPHA':'0.75','STS_OOC_MCTS_MAX_DEPTH':'32',
         'STS_OOC_MCTS_ROOT_SELECTION':'visits','STS_OOC_MCTS_EARLY_STOP':'1'}
    first=study['sourceStart']
    freeze={'studentPrior':{'name':'Arm C d64 trim','checkpointGitRef':'68fe88be8271fa1f9b515f7a9abcf0fb9755e25f:results/C_d64_trim/student.pt',
                          'checkpointSha256':'53739a4375380001fce0323935c187906b5c1d5efd65691f9d75f2dd8884e020',
                          'nativeSha256':STUDENT_C_SHA256,'exporterSha256':sha(repo/'tools/heart1/export_heart1_weights.py')},
            'reviewedSha':reviewed,'binarySha256':sha(bundle/'one_combat'),'models':models,'environment':env,
            'splits':{'train':list(range(first,first+40)),
                      'validation':list(range(first+40,first+48)),'test':list(range(first+48,first+64))},
            'canarySeeds':study['canarySeeds'],'sourceTimeoutSeconds':study['sourceTimeoutSeconds'],
            'cohortWallSeconds':study['cohortWallSeconds'],
            'workers':3,'repeats':64,'captureEvery':4,'maxLeaves':64,'maxDepth':1,
            'toolHashes':{str(bundle/Path(p).name):sha(bundle/Path(p).name) for p in scripts},
            'protocolSha256':sha(bundle/'PROTOCOL.md'),'runtime':runtime_identity(),
            'buildReceiptSha256':sha(root/'build-receipt.json'),'opus490CheckpointSha256':sha(bundle/'opus490.pt')}
    if arm_c_rollout: freeze['capturePolicyContract']='heart1'
    with (root/'freeze.json').open('x') as f: json.dump(freeze,f,indent=2,sort_keys=True)
    freeze_sha=sha(root/'freeze.json')
    def status(stage,**kw): write(root/'status.json',{'pid':os.getpid(),'stage':stage,'time':time.time(),**kw})
    status('canary')
    def unit(seed,capture=True,tag=None,timeout=None):
        if timeout is None: timeout=study['sourceTimeoutSeconds']
        base=root/(tag or f'seed-{seed}'); receipt=base.with_suffix('.receipt.json')
        if receipt.exists() or list(root.glob(base.name+'.*')): raise ValueError('unit output already exists: '+str(base))
        e=dict(env)
        e.update(STS_OOC_MCTS_TRACE=str(base.with_suffix('.mcts.csv')),
                 STS_OOC_DECISION_TRACE=str(base.with_suffix('.trace.jsonl')))
        if capture:
            e.update(STS_OOC_SIBLING_CAPTURE=str(base.with_suffix('.sib.jsonl')),STS_OOC_SIBLING_EVERY='4',
                     STS_OOC_SIBLING_REPEATS='64',STS_OOC_SIBLING_LONG='0',
                     STS_OOC_SIBLING_MAX_DEPTH='1',STS_OOC_SIBLING_MAX_LEAVES='64')
        cmd=['bash',str(bundle/'seed_guard.sh'),str(bundle/'one_combat'),'bestbench','10000','1','20',str(seed),str(base.with_suffix('.csv'))]
        start=time.time(); result={'seed':seed,'capture':capture,'command':cmd,'environment':e,'started':start}
        with base.with_suffix('.log').open('x') as log:
            with subprocess.Popen(cmd,cwd=bundle,env=e,stdout=log,stderr=subprocess.STDOUT,start_new_session=True) as child:
                try: rc=child.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid,signal.SIGTERM)
                    try: child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid,signal.SIGKILL); child.wait()
                    rc=124
        result.update(returncode=rc,seconds=time.time()-start)
        if rc==0:
            try:
                support_path=base.with_suffix('.mcts.csv.support.jsonl')
                support_rows=[json.loads(line) for line in support_path.open()]
                if len(support_rows)!=1:raise ValueError('one source support receipt required')
                result['studentPriorContract']=student_contract(base.with_suffix('.log').read_text(),support_rows[0],seed,study['leafPolicy'])
            except (ValueError,KeyError,OSError) as error:
                result['contractError']=str(error);result['processReturncode']=rc
                rc=65;result['returncode']=rc
        cap=base.with_suffix('.sib.jsonl')
        if capture and cap.exists(): result['captureSha256']=sha(cap)
        # Receipts expose only completion/custody, not run outcomes or target values.
        with receipt.open('x') as f: json.dump(result,f,indent=2,sort_keys=True)
        if rc!=0: raise RuntimeError(f'unit {seed} failed rc={rc}')
        return base
    c1,c2=study['canarySeeds']
    control=unit(c1,False,'canary-control'); treatment=unit(c1,True,'canary-capture')
    for suffix in ('.trace.jsonl','.mcts.csv.actions.jsonl'):
        a=Path(str(control)+suffix); b=Path(str(treatment)+suffix)
        if not a.exists() or not b.exists() or a.read_bytes()!=b.read_bytes():
            raise ValueError('canary changed decisions/actions: '+suffix)
    second=unit(c2,True,'canary-second')
    def canary_coverage(base,seed):
        _,_,coverage=validate_rows((json.loads(line) for line in base.with_suffix('.sib.jsonl').open()),seed,
                                   freeze.get('capturePolicyContract'))
        return coverage
    cover=[canary_coverage(treatment,c1),canary_coverage(second,c2)]
    canary={'parity':True,'coverage':cover}
    if arm_c_rollout:
        canary['artifacts']={p.name:sha(p) for base in (control,treatment,second)
                             for p in sorted(root.glob(base.name+'.*')) if p.is_file()}
    write(root/'canary.json',canary)
    canary_sha=sha(root/'canary.json')
    if any(not c['groups'] or c['accepted']<.8*c['raw'] for c in cover): raise ValueError('canary coverage/support gate')
    if arm_c_rollout:
        status('awaiting_canary_review')
        deadline=time.monotonic()+1800
        approval=root/'canary-reviewed.json'
        while not approval.exists():
            if time.monotonic()>=deadline: raise RuntimeError('independent canary review timeout; no cohort')
            time.sleep(5)
        approval_sha=verify_canary_approval(root,freeze,freeze_sha,canary,canary_sha)
        with (root/'cohort-started.json').open('x') as f:
            json.dump({'freezeSha256':freeze_sha,'approvalSha256':approval_sha,'time':time.time()},f)
    status('collecting',completed=0); start=time.monotonic(); completed=[]
    allseeds=sum(freeze['splits'].values(),[])
    # Each worker checks the same fixed global deadline before starting its next unit.
    def bounded_unit(seed):
        remaining=study['cohortWallSeconds']-(time.monotonic()-start)
        if remaining<=0: raise RuntimeError('cohort wall cap')
        return unit(seed,timeout=min(study['sourceTimeoutSeconds'],remaining))
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(bounded_unit,s):s for s in allseeds}
        failures=[]
        for future in as_completed(futures):
            seed=futures[future]
            try: future.result(); completed.append(seed)
            except Exception as error: failures.append({'seed':seed,'error':str(error)})
            status('collecting',completed=len(completed),failures=failures)
    if failures or len(completed)!=64: raise RuntimeError('INCOMPLETE cohort; no fitting or holdout opening')
    # Recheck bundle identities once before fitting; no mutable repository dependency remains.
    if sha(root/'freeze.json')!=freeze_sha: raise ValueError('original freeze changed during collection')
    verify_bundle(root,freeze); verify_tools(freeze)
    if sha(bundle/'one_combat')!=freeze['binarySha256']: raise ValueError('frozen binary changed')
    for rel,digest in models.items():
        if sha(bundle/rel)!=digest: raise ValueError('frozen model changed: '+rel)
    manifest={'sources':{}}
    for seed in allseeds:
        base=root/f'seed-{seed}';receipt=base.with_suffix('.receipt.json');capture=base.with_suffix('.sib.jsonl')
        r=json.loads(receipt.read_text());digest=sha(capture)
        if r['returncode']!=0 or r['captureSha256']!=digest:raise ValueError('source receipt invalid before corpus freeze')
        manifest['sources'][str(seed)]={'receiptSha256':sha(receipt),'captureSha256':digest}
    with (root/'corpus-manifest.json').open('x') as f:json.dump(manifest,f,indent=2,sort_keys=True)
    status('fitting'); out=root/'fit'
    trainer=[sys.executable,str(bundle/'heart_rollout_distill.py')]
    with (root/'fit.log').open('x') as log:
        r=subprocess.run(trainer+['fit',str(root),str(out)],stdout=log,stderr=subprocess.STDOUT,timeout=1200)
    if r.returncode: raise RuntimeError('fit failed; preserve data and stop')
    if not (out/'selection.json').exists(): status('complete',verdict='INSUFFICIENT'); return
    status('testing')
    with (root/'test.log').open('x') as log:
        r=subprocess.run(trainer+['test',str(root),str(out)],stdout=log,stderr=subprocess.STDOUT,timeout=600)
    if r.returncode: raise RuntimeError('one-shot TEST failed; do not retry')
    result=json.loads((out/'test-result.json').read_text()); status('complete',verdict=result['verdict'])


if __name__=='__main__':
    if len(sys.argv) not in (5,6) or (len(sys.argv)==6 and sys.argv[5]!='--arm-c-rollout'):
        raise SystemExit(__doc__)
    repo,root,reviewed,student_c=Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve(),sys.argv[3],Path(sys.argv[4]).resolve()
    already_existed=root.exists()
    try: run(repo,root,reviewed,student_c,arm_c_rollout=len(sys.argv)==6)
    except BaseException as error:
        if root.exists() and not already_existed: write(root/'failure.json',{'error':str(error),'time':time.time(),'pid':os.getpid()})
        raise
