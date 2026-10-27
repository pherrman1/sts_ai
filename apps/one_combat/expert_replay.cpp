#include "expert_replay.h"
#include "driver_shared.h"
#include "expert_run_log.h"
#include "heart_outcome_capture.h"
#include "run_driver.h"

#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

extern bool g_collectKeys;

namespace one_combat {
namespace {

using namespace sts;
using nlohmann::json;
using Action = search::GameAction;
using RAT = search::GameAction::RewardsActionType;
using expert::baseName;
using expert::cardName;
using expert::jname;

// Decision types STS_EXPERT_REPLAY_TYPES can enable. reward covers card,
// potion, relic and key rewards and chests; event covers Neow and the select
// screens events open.
const std::vector<std::string> kReplayTypes = {"path", "reward", "campfire", "shop", "bossrelic", "event"};

std::set<std::string> replayTypesFromEnv() {
    const char *value = std::getenv("STS_EXPERT_REPLAY_TYPES");
    const std::string spec = value && *value ? value : "all";
    if (spec == "all") return {kReplayTypes.begin(), kReplayTypes.end()};
    if (spec == "none") return {};
    std::set<std::string> types;
    std::istringstream in(spec);
    std::string type;
    while (std::getline(in, type, ',')) {
        if (std::find(kReplayTypes.begin(), kReplayTypes.end(), type) == kReplayTypes.end())
            throw std::runtime_error("STS_EXPERT_REPLAY_TYPES must be all, none, or a comma list of "
                                     "path,reward,campfire,shop,bossrelic,event (got " + spec + ")");
        types.insert(type);
    }
    return types;
}

std::string roomLetter(Room r) {
    switch (r) {
        case Room::MONSTER: return "M"; case Room::ELITE: return "E"; case Room::EVENT: return "?";
        case Room::SHOP: return "$"; case Room::TREASURE: return "T"; case Room::REST: return "R";
        case Room::BOSS: return "B"; default: return "-";
    }
}

std::multiset<std::string> names(const json &list, bool base) {
    std::multiset<std::string> out;
    for (const auto &c : list) out.insert(base ? baseName(c.get<std::string>()) : c.get<std::string>());
    return out;
}

// Plays the logged decisions of one expert run while they stay exact; the
// first decision that is not stops replay for the rest of the run.
class Replayer : expert::RunLog {
public:
    Replayer(const json &run, std::set<std::string> types)
        : RunLog(run), types_(std::move(types)), lastFloor_(run["floor_reached"].get<int>()) {
        if (types_.empty()) { stopped_ = true; stopFloor_ = 0; stopReason_ = "types none"; }
        // Logs before Run History Plus 1.x lack the key fields; a run that reached Act 4 took both keys.
        const bool reachedAct4 = lastFloor_ > 51;
        emeraldUnlogged_ = reachedAct4 && !run.contains("green_key_taken_log");
        sapphireUnlogged_ = reachedAct4 && !run.contains("blue_key_relic_skipped_log");
    }

    const char *step(GameContext &gc) {
        if (stopped_) return nullptr;
        if (gc.act > 3) return stop(gc, "act 4");
        if (!prepareFloor(gc)) return nullptr;
        switch (gc.screenState) {
            case ScreenState::MAP_SCREEN: return doMap(gc);
            case ScreenState::EVENT_SCREEN: return gc.curEvent == Event::NEOW ? doNeow(gc) : doEvent(gc);
            case ScreenState::REWARDS: return doRewards(gc);
            case ScreenState::BOSS_RELIC_REWARDS: return doBossRelic(gc);
            case ScreenState::CARD_SELECT: return doCardSelect(gc);
            case ScreenState::TREASURE_ROOM: return doTreasure(gc);
            case ScreenState::REST_ROOM: return doRest(gc);
            case ScreenState::SHOP_ROOM: return doShop(gc);
            default: return bot("other");
        }
    }

    json summary() const {
        return {{"types", json(std::vector<std::string>(types_.begin(), types_.end()))},
                {"stopFloor", stopFloor_}, {"stopReason", stopReason_}, {"replayed", replayed_},
                {"botScreens", bot_}, {"unopenedCardRewards", unopenedCardRewards_},
                {"potionsLeftBeltFull", potionsLeft_}};
    }

private:
    std::set<std::string> types_;
    int lastFloor_;
    // Take the key at its first offer (Emerald) or at the first chest with no logged relic (Sapphire).
    bool emeraldUnlogged_ = false, sapphireUnlogged_ = false;
    bool stopped_ = false;
    int stopFloor_ = -1;
    std::string stopReason_;
    std::map<std::string, int> replayed_, bot_;
    int unopenedCardRewards_ = 0, potionsLeft_ = 0;
    std::vector<int> pathX_[3];
    bool pathReady_[3] = {false, false, false};
    int preparedFloor_ = -1;
    std::vector<expert::SelectPick> pendingSelect_;
    std::vector<int> pendingEventIdx_;
    bool eventPlanned_ = false, shopChecked_ = false, purgePending_ = false;
    std::vector<std::string> pendingPurchases_;
    std::size_t bossRelicIdx_ = 0;

    bool on(const char *type) const { return types_.count(type) != 0; }

    const char *stop(const GameContext &gc, const std::string &why) {
        stopped_ = true;
        stopFloor_ = gc.floorNum;
        stopReason_ = why;
        return nullptr;
    }
    const char *done(const char *type) {
        ++replayed_[type];
        return "expert";
    }
    const char *bot(const char *type) {
        ++bot_[type];
        return nullptr;
    }

    // Load the logged decisions of the floor the run just entered, and check
    // that the room is the one the expert entered.
    bool prepareFloor(const GameContext &gc) {
        const int f = gc.floorNum;
        if (f == preparedFloor_) return true;
        preparedFloor_ = f;
        pendingSelect_.clear();
        pendingEventIdx_.clear();
        pendingPurchases_.clear();
        eventPlanned_ = shopChecked_ = purgePending_ = false;
        if (f > 0 && gc.curRoom != Room::BOSS && gc.curMapNodeY >= 0 && gc.curMapNodeY <= 14) {
            const auto logged = roomAt(f), engine = roomLetter(gc.curRoom);
            if (logged != engine) { stop(gc, "room " + engine + " vs log " + logged); return false; }
        }
        if (on("shop") && roomAt(f) == "$") {
            pendingPurchases_ = purchases[f];
            purgePending_ = !purges[f].empty();
            for (const auto &c : purges[f]) pendingSelect_.push_back({"remove", c});
        }
        if (on("campfire") && campfire.count(f))
            for (const auto &c : campfire[f])
                if (c.contains("data") && c["data"].is_string()) {
                    const auto key = c["key"].get<std::string>();
                    pendingSelect_.push_back({key == "PURGE" ? "remove" : "upgrade", c["data"].get<std::string>()});
                }
        return true;
    }

    const char *doMap(GameContext &gc) {
        if (!on("path")) return bot("path");
        if (gc.floorNum >= lastFloor_) return stop(gc, "expert log ends");
        const int act0 = gc.act - 1;
        if (!pathReady_[act0]) {
            if (!actPath(act0, *gc.map, pathX_[act0])) return stop(gc, "logged path not on the map (Winged Boots)");
            pathReady_[act0] = true;
        }
        int x = 0;
        if (gc.curMapNodeY != 14) {
            const int y = gc.curMapNodeY + 1;
            if (y >= (int)pathX_[act0].size()) return stop(gc, "logged path ends");
            x = pathX_[act0][y];
        }
        const Action a(x);
        if (!a.isValidAction(gc)) return stop(gc, "map move illegal");
        a.execute(gc);
        return done("path");
    }

    const char *doNeow(GameContext &gc) {
        if (!on("event")) return bot("event");
        const auto bonus = run.value("neow_bonus", std::string());
        const auto cost = run.value("neow_cost", std::string());
        int pick = -1;
        for (int i = 0; i < 4; ++i) {
            const auto &o = gc.info.neowRewards[i];
            // The log records a boss swap's cost as NONE.
            if (jname(o.r) == bonus && (o.r == Neow::Bonus::BOSS_RELIC || jname(o.d) == cost)) pick = i;
        }
        if (pick < 0)
            // The two-option blessing after a short previous run is not modeled.
            return stop(gc, bonus == "THREE_ENEMY_KILL" || bonus == "TEN_PERCENT_HP_BONUS"
                                ? "Neow mini blessing (not modeled)" : "Neow option not offered");
        if (run.contains("neow_bonus_log") && run["neow_bonus_log"].is_object()) {
            const auto &l = run["neow_bonus_log"];
            for (const auto &[k, kind] : {std::pair<const char *, const char *>{"cardsRemoved", "remove"},
                                          {"cardsUpgraded", "upgrade"}, {"cardsTransformed", "transform"},
                                          {"cardsObtained", "obtain"}})
                if (l.contains(k)) for (const auto &c : l[k]) pendingSelect_.push_back({kind, c.get<std::string>()});
        }
        const Action a(pick);
        if (!a.isValidAction(gc)) return stop(gc, "Neow option illegal");
        a.execute(gc);
        return done("event");
    }

    const char *doEvent(GameContext &gc) {
        if (!on("event")) return bot("event");
        const int f = gc.floorNum;
        if (!eventPlanned_) {
            eventPlanned_ = true;
            if (!events.count(f) || events[f].empty()) return stop(gc, "event not logged");
            const auto &e = events[f][0];
            const auto logged = e["event_name"].get<std::string>(), engine = expert::logEventName(gc.curEvent);
            if (logged != engine) return stop(gc, "event " + engine + " vs log " + logged);
            const auto why = expert::planEvent(e, gc, pendingEventIdx_, pendingSelect_);
            if (!why.empty()) return stop(gc, why);
            // Match and Keep, Lab and Bonfire Elementals: the log has no option sequence.
            if (pendingEventIdx_.empty()) return bot("event_unlogged");
        }
        if (pendingEventIdx_.empty()) {
            if (gc.curEvent == Event::MATCH_AND_KEEP || gc.curEvent == Event::LAB
                    || gc.curEvent == Event::BONFIRE_SPIRITS)
                return bot("event_unlogged");
            return stop(gc, "event plan exhausted");
        }
        const Action a(pendingEventIdx_.front());
        if (!a.isValidAction(gc)) return stop(gc, "event option illegal " + engineEvent(gc));
        pendingEventIdx_.erase(pendingEventIdx_.begin());
        a.execute(gc);
        return done("event");
    }

    static std::string engineEvent(const GameContext &gc) { return expert::logEventName(gc.curEvent); }

    const char *doRewards(GameContext &gc) {
        if (!on("reward")) return bot("reward");
        auto &r = gc.info.rewardsContainer;
        const int f = gc.floorNum;
        while (r.goldRewardCount > 0) Action(RAT::GOLD, 0).execute(gc);
        if (r.emeraldKey && (greenKeyFloor == f || emeraldUnlogged_)) {
            emeraldUnlogged_ = false;
            Action(RAT::KEY, 0).execute(gc);
        }
        const bool unloggedSapphire = sapphireUnlogged_ && relicsObtained[f].empty();
        if (r.sapphireKey && (blueKeyFloor == f || unloggedSapphire)) {
            // The key replaces the relic paired with it, the last one.
            if (!unloggedSapphire && (r.relicCount == 0 || jname(r.relics[r.relicCount - 1]) != blueKeyRelic))
                return stop(gc, "sapphire key relic differs");
            sapphireUnlogged_ = false;
            Action(RAT::KEY, 0).execute(gc);
            return done("reward");
        }
        if (r.relicCount > 0) {
            const auto name = jname(r.relics[0]);
            // Floor 0 relics come with the Neow pick.
            if (f > 0) {
                auto &logged = relicsObtained[f];
                auto it = std::find_if(logged.begin(), logged.end(), [&](const json &l) { return l["key"] == name; });
                if (it == logged.end()) return stop(gc, "reward relic " + name + " not logged");
                logged.erase(it);
            }
            Action(RAT::RELIC, 0).execute(gc);
            return done("reward");   // may open a screen
        }
        if (r.potionCount > 0) {
            auto &logged = potionsObtained[f];
            for (int i = r.potionCount - 1; i >= 0; --i) {
                const auto name = jname(r.potions[i]);
                auto it = std::find_if(logged.begin(), logged.end(), [&](const json &l) { return l["key"] == name; });
                if (it == logged.end()) continue;
                const Action a(RAT::POTION, i);
                if (!a.isValidAction(gc)) { ++potionsLeft_; continue; }
                logged.erase(it);
                a.execute(gc);
            }
        }
        auto &logged = cardChoices[f];
        int group = 0;
        while (gc.screenState == ScreenState::REWARDS && group < r.cardRewardCount) {
            const auto &offer = r.cardRewards[group];
            if (logged.empty()) {
                if (f == 0) {
                    // Neow card rewards: the pick is in neow_bonus_log.
                    int ci = -1;
                    for (auto it = pendingSelect_.begin(); it != pendingSelect_.end() && ci < 0; ++it) {
                        if (it->kind != "obtain") continue;
                        for (int i = 0; i < (int)offer.size(); ++i)
                            if (cardName(offer[i]) == it->card) { ci = i; pendingSelect_.erase(it); break; }
                        if (ci >= 0) break;
                    }
                    if (ci < 0) return stop(gc, "Neow card reward not logged");
                    Action(RAT::CARD, group, ci).execute(gc);
                    continue;
                }
                // Vanilla logs nothing for a card reward the player never opened.
                ++unopenedCardRewards_;
                ++group;
                continue;
            }
            std::multiset<std::string> engine, engineBase;
            for (const auto &c : offer) { engine.insert(cardName(c)); engineBase.insert(baseName(cardName(c))); }
            auto offered = [](const json &l, bool base) {
                auto set = names(l["not_picked"], base);
                const auto p = l["picked"].get<std::string>();
                if (p != "SKIP" && p != "Singing Bowl") set.insert(base ? baseName(p) : p);
                return set;
            };
            int hit = -1;
            for (int k = 0; k < (int)logged.size() && hit < 0; ++k) if (offered(logged[k], false) == engine) hit = k;
            // Egg relics show upgraded previews in the log.
            for (int k = 0; k < (int)logged.size() && hit < 0; ++k) if (offered(logged[k], true) == engineBase) hit = k;
            if (hit < 0) return stop(gc, "card offer differs");
            const auto pick = logged[hit]["picked"].get<std::string>();
            logged.erase(logged.begin() + hit);
            if (pick == "SKIP") { ++group; ++replayed_["reward"]; continue; }
            int ci = -1;
            if (pick == "Singing Bowl") {
                if (!gc.hasRelic(RelicId::SINGING_BOWL)) return stop(gc, "Singing Bowl not held");
                ci = 5;
            }
            for (int i = 0; i < (int)offer.size() && ci < 0; ++i) if (cardName(offer[i]) == pick) ci = i;
            for (int i = 0; i < (int)offer.size() && ci < 0; ++i) if (baseName(cardName(offer[i])) == baseName(pick)) ci = i;
            if (ci < 0) return stop(gc, "picked card not offered");
            Action(RAT::CARD, group, ci).execute(gc);
            ++replayed_["reward"];
        }
        if (gc.screenState == ScreenState::REWARDS) Action(RAT::SKIP).execute(gc);
        return done("reward");
    }

    const char *doBossRelic(GameContext &gc) {
        const auto idx = bossRelicIdx_++;
        if (!on("bossrelic")) return bot("bossrelic");
        if (idx >= bossRelics.size()) return stop(gc, "boss relic not logged");
        const auto &b = bossRelics[idx];
        std::multiset<std::string> engine;
        for (int i = 0; i < 3; ++i) engine.insert(jname(gc.info.bossRelics[i]));
        auto logged = names(b["not_picked"], false);
        const auto pick = b.value("picked", std::string("SKIP"));
        if (pick != "SKIP") logged.insert(pick);
        if (logged != engine) return stop(gc, "boss relic offer differs");
        int choice = 3;
        for (int i = 0; i < 3; ++i) if (jname(gc.info.bossRelics[i]) == pick) choice = i;
        Action(choice).execute(gc);
        return done("bossrelic");
    }

    const char *doCardSelect(GameContext &gc) {
        const auto kind = expert::selectKind(gc.info.selectScreenType);
        bool any = false;
        for (auto it = pendingSelect_.begin(); it != pendingSelect_.end(); ++it) {
            if (it->kind != kind) continue;
            any = true;
            const auto &cards = gc.info.toSelectCards;
            int idx = -1;
            for (int i = 0; i < (int)cards.size() && idx < 0; ++i) if (cardName(cards[i].card) == it->card) idx = i;
            for (int i = 0; i < (int)cards.size() && idx < 0; ++i)
                if (baseName(cardName(cards[i].card)) == baseName(it->card)) idx = i;
            if (idx < 0) continue;
            pendingSelect_.erase(it);
            Action(idx).execute(gc);
            return done("select");
        }
        // Bottles, Astrolabe and other picks the log does not record.
        if (!any) return bot("select_unlogged");
        return stop(gc, "logged " + kind + " card not in deck");
    }

    const char *doTreasure(GameContext &gc) {
        if (!on("reward")) return bot("reward");
        // A chest with no logged relic (and no sapphire key) was left closed.
        const bool open = !relicsObtained[gc.floorNum].empty() || blueKeyFloor == gc.floorNum || sapphireUnlogged_;
        Action(open ? 0 : 1).execute(gc);
        return done("reward");
    }

    const char *doRest(GameContext &gc) {
        if (!on("campfire")) return bot("campfire");
        auto &logged = campfire[gc.floorNum];
        if (logged.empty()) return stop(gc, "campfire not logged");
        const auto key = logged.front()["key"].get<std::string>();
        const int idx = key == "REST" ? 0 : key == "SMITH" ? 1 : key == "RECALL" ? 2 : key == "LIFT" ? 3
                      : key == "PURGE" ? 4 : key == "DIG" ? 5 : -1;
        if (idx < 0) return stop(gc, "campfire option " + key);
        const Action a(idx);
        if (!a.isValidAction(gc)) return stop(gc, "campfire " + key + " illegal");
        logged.erase(logged.begin());
        a.execute(gc);
        return done("campfire");
    }

    const char *doShop(GameContext &gc) {
        if (!on("shop")) return bot("shop");
        const int f = gc.floorNum;
        auto &s = gc.info.shop;
        if (!shopChecked_) {
            shopChecked_ = true;
            if (shopContents.count(f) && !shopShelvesMatch(gc, shopContents[f])) return stop(gc, "shop shelves differ");
        }
        while (!pendingPurchases_.empty()) {
            const auto item = pendingPurchases_.front();
            std::optional<Action> a;
            for (int i = 0; i < 7 && !a; ++i)
                if (s.cardPrice(i) != -1 && cardName(s.cards[i]) == item) a = Action(RAT::CARD, i);
            for (int i = 0; i < 7 && !a; ++i)
                if (s.cardPrice(i) != -1 && baseName(cardName(s.cards[i])) == baseName(item)) a = Action(RAT::CARD, i);
            for (int i = 0; i < 3 && !a; ++i)
                if (s.relicPrice(i) != -1 && jname(s.relics[i]) == item) a = Action(RAT::RELIC, i);
            for (int i = 0; i < 3 && !a; ++i)
                if (s.potionPrice(i) != -1 && jname(s.potions[i]) == item) a = Action(RAT::POTION, i);
            if (!a) return stop(gc, "shop item " + item + " not offered");
            if (!a->isValidAction(gc)) return stop(gc, "shop purchase " + item + " unaffordable or belt full");
            pendingPurchases_.erase(pendingPurchases_.begin());
            a->execute(gc);
            ++replayed_["shop"];
            if (gc.screenState != ScreenState::SHOP_ROOM) return "expert";   // the relic opened a screen
        }
        if (purgePending_) {
            purgePending_ = false;
            const Action a(RAT::CARD_REMOVE);
            if (!a.isValidAction(gc)) return stop(gc, "shop removal unaffordable");
            a.execute(gc);
            return done("shop");
        }
        Action(RAT::SKIP).execute(gc);
        return done("shop");
    }

    // The log lists what was left on the shelves after this floor's purchases.
    bool shopShelvesMatch(const GameContext &gc, const json &l) {
        const auto &s = gc.info.shop;
        std::multiset<std::string> ec, er, ep;
        for (int i = 0; i < 7; ++i) if (s.cards[i].getId() != CardId::INVALID) ec.insert(baseName(cardName(s.cards[i])));
        for (int i = 0; i < 3; ++i) { er.insert(jname(s.relics[i])); ep.insert(jname(s.potions[i])); }
        auto lc = names(l["cards"], true), lr = names(l["relics"], false), lp = names(l["potions"], false);
        for (const auto &item : purchases[gc.floorNum]) {
            if (ec.count(baseName(item)) > lc.count(baseName(item))) lc.insert(baseName(item));
            else if (er.count(item) > lr.count(item)) lr.insert(item);
            else if (ep.count(item) > lp.count(item)) lp.insert(item);
        }
        auto subset = [](const std::multiset<std::string> &a, const std::multiset<std::string> &b) {
            for (const auto &x : a) if (a.count(x) > b.count(x)) return false;
            return true;
        };
        return subset(lc, ec) && subset(lr, er) && subset(lp, ep);
    }
};

}  // namespace

int expertReplayGen(const std::string &runFile, const std::string &output) {
    if (!g_collectKeys || g_stopAfterAct != 0 || g_forceRelic != sts::RelicId::INVALID)
        throw std::runtime_error("expertreplay requires the full-run Heart objective, keys on, no forced relic");
    if (t_oocDecisionOverride || t_oocContinuation || t_oocHypotheticalStep)
        throw std::runtime_error("expertreplay requires an unowned real driver context");
    if (std::filesystem::exists(output) && std::filesystem::file_size(output) > 0)
        throw std::runtime_error("expertreplay output " + output + " already exists");
    std::ifstream in(runFile);
    if (!in) throw std::runtime_error("cannot read " + runFile);
    const json run = json::parse(in);
    if (run.value("character_chosen", std::string()) != "IRONCLAD" || run.value("ascension_level", 0) != 20)
        throw std::runtime_error("expertreplay needs an Ironclad A20 run");
    const auto seedPlayed = run["seed_played"].get<std::string>();
    const auto seed = static_cast<std::uint64_t>(std::stoll(seedPlayed));
    const auto types = replayTypesFromEnv();
    Replayer replayer(run, types);
    t_oocDecisionOverride = [&](GameContext &gc) { return replayer.step(gc); };
    struct Reset { ~Reset() { t_oocDecisionOverride = nullptr; } } reset;
    trainingRunStart();
    const auto result = runFullRunOOC(seed, 10000, 20, deployedRestV(), true);
    if (!trainingRunValid(true)) throw std::runtime_error("expert replay run failed simulator integrity");
    const json out = {{"schema", "expert-replay-v1"}, {"runFile", std::filesystem::path(runFile).filename().string()},
        {"playId", run.value("play_id", std::string())}, {"seedPlayed", seedPlayed}, {"engineSeed", seed},
        {"heartKilled", result.won}, {"finalFloor", result.floor}, {"finalAct", result.act},
        {"finalHp", result.hpEnd}, {"maxHp", result.maxHp}, {"fightsLost", result.fightsLost},
        {"deathCombat", result.deathCombat}, {"deathEncounter", result.deathEncounter}, {"sec", result.sec},
        {"expert", {{"victory", run.value("victory", false)}, {"floorReached", run["floor_reached"]}}},
        {"replay", replayer.summary()}, {"producerSha", trainingExecutableGitSha()},
        {"policy", effectiveOocPolicySpecification()}, {"provenance", heartOutcomeRunProvenance()}};
    std::ofstream f(output);
    if (!f) throw std::runtime_error("cannot write " + output);
    f << out.dump() << '\n';
    if (!f) throw std::runtime_error("write failed: " + output);
    std::cout << "[expertreplay] seed=" << seedPlayed << " heartKilled=" << result.won << " floor=" << result.floor
              << " stopFloor=" << out["replay"]["stopFloor"] << " stop=" << out["replay"]["stopReason"] << std::endl;
    return 0;
}

}  // namespace one_combat
