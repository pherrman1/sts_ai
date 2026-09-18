package stsmodelinspector;

import basemod.BaseMod;
import basemod.interfaces.PostInitializeSubscriber;
import basemod.interfaces.PostUpdateSubscriber;
import basemod.interfaces.RenderSubscriber;
import com.badlogic.gdx.graphics.Color;
import com.badlogic.gdx.graphics.g2d.SpriteBatch;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.cards.AbstractCard;
import com.megacrit.cardcrawl.helpers.FontHelper;
import com.megacrit.cardcrawl.rooms.MonsterRoom;
import com.megacrit.cardcrawl.rooms.RestRoom;
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
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

/** Read-only observer. It never calls an AbstractDungeon action or mutates game state. */
@SpireInitializer
public final class STSModelInspector implements PostInitializeSubscriber,
        PostUpdateSubscriber, RenderSubscriber {
    private static final String PROTOCOL = "sts_model_inspector_v1";
    private static final int PROTOCOL_VERSION = 1;
    private static final String TOGGLE = "stsmodelinspector.toggle";

    private static final STSModelInspector INSTANCE = new STSModelInspector();
    private final Advisor advisor = new Advisor();
    private String session = Long.toHexString(System.nanoTime());
    private long sequence;
    private String lastFingerprint = "";
    private Snapshot newest;
    private volatile String advisorStatus = "disconnected";
    private volatile String advisorReason = "not started";
    private volatile long responseSequence = -1;
    private volatile String responseHash = "";
    private volatile boolean panelVisible = true;
    private boolean toggleDown;

    public static void initialize() {
        BaseMod.subscribe(INSTANCE);
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
        boolean down = Keyboard.isKeyDown(loadToggleKey());
        if (down && !toggleDown) panelVisible = !panelVisible;
        toggleDown = down;

        Snapshot snapshot = captureStableSnapshot();
        if (snapshot == null || snapshot.hash.equals(lastFingerprint)) return;
        lastFingerprint = snapshot.hash;
        newest = snapshot;
        advisor.send(snapshot);
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
        FontHelper.renderFontLeftTopAligned(sb, FontHelper.tipBodyFont,
                "Toggle: " + Keyboard.getKeyName(loadToggleKey()), x,
                y - 94.0f * Settings.scale, Color.GRAY);
    }

    private Snapshot captureStableSnapshot() {
        if (AbstractDungeon.player == null
                || AbstractDungeon.currMapNode == null
                || AbstractDungeon.getCurrRoom() == null) return null;
        AbstractRoom room = AbstractDungeon.getCurrRoom();
        String boundary;
        if (AbstractDungeon.screen == AbstractDungeon.CurrentScreen.CARD_REWARD) {
            boundary = "card_reward";
        } else if (room instanceof RestRoom) {
            boundary = "rest";
        } else if (room instanceof MonsterRoom && AbstractDungeon.screen == AbstractDungeon.CurrentScreen.NONE
                && AbstractDungeon.actionManager != null
                && AbstractDungeon.actionManager.actions.isEmpty()
                && !AbstractDungeon.actionManager.turnHasEnded) {
            boundary = "combat";
        } else {
            return null;
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
        String raw = boundary + "|" + character + "|" + AbstractDungeon.ascensionLevel +
                "|" + act + "|" + floor + "|" + hp + "|" + maxHp + "|" + gold +
                "|" + room.getClass().getName() + "|" + AbstractDungeon.screen.name() +
                "|" + deck + "|" + candidates;
        return new Snapshot(session, ++sequence, boundary, character,
                AbstractDungeon.ascensionLevel, act, floor, hp, maxHp, gold,
                deck, candidates, sha256(raw));
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
        return "{\"id\":\"" + escapeJson(card.cardID) + "\",\"upgraded\":" +
                (card.upgraded ? "true" : "false") + ",\"misc\":" + card.misc + "}";
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
        private final ExecutorService io = Executors.newFixedThreadPool(3, r -> {
            Thread t = new Thread(r, "sts-model-inspector-advisor");
            t.setDaemon(true);
            return t;
        });
        private Process process;
        private BufferedWriter stdin;
        private Thread reader;
        private Thread errorReader;

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
                Process started = new ProcessBuilder(executable).redirectErrorStream(false).start();
                process = started;
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
            io.submit(() -> {
                try {
                    write(s.toJson());
                } catch (Exception e) {
                    advisorStatus = "error";
                    advisorReason = e.getClass().getSimpleName();
                }
            });
        }

        private synchronized void write(String line) throws IOException {
            if (stdin == null) throw new IOException("advisor not connected");
            stdin.write(line);
            stdin.newLine();
            stdin.flush();
        }

        synchronized void shutdown() {
            if (process != null) process.destroy();
            if (reader != null) reader.interrupt();
            if (errorReader != null) errorReader.interrupt();
            io.shutdownNow();
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
                        long seq = numberField(line, "sequence");
                        String hash = field(line, "observationHash");
                        Snapshot current = newest;
                        if (current != null && seq == current.sequence && current.hash.equals(hash)) {
                            responseSequence = seq;
                            responseHash = hash;
                            advisorStatus = status == null ? "error" : status.toLowerCase();
                            advisorReason = reason == null ? "" : reason;
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
    }

    private static final class Snapshot {
        final String session, boundary, character, deck, candidates, hash;
        final long sequence;
        final int ascension, act, floor, hp, maxHp, gold;

        Snapshot(String session, long sequence, String boundary, String character,
                 int ascension, int act, int floor, int hp, int maxHp, int gold,
                 String deck, String candidates, String hash) {
            this.session = session; this.sequence = sequence; this.boundary = boundary;
            this.character = character; this.ascension = ascension; this.act = act;
            this.floor = floor; this.hp = hp; this.maxHp = maxHp; this.gold = gold;
            this.deck = deck; this.candidates = candidates; this.hash = hash;
        }

        String toJson() {
            return "{\"protocol\":\"" + PROTOCOL + "\",\"kind\":\"observation\"" +
                    ",\"session\":\"" + escape(session) + "\",\"sequence\":" + sequence +
                    ",\"observationHash\":\"" + hash + "\",\"observation\":{" +
                    "\"boundary\":\"" + boundary + "\",\"character\":\"" + character +
                    "\",\"ascension\":" + ascension + ",\"act\":" + act +
                    ",\"floor\":" + floor + ",\"hp\":" + hp + ",\"maxHp\":" + maxHp +
                    ",\"gold\":" + gold + ",\"deck\":" + deck +
                    ",\"candidates\":" + candidates + "}}";
        }

        private static String escape(String s) { return s.replace("\\", "\\\\").replace("\"", "\\\""); }
    }
}
