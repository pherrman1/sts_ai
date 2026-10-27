// Shared reading of logged Slay the Spire .run files (vanilla RNG, Ironclad) for
// the expert-run replay tools: per-floor indices of the logged decisions, the
// logged map path as engine x coordinates, and the engine event option
// sequence for a logged event choice. Header-only so both the standalone
// fidelity probe and one_combat's expertreplay mode use the same mapping.
#ifndef STS_EXPERT_RUN_LOG_H
#define STS_EXPERT_RUN_LOG_H

#include <array>
#include <map>
#include <sstream>
#include <string>
#include <vector>

#include "nlohmann/json.hpp"

#include "constants/SaveFileMappings.h"
#include "game/GameContext.h"
#include "game/Map.h"
#include "game/Neow.h"

namespace sts::expert {

template <typename E> std::string jname(E e) {
    nlohmann::json j = e;
    return j.is_string() ? j.get<std::string>() : std::string("?");
}

inline std::string cardName(const Card &c) {
    std::string s = jname(c.getId());
    if (c.getUpgraded() > 0) s += "+" + std::to_string(c.getUpgraded());
    return s;
}

inline std::string baseName(const std::string &s) {
    auto p = s.find('+');
    return p == std::string::npos ? s : s.substr(0, p);
}

struct RunLog {
    nlohmann::json run;
    std::map<int, std::vector<nlohmann::json>> cardChoices, relicsObtained, potionsObtained, events, campfire;
    std::map<int, std::vector<std::string>> purchases, purges;
    std::vector<nlohmann::json> bossRelics;
    std::map<int, nlohmann::json> shopContents;
    int greenKeyFloor = -1, blueKeyFloor = -1;
    std::string blueKeyRelic;

    explicit RunLog(const nlohmann::json &r) : run(r) {
        using nlohmann::json;
        for (const auto &c : run["card_choices"]) cardChoices[c["floor"].get<int>()].push_back(c);
        for (const auto &c : run["relics_obtained"]) relicsObtained[c["floor"].get<int>()].push_back(c);
        for (const auto &c : run.value("potions_obtained", json::array())) potionsObtained[c["floor"].get<int>()].push_back(c);
        for (const auto &c : run["event_choices"]) events[c["floor"].get<int>()].push_back(c);
        for (const auto &c : run["campfire_choices"]) campfire[c["floor"].get<int>()].push_back(c);
        const auto &ip = run["items_purchased"]; const auto &ipf = run["item_purchase_floors"];
        for (size_t i = 0; i < ip.size() && i < ipf.size(); ++i) purchases[ipf[i].get<int>()].push_back(ip[i]);
        const auto pu = run.value("items_purged", json::array()); const auto puf = run.value("items_purged_floors", json::array());
        for (size_t i = 0; i < pu.size() && i < puf.size(); ++i) purges[puf[i].get<int>()].push_back(pu[i]);
        for (const auto &b : run["boss_relics"]) bossRelics.push_back(b);
        for (const auto &s : run.value("shop_contents", json::array())) shopContents[s["floor"].get<int>()] = s;
        if (run.contains("green_key_taken_log") && run["green_key_taken_log"].is_number())
            greenKeyFloor = run["green_key_taken_log"].get<int>();
        if (run.contains("blue_key_relic_skipped_log") && run["blue_key_relic_skipped_log"].is_object()) {
            blueKeyFloor = run["blue_key_relic_skipped_log"]["floor"].get<int>();
            blueKeyRelic = run["blue_key_relic_skipped_log"].value("relicID", std::string());
        }
    }

    std::string roomAt(int floor) const {
        const auto &p = run["path_per_floor"];
        if (floor >= 1 && floor - 1 < (int)p.size() && p[floor - 1].is_string()) return p[floor - 1].get<std::string>();
        return "";
    }

    // Engine x per map row of act `act0` (0-based, acts 1-3) for the logged
    // path_taken symbols; false when no edge-connected path matches (Winged
    // Boots jumps).
    bool actPath(int act0, const Map &m, std::vector<int> &out) const {
        const auto &pt = run["path_taken"];
        std::vector<char> syms;
        for (int i = 16 * act0; i < 16 * act0 + 15 && i < (int)pt.size(); ++i) {
            if (!pt[i].is_string()) break;
            auto s = pt[i].get<std::string>();
            if (s == "BOSS") break;
            syms.push_back(s[0]);
        }
        out.clear();
        if (syms.empty()) return true;
        const int n = syms.size();
        std::vector<std::array<int, 7>> nxt(n);
        std::vector<std::array<bool, 7>> ok(n);
        for (int y = n - 1; y >= 0; --y)
            for (int x = 0; x < 7; ++x) {
                const auto &node = m.getNode(x, y);
                ok[y][x] = false; nxt[y][x] = -1;
                if (node.room == Room::NONE || node.getRoomSymbol() != syms[y]) continue;
                if (y == n - 1) { ok[y][x] = true; continue; }
                for (int i = 0; i < node.edgeCount; ++i)
                    if (ok[y + 1][node.edges[i]]) { ok[y][x] = true; nxt[y][x] = node.edges[i]; break; }
            }
        int x = -1;
        for (int i = 0; i < 7; ++i) if (ok[0][i] && m.getNode(i, 0).edgeCount > 0) { x = i; break; }
        if (x < 0) return false;
        for (int y = 0; y < n; ++y) { out.push_back(x); x = nxt[y][x]; }
        return true;
    }
};

// A logged card to pick on a later select screen of the given kind.
struct SelectPick {
    std::string kind;   // remove, upgrade, transform, duplicate, obtain
    std::string card;
};

// The SelectPick kind a select screen takes; "" for screens the log never
// records (Bottled relics).
inline std::string selectKind(CardSelectScreenType t) {
    switch (t) {
        case CardSelectScreenType::REMOVE: case CardSelectScreenType::BONFIRE_SPIRITS: return "remove";
        case CardSelectScreenType::UPGRADE: return "upgrade";
        case CardSelectScreenType::TRANSFORM: case CardSelectScreenType::TRANSFORM_UPGRADE: return "transform";
        case CardSelectScreenType::DUPLICATE: return "duplicate";
        case CardSelectScreenType::OBTAIN: return "obtain";
        default: return "";
    }
}

// Engine event option indices for the logged choice of event entry `e`, and the
// cards its select screens should pick. Returns "" on success, else why the
// choice cannot be mapped. Match and Keep, Lab and Bonfire Elementals have no
// option sequence (empty `idx`, success).
inline std::string planEvent(const nlohmann::json &e, const GameContext &gc, std::vector<int> &idx,
                             std::vector<SelectPick> &select) {
    idx.clear();
    const auto name = e["event_name"].get<std::string>();
    const auto ch = e["player_choice"].get<std::string>();
    for (const auto &[k, kind] : {std::pair<const char *, const char *>{"cards_removed", "remove"},
                                  {"cards_upgraded", "upgrade"}, {"cards_transformed", "transform"}})
        if (e.contains(k)) for (auto &c : e[k]) select.push_back({kind, c.get<std::string>()});
    if (name == "Duplicator" && e.contains("cards_obtained"))
        for (auto &c : e["cards_obtained"]) select.push_back({"duplicate", c.get<std::string>()});
    static const std::map<std::string, std::map<std::string, std::vector<int>>> table = {
        {"Accursed Blacksmith", {{"Forge", {0}}, {"Rummage", {1}}, {"Ignored", {2}}}},
        {"Addict", {{"Obtained Relic", {0}}, {"Stole Relic", {1}}, {"Ignored", {2}}}},
        {"Back to Basics", {{"Elegance", {0}}, {"Simplicity", {1}}}},
        {"Beggar", {{"Gave Gold", {0}}, {"Ignored", {1}}}},
        {"Big Fish", {{"Banana", {0}}, {"Donut", {1}}, {"Box", {2}}}},
        {"Colosseum", {{"Fight", {0, 0}}, {"Fought Nobs", {0, 1}}}},
        {"Cursed Tome", {{"Obtained Book", {0, 2, 3, 4, 5}}, {"Ignored", {1}}, {"Stopped", {0, 2, 3, 4, 6}}}},
        {"Designer", {{"Upgrade", {0}}, {"Upgraded Two", {1}}, {"Single Remove", {2}}, {"Transformed Cards", {3}},
                      {"Upgrade and Remove", {4}}, {"Ignored", {5}}}},
        {"Drug Dealer", {{"Obtain J.A.X.", {0}}, {"Became Test Subject", {1}}, {"Inject Mutagens", {2}}}},
        {"Duplicator", {{"Copied", {0}}, {"Ignored", {1}}}},
        {"FaceTrader", {{"Touch", {0}}, {"Trade", {1}}, {"Leave", {2}}}},
        {"Falling", {{"Removed Skill", {0}}, {"Removed Power", {1}}, {"Removed Attack", {2}}}},
        {"Forgotten Altar", {{"Gave Idol", {0}}, {"Shed Blood", {1}}, {"Smashed Altar", {2}}}},
        {"Fountain of Cleansing", {{"Removed Curses", {0}}, {"Ignored", {1}}}},
        {"Ghosts", {{"Became a Ghost", {0}}, {"Ignored", {1}}}},
        {"Golden Idol", {{"Take Wound", {0, 2}}, {"Take Damage", {0, 3}}, {"Lose Max HP", {0, 4}}, {"Ignored", {1}}}},
        {"Golden Shrine", {{"Pray", {0}}, {"Desecrate", {1}}, {"Ignored", {2}}}},
        {"Golden Wing", {{"Card Removal", {0}}, {"Gained Gold", {1}}, {"Ignored", {2}}}},
        {"Liars Game", {{"AGREE", {0}}, {"Ignored", {1}}, {"DISAGREE", {1}}}},
        {"Living Wall", {{"Forget", {0}}, {"Change", {1}}, {"Grow", {2}}}},
        {"Masked Bandits", {{"Paid Fearfully", {0}}, {"Fought Bandits", {1}}}},
        {"MindBloom", {{"Fight", {0}}, {"Upgrade", {1}}, {"Gold", {2}}, {"Heal", {3}}}},
        {"Mushrooms", {{"Fought Mushrooms", {0}}, {"Healed and dodged fight", {1}}}},
        {"Mysterious Sphere", {{"Fight", {0}}, {"Ignored", {1}}}},
        {"N'loth", {{"Ignored", {2}}}},
        {"Nest", {{"Stole From Cult", {0}}, {"Joined the Cult", {1}}}},
        {"Purifier", {{"Purged", {0}}, {"Ignored", {1}}}},
        {"SecretPortal", {{"Took Portal", {0}}, {"Ignored", {1}}}},
        {"SensoryStone", {{"Memory 1", {0}}, {"Memory 2", {1}}, {"Memory 3", {2}}}},
        {"Shining Light", {{"Entered Light", {0}}, {"Ignored", {1}}}},
        {"The Cleric", {{"Healed", {0}}, {"Card Removal", {1}}, {"Leave", {2}}}},
        {"The Joust", {{"Bet on Murderer", {0}}, {"Bet on Owner", {1}}}},
        {"The Library", {{"Read", {0}}, {"Heal", {1}}}},
        {"The Mausoleum", {{"Opened", {0}}, {"Ignored", {1}}}},
        {"The Moai Head", {{"Heal", {0}}, {"Gave Idol", {1}}, {"Ignored", {2}}}},
        {"The Woman in Blue", {{"Bought 1 Potion", {0}}, {"Bought 2 Potions", {1}}, {"Bought 3 Potions", {2}},
                               {"Bought 0 Potions", {3}}}},
        {"Tomb of Lord Red Mask", {{"Wore Mask", {0}}, {"Paid", {1}}, {"Ignored", {2}}}},
        {"Transmorgrifier", {{"Transformed", {0}}, {"Ignored", {1}}}},
        {"Upgrade Shrine", {{"Upgraded", {0}}, {"Ignored", {1}}}},
        {"Vampires", {{"Became a vampire (Vial)", {0}}, {"Became a vampire", {1}}, {"Ignored", {2}}}},
        {"WeMeetAgain", {{"Gave Potion", {0}}, {"Paid Gold", {1}}, {"Gave Card", {2}}, {"Ignored", {3}}}},
        {"Wheel of Change", {{"Gold", {0}}, {"Relic", {0}}, {"Card Removal", {0}}, {"Cursed", {0}}, {"Full Heal", {0}}, {"Damaged", {0}}}},
        {"Winding Halls", {{"Embrace Madness", {0}}, {"Writhe", {1}}, {"Max HP", {2}}}},
        {"World of Goop", {{"Gather Gold", {0}}, {"Left Gold", {1}}}},
    };
    if (name == "Dead Adventurer") {
        int k = 0;
        auto p = ch.find('\'');
        if (p != std::string::npos) k = std::stoi(ch.substr(p + 1));
        for (int i = 0; i < k; ++i) idx.push_back(0);
        idx.push_back(1);
        return "";
    }
    if (name == "Scrap Ooze") {
        if (ch == "Success") { for (int i = 0; i < 40; ++i) idx.push_back(0); return ""; }
        int dmg = e.value("damage_taken", 0), k = 0, s = 0;
        while (s < dmg) { s += 5 + k; ++k; }
        for (int i = 0; i < k; ++i) idx.push_back(0);
        idx.push_back(1);
        return "";
    }
    if (name == "Knowing Skull") {
        std::istringstream ss(ch); std::string tok;
        while (ss >> tok) idx.push_back(tok == "GOLD" ? 0 : tok == "CARD" ? 1 : 2);
        idx.push_back(3);
        return "";
    }
    if (name == "N'loth" && ch == "Traded Relic") {
        std::string lost = e.contains("relics_lost") && !e["relics_lost"].empty() ? e["relics_lost"][0].get<std::string>() : "";
        const int i0 = gc.info.relicIdx0, i1 = gc.info.relicIdx1;
        if (i0 >= 0 && jname(gc.relics.relics[i0].id) == lost) idx.push_back(0);
        else if (i1 >= 0 && jname(gc.relics.relics[i1].id) == lost) idx.push_back(1);
        else return "N'loth relic " + lost + " not offered";
        return "";
    }
    if (name == "Match and Keep!" || name == "Lab" || name == "Bonfire Elementals") return "";
    auto it = table.find(name);
    if (it == table.end()) return "unmapped event " + name;
    auto jt = it->second.find(ch);
    if (jt == it->second.end()) return "unmapped choice " + name + "/" + ch;
    idx = jt->second;
    return "";
}

// The engine event name in the log's spelling.
inline std::string logEventName(Event e) {
    auto s = jname(e);
    if (s == "Match and Keep") s = "Match and Keep!";
    else if (s == "Sensory Stone") s = "SensoryStone";
    return s;
}

}  // namespace sts::expert

#endif
