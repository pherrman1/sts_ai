"""Names for CardId / RelicId / Potion / MonsterId / MonsterEncounter enum indices from sts_lightspeed headers.
usage: enum_names.py REPO_ROOT OUT.json"""
import re, sys, json
root, out = sys.argv[1:3]
def parse(path, enum):
    txt = open(path).read()
    m = re.search(r"enum class " + enum + r"\b[^{]*\{(.*?)\};", txt, re.S)
    body = re.sub(r"//[^\n]*", "", m.group(1)); body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    names, cur = [], 0
    for it in [x.strip() for x in body.split(",") if x.strip()]:
        if "=" in it:
            nmx, v = [y.strip() for y in it.split("=", 1)]
            cur = int(v, 0)
        else:
            nmx = it
        while len(names) < cur: names.append(None)
        names.append(nmx); cur += 1
    return names
res = {"card": parse(f"{root}/include/constants/Cards.h", "CardId"),
       "relic": parse(f"{root}/include/constants/Relics.h", "RelicId"),
       "potion": parse(f"{root}/include/constants/Potions.h", "Potion"),
       "monster": parse(f"{root}/include/constants/MonsterIds.h", "MonsterId"),
       "encounter": parse(f"{root}/include/constants/MonsterEncounters.h", "MonsterEncounter")}
json.dump(res, open(out, "w"))
print({k: len(v) for k, v in res.items()}, res["card"][:3], res["relic"][:3], res["potion"][:3])
