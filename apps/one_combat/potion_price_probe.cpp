// Paired-continuation resource price probe (potionpriceprobe).
//
// Research only. Plays a source run with the deployed continuation policy and
// samples battle-start states that hold potions. From each sampled state it
// continues copies that differ in one resource: unchanged, one held potion of
// each distinct type removed, and HP lowered by a fixed amount. Every copy
// shares the GameContext RNG, the agent seed and the OOC policy thread state
// (common random numbers), plays the next K fights, and is valued at the
// following battle by the process win/floor models (bootstrap), or by its
// terminal outcome. The difference to the unchanged copy is the price of that
// resource under the current policy; the HP copy calibrates the units.
//
// Optional (SAMPLE=all, EXTRA): sample every battle-start state, add copies with
// gold or max HP lowered, and leaf arms (leaf:concave=K) that differ from base only
// in Silver's victory leaf during the continuation; ooc=heart1 lets the
// STS_OOC_HEART1 student take the out-of-combat steps it encodes; addpot:NAME adds
// a copy holding one more potion NAME (only when a slot is free and no Sozu).

#include "one_combat/driver_shared.h"
#include "one_combat/ooc_policy.h"
#include "one_combat/heart1_policy.h"
#include "one_combat/run_driver.h"
#include "sim/search/NativeSilverBackend.h"

#include <cmath>
#include <optional>
#include <sstream>

namespace {

struct PriceProbeState {
    GameContext gc;
    PathHistory path;
    OocPolicyThreadState policy;
    int battleIdx = 0;
};

struct PriceProbeVariant {
    std::string name;
    GameContext gc;
    std::optional<double> concaveHpK;   // leaf arm: Silver's concave-HP leaf for this copy
};

// EXTRA tokens (comma list): leaf:concave=K, gold:-N, maxhp:-N, ooc=heart1, addpot:NAME.
struct PriceProbeExtra {
    std::vector<double> concaveK;
    std::vector<Potion> addPotions;
    int goldDelta = 0;
    int maxHpDelta = 0;
    bool oocHeart1 = false;
};

PriceProbeExtra parseExtra(const std::string &spec) {
    PriceProbeExtra e;
    std::size_t pos = 0;
    while (pos <= spec.size()) {
        const std::size_t comma = std::min(spec.find(',', pos), spec.size());
        const std::string item = spec.substr(pos, comma - pos);
        pos = comma + 1;
        if (item.empty()) continue;
        auto number = [&](std::size_t from) {
            const std::string text = item.substr(from);
            char *end = nullptr;
            const double v = std::strtod(text.c_str(), &end);
            if (text.empty() || *end != '\0' || !std::isfinite(v) || v <= 0)
                throw std::runtime_error("potionpriceprobe: bad EXTRA item " + item);
            return v;
        };
        if (item.rfind("leaf:concave=", 0) == 0) e.concaveK.push_back(number(13));
        else if (item.rfind("gold:-", 0) == 0) e.goldDelta = static_cast<int>(number(6));
        else if (item.rfind("maxhp:-", 0) == 0) e.maxHpDelta = static_cast<int>(number(7));
        else if (item == "ooc=heart1") e.oocHeart1 = true;
        else if (item.rfind("addpot:", 0) == 0) {
            const std::string name = item.substr(7);
            int id = 2;  // skip INVALID and EMPTY_POTION_SLOT
            while (id < static_cast<int>(std::size(potionEnumNames)) && name != potionEnumNames[id]) ++id;
            if (id >= static_cast<int>(std::size(potionEnumNames)))
                throw std::runtime_error("potionpriceprobe: unknown potion in EXTRA item " + item);
            e.addPotions.push_back(static_cast<Potion>(id));
        }
        else throw std::runtime_error("potionpriceprobe: unknown EXTRA item " + item);
    }
    return e;
}

std::string formatK(double k) {
    std::ostringstream os;
    os << k;
    return os.str();
}

std::string heldPotions(const GameContext &gc) {
    std::string s;
    for (int i = 0; i < gc.potionCapacity; ++i) {
        if (gc.potions[i] == Potion::EMPTY_POTION_SLOT) continue;
        if (!s.empty()) s += '|';
        s += potionEnumNames[static_cast<int>(gc.potions[i])];
    }
    return s;
}

std::vector<PriceProbeVariant> priceVariants(const GameContext &base, int hpDelta, const PriceProbeExtra &extra) {
    std::vector<PriceProbeVariant> v;
    v.push_back({"base", detachedCounterfactualCopy(base)});
    for (const double k : extra.concaveK)
        v.push_back({"leaf:concave=" + formatK(k), detachedCounterfactualCopy(base), k});
    std::vector<Potion> seen;
    for (int i = 0; i < base.potionCapacity; ++i) {
        const Potion p = base.potions[i];
        if (p == Potion::EMPTY_POTION_SLOT) continue;
        if (std::find(seen.begin(), seen.end(), p) != seen.end()) continue;
        seen.push_back(p);
        GameContext copy = detachedCounterfactualCopy(base);
        copy.discardPotionAtIdx(i);
        v.push_back({std::string("pot:") + potionEnumNames[static_cast<int>(p)], std::move(copy)});
    }
    for (const Potion p : extra.addPotions) {
        if (base.potionCount >= base.potionCapacity || base.relics.has(RelicId::SOZU)) continue;
        GameContext copy = detachedCounterfactualCopy(base);
        copy.obtainPotion(p);
        v.push_back({std::string("addpot:") + potionEnumNames[static_cast<int>(p)], std::move(copy)});
    }
    if (hpDelta > 0 && base.curHp > hpDelta) {
        GameContext copy = detachedCounterfactualCopy(base);
        copy.curHp -= hpDelta;
        v.push_back({"hp:-" + std::to_string(hpDelta), std::move(copy)});
    }
    if (extra.goldDelta > 0 && base.gold >= extra.goldDelta) {
        GameContext copy = detachedCounterfactualCopy(base);
        copy.gold -= extra.goldDelta;
        v.push_back({"gold:-" + std::to_string(extra.goldDelta), std::move(copy)});
    }
    if (extra.maxHpDelta > 0 && base.maxHp > extra.maxHpDelta + 1) {
        GameContext copy = detachedCounterfactualCopy(base);
        copy.maxHp -= extra.maxHpDelta;
        copy.curHp = std::min(copy.curHp, copy.maxHp);
        v.push_back({"maxhp:-" + std::to_string(extra.maxHpDelta), std::move(copy)});
    }
    return v;
}

} // namespace

void potionPriceProbe(int nSeeds, std::uint64_t seedStart, int sims, int asc,
                      const std::string &outFile, int statesPerRun, int fightsAhead,
                      int hpDelta, bool allStates, const std::string &extraSpec) {
    const PriceProbeExtra extra = parseExtra(extraSpec);
    if (extra.oocHeart1 && !one_combat::heart1::enabled())
        throw std::runtime_error("potionpriceprobe: ooc=heart1 needs STS_OOC_HEART1");
    struct Heart1Scope {
        bool saved = t_counterfactualHeart1;
        explicit Heart1Scope(bool on) { t_counterfactualHeart1 = on; }
        ~Heart1Scope() { t_counterfactualHeart1 = saved; }
    } heart1Scope(extra.oocHeart1);
    if (nSeeds <= 0 || sims <= 0 || statesPerRun <= 0 || fightsAhead <= 0)
        throw std::runtime_error("potionpriceprobe: invalid arguments");
    std::ofstream out(outFile);
    if (!out) throw std::runtime_error("potionpriceprobe: cannot open " + outFile);
    out << "seed,battleIdx,act,floor,curHp,maxHp,potionCount,potionCapacity,potions,"
           "variant,contSeed,won,floorValue,hp,bootstrapped,survived,altWon,altFloor,valid,"
           "silverSimulations,cpuMs,gold\n";
    for (int s = 0; s < nSeeds; ++s) {
        const std::uint64_t seed = seedStart + static_cast<std::uint64_t>(s);
        trainingRunStart();
        vDisconnect();
        one_combat::resetPathPolicyState();
        // Source run: the same continuation policy the branches use. The
        // observer runs at every battle after the first and only copies state.
        std::vector<PriceProbeState> sampled;
        std::default_random_engine reservoir(seed * 2862933555777941757ULL + 31);
        int eligible = 0;
        const OocPrefixObserver observer = [&](const GameContext &gc, int fights,
                                               const OocContinuationCost &) {
            if ((!allStates && gc.potionCount <= 0) || !t_curPath) return;
            ++eligible;
            PriceProbeState st{detachedCounterfactualCopy(gc), *t_curPath,
                               one_combat::captureOocPolicyThreadState(), fights};
            if ((int)sampled.size() < statesPerRun) { sampled.push_back(std::move(st)); return; }
            const int j = std::uniform_int_distribution<int>(0, eligible - 1)(reservoir);
            if (j < statesPerRun) sampled[j] = std::move(st);
        };
        const OocCounterfactualResult source = finishOocCounterfactual(
            GameContext(CharacterClass::IRONCLAD, seed, asc), sims, seed, PathHistory{},
            -1, false, nullptr, 0, nullptr, false, &observer);
        std::sort(sampled.begin(), sampled.end(),
                  [](const auto &a, const auto &b) { return a.battleIdx < b.battleIdx; });
        std::cout << "[potionpriceprobe] seed=" << seed << " sourceFloor=" << source.floor
                  << " sourceWon=" << source.won << " eligible=" << eligible
                  << " sampled=" << sampled.size() << std::endl;
        for (const auto &st : sampled) {
            std::uint64_t contSeed = seed ^ ((std::uint64_t)(st.battleIdx + 1) * 0x9e3779b97f4a7c15ULL);
            if (!contSeed) contSeed = 1;
            for (auto &variant : priceVariants(st.gc, hpDelta, extra)) {
                one_combat::restoreOocPolicyThreadState(st.policy);
                struct LeafScope {
                    explicit LeafScope(std::optional<double> k) {
                        if (k) search::g_nativeSilverConcaveHpLeafOverride = *k;
                    }
                    ~LeafScope() { search::g_nativeSilverConcaveHpLeafOverride.reset(); }
                } leafScope(variant.concaveHpK);
                OocContinuationCost cost;
                const OocCounterfactualResult r = finishOocCounterfactual(
                    std::move(variant.gc), sims, contSeed, st.path, fightsAhead, true,
                    nullptr, 0, nullptr, false, nullptr, &cost);
                out << seed << ',' << st.battleIdx << ',' << st.gc.act << ',' << st.gc.floorNum << ','
                    << st.gc.curHp << ',' << st.gc.maxHp << ',' << st.gc.potionCount << ','
                    << st.gc.potionCapacity << ',' << heldPotions(st.gc) << ',' << variant.name << ','
                    << contSeed << ',' << r.won << ',' << r.floor << ',' << r.hp << ','
                    << r.bootstrapped << ',' << (r.survivedH ? 1 : 0) << ',' << r.altWon << ','
                    << r.altFloor << ',' << (r.valid ? 1 : 0) << ',' << cost.silverSimulations << ','
                    << cost.cpuMs << ',' << st.gc.gold << '\n';
            }
            out.flush();
        }
    }
}
