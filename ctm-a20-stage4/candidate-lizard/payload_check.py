import sys,hashlib; from tools import ctm_candidate as cc
r={}
for p in sys.argv[1:]:
    h,payload=cc.read(p); r[p]=hashlib.sha256(payload).hexdigest(); print(f"payload_sha256 {r[p]} {p}")
v=len(set(r.values()))==1; print("PAYLOAD_EQUAL" if v else "PAYLOAD_DIFFERS"); sys.exit(0 if v else 1)
