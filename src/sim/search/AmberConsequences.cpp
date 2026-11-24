// Consequence features of the Amber combat encoding (2026-11-24, optional; RunConfig::consequences); see
// AmberEncoder.h for the contract. Amber Eye (https://8e9f.github.io/amber_eye/) names action features "e.g. if an
// attack is lethal"; the rest follows AlphaDefect (arXiv 2611.31076, section 2.2 and appendix B.1): the damage and
// block of each card after all modifiers, the HP the player would lose by ending the turn now, and the HP that
// would remain after an action followed by ending the turn, plus the energy and cards drawn that follow a candidate.
//
// Every value is read off the engine on copies of the encoded state (the search's public view, ADR-0002): a play is
// the legal action executed (search::Action::execute, which runs the queue until the next decision), the end-turn
// preview is END_TURN executed after it. Effects that depend on randomness (random targets, draws) follow the
// copy's RNG, i.e. one sample of the public view, never the real fight's RNG. Monster slots k are engine slots
// 0..4 (MONSTER token float 8 = k/4). Float layout (index: value; "/k" = divided by k; flags 0/1; all slots below
// are 0 in amberEncodeCombat and amberEncodeGame, so a net whose weights for them are 0 is unchanged):
//
// PLAYER (combat; every value 0 while intents are hidden, Runic Dome)
//   40-44 intent damage per hit of the monster in slot k after modifiers (Monster::publicIncomingDamage / hits)/10
//   45-49 its hit count/5 (0 when the monster does not attack)  50 total intent damage/10
//   51 end-turn preview computed (PLAYER_NORMAL, fight undecided, intents shown)  52 HP lost by ending the turn
//   now/10 (signed: negative = healed)  53 the player dies by ending the turn now  54 1 (consequences computed)
// CARD (hand cards with at least one legal play among the encoded actions) and POTION (filled slots with a legal
//   drink); a targeted card / potion fills slot k from the play on target k, an untargeted one from its one play
//   42 1 (previewed)  43-47 damage to slot k (its HP + block lost, >= 0)/10  48-52 the monster in slot k dies
//   (dying or half dead, not escaping)  53 block gained/10  54 HP lost by the player/10 (signed)
//   55 energy change/3 (signed)  56 cards drawn/5  57 the play wins the fight
//   end-turn preview after the play (when PLAYER 51 applies and the play leaves PLAYER_NORMAL, fight undecided):
//   58 fewest HP lost over the card's targets/10  59 most HP lost/10 (signed; a win = 0 lost)
//   60 the play opens a card selection (no end-turn preview then)
// Actions: PLAY_CARD / USE_POTION f[3] = the play kills a monster (Amber's lethal feature; f[3] is 0 elsewhere).
#include "sim/search/AmberEncoder.h"

#include <algorithm>

#include "combat/BattleContext.h"
#include "sim/search/CombatKnowledge.h"

namespace sts::search {

    namespace {

        using T = AmberTokenType;

        inline void put(AmberToken &t, int i, float v) { t.f[i] = amberHalf(v); }
        inline void flag(AmberToken &t, int i, bool v) { t.f[i] = v ? 0x3c00 : 0; }

        // The copies' actions never reach the live knowledge observer, and the debug pointer is restored
        // (as proveSilverUselessBlock).
        struct ObserverScope {
            CombatKnowledgeObserver *observer = g_combatKnowledgeObserver;
            BattleContext *debug = g_debug_bc;
            ObserverScope() { g_combatKnowledgeObserver = nullptr; }
            ~ObserverScope() { g_combatKnowledgeObserver = observer; g_debug_bc = debug; }
            ObserverScope(const ObserverScope &) = delete;
            ObserverScope &operator=(const ObserverScope &) = delete;
        };

        bool killed(const Monster &before, const Monster &after) {
            if (before.id == MonsterId::INVALID || before.isDeadOrEscaped()) return false;
            return (after.isDying() || after.isHalfDead()) && !after.isEscaping();
        }

        struct Play {
            int dmg[5] = {}, kill[5] = {};
            int block = 0, hpLost = 0, energy = 0, drawn = 0;
            bool win = false, select = false, anyKill = false, ended = false;
            int endHpLost = 0;
        };

        void simulate(const BattleContext &s, const search::Action &a, bool endPreview, Play &p) {
            BattleContext c = s;
            a.execute(c);
            for (int k = 0; k < 5; ++k) {
                const Monster &m0 = s.monsters.arr[k], &m1 = c.monsters.arr[k];
                if (m0.id == MonsterId::INVALID && m0.maxHp == 0) continue;
                p.dmg[k] = std::max(0, (m0.curHp + m0.block) - (std::max(0, m1.curHp) + m1.block));
                p.kill[k] = killed(m0, m1);
                p.anyKill |= p.kill[k] != 0;
            }
            p.block = c.player.block - s.player.block;
            p.hpLost = s.player.curHp - c.player.curHp;
            p.energy = c.player.energy - s.player.energy;
            p.drawn = c.cardsDrawn - s.cardsDrawn;
            p.win = c.outcome == Outcome::PLAYER_VICTORY;
            p.select = c.inputState == InputState::CARD_SELECT;
            if (!endPreview) return;
            if (p.win) {
                p.ended = true;
                return;
            }
            if (c.outcome != Outcome::UNDECIDED || c.inputState != InputState::PLAYER_NORMAL) return;
            search::Action(ActionType::END_TURN).execute(c);
            p.ended = true;
            p.endHpLost = s.player.curHp - std::max(0, c.player.curHp);
        }

        // Per-token aggregate of the plays that name it (a card in hand or a potion slot).
        struct Agg {
            bool any = false, win = false, select = false, ended = false;
            int dmg[5] = {}, kill[5] = {};
            int block = 0, hpLost = 0, energy = 0, drawn = 0, endMin = 0, endMax = 0;
        };

        void add(Agg &g, const Play &p, int target) {
            if (target >= 0 && target < 5) {
                g.dmg[target] = p.dmg[target];
                g.kill[target] = p.kill[target];
            } else {
                for (int k = 0; k < 5; ++k) {
                    g.dmg[k] = p.dmg[k];
                    g.kill[k] = p.kill[k];
                }
            }
            if (!g.any) {   // the first play's own numbers (equal over targets for nearly every card)
                g.block = p.block;
                g.hpLost = p.hpLost;
                g.energy = p.energy;
                g.drawn = p.drawn;
            }
            g.win |= p.win;
            g.select |= p.select;
            if (p.ended) {
                const int v = p.win ? 0 : p.endHpLost;
                g.endMin = g.ended ? std::min(g.endMin, v) : v;
                g.endMax = g.ended ? std::max(g.endMax, v) : v;
                g.ended = true;
            }
            g.any = true;
        }

        void write(AmberToken &t, const Agg &g) {
            flag(t, 42, true);
            for (int k = 0; k < 5; ++k) {
                put(t, 43 + k, g.dmg[k] / 10.0f);
                flag(t, 48 + k, g.kill[k] != 0);
            }
            put(t, 53, g.block / 10.0f);
            put(t, 54, g.hpLost / 10.0f);
            put(t, 55, g.energy / 3.0f);
            put(t, 56, g.drawn / 5.0f);
            flag(t, 57, g.win);
            if (g.ended) {
                put(t, 58, g.endMin / 10.0f);
                put(t, 59, g.endMax / 10.0f);
            }
            flag(t, 60, g.select);
        }

    }  // namespace

    void amberAppendConsequences(const BattleContext &state, const std::vector<search::Action> &actions,
                                 AmberTokens &out) {
        if (out.n[static_cast<int>(T::PLAYER)] < 1) return;
        AmberToken &pl = out.at(T::PLAYER, 0);
        flag(pl, 54, true);
        const bool shown = !state.intentsHidden;
        if (shown) {
            int total = 0;
            for (int k = 0; k < 5; ++k) {
                const Monster &m = state.monsters.arr[k];
                if (m.id == MonsterId::INVALID || m.isDeadOrEscaped() || !m.isAttacking()) continue;
                const int hits = std::max(1, m.getMoveBaseDamage(state).attackCount);
                const int dmg = m.publicIncomingDamage(state);   // all hits
                put(pl, 40 + k, static_cast<float>(dmg) / static_cast<float>(hits) / 10.0f);
                put(pl, 45 + k, hits / 5.0f);
                total += dmg;
            }
            put(pl, 50, total / 10.0f);
        }
        const bool normal = state.inputState == InputState::PLAYER_NORMAL && state.outcome == Outcome::UNDECIDED;
        if (!normal) return;
        const bool endPreview = shown;
        ObserverScope scope;
        if (endPreview) {
            BattleContext c = state;
            search::Action(ActionType::END_TURN).execute(c);
            flag(pl, 51, true);
            put(pl, 52, (state.player.curHp - std::max(0, c.player.curHp)) / 10.0f);
            flag(pl, 53, c.outcome == Outcome::PLAYER_LOSS);
        }
        Agg cardAgg[kAmberCap[static_cast<int>(T::CARD)]];
        Agg potAgg[kAmberCap[static_cast<int>(T::POTION)]];
        const int n = std::min<int>(out.nAct, static_cast<int>(actions.size()));
        for (int i = 0; i < n; ++i) {
            const search::Action &a = actions[i];
            AmberAction &enc = out.act[i];
            const auto type = static_cast<AmberActionType>(enc.type);
            Agg *g = nullptr;
            int target = -1;
            if (type == AmberActionType::PLAY_CARD && enc.srcSeg == static_cast<std::uint8_t>(T::CARD)) {
                g = &cardAgg[enc.srcIdx];
                if (enc.tgtSeg == static_cast<std::uint8_t>(T::MONSTER)) target = a.getTargetIdx();
            } else if (type == AmberActionType::USE_POTION && enc.srcSeg == static_cast<std::uint8_t>(T::POTION)) {
                g = &potAgg[enc.srcIdx];
                if (enc.tgtSeg == static_cast<std::uint8_t>(T::MONSTER)) target = a.getTargetIdx();
            }
            if (!g) continue;
            Play p;
            simulate(state, a, endPreview, p);
            enc.f[3] = p.anyKill ? 0x3c00 : 0;
            add(*g, p, target);
        }
        for (int i = 0; i < out.n[static_cast<int>(T::CARD)]; ++i)
            if (cardAgg[i].any) write(out.at(T::CARD, i), cardAgg[i]);
        for (int i = 0; i < out.n[static_cast<int>(T::POTION)]; ++i)
            if (potAgg[i].any) write(out.at(T::POTION, i), potAgg[i]);
    }

}
