#include "expert_replay.h"
#include "driver_shared.h"
#include "expert_run_log.h"
#include "heart_outcome_capture.h"
#include "run_driver.h"

#include <algorithm>
#include <ctime>
#include <random>
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

    bool stopped() const { return stopped_; }
    // expertfights: a shop whose shelves differ from the log only stops the
    // replay when a logged purchase is not offered (the deck stays the expert's).
    void allowShelfDifferences() { lenientShelves_ = true; }

    json summary() const {
        return {{"types", json(std::vector<std::string>(types_.begin(), types_.end()))},
                {"stopFloor", stopFloor_}, {"stopReason", stopReason_}, {"replayed", replayed_},
                {"botScreens", bot_}, {"unopenedCardRewards", unopenedCardRewards_},
                {"potionsLeftBeltFull", potionsLeft_}, {"shelvesDiffered", shelvesDiffered_},
                {"loggedPotionsNotOffered", loggedPotionsNotOffered()}};
    }

    // Logged potions of floors with a reward screen that were neither taken nor
    // left for a full belt: the drop differed from the log (e.g. after the run
    // continued on another copy's combat streams). Potions logged from an event
    // on such a floor count here too.
    int loggedPotionsNotOffered() const {
        int n = 0;
        for (int f : rewardFloors_) {
            const auto it = potionsObtained.find(f);
            const auto left = leftAt_.find(f);
            if (it != potionsObtained.end())
                n += std::max(0, (int)it->second.size() - (left == leftAt_.end() ? 0 : left->second));
        }
        return n;
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
    int unopenedCardRewards_ = 0, potionsLeft_ = 0, shelvesDiffered_ = 0;
    bool lenientShelves_ = false;
    std::set<int> rewardFloors_;
    std::map<int, int> leftAt_;
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
        rewardFloors_.insert(f);
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
                if (!a.isValidAction(gc)) { ++potionsLeft_; ++leftAt_[f]; continue; }
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
            if (shopContents.count(f) && !shopShelvesMatch(gc, shopContents[f])) {
                if (!lenientShelves_) return stop(gc, "shop shelves differ");
                ++shelvesDiffered_;
            }
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

// The expert's logged state around each fight: HP and max HP at the end of
// every floor, the logged outcome of each fight floor, and the potions held
// entering each floor. The inventory needs Run History Plus logs (potion names
// per use and discard); it is rebuilt from potions obtained (rewards, events,
// Neow, Alchemize, Entropic Brew, shop) minus uses and discards, and is known
// only up to the first floor where a used or discarded potion was not held or
// more than four are held.
struct ExpertCombatLog {
    std::vector<int> hp, maxHp;
    std::map<int, json> fight;
    std::map<int, int> uses, fightsOnFloor;
    std::map<int, std::vector<std::string>> useNames, potionsAt, relicsAt;
    int potionsKnownThrough = -1;
    std::string potionsUnknownWhy = "no Run History Plus potion logs";
    int floorReached = 0;
    bool victory = false;
    std::string killedBy;

    static bool isPotion(const std::string &name) {
        const auto p = json(name).get<Potion>();
        return p != Potion::INVALID && p != Potion::EMPTY_POTION_SLOT;
    }

    explicit ExpertCombatLog(const json &run) {
        for (const auto &h : run["current_hp_per_floor"]) hp.push_back(h.get<int>());
        for (const auto &h : run["max_hp_per_floor"]) maxHp.push_back(h.get<int>());
        for (const auto &d : run["damage_taken"]) {
            fight[d["floor"].get<int>()] = d;
            ++fightsOnFloor[d["floor"].get<int>()];
        }
        for (const auto &u : run["potions_floor_usage"]) ++uses[u.get<int>()];
        for (const auto &r : run["relics_obtained"]) relicsAt[r["floor"].get<int>()].push_back(r["key"].get<std::string>());
        floorReached = run["floor_reached"].get<int>();
        victory = run.value("victory", false);
        if (run.contains("killed_by") && run["killed_by"].is_string()) killedBy = run["killed_by"].get<std::string>();
        const auto used = run.value("potion_use_per_floor", json());
        const auto discarded = run.value("potion_discard_per_floor", json());
        if (!used.is_array() || !discarded.is_array()) return;
        for (std::size_t i = 0; i < used.size(); ++i)
            for (const auto &n : used[i]) useNames[(int)i + 1].push_back(n.get<std::string>());
        std::map<int, std::vector<std::string>> gains;
        for (const auto &o : run.value("potions_obtained", json::array()))
            gains[o["floor"].get<int>()].push_back(o["key"].get<std::string>());
        for (const char *k : {"potions_obtained_alchemize", "potions_obtained_entropic_brew"}) {
            const auto per = run.value(k, json::array());
            for (std::size_t i = 0; i < per.size(); ++i)
                for (const auto &n : per[i]) gains[(int)i + 1].push_back(n.get<std::string>());
        }
        const auto &ip = run["items_purchased"];
        const auto &ipf = run["item_purchase_floors"];
        for (std::size_t i = 0; i < ip.size() && i < ipf.size(); ++i)
            if (isPotion(ip[i].get<std::string>())) gains[ipf[i].get<int>()].push_back(ip[i].get<std::string>());
        std::multiset<std::string> held(gains[0].begin(), gains[0].end());
        potionsUnknownWhy.clear();
        for (int f = 1; f <= (int)hp.size(); ++f) {
            potionsAt[f] = std::vector<std::string>(held.begin(), held.end());
            potionsKnownThrough = f;
            for (const auto &n : gains[f]) held.insert(n);
            auto take = [&](const std::string &n) {
                const auto it = held.find(n);
                if (it == held.end()) return false;
                held.erase(it);
                return true;
            };
            bool ok = true;
            for (const auto &n : useNames[f]) ok = take(n) && ok;
            if (f - 1 < (int)discarded.size())
                for (const auto &n : discarded[f - 1]) ok = take(n.get<std::string>()) && ok;
            if (!ok || held.size() > 4) {
                potionsUnknownWhy = "inconsistent after floor " + std::to_string(f);
                break;
            }
        }
    }
    bool potionsKnown(int f) const { return f <= potionsKnownThrough && potionsAt.count(f); }
};

std::vector<std::string> potionNames(const std::array<Potion, 5> &potions) {
    std::vector<std::string> out;
    for (auto p : potions)
        if (p != Potion::EMPTY_POTION_SLOT && p != Potion::INVALID) out.push_back(jname(p));
    std::sort(out.begin(), out.end());
    return out;
}

std::vector<std::string> minus(const std::vector<std::string> &a, const std::vector<std::string> &b) {
    std::multiset<std::string> rest(b.begin(), b.end());
    std::vector<std::string> out;
    for (const auto &x : a) {
        const auto it = rest.find(x);
        if (it == rest.end()) out.push_back(x);
        else rest.erase(it);
    }
    return out;
}

std::uint64_t mix(std::uint64_t x) {
    x += 0x9E3779B97F4A7C15ULL;
    x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
    x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
    return x ^ (x >> 31);
}

double threadCpuSeconds() {
    timespec ts{};
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}

// expertfights: at each fight inside the exact-replay prefix, set HP and max HP
// to the expert's, and with expertPotions (STS_EXPERT_FIGHTS_POTIONS=expert)
// also the potions where the log determines them. By default the bot keeps its
// own potions: they follow its use in earlier fights and the expert's pickups,
// so a potion it drinks is not refilled at the next fight. At fights with
// the logged encounter (hallways included), play K detached copies with the production
// Silver agent: copy 0 keeps the game's battle seed (the expert's deal), copies
// 1..K-1 get a fresh battle seed and fresh persistent combat streams. The run
// continues from copy 0 if it won, else from the first copy that won (seed
// restored), else the driver plays the fight itself.
class FightReplayer {
public:
    // Research arm (STS_EXPERT_FIGHTS_ARMS, default none): a '+'-joined set of `pp` (prior playouts in elite
    // rooms, as STS_SILVER_PRIOR_PLAYOUT_ELITE=1), `flat<N>` (flat N simulations at every root, singletons
    // searched, no learned stop), `potw<W>` (held-potion leaf weight W instead of 11, integer), `rpl<K>` (K
    // greedy playouts per leaf, 2..64, other rollout settings production), `gsh<K>` (Gumbel root with K
    // sampled root edges, 2..64, SilverSearcher::searchGumbelRoot; needs flat<N>), `mb<M>` (max backup with
    // minimum M visits, as STS_SILVER_MAX_BACKUP=M but for this arm's searches only, 1..1000000) and `cnp` /
    // `cnp<P>` (the native combat net's root prior in place of g7f_E's, as STS_SILVER_COMBATNET_PRIOR=1, at softmax
    // temperature P/100, P in 10..400, or STS_SILVER_COMBATNET_PRIOR_TEMP for bare `cnp`; needs
    // STS_SILVER_COMBATNET_PRIOR_MODEL).
    struct Arm {
        std::string name;
        bool priorPlayoutElite = false;
        std::int64_t flat = 0;
        double potionWeight = -1;   // < 0: production
        int rolloutsPerLeaf = 0;    // 0: production
        int gumbelK = 0;            // 0: plain search
        int maxBackup = 0;          // 0: production (STS_SILVER_MAX_BACKUP of the process)
        bool combatNetPrior = false;
        double combatNetTemp = 0;   // > 0: the arm's prior temperature
    };
    // armCopies (STS_EXPERT_FIGHTS_ARM_COPIES, default empty = all): floor -> copies to play (empty set = all
    // copies of that floor). When set, only the listed floors are arm fights, and on them production and each arm
    // play only the listed copies in full (production still plays the copies the main line needs).
    FightReplayer(const json &run, Replayer &replayer, int replicates, int maxAct, bool expertPotions,
                  std::vector<Arm> arms = {}, std::set<std::string> armRooms = {}, int armK = 0,
                  std::map<int, std::set<int>> armCopies = {})
        : log_(run), replayer_(replayer), k_(replicates), maxAct_(maxAct), expertPotions_(expertPotions),
          arms_(std::move(arms)), armRooms_(std::move(armRooms)), armK_(armK), armCopies_(std::move(armCopies)) {}

    bool onBattle(GameContext &gc, search::ScumSearchAgent2 &agent) {
        if (replayer_.stopped() || gc.act > maxAct_) return false;
        const int f = gc.floorNum;
        const std::string engineEnc = jname(gc.info.encounter);
        const auto lf = log_.fight.find(f);
        const std::string loggedEnc = lf == log_.fight.end() ? "" : lf->second["enemies"].get<std::string>();
        json sync = {{"floor", f}, {"act", gc.act}, {"room", roomLetter(gc.curRoom)}, {"encounter", engineEnc},
                     {"loggedEncounter", loggedEnc}, {"engineHp", gc.curHp}, {"engineMaxHp", gc.maxHp},
                     {"enginePotions", potionNames(gc.potions)}};
        bool hpSynced = false, potionsSynced = false;
        if (f >= 2 && f - 2 < (int)log_.hp.size() && log_.hp[f - 2] > 0) {
            gc.maxHp = log_.maxHp[f - 2];
            gc.curHp = std::min(log_.hp[f - 2], gc.maxHp);
            hpSynced = true;
        }
        const bool namesKnown = log_.potionsKnown(f)
            && std::all_of(log_.potionsAt.at(f).begin(), log_.potionsAt.at(f).end(), ExpertCombatLog::isPotion);
        if (log_.potionsKnown(f)) sync["expertPotions"] = log_.potionsAt.at(f);
        if (expertPotions_ && namesKnown && (int)log_.potionsAt.at(f).size() <= gc.potionCapacity) {
            const auto &names = log_.potionsAt.at(f);
            gc.potions.fill(Potion::EMPTY_POTION_SLOT);
            for (std::size_t i = 0; i < names.size(); ++i) gc.potions[i] = json(names[i]).get<Potion>();
            gc.potionCount = (int)names.size();
            potionsSynced = true;
        }
        sync["hpSynced"] = hpSynced;
        sync["potionsSynced"] = potionsSynced;
        sync["hp"] = gc.curHp;
        sync["maxHp"] = gc.maxHp;
        sync["potions"] = potionNames(gc.potions);
        syncs_.push_back(sync);
        if (!hpSynced || loggedEnc != engineEnc) return false;

        json rec = sync;
        rec.erase("enginePotions");
        rec["potionsUnknownWhy"] = potionsSynced || !expertPotions_ ? "" : !log_.potionsKnown(f) ? log_.potionsUnknownWhy
                                     : namesKnown ? "more than the engine's slots" : "unknown potion name";
        int upgrades = 0;
        for (const auto &c : gc.deck.cards) upgrades += c.getUpgraded() > 0;
        rec["deck"] = gc.deck.size();
        rec["upgrades"] = upgrades;
        std::vector<std::string> relics;
        for (const auto &r : gc.relics.relics) relics.push_back(jname(r.id));
        rec["relics"] = relics;
        const auto &lfight = lf->second;
        // Two logged fights on one floor (Colosseum): the log keeps the last one
        // and the floor's exit HP covers both; analyze.py drops such fights.
        rec["loggedFightsOnFloor"] = log_.fightsOnFloor.at(f);
        rec["expert"] = {{"received", lfight["damage"]}, {"turns", lfight["turns"]},
                         {"exitHp", f - 1 < (int)log_.hp.size() ? json(log_.hp[f - 1]) : json()},
                         {"died", !log_.victory && f == log_.floorReached && log_.killedBy == loggedEnc},
                         {"potionsUsed", log_.uses.count(f) ? log_.uses.at(f) : 0},
                         {"potionNamesUsed", log_.useNames.count(f) ? json(log_.useNames.at(f)) : json()},
                         {"relicsObtained", log_.relicsAt.count(f) ? json(log_.relicsAt.at(f)) : json::array()}};
        const auto entryPotions = potionNames(gc.potions);
        // Copy r from this state: production settings, or arm `arm` (index into arms_; research, see Arm).
        auto playCopy = [&](int r, const Arm *arm, std::optional<GameContext> *winner) {
            GameContext copy = detachedCounterfactualCopy(gc);
            if (r > 0) {
                std::mt19937_64 rng(mix(gc.seed ^ mix(f * 1000003ULL + r)));
                for (auto stream : {&copy.aiRng, &copy.cardRandomRng, &copy.miscRng, &copy.monsterHpRng,
                                    &copy.potionRng, &copy.shuffleRng}) {
                    const auto counter = stream->counter;
                    *stream = sts::Random(rng());
                    stream->counter = counter;
                }
                copy.seed = rng();
            }
            search::ScumSearchAgent2 a;
            a.simulationCountBase = arm && arm->flat > 0 ? arm->flat : agent.simulationCountBase;
            a.rng = std::default_random_engine(static_cast<unsigned>(mix(gc.seed + 7919ULL * f + r)));
            if (arm && arm->flat > 0)
                search::g_nativeSilverBudgetOverride = search::NativeSilverBudgetOverride{
                    search::NativeSilverBudgetOverride::Policy::Flat, false};
            if (arm && arm->priorPlayoutElite) search::g_nativeSilverPriorPlayoutEliteOverride = true;
            if (arm && arm->potionWeight >= 0) search::g_nativeSilverPotionWeightOverride = arm->potionWeight;
            if (arm && arm->rolloutsPerLeaf > 0) search::g_nativeSilverRolloutsPerLeafOverride = arm->rolloutsPerLeaf;
            if (arm && arm->maxBackup > 0) search::g_nativeSilverMaxBackupOverride = arm->maxBackup;
            if (arm && arm->combatNetPrior) search::g_nativeSilverCombatNetPriorOverride = true;
            if (arm && arm->combatNetTemp > 0) search::g_nativeSilverCombatNetPriorTempOverride = arm->combatNetTemp;
            if (arm && arm->gumbelK > 0) {
                search::SilverSearcher::GumbelRoot g;
                g.k = arm->gumbelK;
                search::g_nativeSilverGumbelRootOverride = g;
            }
            struct ArmReset { ~ArmReset() { search::g_nativeSilverBudgetOverride.reset();
                                            search::g_nativeSilverPriorPlayoutEliteOverride.reset();
                                            search::g_nativeSilverPotionWeightOverride.reset();
                                            search::g_nativeSilverRolloutsPerLeafOverride.reset();
                                            search::g_nativeSilverGumbelRootOverride.reset();
                                            search::g_nativeSilverMaxBackupOverride.reset();
                                            search::g_nativeSilverCombatNetPriorOverride.reset();
                                            search::g_nativeSilverCombatNetPriorTempOverride.reset(); } } armReset;
            BattleContext bc{};
            const double t0 = threadCpuSeconds();
            a.playoutBattle(copy, bc);
            const double cpu = threadCpuSeconds() - t0;
            const bool decided = bc.outcome != Outcome::UNDECIDED;
            const bool won = bc.outcome == Outcome::PLAYER_VICTORY;
            const bool valid = trainingRunValid(decided);
            const auto exitPotions = potionNames(bc.potions);
            if (won) bc.exitBattle(copy);
            json rep = {{"r", r}, {"won", won}, {"valid", valid}, {"exitHp", won ? copy.curHp : 0},
                        {"exitMaxHp", copy.maxHp}, {"turns", bc.turn}, {"cpu", cpu},
                        {"potionsUsed", minus(entryPotions, exitPotions)},
                        {"potionsGained", minus(exitPotions, entryPotions)},
                        {"decisions", search::g_nativeSilverCombatStats.decisions},
                        {"simulations", search::g_nativeSilverCombatStats.simulations},
                        {"gumbelRoots", search::g_nativeSilverCombatStats.gumbelRoots},
                        {"combatNetPriors", search::g_nativeSilverCombatStats.combatNetPriors}};
            if (won && winner && !*winner) {
                copy.seed = gc.seed;
                *winner = std::move(copy);
            }
            return rep;
        };
        json reps = json::array();
        std::optional<GameContext> next;
        int continuedFrom = -1;
        // With research arms (STS_EXPERT_FIGHTS_ARMS) only fights in armRooms_ play copies 0..armK_-1 in full,
        // production and each arm on the same copy seeds; any other copy is played only until the first win (the
        // main line continues from the first winning copy either way, so it is the same as without arms).
        const bool armFight = !arms_.empty() && armRooms_.count(std::to_string(gc.act) + roomLetter(gc.curRoom))
            && (armCopies_.empty() || armCopies_.count(f));
        const int full = arms_.empty() ? k_ : armFight ? armK_ : 0;
        auto selected = [&](int r) {
            if (armCopies_.empty()) return true;
            const auto it = armCopies_.find(f);
            return it != armCopies_.end() && (it->second.empty() || it->second.count(r));
        };
        for (int r = 0; r < k_; ++r) {
            if (next && (r >= full || !selected(r))) continue;
            const bool hadWinner = next.has_value();
            reps.push_back(playCopy(r, nullptr, &next));
            if (!hadWinner && next) continuedFrom = r;
        }
        if (armFight) {
            json armReps = json::object();
            for (const auto &arm : arms_) {
                json ar = json::array();
                for (int r = 0; r < armK_; ++r)
                    if (selected(r)) ar.push_back(playCopy(r, &arm, nullptr));
                armReps[arm.name] = ar;
            }
            rec["arms"] = armReps;
        }
        rec["replicates"] = reps;
        rec["continuedFrom"] = continuedFrom;
        fights_.push_back(rec);
        if (!next) return false;
        gc = std::move(*next);
        return true;
    }

    json fights() const { return fights_; }
    json syncs() const { return syncs_; }
    json potionLog() const {
        return {{"knownThroughFloor", log_.potionsKnownThrough}, {"unknownWhy", log_.potionsUnknownWhy}};
    }

private:
    ExpertCombatLog log_;
    Replayer &replayer_;
    int k_, maxAct_;
    bool expertPotions_;
    std::vector<Arm> arms_;
    std::set<std::string> armRooms_;
    int armK_;
    std::map<int, std::set<int>> armCopies_;
    json fights_ = json::array(), syncs_ = json::array();
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

int expertFightsGen(const std::string &runFile, const std::string &output) {
    if (!g_collectKeys || g_stopAfterAct != 0 || g_forceRelic != sts::RelicId::INVALID)
        throw std::runtime_error("expertfights requires the full-run Heart objective, keys on, no forced relic");
    if (t_oocDecisionOverride || t_oocContinuation || t_oocHypotheticalStep || t_battleOverride)
        throw std::runtime_error("expertfights requires an unowned real driver context");
    if (std::filesystem::exists(output) && std::filesystem::file_size(output) > 0)
        throw std::runtime_error("expertfights output " + output + " already exists");
    auto envInt = [](const char *name, int def, int lo, int hi) {
        const char *v = std::getenv(name);
        const int x = v && *v ? std::atoi(v) : def;
        if (x < lo || x > hi) throw std::runtime_error(std::string(name) + " out of range");
        return x;
    };
    const int replicates = envInt("STS_EXPERT_FIGHTS_REPLICATES", 4, 1, 64);
    const int maxAct = envInt("STS_EXPERT_FIGHTS_MAX_ACT", 3, 1, 3);
    const char *pm = std::getenv("STS_EXPERT_FIGHTS_POTIONS");
    const std::string potionMode = pm && *pm ? pm : "own";
    if (potionMode != "own" && potionMode != "expert")
        throw std::runtime_error("STS_EXPERT_FIGHTS_POTIONS must be own or expert");
    std::ifstream in(runFile);
    if (!in) throw std::runtime_error("cannot read " + runFile);
    const json run = json::parse(in);
    if (run.value("character_chosen", std::string()) != "IRONCLAD" || run.value("ascension_level", 0) != 20)
        throw std::runtime_error("expertfights needs an Ironclad A20 run");
    const auto seedPlayed = run["seed_played"].get<std::string>();
    const auto seed = static_cast<std::uint64_t>(std::stoll(seedPlayed));
    Replayer replayer(run, {kReplayTypes.begin(), kReplayTypes.end()});
    replayer.allowShelfDifferences();
    // Research (default off): STS_EXPERT_FIGHTS_ARMS=<arm>[,<arm>...] (FightReplayer::Arm) plays every fight whose
    // act and room are in STS_EXPERT_FIGHTS_ARM_ROOMS (e.g. 2E,2B; required) STS_EXPERT_FIGHTS_ARM_REPLICATES
    // (default K) times under production and each arm, on the same copy seeds.
    std::vector<FightReplayer::Arm> arms;
    std::set<std::string> armRooms;
    auto split = [](const std::string &v, char sep) {
        std::vector<std::string> out;
        std::stringstream ss(v);
        for (std::string t; std::getline(ss, t, sep);) out.push_back(t);
        return out;
    };
    if (const char *v = std::getenv("STS_EXPERT_FIGHTS_ARMS"); v && *v) {
        for (const auto &name : split(v, ',')) {
            FightReplayer::Arm arm{name};
            for (const auto &t : split(name, '+')) {
                if (t == "pp") arm.priorPlayoutElite = true;
                else if (t == "cnp") arm.combatNetPrior = true;
                else if (t.size() > 3 && t.size() <= 6 && t.rfind("cnp", 0) == 0
                         && t.find_first_not_of("0123456789", 3) == std::string::npos) {
                    const int p = std::stoi(t.substr(3));
                    if (p < 10 || p > 400) throw std::runtime_error("STS_EXPERT_FIGHTS_ARMS: cnp<P> needs P in 10..400");
                    arm.combatNetPrior = true;
                    arm.combatNetTemp = p / 100.0;
                }
                else if (t.size() > 4 && t.rfind("flat", 0) == 0
                         && t.find_first_not_of("0123456789", 4) == std::string::npos) arm.flat = std::stoll(t.substr(4));
                else if (t.size() > 4 && t.rfind("potw", 0) == 0 && t.size() <= 7
                         && t.find_first_not_of("0123456789", 4) == std::string::npos) arm.potionWeight = std::stoi(t.substr(4));
                else if (t.size() > 3 && t.size() <= 5 && t.rfind("rpl", 0) == 0
                         && t.find_first_not_of("0123456789", 3) == std::string::npos) arm.rolloutsPerLeaf = std::stoi(t.substr(3));
                else if (t.size() > 3 && t.size() <= 5 && t.rfind("gsh", 0) == 0
                         && t.find_first_not_of("0123456789", 3) == std::string::npos) arm.gumbelK = std::stoi(t.substr(3));
                else if (t.size() > 2 && t.size() <= 9 && t.rfind("mb", 0) == 0
                         && t.find_first_not_of("0123456789", 2) == std::string::npos) arm.maxBackup = std::stoi(t.substr(2));
                else throw std::runtime_error("STS_EXPERT_FIGHTS_ARMS: unknown arm part " + t);
            }
            if (arm.flat < 0 || arm.flat > 1000000) throw std::runtime_error("STS_EXPERT_FIGHTS_ARMS: flat out of range");
            if (arm.rolloutsPerLeaf != 0 && (arm.rolloutsPerLeaf < 2 || arm.rolloutsPerLeaf > 64))
                throw std::runtime_error("STS_EXPERT_FIGHTS_ARMS: rpl out of range (2..64)");
            if (arm.gumbelK != 0 && (arm.gumbelK < 2 || arm.gumbelK > 64))
                throw std::runtime_error("STS_EXPERT_FIGHTS_ARMS: gsh out of range (2..64)");
            if (arm.maxBackup < 0 || arm.maxBackup > 1000000)
                throw std::runtime_error("STS_EXPERT_FIGHTS_ARMS: mb out of range (1..1000000)");
            if (arm.gumbelK > 0 && arm.flat == 0)
                throw std::runtime_error("STS_EXPERT_FIGHTS_ARMS: gsh needs flat<N>");
            arms.push_back(arm);
        }
        const char *rooms = std::getenv("STS_EXPERT_FIGHTS_ARM_ROOMS");
        if (!rooms || !*rooms) throw std::runtime_error("STS_EXPERT_FIGHTS_ARMS requires STS_EXPERT_FIGHTS_ARM_ROOMS");
        for (const auto &t : split(rooms, ',')) {
            if (t.size() != 2 || t[0] < '1' || t[0] > '3' || std::string("MEB?$T").find(t[1]) == std::string::npos)
                throw std::runtime_error("STS_EXPERT_FIGHTS_ARM_ROOMS: bad entry " + t);
            armRooms.insert(t);
        }
    } else if (const char *rooms = std::getenv("STS_EXPERT_FIGHTS_ARM_ROOMS"); rooms && *rooms) {
        throw std::runtime_error("STS_EXPERT_FIGHTS_ARM_ROOMS requires STS_EXPERT_FIGHTS_ARMS");
    }
    const int armK = envInt("STS_EXPERT_FIGHTS_ARM_REPLICATES", replicates, 1, replicates);
    // Research (default unset = every arm fight, every copy): STS_EXPERT_FIGHTS_ARM_COPIES=<floor>[:<copy>],...
    // limits the arm fights to the listed floors and, for floor:copy entries, to those copies (a bare floor = all
    // copies), so one long fight's copies can run in separate processes. Copy seeds depend only on (seed, floor,
    // copy), so a copy played alone equals the same copy played with the others.
    std::map<int, std::set<int>> armCopies;
    if (const char *v = std::getenv("STS_EXPERT_FIGHTS_ARM_COPIES"); v && *v) {
        if (arms.empty()) throw std::runtime_error("STS_EXPERT_FIGHTS_ARM_COPIES requires STS_EXPERT_FIGHTS_ARMS");
        auto num = [](const std::string &t, int lo, int hi) {
            if (t.empty() || t.size() > 3 || t.find_first_not_of("0123456789") != std::string::npos)
                throw std::runtime_error("STS_EXPERT_FIGHTS_ARM_COPIES: bad entry " + t);
            const int x = std::stoi(t);
            if (x < lo || x > hi) throw std::runtime_error("STS_EXPERT_FIGHTS_ARM_COPIES: out of range " + t);
            return x;
        };
        std::set<int> allCopies;
        for (const auto &t : split(v, ',')) {
            const auto c = t.find(':');
            const int floor = num(t.substr(0, c), 1, 60);
            if (c == std::string::npos) allCopies.insert(floor);
            else armCopies[floor].insert(num(t.substr(c + 1), 0, armK - 1));
        }
        for (const int floor : allCopies) armCopies[floor].clear();   // empty set: every copy of that floor
    }
    FightReplayer fights(run, replayer, replicates, maxAct, potionMode == "expert", arms, armRooms, armK, armCopies);
    // The run ends at the first decision the log does not replay exactly: the
    // measurement only covers the expert's own states.
    t_oocDecisionOverride = [&](GameContext &gc) -> const char * {
        const char *by = replayer.step(gc);
        if (!replayer.stopped()) return by;
        gc.outcome = GameOutcome::PLAYER_LOSS;
        return "replay_stopped";
    };
    t_battleOverride = [&](GameContext &gc, search::ScumSearchAgent2 &agent) { return fights.onBattle(gc, agent); };
    struct Reset { ~Reset() { t_oocDecisionOverride = nullptr; t_battleOverride = nullptr; } } reset;
    trainingRunStart();
    const auto result = runFullRunOOC(seed, 10000, 20, deployedRestV(), true);
    if (!trainingRunValid(true)) throw std::runtime_error("expert fights run failed simulator integrity");
    const json out = {{"schema", "expert-fights-v1"}, {"runFile", std::filesystem::path(runFile).filename().string()},
        {"playId", run.value("play_id", std::string())}, {"seedPlayed", seedPlayed}, {"engineSeed", seed},
        {"replicates", replicates}, {"maxAct", maxAct}, {"potionMode", potionMode},
        {"arms", [&] { json a = json::array(); for (const auto &x : arms) a.push_back(x.name); return a; }()},
        {"armRooms", armRooms}, {"armReplicates", armK},
        {"armCopies", [&] { json a = json::object();
                            for (const auto &[floor, copies] : armCopies) a[std::to_string(floor)] = copies;
                            return a; }()}, {"endFloor", result.floor}, {"endAct", result.act},
        {"diedInMainLine", result.deathCombat >= 0}, {"sec", result.sec},
        {"expert", {{"victory", run.value("victory", false)}, {"floorReached", run["floor_reached"]}}},
        {"replay", replayer.summary()}, {"potionLog", fights.potionLog()}, {"fights", fights.fights()},
        {"syncs", fights.syncs()}, {"producerSha", trainingExecutableGitSha()},
        {"policy", effectiveOocPolicySpecification()}, {"provenance", heartOutcomeRunProvenance()}};
    std::ofstream f(output);
    if (!f) throw std::runtime_error("cannot write " + output);
    f << out.dump() << '\n';
    if (!f) throw std::runtime_error("write failed: " + output);
    std::cout << "[expertfights] seed=" << seedPlayed << " fights=" << out["fights"].size()
              << " endFloor=" << result.floor << " stop=" << out["replay"]["stopReason"] << std::endl;
    return 0;
}

}  // namespace one_combat
