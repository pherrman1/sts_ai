import sys, json, argparse, numpy as np, torch
sys.path.insert(0, "/root/arch"); sys.path.insert(0, "/home/user/sts_ai/tools")
import silver_az_mlp as M, arch
torch.set_num_threads(4)
data = M.Data("/root/arch/pack-g4.npz")
arch.ENC = arch.encounter_ids(data); arch.MON = arch.monster_ids(data)
scales = data.fit_scales(data.roots(M.TRAIN))
t_orig = data.roots((M.TEST,), data.tags[0]); t_all = data.roots((M.TEST,))
res = {}
for n in sys.argv[1:]:
    ck = torch.load(f"runs/{n}/model.pt", weights_only=False)
    a = argparse.Namespace(**ck["args"]); net = arch.Net(a); net.load_state_dict(ck["state"])
    res[n] = {"fold4_orig": arch.evaluate(net, data, t_orig, scales), "fold4_all": arch.evaluate(net, data, t_all, scales)}
    print(n, json.dumps(res[n]), flush=True)
json.dump(res, open("fold4.json", "w"), indent=1)
