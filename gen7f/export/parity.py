import json, struct, sys, numpy as np
sys.path.insert(0, "/home/philippherrmann/Documents/sts/gen7-gpu/data"); import arch_dev as A, silver_az_mlp as M
f = open("roots.bin", "rb"); R = struct.unpack("i", f.read(4))[0]; big = []; enc_hi = []
for r in range(R):
    n = struct.unpack("i", f.read(4))[0]; s = np.frombuffer(f.read(4 * M.S), np.float32); f.read(4 * n * M.A + 4 * n)
    hi = any(s[c] > 127 for c in A.INTENT_COLS); big += [hi] * n; enc_hi += [s[1] > 127] * n
big = np.array(big); out = {}
for m in ("g7f_E", "g6_E"):
    t = np.loadtxt(f"combat_policy_mlp_{m}.txt.torch_logits"); nat = np.loadtxt(f"native_{m}.txt"); d = np.abs(t - nat)
    rep = json.loads([l for l in open(f"check_{m}.out") if l.startswith("{")][-1])
    out[m] = {"header": open(f"combat_policy_mlp_{m}.txt").readline().strip(), "edges": len(d),
              "max_abs_diff_vs_torch": float(d.max()), "mean_abs_diff": float(d.mean()),
              "edges_with_incoming_dmg_gt127": int(big.sum()), "max_abs_diff_on_those": float(d[big].max()) if big.any() else None,
              "native_us_per_root_min3": rep["mlpUsPerRoot"], "pass_3e-6": bool(d.max() < 3e-6)}
out["roots"] = {"source": "pack-g7f.npz fold 4 (r_seed%5==4), 4000 roots, default_rng(123) (prep_roots.py, pack path changed)", "encounter_gt127_edges": int(sum(enc_hi))}
json.dump(out, open("parity-native-g7f.json", "w"), indent=1); print(json.dumps(out, indent=1))
