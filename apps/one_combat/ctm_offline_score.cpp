// Offline scoring of recorded combat_transition_row_v2 rows with the live
// OOC MCTS combat stack (#418 Stage 0). Reads rows only; runs no seeds.
#include "one_combat/driver_shared.h"
#include "one_combat/combat_predictor_input.h"
#include "one_combat/combat_transition.h"
#include "one_combat/combat_transition_runtime.h"
#include "one_combat/combat_transition_native_contract.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <unistd.h>

namespace {

using J = nlohmann::json;
using one_combat::CombatPredictorInputV1;

void need(bool ok, const std::string &what) {
    if (!ok) throw std::runtime_error("ctmscorerows: " + what);
}

CombatPredictorInputV1 predictorInputFromJson(const J &j) {
    need(j.at("schemaVersion") == CombatPredictorInputV1::SCHEMA, "predictor schema");
    need(j.at("fieldSchemaHash") == one_combat::combatPredictorInputFieldSchemaHash(),
         "predictor field hash");
    CombatPredictorInputV1 p;
    const auto &g = j.at("globals");
    p.globals = {g.at("characterClass").get<int>(), g.at("ascension").get<int>(),
                 g.at("act").get<int>(), g.at("floor").get<int>(), g.at("curHp").get<int>(),
                 g.at("maxHp").get<int>(), g.at("gold").get<int>(), g.at("encounter").get<int>(),
                 g.at("roomClass").get<int>(), g.at("lastRoom").get<int>(),
                 g.at("potionCount").get<int>(), g.at("potionCapacity").get<int>(),
                 g.at("potionKeepValue").get<double>(), g.at("isBurningElite").get<bool>()};
    for (const auto &c : j.at("cards"))
        p.cards.push_back({c.at("cardId").get<int>(), c.at("upgraded").get<bool>(),
                           c.at("misc").get<int>(), c.at("bottleBinding").get<int>()});
    for (const auto &r : j.at("relics"))
        p.relics.push_back({r.at("relicId").get<int>(), r.at("data").get<int>(),
                            r.at("orderIndex").get<int>()});
    for (const auto &q : j.at("potions"))
        p.potions.push_back({q.at("slot").get<int>(), q.at("potionId").get<int>()});
    // The serializer is the field contract: a lossless parse must round-trip.
    need(one_combat::combatPredictorInputJson(p) == j, "predictor input does not round-trip");
    return p;
}

} // namespace

// #460 opening hand: the hand after BattleContext::init(gc), i.e. the first
// draw with innate and Bottled cards and the battle-start relics applied.
// Reads gc only; the battle is a scratch copy.
nlohmann::json ctmOpeningHandJson(const sts::GameContext &gc) {
    sts::BattleContext bc;
    bc.init(gc);
    J hand = J::array();
    for (int i = 0; i < bc.cards.cardsInHand; ++i)
        hand.push_back({{"id", static_cast<int>(bc.cards.hand[i].getId())},
                        {"upgraded", bc.cards.hand[i].isUpgraded()}});
    return {{"cards", std::move(hand)}, {"drawPile", bc.cards.drawPile.size()},
            {"inputState", static_cast<int>(bc.inputState)}};
}

namespace {

// A GameContext that enters the recorded fight: the run seed and floor (which
// seed every combat stream except misc and potion), room, encounter and the
// recorded pre-combat persistent state.
sts::GameContext openingHandContext(const J &row, std::uint64_t seed) {
    const auto &g = row.at("predictorInput").at("globals");
    sts::GameContext gc(static_cast<sts::CharacterClass>(g.at("characterClass").get<int>()), seed,
                        g.at("ascension").get<int>());
    gc.act = row.at("act").get<int>();
    gc.floorNum = row.at("floor").get<int>();
    gc.curRoom = static_cast<sts::Room>(g.at("roomClass").get<int>());
    gc.info.encounter = static_cast<sts::MonsterEncounter>(row.at("encounter").get<int>());
    gc.curMapNodeX = -1;   // never the burning elite: monster buffs do not touch the hand
    gc.curMapNodeY = -1;
    one_combat::applyCombatTransitionState(
        gc, one_combat::combatTransitionStateFromJson(row.at("transition").at("pre")));
    return gc;
}

std::uint64_t splitmix(std::uint64_t x) {
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    return x ^ (x >> 31);
}

} // namespace

// #460 offline: the realized opening hand of every recorded row, plus RESAMPLES
// hands of the same fight under fresh run seeds (a fair shuffle of the same
// deck). Rows without a transition are skipped. Runs no seeds.
int ctmOpeningHands(const std::string &inPath, const std::string &outPath, int resamples) {
    need(resamples >= 0 && resamples <= 256, "RESAMPLES must be 0..256");
    std::ifstream in(inPath);
    need(bool(in), "cannot open " + inPath);
    std::ofstream out(outPath);
    need(bool(out), "cannot open " + outPath);
    std::string line;
    int rows = 0, written = 0, checked = 0;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        const J row = J::parse(line);
        need(row.at("rowSchemaVersion") == "combat_transition_row_v2", "row schema");
        ++rows;
        if (row.at("transition").is_null()) continue;
        const auto seed = row.at("sourceSeed").get<std::uint64_t>();
        const auto fightIdx = row.at("fightIdx").get<int>();
        J o = {{"sourceSeed", seed}, {"fightIdx", fightIdx},
               {"openingHand", ctmOpeningHandJson(openingHandContext(row, seed))}};
        // Rows recorded with STS_CTM_ROW_OPENING_HAND=1 carry the live hand: they must agree.
        if (row.contains("openingHand")) {
            need(row.at("openingHand") == o.at("openingHand"),
                 "reconstructed opening hand differs from the recorded one: seed " + std::to_string(seed)
                 + " fight " + std::to_string(fightIdx));
            ++checked;
        }
        J alt = J::array();
        for (int r = 0; r < resamples; ++r) {
            const auto altSeed = splitmix(seed ^ splitmix((std::uint64_t(fightIdx) << 16) + std::uint64_t(r) + 1));
            alt.push_back(ctmOpeningHandJson(openingHandContext(row, altSeed)).at("cards"));
        }
        o["resampledHands"] = std::move(alt);
        out << o.dump() << '\n';
        ++written;
    }
    need(bool(out), "write failed");
    std::cerr << "ctmopeninghands rows=" << rows << " written=" << written << " checkedAgainstRecorded=" << checked
              << " -> " << outPath << "\n";
    return 0;
}

// Writes one CSV line per row. Rows without a transition (quarantined capture)
// are kept with scored=0 so the analysis can count them.
int ctmScoreRows(const std::string &inPath, const std::string &outPath,
                 const std::string &fastModel, const std::string &standardModel, bool activeLizard) {
    const one_combat::EntropicBrewFallbackCombatTransitionSampler sampler(
        fastModel, standardModel, activeLizard);
    if (sampler.fastRuntime().researchCandidate())
        std::cerr << "ctmscorerows research candidate "
                  << sampler.fastRuntime().identity().at("candidateId").get<std::string>() << '\n';
    std::ifstream in(inPath);
    need(bool(in), "cannot open " + inPath);
    std::ofstream out(outPath);
    need(bool(out), "cannot open " + outPath);
    out << "source_seed,fight_idx,act,floor,room_class,encounter,teacher_id,run_valid,"
           "quarantine_reason,combat_outcome,pre_hp,pre_max_hp,post_hp,post_max_hp,"
           "scored,support_reason,p_death,win_hp_fraction,expected_win_hp,"
           "hist_mass,log_p_post_hp\n";
    out << std::setprecision(9);
    std::string line;
    int rows = 0, scored = 0;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        const J row = J::parse(line);
        need(row.at("rowSchemaVersion") == "combat_transition_row_v2", "row schema");
        ++rows;
        const auto input = predictorInputFromJson(row.at("predictorInput"));
        out << row.at("sourceSeed").get<std::uint64_t>() << ',' << row.at("fightIdx").get<int>()
            << ',' << row.at("act").get<int>() << ',' << row.at("floor").get<int>() << ','
            << row.at("roomClass").get<std::string>() << ',' << row.at("encounter").get<int>()
            << ',' << row.at("teacherId").get<std::string>() << ','
            << (row.at("runValid").get<bool>() ? 1 : 0) << ','
            << row.at("quarantineReason").get<std::string>() << ',';
        const auto &t = row.at("transition");
        if (t.is_null()) {
            out << ",,,,,0,no_transition,,,,,\n";
            continue;
        }
        const auto pre = one_combat::combatTransitionStateFromJson(t.at("pre"));
        need(one_combat::combatTransitionStateJson(pre) == t.at("pre"), "pre state does not round-trip");
        const auto &post = t.at("post");
        const int postHp = post.at("curHp").get<int>();
        out << t.at("combatOutcome").get<int>() << ',' << pre.curHp << ',' << pre.maxHp << ','
            << postHp << ',' << post.at("maxHp").get<int>() << ',';
        const auto support = sampler.supportState(pre, input);
        const auto e = sampler.expectationState(pre, input);
        if (!support.supported || !e.supported) {
            out << "0," << support.reason << ",,,,,\n";
            continue;
        }
        ++scored;
        double mass = 0, meanHp = 0;
        for (std::size_t i = 0; i < e.winningHpHistogram.size(); ++i) {
            mass += e.winningHpHistogram[i];
            meanHp += double(e.winningHpMin + int(i)) * e.winningHpHistogram[i];
        }
        out << "1,supported," << e.death << ',' << e.winningHpFraction << ','
            << (mass > 0 ? meanHp / mass : 0.0) << ',' << mass << ',';
        const int bin = postHp - e.winningHpMin;
        if (t.at("combatOutcome").get<int>() == static_cast<int>(sts::Outcome::PLAYER_VICTORY)) {
            const double p = bin >= 0 && bin < int(e.winningHpHistogram.size())
                ? e.winningHpHistogram[bin] / mass : 0.0;
            out << (p > 0 ? std::log(p) : -INFINITY);
        }
        out << '\n';
    }
    std::cerr << "ctmscorerows rows=" << rows << " scored=" << scored << " -> " << outPath << '\n';
    return 0;
}

// Escape-fit features for tools/ctm_escape.py (#418 PR7). For every surviving row the
// escape-capable artifact would support, writes the artifact's own HP encoding z
// (OUT.f32, little-endian float32, 64 per row) and the labels (OUT.csv). Reads rows
// only; runs no seeds.
int ctmEscapeFeatures(const std::string &inPath, const std::string &model, const std::string &outPrefix) {
    const one_combat::NativeCombatTransitionSampler sampler(model);
    const auto &runtime = sampler.runtime();
    need(runtime.nearFull() && !runtime.escapeCapable(), "features need a near-full artifact without the escape capability");
    auto domain = sampler.domain();
    domain.escape = true;
    const auto deltas = runtime.metadata().at("maxHpClasses").get<std::vector<int>>();
    const int classes = static_cast<int>(runtime.metadata().at("hpClasses").size());
    std::ifstream in(inPath);
    need(bool(in), "cannot open " + inPath);
    std::ofstream features(outPrefix + ".f32", std::ios::binary), out(outPrefix + ".csv");
    need(bool(features) && bool(out), "cannot open " + outPrefix);
    out << "source_seed,fight_idx,supported,reason,z_row,delta_class,hp_class,pre_hp,post_max_hp,"
           "escaped,eligible,boss\n";
    std::string line;
    int rows = 0, written = 0;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        const J row = J::parse(line);
        need(row.at("rowSchemaVersion") == "combat_transition_row_v2", "row schema");
        const auto &t = row.at("transition");
        if (t.is_null() || t.at("combatOutcome").get<int>() != static_cast<int>(sts::Outcome::PLAYER_VICTORY))
            continue;
        ++rows;
        out << row.at("sourceSeed").get<std::uint64_t>() << ',' << row.at("fightIdx").get<int>() << ',';
        const auto input = predictorInputFromJson(row.at("predictorInput"));
        const auto pre = one_combat::combatTransitionStateFromJson(t.at("pre"));
        const auto &post = t.at("post");
        auto reasons = one_combat::nativeComposedSupportReasons(input, pre, domain);
        const bool brew = std::any_of(input.potions.begin(), input.potions.end(), [](const auto &p) {
            return p.potionId == static_cast<int>(sts::Potion::ENTROPIC_BREW);
        });
        if (reasons.empty() && runtime.requiresEntropicBrewFallback() && brew)
            reasons.push_back("entropic_brew_requires_standard_ctm");
        const int postMax = post.at("maxHp").get<int>(), postHp = post.at("curHp").get<int>();
        const auto delta = std::find(deltas.begin(), deltas.end(), postMax - pre.maxHp);
        const int hpClass = runtime.hpClassIndex(postHp - pre.curHp);
        if (reasons.empty() && delta == deltas.end()) reasons.push_back("max_hp_label");
        if (reasons.empty() && (hpClass < 0 || hpClass >= classes || postHp < 1 || postHp > postMax))
            reasons.push_back("hp_label");
        if (!reasons.empty()) {
            out << "0," << reasons.front() << ",-1,,,,,,,\n";
            continue;
        }
        const bool boss = sts::isBossEncounter(static_cast<sts::MonsterEncounter>(input.globals.encounter));
        const auto z = runtime.hpEncoding(input);
        need(z.size() == 64, "HP encoding width");
        features.write(reinterpret_cast<const char *>(z.data()), static_cast<std::streamsize>(z.size() * sizeof(float)));
        out << "1,supported," << written++ << ',' << (delta - deltas.begin()) << ',' << hpClass << ','
            << pre.curHp << ',' << postMax << ',' << (post.at("smokeBombUsed").get<bool>() ? 1 : 0) << ','
            << (one_combat::CombatTransitionRuntime::escapeEligible(pre.potions, pre.potionCapacity, boss) ? 1 : 0)
            << ',' << (boss ? 1 : 0) << '\n';
    }
    need(bool(features) && bool(out), "write failed");
    std::cerr << "ctmescapefeatures victories=" << rows << " supported=" << written << " -> " << outPrefix << ".{f32,csv}\n";
    return 0;
}

// Active-Lizard q/r fit features for tools/ctm_lizard.py (#418 PR9). For every row whose
// pre-state has an active Lizard Tail, writes the routed child (standard for Entropic Brew),
// the Fairy/Brew flags, the child's ordinary and reserve survivals, and the label: 0 a win
// with the Tail unused, 1 a win after it fired, 2 a loss. Reads rows only; runs no seeds.
int ctmLizardFeatures(const std::string &inPath, const std::string &fastModel,
                      const std::string &standardModel, const std::string &outPath) {
    const one_combat::EntropicBrewFallbackCombatTransitionSampler sampler(fastModel, standardModel, true);
    constexpr int tail = static_cast<int>(sts::RelicId::LIZARD_TAIL);
    std::ifstream in(inPath);
    need(bool(in), "cannot open " + inPath);
    std::ofstream out(outPath);
    need(bool(out), "cannot open " + outPath);
    out << "source_seed,fight_idx,label,child,fairy,brew,supported,reason,p_ordinary,p_reserve\n";
    out << std::setprecision(9);
    std::string line;
    int rows = 0, written = 0;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        const J row = J::parse(line);
        need(row.at("rowSchemaVersion") == "combat_transition_row_v2", "row schema");
        const auto &t = row.at("transition");
        if (t.is_null()) continue;
        const auto pre = one_combat::combatTransitionStateFromJson(t.at("pre"));
        const auto active = std::find_if(pre.relics.begin(), pre.relics.end(), [](const auto &r) {
            return r.id == tail;
        });
        if (active == pre.relics.end() || active->data != 1) continue;
        ++rows;
        const int outcome = t.at("combatOutcome").get<int>();
        int label = 2;
        if (outcome == static_cast<int>(sts::Outcome::PLAYER_VICTORY)) {
            label = 0;
            for (const auto &r : t.at("post").at("relics"))
                if (r.at("id").get<int>() == tail && r.at("data").get<int>() == 0) label = 1;
        } else need(outcome == static_cast<int>(sts::Outcome::PLAYER_LOSS), "combat outcome");
        const auto input = predictorInputFromJson(row.at("predictorInput"));
        const auto f = sampler.activeLizardFeatures(pre, input);
        out << row.at("sourceSeed").get<std::uint64_t>() << ',' << row.at("fightIdx").get<int>() << ','
            << label << ',' << (f.brew ? "standard" : "fast") << ',' << int(f.fairy) << ',' << int(f.brew) << ','
            << int(f.supported) << ',' << f.reason << ',';
        if (f.supported) {
            out << f.pOrdinaryWin << ',' << f.pReserveWin;
            ++written;
        } else out << ',';
        out << '\n';
    }
    need(bool(out), "write failed");
    std::cerr << "ctmlizardfeatures activeLizardRows=" << rows << " supported=" << written << " -> " << outPath << "\n";
    return 0;
}

// §527: native parity of the Act-4 survival model (STS_CTM_ACT4_SURVIVAL_MODEL, default on for pathb-a20) with the
// Python fit. Each fixture line holds an Act-4 predictorInput and the Python death probability
// (tools/ctm_act4_survival.py).
int ctmAct4SurvivalSelfTest(const std::string &fixturePath) {
    const one_combat::EntropicBrewFallbackCombatTransitionSampler sampler(
        "selfplay/models/combat_transition_deepsets_pathb_a20_lizard.native",
        "selfplay/models/combat_transition_near_full_escape_pathb_a20.native", false);
    std::ifstream in(fixturePath);
    need(bool(in), "cannot open " + fixturePath);
    std::string line;
    int n = 0;
    double worst = 0;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        const J row = J::parse(line);
        const auto input = predictorInputFromJson(row.at("predictorInput"));
        need(input.globals.encounter == static_cast<int>(sts::MonsterEncounter::THE_HEART) ||
             input.globals.encounter == static_cast<int>(sts::MonsterEncounter::SHIELD_AND_SPEAR),
             "fixture row is not an Act-4 fight");
        worst = std::max(worst, std::abs(1.0 - sampler.fastRuntime().survival(input) - row.at("pDeath").get<double>()));
        ++n;
    }
    if (n == 0 || !(worst < 1e-5)) {
        std::cerr << "ctmact4survivaltest FAIL rows=" << n << " max_abs_diff=" << worst << '\n';
        return 1;
    }
    std::cout << "ctmact4survivaltest PASS rows=" << n << " max_abs_diff=" << worst << '\n';
    return 0;
}

// Scores the deterministic transition fixture rows and checks the output shape.
int ctmScoreRowsSelfTest() {
    const auto dir = std::filesystem::temp_directory_path()
        / ("sts_ctm_score_selftest_" + std::to_string(::getpid()));
    std::filesystem::create_directories(dir);
    const auto rows = (dir / "rows.jsonl").string(), csv = (dir / "scores.csv").string();
    combatTransitionFixture(rows, (dir / "rows.manifest.json").string());
    ctmScoreRows(rows, csv);
    std::ifstream in(csv);
    std::string header, line;
    std::getline(in, header);
    int n = 0, scored = 0;
    while (std::getline(in, line)) {
        ++n;
        if (line.find(",1,supported,") != std::string::npos) ++scored;
    }
    std::filesystem::remove_all(dir);
    if (n != 3 || scored != 3) {
        std::cerr << "ctmscoreselftest FAIL rows=" << n << " scored=" << scored << '\n';
        return 1;
    }
    std::cout << "ctmscoreselftest PASS rows=3 scored=3\n";
    return 0;
}
