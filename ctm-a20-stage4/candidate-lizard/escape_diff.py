"""Step 4 diagnostic: tensor payload of FAST2L vs FAST1-escape (sha256 of bytes after header; per-tensor max abs diff)."""
import sys,hashlib,numpy as np; from tools import ctm_candidate as cc, ctm_escape as ce
a,b=sys.argv[1],sys.argv[2]
pa,pb=cc.read(a)[1],cc.read(b)[1]
ha,hb=hashlib.sha256(pa).hexdigest(),hashlib.sha256(pb).hexdigest()
print(f"payload_sha256 {ha} {a}\npayload_sha256 {hb} {b}")
print("PAYLOAD_EQUAL" if ha==hb else "PAYLOAD_DIFFERS")
ma,ta=ce.read_artifact(a); mb,tb=ce.read_artifact(b)
for n in sorted(set(ta)|set(tb)):
    if n not in ta or n not in tb: print(f"tensor {n} only_in={'A' if n in ta else 'B'}"); continue
    if ta[n].shape!=tb[n].shape: print(f"tensor {n} shape {ta[n].shape} vs {tb[n].shape}"); continue
    d=float(np.max(np.abs(ta[n]-tb[n]))) if ta[n].size else 0.0
    if d>0 or n.startswith('escape'): print(f"tensor {n} shape {list(ta[n].shape)} max_abs_diff {d:.9g}")
