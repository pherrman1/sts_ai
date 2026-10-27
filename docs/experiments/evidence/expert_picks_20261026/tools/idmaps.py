"""Game-id string -> engine enum ordinal, parsed from the repo headers."""
import re, json, sys, os
REPO = "/home/user/sts_ai/include/constants"

def enum_ordinals(path, name):
    src = open(os.path.join(REPO, path)).read()
    body = re.search(r"enum class %s\s*:\s*[\w:]+\s*\{(.*?)\};" % name, src, re.S).group(1)
    body = re.sub(r"//[^\n]*", "", body)
    out, v = {}, -1
    for tok in body.split(","):
        tok = tok.strip()
        if not tok: continue
        if "=" in tok:
            k, val = [t.strip() for t in tok.split("=")]; v = int(val)
        else:
            k = tok; v += 1
        out[k] = v
    return out

def save_names(name):
    src = open(os.path.join(REPO, "SaveFileMappings.h")).read()
    body = re.search(r"NLOHMANN_JSON_SERIALIZE_ENUM\(%s,\s*\{(.*?)\}\)" % name, src, re.S).group(1)
    return {m[1]: m[0] for m in re.findall(r'\{%s::(\w+),\s*"([^"]*)"\}' % name, body)}

def build():
    rel = enum_ordinals("Relics.h", "RelicId"); pot = enum_ordinals("Potions.h", "Potion")
    card_src = open(os.path.join(REPO, "Cards.h")).read()
    ids = re.findall(r'"([^"]*)"', re.search(r"cardStringIds\[\]\s*=\s*\{(.*?)\};", card_src, re.S).group(1))
    cards = {s: i for i, s in enumerate(ids)}
    relics = {s: rel[k] for s, k in save_names("RelicId").items()}
    potions = {s: pot[k] for s, k in save_names("Potion").items()}
    return {"cards": cards, "relics": relics, "potions": potions}

if __name__ == "__main__":
    m = build(); json.dump(m, open(sys.argv[1], "w"), indent=0)
    print({k: len(v) for k, v in m.items()}, m["relics"]["Burning Blood"], m["cards"]["Strike_R"], m["potions"]["Fire Potion"])
