#pragma once

#include <cstdint>
#include <optional>

#include <nlohmann/json.hpp>

#include "game/GameContext.h"

namespace one_combat {

// STS_A4_PERTURB=INDEX:SALT:K:SPECSEED (research, V_A4 entry perturbations; unset = off). runFullRunOOC plays the
// game unchanged up to its real OOC decision INDEX, which must be in Act 4, and forks K children there, one after
// the other. Each child redraws the hidden future with resampleCounterfactualFuture seeded by SALT (0 keeps the game's
// own future), so all K children share one future, then applies its perturbation and plays to the end. Child 0 is the
// unchanged control; child k > 0 applies one realistic change drawn from (SPECSEED, k). heartoutcomegen writes child
// k to OUT.pKK.jsonl (+ .ctm.jsonl; the header gains a4Perturb, the child's perturbation) and the parent appends an a4_perturb row
// naming every child to OUT.jsonl.
struct A4PerturbSpec {
    std::uint64_t index;
    std::uint64_t salt;
    int children;
    std::uint64_t specSeed;
};
std::optional<A4PerturbSpec> parseA4Perturb(const char *value);
const std::optional<A4PerturbSpec> &a4PerturbSpec();   // STS_A4_PERTURB, read once

// Child 0: no change, {"op":"none"}. Child k > 0: one operator drawn uniformly from those that apply to gc (HP,
// max HP, gold, card add/remove, upgrade/un-upgrade, relic add/remove/swap, relic counter, potion add/remove), with
// its parameters drawn from (specSeed, k). Changes only the operator's own fields (relic add also takes the relic out
// of the relic pools) and keeps the deck and relic caches consistent; touches no game Random. Returns what changed.
nlohmann::json applyA4Perturbation(sts::GameContext &gc, std::uint64_t specSeed, int child);

int a4PerturbSelfTest();

// The range of an out-of-combat relic counter (RelicInstance::data in 0..limit-1) as the relic_counter
// operator uses it; 0 for relics without such a counter. fightendpairgen's ctr: copies share it.
int a4CounterLimit(sts::RelicId r);

}  // namespace one_combat
