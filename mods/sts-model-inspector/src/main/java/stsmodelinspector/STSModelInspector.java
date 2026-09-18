package stsmodelinspector;

import basemod.BaseMod;
import basemod.interfaces.PostInitializeSubscriber;
import basemod.interfaces.PostUpdateSubscriber;
import basemod.interfaces.RenderSubscriber;
import basemod.interfaces.OnStartBattleSubscriber;
import basemod.interfaces.PostBattleSubscriber;
import com.badlogic.gdx.graphics.Color;
import com.badlogic.gdx.graphics.g2d.SpriteBatch;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.cards.AbstractCard;
import com.megacrit.cardcrawl.monsters.AbstractMonster;
import com.megacrit.cardcrawl.helpers.FontHelper;
import com.megacrit.cardcrawl.rooms.EventRoom;
import com.megacrit.cardcrawl.rooms.MonsterRoom;
import com.megacrit.cardcrawl.rooms.ShopRoom;
import com.megacrit.cardcrawl.rooms.RestRoom;
import com.megacrit.cardcrawl.rooms.TreasureRoom;
import com.megacrit.cardcrawl.rooms.AbstractRoom;
import com.megacrit.cardcrawl.core.Settings;
import com.evacipated.cardcrawl.modthespire.lib.SpireInitializer;
import org.lwjgl.input.Keyboard;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.util.Properties;

/** Read-only observer. It never calls an AbstractDungeon action or mutates game state. */
@SpireInitializer
public final class STSModelInspector implements PostInitializeSubscriber,
        PostUpdateSubscriber, RenderSubscriber, OnStartBattleSubscriber,
        PostBattleSubscriber {
    private static final String PROTOCOL = "sts_model_inspector_v1";
    private static final int PROTOCOL_VERSION = 1;
    private static final String TOGGLE = "stsmodelinspector.toggle";

    private static final STSModelInspector INSTANCE = new STSModelInspector();
    private final Advisor advisor = new Advisor();
    private String session = Long.toHexString(System.nanoTime());
    private long sequence;
    private String lastFingerprint = "";
    private volatile Snapshot newest;
    private volatile String advisorStatus = "disconnected";
    private volatile String advisorReason = "not started";
    private volatile long responseSequence = -1;
    private volatile String responseHash = "";
    private volatile String ctmStatus = "";
    private volatile String ctmReason = "";
    private volatile double ctmDeath = 0.0;
    private volatile double ctmWinningHp = 0.0;
    private volatile boolean panelVisible = true;
    private volatile String combatEntry = "";
    private volatile String combatEntryHash = "";
    private String lastRoomClass = "NONE";
    private String lastNodeRoomClass = "";
    private int lastNodeX = -1, lastNodeY = -1;
    private boolean previousRoomKnown;
    private boolean toggleDown;

    public static void initialize() {
        BaseMod.subscribe(INSTANCE);
    }

    @Override
    public void receiveOnBattleStart(AbstractRoom room) {
        // BaseMod's hook is at AbstractRoom's battle-start boundary, before
        // player/monster start-of-combat effects are applied.
        // The encounter group may not be populated at this exact hook. Capture
        // persistent state now and bind the revealed encounter below when the
        // combat observation becomes visible.
        String entry = combatEntryJson(room, "");
        if (entry.isEmpty()) { combatEntry = ""; combatEntryHash = ""; return; }
        combatEntry = entry;
        combatEntryHash = sha256(entry);
    }

    @Override
    public void receivePostBattle(AbstractRoom room) {
        combatEntry = "";
        combatEntryHash = "";
        ctmStatus = "";
        ctmReason = "";
        ctmDeath = 0.0;
        ctmWinningHp = 0.0;
    }

    private STSModelInspector() {}

    @Override
    public void receivePostInitialize() {
        advisor.start();
        Runtime.getRuntime().addShutdownHook(new Thread(advisor::shutdown,
                "sts-model-inspector-shutdown"));
    }

    @Override
    public void receivePostUpdate() {
        observeRoomTransition();
        boolean down = Keyboard.isKeyDown(loadToggleKey());
        if (down && !toggleDown) panelVisible = !panelVisible;
        toggleDown = down;

        Snapshot snapshot = captureStableSnapshot();
        if (snapshot == null) {
            if (newest != null) {
                newest = null;
                lastFingerprint = "";
                responseSequence = -1;
                responseHash = "";
                advisor.clearPending();
            }
            return;
        }
        if (snapshot.hash.equals(lastFingerprint)) return;
        lastFingerprint = snapshot.hash;
        Snapshot emitted = snapshot.withSequence(++sequence);
        newest = emitted;
        responseSequence = -1;
        responseHash = "";
        if (!"combat".equals(snapshot.boundary)
                || !snapshot.combatEntryHash.equals(combatEntryHash)) {
            ctmStatus = "";
            ctmReason = "";
            ctmDeath = 0.0;
            ctmWinningHp = 0.0;
        }
        advisorStatus = "waiting";
        advisorReason = "";
        advisor.send(emitted);
    }

    @Override
    public void receiveRender(SpriteBatch sb) {
        if (!panelVisible || newest == null) return;
        float x = 28.0f * Settings.scale;
        float y = Settings.HEIGHT - 120.0f * Settings.scale;
        Color white = Color.WHITE;
        FontHelper.renderFontLeftTopAligned(sb, FontHelper.tipHeaderFont,
                "STS Model Inspector", x, y, white);
        FontHelper.renderFontLeftTopAligned(sb, FontHelper.tipBodyFont,
                "Advisor: " + advisorStatus, x, y - 28.0f * Settings.scale,
                advisorStatus.equals("connected") ? Color.GREEN : Color.ORANGE);
        FontHelper.renderFontLeftTopAligned(sb, FontHelper.tipBodyFont,
                "State: " + newest.boundary + "  Floor: " + newest.floor +
                        "  HP: " + newest.hp + "/" + newest.maxHp,
                x, y - 50.0f * Settings.scale, white);
        String result = responseSequence == newest.sequence && responseHash.equals(newest.hash)
                ? advisorStatus.toUpperCase() + (advisorReason.isEmpty() ? "" : " - " + advisorReason)
                : "WAITING / STALE";
        FontHelper.renderFontLeftTopAligned(sb, FontHelper.tipBodyFont,
                "Observation: " + newest.sequence + "  Advisor: " + result,
                x, y - 72.0f * Settings.scale, white);
        if ("combat".equals(newest.boundary)) {
            String forecast = ctmStatus.isEmpty() ? "CTM — waiting" : "CTM — " + ctmStatus;
            FontHelper.renderFontLeftTopAligned(sb, FontHelper.tipBodyFont, forecast,
                    x, y - 116.0f * Settings.scale, white);
            if ("OK".equals(ctmStatus)) {
                FontHelper.renderFontLeftTopAligned(sb, FontHelper.tipBodyFont,
                        String.format("Death: %.1f%%   HP if survive: %.0f%%",
                                100.0 * ctmDeath, 100.0 * ctmWinningHp),
                        x, y - 138.0f * Settings.scale, white);
            } else if (!ctmReason.isEmpty()) {
                FontHelper.renderFontLeftTopAligned(sb, FontHelper.tipBodyFont, ctmReason,
                        x, y - 138.0f * Settings.scale, Color.ORANGE);
            }
        }
        FontHelper.renderFontLeftTopAligned(sb, FontHelper.tipBodyFont,
                "Toggle: " + Keyboard.getKeyName(loadToggleKey()), x,
                y - ("combat".equals(newest.boundary) ? 160.0f : 94.0f) * Settings.scale, Color.GRAY);
    }

    private Snapshot captureStableSnapshot() {
        if (AbstractDungeon.player == null
                || AbstractDungeon.currMapNode == null
                || AbstractDungeon.getCurrRoom() == null) return null;
        AbstractRoom room = AbstractDungeon.getCurrRoom();
        String boundary;
        if (AbstractDungeon.screen == AbstractDungeon.CurrentScreen.CARD_REWARD) {
            boundary = "card_reward";
        } else if (room instanceof RestRoom && isActionableRestDecision((RestRoom) room)) {
            boundary = "rest";
        } else if (room instanceof MonsterRoom && isPlayerDecisionPoint()) {
            boundary = "combat";
        } else {
            return null;
        }
        if ("combat".equals(boundary) && !combatEntry.isEmpty()
                && combatEntry.contains("\"encounter\":\"\"")) {
            String encounter = encounterName(room);
            if (!encounter.isEmpty()) {
                combatEntry = combatEntry.replace("\"encounter\":\"\"",
                        "\"encounter\":\"" + encounter + "\"");
                combatEntryHash = sha256(combatEntry);
            }
        }
        String character = AbstractDungeon.player.chosenClass == null
                ? "unknown" : AbstractDungeon.player.chosenClass.name();
        int act = AbstractDungeon.actNum;
        int floor = AbstractDungeon.floorNum;
        int hp = AbstractDungeon.player.currentHealth;
        int maxHp = AbstractDungeon.player.maxHealth;
        int gold = AbstractDungeon.player.gold;
        String deck = deckJson();
        String candidates = candidatesJson(boundary);
        String combat = "";
        if ("combat".equals(boundary)) combat = combatJson();
        String raw = boundary + "|" + character + "|" + AbstractDungeon.ascensionLevel +
                "|" + act + "|" + floor + "|" + hp + "|" + maxHp + "|" + gold +
                "|" + room.getClass().getName() + "|" + AbstractDungeon.screen.name() +
                "|" + deck + "|" + candidates + "|" + combat;
        return new Snapshot(session, 0, boundary, character,
                AbstractDungeon.ascensionLevel, act, floor, hp, maxHp, gold,
                deck, candidates, combat, "combat".equals(boundary) ? combatEntry : "",
                "combat".equals(boundary) ? combatEntryHash : "", sha256(raw));
    }

    private void observeRoomTransition() {
        if (AbstractDungeon.currMapNode == null) return;
        int x = AbstractDungeon.currMapNode.x;
        int y = AbstractDungeon.currMapNode.y;
        String current = roomClass(AbstractDungeon.currMapNode.room != null
                ? AbstractDungeon.currMapNode.room : AbstractDungeon.getCurrRoom());
        if (x == lastNodeX && y == lastNodeY) return;
        if (lastNodeX >= 0) {
            lastRoomClass = lastNodeRoomClass;
            previousRoomKnown = true;
        } else {
            // If the observer starts after a save is loaded, the preceding map
            // node is not available. NONE is the native fail-closed category
            // for the first observed node, and lets the entry payload exist so
            // the advisor can apply its ordinary support checks.
            lastRoomClass = "NONE";
            previousRoomKnown = true;
        }
        lastNodeX = x;
        lastNodeY = y;
        lastNodeRoomClass = current;
    }

    private static String roomClass(AbstractRoom room) {
        if (room == null) return "NONE";
        if (room instanceof com.megacrit.cardcrawl.rooms.MonsterRoomBoss) return "BOSS";
        if (room instanceof com.megacrit.cardcrawl.rooms.MonsterRoomElite) return "ELITE";
        if (room instanceof MonsterRoom) return "MONSTER";
        if (room instanceof ShopRoom) return "SHOP";
        if (room instanceof TreasureRoom) return "TREASURE";
        if (room instanceof RestRoom) return "REST";
        if (room instanceof EventRoom) return "EVENT";
        return "EVENT";
    }

    private String encounterName(AbstractRoom room) {
        com.megacrit.cardcrawl.monsters.MonsterGroup group = room == null ? null : room.monsters;
        if (group == null) group = AbstractDungeon.getMonsters();
        if (group == null || group.monsters == null || group.monsters.isEmpty()) return "";
        if (group.monsters.size() != 1) return "";
        String id = group.monsters.get(0).id;
        if (id.equals(com.megacrit.cardcrawl.helpers.MonsterHelper.CULTIST_ENC)) return "CULTIST";
        if (id.equals(com.megacrit.cardcrawl.helpers.MonsterHelper.JAW_WORM_ENC)) return "JAW_WORM";
        if (id.equals(com.megacrit.cardcrawl.helpers.MonsterHelper.BLUE_SLAVER_ENC)) return "BLUE_SLAVER";
        if (id.equals(com.megacrit.cardcrawl.helpers.MonsterHelper.LOOTER_ENC)) return "LOOTER";
        if (id.equals(com.megacrit.cardcrawl.helpers.MonsterHelper.RED_SLAVER_ENC)) return "RED_SLAVER";
        if (id.equals(com.megacrit.cardcrawl.helpers.MonsterHelper.GREMLIN_NOB_ENC)) return "GREMLIN_NOB";
        if (id.equals(com.megacrit.cardcrawl.helpers.MonsterHelper.LAGAVULIN_ENC)) return "LAGAVULIN";
        if (id.equals(com.megacrit.cardcrawl.helpers.MonsterHelper.SPHERE_GUARDIAN_ENC)) return "SPHERIC_GUARDIAN";
        if (id.equals(com.megacrit.cardcrawl.helpers.MonsterHelper.CHOSEN_ENC)) return "CHOSEN";
        if (id.equals(com.megacrit.cardcrawl.helpers.MonsterHelper.SHELL_PARASITE_ENC)) return "SHELL_PARASITE";
        if (id.equals(com.megacrit.cardcrawl.helpers.MonsterHelper.SNAKE_PLANT_ENC)) return "SNAKE_PLANT";
        if (id.equals(com.megacrit.cardcrawl.helpers.MonsterHelper.SNECKO_ENC)) return "SNECKO";
        if (id.equals(com.megacrit.cardcrawl.helpers.MonsterHelper.TRANSIENT_ENC)) return "TRANSIENT";
        if (id.equals(com.megacrit.cardcrawl.helpers.MonsterHelper.ORB_WALKER_ENC)) return "ORB_WALKER";
        if (id.equals(com.megacrit.cardcrawl.helpers.MonsterHelper.SPIRE_GROWTH_ENC)) return "SPIRE_GROWTH";
        if (id.equals(com.megacrit.cardcrawl.helpers.MonsterHelper.MAW_ENC)) return "MAW";
        if (id.equals(com.megacrit.cardcrawl.helpers.MonsterHelper.WRITHING_MASS_ENC)) return "WRITHING_MASS";
        if (id.equals(com.megacrit.cardcrawl.helpers.MonsterHelper.GIANT_HEAD_ENC)) return "GIANT_HEAD";
        if (id.equals(com.megacrit.cardcrawl.helpers.MonsterHelper.NEMESIS_ENC)) return "NEMESIS";
        if (id.equals(com.megacrit.cardcrawl.helpers.MonsterHelper.SLIME_BOSS_ENC)) return "SLIME_BOSS";
        if (id.equals(com.megacrit.cardcrawl.helpers.MonsterHelper.GUARDIAN_ENC)) return "THE_GUARDIAN";
        if (id.equals(com.megacrit.cardcrawl.helpers.MonsterHelper.HEXAGHOST_ENC)) return "HEXAGHOST";
        if (id.equals(com.megacrit.cardcrawl.helpers.MonsterHelper.CHAMP_ENC)) return "CHAMP";
        if (id.equals(com.megacrit.cardcrawl.helpers.MonsterHelper.TIME_EATER_ENC)) return "TIME_EATER";
        return "";
    }

    private String combatEntryJson(AbstractRoom room) {
        return combatEntryJson(room, encounterName(room));
    }

    private String combatEntryJson(AbstractRoom room, String encounter) {
        if (AbstractDungeon.player == null || AbstractDungeon.currMapNode == null) return "";
        boolean burningElite = room instanceof com.megacrit.cardcrawl.rooms.MonsterRoomElite
                && AbstractDungeon.currMapNode.hasEmeraldKey;
        StringBuilder out = new StringBuilder("{\"character\":\"")
                .append(escapeJson(AbstractDungeon.player.chosenClass.name()))
                .append("\",\"ascension\":").append(AbstractDungeon.ascensionLevel)
                .append(",\"act\":").append(AbstractDungeon.actNum)
                .append(",\"floor\":").append(AbstractDungeon.floorNum)
                .append(",\"hp\":").append(AbstractDungeon.player.currentHealth)
                .append(",\"maxHp\":").append(AbstractDungeon.player.maxHealth)
                .append(",\"gold\":").append(AbstractDungeon.player.gold)
                .append(",\"roomClass\":\"").append(roomClass(room))
                .append("\",\"previousRoomClass\":\"").append(lastRoomClass)
                .append("\",\"encounter\":\"").append(encounter)
                .append("\",\"potionKeepValue\":4.0,\"isBurningElite\":")
                .append(burningElite)
                .append(",\"potionCapacity\":").append(AbstractDungeon.player.potionSlots)
                .append(",\"deck\":").append(deckEntryJson())
                .append(",\"relics\":").append(relicEntryJson())
                .append(",\"potions\":").append(potionEntryJson()).append('}');
        return out.toString();
    }

    private static String deckEntryJson() {
        StringBuilder out = new StringBuilder("["); boolean first = true;
        for (AbstractCard card : AbstractDungeon.player.masterDeck.group) {
            if (!first) out.append(','); first = false;
            int bottle = card.inBottleFlame ? 0 : (card.inBottleLightning ? 1 :
                    (card.inBottleTornado ? 2 : -1));
            out.append("{\"id\":\"").append(escapeJson(card.cardID))
                    .append("\",\"upgraded\":").append(card.upgraded)
                    .append(",\"misc\":").append(card.misc)
                    .append(",\"bottleBinding\":").append(bottle).append('}');
        }
        return out.append(']').toString();
    }

    private static String relicEntryJson() {
        StringBuilder out = new StringBuilder("["); boolean first = true;
        for (com.megacrit.cardcrawl.relics.AbstractRelic relic : AbstractDungeon.player.relics) {
            if (!first) out.append(','); first = false;
            out.append("{\"id\":\"").append(escapeJson(relic.relicId))
                    .append("\",\"data\":").append(relic.counter).append('}');
        }
        return out.append(']').toString();
    }

    private static String potionEntryJson() {
        StringBuilder out = new StringBuilder("["); boolean first = true;
        for (int slot = 0; slot < AbstractDungeon.player.potionSlots; ++slot) {
            if (!first) out.append(','); first = false;
            String id = "Potion Slot";
            if (slot < AbstractDungeon.player.potions.size()
                    && AbstractDungeon.player.potions.get(slot) != null)
                id = AbstractDungeon.player.potions.get(slot).ID;
            out.append('\"').append(escapeJson(id)).append('\"');
        }
        for (int slot = AbstractDungeon.player.potionSlots; slot < 5; ++slot) {
            if (!first) out.append(','); first = false; out.append("\"Potion Slot\"");
        }
        return out.append(']').toString();
    }

    private static String deckJson() {
        StringBuilder out = new StringBuilder();
        out.append('[');
        boolean first = true;
        for (AbstractCard card : AbstractDungeon.player.masterDeck.group) {
            if (!first) out.append(',');
            first = false;
            out.append(cardJson(card));
        }
        out.append(']');
        return out.toString();
    }

    private static String candidatesJson(String boundary) {
        StringBuilder out = new StringBuilder("[");
        boolean first = true;
        if ("card_reward".equals(boundary) && AbstractDungeon.cardRewardScreen.rewardGroup != null) {
            for (AbstractCard card : AbstractDungeon.cardRewardScreen.rewardGroup) {
                if (!first) out.append(',');
                first = false;
                out.append(cardJson(card));
            }
        } else if ("rest".equals(boundary)) {
            for (AbstractCard card : AbstractDungeon.player.masterDeck.group) {
                if (!card.canUpgrade()) continue;
                if (!first) out.append(',');
                first = false;
                out.append(cardJson(card));
            }
        }
        return out.append(']').toString();
    }

    private static String cardJson(AbstractCard card) {
        return "{\"id\":\"" + escapeJson(card.cardID) + "\",\"uuid\":\"" +
                escapeJson(String.valueOf(card.uuid)) + "\",\"upgraded\":" +
                (card.upgraded ? "true" : "false") + ",\"misc\":" + card.misc +
                ",\"cost\":" + card.cost + ",\"costForTurn\":" + card.costForTurn + "}";
    }

    private static boolean isPlayerDecisionPoint() {
        if (AbstractDungeon.screen != AbstractDungeon.CurrentScreen.NONE
                || AbstractDungeon.actionManager == null) return false;
        com.megacrit.cardcrawl.actions.GameActionManager actions = AbstractDungeon.actionManager;
        return actions.phase == com.megacrit.cardcrawl.actions.GameActionManager.Phase.WAITING_ON_USER
                && actions.currentAction == null
                && actions.actions.isEmpty()
                && actions.cardQueue.isEmpty()
                && actions.monsterQueue.isEmpty()
                && !actions.turnHasEnded;
    }

    private static boolean isActionableRestDecision(RestRoom room) {
        return room.campfireUI != null
                && !com.megacrit.cardcrawl.rooms.CampfireUI.hidden
                && !room.campfireUI.somethingSelected;
    }

    private static boolean hasRunicDome() {
        for (com.megacrit.cardcrawl.relics.AbstractRelic relic : AbstractDungeon.player.relics) {
            if ("Runic Dome".equals(relic.relicId)) return true;
        }
        return false;
    }

    private static String combatJson() {
        StringBuilder out = new StringBuilder("{\"turn\":");
        out.append(com.megacrit.cardcrawl.actions.GameActionManager.turn)
                .append(",\"energy\":")
                .append(AbstractDungeon.player.energy == null ? 0 : AbstractDungeon.player.energy.energy)
                .append(",\"block\":").append(AbstractDungeon.player.currentBlock)
                .append(",\"hand\":[");
        boolean first = true;
        for (AbstractCard card : AbstractDungeon.player.hand.group) {
            if (!first) out.append(',');
            first = false;
            out.append(cardJson(card));
        }
        out.append("],\"monsters\":[");
        first = true;
        boolean runicDome = hasRunicDome();
        if (AbstractDungeon.getMonsters() != null) {
            for (AbstractMonster monster : AbstractDungeon.getMonsters().monsters) {
                if (monster == null || monster.isDeadOrEscaped()) continue;
                if (!first) out.append(',');
                first = false;
                out.append("{\"id\":\"").append(escapeJson(monster.id))
                        .append("\",\"hp\":").append(monster.currentHealth)
                        .append(",\"block\":").append(monster.currentBlock);
                if (!runicDome) {
                    out.append(",\"intent\":\"")
                            .append(escapeJson(monster.intent == null ? "UNKNOWN" : monster.intent.name()))
                            .append("\",\"intentDamage\":").append(monster.getIntentDmg());
                }
                out.append('}');
            }
        }
        return out.append("]}").toString();
    }

    private static String escapeJson(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private static int loadToggleKey() {
        return Keyboard.KEY_F8;
    }

    private static String sha256(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder out = new StringBuilder();
            for (byte b : digest) out.append(String.format("%02x", b & 0xff));
            return out.toString();
        } catch (Exception e) {
            return "hash-error";
        }
    }

    private final class Advisor {
        private Process process;
        private BufferedWriter stdin;
        private Thread reader;
        private Thread errorReader;
        private Thread writer;
        private Snapshot pendingObservation;
        private boolean stopping;

        synchronized void start() {
            try {
                Properties p = new Properties();
                Path config = Paths.get(System.getProperty("user.home"), ".sts-model-inspector.properties");
                if (Files.isRegularFile(config)) try (BufferedReader r = Files.newBufferedReader(config)) { p.load(r); }
                String executable = p.getProperty("advisor", System.getenv("STS_MODEL_INSPECTOR_ADVISOR"));
                if (executable == null || executable.trim().isEmpty()) {
                    advisorStatus = "disconnected";
                    advisorReason = "set advisor in ~/.sts-model-inspector.properties";
                    return;
                }
                ProcessBuilder builder = new ProcessBuilder(executable);
                String ctmModel = p.getProperty("ctmModel", System.getenv("STS_CTM_MODEL"));
                if (ctmModel != null && !ctmModel.trim().isEmpty())
                    builder.environment().put("STS_CTM_MODEL", ctmModel);
                Process started = builder.redirectErrorStream(false).start();
                process = started;
                stopping = false;
                stdin = new BufferedWriter(new OutputStreamWriter(process.getOutputStream(), StandardCharsets.UTF_8));
                reader = new Thread(() -> readResponses(started), "sts-model-inspector-responses");
                reader.setDaemon(true);
                reader.start();
                errorReader = new Thread(() -> drainErrors(started), "sts-model-inspector-stderr");
                errorReader.setDaemon(true);
                errorReader.start();
                write("{\"protocol\":\"" + PROTOCOL + "\",\"kind\":\"hello\"}");
            } catch (Exception e) {
                advisorStatus = "error";
                advisorReason = e.getClass().getSimpleName();
            }
        }

        void send(Snapshot s) {
            synchronized (this) {
                if (stopping) return;
                pendingObservation = s;
                if (writer == null || !writer.isAlive()) {
                    writer = new Thread(this::writePending, "sts-model-inspector-advisor");
                    writer.setDaemon(true);
                    writer.start();
                }
                notifyAll();
            }
        }

        synchronized void clearPending() {
            pendingObservation = null;
            notifyAll();
        }

        private void writePending() {
            while (true) {
                Snapshot next;
                synchronized (this) {
                    while (pendingObservation == null && !stopping) {
                        try { wait(); } catch (InterruptedException ignored) {}
                    }
                    if (stopping) return;
                    next = pendingObservation;
                    pendingObservation = null;
                }
                try {
                    write(next.toJson());
                } catch (Exception e) {
                    advisorStatus = "error";
                    advisorReason = e.getClass().getSimpleName();
                }
            }
        }

        private synchronized void write(String line) throws IOException {
            if (stdin == null) throw new IOException("advisor not connected");
            stdin.write(line);
            stdin.newLine();
            stdin.flush();
        }

        synchronized void shutdown() {
            stopping = true;
            pendingObservation = null;
            notifyAll();
            if (process != null) process.destroy();
            if (reader != null) reader.interrupt();
            if (errorReader != null) errorReader.interrupt();
            if (writer != null) writer.interrupt();
            process = null;
            stdin = null;
        }

        private void readResponses(Process p) {
            try (BufferedReader r = new BufferedReader(new InputStreamReader(p.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = r.readLine()) != null) {
                    if (line.contains("\"status\":\"READY\"")) {
                        advisorStatus = "connected";
                        advisorReason = "";
                    } else {
                        String status = field(line, "status");
                        String reason = field(line, "reason");
                        String code = field(line, "code");
                        String message = field(line, "message");
                        String responseSession = field(line, "session");
                        long seq = numberField(line, "sequence");
                        String hash = field(line, "observationHash");
                        Snapshot current = newest;
                        if (current != null && current.session.equals(responseSession)
                                && seq == current.sequence && current.hash.equals(hash)) {
                            responseSequence = seq;
                            responseHash = hash;
                            advisorStatus = status == null ? "error" : status.toLowerCase();
                            if ("MODEL_UNAVAILABLE".equals(status)
                                    || "SCHEMA_MISMATCH".equals(status)) {
                                ctmStatus = status.toLowerCase().replace('_', ' ');
                                ctmReason = reason == null ? ctmStatus : reason;
                            }
                            if ("ERROR".equals(status)) {
                                advisorReason = (code == null ? "UNKNOWN" : code) +
                                        (message == null || message.isEmpty() ? "" : " - " + message);
                            } else {
                                advisorReason = reason == null ? "" : reason;
                            }
                            if (line.contains("\"id\":\"ctm_combat_entry_v2\"")) {
                                if (line.contains("\"status\":\"UNSUPPORTED\"")) {
                                    ctmStatus = "unsupported";
                                    ctmReason = reason == null ? "unsupported" : reason;
                                } else if (line.contains("\"deathProbability\":")) {
                                    ctmStatus = "OK";
                                    ctmDeath = doubleField(line, "deathProbability");
                                    ctmWinningHp = doubleField(line, "winningHpFraction");
                                }
                            }
                        }
                    }
                }
                advisorStatus = "disconnected";
                advisorReason = "advisor exited";
            } catch (Exception e) {
                advisorStatus = "disconnected";
                advisorReason = "advisor exited";
            }
        }

        private void drainErrors(Process p) {
            try (BufferedReader r = new BufferedReader(new InputStreamReader(p.getErrorStream(), StandardCharsets.UTF_8))) {
                while (r.readLine() != null) { /* drain; diagnostics stay out of the game UI */ }
            } catch (IOException ignored) {}
        }

        private String field(String json, String key) {
            String needle = "\"" + key + "\":\"";
            int start = json.indexOf(needle);
            if (start < 0) return null;
            start += needle.length();
            int end = json.indexOf('"', start);
            return end < 0 ? null : json.substring(start, end);
        }

        private long numberField(String json, String key) {
            String needle = "\"" + key + "\":";
            int start = json.indexOf(needle);
            if (start < 0) return -1;
            start += needle.length();
            int end = start;
            while (end < json.length() && Character.isDigit(json.charAt(end))) end++;
            try { return Long.parseLong(json.substring(start, end)); }
            catch (Exception e) { return -1; }
        }

        private double doubleField(String json, String key) {
            String needle = "\"" + key + "\":";
            int start = json.indexOf(needle);
            if (start < 0) return 0.0;
            start += needle.length();
            int end = start;
            while (end < json.length() && "0123456789+-.eE".indexOf(json.charAt(end)) >= 0) end++;
            try { return Double.parseDouble(json.substring(start, end)); }
            catch (Exception e) { return 0.0; }
        }
    }

    private static final class Snapshot {
        final String session, boundary, character, deck, candidates, hash;
        final String combat;
        final String combatEntry, combatEntryHash;
        final long sequence;
        final int ascension, act, floor, hp, maxHp, gold;

        Snapshot(String session, long sequence, String boundary, String character,
                 int ascension, int act, int floor, int hp, int maxHp, int gold,
                 String deck, String candidates, String combat, String combatEntry,
                 String combatEntryHash, String hash) {
            this.session = session; this.sequence = sequence; this.boundary = boundary;
            this.character = character; this.ascension = ascension; this.act = act;
            this.floor = floor; this.hp = hp; this.maxHp = maxHp; this.gold = gold;
            this.deck = deck; this.candidates = candidates; this.hash = hash;
            this.combat = combat; this.combatEntry = combatEntry;
            this.combatEntryHash = combatEntryHash;
        }

        Snapshot withSequence(long emittedSequence) {
            return new Snapshot(session, emittedSequence, boundary, character, ascension, act,
                    floor, hp, maxHp, gold, deck, candidates, combat, combatEntry,
                    combatEntryHash, hash);
        }

        String toJson() {
            return "{\"protocol\":\"" + PROTOCOL + "\",\"kind\":\"observation\"" +
                    ",\"session\":\"" + escape(session) + "\",\"sequence\":" + sequence +
                    ",\"observationHash\":\"" + hash + "\",\"observation\":{" +
                    "\"boundary\":\"" + boundary + "\",\"character\":\"" + character +
                    "\",\"ascension\":" + ascension + ",\"act\":" + act +
                    ",\"floor\":" + floor + ",\"hp\":" + hp + ",\"maxHp\":" + maxHp +
                    ",\"gold\":" + gold + ",\"deck\":" + deck +
                    ",\"candidates\":" + candidates +
                    (combat.isEmpty() ? "" : ",\"combat\":" + combat
                        + ",\"combatEntryHash\":\"" + combatEntryHash + "\""
                        + (combatEntry.isEmpty() ? "" : ",\"combatEntry\":" + combatEntry)) + "}}";
        }

        private static String escape(String s) { return s.replace("\\", "\\\\").replace("\"", "\\\""); }
    }
}
