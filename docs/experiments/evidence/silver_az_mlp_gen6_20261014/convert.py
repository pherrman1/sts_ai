# Convert an arch.py checkpoint (no tower/h3/dot/enc) to the tools/silver_az_mlp.py export format.
import sys, torch
c = torch.load(sys.argv[1], weights_only=False)
a = c["args"]; assert not (a["tower"] or a["h3"] or a["dot"] or a.get("enc_emb")), a
st = {("l2." + k[len("hidden.0."):] if k.startswith("hidden.0.") else k): v for k, v in c["state"].items()}
torch.save({"state": st, "scales": c["scales"], "h1": a["h1"], "h2": a["h2"]}, sys.argv[2])
print("ok", sorted(st))
