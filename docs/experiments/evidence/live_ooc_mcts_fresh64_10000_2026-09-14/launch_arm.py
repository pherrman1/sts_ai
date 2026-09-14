"""Render frozen manifest with real exact-checkout cwd, using the native guard launcher.

No game invocation escapes gcp_benchmark.remote_run. Its freshness and active
process checks are retained. GNU env changes cwd only after seed_guard validates
the designated host/root and scans the full argv for the bestbench seed budget.
"""
import importlib.util
import json
from pathlib import Path
import sys

repo=Path(__file__).resolve().parents[4]
spec=importlib.util.spec_from_file_location('gcp_benchmark',repo/'tools/agent/gcp_benchmark.py')
gcp=importlib.util.module_from_spec(spec); spec.loader.exec_module(gcp)
args=gcp.parser().parse_args(['run-manifest',*sys.argv[1:]])
gcp.manifest_check(args)
manifest=gcp.load_run_manifest(args.manifest)
command,log,fresh=gcp.manifest_arm(manifest,args.arm)
# Manifest paths remain root-relative for native validation; executable cwd and
# game result path are absolute when running from the exact linked checkout.
command=[args.remote_root+'/'+token if token in (manifest['binary']['remote_path'],next(a['results'] for a in manifest['arms'] if a['name']==args.arm)) else token for token in command]
command[1:1]=['--chdir='+args.remote_root+'/'+manifest['checkout']]
args.command=command; args.log=log
args.fresh_paths=[*fresh,next(a['results'] for a in manifest['arms'] if a['name']==args.arm)+'.mcts.csv',next(a['results'] for a in manifest['arms'] if a['name']==args.arm)+'.mcts.csv.support.jsonl']
receipt=dict(manifest=str(args.manifest),arm=args.arm,cwd=args.remote_root+'/'+manifest['checkout'],command=command,log=log,fresh_paths=args.fresh_paths,guard_only=args.guard_only)
print(json.dumps(receipt,indent=2),flush=True)
raise SystemExit(gcp.remote_run(args))
