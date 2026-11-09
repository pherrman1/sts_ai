// Native combat net inference and input encoder (combat plan stage 3, 2026-11-08); see CombatTokNet.h.
#include "sim/search/CombatTokNet.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <fstream>
#include <map>
#include <stdexcept>

#include "sim/search/SilverWireJson.h"
#include "sim/search/SilverWireState.h"

namespace sts::search {

    namespace {

        constexpr int kCardV = 512, kMonV = 256, kMoveV = 256, kPotV = 64, kStatV = 128, kZoneV = 16;

        inline float slogf(float x) {
            // numpy / torch: sign(x) * log1p(|x|)
            if (x == 0.0f) return 0.0f;
            const float l = std::log1p(std::fabs(x));
            return x < 0.0f ? -l : l;
        }

        inline float gelu(float x) { return 0.5f * x * (1.0f + std::erf(x * 0.70710678118654752f)); }

        inline int clampi(int v, int lo, int hi) { return v < lo ? lo : v > hi ? hi : v; }

        inline std::int16_t clip16(double v) {
            if (!(v > -32768.0)) return v != v ? 0 : -32768;
            if (v > 32767.0) return 32767;
            return static_cast<std::int16_t>(static_cast<long long>(v));   // trunc toward zero, as Python int()
        }

        // y[t] = x[t] W^T + b for T rows; four rows share each weight row.
        void applyLinear(const CombatTokNet::Linear &l, const float *x, int rows, float *y) {
            const int in = l.in, out = l.out;
            const float *wt = l.wt.data();
            int t = 0;
            for (; t + 4 <= rows; t += 4) {
                float *__restrict y0 = y + static_cast<std::size_t>(t) * out;
                float *__restrict y1 = y0 + out;
                float *__restrict y2 = y1 + out;
                float *__restrict y3 = y2 + out;
                const float *x0 = x + static_cast<std::size_t>(t) * in, *x1 = x0 + in, *x2 = x1 + in, *x3 = x2 + in;
                for (int j = 0; j < out; ++j) y0[j] = y1[j] = y2[j] = y3[j] = l.b[j];
                for (int i = 0; i < in; ++i) {
                    const float a0 = x0[i], a1 = x1[i], a2 = x2[i], a3 = x3[i];
                    const float *__restrict w = wt + static_cast<std::size_t>(i) * out;
                    for (int j = 0; j < out; ++j) {
                        const float wj = w[j];
                        y0[j] += a0 * wj;
                        y1[j] += a1 * wj;
                        y2[j] += a2 * wj;
                        y3[j] += a3 * wj;
                    }
                }
            }
            for (; t < rows; ++t) {
                float *__restrict yt = y + static_cast<std::size_t>(t) * out;
                const float *xt = x + static_cast<std::size_t>(t) * in;
                for (int j = 0; j < out; ++j) yt[j] = l.b[j];
                for (int i = 0; i < in; ++i) {
                    const float a = xt[i];
                    if (a == 0.0f) continue;
                    const float *__restrict w = wt + static_cast<std::size_t>(i) * out;
                    for (int j = 0; j < out; ++j) yt[j] += a * w[j];
                }
            }
        }

        void layerNorm(const float *x, int d, const float *w, const float *b, float *y) {
            float mean = 0.0f;
            for (int i = 0; i < d; ++i) mean += x[i];
            mean /= static_cast<float>(d);
            float var = 0.0f;
            for (int i = 0; i < d; ++i) {
                const float c = x[i] - mean;
                var += c * c;
            }
            var /= static_cast<float>(d);
            const float inv = 1.0f / std::sqrt(var + 1e-5f);
            for (int i = 0; i < d; ++i) y[i] = (x[i] - mean) * inv * w[i] + b[i];
        }

        inline void addRow(float *dst, const std::vector<float> &table, int row, int d, float scale = 1.0f) {
            const float *src = table.data() + static_cast<std::size_t>(row) * d;
            for (int i = 0; i < d; ++i) dst[i] += scale * src[i];
        }

        // --- wire_encoder.encode ------------------------------------------------------------------------------

        const char *const kGlobalScalars[] = {
            "act", "ascension", "cardsDrawn", "encounter", "endTurnQueued", "energyWasted", "extraRollMoveOnTurn",
            "floorNum", "fullDrawOrderObserved", "inputState", "intentsHidden", "loopCount", "miscBits",
            "monsterCount", "monsterTurnIdx", "monstersAlive", "omamoriOwned", "omamoriValue", "outcome",
            "pendingActionQueueObserved", "pendingCardQueueObserved", "potionCapacity", "potionCount",
            "skipMonsterTurn", "skipMonsterTurnBits", "strikeCount", "turn", "turnHasEnded",
            "discardPileBloodCardCount", "drawPileBloodCardCount", "handBloodCardCount", "handNormalityCount",
            "handPainCount",
        };
        const char *const kPlayerScalars[] = {
            "artifact", "attacksPlayedThisTurn", "block", "cardDrawPerTurn", "cardsDiscardedThisTurn",
            "cardsPlayedThisTurn", "characterClass", "combustHpLoss", "curHp", "devaFormEnergyPerTurn", "dexterity",
            "echoFormCardsDoubled", "energy", "energyPerTurn", "focus", "gold", "haveUsedNecronomiconThisTurn",
            "justAppliedBits", "lastAttackUnblockedDamage", "lastTargetedMonster", "maxHp",
            "orangePelletsCardTypesPlayed", "orbSlots", "panacheCounter", "skillsPlayedThisTurn", "stance",
            "strength", "timesDamagedThisCombat",
        };
        const char *const kMonsterScalars[] = {
            "block", "curHp", "escapeNext", "halfDead", "isEscapingB", "latentDamageMask", "maxHp", "miscInfo",
            "pendingDirectMoveChoice", "pendingMoveRolls", "statusBits", "strength", "uniquePower0", "uniquePower1",
            "vulnerable", "weak",
        };
        const char *const kRollInputs[] = {
            "aliveCount", "asleep", "curHp", "halfDead", "knightAlive", "knightCurHp", "knightMaxHp", "maxHp",
            "miscInfo", "monsterTurnNumber", "monstersAlive", "playerConstricted",
        };
        const char *const kCardFields[] = {"id", "upgraded", "cost", "costForTurn", "freeToPlayOnce", "retain",
                                           "specialData"};

        double num(const nlohmann::json &v) {
            if (v.is_boolean()) return v.get<bool>() ? 1.0 : 0.0;
            if (v.is_null()) return 0.0;
            if (v.is_number_unsigned()) return static_cast<double>(v.get<std::uint64_t>());
            if (v.is_number_integer()) return static_cast<double>(v.get<std::int64_t>());
            if (v.is_number()) return v.get<double>();
            throw std::runtime_error("combat net encoder: non-numeric wire leaf");
        }

        const nlohmann::json &field(const nlohmann::json &obj, const char *key) {
            const auto it = obj.find(key);
            if (it == obj.end()) throw std::runtime_error(std::string("combat net encoder: wire lacks ") + key);
            return *it;
        }

        // wire_encoder._flat_numbers: every scalar leaf in document order (objects by key, as nlohmann::json and
        // the JSON rows the Python encoder read keep them); empty lists add nothing.
        void flat(const nlohmann::json &x, std::vector<double> &out) {
            if (x.is_object() || x.is_array()) {
                for (const auto &v : x) flat(v, out);
            } else {
                out.push_back(num(x));
            }
        }

        void setBits(std::uint64_t v, int offset, std::array<std::uint8_t, 128> &dst) {
            for (int i = 0; i < 64; ++i)
                if ((v >> i) & 1ULL) dst[offset + i] = 1;
        }

        std::uint64_t bits64(const nlohmann::json &v) {
            if (v.is_number_unsigned()) return v.get<std::uint64_t>();
            if (v.is_number_integer()) return static_cast<std::uint64_t>(v.get<std::int64_t>());
            return static_cast<std::uint64_t>(num(v));
        }

        void cardRow(int zone, int pos, const nlohmann::json &c, CombatTokInputs &out) {
            if (static_cast<int>(out.cards.size()) >= kCtnCardMax) return;   // tensorize C_MAX cut
            std::array<std::int16_t, 9> row{};
            row[0] = clip16(zone);
            row[1] = clip16(pos);
            for (int f = 0; f < 7; ++f) row[2 + f] = clip16(std::trunc(num(field(c, kCardFields[f]))));
            out.cards.push_back(row);
        }

        std::vector<int> ints(const std::string &v) {
            std::vector<int> out;
            if (v.empty()) return out;
            std::size_t start = 0;
            while (true) {
                const std::size_t end = v.find('_', start);
                out.push_back(std::stoi(v.substr(start, end == std::string::npos ? std::string::npos : end - start)));
                if (end == std::string::npos) break;
                start = end + 1;
            }
            return out;
        }

        const std::map<std::string, int> &zones() {
            static const std::map<std::string, int> z = {
                {"drawPile.knownBottom", 1}, {"drawPile.unknown", 2}, {"drawPile.knownTop", 3},
                {"discardPile.knownBottom", 4}, {"discardPile.unknown", 5}, {"discardPile.knownTop", 6},
                {"exhaustPile.knownBottom", 7}, {"exhaustPile.unknown", 8}, {"exhaustPile.knownTop", 9},
            };
            return z;
        }

    }  // namespace

    float combatTokRoundHalf(float x) {
        std::uint32_t u;
        std::memcpy(&u, &x, 4);
        const std::uint32_t sign = u & 0x80000000u, mag = u & 0x7fffffffu;
        if (mag >= 0x7f800000u) return x;   // inf, nan
        if (mag >= 0x477ff000u) return sign ? -INFINITY : INFINITY;   // >= 65520 rounds past the largest half
        if (mag < 0x38800000u) {   // below 2^-14: half subnormals, step 2^-24
            float a;
            std::memcpy(&a, &mag, 4);
            const float q = std::nearbyint(a * 16777216.0f) / 16777216.0f;
            return sign ? -q : q;
        }
        std::uint32_t base = mag & ~0x1fffu;
        const std::uint32_t rem = mag & 0x1fffu;
        if (rem > 0x1000u || (rem == 0x1000u && (base & 0x2000u))) base += 0x2000u;
        const std::uint32_t r = sign | base;
        float out;
        std::memcpy(&out, &r, 4);
        return out;
    }

    void combatTokEncodeWire(const nlohmann::json &wire, CombatTokInputs &out) {
        out = CombatTokInputs{};
        std::vector<double> g;
        g.reserve(kCtnGlobLen);
        for (const char *k : kGlobalScalars) g.push_back(num(field(wire, k)));
        for (const char *pile : {"drawPile", "discardPile", "exhaustPile"})
            g.push_back(num(field(field(wire, pile), "fullOrderObserved")));
        flat(field(wire, "cardSelect"), g);
        const auto &q = field(wire, "curCardQueueItem");
        for (auto it = q.begin(); it != q.end(); ++it)
            if (it.key() != "card") flat(it.value(), g);
        const auto &pl = field(wire, "player");
        for (const char *k : kPlayerScalars) g.push_back(num(field(pl, k)));
        for (const auto &v : field(pl, "bombs")) g.push_back(num(v));
        for (const auto &v : field(pl, "relicCounters")) g.push_back(num(v));
        if (static_cast<int>(g.size()) != kCtnGlobLen)
            throw std::runtime_error("combat net encoder: global+player length " + std::to_string(g.size())
                                     + ", the net was trained on " + std::to_string(kCtnGlobLen));
        for (int i = 0; i < kCtnGlobLen; ++i)
            out.glob[i] = combatTokRoundHalf(slogf(static_cast<float>(g[i])));

        setBits(bits64(field(pl, "relicBits0")), 0, out.relics);
        setBits(bits64(field(pl, "relicBits1")), 64, out.relics);
        setBits(bits64(field(pl, "statusBits0")), 0, out.sbits);
        setBits(bits64(field(pl, "statusBits1")), 64, out.sbits);
        for (const auto &pair : field(pl, "statusMap")) {
            if (static_cast<int>(out.smap.size()) >= kCtnStatusMax) break;
            const double a = std::trunc(num(pair.at(0))), b = std::trunc(num(pair.at(1)));
            out.smap.push_back({clip16(a), clip16(std::min(b, 32767.0))});
        }

        int pos = 0;
        for (const auto &c : field(wire, "hand")) cardRow(0, pos++, c, out);
        for (const char *pile : {"drawPile", "discardPile", "exhaustPile"}) {
            const auto &p = field(wire, pile);
            for (const char *part : {"knownBottom", "unknown", "knownTop"}) {
                const int zone = zones().at(std::string(pile) + "." + part);
                const bool unknown = std::strcmp(part, "unknown") == 0;
                pos = 0;
                for (const auto &c : field(p, part)) cardRow(zone, unknown ? 0 : pos++, c, out);
            }
        }
        pos = 0;
        for (const auto &c : field(wire, "limbo")) {
            if (static_cast<int>(num(field(c, "id"))) != 0) cardRow(10, pos, c, out);   // id 0 = empty slot
            ++pos;
        }
        pos = 0;
        for (const auto &c : field(wire, "stasisCards")) cardRow(11, pos++, c, out);
        if (static_cast<int>(num(field(field(q, "card"), "id"))) != 0) cardRow(12, 0, field(q, "card"), out);

        std::vector<double> mn;
        for (const auto &m : field(wire, "monsters")) {
            if (static_cast<int>(num(field(m, "id"))) == 0 && static_cast<int>(num(field(m, "maxHp"))) == 0)
                continue;   // empty slot
            if (out.nmon >= kCtnMonMax) break;   // tensorize M_MAX cut
            const auto &hist = field(m, "moveHistory");
            const double h0 = hist.size() > 0 ? num(hist[0]) : 0.0, h1 = hist.size() > 1 ? num(hist[1]) : 0.0;
            out.mcat[out.nmon] = {clip16(num(field(m, "idx"))), clip16(num(field(m, "id"))), clip16(h0), clip16(h1)};
            mn.clear();
            for (const char *k : kMonsterScalars) mn.push_back(num(field(m, k)));
            for (const auto &v : field(m, "smallPowers")) mn.push_back(num(v));
            const auto &ri = field(m, "pendingRollInputs");
            for (const char *k : kRollInputs) mn.push_back(num(field(ri, k)));
            const auto &preds = field(m, "pendingAttackPredicates");
            const auto &rih = field(m, "pendingRollInputHistory");
            mn.push_back(static_cast<double>(preds.size()));
            mn.push_back(static_cast<double>(rih.size()));
            flat(preds, mn);
            flat(rih, mn);
            const int n = std::min<int>(static_cast<int>(mn.size()), kCtnMonNum);
            for (int i = 0; i < n; ++i)
                out.mnum[out.nmon][i] = combatTokRoundHalf(slogf(static_cast<float>(mn[i])));
            ++out.nmon;
        }

        int slot = 0;
        for (const auto &p : field(wire, "potions")) {
            if (slot >= kCtnPotionSlots) break;
            out.potions[slot++] = clip16(std::trunc(num(p)));
        }

        std::vector<double> qv;
        for (int kind = 0; kind < 2; ++kind) {
            for (const auto &it : field(wire, kind == 0 ? "pendingActionQueue" : "pendingCardQueue")) {
                if (static_cast<int>(out.queues.size()) >= kCtnQueueMax) break;
                qv.clear();
                flat(it, qv);
                std::array<std::int16_t, kCtnQueueLen> row{};
                row[0] = static_cast<std::int16_t>(kind);
                for (int i = 0; i + 1 < kCtnQueueLen && i < static_cast<int>(qv.size()); ++i)
                    row[i + 1] = clip16(std::trunc(qv[i]));
                out.queues.push_back(row);
            }
        }
    }

    std::array<std::int16_t, kCtnActionLen> combatTokActionRow(const std::string &semantic) {
        std::array<std::int16_t, kCtnActionLen> row{};
        if (semantic.empty()) return row;
        std::map<std::string, std::string> kv;
        std::size_t start = 0;
        while (start <= semantic.size()) {
            const std::size_t end = semantic.find('/', start);
            const std::string part = semantic.substr(start, end == std::string::npos ? std::string::npos : end - start);
            const std::size_t eq = part.find('=');
            if (eq != std::string::npos) kv[part.substr(0, eq)] = part.substr(eq + 1);
            if (end == std::string::npos) break;
            start = end + 1;
        }
        auto first = [&](const char *k) {
            const auto it = kv.find(k);
            if (it == kv.end()) throw std::runtime_error(std::string("combat net encoder: action lacks ") + k);
            const auto v = ints(it->second);
            return v.empty() ? 0 : v[0];
        };
        auto all = [&](const char *k) {
            const auto it = kv.find(k);
            if (it == kv.end()) throw std::runtime_error(std::string("combat net encoder: action lacks ") + k);
            return ints(it->second);
        };
        int i = 0;
        row[i++] = clip16(first("t"));
        row[i++] = clip16(first("s"));
        auto c = all("c");
        if (c.size() > 1) c[1] = 0;   // the card's unique id: identity only
        for (int k = 0; k < 8; ++k) row[i++] = clip16(k < static_cast<int>(c.size()) ? c[k] : 0);
        row[i++] = clip16(first("o"));
        const auto p = all("p");
        for (int k = 0; k < 2; ++k) row[i++] = clip16(k < static_cast<int>(p.size()) ? p[k] : 0);
        for (const char *k : {"x", "d", "k", "task"}) row[i++] = clip16(first(k));
        const auto selIt = kv.find("sel");
        if (selIt == kv.end()) throw std::runtime_error("combat net encoder: action lacks sel");
        const std::string &sel = selIt->second;
        int n = 0;
        if (!sel.empty()) {
            std::size_t s = 0;
            while (n < kCtnSelMax) {
                const std::size_t e = sel.find('+', s);
                auto card = ints(sel.substr(s, e == std::string::npos ? std::string::npos : e - s));
                card.resize(std::max<std::size_t>(card.size(), 6), 0);
                row[17 + 3 * n] = clip16(card[0]);
                row[18 + 3 * n] = clip16(card[2]);
                row[19 + 3 * n] = clip16(card[5]);
                ++n;
                if (e == std::string::npos) break;
                s = e + 1;
            }
        }
        return row;
    }

    void combatTokEncodeRoot(const BattleContext &state, const SilverSearchContext &context,
                             const std::vector<SilverSearcher::Edge> &edges, CombatTokInputs &out) {
        combatTokEncodeWire(nlohmann::json(wireFromSearchState(state, context)), out);
        out.actions.clear();
        out.actions.reserve(edges.size());
        for (const auto &edge : edges) {
            std::string fp;
            try {
                fp = semanticFingerprint(semanticFromSearchAction(state, edge.action));
            } catch (const std::exception &) {
                fp.clear();   // as silverazgen's fingerprint(): no semantic form
            }
            out.actions.push_back(combatTokActionRow(fp));
        }
    }

    // --- loading ----------------------------------------------------------------------------------------------

    bool CombatTokNet::load(const std::string &path, std::string *error) {
        auto fail = [&](const std::string &why) {
            if (error) *error = path + ": " + why;
            d_ = 0;
            return false;
        };
        std::ifstream f(path, std::ios::binary);
        if (!f) return fail("cannot open");
        char magic[8];
        if (!f.read(magic, 8) || std::memcmp(magic, "CTOKNET1", 8) != 0) return fail("not a CTOKNET1 file");
        std::int32_t hdr[10];
        if (!f.read(reinterpret_cast<char *>(hdr), sizeof(hdr))) return fail("truncated header");
        const int d = hdr[0], nLayers = hdr[1], heads = hdr[2], ffn = hdr[3];
        if (d <= 0 || nLayers <= 0 || heads <= 0 || d % heads != 0 || ffn <= 0) return fail("bad dims");
        if (hdr[4] != kCtnGlobLen || hdr[5] != kCtnMonNum || hdr[6] != kCtnQueueLen || hdr[7] != kCtnActionLen)
            return fail("input lengths differ from this encoder");
        std::int32_t count = 0;
        if (!f.read(reinterpret_cast<char *>(&count), 4) || count <= 0 || count > 4096) return fail("bad tensor count");
        std::map<std::string, std::pair<std::vector<int>, std::vector<float>>> t;
        for (int k = 0; k < count; ++k) {
            std::int32_t len = 0, ndim = 0;
            if (!f.read(reinterpret_cast<char *>(&len), 4) || len <= 0 || len > 256) return fail("bad name");
            std::string name(static_cast<std::size_t>(len), '\0');
            if (!f.read(name.data(), len) || !f.read(reinterpret_cast<char *>(&ndim), 4) || ndim < 1 || ndim > 4)
                return fail("bad tensor " + name);
            std::vector<int> shape(ndim);
            std::size_t n = 1;
            for (auto &s : shape) {
                std::int32_t v = 0;
                if (!f.read(reinterpret_cast<char *>(&v), 4) || v <= 0) return fail("bad shape of " + name);
                s = v;
                n *= static_cast<std::size_t>(v);
            }
            std::vector<float> data(n);
            if (!f.read(reinterpret_cast<char *>(data.data()), static_cast<std::streamsize>(n * 4)))
                return fail("truncated " + name);
            t[name] = {std::move(shape), std::move(data)};
        }
        std::string missing;
        auto get = [&](const std::string &name, std::vector<int> shape) -> std::vector<float> {
            const auto it = t.find(name);
            if (it == t.end() || it->second.first != shape) {
                if (missing.empty()) missing = name;
                return {};
            }
            return it->second.second;
        };
        auto linear = [&](const std::string &name, int in, int out) {
            Linear l;
            l.in = in;
            l.out = out;
            const auto w = get(name + ".weight", {out, in});
            l.b = get(name + ".bias", {out});
            if (w.empty() || l.b.empty()) return l;
            l.wt.resize(static_cast<std::size_t>(in) * out);
            for (int o = 0; o < out; ++o)
                for (int i = 0; i < in; ++i) l.wt[static_cast<std::size_t>(i) * out + o] = w[static_cast<std::size_t>(o) * in + i];
            return l;
        };
        d_ = d;   // read by the lambdas' callers below
        heads_ = heads;
        valueOn_ = hdr[8] != 0;
        auxOn_ = hdr[9] != 0;
        card_ = get("card.weight", {kCardV, d});
        zone_ = get("zone.weight", {kZoneV, d});
        cardNum_ = linear("card_num", 7, d);
        mon_ = get("mon.weight", {kMonV, d});
        monIdx_ = get("mon_idx.weight", {8, d});
        move_ = get("move.weight", {kMoveV, d});
        monNum_ = linear("mon_num", kCtnMonNum, d);
        stat_ = get("stat.weight", {kStatV, d});
        statNum_ = linear("stat_num", 1, d);
        queue_ = linear("queue", kCtnQueueLen, d);
        glob0_ = linear("glob.0", kCtnGlobLen + 256, d);
        glob2_ = linear("glob.2", d, d);
        pot_ = get("pot.weight", {kPotV, d});
        tokType_ = get("tok_type.weight", {5, d});
        layers_.assign(nLayers, Layer{});
        for (int l = 0; l < nLayers; ++l) {
            const std::string p = "trunk.layers." + std::to_string(l) + ".";
            Layer &L = layers_[l];
            {
                // self_attn.in_proj_weight / in_proj_bias, out_proj
                Linear q;
                q.in = d;
                q.out = 3 * d;
                const auto w = get(p + "self_attn.in_proj_weight", {3 * d, d});
                q.b = get(p + "self_attn.in_proj_bias", {3 * d});
                if (!w.empty()) {
                    q.wt.resize(static_cast<std::size_t>(d) * 3 * d);
                    for (int o = 0; o < 3 * d; ++o)
                        for (int i = 0; i < d; ++i)
                            q.wt[static_cast<std::size_t>(i) * 3 * d + o] = w[static_cast<std::size_t>(o) * d + i];
                }
                L.qkv = std::move(q);
            }
            L.proj = linear(p + "self_attn.out_proj", d, d);
            L.ff1 = linear(p + "linear1", d, ffn);
            L.ff2 = linear(p + "linear2", ffn, d);
            L.ln1w = get(p + "norm1.weight", {d});
            L.ln1b = get(p + "norm1.bias", {d});
            L.ln2w = get(p + "norm2.weight", {d});
            L.ln2b = get(p + "norm2.bias", {d});
        }
        normW_ = get("norm.weight", {d});
        normB_ = get("norm.bias", {d});
        aType_ = get("a_type.weight", {8, d});
        aCard_ = get("a_card.weight", {kCardV, d});
        aPot_ = get("a_pot.weight", {kPotV, d});
        aTarget_ = get("a_target.weight", {8, d});
        aNum_ = linear("a_num", kCtnActionLen, d);
        aSel_ = get("a_sel.weight", {kCardV, d});
        pol0_ = linear("pol.0", 3 * d, d);
        pol2_ = linear("pol.2", d, 1);
        val0_ = linear("val.0", d, d);
        val2_ = linear("val.2", d, kCtnValueClasses);
        aux0_ = linear("auxh.0", d, d);
        aux2_ = linear("auxh.2", d, kCtnAux);
        if (!missing.empty()) return fail("missing or misshapen tensor " + missing);
        return true;
    }

    // --- forward ----------------------------------------------------------------------------------------------

    void CombatTokNet::forward(const CombatTokInputs &in, CombatTokOutputs &out) const {
        if (!loaded()) throw std::runtime_error("CombatTokNet: forward without a loaded net");
        const int d = d_;
        // Tokens: global, cards, all kCtnMonMax monster slots (slots >= nmon are padding: they are no keys, but
        // their outputs exist, as in PyTorch, and an action's target may gather one), status pairs with id > 0,
        // queue items.
        std::vector<int> statusRows;
        for (int s = 0; s < static_cast<int>(in.smap.size()); ++s)
            if (in.smap[s][0] > 0) statusRows.push_back(s);
        const int C = static_cast<int>(in.cards.size()), M = kCtnMonMax;
        const int S = static_cast<int>(statusRows.size()), Q = static_cast<int>(in.queues.size());
        const int T = 1 + C + M + S + Q;
        thread_local std::vector<float> x, h, buf, qkv, att, ffh, feat;
        thread_local std::vector<char> key;
        x.assign(static_cast<std::size_t>(T) * d, 0.0f);
        key.assign(T, 1);

        // global token
        feat.assign(kCtnGlobLen + 256, 0.0f);
        for (int i = 0; i < kCtnGlobLen; ++i) feat[i] = slogf(in.glob[i]);
        for (int i = 0; i < 128; ++i) {
            feat[kCtnGlobLen + i] = in.relics[i];
            feat[kCtnGlobLen + 128 + i] = in.sbits[i];
        }
        buf.resize(d);
        applyLinear(glob0_, feat.data(), 1, buf.data());
        for (int i = 0; i < d; ++i) buf[i] = gelu(buf[i]);
        applyLinear(glob2_, buf.data(), 1, x.data());
        for (int s = 0; s < kCtnPotionSlots; ++s) addRow(x.data(), pot_, clampi(in.potions[s], 0, kPotV - 1), d);
        addRow(x.data(), tokType_, 0, d);

        // cards
        if (C > 0) {
            feat.assign(static_cast<std::size_t>(C) * 7, 0.0f);
            static constexpr int cols[7] = {1, 3, 4, 5, 6, 7, 8};
            for (int c = 0; c < C; ++c)
                for (int k = 0; k < 7; ++k) feat[static_cast<std::size_t>(c) * 7 + k] = slogf(in.cards[c][cols[k]]);
            applyLinear(cardNum_, feat.data(), C, x.data() + d);
            for (int c = 0; c < C; ++c) {
                float *row = x.data() + static_cast<std::size_t>(1 + c) * d;
                addRow(row, card_, clampi(in.cards[c][2], 0, kCardV - 1), d);
                addRow(row, zone_, clampi(in.cards[c][0], 0, kZoneV - 1), d);
                addRow(row, tokType_, 1, d);
            }
        }
        // monsters
        {
            feat.assign(static_cast<std::size_t>(M) * kCtnMonNum, 0.0f);
            for (int m = 0; m < M; ++m)
                for (int k = 0; k < kCtnMonNum; ++k) feat[static_cast<std::size_t>(m) * kCtnMonNum + k] = in.mnum[m][k];
            float *base = x.data() + static_cast<std::size_t>(1 + C) * d;
            applyLinear(monNum_, feat.data(), M, base);
            for (int m = 0; m < M; ++m) {
                float *row = base + static_cast<std::size_t>(m) * d;
                const auto &mc = in.mcat[m];
                addRow(row, mon_, clampi(mc[1], 0, kMonV - 1), d);
                addRow(row, monIdx_, clampi(mc[0], 0, 7), d);
                addRow(row, move_, clampi(mc[2], 0, kMoveV - 1), d);
                addRow(row, move_, clampi(mc[3], 0, kMoveV - 1), d, 0.5f);
                addRow(row, tokType_, 2, d);
                key[1 + C + m] = m < in.nmon ? 1 : 0;
            }
        }
        // status
        for (int k = 0; k < S; ++k) {
            const auto &sm = in.smap[statusRows[k]];
            float *row = x.data() + static_cast<std::size_t>(1 + C + M + k) * d;
            const float v = slogf(sm[1]);
            for (int i = 0; i < d; ++i) row[i] = statNum_.b[i] + v * statNum_.wt[i];
            addRow(row, stat_, clampi(sm[0], 0, kStatV - 1), d);
            addRow(row, tokType_, 3, d);
        }
        // queues
        if (Q > 0) {
            feat.assign(static_cast<std::size_t>(Q) * kCtnQueueLen, 0.0f);
            for (int k = 0; k < Q; ++k)
                for (int i = 0; i < kCtnQueueLen; ++i)
                    feat[static_cast<std::size_t>(k) * kCtnQueueLen + i] = slogf(in.queues[k][i]);
            float *base = x.data() + static_cast<std::size_t>(1 + C + M + S) * d;
            applyLinear(queue_, feat.data(), Q, base);
            for (int k = 0; k < Q; ++k) addRow(base + static_cast<std::size_t>(k) * d, tokType_, 4, d);
        }

        // trunk: pre-norm encoder layers (self-attention with key padding, ReLU feed-forward)
        const int hd = d / heads_;
        const float scale = 1.0f / std::sqrt(static_cast<float>(hd));
        h.resize(static_cast<std::size_t>(T) * d);
        qkv.resize(static_cast<std::size_t>(T) * 3 * d);
        att.resize(static_cast<std::size_t>(T) * d);
        std::vector<float> score(T);
        for (const Layer &L : layers_) {
            for (int t = 0; t < T; ++t)
                layerNorm(x.data() + static_cast<std::size_t>(t) * d, d, L.ln1w.data(), L.ln1b.data(),
                          h.data() + static_cast<std::size_t>(t) * d);
            applyLinear(L.qkv, h.data(), T, qkv.data());
            for (int hh = 0; hh < heads_; ++hh) {
                const int qo = hh * hd, ko = d + hh * hd, vo = 2 * d + hh * hd;
                for (int i = 0; i < T; ++i) {
                    const float *qi = qkv.data() + static_cast<std::size_t>(i) * 3 * d + qo;
                    float top = -INFINITY;
                    for (int j = 0; j < T; ++j) {
                        if (!key[j]) continue;
                        const float *kj = qkv.data() + static_cast<std::size_t>(j) * 3 * d + ko;
                        float s = 0.0f;
                        for (int e = 0; e < hd; ++e) s += qi[e] * kj[e];
                        s *= scale;
                        score[j] = s;
                        top = std::max(top, s);
                    }
                    float sum = 0.0f;
                    for (int j = 0; j < T; ++j) {
                        if (!key[j]) continue;
                        score[j] = std::exp(score[j] - top);
                        sum += score[j];
                    }
                    float *ai = att.data() + static_cast<std::size_t>(i) * d + qo;
                    for (int e = 0; e < hd; ++e) ai[e] = 0.0f;
                    const float inv = 1.0f / sum;
                    for (int j = 0; j < T; ++j) {
                        if (!key[j]) continue;
                        const float a = score[j] * inv;
                        const float *vj = qkv.data() + static_cast<std::size_t>(j) * 3 * d + vo;
                        for (int e = 0; e < hd; ++e) ai[e] += a * vj[e];
                    }
                }
            }
            applyLinear(L.proj, att.data(), T, h.data());
            for (std::size_t k = 0; k < static_cast<std::size_t>(T) * d; ++k) x[k] += h[k];
            for (int t = 0; t < T; ++t)
                layerNorm(x.data() + static_cast<std::size_t>(t) * d, d, L.ln2w.data(), L.ln2b.data(),
                          h.data() + static_cast<std::size_t>(t) * d);
            ffh.resize(static_cast<std::size_t>(T) * L.ff1.out);
            applyLinear(L.ff1, h.data(), T, ffh.data());
            for (auto &v : ffh) v = v > 0.0f ? v : 0.0f;
            applyLinear(L.ff2, ffh.data(), T, h.data());
            for (std::size_t k = 0; k < static_cast<std::size_t>(T) * d; ++k) x[k] += h[k];
        }
        // final norm: needed for the global token and the monster slots only
        std::vector<float> cls(d), monH(static_cast<std::size_t>(M) * d);
        layerNorm(x.data(), d, normW_.data(), normB_.data(), cls.data());
        for (int m = 0; m < M; ++m)
            layerNorm(x.data() + static_cast<std::size_t>(1 + C + m) * d, d, normW_.data(), normB_.data(),
                      monH.data() + static_cast<std::size_t>(m) * d);

        // heads on the global token
        std::vector<float> hid(d);
        applyLinear(val0_, cls.data(), 1, hid.data());
        for (auto &v : hid) v = gelu(v);
        applyLinear(val2_, hid.data(), 1, out.value.data());
        applyLinear(aux0_, cls.data(), 1, hid.data());
        for (auto &v : hid) v = gelu(v);
        applyLinear(aux2_, hid.data(), 1, out.aux.data());

        // policy: one logit per action from (global token, action embedding, target monster slot)
        const int E = static_cast<int>(in.actions.size());
        out.logits.assign(E, 0.0f);
        if (E == 0) return;
        std::vector<float> an(static_cast<std::size_t>(E) * kCtnActionLen), at(static_cast<std::size_t>(E) * d);
        for (int e = 0; e < E; ++e)
            for (int k = 0; k < kCtnActionLen; ++k)
                an[static_cast<std::size_t>(e) * kCtnActionLen + k] = slogf(in.actions[e][k]);
        applyLinear(aNum_, an.data(), E, at.data());
        std::vector<float> z(static_cast<std::size_t>(E) * 3 * d);
        for (int e = 0; e < E; ++e) {
            const auto &a = in.actions[e];
            float *row = at.data() + static_cast<std::size_t>(e) * d;
            addRow(row, aType_, clampi(a[0], 0, 7), d);
            addRow(row, aCard_, clampi(a[2], 0, kCardV - 1), d);
            addRow(row, aPot_, clampi(a[11], 0, kPotV - 1), d);
            addRow(row, aTarget_, clampi(a[13] + 1, 0, 7), d);
            for (int s = 0; s < kCtnSelMax; ++s) {
                const int id = clampi(a[17 + 3 * s], 0, kCardV - 1);
                if (id > 0) addRow(row, aSel_, id, d);
            }
            float *zr = z.data() + static_cast<std::size_t>(e) * 3 * d;
            std::copy(cls.begin(), cls.end(), zr);
            std::copy(row, row + d, zr + d);
            if (a[13] >= 0) {
                const float *tg = monH.data() + static_cast<std::size_t>(clampi(a[13], 0, M - 1)) * d;
                std::copy(tg, tg + d, zr + 2 * d);
            } else {
                std::fill(zr + 2 * d, zr + 3 * d, 0.0f);
            }
        }
        std::vector<float> ph(static_cast<std::size_t>(E) * d);
        applyLinear(pol0_, z.data(), E, ph.data());
        for (auto &v : ph) v = gelu(v);
        applyLinear(pol2_, ph.data(), E, out.logits.data());
    }

}
