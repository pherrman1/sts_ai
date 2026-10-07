// Offline scoring of recorded combat_transition_row_v2 rows with the live
// OOC MCTS combat stack (#418 Stage 0). Reads rows only; runs no seeds.
#include "one_combat/driver_shared.h"
#include "one_combat/combat_predictor_input.h"
#include "one_combat/combat_transition.h"
#include "one_combat/combat_transition_runtime.h"

#include <cmath>
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

// Writes one CSV line per row. Rows without a transition (quarantined capture)
// are kept with scored=0 so the analysis can count them.
int ctmScoreRows(const std::string &inPath, const std::string &outPath) {
    const one_combat::EntropicBrewFallbackCombatTransitionSampler sampler(
        "selfplay/models/combat_transition_deepsets_lizard_t2.native",
        "selfplay/models/combat_transition_near_full_except_smoke_v2.native", true);
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
