import os, sys, time, urllib.request
ids = [l.split() for l in open(sys.argv[1]) if l.split()[2] == "ironclad"]
for prof, rid, *_ in ids:
    path = f"raw/{prof}_{rid}.json"
    if os.path.exists(path): continue
    for attempt in range(4):
        try:
            data = urllib.request.urlopen(f"https://baalorlord.tv/runs/{rid}/raw", timeout=60).read()
            open(path, "wb").write(data); break
        except Exception as e:
            print(rid, e, flush=True); time.sleep(2 ** attempt)
    time.sleep(0.2)
print("done")
