package stsmodelinspector;

import com.google.gson.Gson;
import com.megacrit.cardcrawl.cards.AbstractCard;
import com.megacrit.cardcrawl.cards.CardGroup;
import com.megacrit.cardcrawl.core.CardCrawlGame;
import com.megacrit.cardcrawl.core.Settings;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.map.MapEdge;
import com.megacrit.cardcrawl.map.MapRoomNode;
import com.megacrit.cardcrawl.relics.AbstractRelic;
import com.megacrit.cardcrawl.rewards.RewardItem;
import com.megacrit.cardcrawl.rooms.AbstractRoom;
import com.megacrit.cardcrawl.shop.ShopScreen;
import com.megacrit.cardcrawl.shop.StorePotion;
import com.megacrit.cardcrawl.shop.StoreRelic;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;

/** Detached, read-only public OOC projection. Never calls game actions or RNG. */
final class LiveOocCapture {
    private static final Gson JSON = new Gson();
    private static final String CHOICES = "mcpthespire.ChoiceScreenUtils";
    private static Object rewardPlayer, rewardNode;
    private static long nextRewardIdentity;
    private static final java.util.IdentityHashMap<Object,String> rewardIdentities = new java.util.IdentityHashMap<>();
    static final SeenRelicOffers seenRelicOffers = new SeenRelicOffers();
    static final CombatClassHistory combatClassHistory = new CombatClassHistory();

    // A seed alone does not identify a saved run. Only an identity-checked
    // BaseMod checkpoint may restore this ledger; legacy TSVs are preserved
    // on disk but are never used to qualify a different save or rollback.
    static final class CombatClassHistory {
        private Object player, lastGroup;
        private long seed;
        private int act = -1, lastFloor = -1;
        private boolean complete;
        private final List<Map<String,Object>> entries = new ArrayList<>();

        void clear() {
            player = null; lastGroup = null; seed = 0; act = -1; lastFloor = -1;
            complete = false; entries.clear();
        }
        void resetForFreshRun(Object currentPlayer, long currentSeed, int currentAct) {
            clear(); player = currentPlayer; seed = currentSeed; act = currentAct; complete = true;
        }
        boolean restoreCheckpoint(Object currentPlayer, long currentSeed, int currentAct,
                int floor, RelicOfferRecorder.SaveData data, List<Integer> completedFloors) {
            clear();
            if (data == null || !Integer.valueOf(currentAct).equals(data.combatAct) || data.combatEntries == null
                    || data.combatEntries.size() > 20 || !Boolean.TRUE.equals(data.combatComplete)) return false;
            int previous = currentAct <= 1 ? 0 : currentAct == 2 ? 17 : currentAct == 3 ? 34 : 51;
            for (Map<String,Object> entry : data.combatEntries) {
                if (entry == null || !(entry.get("floor") instanceof Number)) { entries.clear(); return false; }
                Number number = (Number)entry.get("floor");
                int f = number.intValue();
                Object kind = entry.get("kind"), encounter = entry.get("encounter");
                boolean sameFloorColosseum = f == previous && !entries.isEmpty()
                        && colosseumPair(currentAct, entries.get(entries.size()-1), String.valueOf(kind), String.valueOf(encounter));
                boolean colosseumEncounter = "COLOSSEUM_EVENT_SLAVERS".equals(encounter)
                        || "COLOSSEUM_EVENT_NOBS".equals(encounter);
                if ((colosseumEncounter && (currentAct != 2 || !"FIXED_EVENT".equals(kind)))
                        || ("COLOSSEUM_EVENT_NOBS".equals(encounter) && !sameFloorColosseum)
                        || number.doubleValue() != f || f < previous || (f == previous && !sameFloorColosseum) || f > floor
                        || !Arrays.asList("NORMAL_QUEUE", "ELITE_QUEUE", "FIXED_EVENT", "BOSS").contains(kind)
                        || !(encounter instanceof String)
                        || (("NORMAL_QUEUE".equals(kind) || "ELITE_QUEUE".equals(kind))
                            && ((String)encounter).isEmpty())) { entries.clear(); return false; }
                entries.add(object("floor", f, "kind", kind, "encounter", encounter));
                previous = f;
            }
            // A save made during the current fight may include that fight
            // before damage_taken is appended. No other extra entry is valid.
            int extra = entries.size() - completedFloors.size();
            if (extra < 0 || extra > 1 || (extra == 1
                    && !Integer.valueOf(floor).equals(entries.get(entries.size()-1).get("floor")))) {
                entries.clear(); return false;
            }
            for (int i = 0; i < completedFloors.size(); ++i)
                if (!completedFloors.get(i).equals(entries.get(i).get("floor"))) {
                    entries.clear(); return false;
                }
            player = currentPlayer; seed = currentSeed; act = currentAct; lastFloor = floor;
            complete = true;
            return true;
        }
        void observe(Object currentPlayer, long currentSeed, int currentAct, int floor,
                boolean noPriorActCombat, boolean inCombat, Object group, String kind,
                String encounter) {
            observe(currentPlayer,currentSeed,currentAct,floor,noPriorActCombat,inCombat,group,kind,encounter,null);
        }
        private static boolean colosseumPair(int act, Map<String,Object> first, String kind, String encounter) {
            return act == 2 && "FIXED_EVENT".equals(first.get("kind")) && "FIXED_EVENT".equals(kind)
                    && "COLOSSEUM_EVENT_SLAVERS".equals(first.get("encounter"))
                    && "COLOSSEUM_EVENT_NOBS".equals(encounter);
        }
        void observe(Object currentPlayer, long currentSeed, int currentAct, int floor,
                boolean noPriorActCombat, boolean inCombat, Object group, String kind,
                String encounter, String eventClass) {
            if (player != currentPlayer || seed != currentSeed || act != currentAct
                    || floor < lastFloor) {
                player = currentPlayer; seed = currentSeed; act = currentAct;
                entries.clear(); lastGroup = null; complete = noPriorActCombat;
            }
            lastFloor = floor;
            if (!inCombat) { lastGroup = null; return; }
            if (group == null) return;
            if (!Arrays.asList("NORMAL_QUEUE", "ELITE_QUEUE", "FIXED_EVENT", "BOSS").contains(kind)) {
                complete = false; return;
            }
            if (("NORMAL_QUEUE".equals(kind) || "ELITE_QUEUE".equals(kind))
                    && (encounter == null || encounter.isEmpty())) { complete = false; return; }
            boolean existingQualifiedFight = complete && !entries.isEmpty()
                    && Integer.valueOf(floor).equals(entries.get(entries.size()-1).get("floor"))
                    && kind.equals(entries.get(entries.size()-1).get("kind"))
                    && encounter != null && encounter.equals(entries.get(entries.size()-1).get("encounter"));
            // A bound checkpoint can already prove the current fight even if
            // save reconstruction has not recreated its event object yet.
            // Starting a new Colosseum fight still requires its actual owner.
            if (("COLOSSEUM_EVENT_SLAVERS".equals(encounter) || "COLOSSEUM_EVENT_NOBS".equals(encounter))
                    && (currentAct != 2 || !"FIXED_EVENT".equals(kind)
                        || (!"Colosseum".equals(eventClass) && !existingQualifiedFight))) {
                complete = false; return;
            }
            if ("COLOSSEUM_EVENT_NOBS".equals(encounter) && (entries.isEmpty()
                    || !Integer.valueOf(floor).equals(entries.get(entries.size()-1).get("floor")))) {
                complete = false; return;
            }
            if (group != lastGroup) {
                if (!entries.isEmpty()
                        && ((Number)entries.get(entries.size() - 1).get("floor")).intValue() == floor) {
                    Map<String,Object> previous = entries.get(entries.size() - 1);
                    if ("Colosseum".equals(eventClass) && colosseumPair(currentAct,previous,kind,encounter))
                        entries.add(object("floor",floor,"kind",kind,"encounter",encounter));
                    else if (!kind.equals(previous.get("kind"))
                            || !String.valueOf(previous.get("encounter")).equals(encounter)) complete = false;
                } else entries.add(object("floor", floor, "kind", kind,
                        "encounter", encounter == null ? "" : encounter));
                lastGroup = group;
            }
        }
        void invalidate() { complete = false; }
        boolean complete() { return complete; }
        int act() { return act; }
        boolean completeFor(List<Integer> completedFloors) {
            if (!complete || entries.size() != completedFloors.size()) return false;
            for (int i = 0; i < entries.size(); ++i)
                if (!completedFloors.get(i).equals(entries.get(i).get("floor"))) return false;
            return true;
        }
        List<Map<String,Object>> snapshot() {
            List<Map<String,Object>> copy = new ArrayList<>();
            for (Map<String,Object> entry : entries) copy.add(new LinkedHashMap<>(entry));
            return copy;
        }
    }

    static void observeCombatRoom(AbstractRoom room) {
        if (AbstractDungeon.player == null || room == null) return;
        RelicOfferRecorder.bind();
        final int act = AbstractDungeon.actNum, floor = AbstractDungeon.floorNum;
        final int actStart = act <= 1 ? 0 : act == 2 ? 17 : act == 3 ? 34 : 51;
        boolean noPriorActCombat = true;
        if (CardCrawlGame.metricData != null) {
            for (Object raw : CardCrawlGame.metricData.damage_taken) {
                Object value = map(raw).get("floor");
                if (!(value instanceof Number)) { noPriorActCombat = false; break; }
                int priorFloor = ((Number)value).intValue();
                if (priorFloor > actStart && priorFloor <= floor) {
                    noPriorActCombat = false;
                    break;
                }
            }
        } else noPriorActCombat = false;
        boolean inCombat = room.phase == AbstractRoom.RoomPhase.COMBAT;
        String kind = null;
        if (inCombat) {
            String roomClass = room.getClass().getSimpleName();
            if (room.event != null || "EventRoom".equals(roomClass)) kind = "FIXED_EVENT";
            else if ("MonsterRoomElite".equals(roomClass)) kind = "ELITE_QUEUE";
            else if ("MonsterRoomBoss".equals(roomClass)) kind = "BOSS";
            else if ("MonsterRoom".equals(roomClass)) kind = "NORMAL_QUEUE";
        }
        combatClassHistory.observe(AbstractDungeon.player, Settings.seed, act, floor,
                noPriorActCombat, inCombat, inCombat ? AbstractDungeon.getMonsters() : null, kind,
                inCombat ? STSModelInspector.encounterName(room) : "",
                room.event == null ? null : room.event.getClass().getSimpleName());
    }

    static void invalidateCombatRoomHistory() { combatClassHistory.invalidate(); }

    // Public offers qualify only from fresh observation or an exact save
    // checkpoint. Legacy saves cannot recover previously unobserved offers.
    static final class SeenRelicOffers {
        private Object player;
        private long seed;
        private int lastFloor = -1;
        private boolean complete;
        private final LinkedHashSet<String> offers = new LinkedHashSet<>();

        void clear() {
            player = null; seed = 0; lastFloor = -1; complete = false; offers.clear();
        }
        boolean restore(Object currentPlayer, long currentSeed, int floor,
                RelicOfferRecorder.SaveData saved, String character, int ascension) {
            clear(); player = currentPlayer; seed = currentSeed; lastFloor = floor;
            if (!RelicOfferRecorder.matches(saved, currentSeed, floor, character, ascension)
                    || saved.offers == null || saved.offers.size() > 181) return false;
            for (String id : saved.offers) {
                if (id == null || id.isEmpty() || !offers.add(id)) {
                    offers.clear(); return false;
                }
            }
            complete = saved.complete;
            return true;
        }
        void add(String id) {
            if (id == null || id.isEmpty()) { invalidate(); return; }
            offers.add(id);
        }

        void observe(Object currentPlayer, long currentSeed, int floor,
                     boolean freshRun, String screen, Map<String,Object> details) {
            if (player != currentPlayer || seed != currentSeed || floor < lastFloor) {
                player = currentPlayer;
                seed = currentSeed;
                lastFloor = -1;
                complete = freshRun;
                offers.clear();
            }
            if (lastFloor >= 0 && floor > lastFloor + 1) complete = false;
            lastFloor = floor;
            if ("shop".equals(screen)) {
                for (Object entry : list(details.get("relics"))) {
                    Map<String,Object> offer = map(entry);
                    if (offer.get("id") != null && ((Number)offer.get("price")).intValue() >= 0)
                        offers.add(String.valueOf(offer.get("id")));
                }
            } else if ("combat_reward".equals(screen) || "rewards".equals(screen)
                    || "boss_relic".equals(screen)) {
                for (Object relic : list(details.get("relics")))
                    offers.add(String.valueOf(relic));
            }
        }
        void invalidate() { complete = false; }
        boolean complete() { return complete; }
        List<String> snapshot() { return new ArrayList<>(offers); }
    }

    static String rewardIdentity(Object reward) {
        return rewardIdentity(reward, AbstractDungeon.player, AbstractDungeon.currMapNode);
    }

    static String rewardIdentity(Object reward, Object player, Object node) {
        if (rewardPlayer != player || rewardNode != node) {
            rewardIdentities.clear();
            rewardPlayer = player;
            rewardNode = node;
        }
        String identity = rewardIdentities.get(reward);
        if (identity == null) {
            identity = "reward-" + (++nextRewardIdentity);
            rewardIdentities.put(reward, identity);
        }
        return identity;
    }
    private LiveOocCapture() {}

    static String capture() {
        if (AbstractDungeon.player == null || AbstractDungeon.currMapNode == null
                || AbstractDungeon.isFadingIn || AbstractDungeon.isFadingOut) return null;
        // waitingOnFadeOut is a legacy latch: vanilla sets it at the first
        // room transition and never clears it until a dungeon constructor.
        // It is not a live animation/readiness signal. Use the actual fading
        // flags above and MCP's command-ready state below.
        Map<String,Object> out = object("schemaVersion", 1, "screen", "unknown");
        try {
            // Use only the MCP mod's read-only screen converters. This avoids
            // maintaining a second subtly different ordering of legal choices.
            Map<String,Object> state = map(call("mcpthespire.GameStateConverter", "getScreenOnlyState"));
            if (!Boolean.TRUE.equals(state.get("ready_for_command"))) return null;
            String type = String.valueOf(state.get("screen_type"));
            if ("NONE".equals(type) && "COMBAT".equals(state.get("room_phase"))) return null;
            out.put("mcpState", state);
            out.put("screen", canonicalScreen(type));
            // Correlation survives a later unsupported optional projection.
            Map<String,Object> core = object("character", AbstractDungeon.player.chosenClass.name(),
                    "ascension", AbstractDungeon.ascensionLevel, "act", AbstractDungeon.actNum,
                    "floor", AbstractDungeon.floorNum, "hp", AbstractDungeon.player.currentHealth,
                    "maxHp", AbstractDungeon.player.maxHealth, "gold", AbstractDungeon.player.gold);
            out.put("publicState", core);
            List<Map<String,Object>> choices = new ArrayList<>();
            out.put("liveChoices", choices);
            boolean freshRun = AbstractDungeon.floorNum == 0
                    && CardCrawlGame.metricData != null
                    && CardCrawlGame.metricData.path_taken != null
                    && CardCrawlGame.metricData.path_taken.isEmpty();
            if (freshRun) combatClassHistory.resetForFreshRun(
                    AbstractDungeon.player, Settings.seed, AbstractDungeon.actNum);
            capturePublicState(core);
            List<?> labels = list(call(CHOICES, "getCurrentChoiceList"));
            switch (type) {
                case "CARD_REWARD": cardReward(out, choices, labels); break;
                case "COMBAT_REWARD": rewards(out, choices, labels); break;
                case "REST": rest(out, choices, labels); break;
                case "MAP": mapScreen(out, choices, labels); break;
                case "SHOP_SCREEN": shop(out, choices, labels); break;
                case "GRID": selector(out, choices, labels); break;
                case "BOSS_REWARD": boss(out, choices, labels); break;
                case "CHEST": treasure(out, choices, labels); break;
                case "EVENT": event(out, choices, labels); break;
                default:
                    out.put("screen", type.toLowerCase(java.util.Locale.ROOT));
                    out.put("unsupportedReason", "NATIVE_SCREEN_UNSUPPORTED:" + type);
            }
            if ("map".equals(out.get("screen")) && activeWingBoots(core))
                unsupported(out, "RELIC_NATIVE_STATE_UNREPRESENTABLE:WingedGreaves:active");
            RelicOfferRecorder.observe();
            core.put("seenRelics", seenRelicOffers.snapshot());
            core.put("seenRelicsComplete", RelicOfferRecorder.projectionComplete());
            finalizeSupportReason(out);
        } catch (ReflectiveOperationException | RuntimeException failure) {
            combatClassHistory.invalidate();
            recordCaptureError(out, failure);
        }
        return JSON.toJson(out);
    }

    static void finalizeSupportReason(Map<String,Object> observation) {
        if (observation.containsKey("unsupportedReason")) return;
        Map<String,Object> publicState = map(observation.get("publicState"));
        if (!Boolean.TRUE.equals(publicState.get("pathComplete")))
            observation.put("unsupportedReason", "PATH_HISTORY_UNAVAILABLE");
        else if (publicState.containsKey("unsupportedReason"))
            observation.put("unsupportedReason", publicState.get("unsupportedReason"));
        else observation.put("unsupportedReason", "");
    }

    static void recordCaptureError(Map<String,Object> observation, Exception failure) {
        // An unexpected capture failure is an integrity error, never permission
        // for the driver to fall back. Preserve all correlation fields already
        // obtained so the failure packet identifies the exact live boundary.
        observation.put("captureError", failure.getClass().getSimpleName()
                + ":" + String.valueOf(failure.getMessage()));
    }

    private static void capturePublicState(Map<String,Object> p) throws ReflectiveOperationException {
        p.putAll(object("character", AbstractDungeon.player.chosenClass.name(),
                "ascension", AbstractDungeon.ascensionLevel, "act", AbstractDungeon.actNum,
                "floor", AbstractDungeon.floorNum, "hp", AbstractDungeon.player.currentHealth,
                "maxHp", AbstractDungeon.player.maxHealth, "gold", AbstractDungeon.player.gold,
                "blueKey", Settings.hasSapphireKey, "greenKey", Settings.hasEmeraldKey,
                "redKey", Settings.hasRubyKey, "keysEnabled", Settings.isFinalActAvailable,
                "potionCapacity", AbstractDungeon.player.potionSlots,
                "boss", AbstractDungeon.bossKey == null ? "" : AbstractDungeon.bossKey));
        List<Object> deck = new ArrayList<>();
        for (AbstractCard c : AbstractDungeon.player.masterDeck.group) deck.add(card(c));
        p.put("deck", deck);
        List<Object> relics = new ArrayList<>();
        for (AbstractRelic r : AbstractDungeon.player.relics)
            relics.add(object("id", r.relicId, "data", nativeRelicData(r.relicId, r.counter, r.usedUp, p),
                    "liveCounter", r.counter, "usedUp", r.usedUp));
        p.put("relics", relics);
        List<String> potions = new ArrayList<>();
        if (AbstractDungeon.player.potionSlots > 5 || AbstractDungeon.player.potions.size() > 5)
            unsupported(p, "NATIVE_POTION_CAPACITY_EXCEEDED");
        for (int i = 0; i < Math.max(5, AbstractDungeon.player.potions.size()); ++i) potions.add(i < AbstractDungeon.player.potions.size()
                ? AbstractDungeon.player.potions.get(i).ID : "Potion Slot");
        p.put("potions", potions);
        List<Object> nodes = new ArrayList<>();
        int burningX = -1, burningY = -1;
        if (AbstractDungeon.map != null) for (List<MapRoomNode> row : AbstractDungeon.map)
            for (MapRoomNode n : row) {
                if (n.y < 0 || n.y > 14) continue;
                List<Integer> edges = new ArrayList<>();
                for (MapEdge edge : n.getEdges()) {
                    int childX = AbstractDungeon.actNum == 4 ? edge.dstX
                            : nativeEdgeDestination(n.y, edge.dstX, edge.dstY);
                    if (!edges.contains(childX)) edges.add(childX);
                }
                if (n.hasEmeraldKey) { burningX = n.x; burningY = n.y; }
                // getMapSymbol retains '?' for converted event rooms, matching
                // native immutable map nodes and avoiding future encounter data.
                nodes.add(object("x", n.x, "y", n.y, "room", roomSymbol(n.room == null
                        ? null : n.room.getMapSymbol()), "edges", edges));
            }
        if (AbstractDungeon.actNum == 4 || nodes.size() != 105)
            unsupported(p, "VISIBLE_MAP_UNREPRESENTABLE:ACT_" + AbstractDungeon.actNum);
        p.put("map", object("x", AbstractDungeon.currMapNode.x, "y", AbstractDungeon.currMapNode.y,
                "burningEliteX", burningX, "burningEliteY", burningY, "nodes", nodes));
        int[] visits = new int[10];
        List<String> path = CardCrawlGame.metricData == null ? null : CardCrawlGame.metricData.path_taken;
        boolean exact = path != null && (AbstractDungeon.floorNum == 0 || !path.isEmpty());
        if (path != null && path.size() < AbstractDungeon.floorNum - 2 * AbstractDungeon.actNum)
            exact = false; // Missing persisted earlier-act history, never invent zeroes.
        // Damage history identifies completed boss floors publicly. Read it
        // before path normalization so a persisted boss-transition marker can
        // be qualified after entering the next act.
        List<Integer> combatFloors = new ArrayList<>();
        if (CardCrawlGame.metricData != null) {
            for (Object raw : CardCrawlGame.metricData.damage_taken) {
                Object floor = map(raw).get("floor");
                if (floor instanceof Number) combatFloors.add(((Number) floor).intValue());
                else exact = false;
            }
        } else {
            exact = false;
        }
        p.put("combatFloors", combatFloors);
        int combatActStart = AbstractDungeon.actNum <= 1 ? 0 : AbstractDungeon.actNum == 2 ? 17
                : AbstractDungeon.actNum == 3 ? 34 : 51;
        List<Integer> currentActCombatFloors = new ArrayList<>();
        for (int floor : combatFloors)
            if (floor > combatActStart && floor <= AbstractDungeon.floorNum)
                currentActCombatFloors.add(floor);
        p.put("combatHistory", combatClassHistory.snapshot());
        p.put("combatHistoryComplete", combatClassHistory.completeFor(currentActCombatFloors));
        // At the act-boss transition vanilla can leave one non-room sentinel
        // at the end of metricData.path_taken. It is not a missing historical
        // room: the current MapRoomNode is row 15, above the visible map.
        // Omit only that exact trailing sentinel; all other unknown symbols
        // remain fail-closed.
        boolean bossTransitionSentinel = AbstractDungeon.currMapNode.y == 15;
        String inferredBossPrecedingRoom = "";
        if (bossTransitionSentinel && AbstractDungeon.currMapNode.getParents() != null) {
            for (MapRoomNode parent : AbstractDungeon.currMapNode.getParents()) {
                if (parent != null && parent.room != null) {
                    String candidate = roomSymbol(parent.room.getMapSymbol());
                    if (!"INVALID".equals(candidate)) {
                        inferredBossPrecedingRoom = candidate;
                        break;
                    }
                }
            }
        }
        if (bossTransitionSentinel && inferredBossPrecedingRoom.isEmpty()
                && AbstractDungeon.pathX != null && AbstractDungeon.pathY != null
                && AbstractDungeon.pathX.size() == AbstractDungeon.pathY.size()) {
            for (int i = AbstractDungeon.pathX.size() - 1; i >= 0; --i) {
                int x = AbstractDungeon.pathX.get(i), y = AbstractDungeon.pathY.get(i);
                if (AbstractDungeon.map == null || y < 0 || y >= AbstractDungeon.map.size()) continue;
                List<MapRoomNode> row = AbstractDungeon.map.get(y);
                if (row == null || x < 0 || x >= row.size() || row.get(x) == null
                        || row.get(x).room == null) continue;
                String candidate = roomSymbol(row.get(x).room.getMapSymbol());
                if (!"INVALID".equals(candidate)) {
                    inferredBossPrecedingRoom = candidate;
                    break;
                }
            }
        }
        List<String> canonicalPathHistory = path == null ? new ArrayList<>()
                : canonicalPathHistory(path, bossTransitionSentinel,
                        inferredBossPrecedingRoom, AbstractDungeon.actNum, combatFloors);
        for (String canonical : canonicalPathHistory) {
            int idx = Arrays.asList("SHOP", "REST", "EVENT", "ELITE", "MONSTER", "TREASURE",
                    "BOSS", "BOSS_TREASURE", "NONE", "INVALID").indexOf(canonical);
            if (idx >= 0 && idx < 6) ++visits[idx];
            else if (idx != 6 && idx != 7 && idx != 8) exact = false;
        }
        p.put("pathVisits", visits);
        p.put("pathHistory", canonicalPathHistory);
        p.put("pathComplete", exact);
        int[] actVisits = new int[10];
        int actStartFloor = AbstractDungeon.actNum <= 1 ? 0 : AbstractDungeon.actNum == 2 ? 17
                : AbstractDungeon.actNum == 3 ? 34 : 51;
        int currentActRooms = Math.max(0, AbstractDungeon.floorNum - actStartFloor);
        if (path != null) for (String symbol : path.subList(Math.max(0, path.size() - currentActRooms), path.size())) {
            int idx = Arrays.asList("SHOP", "REST", "EVENT", "ELITE", "MONSTER", "TREASURE",
                    "BOSS", "BOSS_TREASURE", "NONE", "INVALID").indexOf(roomSymbol(symbol));
            if (idx >= 0 && idx < 6) ++actVisits[idx];
        }
        p.put("currentActPathVisits", actVisits);
        QuestionRoomHistory questions = QuestionRoomHistory.capture(path,
                CardCrawlGame.metricData == null ? null : CardCrawlGame.metricData.path_per_floor,
                AbstractDungeon.actNum, AbstractDungeon.floorNum,
                QuestionRoomHistory.roomOutcome(AbstractDungeon.getCurrRoom().getClass().getSimpleName()));
        p.put("questionOutcomes", questions.outcomes);
        p.put("questionHistoryComplete", exact && questions.complete
                && questions.outcomes.size() == actVisits[2]);
        List<String> acquiredRelics = new ArrayList<>();
        List<String> priorEvents = new ArrayList<>();
        int shopRemovals = 0;
        if (CardCrawlGame.metricData != null) {
            for (Object raw : CardCrawlGame.metricData.relics_obtained) {
                Object key = map(raw).get("key");
                if (key != null && !acquiredRelics.contains(String.valueOf(key))) acquiredRelics.add(String.valueOf(key));
            }
            for (Object raw : CardCrawlGame.metricData.event_choices) {
                Map<String,Object> event = map(raw);
                Object name = event.get("event_name");
                if (name != null) {
                    String eventId=canonicalEventId(String.valueOf(name));
                    if (!priorEvents.contains(eventId)) priorEvents.add(eventId);
                }
                for (String key : Arrays.asList("relics_obtained", "relics_lost")) {
                    Object values = event.get(key);
                    if (values instanceof List) for (Object relic : (List<?>)values)
                        if (!acquiredRelics.contains(String.valueOf(relic))) acquiredRelics.add(String.valueOf(relic));
                }
            }
            shopRemovals = CardCrawlGame.metricData.purchased_purges;
        }
        for (AbstractRelic relic : AbstractDungeon.player.relics)
            if (!acquiredRelics.contains(relic.relicId)) acquiredRelics.add(relic.relicId);
        p.put("acquiredRelics", acquiredRelics);
        // Vanilla metrics omit offered-but-skipped relics. The in-session
        // observer fills these only after a fresh-run boundary has been seen.
        p.put("seenRelics", new ArrayList<String>());
        p.put("seenRelicsComplete", false);
        p.put("priorEvents", priorEvents);
        p.put("shopRemoveCount", shopRemovals);
    }

    static String canonicalEventId(String liveId) {
        // The native save mapping spells Neow differently from the Java class.
        if ("NEOW".equals(liveId)) return "Neow";
        if ("Match and Keep!".equals(liveId)) return "Match and Keep";
        if ("SensoryStone".equals(liveId)) return "Sensory Stone";
        return liveId;
    }

    static boolean simpleInitialEventSupported(String simple) {
        return Arrays.asList("BigFish", "GoldShrine",
                "LivingWall", "Sssserpent", "Mushrooms", "TheLibrary",
                "TheMausoleum", "MysteriousSphere", "SecretPortal", "FountainOfCurseRemoval", "UpgradeShrine",
                "PurificationShrine", "Transmogrifier", "Duplicator", "Bonfire", "TheJoust",
                "WomanInBlue").contains(simple);
    }

    static String canonicalScreen(String type) {
        switch (type) {
            case "SHOP_SCREEN": return "shop";
            case "GRID": return "selector";
            case "BOSS_REWARD": return "boss_relic";
            case "CHEST": return "treasure";
            default: return type.toLowerCase(java.util.Locale.ROOT);
        }
    }

    static int nativeEdgeDestination(int sourceY, int destinationX, int destinationY) {
        if (sourceY >= 0 && sourceY < 14 && destinationY == sourceY + 1
                && destinationX >= 0 && destinationX < 7) return destinationX;
        // Vanilla MapGenerator._createPaths places the visual boss two rows
        // above row 14 (dstX=3,dstY=16). Native Map::createPathsIteration stores
        // exactly the same terminal connection as row14.addEdge(3).
        if (sourceY == 14 && destinationX == 3 && destinationY == 16) return 3;
        throw new IllegalArgumentException("nonadjacent map edge " + sourceY + "->"
                + destinationX + "," + destinationY);
    }

    private static final List<String> PERSISTENT_RELIC_COUNTERS = Arrays.asList(
            "Happy Flower", "Incense Burner", "InkBottle", "Inserter", "Nunchaku", "Pen Nib", "Sundial",
            "NeowsBlessing", "Omamori", "Girya", "Tiny Chest", "WingedGreaves");

    private static void unsupported(Map<String,Object> state, String reason) {
        if (!state.containsKey("unsupportedReason")) state.put("unsupportedReason", reason);
    }

    static int nativeRelicData(String id, int counter, boolean usedUp, Map<String,Object> state) {
        if ("WingedGreaves".equals(id)) {
            // Java's counter is the public remaining-use count. Native relic
            // feature encoding has always represented Wing Boots as data=0;
            // the live importer carries the counter in a separate field.
            return 0;
        }
        if ("NeowsBlessing".equals(id) || "Omamori".equals(id)) {
            // Spent Java -2 is native 0 remaining charges; the CTM rejects
            // negative charge data. Share the combat-entry mapping.
            return STSModelInspector.combatEntryRelicData(id, counter, usedUp);
        }
        if ("MawBank".equals(id)) {
            // Java tests usedUp and writes counter=-2 on spending; native
            // obtainRelic starts at 1, loseGold(inShop) writes 0.
            return usedUp ? 0 : 1;
        }
        if ("Lizard Tail".equals(id)) {
            // Java uses usedUp/-2; native obtainRelic and revival use 1/0.
            return usedUp || counter == -2 ? 0 : 1;
        }
        if ("Matryoshka".equals(id) || "NlothsMask".equals(id)) {
            // Both games decrement the remaining chest charges. Vanilla's
            // setCounter(-2) marks the exhausted relic instead of retaining 0.
            int max = "Matryoshka".equals(id) ? 2 : 1;
            if (!usedUp && counter != -2 && (counter < 0 || counter > max))
                unsupported(state, "RELIC_NATIVE_STATE_UNREPRESENTABLE:" + id + ":counter");
            return usedUp || counter == -2 ? 0 : counter;
        }
        if (counter > 0 && !PERSISTENT_RELIC_COUNTERS.contains(id))
            unsupported(state, "RELIC_NATIVE_COUNTER_UNQUALIFIED:" + id);
        // Nonpositive counters have the same V4 token encoding as native zero.
        // Known persistent counters are copied exactly, never reconstructed.
        return counter;
    }

    private static boolean activeWingBoots(Map<String,Object> state) {
        for (Object raw : list(state.get("relics"))) {
            Map<String,Object> relic = map(raw);
            if ("WingedGreaves".equals(relic.get("id"))
                    && relic.get("liveCounter") instanceof Number
                    && ((Number)relic.get("liveCounter")).intValue() > 0)
                return true;
        }
        return false;
    }

    static Map<String,Object> card(AbstractCard c) throws ReflectiveOperationException {
        int binding = c.inBottleFlame ? 0 : c.inBottleLightning ? 1 : c.inBottleTornado ? 2 : -1;
        return object("id", c.cardID, "upgraded", c.upgraded, "misc", "Searing Blow".equals(c.cardID) ? c.timesUpgraded : c.misc,
                "bottleBinding", binding, "uuid", String.valueOf(c.uuid));
    }
    private static List<Object> cards(List<AbstractCard> cs) throws ReflectiveOperationException {
        List<Object> result = new ArrayList<>();
        for (AbstractCard c : cs) result.add(card(c));
        return result;
    }
    private static Map<String,Object> emptyRewards() {
        return object("cardRewards", new ArrayList<>(), "gold", new ArrayList<>(),
                "relics", new ArrayList<>(), "potions", new ArrayList<>(),
                "emeraldKey", false, "sapphireKey", false);
    }
    private static boolean hasPotionSlot() {
        int occupied = 0;
        int capacity = AbstractDungeon.player.potionSlots;
        for (int i = 0; i < capacity && i < AbstractDungeon.player.potions.size(); ++i) {
            if (AbstractDungeon.player.potions.get(i) != null
                    && !"Potion Slot".equals(AbstractDungeon.player.potions.get(i).ID)) ++occupied;
        }
        return occupied < capacity;
    }
    private static void cardReward(Map<String,Object> out, List<Map<String,Object>> cs, List<?> labels)
            throws ReflectiveOperationException {
        out.put("screen", "card_reward");
        if (AbstractDungeon.cardRewardScreen.rItem != null)
            out.put("rewardIdentity", rewardIdentity(AbstractDungeon.cardRewardScreen.rItem));
        Map<String,Object> r = emptyRewards();
        List<AbstractCard> offered = AbstractDungeon.cardRewardScreen.rewardGroup;
        mutableList(r.get("cardRewards")).add(cards(offered)); out.put("details", r);
        for (int i = 0; i < offered.size(); ++i) add(cs, labels, i, "card", i, 0);
        boolean bowl = Boolean.TRUE.equals(call(CHOICES, "isBowlAvailable"));
        if (bowl) add(cs, labels, offered.size(), "card", 5, 0);
        else if (Boolean.TRUE.equals(call(CHOICES, "isCardRewardSkipAvailable")))
            button(cs, "skip", "card", 5, 0);
        // The native global skip has the same current-screen effect as skip.
        if (Boolean.TRUE.equals(call(CHOICES, "isCardRewardSkipAvailable")))
            button(cs, "skip", "skip", 0, 0);
        else out.put("unsupportedReason", "CARD_REWARD_SKIP_UNAVAILABLE");
    }
    private static void rewards(Map<String,Object> out, List<Map<String,Object>> cs, List<?> labels)
            throws ReflectiveOperationException {
        out.put("screen", "combat_reward");
        Map<String,Object> r = emptyRewards(); out.put("details", r);
        List<Object> occurrences = new ArrayList<>(); out.put("rewardOccurrences", occurrences);
        List<RewardItem> offered = AbstractDungeon.combatRewardScreen.rewards;
        for (int i = 0; i < offered.size(); ++i) {
            RewardItem reward = offered.get(i);
            String kind = reward.type.name();
            occurrences.add(object("index", i, "type", kind, "identity", rewardIdentity(reward)));
            if ("CARD".equals(kind)) {
                // The unopened reward icon reveals only its type. Vanilla
                // has already generated reward.cards, but those identities
                // are not yet public and must never enter this observation.
                out.put("unsupportedReason", "CARD_GROUP_NOT_REVEALED");
            } else if ("GOLD".equals(kind) || "STOLEN_GOLD".equals(kind)) {
                int idx = list(r.get("gold")).size();
                mutableList(r.get("gold")).add(reward.goldAmt + reward.bonusGold);
                add(cs, labels, i, "gold", idx, 0);
            } else if ("RELIC".equals(kind)) {
                int idx = list(r.get("relics")).size(); mutableList(r.get("relics")).add(reward.relic.relicId);
                add(cs, labels, i, "relic", idx, 0);
            } else if ("POTION".equals(kind)) {
                int idx = list(r.get("potions")).size(); mutableList(r.get("potions")).add(reward.potion.ID);
                if (hasPotionSlot()) add(cs, labels, i, "potion", idx, 0);
            } else if ("EMERALD_KEY".equals(kind) || "SAPPHIRE_KEY".equals(kind)) {
                r.put("EMERALD_KEY".equals(kind) ? "emeraldKey" : "sapphireKey", true);
                add(cs, labels, i, "key", 0, 0);
            } else out.put("unsupportedReason", "REWARD_TYPE_UNREPRESENTABLE:" + kind);
        }
        addPotionDiscards(cs,!list(r.get("potions")).isEmpty());
        button(cs, "proceed", "skip", 0, 0);
    }
    private static void addPotionDiscards(List<Map<String,Object>> choices,boolean refillAvailable) {
        List<String> held=new ArrayList<>();
        for(com.megacrit.cardcrawl.potions.AbstractPotion potion:AbstractDungeon.player.potions)
            held.add(potion==null?null:potion.ID);
        capturePotionDiscards(choices,held,AbstractDungeon.player.potionSlots,refillAvailable,
                AbstractDungeon.player.hasRelic("Sozu"));
    }
    static void capturePotionDiscards(List<Map<String,Object>> choices,List<String> held,int capacity,
            boolean refillAvailable,boolean sozu) {
        if(!refillAvailable||sozu||capacity<1||capacity>5||held.size()<capacity)return;
        for(int i=0;i<capacity;++i)
            if(held.get(i)==null||held.get(i).isEmpty()||"Potion Slot".equals(held.get(i)))return;
        for(int i=0;i<capacity;++i)choices.add(object("nativeAction",object("kind","discard_potion","index",i,"group",0),
                "liveAction",object("kind","discard_potion","potionSlot",i+1)));
    }
    private static void rest(Map<String,Object> out, List<Map<String,Object>> cs, List<?> labels)
            throws ReflectiveOperationException {
        out.put("screen", "rest");
        List<?> buttons = list(call(CHOICES, "getValidRestRoomButtons"));
        List<Integer> options = new ArrayList<>();
        List<String> types = Arrays.asList("RestOption", "SmithOption", "RecallOption", "LiftOption", "TokeOption", "DigOption");
        for (int i = 0; i < buttons.size(); ++i) {
            int index = types.indexOf(buttons.get(i).getClass().getSimpleName());
            if (index < 0) throw new IllegalArgumentException("unknown campfire option");
            options.add(index); add(cs, labels, i, "option", index, 0);
        }
        if (buttons.isEmpty()) { options.add(6); button(cs, "proceed", "option", 6, 0); }
        out.put("details", object("options", options));
    }
    private static void mapScreen(Map<String,Object> out, List<Map<String,Object>> cs, List<?> labels)
            throws ReflectiveOperationException {
        out.put("screen", "map");
        out.put("details", object());
        List<?> nodes = list(call(CHOICES, "getMapScreenNodeChoices"));
        if (Boolean.TRUE.equals(call(CHOICES, "bossNodeAvailable"))) {
            if (captureForcedBossMap(out, cs, labels, AbstractDungeon.actNum,
                    AbstractDungeon.getCurrMapNode().y, nodes.size())) return;
            add(cs, labels, 0, "option", 0, 0); return;
        }
        for (int i = 0; i < nodes.size(); ++i) {
            MapRoomNode n = (MapRoomNode) nodes.get(i);
            Map<String,Object> c = add(cs, labels, i, "option", n.x, 0);
            c.put("x", n.x); c.put("y", n.y);
        }
    }
    private static void selector(Map<String,Object> out, List<Map<String,Object>> cs, List<?> labels)
            throws ReflectiveOperationException {
        out.put("screen", "selector");
        boolean upgrade = AbstractDungeon.gridSelectScreen.forUpgrade;
        if (AbstractDungeon.gridSelectScreen.confirmScreenUp || AbstractDungeon.gridSelectScreen.isJustForConfirming) {
            if (captureSelectorConfirmation(out, cs, labels,
                    AbstractDungeon.gridSelectScreen.isJustForConfirming,
                    AbstractDungeon.gridSelectScreen.confirmScreenUp)) return;
            if (AbstractDungeon.gridSelectScreen.confirmScreenUp && !AbstractDungeon.gridSelectScreen.isJustForConfirming) {
                List<Object> targets = new ArrayList<>();
                for (Object raw : list(call(CHOICES, "getGridScreenCards"))) {
                    AbstractCard c = (AbstractCard) raw;
                    targets.add(object("deckIndex", AbstractDungeon.player.masterDeck.group.indexOf(c),
                            "uuid", String.valueOf(c.uuid), "card", card(c)));
                }
                Object hovered = field(AbstractDungeon.gridSelectScreen, "hoveredCard");
                int preview = AbstractDungeon.player.masterDeck.group.indexOf(hovered);
                if (captureSelectorPreview(out, cs, labels, targets, String.valueOf(selectorType().get("type")),
                        preview, ((Number)field(AbstractDungeon.gridSelectScreen, "numCards")).intValue(),
                        AbstractDungeon.gridSelectScreen.selectedCards.size())) {
                    captureSelectorContinuation(out);
                    return;
                }
            }
            out.put("unsupportedReason", "SELECTOR_CONFIRMATION_ONLY");
            out.put("details", object("type", upgrade ? "upgrade" : "other", "confirm", true));
            return;
        }
        List<?> offered = list(call(CHOICES, "getGridScreenCards"));
        Map<String,Object> selectorType = selectorType();
        if ("obtain".equals(selectorType.get("type"))) {
            List<Object> cards = new ArrayList<>();
            for (Object raw : offered) {
                AbstractCard c = (AbstractCard)raw;
                if (AbstractDungeon.player.masterDeck.group.contains(c))
                    throw new IllegalArgumentException("library offer is already in master deck");
                cards.add(object("uuid", String.valueOf(c.uuid), "card", card(c)));
            }
            if (!captureLibrarySelector(out, cs, labels, cards,
                    ((Number)field(AbstractDungeon.gridSelectScreen, "numCards")).intValue(),
                    AbstractDungeon.gridSelectScreen.selectedCards.size()))
                out.put("unsupportedReason", "LIBRARY_SELECTOR_UNREPRESENTABLE");
            return;
        }
        List<Integer> selected = new ArrayList<>();
        List<Object> selectionCards = new ArrayList<>();
        for (int i = 0; i < offered.size(); ++i) {
            AbstractCard c = (AbstractCard) offered.get(i);
            // MCP retains selected cards as toggle choices. The native
            // continuation chooses only the remaining picks, so preserve the
            // physical MCP index while assigning a dense native option index.
            if (AbstractDungeon.gridSelectScreen.selectedCards.contains(c)) continue;
            int index = AbstractDungeon.player.masterDeck.group.indexOf(c);
            if (index < 0) throw new IllegalArgumentException("selector card not in master deck");
            Map<String,Object> choice = add(cs, labels, i, "option", selectionCards.size(), 0);
            choice.put("deckIndex", index); choice.put("uuid", String.valueOf(c.uuid));
            selectionCards.add(object("deckIndex", index, "card", card(c)));
        }
        List<Object> selectedCards = new ArrayList<>();
        for (AbstractCard c : AbstractDungeon.gridSelectScreen.selectedCards) {
            int index = AbstractDungeon.player.masterDeck.group.indexOf(c);
            if (index < 0 || selected.contains(index))
                throw new IllegalArgumentException("selected card not uniquely in master deck");
            selected.add(index);
            selectedCards.add(object("deckIndex", index, "card", card(c)));
        }
        boolean confirm = AbstractDungeon.gridSelectScreen.confirmScreenUp;
        out.put("details", object("type", selectorType.get("type"),
                "bottleType", selectorType.getOrDefault("bottleType", ""),
                "requiredPicks", ((Number)field(AbstractDungeon.gridSelectScreen, "numCards")).intValue(),
                "completedPicks", selected.size(), "cards", selectionCards,
                "selectedCards", selectedCards, "selectedDeckIndices", selected, "confirm", confirm));
        captureSelectorContinuation(out);
        if (confirm) out.put("unsupportedReason", "SELECTOR_CONFIRMATION_ONLY");
    }

    private static void captureSelectorContinuation(Map<String,Object> out) throws ReflectiveOperationException {
        Object event=AbstractDungeon.getCurrRoom().event;
        if(event!=null && "Designer".equals(event.getClass().getSimpleName())
                && "DONE".equals(LiveEventCapture.phase(event))
                && "REMOVE_AND_UPGRADE".equals(String.valueOf(field(event,"option")))) {
            map(out.get("details")).put("afterSelect","designer_upgrade");
            map(out.get("details")).put("event","Designer");
            map(out.get("details")).put("eventPhase","DONE");
            map(out.get("details")).put("eventOption","REMOVE_AND_UPGRADE");
        }
    }

    static boolean captureSelectorPreview(Map<String,Object> out, List<Map<String,Object>> choices,
            List<?> labels, List<Object> cards, String type, int previewDeckIndex, int required, int completed) {
        if (!Arrays.asList("upgrade", "remove", "transform", "bonfire").contains(type)
                || required != 1 || completed != 0 || cards.isEmpty() || !labels.isEmpty()
                || previewDeckIndex < 0) return false;
        Map<String,Object> state = map(out.get("mcpState"));
        Object rawChoices = state.get("choice_list");
        if (!"GRID".equals(state.get("screen_type")) || !Boolean.TRUE.equals(state.get("ready_for_command"))
                || !Boolean.TRUE.equals(state.get("can_proceed")) || !Boolean.TRUE.equals(state.get("can_cancel"))
                || (rawChoices != null && (!(rawChoices instanceof List) || !list(rawChoices).isEmpty()))) return false;
        java.util.Set<Object> indices = new java.util.HashSet<>(), uuids = new java.util.HashSet<>();
        for (Object raw : cards) {
            Map<String,Object> entry = map(raw);
            if (!(entry.get("deckIndex") instanceof Integer) || (Integer)entry.get("deckIndex") < 0
                    || !indices.add(entry.get("deckIndex")) || !(entry.get("uuid") instanceof String)
                    || ((String)entry.get("uuid")).isEmpty() || !uuids.add(entry.get("uuid"))
                    || !(entry.get("card") instanceof Map)) return false;
        }
        if (!indices.contains(previewDeckIndex)) return false;
        out.put("details", object("type", type, "selectorPreview", true, "previewDeckIndex", previewDeckIndex,
                "requiredPicks", 1, "completedPicks", 0, "selectedCards", new ArrayList<>(), "cards", cards,
                "confirmScreenUp", true, "isJustForConfirming", false, "confirm", true));
        button(choices, "proceed", "option", 0, 0); button(choices, "cancel", "option", 1, 0);
        out.remove("unsupportedReason");
        return true;
    }

    static boolean captureLibrarySelector(Map<String,Object> out, List<Map<String,Object>> choices,
            List<?> labels, List<Object> cards, int required, int completed) {
        if (required != 1 || completed != 0 || cards.size() != 20 || labels.size() != 20
                || !soleMcpContinuation(out, "GRID", false, 20)) return false;
        java.util.Set<Object> ids = new java.util.HashSet<>(), uuids = new java.util.HashSet<>();
        for (Object raw : cards) {
            Map<String,Object> offer = map(raw), c = map(offer.get("card"));
            if (offer.containsKey("deckIndex") || !(offer.get("uuid") instanceof String)
                    || ((String)offer.get("uuid")).isEmpty() || !uuids.add(offer.get("uuid"))
                    || !(c.get("id") instanceof String) || !ids.add(c.get("id"))) return false;
        }
        out.put("details", object("type", "obtain", "event", "The Library", "phase", 1,
                "requiredPicks", 1, "completedPicks", 0, "selectedCards", new ArrayList<>(),
                "cards", cards, "confirm", false));
        for (int i = 0; i < cards.size(); ++i)
            add(choices, labels, i, "option", i, 0).put("uuid", map(cards.get(i)).get("uuid"));
        return true;
    }

    private static boolean soleMcpContinuation(Map<String,Object> out, String screen,
            boolean proceed, int choiceCount) {
        Object raw = out.get("mcpState");
        if (!(raw instanceof Map)) return false;
        Map<String,Object> state = map(raw);
        Object choices = state.get("choice_list");
        int count = choices == null ? 0 : choices instanceof List ? list(choices).size() : -1;
        return screen.equals(state.get("screen_type"))
                && Boolean.TRUE.equals(state.get("ready_for_command"))
                && Boolean.FALSE.equals(state.get("can_cancel"))
                && Boolean.valueOf(proceed).equals(state.get("can_proceed"))
                && count == choiceCount;
    }

    static boolean captureForcedBossMap(Map<String,Object> out, List<Map<String,Object>> choices,
            List<?> labels, int act, int y, int nodeCount) {
        // bossNodeAvailable alone only checks the map row. A dismissable map
        // may have been opened before finishing the last campfire action.
        if (act < 1 || act > 3 || y != 14 || nodeCount != 0 || labels.size() != 1
                || !soleMcpContinuation(out, "MAP", false, 1)) return false;
        out.put("details", object("mechanicalTransition", "boss_map",
                "bossNodeAvailable", true, "nodeChoices", 0));
        add(choices, labels, 0, "option", 0, 0);
        return true;
    }

    static boolean captureSelectorConfirmation(Map<String,Object> out, List<Map<String,Object>> choices,
            List<?> labels, boolean resultOnly, boolean preview) {
        // Upgrade/remove/transform previews expose Cancel even when canCancel
        // is false. Only a completed result display has no remaining decision.
        if (!resultOnly || preview || !labels.isEmpty()
                || !soleMcpContinuation(out, "GRID", true, 0)) return false;
        out.put("details", object("type", "confirmation", "mechanicalTransition", "selector_confirm",
                "isJustForConfirming", true, "confirmScreenUp", false, "confirm", true));
        button(choices, "proceed", "option", 0, 0);
        return true;
    }

    private static Map<String,Object> selectorType() throws ReflectiveOperationException {
        List<String> owners = new ArrayList<>();
        for (AbstractRelic relic : AbstractDungeon.player.relics) {
            String id = relic.relicId;
            if (Arrays.asList("Bottled Flame", "Bottled Lightning", "Bottled Tornado", "DollysMirror").contains(id)
                    && Boolean.FALSE.equals(field(relic, "cardSelected"))) owners.add(id);
            if ("Astrolabe".equals(id) && Boolean.FALSE.equals(field(relic, "cardsSelected"))) owners.add(id);
        }
        Object event = AbstractDungeon.getCurrRoom().event;
        String eventClass = event == null ? "" : event.getClass().getSimpleName();
        if ("BackToBasics".equals(eventClass)
                && "COMPLETE".equals(String.valueOf(field(event, "screen")))) owners.add("BackToBasics");
        if ("TheLibrary".equals(eventClass) && Integer.valueOf(1).equals(field(event, "screenNum"))
                && Boolean.TRUE.equals(field(event, "pickCard"))) owners.add("TheLibrary");
        if ("NoteForYourself".equals(eventClass) && "COMPLETE".equals(LiveEventCapture.phase(event))
                && Boolean.TRUE.equals(field(event,"cardSelect"))) owners.add("NoteForYourself");
        if ("DrugDealer".equals(eventClass) && "1".equals(LiveEventCapture.phase(event))
                && Boolean.FALSE.equals(field(event,"cardsSelected"))) owners.add("DrugDealer");
        if ("Designer".equals(eventClass) && "DONE".equals(LiveEventCapture.phase(event))
                && "TRANSFORM".equals(String.valueOf(field(event,"option")))) owners.add("DesignerTransform");
        boolean bonfire = "Bonfire".equals(eventClass)
                && "CHOOSE".equals(String.valueOf(field(event, "screen")))
                && Boolean.TRUE.equals(field(event, "cardSelect"));
        boolean duplicator = "Duplicator".equals(eventClass)
                && Integer.valueOf(2).equals(field(event, "screenNum"));
        return selectorType(AbstractDungeon.gridSelectScreen.forUpgrade,
                AbstractDungeon.gridSelectScreen.forPurge, AbstractDungeon.gridSelectScreen.forTransform,
                owners, bonfire, duplicator);
    }

    // Identify the owning vanilla continuation, never localized prompt text.
    // Astrolabe opens an unflagged grid; Bonfire sets forPurge despite having
    // a distinct reward continuation. Relic waiting flags take precedence.
    static Map<String,Object> selectorType(boolean upgrade, boolean purge, boolean transform,
            List<String> owners, boolean bonfire, boolean duplicator) {
        if (owners.size() > 1) return object("type", "other");
        if (owners.size() == 1) {
            if (upgrade || purge || transform) return object("type", "other");
            switch (owners.get(0)) {
                case "Astrolabe": return object("type", "transform_upgrade");
                case "DollysMirror": return object("type", "duplicate");
                case "BackToBasics": return object("type", "remove");
                case "TheLibrary": return object("type", "obtain");
                case "NoteForYourself": return object("type", "remove");
                case "DrugDealer": case "DesignerTransform": return object("type", "transform");
                case "Bottled Flame": return object("type", "bottle", "bottleType", "attack");
                case "Bottled Lightning": return object("type", "bottle", "bottleType", "skill");
                case "Bottled Tornado": return object("type", "bottle", "bottleType", "power");
                default: return object("type", "other");
            }
        }
        if (bonfire) return object("type", !upgrade && purge && !transform ? "bonfire" : "other");
        if (duplicator && !upgrade && !purge && !transform) return object("type", "duplicate");
        if ((upgrade ? 1 : 0) + (purge ? 1 : 0) + (transform ? 1 : 0) > 1)
            return object("type", "other");
        return object("type", upgrade ? "upgrade" : purge ? "remove" : transform ? "transform" : "other");
    }
    private static void boss(Map<String,Object> out, List<Map<String,Object>> cs, List<?> labels) {
        out.put("screen", "boss_relic");
        List<String> relics = new ArrayList<>();
        for (int i = 0; i < AbstractDungeon.bossRelicScreen.relics.size(); ++i) {
            relics.add(AbstractDungeon.bossRelicScreen.relics.get(i).relicId); add(cs, labels, i, "option", i, 0);
        }
        out.put("details", object("relics", relics)); button(cs, "cancel", "option", 3, 0);
    }
    private static void treasure(Map<String,Object> out, List<Map<String,Object>> cs, List<?> labels)
            throws ReflectiveOperationException {
        out.put("screen", "treasure");
        Object chest = field(AbstractDungeon.getCurrRoom(), "chest");
        boolean opened = Boolean.TRUE.equals(field(chest, "isOpen"));
        out.put("details", object("chestType", chest.getClass().getSimpleName(), "opened", opened));
        if (opened) {
            // The completed boss chest exposes only MCP's Proceed button.
            // Publish that actual action so the advisor's native pass-through
            // can validate and return it without reopening the chest.
            captureOpenedTreasure(out, cs,
                    Boolean.TRUE.equals(map(out.get("mcpState")).get("can_proceed")));
        } else {
            if (captureBossChestReveal(out, cs, labels, chest.getClass().getSimpleName(), AbstractDungeon.actNum)) return;
            captureUnopenedTreasure(out, cs, labels, chest.getClass().getSimpleName(),
                    Boolean.TRUE.equals(map(out.get("mcpState")).get("can_proceed")));
        }
    }
    static boolean captureBossChestReveal(Map<String,Object> out, List<Map<String,Object>> choices,
            List<?> labels, String chestType, int act) {
        // BossChest.open calls only CursedKey (a no-op for boss=true) and
        // explicitly excludes Matryoshka. Revealing preserves the later Skip;
        // this is an informational policy, not a claim that Proceed is absent.
        if (!"BossChest".equals(chestType) || act < 1 || act > 3 || labels.size()!=1
                || !soleMcpContinuation(out,"CHEST",true,1)) return false;
        out.put("details",object("chestType","BossChest","opened",false,
                "mechanicalTransition","boss_chest_reveal"));
        add(choices,labels,0,"option",0,0);button(choices,"proceed","option",1,0);
        out.remove("unsupportedReason");return true;
    }
    static void captureUnopenedTreasure(Map<String,Object> out, List<Map<String,Object>> choices,
            List<?> labels, String chestType, boolean canProceed) {
        // Size is visible. Do not read goldReward/relicReward: these are
        // hidden pre-rolls; native MCTS samples their correlated public prior.
        int size = Arrays.asList("SmallChest", "MediumChest", "LargeChest").indexOf(chestType);
        if (size >= 0) map(out.get("details")).put("chestSize", size);
        if (labels.size() == 1) add(choices, labels, 0, "option", 0, 0);
        if (canProceed) button(choices, "proceed", "option", 1, 0);
        if (size < 0) out.put("unsupportedReason", "TREASURE_STATE_UNREPRESENTABLE");
        else if (labels.size() != 1 || !canProceed)
            out.put("unsupportedReason", "TREASURE_ACTIONS_UNREPRESENTABLE");
    }
    static void captureOpenedTreasure(Map<String,Object> out, List<Map<String,Object>> choices,
            boolean canProceed) {
        if (canProceed) button(choices, "proceed", "option", 1, 0);
        else out.put("unsupportedReason", "CHEST_ALREADY_OPEN");
    }
    private static void event(Map<String,Object> out, List<Map<String,Object>> cs, List<?> labels)
            throws ReflectiveOperationException {
        out.put("screen", "event");
        Object event = AbstractDungeon.getCurrRoom().event;
        String simple = event.getClass().getSimpleName();
        String id = canonicalEventId("NeowEvent".equals(simple) ? "NEOW" : String.valueOf(field(event, "ID")));
        Object phase = LiveEventCapture.phase(event);
        List<?> active = list(call(CHOICES, "getActiveEventButtons"));
        List<?> all = list(call(CHOICES, "getEventButtons"));
        List<Object> options = new ArrayList<>();
        for (int i = 0; i < active.size(); ++i) {
            int index = ((Number)field(active.get(i), "slot")).intValue();
            if (index != all.indexOf(active.get(i))) throw new IllegalArgumentException("event slot/order disagreement");
            options.add(object("index", index, "disabled", false));
            add(cs, labels, i, "option", index, 0);
        }
        if ("GremlinWheelGame".equals(simple) && active.isEmpty() && labels.size()==1
                && "INTRO".equals(phase) && Boolean.TRUE.equals(field(event,"startSpin"))
                && Boolean.FALSE.equals(field(event,"buttonPressed"))
                && Float.valueOf(0f).equals(field(event,"bounceTimer"))) {
            // MCP's special Spin click sets buttonPressed; no dialog button
            // exists, and the already rolled result remains private.
            phase="SPIN_READY";
            options.add(object("index",0,"disabled",false));add(cs,labels,0,"option",0,0);
        }
        Map<String,Object> e = object("id", id, "phase", String.valueOf(phase), "options", options, "eventData", 0);
        out.put("event", e);
        out.put("details", object("event", id, "eventData", 0, "phase", 0,
                "upgradeOne", false, "cleanUpIsRemoveCard", false,
                "skillCardDeckIdx", -1, "powerCardDeckIdx", -1, "attackCardDeckIdx", -1,
                "potionIdx", -1, "gold", -1, "cardIdx", -1));
        if("SPIN_READY".equals(phase))map(out.get("details")).putAll(object(
                "startSpin",true,"buttonPressed",false,"bounceTimer",0));
        // Only initial phases with native one-to-one option indices qualify.
        boolean initial = "INTRO".equals(String.valueOf(phase)) || "0".equals(String.valueOf(phase));
        if (!simpleInitialEventSupported(simple) || !initial)
            out.put("unsupportedReason", "EVENT_PHASE_UNREPRESENTABLE:" + id + ":" + phase);
        if ("TheLibrary".equals(simple) && "0".equals(String.valueOf(phase)))
            map(out.get("details")).put("hpAmount0", ((Number)field(event, "healAmt")).intValue());
        if ("TheLibrary".equals(simple) && "1".equals(String.valueOf(phase)))
            captureMechanicalTransition(out, options, "event_leave");
        if ("AccursedBlacksmith".equals(simple) || "BackToBasics".equals(simple))
            captureForgeOrWriting(out, simple, String.valueOf(phase), options,
                    AbstractDungeon.player.masterDeck.getUpgradableCards().size(),
                    CardGroup.getGroupWithoutBottledCards(AbstractDungeon.player.masterDeck.getPurgeableCards()).size());
        if ("GoopPuddle".equals(simple)) {
            captureGoopPuddle(out, String.valueOf(phase), options,
                    ((Number)field(event, "damage")).intValue(),
                    ((Number)field(event, "gold")).intValue(),
                    ((Number)field(event, "goldLoss")).intValue(), AbstractDungeon.player.gold);
        }
        if ("NeowEvent".equals(simple)) {
            List<Object> offers = new ArrayList<>();
            Object rs = optionalField(event, "rewards");
            if (rs instanceof List) for (Object reward : list(rs))
                offers.add(object("type", String.valueOf(field(reward, "type")), "drawback", String.valueOf(field(reward, "drawback"))));
            e.put("neowRewards", offers);
            captureNeowOffers(out, offers, String.valueOf(phase), options);
            captureNeowTransition(out, String.valueOf(phase), options);
        }
        LiveEventCapture.capture(out, event, options, cs);
        MatchGameCapture.capture(out,event,cs,labels);
    }

    // Installed vanilla buttonEffect implementations use these exact phases
    // and slots; result pages merely open the map after their effects settle.
    static void captureForgeOrWriting(Map<String,Object> out, String simple, String phase,
            List<Object> options, int upgradeable, int removable) {
        boolean forge = "AccursedBlacksmith".equals(simple);
        boolean writing = "BackToBasics".equals(simple);
        if (!forge && !writing) return;
        if ((forge && "2".equals(phase)) || (writing && "COMPLETE".equals(phase))) {
            captureMechanicalTransition(out, options, "event_leave");
            return;
        }
        if (!(forge ? "0".equals(phase) : "INTRO".equals(phase)) || (writing && removable < 1)) return;
        int first = forge && upgradeable == 0 ? 1 : 0;
        int count = (forge ? 3 : 2) - first;
        if (options.size() != count) return;
        for (int i = 0; i < count; ++i)
            if (!Integer.valueOf(i + first).equals(map(options.get(i)).get("index"))
                    || !Boolean.FALSE.equals(map(options.get(i)).get("disabled"))) return;
        out.remove("unsupportedReason");
    }

    // GoopPuddle's randomized loss is printed in the visible second option.
    // Capture that amount; never regenerate it from a synthetic RNG state.
    static void captureGoopPuddle(Map<String,Object> out, String phase, List<Object> options,
            int damage, int gold, int goldLoss, int playerGold) {
        if ("RESULT".equals(phase)) {
            captureMechanicalTransition(out, options, "event_leave");
            return;
        }
        if (!"INTRO".equals(phase) || damage != 11 || gold != 75
                || goldLoss < 0 || goldLoss > playerGold || options.size() != 2) return;
        for (int i = 0; i < options.size(); ++i)
            if (!Integer.valueOf(i).equals(map(options.get(i)).get("index"))
                    || !Boolean.FALSE.equals(map(options.get(i)).get("disabled"))) return;
        map(out.get("details")).put("goldLoss", goldLoss);
        out.remove("unsupportedReason");
    }

    // Verified NeowEvent.buttonEffect: 0/1 reveal offers, 99 opens the map.
    // Phase 2 has a real choice; daily/endless phases are deliberately absent.
    static void captureNeowTransition(Map<String,Object> out, String phase, List<Object> options) {
        if (!("0".equals(phase) || "1".equals(phase) || "99".equals(phase))) return;
        captureMechanicalTransition(out, options, "99".equals(phase) ? "event_leave" : "neow_intro");
    }

    private static void captureMechanicalTransition(Map<String,Object> out,
            List<Object> options, String transition) {
        if (options.size() != 1) return;
        Map<String,Object> option = map(options.get(0));
        if (!Integer.valueOf(0).equals(option.get("index"))
                || !Boolean.FALSE.equals(option.get("disabled"))) return;
        map(out.get("details")).put("mechanicalTransition", transition);
        out.remove("unsupportedReason");
    }

    // Both normal and early-death rewards use phase 3. Qualify the complete
    // captured slot mapping before exposing any offer to the native advisor.
    static void captureNeowOffers(Map<String,Object> out, List<Object> offers,
            String phase, List<Object> options) {
        if (!(offers.size() == 2 || offers.size() == 4) || !"3".equals(phase)
                || options.size() != offers.size()) return;
        for (int i = 0; i < options.size(); ++i) {
            Map<String,Object> option = map(options.get(i));
            if (!Integer.valueOf(i).equals(option.get("index"))
                    || !Boolean.FALSE.equals(option.get("disabled"))) return;
        }
        List<Object> nativeOffers = new ArrayList<>();
        for (Object offer : offers)
            nativeOffers.add(object("bonus", map(offer).get("type"), "drawback", map(offer).get("drawback")));
        map(out.get("details")).put("neow", nativeOffers);
        out.remove("unsupportedReason"); out.put("screen", "neow");
    }

    private static void shop(Map<String,Object> out, List<Map<String,Object>> cs, List<?> labels)
            throws ReflectiveOperationException {
        out.put("screen", "shop");
        ShopScreen shop = AbstractDungeon.shopScreen;
        List<?> cardItems = list(call(CHOICES, "getShopScreenCards"));
        List<?> relicItems = list(field(shop, "relics"));
        List<?> potionItems = list(field(shop, "potions"));
        List<Object> cards = new ArrayList<>(Arrays.asList(new Object[7]));
        List<Object> relics = new ArrayList<>(Arrays.asList(new Object[3]));
        List<Object> potions = new ArrayList<>(Arrays.asList(new Object[3]));
        int[] prices = new int[13]; Arrays.fill(prices, -1);
        IdentityShopSlots slots = new IdentityShopSlots(shop);
        for (Object item : cardItems) {
            AbstractCard c = (AbstractCard)item; int idx = slots.index(c);
            if (idx < 0 || idx > 6) throw new IllegalArgumentException("shop card slot lost");
            cards.set(idx, card(c)); prices[idx] = c.price;
        }
        for (Object item : relicItems) {
            StoreRelic r = (StoreRelic)item; int idx = ((Number)field(r, "slot")).intValue();
            if (!r.isPurchased) { relics.set(idx, r.relic.relicId); prices[7 + idx] = r.price; }
        }
        for (Object item : potionItems) {
            StorePotion p = (StorePotion)item; int idx = ((Number)field(p, "slot")).intValue();
            if (!p.isPurchased) { potions.set(idx, p.potion.ID); prices[10 + idx] = p.price; }
        }
        List<Object> cardOffers = new ArrayList<>(), relicOffers = new ArrayList<>(), potionOffers = new ArrayList<>();
        for (int i = 0; i < 7; ++i) cardOffers.add(object("card", cards.get(i), "price", prices[i]));
        for (int i = 0; i < 3; ++i) {
            relicOffers.add(object("id", relics.get(i), "price", prices[7 + i]));
            potionOffers.add(object("id", potions.get(i), "price", prices[10 + i]));
        }
        out.put("details", object("cards", cardOffers, "relics", relicOffers, "potions", potionOffers,
                "removeCost", shop.purgeAvailable ? ShopScreen.actualPurgeCost : -1));
        List<?> available = list(call(CHOICES, "getAvailableShopItems"));
        for (int i = 0; i < available.size(); ++i) {
            Object item = available.get(i);
            if (item instanceof AbstractCard) add(cs, labels, i, "card", slots.index((AbstractCard)item), 0);
            else if (item instanceof StoreRelic) add(cs, labels, i, "relic", ((Number)field(item, "slot")).intValue(), 0);
            else if (item instanceof StorePotion) add(cs, labels, i, "potion", ((Number)field(item, "slot")).intValue(), 0);
            else if (item instanceof String && shop.purgeAvailable) add(cs, labels, i, "remove", 0, 0);
            else throw new IllegalArgumentException("unknown shop choice type");
        }
        boolean affordablePotion=false;
        for(int i=0;i<3;++i)if(prices[10+i]>=0&&prices[10+i]<=AbstractDungeon.player.gold)
            affordablePotion=true;
        addPotionDiscards(cs,affordablePotion);
        button(cs, "cancel", "skip", 0, 0);
    }
    // ShopScreen is reused between rooms, so the owning run/player and node
    // delimit this read-only slot cache. It contains no hidden offers.
    private static Object slotPlayer, slotNode;
    private static final java.util.IdentityHashMap<AbstractCard,Integer> cardSlots = new java.util.IdentityHashMap<>();
    private static final Map<String,Integer> positionSlots = new LinkedHashMap<>();
    private static final class IdentityShopSlots {
        IdentityShopSlots(ShopScreen shop) {
            if (slotPlayer != AbstractDungeon.player || slotNode != AbstractDungeon.currMapNode) {
                cardSlots.clear(); positionSlots.clear();
                slotPlayer = AbstractDungeon.player; slotNode = AbstractDungeon.currMapNode;
                if (shop.coloredCards.size() != 5 || shop.colorlessCards.size() != 2)
                    throw new IllegalArgumentException("resumed shop has no exact slot history");
                for (int i = 0; i < 5; ++i) remember(shop.coloredCards.get(i), i);
                for (int i = 0; i < 2; ++i) remember(shop.colorlessCards.get(i), i + 5);
            }
        }
        private static String position(AbstractCard c) { return c.target_x + ":" + c.target_y; }
        private static void remember(AbstractCard c, int index) {
            cardSlots.put(c, index); positionSlots.put(position(c), index);
        }
        int index(AbstractCard c) {
            Integer known = cardSlots.get(c);
            if (known != null) return known;
            // Courier replacement occupies the original physical offer slot.
            known = positionSlots.get(position(c));
            if (known == null) throw new IllegalArgumentException("shop replacement slot unrepresented");
            remember(c, known); return known;
        }
    }

    private static Map<String,Object> add(List<Map<String,Object>> out, List<?> labels, int choiceIndex,
            String kind, int index, int group) {
        if (choiceIndex < 0 || choiceIndex >= labels.size()) throw new IllegalArgumentException("choice occurrence unavailable");
        Map<String,Object> c = object("choiceIndex", choiceIndex + 1, "mcpLabel", labels.get(choiceIndex),
                "nativeAction", object("kind", kind, "index", index, "group", group),
                "liveAction", object("kind", "choose", "choiceIndex", choiceIndex + 1));
        out.add(c); return c;
    }
    private static void button(List<Map<String,Object>> out, String button, String kind, int index, int group) {
        out.add(object("nativeAction", object("kind", kind, "index", index, "group", group),
                "liveAction", object("kind", button)));
    }
    private static String roomSymbol(String s) {
        if (s == null || "N".equals(s)) return "NONE";
        switch (s) { case "$": return "SHOP"; case "R": return "REST"; case "?": return "EVENT";
            case "E": return "ELITE"; case "M": return "MONSTER"; case "T": return "TREASURE";
            case "B": return "BOSS"; default: return "INVALID"; }
    }
    static List<String> canonicalPathHistory(List<String> raw, boolean bossTransitionSentinel,
            String inferredBossPrecedingRoom, int act, List<Integer> combatFloors) {
        List<String> result = new ArrayList<>();
        for (int i = 0; i < raw.size(); ++i) {
            String symbol = roomSymbol(raw.get(i));
            if ("INVALID".equals(symbol) && bossTransitionSentinel && i == raw.size() - 1) {
                // The current boss-transition sentinel may stand for the
                // preceding visible map room, not for the boss itself.
                symbol = inferredBossPrecedingRoom;
            } else if ("INVALID".equals(symbol)
                    && completedBossMarker(result, act, combatFloors)) {
                symbol = "BOSS";
            }
            result.add(symbol);
        }
        return result;
    }
    private static boolean completedBossMarker(List<String> preceding, int act,
            List<Integer> combatFloors) {
        int completedBosses = 0, roomsSinceBoss = 0;
        for (String symbol : preceding) {
            if ("BOSS".equals(symbol)) { ++completedBosses; roomsSinceBoss = 0; }
            else if (Arrays.asList("SHOP", "REST", "EVENT", "ELITE", "MONSTER", "TREASURE")
                    .contains(symbol)) ++roomsSinceBoss;
            else if (!"NONE".equals(symbol) && !"BOSS_TREASURE".equals(symbol)) return false;
        }
        // A completed act has exactly fifteen public map rooms. The combat
        // metric then confirms the boss floor; arbitrary unknown symbols do
        // not get promoted into a fabricated historical room.
        return completedBosses < act - 1 && roomsSinceBoss == 15
                && combatFloors.contains(16 + 17 * completedBosses);
    }
    private static Map<String,Object> object(Object... entries) {
        Map<String,Object> value = new LinkedHashMap<>();
        for (int i = 0; i < entries.length; i += 2) value.put((String)entries[i], entries[i + 1]);
        return value;
    }
    @SuppressWarnings("unchecked") private static Map<String,Object> map(Object o) { return (Map<String,Object>) o; }
    @SuppressWarnings("unchecked") private static List<Object> mutableList(Object o) { return (List<Object>) o; }
    private static List<?> list(Object o) { return (List<?>) o; }
    private static Object call(String type, String name) throws ReflectiveOperationException {
        Method m = Class.forName(type).getDeclaredMethod(name); m.setAccessible(true); return m.invoke(null);
    }
    private static Object optionalField(Object o, String name) throws ReflectiveOperationException {
        try { return field(o, name); } catch (NoSuchFieldException absent) { return null; }
    }
    private static Object field(Object o, String name) throws ReflectiveOperationException {
        for (Class<?> c = o.getClass(); c != null; c = c.getSuperclass()) {
            try { Field f = c.getDeclaredField(name); f.setAccessible(true); return f.get(o); }
            catch (NoSuchFieldException missing) { /* Check superclass. */ }
        }
        throw new NoSuchFieldException(o.getClass().getName() + "." + name);
    }
}
