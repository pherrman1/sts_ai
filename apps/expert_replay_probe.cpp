// Expert-run replay fidelity probe. Replays the out-of-combat decisions of a
// logged Slay the Spire .run file (vanilla RNG, Ironclad) on the native engine
// with battles skipped, syncing HP / max HP / gold to the log at every floor,
// and compares what the engine generates against what the log recorded:
// card reward offers, '?' room outcomes and event names, relics from
// rewards/chests/events, boss relic offers, potions and (when logged) shop
// contents. Acts 1-3 only. Prints one JSON line per run.
//
// usage: expert-replay-probe <run.json>...
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

#include "nlohmann/json.hpp"

#include "expert_run_log.h"
#include "game/Game.h"
#include "game/GameContext.h"
#include "game/Map.h"
#include "game/Neow.h"
#include "sim/search/GameAction.h"

using namespace sts;
using nlohmann::json;
using Action = search::GameAction;
using RAT = search::GameAction::RewardsActionType;

namespace {

using expert::baseName;
using expert::cardName;
using expert::jname;

struct Tally {
    int match = 0, mismatch = 0, firstMismatchFloor = -1;
    json examples = json::array();
    void add(bool ok, int floor, const json &detail) {
        if (ok) { ++match; return; }
        ++mismatch;
        if (firstMismatchFloor < 0) firstMismatchFloor = floor;
        if (examples.size() < 4) examples.push_back(detail);
    }
    json j() const {
        return {{"match", match}, {"mismatch", mismatch}, {"firstMismatchFloor", firstMismatchFloor},
                {"examples", examples}};
    }
};

struct Replayer : expert::RunLog {
    GameContext gc;
    std::map<std::string, Tally> t;
    json notes = json::array();
    int firstGuessFloor = -1;     // first floor where a decision could not be replayed exactly
    int lastFloor = 0;

    std::vector<int> pathX[3];
    std::vector<std::string> pendingSelect;   // card names to pick on the next select screens
    std::vector<int> pendingEventIdx;
    int bossRelicIdx = 0;
    int unloggedOffers = 0;

    Replayer(const json &r, std::uint64_t seed) : RunLog(r), gc(CharacterClass::IRONCLAD, seed, 20) {
        gc.skipBattles = true;
    }

    void guess(const std::string &what) {
        if (firstGuessFloor < 0) firstGuessFloor = gc.floorNum;
        if (notes.size() < 12) notes.push_back(std::to_string(gc.floorNum) + ": " + what);
    }

    int hpAt(const char *key, int floor) {
        const auto &a = run[key];
        if (floor >= 1 && floor - 1 < (int)a.size() && a[floor - 1].is_number()) return a[floor - 1].get<int>();
        return -1;
    }

    void syncToFloorEnd(int floor) {
        int hp = hpAt("current_hp_per_floor", floor), mhp = hpAt("max_hp_per_floor", floor), g = hpAt("gold_per_floor", floor);
        if (mhp > 0) gc.maxHp = mhp;
        if (hp > 0) gc.curHp = std::min(hp, gc.maxHp);
        if (g >= 0) gc.gold = g;
    }

    bool computePath(int act, const Map &m) { return actPath(act, m, pathX[act]); }

    static std::string roomLetter(Room r) {
        switch (r) {
            case Room::MONSTER: return "M"; case Room::ELITE: return "E"; case Room::EVENT: return "?";
            case Room::SHOP: return "$"; case Room::TREASURE: return "T"; case Room::REST: return "R";
            case Room::BOSS: return "B"; default: return "-";
        }
    }

    // ---- screens ----

    void doMap() {
        const int floor = gc.floorNum + 1;
        syncToFloorEnd(gc.floorNum);
        const int act = gc.act - 1;
        int x;
        if (gc.curMapNodeY == 14) {
            x = 0;
        } else {
            const int y = gc.curMapNodeY + 1;
            if (y >= (int)pathX[act].size()) throw std::runtime_error("path exhausted");
            x = pathX[act][y];
        }
        if (gc.mapMoveCost(x) < 0) {
            // Winged Boots jump or path ambiguity
            if (gc.hasRelic(RelicId::WING_BOOTS) && gc.curMapNodeY >= 0) {
                gc.wingBootsCharges = std::max(gc.wingBootsCharges, 1);
            }
            if (gc.mapMoveCost(x) < 0) throw std::runtime_error("map move invalid");
        }
        prepareFloor(floor);
        gc.transitionToMapNode(x);
        // compare room outcome for '?' nodes
        const auto logged = roomAt(floor);
        if (gc.curMapNodeY < 15 && gc.map->getNode(x, gc.curMapNodeY).room == Room::EVENT) {
            const auto eng = roomLetter(gc.curRoom);
            t["questionRoomOutcome"].add(eng == logged, floor, {{"floor", floor}, {"log", logged}, {"eng", eng}});
            if (gc.curRoom == Room::EVENT) {
                auto ev = events.count(floor) ? events[floor][0]["event_name"].get<std::string>() : std::string("<none>");
                auto engEv = expert::logEventName(gc.curEvent);
                t["eventName"].add(ev == engEv, floor, {{"floor", floor}, {"log", ev}, {"eng", engEv}});
                planEvent(floor, ev == engEv);
            }
        }
    }

    void prepareFloor(int floor) {
        pendingSelect.clear();
        pendingEventIdx.clear();
        if (purges.count(floor)) for (auto &c : purges[floor]) pendingSelect.push_back(c);
        if (campfire.count(floor)) for (auto &c : campfire[floor])
            if (c.contains("data") && c["data"].is_string()) pendingSelect.push_back(c["data"]);
    }

    void planEvent(int floor, bool nameOk) {
        if (!nameOk || !events.count(floor)) { guess("event mismatch, leaving"); return; }
        const auto &e = events[floor][0];
        std::vector<expert::SelectPick> picks;
        const auto why = expert::planEvent(e, gc, pendingEventIdx, picks);
        for (const auto &p : picks) pendingSelect.push_back(p.card);
        if (why.rfind("N'loth", 0) == 0) {
            pendingEventIdx = {0};
            t["eventOffer"].add(false, floor, {{"floor", floor}, {"event", "N'loth"}, {"why", why}});
        } else if (!why.empty()) {
            guess(why);
        }
    }

    void doEvent() {
        if (gc.curEvent == Event::NEOW) { doNeow(); return; }
        if (gc.curEvent == Event::MATCH_AND_KEEP) {
            // unreplayable (positions unknown); uses only floor-reseeded miscRng
            auto acts = Action::getAllActionsInState(gc);
            for (auto &a : acts) if (!a.isPotionAction()) { a.execute(gc); return; }
            throw std::runtime_error("match and keep stuck");
        }
        int idx = -1;
        if (!pendingEventIdx.empty()) { idx = pendingEventIdx.front(); pendingEventIdx.erase(pendingEventIdx.begin()); }
        if (idx < 0 || !Action(idx).isValidAction(gc)) {
            if (idx >= 0) guess("event idx invalid " + jname(gc.curEvent) + " " + std::to_string(idx));
            // choose highest valid index (usually leave)
            idx = -1;
            for (int i = 11; i >= 0; --i) if (Action(i).isValidAction(gc)) { idx = i; break; }
            if (idx < 0) throw std::runtime_error("no valid event action");
        }
        gc.chooseEventOption(idx);
    }

    void doNeow() {
        const auto bonus = run.value("neow_bonus", std::string());
        const auto cost = run.value("neow_cost", std::string());
        int pick = -1;
        for (int i = 0; i < 4; ++i) {
            const auto &o = gc.info.neowRewards[i];
            if (jname(o.r) == bonus && (o.r == Neow::Bonus::BOSS_RELIC || jname(o.d) == cost)) pick = i;
        }
        if (pick < 0 && (bonus == "THREE_ENEMY_KILL" || bonus == "TEN_PERCENT_HP_BONUS")) {
            // the 2-option mini blessing after a short previous run: no RNG, fixed options
            t["neowMiniBlessing"].add(true, 0, {});
            json bj = bonus;
            gc.chooseNeowOption(Neow::Option{bj.get<Neow::Bonus>(), Neow::Drawback::NONE});
            return;
        }
        t["neowPicked"].add(pick >= 0, 0, {{"bonus", bonus}, {"cost", cost}});
        if (pick < 0) { guess("neow option not offered"); pick = 0; }
        if (run.contains("neow_bonus_log") && run["neow_bonus_log"].is_object()) {
            const auto &l = run["neow_bonus_log"];
            for (const char *k : {"cardsRemoved", "cardsUpgraded", "cardsTransformed", "cardsObtained"})
                if (l.contains(k)) for (auto &c : l[k]) pendingSelect.push_back(c);
        } else {
            const auto r = gc.info.neowRewards[pick].r;
            if (r == Neow::Bonus::REMOVE_CARD || r == Neow::Bonus::REMOVE_TWO || r == Neow::Bonus::TRANSFORM_CARD ||
                r == Neow::Bonus::TRANSFORM_TWO_CARDS || r == Neow::Bonus::UPGRADE_CARD || r == Neow::Bonus::THREE_CARDS ||
                r == Neow::Bonus::RANDOM_COLORLESS || r == Neow::Bonus::RANDOM_COLORLESS_2 || r == Neow::Bonus::THREE_RARE_CARDS)
                guess("neow sub-choice not logged (old run)");
        }
        gc.chooseEventOption(pick);
    }

    int findInSelect(const std::string &name) {
        const auto &cards = gc.info.toSelectCards;
        for (int i = 0; i < (int)cards.size(); ++i) if (cardName(cards[i].card) == name) return i;
        for (int i = 0; i < (int)cards.size(); ++i) if (baseName(cardName(cards[i].card)) == baseName(name)) return i;
        return -1;
    }

    void doCardSelect() {
        int idx = -1;
        for (size_t k = 0; k < pendingSelect.size(); ++k) {
            idx = findInSelect(pendingSelect[k]);
            if (idx >= 0) { pendingSelect.erase(pendingSelect.begin() + k); break; }
        }
        if (idx < 0) {
            if (gc.info.selectScreenType == CardSelectScreenType::OBTAIN && cardChoices.count(gc.floorNum)) {
                for (auto &c : cardChoices[gc.floorNum]) { idx = findInSelect(c["picked"]); if (idx >= 0) break; }
            }
        }
        if (idx < 0) {
            guess("card select by name failed (type " + std::to_string((int)gc.info.selectScreenType) + ")");
            idx = 0;
        }
        gc.chooseSelectCardScreenOption(idx);
    }

    void doRewards() {
        auto &r = gc.info.rewardsContainer;
        const int floor = gc.floorNum;
        // gold
        while (r.goldRewardCount > 0) Action(RAT::GOLD, 0).execute(gc);
        // keys: emerald
        if (r.emeraldKey && greenKeyFloor == floor) { Action(RAT::KEY, 0).execute(gc); }
        // relics
        if (r.relicCount > 0) {
            auto &logged = relicsObtained[floor];
            const auto name = jname(r.relics[0]);
            bool ok = false;
            for (auto &l : logged) if (l["key"] == name) ok = true;
            bool sapphireSkip = (blueKeyFloor == floor && run["blue_key_relic_skipped_log"]["relicID"] == name);
            if (!logged.empty() || sapphireSkip) t["rewardRelic"].add(ok || sapphireSkip, floor, {{"floor", floor}, {"eng", name}, {"log", logged}});
            if (sapphireSkip && r.sapphireKey) { Action(RAT::KEY, 0).execute(gc); return; }
            Action(RAT::RELIC, 0).execute(gc);
            return;  // may open a screen; the loop re-enters
        }
        // potions
        if (r.potionCount > 0) {
            auto &logged = potionsObtained[floor];
            if (run.contains("potions_floor_spawned") && floor > 0) {
                bool spawned = false;
                for (auto &f : run["potions_floor_spawned"]) if (f == floor) spawned = true;
                t["potionDropFloor"].add(spawned, floor, {{"floor", floor}, {"eng", jname(r.potions[0])}});
            }
            for (int i = 0; i < r.potionCount; ++i) {
                const auto name = jname(r.potions[i]);
                bool ok = false;
                for (auto &l : logged) if (l["key"] == name) ok = true;
                if (!logged.empty()) t["rewardPotionTaken"].add(ok, floor, {{"floor", floor}, {"eng", name}, {"log", logged}});
            }
            for (int i = r.potionCount - 1; i >= 0; --i) {
                bool want = false;
                for (auto &l : logged) if (l["key"] == jname(r.potions[i])) want = true;
                if (!want) continue;
                if (gc.potionCount >= gc.potionCapacity) {
                    for (int s = 0; s < gc.potionCapacity; ++s)
                        if (gc.potions[s] != Potion::EMPTY_POTION_SLOT) { gc.discardPotionAtIdx(s); break; }
                }
                Action(RAT::POTION, i).execute(gc);
            }
        }
        // card rewards
        while (gc.screenState == ScreenState::REWARDS && r.cardRewardCount > 0) {
            auto &logged = cardChoices[floor];
            const auto &cr = r.cardRewards[0];
            std::multiset<std::string> eng;
            for (const auto &c : cr) eng.insert(cardName(c));
            int hit = -1;
            for (int k = 0; k < (int)logged.size(); ++k) {
                std::multiset<std::string> lg;
                for (auto &c : logged[k]["not_picked"]) lg.insert(c.get<std::string>());
                auto p = logged[k]["picked"].get<std::string>();
                if (p != "SKIP" && p != "Singing Bowl") lg.insert(p);
                if (lg == eng) { hit = k; break; }
            }
            int baseHit = -1;
            {
                std::multiset<std::string> engB;
                for (auto &s : eng) engB.insert(baseName(s));
                for (int k = 0; k < (int)logged.size() && baseHit < 0; ++k) {
                    std::multiset<std::string> lg;
                    for (auto &c : logged[k]["not_picked"]) lg.insert(baseName(c.get<std::string>()));
                    auto p = logged[k]["picked"].get<std::string>();
                    if (p != "SKIP" && p != "Singing Bowl") lg.insert(baseName(p));
                    if (lg == engB) baseHit = k;
                }
            }
            if (hit < 0) hit = baseHit;
            json engj = json::array(); for (auto &s : eng) engj.push_back(s);
            if (logged.empty() && floor > 0) {
                // vanilla logs no entry for a card reward that was never opened
                ++unloggedOffers;
                r.removeCardReward(0);
                continue;
            }
            if (hit >= 0) {
                std::multiset<std::string> lg;
                for (auto &c : logged[hit]["not_picked"]) lg.insert(c.get<std::string>());
                auto p = logged[hit]["picked"].get<std::string>();
                if (p != "SKIP" && p != "Singing Bowl") lg.insert(p);
                t["cardOfferUpgradeFlags"].add(lg == eng, floor, {{"floor", floor}, {"eng", engj}, {"log", logged[hit]}});
            }
            t["cardOffer"].add(hit >= 0, floor, {{"floor", floor}, {"eng", engj}, {"log", logged}});
            int k = hit >= 0 ? hit : (logged.empty() ? -1 : 0);
            std::string pick = k >= 0 ? logged[k]["picked"].get<std::string>() : "SKIP";
            if (k < 0 && !pendingSelect.empty()) { pick = pendingSelect.front(); pendingSelect.erase(pendingSelect.begin()); }
            if (k >= 0) logged.erase(logged.begin() + k);
            int ci = -1;
            for (int i = 0; i < (int)cr.size(); ++i) if (cardName(cr[i]) == pick) ci = i;
            for (int i = 0; i < (int)cr.size() && ci < 0; ++i) if (baseName(cardName(cr[i])) == baseName(pick)) ci = i;
            if (ci < 0 && pick != "SKIP" && pick != "Singing Bowl") {
                // offer mismatch: obtain the logged card directly to keep the deck in sync
                try { json pj = baseName(pick); gc.deck.obtain(gc, Card(pj.get<CardId>())); } catch (...) {}
            }
            if (ci >= 0) Action(RAT::CARD, 0, ci).execute(gc);
            else if (pick == "Singing Bowl" && gc.hasRelic(RelicId::SINGING_BOWL)) Action(RAT::CARD, 0, 5).execute(gc);
            else r.removeCardReward(0);
        }
        if (gc.screenState == ScreenState::REWARDS) Action(RAT::SKIP).execute(gc);
    }

    void doBossRelic() {
        json engj = json::array();
        std::multiset<std::string> eng;
        for (int i = 0; i < 3; ++i) { eng.insert(jname(gc.info.bossRelics[i])); engj.push_back(jname(gc.info.bossRelics[i])); }
        int pick = 3;  // skip
        if (bossRelicIdx < (int)bossRelics.size()) {
            const auto &b = bossRelics[bossRelicIdx];
            std::multiset<std::string> lg;
            for (auto &c : b["not_picked"]) lg.insert(c.get<std::string>());
            std::string p = b.value("picked", std::string("SKIP"));
            if (p != "SKIP") lg.insert(p);
            t["bossRelicOffer"].add(lg == eng, gc.floorNum, {{"floor", gc.floorNum}, {"eng", engj}, {"log", b}});
            for (int i = 0; i < 3; ++i) if (jname(gc.info.bossRelics[i]) == p) pick = i;
            if (pick == 3 && p != "SKIP") {
                guess("boss relic not offered: " + p);
                try { json pj = p; gc.obtainRelic(pj.get<RelicId>()); } catch (...) {}
            }
        }
        ++bossRelicIdx;
        gc.chooseBossRelic(pick);
    }

    void doTreasure() {
        // a chest with no logged relic (and no sapphire key) was left closed
        const bool opened = !relicsObtained[gc.floorNum].empty() || blueKeyFloor == gc.floorNum;
        Action(opened ? 0 : 1).execute(gc);
    }

    void doRest() {
        const int floor = gc.floorNum;
        int idx = 6;
        if (campfire.count(floor) && !campfire[floor].empty()) {
            auto key = campfire[floor][0]["key"].get<std::string>();
            idx = key == "REST" ? 0 : key == "SMITH" ? 1 : key == "RECALL" ? 2 : key == "LIFT" ? 3 :
                  key == "PURGE" ? 4 : key == "DIG" ? 5 : 6;
        }
        if (!Action(idx).isValidAction(gc)) {
            for (int i = 6; i >= 0; --i) if (Action(i).isValidAction(gc)) { idx = i; break; }
        }
        gc.chooseCampfireOption(idx);
    }

    void doShop() {
        const int floor = gc.floorNum;
        auto &s = gc.info.shop;
        if (shopContents.count(floor)) {
            const auto &l = shopContents[floor];
            std::multiset<std::string> ec, er, ep, lc, lr, lp;
            for (int i = 0; i < 7; ++i) if (s.cards[i].getId() != CardId::INVALID) ec.insert(baseName(cardName(s.cards[i])));
            for (int i = 0; i < 3; ++i) { er.insert(jname(s.relics[i])); ep.insert(jname(s.potions[i])); }
            for (auto &c : l["cards"]) lc.insert(baseName(c.get<std::string>()));
            for (auto &c : l["relics"]) lr.insert(c.get<std::string>());
            for (auto &c : l["potions"]) lp.insert(c.get<std::string>());
            // the log lists what was left on the shelves; add back this floor's purchases
            for (const auto &item : purchases[floor]) {
                if (ec.count(baseName(item)) > lc.count(baseName(item))) lc.insert(baseName(item));
                else if (er.count(item) > lr.count(item)) lr.insert(item);
                else if (ep.count(item) > lp.count(item)) lp.insert(item);
            }
            auto subset = [](const std::multiset<std::string> &a, const std::multiset<std::string> &b) {
                for (const auto &x : a) if (a.count(x) > b.count(x)) return false;
                return true;
            };
            t["shopCards"].add(subset(lc, ec), floor, {{"floor", floor}, {"eng", json(std::vector<std::string>(ec.begin(), ec.end()))}, {"log", json(std::vector<std::string>(lc.begin(), lc.end()))}});
            t["shopRelics"].add(subset(lr, er), floor, {{"floor", floor}, {"eng", json(std::vector<std::string>(er.begin(), er.end()))}, {"log", l["relics"]}});
            t["shopPotions"].add(subset(lp, ep), floor, {{"floor", floor}, {"eng", json(std::vector<std::string>(ep.begin(), ep.end()))}, {"log", json(std::vector<std::string>(lp.begin(), lp.end()))}});
        }
        gc.gold = 99999;  // purchases replay regardless of gold; synced at floor end
        for (const auto &item : purchases[floor]) {
            bool done = false;
            for (int i = 0; i < 7 && !done; ++i)
                if (s.cardPrice(i) != -1 && s.cards[i].getId() != CardId::INVALID && cardName(s.cards[i]) == item) { s.buyCard(gc, i); done = true; }
            for (int i = 0; i < 3 && !done; ++i)
                if (s.relicPrice(i) != -1 && jname(s.relics[i]) == item) { s.buyRelic(gc, i); done = true; }
            for (int i = 0; i < 3 && !done; ++i)
                if (s.potionPrice(i) != -1 && jname(s.potions[i]) == item) {
                    if (gc.potionCount >= gc.potionCapacity)
                        for (int k = 0; k < gc.potionCapacity; ++k) if (gc.potions[k] != Potion::EMPTY_POTION_SLOT) { gc.discardPotionAtIdx(k); break; }
                    s.buyPotion(gc, i); done = true;
                }
            t["shopPurchaseAvailable"].add(done, floor, {{"floor", floor}, {"item", item}});
            if (gc.screenState != ScreenState::SHOP_ROOM) return;  // relic opened a screen
        }
        purchases[floor].clear();
        if (!purges[floor].empty() && s.removeCost != -1) {
            purges[floor].clear();
            s.buyCardRemove(gc);
            return;
        }
        Action(RAT::SKIP).execute(gc);
    }

    json replay() {
        const int maxFloor = std::min(run["floor_reached"].get<int>(), 51);
        if (!computePath(0, *gc.map)) notes.push_back("act1 path not found");
        int steps = 0;
        std::string stop = "ok";
        try {
            while (gc.outcome == GameOutcome::UNDECIDED && steps++ < 5000) {
                if (gc.act > 3) { stop = "act4"; break; }
                if (gc.floorNum >= 51 && gc.screenState == ScreenState::MAP_SCREEN) { stop = "act3 done"; break; }
                if (gc.screenState == ScreenState::MAP_SCREEN) {
                    if (gc.curMapNodeY == -1 && pathX[gc.act - 1].empty()) {
                        if (!computePath(gc.act - 1, *gc.map)) { stop = "path not found act " + std::to_string(gc.act); break; }
                    }
                    if (gc.floorNum >= maxFloor) { stop = "reached logged floor"; break; }
                    doMap();
                    continue;
                }
                switch (gc.screenState) {
                    case ScreenState::EVENT_SCREEN: doEvent(); break;
                    case ScreenState::REWARDS: doRewards(); break;
                    case ScreenState::BOSS_RELIC_REWARDS: doBossRelic(); break;
                    case ScreenState::CARD_SELECT: doCardSelect(); break;
                    case ScreenState::TREASURE_ROOM: doTreasure(); break;
                    case ScreenState::REST_ROOM: doRest(); break;
                    case ScreenState::SHOP_ROOM: doShop(); break;
                    default: throw std::runtime_error("unexpected screen " + std::to_string((int)gc.screenState));
                }
                if (gc.floorNum > lastFloor) lastFloor = gc.floorNum;
            }
        } catch (const std::exception &e) {
            stop = std::string("error: ") + e.what() + " floor " + std::to_string(gc.floorNum) + " screen " + std::to_string((int)gc.screenState) + " y " + std::to_string(gc.curMapNodeY) + " act " + std::to_string(gc.act);
        }
        // chest/event relics: compare relics_obtained for non-reward sources at the end
        json out;
        out["stop"] = stop;
        out["lastFloor"] = gc.floorNum;
        out["firstGuessFloor"] = firstGuessFloor;
        out["unloggedOffers"] = unloggedOffers;
        out["notes"] = notes;
        for (auto &kv : t) out["t"][kv.first] = kv.second.j();
        // relic set comparison: logged relics obtained on floors replayed vs engine relics
        std::multiset<std::string> eng;
        for (const auto &r : gc.relics.relics) eng.insert(jname(r.id));
        int have = 0, total = 0;
        for (const auto &kv : relicsObtained) if (kv.first <= gc.floorNum)
            for (auto &l : kv.second) { ++total; if (eng.count(l["key"].get<std::string>())) ++have; }
        out["relicsHeldOfLogged"] = {have, total};
        return out;
    }
};

}  // namespace

int main(int argc, char **argv) {
    for (int i = 1; i < argc; ++i) {
        json out;
        out["file"] = argv[i];
        try {
            std::ifstream f(argv[i]);
            json run = json::parse(f);
            const auto seedStr = run["seed_played"].get<std::string>();
            out["seed"] = seedStr;
            if (run.value("character_chosen", std::string()) != "IRONCLAD" || run.value("ascension_level", 0) != 20) {
                out["stop"] = "skip: not Ironclad A20";
            } else {
                Replayer r(run, static_cast<std::uint64_t>(std::stoll(seedStr)));
                out.update(r.replay());
            }
        } catch (const std::exception &e) {
            out["stop"] = std::string("load error: ") + e.what();
        }
        std::cout << out.dump() << std::endl;
    }
    return 0;
}
