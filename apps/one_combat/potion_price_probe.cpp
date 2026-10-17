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

#include "one_combat/driver_shared.h"
#include "one_combat/ooc_policy.h"

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
};

std::string heldPotions(const GameContext &gc) {
    std::string s;
    for (int i = 0; i < gc.potionCapacity; ++i) {
        if (gc.potions[i] == Potion::EMPTY_POTION_SLOT) continue;
        if (!s.empty()) s += '|';
        s += potionEnumNames[static_cast<int>(gc.potions[i])];
    }
    return s;
}

std::vector<PriceProbeVariant> priceVariants(const GameContext &base, int hpDelta) {
    std::vector<PriceProbeVariant> v;
    v.push_back({"base", detachedCounterfactualCopy(base)});
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
    if (hpDelta > 0 && base.curHp > hpDelta) {
        GameContext copy = detachedCounterfactualCopy(base);
        copy.curHp -= hpDelta;
        v.push_back({"hp:-" + std::to_string(hpDelta), std::move(copy)});
    }
    return v;
}

} // namespace

void potionPriceProbe(int nSeeds, std::uint64_t seedStart, int sims, int asc,
                      const std::string &outFile, int statesPerRun, int fightsAhead,
                      int hpDelta) {
    if (nSeeds <= 0 || sims <= 0 || statesPerRun <= 0 || fightsAhead <= 0)
        throw std::runtime_error("potionpriceprobe: invalid arguments");
    std::ofstream out(outFile);
    if (!out) throw std::runtime_error("potionpriceprobe: cannot open " + outFile);
    out << "seed,battleIdx,act,floor,curHp,maxHp,potionCount,potionCapacity,potions,"
           "variant,contSeed,won,floorValue,hp,bootstrapped,survived,altWon,altFloor,valid,"
           "silverSimulations,cpuMs\n";
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
            if (gc.potionCount <= 0 || !t_curPath) return;
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
            for (auto &variant : priceVariants(st.gc, hpDelta)) {
                one_combat::restoreOocPolicyThreadState(st.policy);
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
                    << cost.cpuMs << '\n';
            }
            out.flush();
        }
    }
}
