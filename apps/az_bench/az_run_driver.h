// Stage 1 of the Amber-Eye-style self-play loop (2026-11-17): the whole-run self-play producer. Worker threads each
// play hundreds of A20 Ironclad runs from Neow to the end; every decision with more than one legal action runs a
// Gumbel AlphaZero search whose leaves are net evaluations, as in the stage 0 combat driver (az_driver.h): requests
// go on one queue, batching threads (Python with the GPU net) pack them into flat batches (az_pack.h) and post the
// results back. Positions of searched moves are kept as training samples whose labels (final outcome, HP at the end
// of the floor) are filled in when the run ends.
//
// From https://8e9f.github.io/amber_eye/: one net for combat and out-of-combat states; Gumbel AlphaZero with 64 / 16
// positions per full / fast move, playout cap randomization p = 0.25; double progressive widening at chance nodes;
// a step that reveals hidden information is resampled in the search; utility U = F + H at first (F = expected final
// floor, H = HP), later P(win) + 0.25 H out of combat and F + 0.5 H in combat.
//
// Our choices (defaults; RunConfig::chanceOnReveal / crossCombat / simHelp switch to Amber's rules): the search tree ends at combat boundaries: an out-of-combat action that starts a fight leads to a
// leaf (the fight's first decision, valued by the net) and a combat action that wins the fight leads to a leaf (the
// state after the fight, valued by the net); a lost fight is terminal. Out-of-combat edges are all chance edges: each
// new outcome is a detached copy of the parent with its hidden future resampled (sampleNoncombatFuture) before the
// action executes; combat edges reseed the search RNG as in stage 0. F = E[final floor] / 57 (a win counts 57), H =
// E[HP at the end of the floor] / max HP; the net's heads are turned into F and E[HP] by the caller, the driver
// mixes U = F + w H with w = hpWeightCombat or hpWeightOoc and scales by 1 / (1 + w) into [0, 1]. One leaf in flight
// per run (RunConfig::parallelNodes: Amber's several per candidate), no tree reuse between moves. The improved policy completes unvisited edges' Q with the net's root value
// (not the paper's v_mix; a stage-1 simplification).
#ifndef STS_AZ_RUN_DRIVER_H
#define STS_AZ_RUN_DRIVER_H

#include <algorithm>
#include <array>
#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <deque>
#include <memory>
#include <mutex>
#include <optional>
#include <random>
#include <stdexcept>
#include <thread>
#include <unordered_map>
#include <vector>

#include "az_pack.h"
#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/Action.h"
#include "sim/search/AmberTokens.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/GameAction.h"
#include "sim/search/SilverSearcher.h"

namespace sts::azbench {

    using CombatEncodeFn = void (*)(const BattleContext &, const search::SilverSearchContext &,
                                    const std::vector<search::Action> &, search::AmberTokens &);
    using GameEncodeFn = void (*)(const GameContext &, const std::vector<search::GameAction> &,
                                  search::AmberTokens &);

    // Placeholder out-of-combat encoder (the default is the native search::amberEncodeGame): run / deck / relic / potion
    // tokens and one OPTION token per legal action (type = screen, action bits as features).
    void stubEncodeGame(const GameContext &gc, const std::vector<search::GameAction> &actions,
                        search::AmberTokens &out);

    // Fair play (ADR-0002): the search and the net see a fight only through the player's public view, as the
    // production Silver search does (nativeSilverSearchRoot): the draw pile is the player's information set (known
    // top / bottom, unknown multiset; concrete only under Frozen Eye) and under Runic Dome the rolled intents are
    // hidden. A per-run CombatKnowledgeState follows the real fight; it observes bc.init and every real action.
    //
    // Starts the fight of gc in bc with knowledge tracking (knowledge is reset).
    void initObservedBattle(const GameContext &gc, BattleContext &bc, search::CombatKnowledgeState &knowledge);
    // Executes a real combat action with the knowledge tracker observing it.
    void executeObserved(BattleContext &bc, std::uint32_t bits, search::CombatKnowledgeState &knowledge);
    // The public view of a live fight (search root and net input). Returns an empty string, or why the view cannot
    // be built (the run is then abandoned as a loss).
    std::string publicCombatRoot(const BattleContext &live, search::CombatKnowledgeState &knowledge,
                                 BattleContext &root);

    constexpr int kOutcomeClasses = 57;   // 0 = win, f = death on floor f (1..56)
    constexpr int kHpClasses = 256;
    constexpr int kAscensions = 21;
    constexpr int kFloors = 56;           // floors 1..56 of the per-floor HP head (utility AMBER)

    // Utility H of the search (U = (F + w H) / (1 + w), F = E[final floor] / 57, a win counts 57).
    //   FLOOR_HP (stage 1 default): H = E[HP at the end of the current floor] / max HP, from the 256-class HP head.
    //   AMBER (2026-11-17, default off): Amber Eye's early utility, H = 1/56 [(floor - 1) + sum_{f >= floor} E[HP_f] / 255]
    //     with E[HP_f] (f = 1..56) from a per-floor HP head (0 after death); past floors count 1 each. A run that
    //     ends alive (Heart kill, or the act 3 boss without the keys) keeps its last HP on its last floor; a Heart
    //     kill also keeps it on the floors after (our choice), a keyless victory has 0 there (the run is over).
    // AMBER2 (2026-11-20, Amber Eye's later utility, "after a few more hours" once the win rate was significant):
    // out of combat P(win) + 0.25 H, in combat F + 0.5 H, both with Amber's H; which one applies is the evaluated
    // STATE's kind ("for out-of-combat states ... for in-combat states", Philipp's fidelity choice 2026-11-20), so a
    // fight-start leaf under an out-of-combat root gets the combat utility. P(win) is the outcome head's class 0, so
    // AMBER2 needs dist in submit. Both are divided by the same 1.5 (in [0, 1]): a constant factor keeps Amber's
    // cross-kind ratios exactly (an out-of-combat state is worth at most 1.25 / 1.5).
    // AMBER2_ROOT (2026-11-20): the same two utilities, but the search ROOT's kind picks one for the whole tree
    // (every leaf and terminal of a tree uses it). With --cross-combat, per-state kinds put a won fight's next
    // out-of-combat state (P(win) + 0.25 H) far below the fight itself (F + 0.5 H) unless the win rate is ~90 %:
    // at A12 (~3 % wins) the search stalled fights and runs died on floor 1-2. One utility per tree has no such jump.
    // Amber's page does not say which; Philipp chose to try the root kind (2026-11-20).
    enum class Utility : int { FLOOR_HP = 0, AMBER = 1, AMBER2 = 2, AMBER2_ROOT = 3 };
    inline bool isAmber2(Utility u) { return u == Utility::AMBER2 || u == Utility::AMBER2_ROOT; }
    inline bool usesAmberH(Utility u) { return u == Utility::AMBER || isAmber2(u); }
    constexpr double kAmber2HpOoc = 0.25, kAmber2HpCombat = 0.5, kAmber2Scale = 1.5;
    // AMBER2 value of a leaf (net) or terminal state: in combat (F + 0.5 H) / 1.5, else (P(win) + 0.25 H) / 1.5.
    inline double amber2Value(bool stateCombat, double F, double pWin, double H) {
        const double w = stateCombat ? kAmber2HpCombat : kAmber2HpOoc;
        return (std::clamp(stateCombat ? F : pWin, 0.0, 1.0) + w * H) / kAmber2Scale;
    }

    // Amber H of a state on `floor` from per-floor HP predictions hpf[f - 1] = E[HP_f] / 255 (clamped to [0, 1]).
    inline double amberH(int floor, const float *hpf) {
        const int fl = std::clamp(floor, 1, kFloors);
        double s = fl - 1;
        for (int f = fl; f <= kFloors; ++f) s += std::clamp(static_cast<double>(hpf[f - 1]), 0.0, 1.0);
        return s / kFloors;
    }

    // Amber H of a finished run that ended on `floor` with `hp`: death (alive = false) has HP 0 from its floor on;
    // a keyless act 3 victory has hp on its floor and 0 after; a Heart kill has hp on its floor and all later ones.
    inline double amberTerminalH(bool heartKill, bool alive, int floor, int hp) {
        const int fl = std::clamp(floor, 1, kFloors);
        const double h = alive ? std::clamp(hp, 0, 255) / 255.0 : 0.0;
        return ((fl - 1) + h * (heartKill ? kFloors - fl + 1 : 1)) / kFloors;
    }

    // Per-floor HP labels of a sample on `sampleFloor` (Amber utility): out[f - 1] = HP at the end of floor f for
    // f >= max(1, sampleFloor), -1 (masked) before. floorHp[f] (f = 1..56) is the run's recorded HP at the end of floor
    // f (-1 = not reached); unreached floors get `tailHp` (0 after a death or a keyless victory, the final HP after a
    // Heart kill).
    inline void amberFloorLabels(int sampleFloor, const std::int16_t *floorHp, int tailHp, std::int16_t *out) {
        const int fl = std::clamp(sampleFloor, 1, kFloors);
        for (int f = 1; f <= kFloors; ++f)
            out[f - 1] = f < fl ? std::int16_t(-1) : (floorHp[f] >= 0 ? floorHp[f] : static_cast<std::int16_t>(tailHp));
    }

    // Completed Q of k edges (prior logits, visits n, value sums w) of a node with net value `value`. rescale false:
    // a visited edge's mean w / n, an unvisited one `value`. rescale true (Gumbel MuZero, mctx
    // qtransform_completed_by_mix_value): an unvisited edge gets v_mix = (value + N sum_visited(pi q) /
    // sum_visited(pi)) / (1 + N) with pi = softmax(logit), N = sum n; then all k values are min-max rescaled to
    // [0, 1] (range floored at 1e-8, so equal values all map to 0).
    void completedQValues(int k, const float *logit, const std::int32_t *n, const double *w, double value,
                          bool rescale, double *q);

    // Amber Eye exploration (RunConfig::exploreAmber): the finished runs in which an item appeared, by the item's
    // smallest gap m to the top pick in that run (m = 0: the search picked it itself). Gaps m > 0 go into bins of
    // kBin (the last bin takes m >= (kBins - 1) kBin, where exp(-m / 4) < 5e-5).
    struct AmberGapHist {
        static constexpr double kBin = 0.05;
        static constexpr int kBins = 800;
        std::int64_t natural = 0;              // runs with m = 0
        std::array<std::uint32_t, kBins> n{};  // runs with m > 0, by bin
        std::int64_t runs = 0;                 // runs in which the item was offered (natural + sum n)
        void add(double m) {
            ++runs;
            if (m <= 0) { ++natural; return; }
            ++n[std::min(kBins - 1, static_cast<int>(m / kBin))];
        }
    };

    // Amber Eye's per-item c: the c with natural + sum_b n_b min(1, c exp(-m_b / T)) = need (m_b = bin centre), i.e.
    // the c at which the item, boosted with probability min(1, c exp(-m / T)), would have been picked in `need` of the
    // logged runs. 0 when natural >= need; +infinity when even always picking it falls short. Bisection on log c.
    double amberExploreC(const AmberGapHist &h, double need, double T);

    // Pick-rate item of a root action (exploreC / exploreAmber): a hash of the action type and its source token (a
    // CARD or an OPTION token of amberEncodeGame); the driver keeps its low bits as the item's bucket.
    //   clean false (the first rule, 2026-11-17): the token's ids[0], ids[1] and, for an OPTION, its features 12-51.
    //     Those hold the kind one-hot but also the index within the group (30), legal (31), price (32), affordable
    //     (33), gold amount (34), upgraded (35), specialData (38): one shop item at two prices or in two slots is
    //     two items, so most shop offers are items of their own (never offered in pickTarget of the runs), and
    //     of the Neow bonus one-hot (40-58) and drawback one-hot (59-63) only 40-51 count.
    //   clean true (RunConfig::exploreCleanKeys, 2026-11-21): what the choice IS. A CARD token: its card id. An
    //     OPTION: ids[0] (the card / relic / potion / event id), its kind (reward relic, shop card, shop relic,
    //     shop potion, boss relic, ... stay separate items, as Amber Eye's separate charts) and by kind: REST the
    //     rest option one-hot (40-46), NEOW the bonus and drawback one-hots (40-63), EVENT the option index one-hot
    //     (40-51). Not the slot, price, affordability, upgrade, or the deck card / relic an event option names.
    inline std::uint64_t exploreItemHash(int actionType, const search::AmberToken &tok, bool option, bool clean) {
        constexpr std::uint64_t kMul = 0x100000001b3ull;
        std::uint64_t h = 0x9e3779b97f4a7c15ull * static_cast<std::uint64_t>(actionType + 1);
        if (!clean) {
            for (int c = 0; c < 2; ++c) h = (h ^ static_cast<std::uint16_t>(tok.ids[c])) * kMul;
            if (option)
                for (int c = 12; c < 52; ++c) h = (h ^ tok.f[c]) * kMul;
            h ^= h >> 29;
            return h;
        }
        h = (h ^ static_cast<std::uint16_t>(tok.ids[0])) * kMul;
        if (option) {
            int kind = -1;
            for (int c = 12; c <= 28; ++c) if (tok.f[c]) { kind = c - 12; break; }
            h = (h ^ static_cast<std::uint64_t>(kind + 2)) * kMul;
            int lo = 0, hi = -1;   // OptKind (AmberGameEncoder.cpp): REST 12, NEOW 13, EVENT 14
            if (kind == 12) { lo = 40; hi = 46; }
            else if (kind == 13) { lo = 40; hi = 63; }
            else if (kind == 14) { lo = 40; hi = 51; }
            for (int c = lo; c <= hi; ++c) h = (h ^ static_cast<std::uint64_t>(tok.f[c] != 0)) * kMul;
        }
        h ^= h >> 29;
        return h;
    }

    // Singing Bowl (+2 Max HP instead of a card reward): the engine accepts and executes RewardsActionType::CARD
    // (group, 5), but GameAction::getAllActionsInState (sts_lightspeed import) never lists it, so the net could not
    // choose it although amberEncodeGame shows the SINGING_BOWL option. On a reward screen with the relic, appends
    // one such action per card reward (the game offers the Bowl on each) and returns how many; else 0.
    int appendSingingBowlActions(const GameContext &gc, std::vector<search::GameAction> &v);

    // Potion discards out of combat (2026-11-19, Philipp's choice "discard where it helps"): with every potion slot
    // full, no Sozu, and a potion on offer (a reward potion, or a shop potion the gold affords), appends one discard
    // (bits 0xC0000000 | slot) per distinct held potion, so the net can make room for the offered one; discarding
    // anywhere else never beats keeping the potion. GameAction::getAllActionsInState lists no potion action. Returns
    // how many were added.
    int appendPotionReplacementDiscards(const GameContext &gc, std::vector<search::GameAction> &v);

    // Out-of-combat drinks (2026-11-19, Philipp: "basically only Fruit Juice and Blood Potion", where it helps): on
    // every out-of-combat decision screen except card selects, one drink (bits 0x80000000 | slot) per distinct held
    // Fruit Juice (+5 Max HP, always) and Blood Potion (heal, only below Max HP). Returns how many were added.
    int appendOocPotionDrinks(const GameContext &gc, std::vector<search::GameAction> &v);

    // RunConfig::forceKeys: restricts v (the legal out-of-combat actions of gc) by the ADR-0063 key backstops
    // (search::heartKeyAction / heartKeyActionAllowed, keys collected). Returns -1 when nothing was removed, 0 / 1 / 2
    // when a Sapphire / Ruby / Emerald backstop left a single action, 3 when the Emerald rule narrowed the Act-3 route
    // to the edges that still reach the burning elite.
    int keyBackstopActions(const GameContext &gc, std::vector<search::GameAction> &v);

    // RunConfig::oocCanon: on a CARD_SELECT screen, drops every selection whose card (Card ==, bottle state) equals an
    // earlier selectable one. Returns the number of actions removed.
    int canonicalOocSelectActions(const GameContext &gc, std::vector<search::GameAction> &v);
    // RunConfig::forcePotions: on a REWARDS screen whose offered potions all fit into the free slots, keeps only the
    // first potion pickup (when v has it and more than one action). Returns 1 when it restricted v, else -1.
    int forcedRewardPotionActions(const GameContext &gc, std::vector<search::GameAction> &v);

    // RunConfig::forceRewards: restricts v (the legal out-of-combat actions of gc) on a treasure room and a REWARDS
    // screen (elites, chests, event fights; not the boss relic screen). Returns -1 when nothing was removed, 0 when only
    // opening the chest is left (no Cursed Key), 1 when only taking a forced relic is left, 2 when a card-first relic
    // (Whetstone, War Paint) was removed while a card reward is still open. A forced relic is every offered relic
    // except Philipp's reviewed list (Bottled Flame / Lightning / Tornado, Dead Branch, Tungsten Rod, Unceasing Top,
    // Juzu Bracelet; apps/one_combat/ooc_tree_rules.cpp) and the relic paired with a Sapphire Key.
    int forcedRewardActions(const GameContext &gc, std::vector<search::GameAction> &v);
    // forceRewards: the forced relic still on gc's REWARDS screen that leaving it (SKIP) takes first (a card-first
    // relic deferred while the card reward was open), or nullopt.
    std::optional<search::GameAction> forcedRewardBeforeLeave(const GameContext &gc);

    // Heart search probe (RunConfig::heartArms): one arm's search budget for the Heart fight.
    struct HeartArm {
        int fullSims = 64, fastSims = 16;
        double fullProb = 0.25;
        int fullCandidates = 16, fastCandidates = 4;
    };

    // Heart search probe: one Heart fight played from a stored start.
    struct HeartResult {
        std::uint64_t seed = 0;     // the run seed the start came from
        int arm = 0, rep = 0;
        int win = 0;                // the Heart was killed
        int heartHp = 0;            // Heart HP left at the fight's end (0 on a kill)
        int heartMaxHp = 0;
        int playerHpStart = 0, playerMaxHp = 0, playerHpEnd = 0;
        int turns = 0, moves = 0, searched = 0, stall = 0;
        int deckSize = 0, relics = 0, asc = 0;
    };

    // Per-run Heart log (RunConfig::heartLogRate, 2026-11-19, diagnostic, default off): one record per finished run
    // that fought the Heart (every kill; other Heart runs with probability heartLogRate, decided by a hash of the run
    // seed, so the search RNG is untouched). Net / search values are -1 when the outcome distribution is not
    // available (searchEmaLambda == 0).
    struct HeartRunLog {
        std::uint64_t seed = 0;
        int asc = 0, win = 0, floor = 0;
        int heartHp = 0, heartMaxHp = 0;        // Heart HP left at the fight's end (0 on a kill)
        int entryHp = 0, entryMaxHp = 0;        // player HP entering the Heart fight
        int endHp = 0;                          // player HP at the run's end (0 after a death)
        int turns = 0, gold = 0;
        // Root of the run's first searched move in each act (index act - 1, 1..4) and of the Heart fight's first
        // searched move (index 4): the net's P(win), P(death on the Heart floor, outcome class 55, in every slot),
        // E[final floor] (win = 57) and
        // utility value at the root, and the search result's P(win) and mean utility after the move's search.
        // floorAt = the floor of that root (-1 = never reached).
        std::array<int, 5> floorAt{-1, -1, -1, -1, -1};
        std::array<float, 5> netPWin{}, netPHeartDeath{}, netEFloor{}, netValue{}, searchPWin{}, searchValue{};
        std::array<std::int16_t, kFloors + 1> floorHp{};   // utility AMBER: HP at the end of floor f (-1 = none)
        std::vector<std::pair<int, int>> deck;   // (CardId, upgraded) at the Heart fight's start
        std::vector<int> relics;                 // RelicId at the Heart fight's start
        std::vector<int> potions;                // Potion at the Heart fight's start (non-empty slots)
        std::int64_t elites = 0, rest = 0, smith = 0;
    };

    struct RunConfig {
        int workers = 11;
        int gamesPerWorker = 700;
        int ascension = 20;             // of the first runs; setAscension changes it while running
        std::uint64_t seedBase = 0;     // run seeds seedBase, seedBase + 1, ... (one per started run)
        std::int64_t maxRuns = -1;      // stop starting runs after this many (-1 = unlimited)
        int fullSims = 64, fastSims = 16;
        int fullCandidates = 16, fastCandidates = 4;
        double fullProb = 0.25;
        double cVisit = 50, cScale = 1.0;
        // Search-noise / Q-transform flags (2026-11-17, both default = previous behaviour):
        // fastNoise false: fast (low-budget) moves get no Gumbel noise (Amber Eye: "not applying exploration noise to
        // them"); they pick the top logits as candidates and play the best logit + sigma(Q).
        // qRescale true: completed Q as in Gumbel MuZero / mctx (unvisited edges = mixed value, then min-max rescale of
        // each node's completed Q to [0, 1]), at the root (halving, final pick, improved policy) and inside the tree.
        // With it, mctx's value scale cScale = 0.1 is the paper setting (cScale 1 then makes the policy nearly argmax).
        bool fastNoise = true;
        bool qRescale = false;
        double wideningC = 3.7028, wideningAlpha = 0.52389;
        double hpWeightCombat = 1.0, hpWeightOoc = 1.0;   // U = F + w H (Amber's first utility: both 1)
        Utility utility = Utility::FLOOR_HP;   // H (see Utility); AMBER needs per-floor HP results in submit
        // FLOOR_HP only (2026-11-17, default off): a keyless act 3 victory (the run ends after the act 3 boss without
        // the three keys, no win) keeps H = HP / max HP as a terminal and HP as its floor's hp_end label, instead of
        // H = 0 like a death (which made beating the boss worth about as much as dying to it). AMBER always does.
        bool keylessHp = false;
        int maxMovesPerFight = 400;     // a fight past this many decisions counts as lost (stall guard)
        double keepFull = 1.0;          // keep probability of a full-search move as a sample (policy + value)
        double keepFast = 0.0;          // ... of a fast-search move (value only)
        // Samples of unfinished runs wait in memory for their labels (~5.5 KB each). Above this many, the keep
        // probabilities are scaled by maxPendingSamples / pending, so memory stays bounded as runs get longer.
        // <= 0 (2026-11-17): no cap, every kept move becomes a sample (Amber Eye trains on all full moves).
        std::int64_t maxPendingSamples = 300000;
        std::uint64_t searchSeed = 0;   // search / Gumbel / resampling RNG
        int testMaxHp = 0;              // tests only: > 0 sets max / current HP at the run's start (reach late floors)
        // Pick-rate exploration (from Amber Eye; 2026-11-17, default off): an out-of-combat item (CHOOSE_CARD / CHOOSE_OPTION source token: card reward, event /
        // Neow option, relic, shop item) picked in fewer than pickTarget of all runs so far is under target. A root
        // offering one gets a full search, and with probability min(1, exploreC * (1 - rate / pickTarget)) the most
        // under-target item is played instead of the search's choice (the sample keeps the search policy). Rates are over
        // the runs finished in this process, after a warm-up of 1 / pickTarget runs.
        double exploreC = 0;
        double pickTarget = 0.01;
        // Amber Eye exploration (2026-11-17, default off; not with exploreC): the same items, rate = share of finished
        // runs in which the item was played (once per run), under target below pickTarget (same warm-up). A root
        // offering an under-target item gets a full search in which every under-target item is a candidate on top of
        // the usual ones and survives every halving. After the search, the under-target items other than the pick are
        // tried in random order: item i is played instead with probability min(1, c_i exp(-m_i / exploreT)), m_i the
        // gap of its policy logit (the net's prior logit; Amber Eye: "how far they are below the choice actually taken
        // (in terms of policy logits)") below the pick's, 0 if above; the first hit is played. Only the item the search
        // itself played counts as m = 0 ("natural") in the log; any other item logs at least 1e-9 (bin 0). c_i is amberExploreC over the runs finished so far (each run logs every item's smallest gap). The
        // sample keeps the search policy; the run's labels follow the move played.
        bool exploreAmber = false;
        double exploreT = 4.0;
        // exploreAmber variant (2026-11-19, default off; a deviation from Amber Eye's text, Philipp): the pick-rate target
        // counts the runs in which the item was OFFERED, not all runs. An item is under target when it was played in fewer
        // than pickTarget of the finished runs that offered it (after 1 / pickTarget such runs), and c solves the same
        // bisection with need = pickTarget * offered runs, so c stays finite. Without it an item offered in fewer than
        // pickTarget of all runs can never reach the target, gets c = infinity and is forced at every offer.
        bool explorePerOffer = false;
        // exploreAmber variants (2026-11-19, default off; deviations from our reading of Amber Eye's text, Philipp
        // decides per run). exploreGapSearch: the gap m of an item is taken in the search's final root score
        // (Gumbel + logit + sigma(completed Q)) below the search's pick, instead of in the net's prior logits.
        // exploreDeckOnly: only acquisitions (card rewards / shop cards, reward / shop / boss relics, reward / shop
        // potions) are pick-rate items; deck edits (remove / upgrade / transform), event, campfire, Neow and other
        // choices are never forced nor tracked.
        bool exploreGapSearch = false;
        bool exploreDeckOnly = false;
        // exploreC / exploreAmber (2026-11-21, default off = the first rule): a pick-rate item is what the choice is
        // (exploreItemHash clean), without the shop slot, price and affordability that made nearly every shop offer
        // an item of its own. Amber Eye sets its target per choice ("card picks, event choices, Neow bonuses, and
        // relics"); with the first rule and a target over all runs such fragments had c = infinity (forced at every
        // offer: 9.3 forced picks per run, 2026-11-19), with explorePerOffer they never pass the warm-up.
        bool exploreCleanKeys = false;
        // Per-run evaluation cache (2026-11-17, default off): a leaf whose encoded net input (live tokens and legal
        // actions) equals one this run already had evaluated with the current weights (setWeightsVersion) takes
        // that result instead of a new net evaluation. Exact: the net sees only its input, so the cached result is
        // what a new evaluation with the same weights returns. Results of other weights versions are never used.
        // At most evalCacheCap entries per run (the cache is emptied when full).
        bool evalCache = false;
        int evalCacheCap = 1024;
        // Compact sample storage (2026-11-18, default off; Amber Eye: "we can still store the data efficiently by
        // keeping a common dictionary of tokens which are referenced by index in replay buffer states. Most tokens,
        // especially cards and relics, are shared between many different states"): a kept sample does not copy its
        // tokens but refers by index (Sample::tokIdx) to its run's dictionary of distinct tokens (TokenDict), so
        // samples that wait for their labels take a fraction of the memory and maxPendingSamples <= 0 (every full
        // move trained on) fits. Lossless: Sample::expandToken gives back exactly the tokens of the copied layout.
        bool compactSamples = false;
        // Heart-key backstops (2026-11-18, default off; Philipp-approved deviation from Amber Eye for the curriculum
        // phase): the ADR-0063 rules of search::heartKeyAction / heartKeyActionAllowed (RunGoal.h) restrict the
        // out-of-combat action lists, in the real runs and in the search tree. Sapphire: the Act-3 chest (row >= 8)
        // is opened and its key taken; Ruby: the last campfire before the Act-3 boss allows only Recall; Emerald: on
        // the Act-3 map only edges that still reach the burning elite (its key reward is taken). A forced move is the
        // only legal action: played without a search, so it gives no sample (no policy target); the run's value
        // labels are unchanged. Initial state of setForceKeys; a run keeps the state it started with. Needs the
        // ADR-0063 default rules (STS_KEY_* unset, or policy / policy / mask).
        bool forceKeys = false;
        // Forced reward choices (2026-11-19, default off; Philipp-approved deviation from Amber Eye, who leaves them to
        // the net): a treasure chest is opened unless we hold Cursed Key, and every relic on a REWARDS screen (elites,
        // chests, event fights; boss relics stay learned) is taken unless it is on the reviewed list
        // (forcedRewardActions). Order: Ceramic Fish, Molten / Toxic / Frozen Egg and Potion Belt before the card
        // reward (they act on it / on the potions), Whetstone and War Paint after it (they can upgrade the new card;
        // leaving the screen takes them first), every other relic at once (the order does not change its outcome).
        // Reward gold stays with simHelp (taken first; no reward-pool relic acts on gold). Applied in the real runs
        // and in the search tree; a forced move is the only legal action (played without a search, no sample).
        bool forceRewards = false;
        // RNG Fix mod for the real runs (2026-11-21, default off; Amber Eye: "Both the training and evaluation
        // settings use the RNGFix mod"): every run starts as GameContext(..., rngFix = true), so the game's random
        // streams have one seed each instead of all sharing the run seed (GameContext::rngFix). The search already
        // draws its futures from independent streams (sampleNoncombatFuture); it keeps the flag through copies, so
        // the per-floor streams of a sampled future are decoupled too.
        bool rngFix = false;
        // Identical cards on an out-of-combat card selection screen (2026-11-20, default off; Amber Eye canonicalizes
        // actions, "if multiple Defends are in hand, the simulator only exposes playing the first one"): of several
        // selectable cards with equal Card (id, upgrade, misc) and bottle state only the first stays legal
        // (canonicalOocSelectActions). Smith, purge, transform, duplicate, bottle and event selections; the same
        // multiset of cards results (only the deck position of an upgraded copy can differ).
        bool oocCanon = false;
        // Reward potions (2026-11-20, default off; Philipp-approved deviation from Amber Eye): on a REWARDS screen
        // whose potions all fit into the free slots, the first potion is taken (forcedRewardPotionActions), after the
        // forceRewards relic rules. Leaving a potion is never better: it can be thrown away later, out of combat too.
        bool forcePotions = false;
        // Card stacks (2026-11-17, default off; changes the net input, needs its own run): identical cards become one
        // CARD token with a copy count (search::amberMergeCards), ~25-35 % fewer tokens late in a run.
        bool mergeCards = false;
        // Amber Eye search fidelity (2026-11-17, all default off; https://8e9f.github.io/amber_eye/):
        // chanceOnReveal: an out-of-combat edge is a chance edge only when its step reveals hidden information
        //   (search::oocStepRevealsHidden: an RNG stream drew, a pre-shuffled pool or encounter queue was read, a fight
        //   started, a new act); other edges are deterministic with one child. Off: every out-of-combat edge is a
        //   chance edge. A won fight's exit (rewards) is tested the same way and makes its combat edge a chance edge.
        // crossCombat: one search over combat and out-of-combat states. A fight's first state and the state after a
        //   won fight are expanded like any node (combat nodes keep the game state of their fight's start, `outer`).
        //   Off: both are leaves valued by the net.
        // simHelp: the simulator help Amber lists: "in positions with one legal action, it is automatically taken;
        //   gold from rewards is automatically taken; [...] buying Prismatic Shard is banned", in the real run and
        //   inside the search (a step there runs on through forced positions and gold; it is one edge).
        bool chanceOnReveal = false;
        bool crossCombat = false;
        bool simHelp = false;
        // Savescum (2026-11-18, default off; Amber Eye: "At the very start of training, I allowed the search to
        // 'savescum' by giving it knowledge of future RNG outcomes. This improves play strength not just by having
        // the advance knowledge, but also by avoiding wasting search budget on sampling RNG. [...] turned off early").
        // The search steps copies of the real run with the real RNG and the real hidden state: nothing is resampled,
        // no edge is a chance edge (no double progressive widening), so the child of an action is exactly the state
        // the real run reaches with it. The net still sees the public view (Philipp's choice, 2026-11-18): a combat
        // node keeps the real fight and its knowledge tracker (observing every in-tree step, as the real run does)
        // and is encoded and enumerated through publicCombatRoot; out-of-combat states never encode hidden state.
        // Uses the Amber search path (as chanceOnReveal / crossCombat / simHelp do; with them it overrides
        // chanceOnReveal). Labels and training are unchanged. Initial state of setSavescum; turning it off reaches runs in
        // progress at their next searched move (samples already taken stay in the replay window).
        bool savescum = false;
        // Parallel search nodes (2026-11-21, default 0 = off: one evaluation in flight per run). Amber Eye, "Efficient
        // search": "we additionally allow multiple searches in the same game tree using virtual visits. In
        // self-play, up to 4 nodes per candidate move's subtree were allowed to be visited in parallel" (4 = Amber's
        // self-play value; the page says no more about the mechanism). With parallelNodes = P > 0 a halving phase's
        // simulations start together as a wave, at most P in flight per root candidate (so up to P x candidates
        // per run). A simulation in flight is a virtual loss on every edge of its path, as in the paper the page
        // links for "virtual visits" (Chaslot, Winands, van den Herik 2008: "assign one 'virtual loss' when a node
        // is visited by a thread [...] removed when the thread [...] starts propagating the result"; Philipp's
        // choice 2026-11-21 over a visit without a value): until its answer is backed up it counts as a visit of
        // value 0, the lowest utility, in everything that steers the next simulations below the root (the
        // edge's mean Q and so the completed Q, sigma's visit count, the selection pi' - N / (1 + sum N), the
        // widening limit and the outcome picked at a chance edge), so they spread over other edges and outcomes.
        // Every phase ends with all its answers in, so what is read at the root (halving, pick, improved
        // policy, value targets) holds finished simulations only. Our choices where page and paper are silent: a
        // simulation that reaches a node whose
        // evaluation is still in flight waits for that answer (it is tried again in the next wave); a wave's
        // answers are handled together, in the order the simulations started, so the search does not depend on
        // answer timing. The same simulations per move; the tree differs from the one-at-a-time search because
        // later simulations of a wave do not see the earlier ones' values.
        int parallelNodes = 0;
        // Search-backed EMA outcome targets (2026-11-17, default 0 = off), Amber Eye's value labels: "a combination
        // of the search result and an exponential weighted average of future moves' search outcomes". With
        // searchEmaLambda = lam in (0, 1): every node carries the net's outcome distribution (57 classes; submit needs
        // `dist`), a terminal leaf the one-hot of its outcome. The search result of a searched move is the root's
        // backed-up distribution: the mean over the root evaluation and every simulation's leaf distribution (the
        // same mean as the scalar Sample::searchValue: a mean over the tree's leaves, not the value of the move
        // played). When the run ends, along the chain's moves m = 0 .. M-1: target_M = one_hot(final outcome),
        // target_m = (1 - lam) D_m + lam target_{m+1}; a kept sample gets its move's target (Sample::outcomeTarget).
        // The chain's moves: searchEmaFullOnly true = the run's full-search moves only (Amber Eye trains on and
        // stores targets / value distributions for full moves only), false = all searched moves (full and fast).
        // A kept move outside the chain (a fast move with searchEmaFullOnly) gets the target of the next chain move
        // (one_hot(final outcome) if none). Either way kept or not does not matter. The selection is unchanged.
        // Chain distributions are held as float16 until the run ends (~114 B per chain move).
        double searchEmaLambda = 0;
        bool searchEmaFullOnly = true;
        // Search-backed EMA targets for the HP heads too (2026-11-21, default off; needs searchEmaLambda > 0 and
        // Amber's search rules: chanceOnReveal, crossCombat or simHelp). Amber Eye's page does not name the HP heads'
        // targets; it stores "labels for the outcome and HP distributions" as 8-bit value distributions, and its
        // value labels are the search / EMA combination (Philipp 2026-11-21: both HP heads). Every node carries, next
        // to its outcome distribution, what its value says about the search root's HP questions:
        //   - the distribution of the HP at the end of the ROOT's floor [256]: the net's HP softmax (submit needs
        //     `hpDist`) while the node is on the root's floor; the one-hot of the HP with which the path left that
        //     floor once the node is past it; a run-ending leaf: the one-hot of its real HP (0 on death);
        //   - utility AMBER / AMBER2 only: E[HP_f] / 255 for every floor f from the root's on [56]: the net's
        //     per-floor prediction from the node's floor on, the path's real HP for the floors it passed, a
        //     run-ending leaf's real values (death: 0 from its floor on; Heart kill: its HP from its floor on).
        // The search result of a searched move is the mean over the root evaluation and every simulation's leaf, as
        // for the outcome distribution. The chains use the same moves and lambda as the outcome's:
        //   - floor HP distribution: the chain ends with the floor (the head asks about this floor only):
        //     target = one_hot(real HP at the end of the floor) after the floor's last chain move
        //     (Sample::hpTargetQ, 8-bit fixed point over its nonzero interval, Amber's stored format);
        //   - per-floor HP: along the whole run, floor by floor: a floor's target is its real HP once the run has
        //     left it (Sample::hpFloorTarget, HP / 255, -1 before the sample's floor).
        // Sample::hpEnd / hpFloor keep the real labels. The selection is unchanged.
        bool searchEmaHp = false;
        // Heart search probe (2026-11-18, diagnostic, default empty = off). When a run reaches the Heart fight, its
        // game state at the fight's start is stored and the fight is played heartArms.size() x heartReps times from
        // that same state (same game RNG at the start; job j plays arm j % arms, rep j / arms), each with the arm's
        // search budget instead of fullSims / fastSims / fullProb / candidates. Every play gives one HeartResult
        // (heartResults); the run then ends with the last play's outcome. Moves before the Heart use the normal
        // budget. Meant for a frozen net (no training) with keepFull = keepFast = 0.
        std::vector<HeartArm> heartArms;
        int heartReps = 1;
        // Per-run Heart log (2026-11-19, diagnostic, default 0 = off; HeartRunLog, takeHeartRunLogs): > 0 records every
        // Heart kill and each other run that fought the Heart with this probability. Logging only: play is unchanged.
        double heartLogRate = 0;
        CombatEncodeFn encodeCombat = nullptr;   // default: search::amberEncodeCombat
        GameEncodeFn encodeGame = nullptr;       // default: search::amberEncodeGame (stubEncodeGame = placeholder)
    };

    // RunConfig::compactSamples: the distinct tokens of one run (flat layout, as Sample's copied tokens), in order
    // of first use. Written only by the run's worker while the run plays; read once the run's samples are done.
    struct TokenDict {
        static constexpr std::size_t kMax = 65535;   // tokIdx is 16 bit: a run past this starts a new dictionary
        std::vector<std::int8_t> tokType;
        std::vector<std::int16_t> ids;       // [n][4]
        std::vector<std::uint16_t> f;        // [n][64] float16 bits
        std::size_t size() const { return tokType.size(); }
    };

    // One training sample: the searched position's live tokens and legal actions (flat layout of one row, as
    // packFlat writes it), the improved policy over its actions (full moves), and its labels.
    struct Sample {
        // Tokens, copied (tokType / ids / f) or, RunConfig::compactSamples, as indices into the run's dictionary
        // (dict / tokIdx; tokType / ids / f then empty). numTokens / expandToken read either form.
        std::vector<std::int8_t> tokType;
        std::vector<std::int16_t> ids;       // [n][4]
        std::vector<std::uint16_t> f;        // [n][64] float16 bits
        std::shared_ptr<const TokenDict> dict;
        std::vector<std::uint16_t> tokIdx;   // [n] position in *dict
        std::size_t numTokens() const { return dict ? tokIdx.size() : tokType.size(); }
        // Token t in the copied layout: type, ids [4], f [64].
        void expandToken(std::size_t t, std::int8_t &type, const std::int16_t *&id, const std::uint16_t *&fv) const {
            const std::size_t k = dict ? tokIdx[t] : t;
            const auto &tt = dict ? dict->tokType : tokType;
            const auto &ii = dict ? dict->ids : ids;
            const auto &ff = dict ? dict->f : f;
            type = tt[k];
            id = ii.data() + k * search::kAmberCat;
            fv = ff.data() + k * search::kAmberFloat;
        }
        std::vector<std::int16_t> aType, aSrc, aTgt;
        std::vector<std::uint16_t> aF;       // [a][8]
        std::vector<float> policy;           // [a] improved policy (empty for a fast move)
        float searchValue = 0;               // root value after the search (scaled utility)
        std::int16_t outcome = -1;           // label: 0 win, f death floor
        std::int16_t hpEnd = -1;             // label: HP at the end of this floor (0 on death)
        std::vector<std::int16_t> hpFloor;   // utility AMBER only: [56] HP at the end of floor f (-1 before this floor)
        std::int16_t maxHp = 0, floor = 0;
        std::uint8_t combat = 0;
        std::uint64_t run = 0;               // run seed
        // searchEmaLambda > 0 only: the root's search-backed outcome distribution [57], the EMA target [57] and the
        // final outcome's weight lam^(M - m) in it; emaMove = the sample's index among the run's searched moves.
        std::vector<float> searchDist, outcomeTarget;
        float emaRealWeight = 0;
        std::int32_t emaMove = -1;
        // searchEmaHp only: the EMA target of the floor HP distribution as round(255 p) over classes
        // hpTargetLo .. hpTargetLo + size - 1 (0 elsewhere), and the per-floor targets [56] (utility AMBER; HP / 255,
        // -1 before this floor).
        std::int16_t hpTargetLo = 0;
        std::vector<std::uint8_t> hpTargetQ;
        std::vector<float> hpFloorTarget;
    };

    // Run progress counters of finished runs (2026-11-17; why A0 runs rarely reach Act 4): keys held at the run's
    // end, campfire choices, elite fights, Act 4 and the Heart. Counted per run while it plays, added to the run's
    // ascension when it ends.
    struct RunProgress {
        std::int64_t ruby = 0, emerald = 0, sapphire = 0, allKeys = 0;   // runs ending with the key / all three
        std::int64_t campfires = 0;        // campfire choices (rest, smith, recall, lift, toke, dig)
        std::int64_t recallOffered = 0;    // ... of which with Recall legal (keys on, no Ruby key yet)
        std::int64_t rest = 0, smith = 0, recall = 0, otherCampfire = 0;
        std::int64_t elites = 0;           // elite fights started (Room::ELITE; not event elites)
        std::int64_t burningElites = 0;    // ... of which the burning (Emerald key) elite
        std::int64_t act4 = 0;             // runs that entered Act 4
        std::int64_t heart = 0;            // runs that started the Heart fight
        std::int64_t keylessVictories = 0; // runs ended by the Act 3 boss without the three keys (floor 51)
        // Heart fights (2026-11-18, logging only): the Heart's HP left when the fight ended (0 = killed) as a histogram
        // of 50-HP bins (bin 15 = 750, A0 max HP), its sum, the player's HP entering the fight and the fight's turn
        // count at its end; summed over runs that fought the Heart (divide by `heart`).
        static constexpr int kHeartHpBins = 16;
        std::array<std::int64_t, kHeartHpBins> heartHpHist{};
        std::int64_t heartHpSum = 0, heartEntryHpSum = 0, heartTurnsSum = 0;
        // Relics held and cards in the deck at the run's end (2026-11-18, logging only), summed over finished runs
        // (divide by runs).
        std::int64_t relicsSum = 0, deckSizeSum = 0;
        // Economy and relic sources (2026-11-19, logging only; why runs end with few relics): treasure rooms reached
        // and left without opening the chest; reward-screen relics taken and left behind when leaving the screen, by
        // room (elite fight, treasure chest, other: monster, event, boss); shop visits (each ends with leaving) and
        // purchases; boss relic screens skipped; gold gained and lost out of combat (rewards, events, shops).
        std::int64_t chests = 0, chestsSkipped = 0;
        std::int64_t chestsSkippedCursedKey = 0;   // of chestsSkipped: with Cursed Key (forceRewards leaves them open)
        std::int64_t relicsTakenElite = 0, relicsTakenChest = 0, relicsTakenOther = 0;
        std::int64_t relicsLeftElite = 0, relicsLeftChest = 0, relicsLeftOther = 0;
        std::int64_t shops = 0, shopCards = 0, shopRelics = 0, shopPotions = 0, shopRemoves = 0;
        std::int64_t bossRelicSkips = 0, goldGained = 0, goldLost = 0;
        std::int64_t sapphireRelicForfeits = 0;   // chest relics given up for the Sapphire key (neither taken nor left)
        std::int64_t oocPotionDiscards = 0, oocPotionDrinks = 0;   // out-of-combat potion actions taken
        RunProgress &operator+=(const RunProgress &o) {
            ruby += o.ruby; emerald += o.emerald; sapphire += o.sapphire; allKeys += o.allKeys;
            campfires += o.campfires; recallOffered += o.recallOffered;
            rest += o.rest; smith += o.smith; recall += o.recall; otherCampfire += o.otherCampfire;
            elites += o.elites; burningElites += o.burningElites; act4 += o.act4; heart += o.heart;
            keylessVictories += o.keylessVictories;
            for (int k = 0; k < kHeartHpBins; ++k) heartHpHist[k] += o.heartHpHist[k];
            heartHpSum += o.heartHpSum; heartEntryHpSum += o.heartEntryHpSum; heartTurnsSum += o.heartTurnsSum;
            relicsSum += o.relicsSum; deckSizeSum += o.deckSizeSum;
            chests += o.chests; chestsSkipped += o.chestsSkipped; chestsSkippedCursedKey += o.chestsSkippedCursedKey;
            relicsTakenElite += o.relicsTakenElite; relicsTakenChest += o.relicsTakenChest;
            relicsTakenOther += o.relicsTakenOther; relicsLeftElite += o.relicsLeftElite;
            relicsLeftChest += o.relicsLeftChest; relicsLeftOther += o.relicsLeftOther;
            shops += o.shops; shopCards += o.shopCards; shopRelics += o.shopRelics; shopPotions += o.shopPotions;
            shopRemoves += o.shopRemoves; bossRelicSkips += o.bossRelicSkips;
            goldGained += o.goldGained; goldLost += o.goldLost; sapphireRelicForfeits += o.sapphireRelicForfeits;
            oocPotionDiscards += o.oocPotionDiscards; oocPotionDrinks += o.oocPotionDrinks;
            return *this;
        }
    };

    struct RunStats {
        std::int64_t evals = 0, moves = 0, searchedMoves = 0, runsStarted = 0, runsDone = 0, wins = 0;
        std::int64_t floorsSum = 0, stalls = 0, terminalLeaves = 0, unsupported = 0;
        std::int64_t invalidActions = 0;      // chosen actions not valid in the real fight after translation (bug; run lost)
        std::int64_t knowledgeFailures = 0;   // fights whose public view could not be built (run abandoned as a loss)
        std::int64_t encodeCut = 0, encodeCutOoc = 0;   // tokens / actions past capacity (combat, out of combat; MAP keeps the nearest 32 nodes)
        std::int64_t samplesDone = 0, samplesPending = 0;
        std::int64_t batches = 0, batchRows = 0;
        std::array<std::int64_t, kOutcomeClasses> outcomes{};   // finished runs per outcome class
        // Per ascension (curriculum): finished runs, Heart kills, final floors.
        std::array<std::int64_t, kAscensions> runsDoneAsc{}, winsAsc{}, floorsSumAsc{};
        std::array<RunProgress, kAscensions> progressAsc{};   // finished runs' progress counters per ascension
        std::int64_t oocRoots = 0, exploreRoots = 0, forcedPicks = 0;   // searched OOC decisions; with an under-target item; forced
        // exploreAmber diagnostics: forcing attempts (under-target item tried after a search) and of those with c = 0 /
        // c = infinity; items logged with m = 0 at a run's end, and of those not played in that run (must stay 0).
        std::int64_t exploreAttempts = 0, exploreCZero = 0, exploreCInf = 0, exploreNatural = 0, exploreNaturalUnplayed = 0;
        std::int64_t cacheHits = 0;           // leaves answered by the evaluation cache (not counted in evals)
        // parallelNodes: waves started and the evaluations in them (waveFlights / waves = evaluations in flight per
        // run and wave), and simulations that had to wait for a node whose evaluation was in flight.
        std::int64_t waves = 0, waveFlights = 0, simCollisions = 0;
        // Search diagnostics of searched out-of-combat roots (always on): per full / fast move, roots, roots whose
        // search pick is not the visited edge of highest mean Q (before a forced pick), and the sum of that root's
        // raw visited-Q spread (max - min mean Q, roots with >= 2 visited edges) and its count.
        std::array<std::int64_t, 2> oocSearched{}, oocNotBestQ{}, oocSpreadN{};
        std::array<double, 2> oocSpreadSum{};
        // Amber search rules (RunConfig::chanceOnReveal / crossCombat): first expansions of out-of-combat edges that
        // were deterministic / chance edges, and fights started / won inside the search (crossCombat).
        std::array<std::int64_t, 2> oocEdgeKinds{};
        std::int64_t treeFightStarts = 0, treeFightExits = 0;
        std::int64_t autoGold = 0;   // simHelp: reward gold taken automatically in the real runs
        // forceKeys: real moves forced by a key backstop [Sapphire (chest opened / key taken), Ruby (Recall), Emerald
        // (route edge / key taken)], and real Act-3 map decisions whose route the Emerald rule narrowed (still a choice).
        std::array<std::int64_t, 3> forcedKeys{};
        // exploreAmber (always on): forcing attempts and forced picks per item class (kExploreClasses order:
        // card, deck_edit, relic, potion, event, rest, other_option, other).
        std::array<std::int64_t, 8> exploreAttemptsByClass{}, forcedByClass{};
        std::int64_t keyRouteMasked = 0;
        // forceRewards: real moves forced [chest opened, relic taken], real card decisions with a card-first relic
        // held back, and card-first relics taken on leaving the screen.
        std::array<std::int64_t, 2> forcedRewards{};
        std::int64_t rewardRelicDeferred = 0, rewardRelicOnLeave = 0;
        // oocCanon: real card selection screens with a duplicate removed, and the actions removed there;
        // forcePotions: real reward potions taken by the rule.
        std::int64_t oocCanonScreens = 0, oocCanonRemoved = 0, forcedPotions = 0;
        // savescum: runs started with it; searched moves whose played edge's child was a decision state, and of those
        // the ones whose real next decision state differed from it (fingerprint incl. RNG counters; must stay 0).
        std::int64_t savescumRuns = 0, savescumChecks = 0, savescumMismatches = 0;
        std::int64_t heartHpMin = -1;   // lowest Heart HP left at the end of any Heart fight so far (-1 = none yet)
        // Memory gauges (current values, not cumulative; refreshed about once a second by each worker): node-pool
        // slots of all runs and those holding a game state / a fight (memPoolBc) / a savescum real fight / a
        // fight-start game state (crossCombat), and the capacities of the runs' pending-sample and move-distribution buffers and their
        // eval-cache entries; memEdgeCap: edge-list capacity (Edge elements) of all slots. Finished samples not yet
        // taken: memDone (driver level).
        std::int64_t memPoolNodes = 0, memPoolGc = 0, memPoolReal = 0, memPoolOuter = 0, memEdgeCap = 0, memPoolBc = 0;
        std::int64_t memPendingCap = 0, memMoveDistCap = 0, memCacheEntries = 0, memDone = 0;
        std::int64_t memFlights = 0;   // allocated flight slots of all runs (one encoded input each, ~60 KB)
        double stepCpu = 0, encodeCpu = 0, searchCpu = 0, packSeconds = 0;
    };

    class RunDriver {
    public:
        explicit RunDriver(RunConfig cfg);
        ~RunDriver();
        void start();
        void stop();
        // Waits up to timeoutUs for minRows queued requests without taking any; true when they are there (the
        // caller can do other work between short waits, e.g. hand back a finished batch, and then take the batch).
        bool waitRequests(int minRows, int timeoutUs);
        // As Driver::nextBatchFlat (az_driver.h): takes up to maxRows requests, packs them into buf.
        std::vector<std::uint32_t> nextBatchFlat(int maxRows, int minRows, int timeoutMs,
                                                 const std::vector<int> &rowBuckets,
                                                 const std::vector<int> &tokBuckets,
                                                 const std::vector<int> &actBuckets, const FlatBuffers &buf,
                                                 FlatShape &shape, int packThreads = 1);
        // Results: logits[row][action] (`actions` per row), F[row] in [0, 1] and expected HP at the end of the
        // floor ehp[row] (absolute) for each ticket; utility AMBER also needs hpf[row][56] = E[HP_f] / 255;
        // searchEmaLambda > 0 needs dist[row][57], the outcome head's softmax (class 0 = win, f = death on floor f);
        // searchEmaHp needs hpDist[row][256], the floor HP head's softmax.
        // version: the weights version (setWeightsVersion) the batch was evaluated with (evaluation cache).
        void submit(const std::uint32_t *tickets, int rows, int actions, const float *logits, const float *F,
                    const float *ehp, const float *hpf = nullptr, std::uint32_t version = 0,
                    const float *dist = nullptr, const float *hpDist = nullptr);
        // The weights version of evaluations from now on (evaluation cache): set it when the net's weights change,
        // before evaluating the next batch with them. Cached results of other versions are not used.
        void setWeightsVersion(std::uint32_t v) { weightsVersion_.store(v, std::memory_order_release); }
        // Moves up to maxSamples finished samples (labels filled) into out, then the rest of the last run taken (a
        // run is never split across calls).
        void takeSamples(int maxSamples, std::vector<Sample> &out);
        RunStats stats() const;
        const RunConfig &config() const { return cfg_; }
        std::uint64_t nextSeed();   // the next run seed (thread-safe); runsStarted counts these
        // Ascension of runs started from now on (curriculum; runs in progress keep theirs). 0..20.
        void setAscension(int a) {
            if (a < 0 || a >= kAscensions) throw std::invalid_argument("run driver: ascension 0..20");
            ascension_.store(a);
        }
        int ascension() const { return ascension_.load(); }
        // Heart-key backstops (RunConfig::forceKeys) for runs started from now on (curriculum: off from the first
        // step-up; runs in progress keep theirs).
        void setForceKeys(bool on);   // throws unless the ADR-0063 default key rules hold (on only)
        bool forceKeys() const { return forceKeys_.load(); }
        // Savescum (RunConfig::savescum): on for runs started from now on; off also for runs in progress, from their
        // next searched move.
        void setSavescum(bool on) { savescum_.store(on); }
        bool savescum() const { return savescum_.load(); }
        // Heart search probe (RunConfig::heartArms): the finished Heart plays so far.
        std::vector<HeartResult> heartResults() const {
            std::lock_guard<std::mutex> l(heartM_);
            return heartResults_;
        }

        // Per-run Heart log (RunConfig::heartLogRate): the records since the last call (moved out).
        std::vector<HeartRunLog> takeHeartRunLogs() {
            std::lock_guard<std::mutex> l(heartLogM_);
            std::vector<HeartRunLog> out;
            out.swap(heartLogs_);
            return out;
        }

        struct Node;
        struct Run;
        struct Worker;

    private:
        void workerLoop(int w);
        std::vector<std::uint32_t> takeRequests(int maxRows, int minRows, int timeoutMs);
        RunConfig cfg_;
        std::vector<std::unique_ptr<Worker>> workers_;
        std::vector<std::thread> threads_;
        std::atomic<bool> stop_{false};
        std::atomic<std::int64_t> seedsUsed_{0};
        std::atomic<std::int64_t> pending_{0};   // samples of unfinished runs, all workers
        static constexpr int kPickBuckets = 1 << 16;
        std::unique_ptr<std::atomic<std::uint32_t>[]> picks_;
        std::unique_ptr<std::atomic<std::uint32_t>[]> offers_;   // explorePerOffer: finished runs that offered the item
        struct ExploreItem { AmberGapHist hist; double c = 0; std::int64_t stamp = -1; };
        std::mutex exploreM_;                              // exploreItems_ (exploreAmber)
        std::unordered_map<int, ExploreItem> exploreItems_;   // item bucket -> gap log and its c (exploreAmber)
        double exploreItemC(int key, std::int64_t games);
        std::atomic<int> ascension_{20};
        std::atomic<bool> forceKeys_{false};
        std::atomic<bool> savescum_{false};
        std::atomic<std::uint32_t> weightsVersion_{0};
        std::atomic<std::int64_t> runsDone_{0};   // finished runs, all workers (pick-rate denominator)   // real picks per item hash (pick-rate exploration)
        mutable std::mutex qm_;
        std::condition_variable qcv_;
        std::deque<std::uint32_t> queue_;   // ticket = worker << 26 | flight slot << 16 | run
        mutable std::mutex sampleM_;
        std::deque<Sample> done_;
        std::atomic<std::int64_t> batches_{0}, batchRows_{0}, packNs_{0};
        mutable std::mutex heartM_;
        std::vector<HeartResult> heartResults_;
        std::mutex heartLogM_;
        std::vector<HeartRunLog> heartLogs_;
    };

}

#endif
