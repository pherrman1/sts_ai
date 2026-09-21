package stsmodelinspector;

import com.google.gson.Gson;
import com.megacrit.cardcrawl.cards.AbstractCard;
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
    private static final SeenRelicOffers seenRelicOffers = new SeenRelicOffers();

    // Only an uninterrupted observation from a fresh Neow boundary can
    // account for skipped offers. A resumed/mid-run observer stays incomplete.
    static final class SeenRelicOffers {
        private Object player;
        private long seed;
        private int lastFloor = -1;
        private boolean complete;
        private final LinkedHashSet<String> offers = new LinkedHashSet<>();

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
            boolean freshRun = AbstractDungeon.floorNum == 0
                    && CardCrawlGame.metricData != null
                    && CardCrawlGame.metricData.path_taken != null
                    && CardCrawlGame.metricData.path_taken.isEmpty();
            seenRelicOffers.observe(AbstractDungeon.player, Settings.seed,
                    AbstractDungeon.floorNum, freshRun, String.valueOf(out.get("screen")),
                    map(out.getOrDefault("details", object())));
            core.put("seenRelics", seenRelicOffers.snapshot());
            core.put("seenRelicsComplete", seenRelicOffers.complete());
            if (!Boolean.TRUE.equals(map(out.get("publicState")).get("pathComplete")))
                out.put("unsupportedReason", "PATH_HISTORY_UNAVAILABLE");
            if (map(out.get("publicState")).containsKey("unsupportedReason"))
                out.put("unsupportedReason", map(out.get("publicState")).get("unsupportedReason"));
            if (!out.containsKey("unsupportedReason")) out.put("unsupportedReason", "");
        } catch (ReflectiveOperationException | RuntimeException failure) {
            seenRelicOffers.invalidate();
            recordCaptureError(out, failure);
        }
        return JSON.toJson(out);
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
        if (path != null) for (int i = 0; i < path.size(); ++i) {
            String canonical = roomSymbol(path.get(i));
            if (bossTransitionSentinel && i == path.size() - 1 && "INVALID".equals(canonical)) {
                // Vanilla can omit the last pre-boss map symbol while the
                // public damage metric already records that floor's combat.
                // Recover it only from the actual parent node; otherwise keep
                // the history incomplete and fail closed below.
                canonical = inferredBossPrecedingRoom;
                if (canonical.isEmpty()) { exact = false; continue; }
            }
            int idx = Arrays.asList("SHOP", "REST", "EVENT", "ELITE", "MONSTER", "TREASURE",
                    "BOSS", "BOSS_TREASURE", "NONE", "INVALID").indexOf(canonical);
            if (idx >= 0 && idx < 6) ++visits[idx];
            else if (idx != 6 && idx != 7 && idx != 8) exact = false;
        }
        p.put("pathVisits", visits);
        p.put("pathComplete", exact);
        List<String> canonicalPathHistory = new ArrayList<>();
        if (path != null) for (int i = 0; i < path.size(); ++i) {
            String canonical = roomSymbol(path.get(i));
            if (bossTransitionSentinel && i == path.size() - 1 && "INVALID".equals(canonical))
                canonical = inferredBossPrecedingRoom;
            if (canonical.isEmpty()) continue;
            canonicalPathHistory.add(canonical);
        }
        p.put("pathHistory", canonicalPathHistory);
        // MetricData preserves the completed combat floor and the encounter
        // key even when the original map symbol was '?'.  Keep only the
        // public floor identity here; future encounter identities remain
        // hidden and are sampled by the native belief root.
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

    static boolean simpleInitialEventSupported(String simple) {
        return Arrays.asList("BigFish", "GoldenShrine", "ShiningLight", "WorldOfGoop",
                "LivingWall", "LiarsGame", "Mushrooms", "Ghosts", "WindingHalls", "TheLibrary",
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
            "NeowsBlessing", "Omamori", "Girya", "Tiny Chest");

    private static void unsupported(Map<String,Object> state, String reason) {
        if (!state.containsKey("unsupportedReason")) state.put("unsupportedReason", reason);
    }

    static int nativeRelicData(String id, int counter, boolean usedUp, Map<String,Object> state) {
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
        if ("Matryoshka".equals(id) || "WingedGreaves".equals(id)
                || "NlothsMask".equals(id)) {
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
        out.put("details", object("type", upgrade ? "upgrade" : AbstractDungeon.gridSelectScreen.forPurge ? "remove"
                        : AbstractDungeon.gridSelectScreen.forTransform ? "transform" : "other",
                "requiredPicks", ((Number)field(AbstractDungeon.gridSelectScreen, "numCards")).intValue(),
                "completedPicks", selected.size(), "cards", selectionCards,
                "selectedDeckIndices", selected, "confirm", confirm));
        if (confirm) out.put("unsupportedReason", "SELECTOR_CONFIRMATION_ONLY");
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
            add(cs, labels, i, "option", index, 0);
        }
        Map<String,Object> e = object("id", id, "phase", String.valueOf(phase), "options", options, "eventData", 0);
        out.put("event", e);
        out.put("details", object("event", id, "eventData", 0, "phase", 0,
                "upgradeOne", false, "cleanUpIsRemoveCard", false,
                "skillCardDeckIdx", -1, "powerCardDeckIdx", -1, "attackCardDeckIdx", -1,
                "potionIdx", -1, "gold", -1, "cardIdx", -1));
        // Only initial phases with native one-to-one option indices qualify.
        boolean initial = "INTRO".equals(String.valueOf(phase)) || "0".equals(String.valueOf(phase));
        if (!simpleInitialEventSupported(simple) || !initial)
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
