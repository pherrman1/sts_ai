package stsmodelinspector;

import com.google.gson.Gson;
import com.megacrit.cardcrawl.cards.AbstractCard;
import com.megacrit.cardcrawl.core.CardCrawlGame;
import com.megacrit.cardcrawl.core.Settings;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.events.exordium.DeadAdventurer;
import com.megacrit.cardcrawl.map.MapEdge;
import com.megacrit.cardcrawl.map.MapRoomNode;
import com.megacrit.cardcrawl.relics.AbstractRelic;
import com.megacrit.cardcrawl.relics.BottledFlame;
import com.megacrit.cardcrawl.relics.BottledLightning;
import com.megacrit.cardcrawl.relics.BottledTornado;
import com.megacrit.cardcrawl.localization.LocalizedStrings;
import com.megacrit.cardcrawl.rewards.RewardItem;
import com.megacrit.cardcrawl.rooms.AbstractRoom;
import com.megacrit.cardcrawl.shop.ShopScreen;
import com.megacrit.cardcrawl.shop.StorePotion;
import com.megacrit.cardcrawl.shop.StoreRelic;
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
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
    private static final SeenRelicOffers seenRelicOffers = new SeenRelicOffers();
    private static final CombatClassHistory combatClassHistory = new CombatClassHistory();
    private static final QuestionHistory questionHistory = new QuestionHistory();
    private static final CardRewardVisits cardRewardVisits = new CardRewardVisits();

    static final class CardRewardVisits {
        private Object player, node;
        private String opened;
        private final LinkedHashSet<String> declined = new LinkedHashSet<>();
        private void scope(Object currentPlayer, Object currentNode) {
            if (player == currentPlayer && node == currentNode) return;
            player = currentPlayer; node = currentNode; opened = null; declined.clear();
        }
        void opened(Object currentPlayer, Object currentNode, String identity) {
            scope(currentPlayer, currentNode);
            opened = identity;
        }
        void parent(Object currentPlayer, Object currentNode, List<String> cardIdentities) {
            scope(currentPlayer, currentNode);
            if (opened != null && cardIdentities.contains(opened)) declined.add(opened);
            opened = null;
        }
        boolean declined(String identity) { return declined.contains(identity); }
    }

    static final class QuestionHistory {
        private long seed = Long.MIN_VALUE;
        private int act = -1;
        private boolean invalid;
        private final List<Map<String,Object>> entries = new ArrayList<>();

        private Path path(long runSeed, int runAct) {
            return Paths.get(System.getProperty("user.home", "."), ".cache",
                    "sts-model-inspector", "question-history", runSeed + "-act" + runAct + ".tsv");
        }
        private void load(long runSeed, int runAct) {
            if (seed == runSeed && act == runAct) return;
            seed = runSeed; act = runAct; invalid = false; entries.clear();
            Path ledger = path(seed, act);
            if (!Files.isRegularFile(ledger)) return;
            try (BufferedReader reader = Files.newBufferedReader(ledger, StandardCharsets.UTF_8)) {
                String line;
                int previous = 0;
                while ((line = reader.readLine()) != null) {
                    String[] fields = line.split("\\t", -1);
                    if (fields.length != 2) throw new IllegalArgumentException("question ledger fields");
                    int floor = Integer.parseInt(fields[0]);
                    if (floor <= previous || !valid(fields[1]))
                        throw new IllegalArgumentException("question ledger order or outcome");
                    entries.add(object("floor", floor, "outcome", fields[1]));
                    previous = floor;
                }
            } catch (IOException | RuntimeException failure) {
                entries.clear(); invalid = true;
            }
        }
        private static boolean valid(String outcome) {
            return Arrays.asList("MONSTER", "SHOP", "TREASURE", "EVENT").contains(outcome);
        }
        private void persist() {
            if (invalid) return;
            Path ledger = path(seed, act);
            try {
                Files.createDirectories(ledger.getParent());
                Path temp = ledger.resolveSibling(ledger.getFileName() + ".tmp");
                try (BufferedWriter writer = Files.newBufferedWriter(temp, StandardCharsets.UTF_8)) {
                    for (Map<String,Object> entry : entries)
                        writer.write(entry.get("floor") + "\t" + entry.get("outcome") + "\n");
                }
                try { Files.move(temp, ledger, java.nio.file.StandardCopyOption.ATOMIC_MOVE,
                        java.nio.file.StandardCopyOption.REPLACE_EXISTING); }
                catch (java.nio.file.AtomicMoveNotSupportedException ignored) {
                    Files.move(temp, ledger, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
                }
            } catch (IOException failure) { invalid = true; }
        }
        void observe(long runSeed, int runAct, int floor, int expectedCount,
                boolean currentQuestion, String roomClass) {
            load(runSeed, runAct);
            if (floor == 0) {
                entries.clear(); invalid = false;
                try {
                    for (int a = 1; a <= 4; ++a) Files.deleteIfExists(path(runSeed, a));
                } catch (IOException failure) { invalid = true; }
                return;
            }
            if (!currentQuestion || invalid) return;
            String outcome = roomClass.startsWith("MonsterRoom") ? "MONSTER"
                    : "ShopRoom".equals(roomClass) ? "SHOP"
                    : roomClass.startsWith("TreasureRoom") ? "TREASURE"
                    : "EventRoom".equals(roomClass) ? "EVENT" : "";
            if (!valid(outcome)) return;
            for (Map<String,Object> entry : entries) {
                if (((Number)entry.get("floor")).intValue() != floor) continue;
                if (!outcome.equals(entry.get("outcome"))) invalid = true;
                return;
            }
            if (entries.size() >= expectedCount
                    || (!entries.isEmpty() && floor <= ((Number)entries.get(entries.size()-1).get("floor")).intValue())) {
                invalid = true; return;
            }
            entries.add(object("floor", floor, "outcome", outcome));
            persist();
        }
        boolean completeFor(int expectedCount) { return !invalid && entries.size() == expectedCount; }
        List<Map<String,Object>> snapshot() { return new ArrayList<>(entries); }
    }

    // The public damage metric records a combat's floor but not whether that
    // combat consumed an encounter queue. Observe the live room class before
    // the fight, and only claim complete current-act history when no earlier
    // current-act combat predates this observer.
    static final class CombatClassHistory {
        private Object player, lastGroup;
        private long seed;
        private int act = -1, lastFloor = -1;
        private boolean complete;
        private boolean restored;
        private final List<Map<String,Object>> entries = new ArrayList<>();

        private Path ledgerPath(long currentSeed, int currentAct) {
            String home = System.getProperty("user.home", ".");
            return Paths.get(home, ".cache", "sts-model-inspector", "combat-history",
                    currentSeed + "-act" + currentAct + ".tsv");
        }

        void resetForFreshRun(Object currentPlayer, long currentSeed, int currentAct) {
            player = currentPlayer; seed = currentSeed; act = currentAct;
            restored = true; lastFloor = -1; lastGroup = null;
            entries.clear(); complete = true;
            try {
                for (int oldAct = 1; oldAct <= 4; ++oldAct)
                    Files.deleteIfExists(ledgerPath(currentSeed, oldAct));
            } catch (IOException ignored) { complete = false; }
        }

        private void restore(Object currentPlayer, long currentSeed, int currentAct) {
            if (restored && player == currentPlayer && seed == currentSeed && act == currentAct) return;
            restored = true;
            player = currentPlayer; seed = currentSeed; act = currentAct; lastFloor = -1;
            entries.clear(); lastGroup = null;
            Path path = ledgerPath(currentSeed, currentAct);
            if (!Files.isRegularFile(path)) return;
            complete = true;
            try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
                String line;
                while ((line = reader.readLine()) != null) {
                    String[] fields = line.split("\\t", -1);
                    if (fields.length != 3) { complete = false; break; }
                    int floor = Integer.parseInt(fields[0]);
                    String kind = fields[1];
                    String encounter = fields[2];
                    if (floor < 1 || kind.isEmpty()
                            || (("NORMAL_QUEUE".equals(kind) || "ELITE_QUEUE".equals(kind))
                                && encounter.isEmpty())) { complete = false; break; }
                    entries.add(object("floor", floor, "kind", kind, "encounter", encounter));
                    lastFloor = Math.max(lastFloor, floor);
                }
            } catch (IOException | NumberFormatException failure) {
                entries.clear(); complete = false;
            }
        }

        private void persist() {
            if (player == null || act < 1 || seed == 0 || !complete) return;
            Path path = ledgerPath(seed, act);
            try {
                Files.createDirectories(path.getParent());
                Path temp = path.resolveSibling(path.getFileName() + ".tmp");
                try (BufferedWriter writer = Files.newBufferedWriter(temp, StandardCharsets.UTF_8)) {
                    for (Map<String,Object> entry : entries)
                        writer.write(entry.get("floor") + "\t" + entry.get("kind") + "\t"
                                + entry.getOrDefault("encounter", "") + "\n");
                }
                try { Files.move(temp, path, java.nio.file.StandardCopyOption.ATOMIC_MOVE,
                        java.nio.file.StandardCopyOption.REPLACE_EXISTING); }
                catch (java.nio.file.AtomicMoveNotSupportedException ignored) {
                    Files.move(temp, path, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
                }
            } catch (IOException ignored) {
                complete = false;
            }
        }

        void observe(Object currentPlayer, long currentSeed, int currentAct, int floor,
                boolean noPriorActCombat, boolean inCombat, Object group, String kind,
                String encounter) {
            if (player != currentPlayer || seed != currentSeed || act != currentAct
                    || floor < lastFloor) {
                player = currentPlayer;
                seed = currentSeed;
                act = currentAct;
                entries.clear();
                lastGroup = null;
                complete = noPriorActCombat;
                restored = false;
            }
            restore(currentPlayer, currentSeed, currentAct);
            lastFloor = floor;
            if (!inCombat) { lastGroup = null; return; }
            // A transition frame may already say COMBAT before vanilla has
            // populated its monster group. Wait for the first real group;
            // missing fights are caught against damage_taken at the next OOC.
            if (group == null) return;
            if (kind == null) {
                complete = false; return;
            }
            if (("NORMAL_QUEUE".equals(kind) || "ELITE_QUEUE".equals(kind))
                    && (encounter == null || encounter.isEmpty())) {
                // Loading a completed combat can expose its room and group
                // before the encounter identity is restored. The floor ledger
                // still catches any fight never observed with an identity.
                return;
            }
            if (group != lastGroup) {
                if (!entries.isEmpty()
                        && ((Number)entries.get(entries.size() - 1).get("floor")).intValue() == floor) {
                    String previousKind = String.valueOf(entries.get(entries.size() - 1).get("kind"));
                    String previousEncounter = String.valueOf(entries.get(entries.size() - 1).getOrDefault("encounter", ""));
                    if (!previousKind.equals(kind) || !previousEncounter.equals(encounter)) {
                        complete = false;
                    }
                } else {
                    entries.add(object("floor", floor, "kind", kind,
                            "encounter", encounter == null ? "" : encounter));
                }
                lastGroup = group;
                persist();
            }
        }
        void invalidate() {
            complete = false;
        }
        boolean completeFor(List<Integer> completedFloors) {
            if (!complete || entries.size() != completedFloors.size()) return false;
            for (int i = 0; i < entries.size(); ++i) {
                if (((Number)entries.get(i).get("floor")).intValue() != completedFloors.get(i))
                    return false;
                String kind = String.valueOf(entries.get(i).get("kind"));
                if (("NORMAL_QUEUE".equals(kind) || "ELITE_QUEUE".equals(kind))
                        && String.valueOf(entries.get(i).getOrDefault("encounter", "")).isEmpty())
                    return false;
            }
            return true;
        }
        List<Map<String,Object>> snapshot() { return new ArrayList<>(entries); }
        void restoreFor(Object currentPlayer, long currentSeed, int currentAct) {
            restore(currentPlayer, currentSeed, currentAct);
        }
    }

    static void observeCombatRoom(AbstractRoom room) {
        if (AbstractDungeon.player == null || room == null) return;
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
                inCombat ? STSModelInspector.encounterName(room) : "");
    }

    static void invalidateCombatRoomHistory() { combatClassHistory.invalidate(); }

    // Only an uninterrupted observation from a fresh Neow boundary can
    // account for skipped offers. A resumed/mid-run observer stays incomplete.
    static final class SeenRelicOffers {
        private Object player;
        private long seed;
        private int lastFloor = -1;
        private boolean complete;
        private final LinkedHashSet<String> offers = new LinkedHashSet<>();

        private Path ledgerPath(long currentSeed) {
            return Paths.get(System.getProperty("user.home", "."), ".cache",
                    "sts-model-inspector", "seen-relic-offers", currentSeed + ".tsv");
        }

        private boolean restore(long currentSeed, int currentFloor) {
            Path path = ledgerPath(currentSeed);
            if (!Files.isRegularFile(path)) return false;
            try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
                String header = reader.readLine();
                if (header == null) return false;
                String[] fields = header.split("\\t", -1);
                if (fields.length != 3 || !"v1".equals(fields[0])) return false;
                int savedFloor = Integer.parseInt(fields[1]);
                if (savedFloor < 0 || savedFloor > currentFloor
                        || (!"0".equals(fields[2]) && !"1".equals(fields[2]))) return false;
                LinkedHashSet<String> restoredOffers = new LinkedHashSet<>();
                String line;
                while ((line = reader.readLine()) != null) {
                    if (line.isEmpty() || line.indexOf('\t') >= 0 || restoredOffers.size() >= 181)
                        return false;
                    restoredOffers.add(line);
                }
                lastFloor = savedFloor;
                complete = "1".equals(fields[2]);
                offers.clear();
                offers.addAll(restoredOffers);
                return true;
            } catch (IOException | NumberFormatException failure) { return false; }
        }

        private void persist() {
            if (player == null) return;
            Path path = ledgerPath(seed);
            try {
                Files.createDirectories(path.getParent());
                Path temp = path.resolveSibling(path.getFileName() + ".tmp");
                try (BufferedWriter writer = Files.newBufferedWriter(temp, StandardCharsets.UTF_8)) {
                    writer.write("v1\t" + lastFloor + "\t" + (complete ? "1" : "0") + "\n");
                    for (String offer : offers) writer.write(offer + "\n");
                }
                try { Files.move(temp, path, java.nio.file.StandardCopyOption.ATOMIC_MOVE,
                        java.nio.file.StandardCopyOption.REPLACE_EXISTING); }
                catch (java.nio.file.AtomicMoveNotSupportedException ignored) {
                    Files.move(temp, path, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
                }
            } catch (IOException failure) { complete = false; }
        }

        void observe(Object currentPlayer, long currentSeed, int floor,
                     boolean freshRun, String screen, Map<String,Object> details) {
            if (player != currentPlayer || seed != currentSeed || floor < lastFloor) {
                player = currentPlayer;
                seed = currentSeed;
                lastFloor = -1;
                complete = freshRun;
                offers.clear();
                if (!freshRun && restore(currentSeed, floor)) {
                    // Preserve offers observed before a process restart.
                }
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
            persist();
        }
        void invalidate() { complete = false; persist(); }
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
            seenRelicOffers.observe(AbstractDungeon.player, Settings.seed,
                    AbstractDungeon.floorNum, freshRun, String.valueOf(out.get("screen")),
                    map(out.getOrDefault("details", object())));
            core.put("seenRelics", seenRelicOffers.snapshot());
            core.put("seenRelicsComplete", seenRelicOffers.complete());
            finalizeSupportReason(out);
        } catch (ReflectiveOperationException | RuntimeException failure) {
            seenRelicOffers.invalidate();
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
        combatClassHistory.restoreFor(AbstractDungeon.player, Settings.seed, AbstractDungeon.actNum);
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
        boolean currentQuestion = !canonicalPathHistory.isEmpty()
                && "EVENT".equals(canonicalPathHistory.get(canonicalPathHistory.size() - 1));
        questionHistory.observe(Settings.seed, AbstractDungeon.actNum, AbstractDungeon.floorNum,
                actVisits[2], currentQuestion, AbstractDungeon.getCurrRoom().getClass().getSimpleName());
        p.put("questionOutcomes", questionHistory.snapshot());
        p.put("questionHistoryComplete", questionHistory.completeFor(actVisits[2]));
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
                if (name != null && !priorEvents.contains(String.valueOf(name))) priorEvents.add(String.valueOf(name));
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
        return "NEOW".equals(liveId) ? "Neow" : liveId;
    }

    static String visibleChestSize(String chestClass) {
        if ("SmallChest".equals(chestClass)) return "SMALL";
        if ("MediumChest".equals(chestClass)) return "MEDIUM";
        if ("LargeChest".equals(chestClass)) return "LARGE";
        return "";
    }

    static int scrapOozeRetryCount(int publicChance, int publicDamage, int ascension) {
        int expectedDamage = ascension >= 15 ? 5 : 3;
        if (publicDamage != expectedDamage || publicChance < 25 || publicChance > 95
                || (publicChance - 25) % 10 != 0)
            throw new IllegalArgumentException("Scrap Ooze public retry state differs from native event");
        return (publicChance - 25) / 10;
    }

    static boolean simpleInitialEventSupported(String simple) {
        return Arrays.asList("BigFish", "Beggar", "GoldenIdolEvent", "ShiningLight", "WeMeetAgain",
                "LivingWall", "Sssserpent", "ScrapOoze", "Mushrooms", "TheLibrary",
                "TheMausoleum", "MysteriousSphere", "SecretPortal", "FountainOfCurseRemoval", "UpgradeShrine",
                "PurificationShrine", "Transmogrifier", "Duplicator", "Bonfire", "TheJoust",
                "WomanInBlue").contains(simple);
    }

    static int deadAdventurerPublicEncounter(Object phase, List<?> labels, List<?> options,
            String body, String[] descriptions, int ascension) {
        if (!"INTRO".equals(String.valueOf(phase)) || labels.size() != 2 || options.size() != 2
                || descriptions.length < 7
                || ((Number)map(options.get(0)).get("index")).intValue() != 0
                || ((Number)map(options.get(1)).get("index")).intValue() != 1
                || !String.valueOf(labels.get(0)).contains("[Search]")
                || !String.valueOf(labels.get(0)).contains((ascension >= 15 ? 35 : 25) + "%")
                || !String.valueOf(labels.get(1)).contains("[Leave]")) return -1;
        for (int encounter = 0; encounter < 3; ++encounter)
            if (body.equals(descriptions[2] + descriptions[3 + encounter] + descriptions[6]))
                return encounter;
        return -1;
    }

    static boolean clericInitialVisible(Object phase, List<?> labels, List<?> options,
                                        int healAmount, int purifyCost, int maxHp, int gold,
                                        int ascension) {
        int expectedCost = ascension >= 15 ? 75 : 50;
        return "0".equals(String.valueOf(phase)) && labels.size() == 3 && options.size() == 3
                && gold >= expectedCost && healAmount == (int)(maxHp * 0.25f)
                && purifyCost == expectedCost
                && ((Number)map(options.get(0)).get("index")).intValue() == 0
                && ((Number)map(options.get(1)).get("index")).intValue() == 1
                && ((Number)map(options.get(2)).get("index")).intValue() == 2
                && String.valueOf(labels.get(0)).contains("[Heal]")
                && String.valueOf(labels.get(0)).contains("35 Gold")
                && String.valueOf(labels.get(0)).contains(Integer.toString(healAmount))
                && String.valueOf(labels.get(1)).contains("[Purify]")
                && String.valueOf(labels.get(1)).contains(purifyCost + " Gold")
                && String.valueOf(labels.get(2)).contains("[Leave]");
    }

    static boolean goopInitialVisible(Object phase, List<?> labels, List<?> options,
                                      int damage, int gain, int goldLoss, int playerGold) {
        return "INTRO".equals(String.valueOf(phase)) && labels.size() == 2 && options.size() == 2
                && ((Number)map(options.get(0)).get("index")).intValue() == 0
                && ((Number)map(options.get(1)).get("index")).intValue() == 1
                && damage == 11 && gain == 75 && goldLoss >= 0 && goldLoss <= playerGold
                && String.valueOf(labels.get(0)).contains(Integer.toString(gain))
                && String.valueOf(labels.get(0)).contains(Integer.toString(damage))
                && String.valueOf(labels.get(1)).contains(Integer.toString(goldLoss));
    }

    static boolean goldShrineInitialVisible(Object phase, List<?> labels, List<?> options,
                                            int goldAmount, int ascension) {
        int expected = ascension >= 15 ? 50 : 100;
        return "INTRO".equals(String.valueOf(phase)) && labels.size() == 3 && options.size() == 3
                && ((Number)map(options.get(0)).get("index")).intValue() == 0
                && ((Number)map(options.get(1)).get("index")).intValue() == 1
                && ((Number)map(options.get(2)).get("index")).intValue() == 2
                && goldAmount == expected
                && String.valueOf(labels.get(0)).contains(Integer.toString(expected))
                && String.valueOf(labels.get(1)).contains("275");
    }

    static boolean nestDecisionVisible(String simple, Object phase, List<?> labels, List<?> options,
            int ascension) {
        if (!"Nest".equals(simple) || !"1".equals(String.valueOf(phase))
                || labels.size() != 2 || options.size() != 2) return false;
        int gold = ascension >= 15 ? 50 : 99;
        return ((Number)map(options.get(0)).get("index")).intValue() == 0
                && ((Number)map(options.get(1)).get("index")).intValue() == 1
                && String.valueOf(labels.get(0)).contains("Obtain " + gold + " Gold")
                && String.valueOf(labels.get(1)).contains("Ritual Dagger")
                && String.valueOf(labels.get(1)).contains("Lose 6 HP");
    }

    static boolean goldenWingInitialVisible(Object phase, List<?> labels, List<?> options,
            boolean canAttack, int damage) {
        if (!"INTRO".equals(String.valueOf(phase)) || damage != 7
                || labels.size() != (canAttack ? 3 : 2) || options.size() != labels.size()) return false;
        int[] expected = canAttack ? new int[]{0, 1, 2} : new int[]{0, 2};
        for (int i = 0; i < expected.length; ++i)
            if (((Number)map(options.get(i)).get("index")).intValue() != expected[i]) return false;
        return String.valueOf(labels.get(0)).contains("Lose 7 HP")
                && String.valueOf(labels.get(labels.size() - 1)).contains("Leave");
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
        if ("MawBank".equals(id)) {
            // Java tests usedUp and writes counter=-2 on spending; native
            // obtainRelic starts at 1, loseGold(inShop) writes 0.
            return usedUp ? 0 : 1;
        }
        if ("Lizard Tail".equals(id)) {
            // Native fresh-run initialization currently differs from Java.
            // Do not silently choose between the raw-save and fresh-run forms.
            if (!usedUp) unsupported(state, "RELIC_NATIVE_STATE_UNREPRESENTABLE:Lizard Tail:active");
            return usedUp ? 0 : counter;
        }
        if ("Matryoshka".equals(id) || "NlothsMask".equals(id)) {
            if (counter > 0)
                unsupported(state, "RELIC_NATIVE_STATE_UNREPRESENTABLE:" + id + ":active");
            return usedUp ? 0 : counter;
        }
        if (counter > 0 && !PERSISTENT_RELIC_COUNTERS.contains(id))
            unsupported(state, "RELIC_NATIVE_COUNTER_UNQUALIFIED:" + id);
        // Nonpositive counters have the same V4 token encoding as native zero.
        // Known persistent counters are copied exactly, never reconstructed.
        return counter;
    }

    private static Map<String,Object> card(AbstractCard c) throws ReflectiveOperationException {
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
                "emeraldKey", false, "sapphireKey", false, "opaqueCardRewardGroups", 0);
    }
    static boolean hasStrategicParentReward(List<String> rewardTypes) {
        for (String kind : rewardTypes)
            if ("RELIC".equals(kind) || "POTION".equals(kind)
                    || "EMERALD_KEY".equals(kind) || "SAPPHIRE_KEY".equals(kind)) return true;
        return false;
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
        if (AbstractDungeon.cardRewardScreen.rItem != null) {
            String identity = rewardIdentity(AbstractDungeon.cardRewardScreen.rItem);
            out.put("rewardIdentity", identity);
            cardRewardVisits.opened(AbstractDungeon.player, AbstractDungeon.currMapNode, identity);
        }
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
        List<String> cardIdentities = new ArrayList<>();
        List<String> rewardTypes = new ArrayList<>();
        for (RewardItem reward : offered)
            { rewardTypes.add(reward.type.name());
              if ("CARD".equals(reward.type.name())) cardIdentities.add(rewardIdentity(reward)); }
        boolean hasUnrevealedCard = false;
        int opaqueCardRewardGroups = 0;
        List<String> visibleTypes = new ArrayList<>();
        for (String kind : rewardTypes)
            if (!"CARD".equals(kind)) visibleTypes.add(kind);
        boolean hasStrategicParentReward = hasStrategicParentReward(visibleTypes);
        cardRewardVisits.parent(AbstractDungeon.player, AbstractDungeon.currMapNode, cardIdentities);
        for (int i = 0; i < offered.size(); ++i) {
            RewardItem reward = offered.get(i);
            String kind = reward.type.name();
            String identity = rewardIdentity(reward);
            occurrences.add(object("index", i, "type", kind, "identity", identity));
            if ("CARD".equals(kind)) {
                // The unopened reward icon reveals only its type. Vanilla
                // has already generated reward.cards, but those identities
                // are not yet public and must never enter this observation.
                if (!cardRewardVisits.declined(identity)) {
                    hasUnrevealedCard = true;
                    ++opaqueCardRewardGroups;
                }
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
        map(out.get("details")).put("opaqueCardRewardGroups", opaqueCardRewardGroups);
        if (hasUnrevealedCard && !hasStrategicParentReward)
            out.put("unsupportedReason", "CARD_GROUP_NOT_REVEALED");
        button(cs, "proceed", "skip", 0, 0);
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
            out.put("unsupportedReason", "SELECTOR_CONFIRMATION_ONLY");
            out.put("details", object("type", upgrade ? "upgrade" : "other", "confirm", true));
            return;
        }
        List<?> offered = list(call(CHOICES, "getGridScreenCards"));
        List<Integer> indices = new ArrayList<>(), selected = new ArrayList<>();
        for (int i = 0; i < offered.size(); ++i) {
            AbstractCard c = (AbstractCard) offered.get(i);
            int index = AbstractDungeon.player.masterDeck.group.indexOf(c);
            if (index < 0) throw new IllegalArgumentException("selector card not in master deck");
            indices.add(index);
            Map<String,Object> choice = add(cs, labels, i, "option", i, 0);
            choice.put("deckIndex", index); choice.put("uuid", String.valueOf(c.uuid));
        }
        for (AbstractCard c : AbstractDungeon.gridSelectScreen.selectedCards)
            selected.add(AbstractDungeon.player.masterDeck.group.indexOf(c));
        boolean confirm = AbstractDungeon.gridSelectScreen.confirmScreenUp;
        List<Object> selectionCards = new ArrayList<>();
        for (int i = 0; i < offered.size(); ++i)
            selectionCards.add(object("deckIndex", indices.get(i), "card", card((AbstractCard)offered.get(i))));
        String bottle = bottleSelectorType((String)field(AbstractDungeon.gridSelectScreen, "tipMsg"), offered);
        out.put("details", object("type", upgrade ? "upgrade" : AbstractDungeon.gridSelectScreen.forPurge ? "remove"
                        : AbstractDungeon.gridSelectScreen.forTransform ? "transform" : bottle,
                "requiredPicks", ((Number)field(AbstractDungeon.gridSelectScreen, "numCards")).intValue(),
                "completedPicks", selected.size(), "cards", selectionCards,
                "selectedDeckIndices", selected, "confirm", confirm));
        if (confirm) out.put("unsupportedReason", "SELECTOR_CONFIRMATION_ONLY");
    }
    private static String bottleSelectorType(String prompt, List<?> offered) {
        if (prompt == null || offered.isEmpty() || AbstractDungeon.player == null) return "other";
        for (AbstractRelic relic : AbstractDungeon.player.relics) {
            AbstractCard.CardType type;
            AbstractCard bound;
            if (relic instanceof BottledFlame) {
                type = AbstractCard.CardType.ATTACK; bound = ((BottledFlame)relic).card;
            } else if (relic instanceof BottledLightning) {
                type = AbstractCard.CardType.SKILL; bound = ((BottledLightning)relic).card;
            } else if (relic instanceof BottledTornado) {
                type = AbstractCard.CardType.POWER; bound = ((BottledTornado)relic).card;
            } else continue;
            if (bound != null || relic.DESCRIPTIONS.length < 2
                    || !bottlePromptMatches(prompt, relic.DESCRIPTIONS[1], relic.name,
                            LocalizedStrings.PERIOD)) continue;
            boolean matching = true;
            for (Object card : offered) if (!(card instanceof AbstractCard)
                    || ((AbstractCard)card).type != type) matching = false;
            if (matching) return "bottle";
        }
        return "other";
    }
    static boolean bottlePromptMatches(String prompt, String description, String relicName, String period) {
        return prompt != null && description != null && relicName != null && period != null
                && prompt.equals(description + relicName + period);
    }
    private static void boss(Map<String,Object> out, List<Map<String,Object>> cs, List<?> labels) {
        out.put("screen", "boss_relic");
        List<String> relics = new ArrayList<>();
        for (int i = 0; i < AbstractDungeon.bossRelicScreen.relics.size(); ++i) {
            relics.add(AbstractDungeon.bossRelicScreen.relics.get(i).relicId); add(cs, labels, i, "option", i, 0);
        }
        // MCPTheSpire advertises Skip for the boss relic screen's fourth option.
        out.put("details", object("relics", relics)); button(cs, "skip", "option", 3, 0);
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
            // Chest size is visible. Gold and relic tier remain hidden and
            // are sampled together by the native root particle.
            String size = visibleChestSize(chest.getClass().getSimpleName());
            if (size.isEmpty()) out.put("unsupportedReason", "TREASURE_STATE_UNREPRESENTABLE:"
                    + chest.getClass().getSimpleName());
            if (!out.containsKey("unsupportedReason"))
                out.put("details", object("chestType", chest.getClass().getSimpleName(),
                        "opened", false, "chestSize", size));
            add(cs, labels, 0, "option", 0, 0);
            button(cs, "proceed", "option", 1, 0);
        }
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
        Object phase = optionalField(event, "screen");
        if (phase == null) phase = optionalField(event, "screenNum");
        List<?> active = list(call(CHOICES, "getActiveEventButtons"));
        List<?> all = list(call(CHOICES, "getEventButtons"));
        List<Object> options = new ArrayList<>();
        for (int i = 0; i < active.size(); ++i) {
            int index = ((Number)field(active.get(i), "slot")).intValue();
            if (index != all.indexOf(active.get(i))) throw new IllegalArgumentException("event slot/order disagreement");
            options.add(object("index", index, "disabled", false));
            int nativeIndex = "GoldenIdolEvent".equals(simple) && "1".equals(String.valueOf(phase))
                    ? index + 2 : index;
            add(cs, labels, i, "option", nativeIndex, 0);
        }
        Map<String,Object> e = object("id", id, "phase", String.valueOf(phase), "options", options, "eventData", 0);
        out.put("event", e);
        out.put("details", object("event", id, "eventData", 0, "phase", 0,
                "upgradeOne", false, "cleanUpIsRemoveCard", false,
                "skillCardDeckIdx", -1, "powerCardDeckIdx", -1, "attackCardDeckIdx", -1,
                "potionIdx", -1, "gold", -1, "cardIdx", -1));
        if ("ShiningLight".equals(simple))
            map(out.get("details")).put("hpAmount0", field(event, "damage"));
        if ("GoldenIdolEvent".equals(simple)) {
            map(out.get("details")).put("hpAmount0", field(event, "damage"));
            map(out.get("details")).put("hpAmount1", field(event, "maxHpLoss"));
            map(out.get("details")).put("phase", ((Number)phase).intValue());
        }
        boolean goldenWing = "GoldenWing".equals(simple)
                && goldenWingInitialVisible(phase, labels, options,
                        Boolean.TRUE.equals(field(event, "canAttack")),
                        ((Number)field(event, "damage")).intValue());
        if ("ScrapOoze".equals(simple) && "0".equals(String.valueOf(phase)))
            map(out.get("details")).put("eventData", scrapOozeRetryCount(
                    ((Number)field(event, "relicObtainChance")).intValue(),
                    ((Number)field(event, "dmg")).intValue(), AbstractDungeon.ascensionLevel));
        boolean goop = false;
        if ("GoopPuddle".equals(simple) && "INTRO".equals(String.valueOf(phase))) {
            int damage = ((Number)field(event, "damage")).intValue();
            int gain = ((Number)field(event, "gold")).intValue();
            int goldLoss = ((Number)field(event, "goldLoss")).intValue();
            goop = goopInitialVisible(phase, labels, options, damage, gain, goldLoss,
                    AbstractDungeon.player.gold);
            if (goop) map(out.get("details")).put("goldLoss", goldLoss);
        }
        boolean goldShrine = "GoldShrine".equals(simple)
                && goldShrineInitialVisible(phase, labels, options,
                        ((Number)field(event, "goldAmt")).intValue(), AbstractDungeon.ascensionLevel);
        boolean cleric = "Cleric".equals(simple)
                && clericInitialVisible(phase, labels, options,
                        ((Number)field(event, "healAmt")).intValue(),
                        ((Number)field(event, "purifyCost")).intValue(),
                        AbstractDungeon.player.maxHealth, AbstractDungeon.player.gold,
                        AbstractDungeon.ascensionLevel);
        if (cleric) map(out.get("details")).put("hpAmount0", field(event, "healAmt"));
        int deadAdventurerEncounter = "DeadAdventurer".equals(simple)
                ? deadAdventurerPublicEncounter(phase, labels, options,
                        String.valueOf(field(event, "body")), DeadAdventurer.DESCRIPTIONS,
                        AbstractDungeon.ascensionLevel) : -1;
        if (deadAdventurerEncounter >= 0)
            map(out.get("details")).put("deadAdventurerEncounter", deadAdventurerEncounter);
        if ("WeMeetAgain".equals(simple) && "INTRO".equals(String.valueOf(phase))) {
            Map<String,Object> details = map(out.get("details"));
            Object offeredPotion = field(event, "potionOption");
            Object offeredCard = field(event, "cardOption");
            int goldAmount = ((Number)field(event, "goldAmount")).intValue();
            int potionIndex = -1, cardIndex = -1;
            if (offeredPotion != null) {
                for (int i = 0; i < AbstractDungeon.player.potions.size(); ++i)
                    if (AbstractDungeon.player.potions.get(i) == offeredPotion) potionIndex = i;
                if (potionIndex < 0) throw new IllegalArgumentException("We Meet Again potion identity lost");
            }
            if (offeredCard != null) {
                AbstractCard card = (AbstractCard)offeredCard;
                for (int i = 0; i < AbstractDungeon.player.masterDeck.group.size(); ++i)
                    if (AbstractDungeon.player.masterDeck.group.get(i).uuid.equals(card.uuid)) cardIndex = i;
                if (cardIndex < 0) throw new IllegalArgumentException("We Meet Again card identity lost");
            }
            details.put("potionIdx", potionIndex);
            details.put("gold", goldAmount >= 50 ? goldAmount : -1);
            details.put("cardIdx", cardIndex);
            List<Integer> expected = new ArrayList<>();
            if (potionIndex >= 0) expected.add(0);
            if (goldAmount >= 50) expected.add(1);
            if (cardIndex >= 0) expected.add(2);
            expected.add(3);
            if (expected.size() != options.size())
                throw new IllegalArgumentException("We Meet Again public options differ from native availability");
            for (int i = 0; i < expected.size(); ++i)
                if (((Number)map(options.get(i)).get("index")).intValue() != expected.get(i))
                    throw new IllegalArgumentException("We Meet Again option slots differ from native order");
        }
        // Only initial phases with native one-to-one option indices qualify.
        boolean initial = "INTRO".equals(String.valueOf(phase)) || "0".equals(String.valueOf(phase));
        boolean idolTrap = "GoldenIdolEvent".equals(simple) && "1".equals(String.valueOf(phase))
                && options.size() == 3 && labels.size() == 3
                && ((Number)map(options.get(0)).get("index")).intValue() == 0
                && ((Number)map(options.get(1)).get("index")).intValue() == 1
                && ((Number)map(options.get(2)).get("index")).intValue() == 2;
        if (!(simpleInitialEventSupported(simple) && initial)
                && !goop
                && !goldShrine
                && !nestDecisionVisible(simple, phase, labels, options, AbstractDungeon.ascensionLevel)
                && !idolTrap && !goldenWing && !cleric && deadAdventurerEncounter < 0)
            out.put("unsupportedReason", "EVENT_PHASE_UNREPRESENTABLE:" + id + ":" + phase);
        if ("NeowEvent".equals(simple)) {
            List<Object> offers = new ArrayList<>();
            Object rs = optionalField(event, "rewards");
            if (rs instanceof List) for (Object reward : list(rs))
                offers.add(object("type", String.valueOf(field(reward, "type")), "drawback", String.valueOf(field(reward, "drawback"))));
            e.put("neowRewards", offers);
            if (offers.size() == 4 && "3".equals(String.valueOf(phase)) && active.size() == 4) {
                List<Object> nativeOffers = new ArrayList<>();
                for (Object offer : offers) nativeOffers.add(object("bonus", map(offer).get("type"), "drawback", map(offer).get("drawback")));
                map(out.get("details")).put("neow", nativeOffers);
                out.remove("unsupportedReason"); out.put("screen", "neow");
            }
        }
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
