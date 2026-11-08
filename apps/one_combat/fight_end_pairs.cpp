// Paired fight-end continuations (fightendpairgen), research only.
//
// Plays a source run with the continuation policy finishOocCounterfactual plays
// and reservoir-samples won fights at the moment they end: the REWARDS screen,
// before any reward is taken (the state Silver's victory leaf values). Each
// sampled fight end is forked into a base copy plus single-change copies (HP,
// one held potion, max HP, gold, a curse, a relic counter). Every copy is a
// detachedCounterfactualCopy, restores the same OOC policy thread state and
// plays on the same continuation seed (common random numbers) to the run end.
// One JSONL row per copy: the outcome, the heart1 public record, the plain
// state §732's features read, and Silver's victory-leaf terms of the copy.
// Fight luck (luck=R, research, default off): at the start of every source fight, R detached copies of the state
// play only that fight on fresh battle and carried streams (fightreplay's redraw) with the fight's own budget; one
// "luck" row per fight carries the real and the replayed fight ends, the per-fight luck u = y_real - y_replay of a
// luck regression. luck_identity=N replays the fights of the first N source seeds once more unchanged (replicate
// 0), which must reproduce the real fight. The replays never touch the run: own copy, own agent, the run's health
// counters and battle-exit hooks restored, so source and fork rows equal those of the same call without luck.
// Reward luck (rewards=1, research, default off): the source row lists the potion roll of every won source fight
// whose reward rolls one (normal, elite, act 1-2 boss): the chance at the roll (40 + potionChance at the fight's
// start, clamped to 0-100; 100 with White Beast Statue), whether a potion dropped and which. The roll's chance is known, so
// dropped - chance is a luck draw without a replay. Logging only reads the state.
// See docs/knowledge-base/research/fight-end-pairs.md.

#include "one_combat/driver_shared.h"
#include "one_combat/heart1_policy.h"
#include "one_combat/ooc_policy.h"
#include "one_combat/run_driver.h"
#include "one_combat/a4_perturb.h"
#include "one_combat/ooc_mcts_adapter.h"
#include "sim/search/NativeSilverBackend.h"
#include "sim/search/SimHealth.h"

#include <cmath>
#include <ctime>
#include <optional>
#include <random>
#include <sstream>
#include <unistd.h>

// Hook for inputs that are not on main (LONG_B's obs.v2.* lives on its branch):
// when set, its value is written as "obsV2" in every copy row. Unset on main.
std::function<nlohmann::json(const GameContext &)> g_fightEndPairsExtraObservation;

namespace {

// ------------------------------------------------------------------ options

struct FightEndOptions {
    int forksPerRun = 4;             // n=: reservoir size (per stratum when stratified); 0 = no forks
    std::vector<std::string> rooms{"NORMAL", "ELITE", "BOSS"};   // rooms=A+B
    std::vector<int> acts{1, 2, 3, 4};                            // acts=1+2
    std::string strata = "none";     // strata=none|room|act|room_act
    int horizon = -1;                // horizon=end|N (fights per copy; N is for tests)
    int sourceFights = -1;           // source_fights=end|N (tests only)
    bool oocHeart1 = false;          // ooc=heart1: as potionpriceprobe's EXTRA
    bool oocPpo = false;             // ooc=ppo: the STS_OOC_HEART1_PPO net first, as the PPO runner's chain
    int luck = 0;                    // luck=R (0-8): R fresh replays of every source fight; 0 = off
    int luckIdentity = 0;            // luck_identity=N: the first N source seeds also replay every fight unchanged
    bool rewards = false;            // rewards=1: the source row lists every combat reward's potion roll
};

std::vector<std::string> splitOn(const std::string &s, char sep) {
    std::vector<std::string> out;
    std::size_t at = 0;
    while (at <= s.size()) {
        const std::size_t next = std::min(s.find(sep, at), s.size());
        out.push_back(s.substr(at, next - at));
        at = next + 1;
    }
    return out;
}

int parsePositive(const std::string &text, const std::string &what) {
    if (text.empty() || text.find_first_not_of("0123456789") != std::string::npos || text.size() > 6
            || std::stoi(text) <= 0)
        throw std::runtime_error("fightendpairgen: bad " + what + " " + text);
    return std::stoi(text);
}

int parseCount(const std::string &text, const std::string &what, int maxValue) {
    if (text.empty() || text.find_first_not_of("0123456789") != std::string::npos || text.size() > 6
            || std::stoi(text) > maxValue)
        throw std::runtime_error("fightendpairgen: bad " + what + " " + text);
    return std::stoi(text);
}

FightEndOptions parseOptions(const std::string &spec) {
    FightEndOptions o;
    if (spec.empty() || spec == "-") return o;
    for (const auto &item : splitOn(spec, ',')) {
        if (item.empty()) continue;
        const auto eq = item.find('=');
        if (eq == std::string::npos) throw std::runtime_error("fightendpairgen: bad option " + item);
        const std::string key = item.substr(0, eq), value = item.substr(eq + 1);
        if (key == "n") o.forksPerRun = parseCount(value, "n", 999999);
        else if (key == "rooms") {
            o.rooms = splitOn(value, '+');
            for (const auto &r : o.rooms)
                if (r != "NORMAL" && r != "ELITE" && r != "BOSS" && r != "OTHER")
                    throw std::runtime_error("fightendpairgen: rooms are NORMAL, ELITE, BOSS, OTHER; got " + r);
        } else if (key == "acts") {
            o.acts.clear();
            for (const auto &a : splitOn(value, '+')) {
                const int act = parsePositive(a, "act");
                if (act > 4) throw std::runtime_error("fightendpairgen: acts are 1-4");
                o.acts.push_back(act);
            }
        } else if (key == "strata") {
            if (value != "none" && value != "room" && value != "act" && value != "room_act")
                throw std::runtime_error("fightendpairgen: strata is none, room, act or room_act");
            o.strata = value;
        } else if (key == "horizon") o.horizon = value == "end" ? -1 : parsePositive(value, "horizon");
        else if (key == "source_fights") o.sourceFights = value == "end" ? -1 : parsePositive(value, "source_fights");
        else if (key == "ooc") {
            if (value != "heart1" && value != "ppo")
                throw std::runtime_error("fightendpairgen: ooc is heart1 or ppo");
            o.oocHeart1 = value == "heart1";
            o.oocPpo = value == "ppo";
        } else if (key == "luck") o.luck = parseCount(value, "luck", 8);
        else if (key == "luck_identity") o.luckIdentity = parseCount(value, "luck_identity", 999999);
        else if (key == "rewards") o.rewards = parseCount(value, "rewards", 1) == 1;
        else throw std::runtime_error("fightendpairgen: unknown option " + key);
    }
    return o;
}

nlohmann::json optionsJson(const FightEndOptions &o) {
    return {{"n", o.forksPerRun}, {"rooms", o.rooms}, {"acts", o.acts}, {"strata", o.strata},
            {"horizon", o.horizon < 0 ? nlohmann::json("end") : nlohmann::json(o.horizon)},
            {"source_fights", o.sourceFights < 0 ? nlohmann::json("end") : nlohmann::json(o.sourceFights)},
            {"ooc", o.oocPpo ? "ppo" : o.oocHeart1 ? "heart1" : "deployed"}, {"luck", o.luck},
            {"luck_identity", o.luckIdentity}, {"rewards", o.rewards ? 1 : 0}};
}

// ----------------------------------------------------------------- variants

// One change token. kind: noop, hp, pot, maxhp, gold, curse, ctr.
struct ChangeToken {
    std::string kind;
    int amount = 0;                         // hp/maxhp/gold: the amount lowered; ctr: the signed shift
    Potion potion = Potion::INVALID;        // pot:NAME (INVALID = every distinct held type, "pot:*")
    CardId curse = CardId::INVALID;
    RelicId relic = RelicId::INVALID;       // ctr:RELIC (INVALID = every held counter relic, "ctr:*")
};

constexpr const char *kDefaultVariants = "hp:-3,hp:-8,hp:-15,pot:*,maxhp:-5,gold:-50";

template <std::size_t N>
int enumIndex(const char *const (&names)[N], const std::string &name, int from = 0) {
    for (int i = from; i < static_cast<int>(N); ++i)
        if (name == names[i]) return i;
    return -1;
}

std::vector<ChangeToken> parseVariants(const std::string &specIn) {
    const std::string spec = specIn.empty() || specIn == "default" ? kDefaultVariants : specIn;
    std::vector<ChangeToken> out;
    if (spec == "-") return out;
    for (const auto &item : splitOn(spec, ',')) {
        if (item.empty()) continue;
        const auto parts = splitOn(item, ':');
        const auto bad = [&] { return std::runtime_error("fightendpairgen: bad variant " + item); };
        const auto negative = [&](const std::string &t) {
            if (t.size() < 2 || t[0] != '-') throw bad();
            return parsePositive(t.substr(1), "amount in " + item);
        };
        ChangeToken c;
        c.kind = parts[0];
        if (c.kind == "noop" && parts.size() == 1) {
        } else if ((c.kind == "hp" || c.kind == "maxhp" || c.kind == "gold") && parts.size() == 2) {
            c.amount = negative(parts[1]);
        } else if (c.kind == "pot" && parts.size() == 2) {
            if (parts[1] != "*") {
                const int id = enumIndex(potionEnumNames, parts[1], 2);
                if (id < 0) throw bad();
                c.potion = static_cast<Potion>(id);
            }
        } else if (c.kind == "curse" && parts.size() == 2) {
            const int id = enumIndex(cardEnumStrings, parts[1], 1);
            if (id < 0 || Card(static_cast<CardId>(id)).getType() != CardType::CURSE) throw bad();
            c.curse = static_cast<CardId>(id);
        } else if (c.kind == "ctr" && parts.size() == 3) {
            if (parts[1] != "*") {
                const int id = enumIndex(relicEnumNames, parts[1]);
                if (id < 0 || one_combat::a4CounterLimit(static_cast<RelicId>(id)) <= 0) throw bad();
                c.relic = static_cast<RelicId>(id);
            }
            const std::string &v = parts[2];
            if (v.size() < 2 || (v[0] != '+' && v[0] != '-')) throw bad();
            c.amount = parsePositive(v.substr(1), "shift in " + item) * (v[0] == '-' ? -1 : 1);
        } else {
            throw bad();
        }
        out.push_back(c);
    }
    return out;
}

struct FightEndCopy {
    std::string name;
    nlohmann::json change;
    GameContext gc;
};
struct FightEndSkip {
    std::string name;
    std::string reason;
};
struct FightEndCopies {
    std::vector<FightEndCopy> copies;   // copies[0] is the unchanged base
    std::vector<FightEndSkip> skips;
};

std::string signedText(int v) { return (v >= 0 ? "+" : "") + std::to_string(v); }

// The copies of one fork. Each change touches only its own fields and no game Random.
FightEndCopies buildCopies(const GameContext &base, const std::vector<ChangeToken> &tokens) {
    FightEndCopies out;
    out.copies.push_back({"base", {{"op", "none"}}, detachedCounterfactualCopy(base)});
    for (const auto &t : tokens) {
        if (t.kind == "noop") {
            out.copies.push_back({"noop", {{"op", "noop"}}, detachedCounterfactualCopy(base)});
        } else if (t.kind == "hp") {
            const std::string name = "hp:-" + std::to_string(t.amount);
            if (base.curHp - t.amount < 1) { out.skips.push_back({name, "hp_below_1"}); continue; }
            GameContext gc = detachedCounterfactualCopy(base);
            gc.curHp -= t.amount;
            out.copies.push_back({name, {{"op", "hp"}, {"before", base.curHp}, {"after", gc.curHp}}, std::move(gc)});
        } else if (t.kind == "pot") {
            std::vector<Potion> seen;
            for (int i = 0; i < base.potionCapacity; ++i) {
                const Potion p = base.potions[i];
                if (p == Potion::EMPTY_POTION_SLOT || p == Potion::INVALID) continue;
                if (t.potion != Potion::INVALID && p != t.potion) continue;
                if (std::find(seen.begin(), seen.end(), p) != seen.end()) continue;
                seen.push_back(p);
                GameContext gc = detachedCounterfactualCopy(base);
                gc.discardPotionAtIdx(i);
                out.copies.push_back({std::string("pot:") + potionEnumNames[static_cast<int>(p)],
                                      {{"op", "pot"}, {"removed", potionEnumNames[static_cast<int>(p)]}, {"slot", i}},
                                      std::move(gc)});
            }
            if (seen.empty())
                out.skips.push_back({t.potion == Potion::INVALID ? std::string("pot:*")
                                         : std::string("pot:") + potionEnumNames[static_cast<int>(t.potion)],
                                     "potion_not_held"});
        } else if (t.kind == "maxhp") {
            const std::string name = "maxhp:-" + std::to_string(t.amount);
            if (base.maxHp - t.amount < 1) { out.skips.push_back({name, "maxhp_below_1"}); continue; }
            GameContext gc = detachedCounterfactualCopy(base);
            gc.loseMaxHp(t.amount);   // the game's loss: current HP clipped to the new max
            out.copies.push_back({name, {{"op", "maxhp"}, {"before", base.maxHp}, {"after", gc.maxHp},
                                         {"curHpBefore", base.curHp}, {"curHpAfter", gc.curHp}}, std::move(gc)});
        } else if (t.kind == "gold") {
            const std::string name = "gold:-" + std::to_string(t.amount);
            if (base.gold < t.amount) { out.skips.push_back({name, "gold_below_amount"}); continue; }
            GameContext gc = detachedCounterfactualCopy(base);
            gc.gold -= t.amount;
            out.copies.push_back({name, {{"op", "gold"}, {"before", base.gold}, {"after", gc.gold}}, std::move(gc)});
        } else if (t.kind == "curse") {
            const std::string name = std::string("curse:") + cardEnumStrings[static_cast<int>(t.curse)];
            if (base.deck.size() >= Deck::MAX_SIZE) { out.skips.push_back({name, "deck_full"}); continue; }
            GameContext gc = detachedCounterfactualCopy(base);
            // Raw add: no Omamori charge, no Darkstone max HP, so the copy differs by the card only.
            gc.deck.obtainRaw(Card(t.curse));
            out.copies.push_back({name, {{"op", "curse"}, {"added", cardEnumStrings[static_cast<int>(t.curse)]}},
                                  std::move(gc)});
        } else if (t.kind == "ctr") {
            bool any = false;
            for (const auto &r : base.relics.relics) {
                const int limit = one_combat::a4CounterLimit(r.id);
                if (limit <= 0 || (t.relic != RelicId::INVALID && r.id != t.relic)) continue;
                any = true;
                const std::string name = std::string("ctr:") + relicEnumNames[static_cast<int>(r.id)] + ":"
                    + signedText(t.amount);
                // Counters cycle (a4_perturb's table: 0..limit-1), so the shift wraps.
                const int after = ((r.data + t.amount) % limit + limit) % limit;
                if (r.data < 0 || r.data >= limit) { out.skips.push_back({name, "counter_out_of_range"}); continue; }
                if (after == r.data) { out.skips.push_back({name, "counter_unchanged"}); continue; }
                GameContext gc = detachedCounterfactualCopy(base);
                gc.relics.getRelicValueRef(r.id) = after;
                out.copies.push_back({name, {{"op", "ctr"}, {"relic", relicEnumNames[static_cast<int>(r.id)]},
                                             {"before", r.data}, {"after", after}}, std::move(gc)});
            }
            if (!any)
                out.skips.push_back({std::string("ctr:") + (t.relic == RelicId::INVALID ? std::string("*")
                                         : std::string(relicEnumNames[static_cast<int>(t.relic)])) + ":"
                                         + signedText(t.amount), "counter_relic_not_held"});
        }
    }
    return out;
}

// -------------------------------------------------------------- row fields

// The plain state §732's features read (fit_value.py Feat.row; make_variants.py to_json), plus gold.
nlohmann::json plainState(const GameContext &gc) {
    nlohmann::json potions = nlohmann::json::array(), deck = nlohmann::json::array(),
                   misc = nlohmann::json::array(), relics = nlohmann::json::array(), data = nlohmann::json::array();
    for (int i = 0; i < gc.potionCapacity; ++i)
        if (gc.potions[i] != Potion::EMPTY_POTION_SLOT && gc.potions[i] != Potion::INVALID)
            potions.push_back(potionEnumNames[static_cast<int>(gc.potions[i])]);
    for (const auto &c : gc.deck.cards) {
        deck.push_back(std::string(cardNames[static_cast<int>(c.getId())]) + (c.getUpgraded() ? "+" : ""));
        misc.push_back(c.misc);
    }
    for (const auto &r : gc.relics.relics) {
        relics.push_back(relicEnumNames[static_cast<int>(r.id)]);
        data.push_back(r.data);
    }
    return {{"hp", gc.curHp}, {"maxHp", gc.maxHp}, {"potions", potions}, {"potionCapacity", gc.potionCapacity},
            {"deck", deck}, {"deckMisc", misc}, {"relics", relics}, {"relicData", data}, {"gold", gc.gold}};
}

int relicData(const GameContext &gc, RelicId r) {
    for (const auto &x : gc.relics.relics)
        if (x.id == r) return x.data;
    return -1;
}

// Silver's victory-leaf terms of this state at default weights (SilverSearcher::evaluateEndState, victory
// branch): HP (already healed: the fork is after BattleContext::exitBattle), held potions × 11, the death-save
// HP of Fairy (0.3/0.6 max HP) and Lizard Tail (0.5 max HP; counted only unused, as §732's L), max HP and gold
// at their leaf weights (2 and 0.25 per unit; the tree uses differences to the root, so a constant cancels).
// silverL = hp + 2 maxHp + 11 potions + deathSave is §732's L (S&S); the raw terms are written so any other
// weighting can be recomputed. winBonus and the turn penalty are fight-local and omitted.
nlohmann::json leafTerms(const GameContext &gc) {
    const bool bloom = gc.relics.has(RelicId::MARK_OF_THE_BLOOM);
    bool fairy = false;
    for (int i = 0; i < gc.potionCapacity; ++i) fairy = fairy || gc.potions[i] == Potion::FAIRY_POTION;
    const bool bark = gc.relics.has(RelicId::SACRED_BARK);
    const bool lizard = gc.relics.has(RelicId::LIZARD_TAIL);
    const bool lizardUnused = lizard && relicData(gc, RelicId::LIZARD_TAIL) == 1;
    double deathSave = 0;
    if (!bloom) {
        if (fairy) deathSave += gc.maxHp * (bark ? 0.6 : 0.3);
        if (lizardUnused) deathSave += 0.5 * gc.maxHp;
    }
    const int incense = gc.relics.has(RelicId::INCENSE_BURNER) ? relicData(gc, RelicId::INCENSE_BURNER) : -1;
    const double potionScore = 11.0 * gc.potionCount;
    return {{"hp", gc.curHp}, {"maxHp", gc.maxHp}, {"potionCount", gc.potionCount}, {"potionScore", potionScore},
            {"fairy", fairy}, {"sacredBark", bark}, {"lizardTail", lizard}, {"lizardTailUnused", lizardUnused},
            {"markOfTheBloom", bloom}, {"deathSave", deathSave}, {"gold", gc.gold}, {"incenseCounter", incense},
            {"silverL", gc.curHp + 2.0 * gc.maxHp + potionScore + deathSave}};
}

const char *encounterName(MonsterEncounter e) {
    const int i = static_cast<int>(e);
    return i >= 0 && i < static_cast<int>(std::size(monsterEncounterEnumNames)) ? monsterEncounterEnumNames[i] : "?";
}

std::uint64_t continuationSeed(std::uint64_t seed, int fightIndex) {
    // splitmix64 of (seed, fight): the same for every copy of a fork (CRN), different across forks.
    std::uint64_t z = seed * 0x9e3779b97f4a7c15ULL + static_cast<std::uint64_t>(fightIndex + 1) * 0xd1b54a32d192ed03ULL
        + 0x46454e4450414952ULL;   // "FENDPAIR"
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
    z ^= z >> 31;
    return z ? z : 1;
}

// ---------------------------------------------------------------- fight luck

// Replicate r >= 1 of a source fight: a fresh battle seed (BattleContext::init and the Silver planner derive the
// combat streams from seed + floor) and fresh carried streams with their counters kept, the redraw of fightreplay
// (fight_replay.cpp). Keyed by (run seed, fight index, replicate) with its own constant, so a replay is
// independent of the run's own fight and of every fork's continuation seed.
std::uint64_t luckRedraw(GameContext &gc, std::uint64_t seed, int fightIndex, int r) {
    std::uint64_t z = seed * 0x9e3779b97f4a7c15ULL + static_cast<std::uint64_t>(fightIndex + 1) * 0xd1b54a32d192ed03ULL
        + static_cast<std::uint64_t>(r) * 0xa0761d6478bd642fULL + 0x46454e444c55434bULL;   // "FENDLUCK"
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
    z ^= z >> 31;
    std::mt19937_64 rng(z);
    gc.seed = rng();
    for (auto stream : {&gc.aiRng, &gc.cardRandomRng, &gc.miscRng, &gc.monsterHpRng, &gc.potionRng,
                        &gc.shuffleRng}) {
        const auto counter = stream->counter;
        *stream = Random(rng());
        stream->counter = counter;
    }
    return gc.seed;
}

// The fight-end fields a luck regression reads (the real end also gets plainState, for identity checks).
nlohmann::json luckFields(const GameContext &gc) {
    int upgrades = 0;
    long long misc = 0;
    for (const auto &c : gc.deck.cards) {
        upgrades += c.getUpgraded();
        misc += c.misc;
    }
    nlohmann::json potions = nlohmann::json::array(), data = nlohmann::json::array();
    for (int i = 0; i < gc.potionCapacity; ++i)
        if (gc.potions[i] != Potion::EMPTY_POTION_SLOT && gc.potions[i] != Potion::INVALID)
            potions.push_back(potionEnumNames[static_cast<int>(gc.potions[i])]);
    for (const auto &r : gc.relics.relics) data.push_back(r.data);
    return {{"hp", gc.curHp}, {"maxHp", gc.maxHp}, {"potionCount", gc.potionCount}, {"potions", potions},
            {"gold", gc.gold}, {"deckSize", gc.deck.size()}, {"upgrades", upgrades}, {"misc", misc},
            {"relicData", data}};
}

struct LuckReplay {
    int replicate = 0;
    std::uint64_t battleSeed = 0;
    bool won = false, alive = false;
    int combatOutcome = 0, turns = 0, healthFailures = 0;
    double cpuMs = 0;
    std::int64_t simulations = 0;
    std::string error;            // a CombatStateFailure of the replay (the run is unaffected)
    nlohmann::json fields, state; // state: replicate 0 only (identity check)
};

// One replay of the fight that starts at `start`: its own detached copy and agent with the fight's budget, the
// battle exited as the run exits it. The run's health counters and battle-exit hooks are restored afterwards.
LuckReplay playLuckReplay(const GameContext &start, const OocFightStart &fs, std::uint64_t seed, int replicate) {
    LuckReplay out;
    out.replicate = replicate;
    GameContext gc = detachedCounterfactualCopy(start);
    out.battleSeed = replicate == 0 ? gc.seed : luckRedraw(gc, seed, fs.fightIndex, replicate);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = fs.simulationCountBase;
    agent.simulationCountTotal = 0;
    agent.rng = std::default_random_engine(gc.seed);   // out-of-combat only; the fight never draws from it
    const int healthTotal = search::g_simHealthFailureCount;
    const auto healthByReason = search::g_simHealthFailureCounts;
    struct ExitHooksOff {
        decltype(g_onBattleExitRaw) raw = std::move(g_onBattleExitRaw);
        decltype(g_onBattleExitPersistent) persistent = std::move(g_onBattleExitPersistent);
        ExitHooksOff() { g_onBattleExitRaw = nullptr; g_onBattleExitPersistent = nullptr; }
        ~ExitHooksOff() { g_onBattleExitRaw = std::move(raw); g_onBattleExitPersistent = std::move(persistent); }
    } hooksOff;
    BattleContext bc;
    const std::clock_t cpuStart = std::clock();
    try {
        agent.playoutBattle(gc, bc);
        bc.exitBattle(gc);
    } catch (const search::CombatStateFailure &e) {
        out.error = e.what();
    }
    out.cpuMs = 1000.0 * static_cast<double>(std::clock() - cpuStart) / CLOCKS_PER_SEC;
    out.healthFailures = search::g_simHealthFailureCount - healthTotal;
    search::g_simHealthFailureCount = healthTotal;   // the run's validity counts the run's own fights only
    search::g_simHealthFailureCounts = healthByReason;
    out.simulations = agent.simulationCountTotal;
    out.combatOutcome = static_cast<int>(bc.outcome);
    out.turns = bc.turn;
    out.won = out.error.empty() && bc.outcome == Outcome::PLAYER_VICTORY;
    out.alive = out.error.empty() && gc.outcome != GameOutcome::PLAYER_LOSS;
    out.fields = luckFields(gc);
    if (replicate == 0) out.state = plainState(gc);
    return out;
}

struct SampledFork {
    GameContext gc;
    PathHistory path;
    OocPolicyThreadState policy;
    int fightIndex = 0;
    int act = 0;
    Room room = Room::INVALID;
    MonsterEncounter encounter = MonsterEncounter::INVALID;
};

std::string stratumOf(const FightEndOptions &o, const std::string &room, int act) {
    if (o.strata == "room") return room;
    if (o.strata == "act") return std::to_string(act);
    if (o.strata == "room_act") return room + "/" + std::to_string(act);
    return "all";
}

struct ContinuationTrack {
    int lastAct = 0, lastFloor = 0, lastHp = 0;
    bool died = false;
    int deathAct = 0, deathFloor = -1;
    MonsterEncounter deathEncounter = MonsterEncounter::INVALID;
    MonsterEncounter lastEncounter = MonsterEncounter::INVALID;
    bool lastWon = false;
    int fights = 0;
};

void writeManifest(const std::string &path, const nlohmann::json &args) {
    nlohmann::json env = nlohmann::json::object();
    for (char **e = ::environ; e && *e; ++e) {
        const std::string kv(*e);
        if (kv.rfind("STS_", 0) != 0 && kv.rfind("OMP_", 0) != 0) continue;
        const auto eq = kv.find('=');
        env[kv.substr(0, eq)] = eq == std::string::npos ? "" : kv.substr(eq + 1);
    }
    const nlohmann::json m = {
        {"schema", "fightendpairs-manifest-v1"}, {"mode", "fightendpairgen"}, {"args", args},
        {"git_sha", trainingExecutableGitSha()}, {"executable_sha256", fileSha256(g_mainBinaryPath)},
        {"ooc_policy", effectiveOocPolicySpecification()}, {"silver_leaf", effectiveSilverLeafSpecification()},
        {"silver_learned_stop", search::nativeSilverLearnedStopEnabled()}, {"env", env}};
    std::ofstream out(path);
    if (!out) throw std::runtime_error("fightendpairgen: cannot open " + path);
    out << m.dump(2) << '\n';
}

} // namespace

namespace one_combat {

void fightEndPairGen(int nSeeds, std::uint64_t seedStart, int sims, int asc, const std::string &outFile,
                     const std::string &optionSpec, const std::string &variantSpec, bool manifest) {
    const FightEndOptions opt = parseOptions(optionSpec);
    const std::vector<ChangeToken> tokens = parseVariants(variantSpec);
    const bool luckOn = opt.luck > 0 || opt.luckIdentity > 0;
    if (nSeeds <= 0 || sims <= 0) throw std::runtime_error("fightendpairgen: invalid arguments");
    if (opt.oocHeart1 && !heart1::enabled())
        throw std::runtime_error("fightendpairgen: ooc=heart1 needs STS_OOC_HEART1");
    if (opt.oocPpo && (!heart1::enabled() || !heart1::ppoEnabled() || liveOocMctsEnabled()))
        throw std::runtime_error("fightendpairgen: ooc=ppo needs STS_OOC_HEART1, STS_OOC_HEART1_PPO=1 and STS_OOC_MCTS=0");
    struct Heart1Scope {
        bool saved = t_counterfactualHeart1;
        explicit Heart1Scope(bool on) { t_counterfactualHeart1 = on; }
        ~Heart1Scope() { t_counterfactualHeart1 = saved; }
    } heart1Scope(opt.oocHeart1);
    struct PpoScope {
        bool saved = t_counterfactualPpo;
        explicit PpoScope(bool on) { t_counterfactualPpo = on; }
        ~PpoScope() { t_counterfactualPpo = saved; }
    } ppoScope(opt.oocPpo);
    // ooc=ppo: the net's counters of the call just played (decisions, fallbacks), for the rows.
    const auto ppoCounts = [&]() -> nlohmann::json {
        const heart1::PpoGameCounts c = heart1::ppoGameCounts();
        return {{"decisions", c.decisions}, {"single", c.single}, {"fallbacks", c.fallbacks},
                {"autoGold", c.autoGold}};
    };
    const nlohmann::json args = {{"nSeeds", nSeeds}, {"seedStart", seedStart}, {"sims", sims}, {"asc", asc},
                                 {"options", optionsJson(opt)},
                                 {"variants", variantSpec.empty() || variantSpec == "default" ? kDefaultVariants
                                                                                              : variantSpec}};
    if (manifest) writeManifest(outFile + ".manifest.json", args);
    std::ofstream out(outFile);
    if (!out) throw std::runtime_error("fightendpairgen: cannot open " + outFile);
    const bool keepRoom[4] = {
        std::find(opt.rooms.begin(), opt.rooms.end(), "NORMAL") != opt.rooms.end(),
        std::find(opt.rooms.begin(), opt.rooms.end(), "ELITE") != opt.rooms.end(),
        std::find(opt.rooms.begin(), opt.rooms.end(), "BOSS") != opt.rooms.end(),
        std::find(opt.rooms.begin(), opt.rooms.end(), "OTHER") != opt.rooms.end()};
    const auto roomKept = [&](const std::string &r) {
        return r == "NORMAL" ? keepRoom[0] : r == "ELITE" ? keepRoom[1] : r == "BOSS" ? keepRoom[2] : keepRoom[3];
    };
    for (int s = 0; s < nSeeds; ++s) {
        const std::uint64_t seed = seedStart + static_cast<std::uint64_t>(s);
        trainingRunStart();
        vDisconnect();
        resetPathPolicyState();
        // Source run: one reservoir per stratum; the observer only copies state (no RNG).
        std::map<std::string, std::pair<int, std::vector<SampledFork>>> reservoirs;   // seen, kept
        std::default_random_engine reservoir(seed * 2862933555777941757ULL + 97);
        int fightEnds = 0, eligible = 0;
        std::map<std::string, int> ineligible;
        bool sourceLastWon = false;
        MonsterEncounter sourceLastEncounter = MonsterEncounter::INVALID;
        // luck=: the replays of each source fight are played at its start and written with its end as one row.
        struct PendingLuck {
            int fightIndex = -1, budget = 0;
            MonsterEncounter encounter = MonsterEncounter::INVALID;
            nlohmann::json start, relics = nlohmann::json::array();
            std::vector<LuckReplay> replays;
        };
        std::optional<PendingLuck> pendingLuck;
        struct LuckTally {
            int fights = 0, replays = 0, errors = 0, healthFailures = 0, identityChecked = 0, identityMismatches = 0;
            double cpuMs = 0;
        } luckTally;
        const bool identitySeed = s < opt.luckIdentity;
        // rewards=: potionChance at each source fight's start, and the rolls of the run.
        std::optional<int> potionChanceAtStart;   // potionChance can be negative (-10 per drop)
        nlohmann::json rewardRolls = nlohmann::json::array();
        int rewardInconsistent = 0;
        const auto logRewardRoll = [&](const GameContext &gc, const OocFightEnd &fe) {
            const std::optional<int> start = potionChanceAtStart;
            potionChanceAtStart.reset();
            // GameContext::afterBattle rolls the reward inside BattleContext::exitBattle, before this observer.
            // createCombatReward / createEliteCombatReward / createBossCombatReward (acts 1-2) roll one potion
            // after the gold (and elite relics), so the reward has fewer than 4 items at the roll and
            // addPotionRewards' zero-chance case cannot occur.
            const bool rolls = fe.room == Room::MONSTER || fe.room == Room::ELITE || (fe.room == Room::BOSS && fe.act < 3);
            if (!fe.won || !rolls || gc.outcome != GameOutcome::UNDECIDED || gc.screenState != ScreenState::REWARDS)
                return;
            const auto &rw = gc.info.rewardsContainer;
            const bool dropped = rw.potionCount > 0;
            const bool consistent = start && gc.potionChance == *start + (dropped ? -10 : 10);
            // addPotionRewards: drop if potionRng.random(99) (0-99) < 40 + potionChance, or always with the statue.
            const int chance = gc.relics.has(RelicId::WHITE_BEAST_STATUE) ? 100
                                                                          : std::clamp(40 + start.value_or(0), 0, 100);
            rewardInconsistent += !consistent;
            nlohmann::json x = {{"fightIndex", fe.fightIndex}, {"act", fe.act}, {"floor", fe.floor},
                                {"room", combatEvalRoomClass(fe.room)},
                                {"chance", chance},
                                {"dropped", dropped}, {"potionCount", gc.potionCount},
                                {"potionCapacity", gc.potionCapacity}, {"sozu", gc.relics.has(RelicId::SOZU)}};
            if (dropped) x["potion"] = potionEnumNames[static_cast<int>(rw.potions[0])];
            if (!consistent)
                x["inconsistent"] = {{"potionChanceAtStart", start ? nlohmann::json(*start) : nlohmann::json(nullptr)},
                                     {"potionChanceAfter", gc.potionChance}};
            rewardRolls.push_back(std::move(x));
        };
        const OocFightStartObserver luckStart = [&](const GameContext &gc, const OocFightStart &fs) {
            if (pendingLuck) throw std::runtime_error("fightendpairgen: fight started before the last one ended");
            PendingLuck p;
            p.fightIndex = fs.fightIndex;
            p.budget = fs.simulationCountBase;
            p.encounter = fs.encounter;
            p.start = luckFields(gc);
            for (const auto &r : gc.relics.relics) p.relics.push_back(relicEnumNames[static_cast<int>(r.id)]);
            for (int r = identitySeed ? 0 : 1; r <= opt.luck; ++r) p.replays.push_back(playLuckReplay(gc, fs, seed, r));
            pendingLuck = std::move(p);
        };
        const auto writeLuckRow = [&](const GameContext &gc, const OocFightEnd &fe) {
            if (!pendingLuck || pendingLuck->fightIndex != fe.fightIndex)
                throw std::runtime_error("fightendpairgen: no luck replays for fight " + std::to_string(fe.fightIndex));
            const nlohmann::json realFields = luckFields(gc), realState = plainState(gc);
            const bool realAlive = gc.outcome != GameOutcome::PLAYER_LOSS;
            nlohmann::json row = {{"kind", "luck"}, {"seed", seed}, {"fightIndex", fe.fightIndex}, {"act", fe.act},
                                  {"floor", fe.floor}, {"room", combatEvalRoomClass(fe.room)},
                                  {"encounter", encounterName(fe.encounter)}, {"budget", pendingLuck->budget},
                                  {"relics", pendingLuck->relics}, {"start", pendingLuck->start},
                                  {"real", {{"won", fe.won}, {"alive", realAlive}, {"fields", realFields},
                                            {"state", realState}}}};
            if (pendingLuck->encounter != fe.encounter) row["startEncounter"] = encounterName(pendingLuck->encounter);
            nlohmann::json replays = nlohmann::json::array();
            for (const auto &r : pendingLuck->replays) {
                ++luckTally.replays;
                luckTally.cpuMs += r.cpuMs;
                luckTally.errors += !r.error.empty();
                luckTally.healthFailures += r.healthFailures;
                if (r.replicate == 0) {   // a check, not a luck draw
                    const bool same = r.error.empty() && r.healthFailures == 0 && r.won == fe.won
                        && r.alive == realAlive && r.fields == realFields && r.state == realState;
                    ++luckTally.identityChecked;
                    luckTally.identityMismatches += !same;
                    row["identity"] = same;
                    if (!same)
                        row["identityReplay"] = {{"won", r.won}, {"alive", r.alive}, {"fields", r.fields},
                                                 {"error", r.error}, {"healthFailures", r.healthFailures}};
                    continue;
                }
                nlohmann::json x = {{"r", r.replicate}, {"battleSeed", r.battleSeed}, {"won", r.won},
                                    {"alive", r.alive}, {"combatOutcome", r.combatOutcome}, {"turns", r.turns},
                                    {"cpuMs", r.cpuMs}, {"simulations", r.simulations},
                                    {"healthFailures", r.healthFailures}, {"fields", r.fields}};
                if (!r.error.empty()) x["error"] = r.error;
                replays.push_back(std::move(x));
            }
            row["replays"] = std::move(replays);
            ++luckTally.fights;
            out << row.dump() << '\n';
            pendingLuck.reset();
        };
        const OocFightStartObserver fightStart = [&](const GameContext &gc, const OocFightStart &fs) {
            if (opt.rewards) potionChanceAtStart = gc.potionChance;
            if (luckOn) luckStart(gc, fs);
        };
        const OocFightEndObserver observer = [&](const GameContext &gc, const OocFightEnd &fe) {
            sourceLastWon = fe.won;
            sourceLastEncounter = fe.encounter;
            if (luckOn) writeLuckRow(gc, fe);
            if (opt.rewards) logRewardRoll(gc, fe);
            if (!fe.won) return;
            ++fightEnds;
            const std::string room = combatEvalRoomClass(fe.room);
            std::string why;
            if (gc.outcome != GameOutcome::UNDECIDED) why = "run_decided";
            else if (gc.screenState != ScreenState::REWARDS) why = "not_rewards_screen";
            else if (!roomKept(room)) why = "room_filtered";
            else if (std::find(opt.acts.begin(), opt.acts.end(), fe.act) == opt.acts.end()) why = "act_filtered";
            else if (!t_curPath) why = "no_path";
            if (!why.empty()) { ++ineligible[why]; return; }
            ++eligible;
            if (opt.forksPerRun == 0) return;
            auto &[seen, kept] = reservoirs[stratumOf(opt, room, fe.act)];
            ++seen;
            SampledFork f{detachedCounterfactualCopy(gc), *t_curPath, captureOocPolicyThreadState(),
                          fe.fightIndex, fe.act, fe.room, fe.encounter};
            if (static_cast<int>(kept.size()) < opt.forksPerRun) { kept.push_back(std::move(f)); return; }
            const int j = std::uniform_int_distribution<int>(0, seen - 1)(reservoir);
            if (j < opt.forksPerRun) kept[j] = std::move(f);
        };
        OocContinuationCost sourceCost;
        const OocCounterfactualResult source = finishOocCounterfactual(
            GameContext(CharacterClass::IRONCLAD, seed, asc), sims, seed, PathHistory{}, opt.sourceFights, false,
            nullptr, 0, nullptr, false, nullptr, &sourceCost, false, nullptr, &observer,
            luckOn || opt.rewards ? &fightStart : nullptr);
        if (pendingLuck) throw std::runtime_error("fightendpairgen: a source fight started but never ended");
        std::vector<SampledFork> sampled;
        for (auto &[stratum, r] : reservoirs)
            for (auto &f : r.second) sampled.push_back(std::move(f));
        std::sort(sampled.begin(), sampled.end(),
                  [](const auto &a, const auto &b) { return a.fightIndex < b.fightIndex; });
        const bool sourceHeartKill = source.valid && source.won > 0.5 && sourceLastWon
            && sourceLastEncounter == MonsterEncounter::THE_HEART;
        nlohmann::json sourceRow{{"kind", "source"}, {"seed", seed}, {"valid", source.valid}, {"won", source.won},
                                 {"heartKill", sourceHeartKill},
                                 {"floor", source.floor}, {"fightEnds", fightEnds}, {"eligible", eligible},
                                 {"ineligible", ineligible}, {"sampled", sampled.size()},
                                 {"cost", {{"cpuMs", sourceCost.cpuMs}, {"wallMs", sourceCost.wallMs},
                                           {"silverSimulations", sourceCost.silverSimulations}}}};
        if (opt.oocPpo) sourceRow["ppo"] = ppoCounts();
        // luck=: cost.cpuMs/wallMs then include the replays (luck.cpuMs); every other field is the run's own.
        if (luckOn)
            sourceRow["luck"] = {{"replicates", opt.luck}, {"identitySeed", identitySeed},
                                 {"fights", luckTally.fights}, {"replays", luckTally.replays},
                                 {"errors", luckTally.errors}, {"healthFailures", luckTally.healthFailures},
                                 {"identityChecked", luckTally.identityChecked},
                                 {"identityMismatches", luckTally.identityMismatches}, {"cpuMs", luckTally.cpuMs}};
        if (opt.rewards) sourceRow["rewards"] = {{"rolls", rewardRolls}, {"inconsistent", rewardInconsistent}};
        out << sourceRow.dump() << '\n';
        out.flush();
        std::cout << "[fightendpairgen] seed=" << seed << " sourceFloor=" << source.floor
                  << " sourceWon=" << source.won << " fightEnds=" << fightEnds << " eligible=" << eligible
                  << " sampled=" << sampled.size();
        if (luckOn)
            std::cout << " luckFights=" << luckTally.fights << " luckReplays=" << luckTally.replays
                      << " luckErrors=" << luckTally.errors << " identityMismatches=" << luckTally.identityMismatches;
        std::cout << std::endl;
        for (int fork = 0; fork < static_cast<int>(sampled.size()); ++fork) {
            const SampledFork &f = sampled[fork];
            const std::uint64_t contSeed = continuationSeed(seed, f.fightIndex);
            const nlohmann::json at = {
                {"seed", seed}, {"fork", fork}, {"fightIndex", f.fightIndex}, {"act", f.act},
                {"floor", f.gc.floorNum}, {"room", combatEvalRoomClass(f.room)},
                {"encounter", encounterName(f.encounter)}, {"contSeed", contSeed}};
            FightEndCopies copies = buildCopies(f.gc, tokens);
            for (const auto &skip : copies.skips) {
                nlohmann::json row = at;
                row.update({{"kind", "skip"}, {"variant", skip.name}, {"reason", skip.reason}});
                out << row.dump() << '\n';
            }
            for (auto &copy : copies.copies) {
                nlohmann::json row = at;
                row.update({{"kind", "copy"}, {"variant", copy.name}, {"change", copy.change}});
                std::string reason;
                nlohmann::json record;
                if (heart1::buildPublicLeafRecord(copy.gc, record, &reason)) row["heart1"] = std::move(record);
                else row["heart1"] = {{"unsupported", reason.empty() ? "unsupported" : reason}};
                row["state"] = plainState(copy.gc);
                row["leaf"] = leafTerms(copy.gc);
                if (g_fightEndPairsExtraObservation) row["obsV2"] = g_fightEndPairsExtraObservation(copy.gc);
                restoreOocPolicyThreadState(f.policy);
                ContinuationTrack track;
                const OocFightEndObserver follow = [&](const GameContext &now, const OocFightEnd &fe) {
                    ++track.fights;
                    track.lastHp = fe.won ? now.curHp : 0;
                    track.lastAct = fe.act;
                    track.lastFloor = fe.floor;
                    track.lastEncounter = fe.encounter;
                    track.lastWon = fe.won;
                    if (!fe.won) {
                        track.died = true;
                        track.deathAct = fe.act;
                        track.deathFloor = fe.floor;
                        track.deathEncounter = fe.encounter;
                    }
                };
                OocContinuationCost cost;
                const int startAct = copy.gc.act;
                const OocCounterfactualResult r = finishOocCounterfactual(
                    std::move(copy.gc), sims, contSeed, f.path, opt.horizon, false, nullptr, 0, nullptr, false,
                    nullptr, &cost, false, nullptr, &follow);
                const bool gameWon = r.valid && r.won > 0.5;
                const bool heartKill = gameWon && track.lastWon && track.lastEncounter == MonsterEncounter::THE_HEART;
                const bool lost = r.valid && !gameWon;
                row["outcome"] = {
                    {"valid", r.valid}, {"heartKill", heartKill}, {"won", gameWon},
                    {"finalAct", track.fights ? track.lastAct : startAct}, {"finalFloor", r.floor},
                    {"deathFloor", lost ? (track.died ? track.deathFloor : static_cast<int>(r.floor)) : -1},
                    {"deathAct", lost && track.died ? track.deathAct : -1},
                    {"deathEncounter", lost && track.died ? encounterName(track.deathEncounter) : ""},
                    {"finalHp", r.hp}, {"fights", track.fights}, {"lastFightFloor", track.lastFloor},
                    {"lastFightHp", track.lastHp}, {"horizon", opt.horizon < 0 ? -1 : opt.horizon}};
                if (opt.oocPpo) row["ppo"] = ppoCounts();
                row["silverSims"] = sims;
                row["cost"] = {{"cpuMs", cost.cpuMs}, {"wallMs", cost.wallMs},
                               {"silverSimulations", cost.silverSimulations},
                               {"combatDecisions", cost.combatDecisions}};
                out << row.dump() << '\n';
            }
            out.flush();
        }
    }
}

// ------------------------------------------------------------------ self test

namespace {

void check(bool ok, const std::string &what) {
    if (!ok) throw std::runtime_error("fightendpairselftest: " + what);
}

std::string rngFingerprint(const GameContext &gc) {
    std::ostringstream os;
    for (const Random *r : {&gc.aiRng, &gc.cardRandomRng, &gc.cardRng, &gc.eventRng, &gc.mathUtilRng,
                            &gc.merchantRng, &gc.miscRng, &gc.monsterHpRng, &gc.monsterRng, &gc.neowRng,
                            &gc.potionRng, &gc.relicRng, &gc.shuffleRng, &gc.treasureRng})
        os << r->counter << ':' << r->seed0 << ':' << r->seed1 << ';';
    return os.str();
}

// The fields of plainState that differ between a and b.
std::vector<std::string> changedFields(const GameContext &a, const GameContext &b) {
    const auto ja = plainState(a), jb = plainState(b);
    std::vector<std::string> out;
    for (auto it = ja.begin(); it != ja.end(); ++it)
        if (jb.at(it.key()) != it.value()) out.push_back(it.key());
    return out;
}

// Rows without their timing (cpuMs, wallMs); simulation and decision counts stay.
std::vector<nlohmann::json> readRows(const std::string &path) {
    std::ifstream in(path);
    std::vector<nlohmann::json> rows;
    for (std::string line; std::getline(in, line);) {
        if (line.empty()) continue;
        auto row = nlohmann::json::parse(line);
        if (row.contains("cost")) { row["cost"].erase("cpuMs"); row["cost"].erase("wallMs"); }
        rows.push_back(std::move(row));
    }
    return rows;
}

void fastSelfTest() {
    // Specs.
    check(parseVariants("default").size() == 6, "default variant count");
    check(parseVariants("-").empty(), "empty variant list");
    for (const char *bad : {"hp:3", "hp:-0", "pot:NOPE", "curse:STRIKE_RED", "ctr:AKABEKO:+1", "ctr:PEN_NIB:1",
                            "gold", "maxhp:-x", "foo"}) {
        bool threw = false;
        try { parseVariants(bad); } catch (const std::runtime_error &) { threw = true; }
        check(threw, std::string("variant accepted: ") + bad);
    }
    const auto o = parseOptions("n=2,rooms=ELITE+BOSS,acts=2+3,strata=room_act,horizon=3,ooc=heart1");
    check(o.forksPerRun == 2 && o.rooms.size() == 2 && o.acts.size() == 2 && o.strata == "room_act"
              && o.horizon == 3 && o.oocHeart1 && !o.oocPpo, "option parse");
    const auto p = parseOptions("n=4,ooc=ppo");
    check(p.oocPpo && !p.oocHeart1 && optionsJson(p).at("ooc") == "ppo", "ooc=ppo parse");
    check(optionsJson(parseOptions("-")).at("ooc") == "deployed", "ooc default");
    const auto l = parseOptions("n=0,ooc=ppo,luck=1,luck_identity=2");
    check(l.forksPerRun == 0 && l.oocPpo && l.luck == 1 && l.luckIdentity == 2 && optionsJson(l).at("luck") == 1
              && optionsJson(l).at("luck_identity") == 2, "luck option parse");
    check(parseOptions("-").luck == 0 && parseOptions("-").luckIdentity == 0, "luck default off");
    const auto rwo = parseOptions("n=0,rewards=1");
    check(rwo.rewards && optionsJson(rwo).at("rewards") == 1 && !parseOptions("-").rewards
              && optionsJson(parseOptions("-")).at("rewards") == 0, "rewards option parse");
    for (const char *bad : {"n=-1", "rooms=SHOP", "acts=5", "strata=floor", "x=1", "n", "ooc=student", "luck=9",
                            "luck=x", "luck_identity=-1", "luck=", "rewards=2", "rewards=x"}) {
        bool threw = false;
        try { parseOptions(bad); } catch (const std::runtime_error &) { threw = true; }
        check(threw, std::string("option accepted: ") + bad);
    }

    // A fixture state (Neow screen of a used smoke seed; no game step is played).
    GameContext base(CharacterClass::IRONCLAD, 111459990ULL, 20);
    base.curHp = 30;
    base.gold = 120;
    for (int i = 0; i < static_cast<int>(base.potions.size()); ++i) base.potions[i] = Potion::EMPTY_POTION_SLOT;
    base.potionCount = 0;
    base.obtainPotion(Potion::FAIRY_POTION);
    base.obtainPotion(Potion::BLOCK_POTION);
    check(base.potionCount == 2, "fixture potions");
    base.relics.add({RelicId::INCENSE_BURNER, 5});
    base.relics.add({RelicId::LIZARD_TAIL, 1});
    const auto copies = buildCopies(base, parseVariants(
        "noop,hp:-3,hp:-8,hp:-15,pot:*,maxhp:-5,gold:-50,curse:REGRET,ctr:INCENSE_BURNER:+1,ctr:*:-2,pot:SMOKE_BOMB"));
    std::vector<std::string> names;
    for (const auto &c : copies.copies) names.push_back(c.name);
    const std::vector<std::string> expected = {"base", "noop", "hp:-3", "hp:-8", "hp:-15", "pot:FAIRY_POTION",
        "pot:BLOCK_POTION", "maxhp:-5", "gold:-50", "curse:REGRET", "ctr:INCENSE_BURNER:+1", "ctr:INCENSE_BURNER:-2"};
    check(names == expected, "copy names");
    check(copies.skips.size() == 1 && copies.skips[0].name == "pot:SMOKE_BOMB"
              && copies.skips[0].reason == "potion_not_held", "potion skip");
    const std::map<std::string, std::vector<std::string>> fields = {
        {"base", {}}, {"noop", {}}, {"hp:-3", {"hp"}}, {"hp:-8", {"hp"}}, {"hp:-15", {"hp"}},
        {"pot:FAIRY_POTION", {"potions"}}, {"pot:BLOCK_POTION", {"potions"}}, {"maxhp:-5", {"maxHp"}},
        {"gold:-50", {"gold"}}, {"curse:REGRET", {"deck", "deckMisc"}},
        {"ctr:INCENSE_BURNER:+1", {"relicData"}}, {"ctr:INCENSE_BURNER:-2", {"relicData"}}};
    const std::string fp = rngFingerprint(base);
    for (const auto &c : copies.copies) {
        auto changed = changedFields(base, c.gc);
        auto want = fields.at(c.name);
        // deckMisc keeps its values when a curse adds misc 0: only the list length changes.
        check(changed == want, "changed fields of " + c.name);
        check(rngFingerprint(c.gc) == fp, "RNG differs in " + c.name);   // CRN: copies share every game Random
        check(c.gc.seed == base.seed && c.gc.floorNum == base.floorNum && c.gc.screenState == base.screenState,
              "run position differs in " + c.name);
        check(!base.map || c.gc.map.get() != base.map.get(), "map not detached in " + c.name);
    }
    const auto &byName = [&](const std::string &n) -> const GameContext & {
        for (const auto &c : copies.copies) if (c.name == n) return c.gc;
        throw std::runtime_error("missing " + n);
    };
    check(byName("hp:-15").curHp == 15 && byName("maxhp:-5").maxHp == base.maxHp - 5, "hp values");
    check(byName("gold:-50").gold == 70 && byName("pot:FAIRY_POTION").potionCount == 1, "gold/potion values");
    check(relicData(byName("ctr:INCENSE_BURNER:+1"), RelicId::INCENSE_BURNER) == 0, "incense wraps 5 -> 0");
    check(relicData(byName("ctr:INCENSE_BURNER:-2"), RelicId::INCENSE_BURNER) == 3, "incense 5 -> 3");
    check(byName("curse:REGRET").deck.size() == base.deck.size() + 1, "curse added");
    check(leafTerms(byName("noop")) == leafTerms(base) && plainState(byName("noop")) == plainState(base),
          "noop rows equal base rows");
    check(leafTerms(base).at("deathSave").get<double>() == 0.3 * base.maxHp + 0.5 * base.maxHp, "death save");
    check(leafTerms(byName("pot:FAIRY_POTION")).at("deathSave").get<double>() == 0.5 * base.maxHp, "fairy removed");

    // Skips at the bounds.
    GameContext poor = detachedCounterfactualCopy(base);
    poor.curHp = 10;
    poor.gold = 49;
    poor.maxHp = 5;
    poor.curHp = 5;
    const auto skipped = buildCopies(poor, parseVariants("hp:-3,hp:-8,maxhp:-5,gold:-50,ctr:PEN_NIB:+1,ctr:*:+6"));
    std::map<std::string, std::string> reasons;
    for (const auto &s : skipped.skips) reasons[s.name] = s.reason;
    check(reasons.at("hp:-8") == "hp_below_1" && reasons.at("maxhp:-5") == "maxhp_below_1"
              && reasons.at("gold:-50") == "gold_below_amount" && reasons.at("ctr:PEN_NIB:+1") == "counter_relic_not_held"
              && reasons.at("ctr:INCENSE_BURNER:+6") == "counter_unchanged",
          "skip reasons");
    check(skipped.copies.size() == 2 && skipped.copies[1].name == "hp:-3", "copies at the bounds");
    check(continuationSeed(1, 0) != continuationSeed(1, 1) && continuationSeed(1, 0) == continuationSeed(1, 0),
          "continuation seed");

    // Luck redraw: deterministic per (seed, fight, replicate), new seed and carried streams, counters and every
    // persistent field kept.
    GameContext r1 = detachedCounterfactualCopy(base), r1b = detachedCounterfactualCopy(base),
                r2 = detachedCounterfactualCopy(base), f2 = detachedCounterfactualCopy(base);
    const auto s1 = luckRedraw(r1, base.seed, 3, 1), s1b = luckRedraw(r1b, base.seed, 3, 1);
    const auto s2 = luckRedraw(r2, base.seed, 3, 2), sf = luckRedraw(f2, base.seed, 4, 1);
    check(s1 == s1b && rngFingerprint(r1) == rngFingerprint(r1b), "luck redraw is not deterministic");
    check(s1 != s2 && s1 != sf && s1 != base.seed && rngFingerprint(r1) != rngFingerprint(r2), "luck redraw repeats");
    check(r1.miscRng.counter == base.miscRng.counter && r1.potionRng.counter == base.potionRng.counter
              && r1.miscRng.seed0 != base.miscRng.seed0 && r1.cardRng.seed0 == base.cardRng.seed0
              && r1.relicRng.seed0 == base.relicRng.seed0, "luck redraw streams");
    check(plainState(r1) == plainState(base) && luckFields(r1) == luckFields(base), "luck redraw changes the state");
    check(luckFields(base).at("potionCount") == 2 && luckFields(base).at("hp") == 30, "luck fields");
    std::cout << "fightendpairselftest: fast checks passed\n";
}

// Plays real continuations (cheap settings): run-twice identity, base twice, noop == base, and the observer's
// default-off identity. Needs the run environment a smoke uses (see the doc).
void fullSelfTest(int sims, const std::string &dir) {
    const std::uint64_t seed = 111459990ULL;   // used smoke seed (PPO smoke, 2026-11)
    const std::string opts = "n=2,horizon=2,source_fights=6";
    const std::string a = dir + "/fightendpairs-a.jsonl", b = dir + "/fightendpairs-b.jsonl";
    fightEndPairGen(1, seed, sims, 20, a, opts, "noop,hp:-8,pot:*", false);
    fightEndPairGen(1, seed, sims, 20, b, opts, "noop,hp:-8,pot:*", false);
    const auto ra = readRows(a), rb = readRows(b);
    check(!ra.empty() && ra == rb, "same arguments give different rows (run twice)");
    int pairs = 0;
    for (const auto &row : ra) {
        if (row.at("kind") != "copy" || row.at("variant") != "noop") continue;
        for (const auto &baseRow : ra)
            if (baseRow.at("kind") == "copy" && baseRow.at("variant") == "base" && baseRow.at("fork") == row.at("fork")) {
                check(baseRow.at("outcome") == row.at("outcome") && baseRow.at("cost") == row.at("cost"),
                      "noop outcome differs from base");
                check(baseRow.at("heart1") == row.at("heart1") && baseRow.at("leaf") == row.at("leaf"),
                      "noop record differs from base");
                ++pairs;
            }
    }
    check(pairs > 0, "no fork sampled");

    // Default-off identity of the fight-end hook: a no-op observer leaves the run unchanged.
    const auto play = [&](bool hook) {
        trainingRunStart();
        vDisconnect();
        resetPathPolicyState();
        FutureFightProbe probe;
        int calls = 0;
        const OocFightEndObserver noop = [&](const GameContext &, const OocFightEnd &) { ++calls; };
        const auto r = finishOocCounterfactual(GameContext(CharacterClass::IRONCLAD, seed, 20), sims, seed,
                                               PathHistory{}, 6, false, &probe, 0, nullptr, false, nullptr, nullptr,
                                               false, nullptr, hook ? &noop : nullptr);
        std::ostringstream os;
        os << r.won << ',' << r.floor << ',' << r.hp << ',' << r.valid << ';';
        for (const auto &x : probe.fights)
            os << static_cast<int>(x.encounter) << ':' << x.floor << ':' << x.hp << ':' << x.passed << ';';
        check(!hook || calls == static_cast<int>(probe.fights.size()), "observer call count");
        return os.str();
    };
    check(play(false) == play(true), "fight-end observer changes the run");

    // luck=: the replays leave every source and fork row unchanged, replicate 0 reproduces each real fight, and
    // the fresh replays are new draws of it.
    const std::string c = dir + "/fightendpairs-luck.jsonl";
    fightEndPairGen(1, seed, sims, 20, c, opts + ",luck=1,luck_identity=1", "noop,hp:-8,pot:*", false);
    std::vector<nlohmann::json> plain;
    int luckRows = 0, differs = 0;
    for (auto row : readRows(c)) {
        if (row.at("kind") == "luck") {
            check(row.at("fightIndex") == luckRows, "luck rows out of order");
            ++luckRows;
            check(row.value("identity", false), "replicate 0 differs from the real fight " + row.dump());
            check(!row.contains("startEncounter"), "fight-start encounter differs from the fight's");
            const auto &reps = row.at("replays");
            check(reps.size() == 1 && reps[0].at("r") == 1 && !reps[0].contains("error")
                      && reps[0].at("healthFailures") == 0 && reps[0].at("simulations").get<long long>() > 0,
                  "fresh replay row");
            differs += reps[0].at("fields") != row.at("real").at("fields") || reps[0].at("won") != row.at("real").at("won");
            continue;
        }
        if (row.at("kind") == "source") {
            const auto &l = row.at("luck");
            check(l.at("fights") == luckRows && l.at("replays") == 2 * luckRows && l.at("identityChecked") == luckRows
                      && l.at("identityMismatches") == 0 && l.at("errors") == 0 && l.at("identitySeed") == true,
                  "source luck tally");
            row.erase("luck");
        }
        plain.push_back(std::move(row));
    }
    check(luckRows > 0 && plain == ra, "luck replays change the source or fork rows");
    check(differs > 0, "no fresh replay differs from its real fight");

    // rewards=: the roll log leaves every source and fork row unchanged, and each roll's chance agrees with the
    // potion chance the engine moved (start + 10 without a drop, start - 10 with one).
    const std::string d = dir + "/fightendpairs-rewards.jsonl";
    fightEndPairGen(1, seed, sims, 20, d, opts + ",rewards=1", "noop,hp:-8,pot:*", false);
    std::vector<nlohmann::json> unlogged;
    int rolls = 0, drops = 0;
    for (auto row : readRows(d)) {
        if (row.at("kind") == "source") {
            const auto &log = row.at("rewards");
            check(log.at("inconsistent") == 0, "reward roll disagrees with the engine's potion chance " + log.dump());
            for (const auto &x : log.at("rolls")) {
                const int chance = x.at("chance");
                const bool dropped = x.at("dropped");
                check(chance >= 0 && chance <= 100 && x.contains("potion") == dropped
                          && !(dropped && chance == 0) && !(!dropped && chance == 100), "reward roll " + x.dump());
                ++rolls;
                drops += dropped;
            }
            row.erase("rewards");
        }
        unlogged.push_back(std::move(row));
    }
    check(rolls > 0 && unlogged == ra, "reward logging changes the source or fork rows");
    std::cout << "fightendpairselftest: full checks passed (" << pairs << " noop/base pairs, " << luckRows
              << " luck fights, " << differs << " differ, " << rolls << " reward rolls, " << drops << " drops)\n";
}

} // namespace

int fightEndPairSelfTest(int argc, char **argv) {
    fastSelfTest();
    if (argc > 2 && std::string(argv[2]) == "full") {
        const int sims = argc > 3 ? std::stoi(argv[3]) : 20;
        const std::string dir = argc > 4 ? argv[4] : ".";
        fullSelfTest(sims, dir);
    }
    return 0;
}

} // namespace one_combat
