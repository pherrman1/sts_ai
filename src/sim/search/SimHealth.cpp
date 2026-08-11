//
// SimHealth.cpp: runtime simulator-health monitor implementation.
//
// See include/sim/search/SimHealth.h for the contract. The report function is
// deliberately small and self-contained: format the diagnostic, serialize the
// offending state with the fightrep BattleContext format, write a metadata
// sidecar. Policy/control-flow code decides WHEN an invariant has failed; this
// file only reports and captures.
//

#include "sim/search/SimHealth.h"

#include "combat/BattleContextBinary.h"
#include "constants/MonsterEncounters.h"
#include "sim/search/BattleScumSearcher2.h"
#include "sim/search/BattleScumSearcher3.h"

#include <atomic>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>

namespace sts::search {

thread_local int g_simHealthFailureCount = 0;

namespace {

const char *failureName(SimHealthFailure f) {
    switch (f) {
        case SimHealthFailure::UNDECIDED_BATTLE_EXIT: return "UNDECIDED_BATTLE_EXIT";
        case SimHealthFailure::NO_LEGAL_PROGRESSION:  return "NO_LEGAL_PROGRESSION";
        case SimHealthFailure::INVALID_LIVE_ACTION:   return "INVALID_LIVE_ACTION";
    }
    return "UNKNOWN";
}

// STS_SIM_HEALTH_CAPTURE_DIR: opt-in capture directory (read once, thread-safe
// static init). Unset -> diagnostics still appear, no disk capture.
std::string captureDir() {
    static const std::string dir = [] {
        const char *e = std::getenv("STS_SIM_HEALTH_CAPTURE_DIR");
        return e ? std::string(e) : std::string();
    }();
    return dir;
}

std::string metadataText(const BattleContext &bc, const SimHealthMeta &meta,
                         const char *name) {
    std::ostringstream os;
    os << "reason=" << name << '\n';
    os << "seed=" << bc.seed << '\n';
    os << "floor=" << bc.floorNum << '\n';
    os << "encounter=" << monsterEncounterEnumNames[(int)bc.encounter]
       << '(' << (int)bc.encounter << ")\n";
    os << "turn=" << bc.turn << '\n';
    os << "decisionIdx=" << meta.decisionIdx << '\n';
    os << "playerHp=" << bc.player.curHp << '/' << bc.player.maxHp << '\n';
    os << "outcome=" << battleOutcomeStrings[(int)bc.outcome]
       << '(' << (int)bc.outcome << ")\n";
    os << "inputState=" << (int)bc.inputState << '\n';
    os << "cardSelectTask=" << cardSelectTaskStrings[(int)bc.cardSelectInfo.cardSelectTask]
       << '(' << (int)bc.cardSelectInfo.cardSelectTask << ")\n";
    os << "pickCount=" << bc.cardSelectInfo.pickCount << '\n';
    os << "cardsInHand=" << bc.cards.cardsInHand << '\n';
    os << "drawPile=" << bc.cards.drawPile.size() << '\n';
    os << "discardPile=" << bc.cards.discardPile.size() << '\n';
    os << "exhaustPile=" << bc.cards.exhaustPile.size() << '\n';
    if (meta.hasChosenAction) os << "chosenActionBits=" << meta.chosenActionBits << '\n';
    os << "rng.ai=" << bc.aiRng.counter << '\n';
    os << "rng.cardRandom=" << bc.cardRandomRng.counter << '\n';
    os << "rng.misc=" << bc.miscRng.counter << '\n';
    os << "rng.monsterHp=" << bc.monsterHpRng.counter << '\n';
    os << "rng.potion=" << bc.potionRng.counter << '\n';
    os << "rng.shuffle=" << bc.shuffleRng.counter << '\n';
    os << "searcherType=" << (g_useSearcher3 ? "S3" : "S2") << '\n';
    os << "fairMode=" << (g_fairPlay ? "1" : "0") << '\n';
    os << "particles=" << g_s3Particles << '\n';
    return os.str();
}

// Race-safe capture write. The per-process atomic sequence number guarantees a
// unique stem even when multiple threads fail at the same state in the same
// run. Capture failures only print; the original health diagnostic was already
// emitted and is never hidden.
void writeCapture(const BattleContext &bc, const SimHealthMeta &meta,
                  const char *name) {
    const std::string dir = captureDir();
    if (dir.empty()) return;
    // Create the capture directory on demand so a freshly-set
    // STS_SIM_HEALTH_CAPTURE_DIR "just works"; genuine write failures (e.g.
    // permissions) still fall through to the capture-write warning below.
    std::error_code ec;
    std::filesystem::create_directories(dir, ec);
    static std::atomic<int> seq{0};
    std::ostringstream stem;
    stem << "sim_bug_" << bc.seed << "_f" << bc.floorNum << "_t" << bc.turn;
    if (meta.decisionIdx >= 0) stem << "_d" << meta.decisionIdx;
    stem << '_' << name << '_' << seq.fetch_add(1);

    const std::vector<std::uint8_t> blob = sts::serializeBattleContext(bc);
    {
        std::ofstream bin(dir + '/' + stem.str() + ".bin", std::ios::binary);
        if (!bin) {
            std::cerr << "[sim-health][capture-write-error] cannot open "
                      << dir << '/' << stem.str() << ".bin "
                      << "(original health diagnostic above)\n";
            return;
        }
        bin.write((const char *)blob.data(), (std::streamsize)blob.size());
    }
    {
        std::ofstream txt(dir + '/' + stem.str() + ".txt");
        if (!txt) {
            std::cerr << "[sim-health][capture-write-error] cannot open "
                      << dir << '/' << stem.str() << ".txt "
                      << "(original health diagnostic above)\n";
            return;
        }
        txt << metadataText(bc, meta, name);
    }
}

} // namespace

void reportSimHealthFailure(const BattleContext &bc, SimHealthFailure reason,
                            const SimHealthMeta &meta) {
    ++g_simHealthFailureCount;
    const char *name = failureName(reason);

    std::ostringstream diag;
    diag << "[sim-health][HARD] " << name
         << " seed=" << bc.seed
         << " floor=" << bc.floorNum
         << " encounter=" << monsterEncounterEnumNames[(int)bc.encounter]
         << '(' << (int)bc.encounter << ')'
         << " turn=" << bc.turn;
    if (meta.decisionIdx >= 0) diag << " decision=" << meta.decisionIdx;
    diag << " inputState=" << (int)bc.inputState;
    if (bc.inputState == InputState::CARD_SELECT) {
        diag << " cardSelectTask=" << cardSelectTaskStrings[(int)bc.cardSelectInfo.cardSelectTask]
             << '(' << (int)bc.cardSelectInfo.cardSelectTask << ')'
             << " pickCount=" << bc.cardSelectInfo.pickCount;
    }
    diag << " hand=" << bc.cards.cardsInHand
         << " draw=" << bc.cards.drawPile.size()
         << " discard=" << bc.cards.discardPile.size()
         << " exhaust=" << bc.cards.exhaustPile.size()
         << " outcome=" << battleOutcomeStrings[(int)bc.outcome]
         << '(' << (int)bc.outcome << ')'
         << " playerHp=" << bc.player.curHp << '/' << bc.player.maxHp;
    if (meta.hasChosenAction) {
        diag << " actionBits=0x" << std::hex << meta.chosenActionBits << std::dec;
    }
    std::cerr << diag.str() << '\n';

    writeCapture(bc, meta, name);
}

void reportSimHealthWarning(const BattleContext &bc, const char *code,
                            const SimHealthMeta &meta) {
    (void)meta;
    std::cerr << "[sim-health][WARN] " << code
              << " seed=" << bc.seed << " floor=" << bc.floorNum
              << " turn=" << bc.turn << " hand=" << bc.cards.cardsInHand
              << " outcome=" << battleOutcomeStrings[(int)bc.outcome]
              << '\n';
}

} // namespace sts::search
