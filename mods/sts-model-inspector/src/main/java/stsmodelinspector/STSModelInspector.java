package stsmodelinspector;

import basemod.BaseMod;
import basemod.interfaces.PostInitializeSubscriber;
import basemod.interfaces.PostUpdateSubscriber;
import basemod.interfaces.RenderSubscriber;
import basemod.interfaces.OnStartBattleSubscriber;
import basemod.interfaces.PostBattleSubscriber;
import com.badlogic.gdx.graphics.Color;
import com.badlogic.gdx.graphics.g2d.SpriteBatch;
import com.megacrit.cardcrawl.cards.DamageInfo;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.cards.AbstractCard;
import com.megacrit.cardcrawl.monsters.AbstractMonster;
import com.megacrit.cardcrawl.powers.AbstractPower;
import com.megacrit.cardcrawl.helpers.FontHelper;
import com.megacrit.cardcrawl.helpers.ImageMaster;
import com.megacrit.cardcrawl.rooms.EventRoom;
import com.megacrit.cardcrawl.rooms.MonsterRoom;
import com.megacrit.cardcrawl.rooms.ShopRoom;
import com.megacrit.cardcrawl.rooms.RestRoom;
import com.megacrit.cardcrawl.rooms.TreasureRoom;
import com.megacrit.cardcrawl.rooms.AbstractRoom;
import com.megacrit.cardcrawl.core.Settings;
import com.megacrit.cardcrawl.ui.panels.EnergyPanel;
import com.evacipated.cardcrawl.modthespire.lib.SpireInitializer;
import org.lwjgl.input.Keyboard;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.lang.reflect.Field;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Properties;

/** Read-only observer. It never calls an AbstractDungeon action or mutates game state. */
@SpireInitializer
public final class STSModelInspector implements PostInitializeSubscriber,
        PostUpdateSubscriber, RenderSubscriber, OnStartBattleSubscriber,
        PostBattleSubscriber {
    private static final String PROTOCOL = "sts_model_inspector_v1";
    private static final int PROTOCOL_VERSION = 1;
    private static final String TOGGLE = "stsmodelinspector.toggle";
    private static int trackedLastUnblockedDamage;
    private static int trackedTimesDamaged;
    private static boolean trackedPlayerVulnerableSeen;
    private static int trackedLastTargetedMonster = 1;

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
    private volatile String advisorResponseJson = "";
    private volatile String ctmStatus = "";
    private volatile String ctmReason = "";
    private volatile String silverStatus = "";
    private volatile String silverReason = "";
    private volatile String silverSelectedAction = "";
    private volatile String silverSelectedLabel = "";
    private volatile String silverRanking = "";
    private volatile int silverPlayerTurn = -1;
    private volatile int silverDecisionInTurn = -1;
    private volatile boolean silverRerootExact;
    private volatile boolean silverEquivalentCopyReroot;
    private volatile boolean silverRerootFallback;
    private volatile String silverFallbackReason = "";
    private volatile long silverInheritedVisits;
    private volatile double ctmDeath = 0.0;
    private volatile int ctmHistogramMin = 1;
    private volatile double[] ctmHistogram = new double[0];
    private volatile boolean panelVisible = true;
    private volatile String combatEntry = "";
    private volatile String combatEntryHash = "";
    private final LatestPublisher latestPublisher = new LatestPublisher();
    private String lastRoomClass = "";
    private String lastNodeRoomClass = "";
    private int lastNodeX = -1, lastNodeY = -1;
    private boolean toggleDown;

    public static void initialize() {
        BaseMod.subscribe(INSTANCE);
    }

    /** Called by the post-AbstractPlayer.damage ModTheSpire patch. */
    static void recordPlayerDamage(DamageInfo info, int finalDamage) {
        if (info == null || AbstractDungeon.player == null
                || AbstractDungeon.currMapNode == null) return;
        if (info.type == DamageInfo.DamageType.HP_LOSS) {
            if (finalDamage > 0) ++trackedTimesDamaged;
            return;
        }
        // lastDamageTaken is assigned by vanilla after block, powers, relics,
        // Buffer, Torii, and Tungsten Rod have resolved.  The patch invokes
        // this once per public damage() call, so multi-hit attacks remain
        // events rather than being collapsed into a turn total.
        trackedLastUnblockedDamage = Math.max(0, finalDamage);
        if (finalDamage > 0) ++trackedTimesDamaged;
    }

    @Override
    public void receiveOnBattleStart(AbstractRoom room) {
        trackedLastUnblockedDamage = 0;
        trackedTimesDamaged = 0;
        trackedPlayerVulnerableSeen = false;
        trackedLastTargetedMonster = 1;
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
        silverStatus = "";
        silverReason = "";
        silverSelectedAction = "";
        silverSelectedLabel = "";
        silverRanking = "";
        silverPlayerTurn = -1;
        silverDecisionInTurn = -1;
        trackedLastUnblockedDamage = 0;
        trackedTimesDamaged = 0;
        trackedPlayerVulnerableSeen = false;
        trackedLastTargetedMonster = 1;
        silverRerootExact = false;
        silverEquivalentCopyReroot = false;
        silverRerootFallback = false;
        silverFallbackReason = "";
        silverInheritedVisits = 0;
        ctmDeath = 0.0;
        ctmHistogram = new double[0];
    }

    private STSModelInspector() {}

    @Override
    public void receivePostInitialize() {
        latestPublisher.start();
        latestPublisher.clear();
        advisor.start();
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            advisor.shutdown();
            latestPublisher.shutdown();
        },
                "sts-model-inspector-shutdown"));
    }

    @Override
    public void receivePostUpdate() {
        trackLastTargetedMonster();
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
                advisorResponseJson = "";
                advisor.clearPending();
                latestPublisher.clear();
            }
            return;
        }
        if (snapshot.hash.equals(lastFingerprint)) return;
        lastFingerprint = snapshot.hash;
        Snapshot emitted = snapshot.withSequence(++sequence);
        newest = emitted;
        responseSequence = -1;
        responseHash = "";
        advisorResponseJson = "";
        if (!"combat".equals(snapshot.boundary)
                || !snapshot.combatEntryHash.equals(combatEntryHash)) {
            ctmStatus = "";
            ctmReason = "";
            ctmDeath = 0.0;
            ctmHistogram = new double[0];
        }
        advisorStatus = "waiting";
        advisorReason = "";
        advisor.send(emitted);
        latestPublisher.publishObservation(emitted);
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
                        String.format("Death chance: %.1f%%", 100.0 * ctmDeath),
                        x, y - 138.0f * Settings.scale, white);
                renderHistogram(sb, x, y - 190.0f * Settings.scale);
            } else if (!ctmReason.isEmpty()) {
                FontHelper.renderFontLeftTopAligned(sb, FontHelper.tipBodyFont, ctmReason,
                        x, y - 138.0f * Settings.scale, Color.ORANGE);
            }
            String silverHeading = "Silver — waiting";
            if (!silverStatus.isEmpty()) {
                String decisionLabel = "turn " + silverPlayerTurn
                        + " decision " + silverDecisionInTurn;
                if ("OK".equals(silverStatus) && silverPlayerTurn == 1
                        && silverDecisionInTurn == 0) {
                    silverHeading = "Silver — " + decisionLabel + " — fresh";
                } else if ("OK".equals(silverStatus)
                        && (silverRerootExact || silverEquivalentCopyReroot)) {
                    silverHeading = "Silver — " + decisionLabel + " — reused "
                            + silverInheritedVisits + " visits";
                } else if ("OK".equals(silverStatus) && silverRerootFallback) {
                    silverHeading = "Silver — " + decisionLabel + " — fresh fallback";
                } else {
                    silverHeading = "Silver — " + silverStatus;
                }
            }
            FontHelper.renderFontLeftTopAligned(sb, FontHelper.tipBodyFont, silverHeading,
                    x, y - 320.0f * Settings.scale, white);
            String silverDetail = !silverReason.isEmpty() ? silverReason
                    : silverRerootFallback ? silverFallbackReason : "";
            if (!silverDetail.isEmpty()) FontHelper.renderFontLeftTopAligned(sb, FontHelper.tipBodyFont,
                    silverDetail, x, y - 342.0f * Settings.scale, Color.ORANGE);
            if (!silverRanking.isEmpty()) {
                int row = 0;
                for (String value : silverRanking.split("\\n")) {
                    String[] fields = value.split("\\|", -1);
                    if (fields.length < 3) continue;
                    FontHelper.renderFontLeftTopAligned(sb, FontHelper.tipBodyFont,
                            (row + 1) + "  " + fields[0] + "  " + fields[1] + " visits  Q " + fields[2],
                            x, y - (364.0f + row * 20.0f) * Settings.scale, white);
                    ++row;
                }
            }
        }
        FontHelper.renderFontLeftTopAligned(sb, FontHelper.tipBodyFont,
                "Toggle: " + Keyboard.getKeyName(loadToggleKey()), x,
                y - ("combat".equals(newest.boundary) ? 470.0f : 94.0f) * Settings.scale, Color.GRAY);
    }

    private void renderHistogram(SpriteBatch sb, float x, float top) {
        if (ctmHistogram.length == 0) return;
        FontHelper.renderFontLeftTopAligned(sb, FontHelper.tipBodyFont,
                "Surviving final HP distribution (absolute)", x, top, Color.WHITE);
        int first = -1;
        int last = -1;
        for (int i = 0; i < ctmHistogram.length; ++i) {
            if (ctmHistogram[i] > 0.000001) {
                if (first < 0) first = i;
                last = i;
            }
        }
        if (first < 0) return;
        final int span = last - first + 1;
        final int buckets = Math.min(16, span);
        double maximum = 0.0;
        for (int bucket = 0; bucket < buckets; ++bucket) {
            int begin = first + bucket * span / buckets;
            int end = first + (bucket + 1) * span / buckets;
            double probability = 0.0;
            for (int i = begin; i < end; ++i) probability += ctmHistogram[i];
            maximum = Math.max(maximum, probability);
        }
        if (maximum <= 0.0) return;
        float chartX = x + 42.0f * Settings.scale;
        float barWidth = 12.0f * Settings.scale;
        // Leave a real gap below the forecast text.  The histogram is a
        // secondary diagnostic, so its title and annotations must not collide
        // with the CTM status lines above it.
        float base = top - 118.0f * Settings.scale;
        float chartHeight = 92.0f * Settings.scale;
        float chartWidth = buckets * barWidth;
        // A faint grid makes the distribution readable without competing with
        // the game scene or the cyan bars.
        sb.setColor(0.55f, 0.85f, 1.0f, 0.20f);
        for (int tick = 0; tick <= 4; ++tick) {
            float gridY = base + chartHeight * tick / 4.0f;
            sb.draw(ImageMaster.WHITE_SQUARE_IMG, chartX, gridY,
                    chartWidth, Settings.scale);
        }
        for (int tick = 0; tick <= 4; ++tick) {
            float gridX = chartX + chartWidth * tick / 4.0f;
            sb.draw(ImageMaster.WHITE_SQUARE_IMG, gridX, base,
                    Settings.scale, chartHeight);
        }
        sb.setColor(Color.WHITE);
        sb.draw(ImageMaster.WHITE_SQUARE_IMG, chartX, base,
                chartWidth, 1.5f * Settings.scale);
        sb.draw(ImageMaster.WHITE_SQUARE_IMG, chartX, base,
                1.5f * Settings.scale, chartHeight);
        float tickScaleX = FontHelper.tipBodyFont.getData().scaleX;
        float tickScaleY = FontHelper.tipBodyFont.getData().scaleY;
        FontHelper.tipBodyFont.getData().setScale(tickScaleX * 0.72f, tickScaleY * 0.72f);
        for (int tick = 0; tick <= 4; ++tick) {
            float gridY = base + chartHeight * tick / 4.0f;
            sb.draw(ImageMaster.WHITE_SQUARE_IMG, chartX - 5.0f * Settings.scale,
                    gridY, 5.0f * Settings.scale, Settings.scale);
            FontHelper.renderFontLeftTopAligned(sb, FontHelper.tipBodyFont,
                    String.format(Locale.ROOT, "%.0f%%", 100.0 * maximum * tick / 4.0),
                    x, gridY + 5.0f * Settings.scale, Color.GRAY);
        }
        for (int bucket = 0; bucket < buckets; ++bucket) {
            int begin = first + bucket * span / buckets;
            int end = first + (bucket + 1) * span / buckets;
            double probability = 0.0;
            for (int i = begin; i < end; ++i) probability += ctmHistogram[i];
            float height = (float) (chartHeight * probability / maximum);
            sb.setColor(Color.CYAN);
            sb.draw(ImageMaster.WHITE_SQUARE_IMG, chartX + bucket * barWidth,
                    base, barWidth - Settings.scale, height);
        }
        sb.setColor(Color.WHITE);
        int firstHp = ctmHistogramMin + first;
        int lastHp = ctmHistogramMin + last;
        float[] xTicks = {0.0f, 0.2f, 0.4f, 0.6f, 0.8f, 1.0f};
        for (int tick = 0; tick < xTicks.length; ++tick) {
            float tickX = chartX + chartWidth * xTicks[tick];
            sb.draw(ImageMaster.WHITE_SQUARE_IMG, tickX, base - 5.0f * Settings.scale,
                    Settings.scale, 5.0f * Settings.scale);
            int hp = firstHp + Math.round((lastHp - firstHp) * xTicks[tick]);
            boolean repeated = tick > 0
                    && hp == firstHp + Math.round((lastHp - firstHp) * xTicks[tick - 1]);
            if (!repeated) {
                FontHelper.renderFontLeftTopAligned(sb, FontHelper.tipBodyFont,
                        Integer.toString(hp), tickX - 4.0f * Settings.scale,
                        base - 18.0f * Settings.scale, Color.GRAY);
            }
        }
        FontHelper.tipBodyFont.getData().setScale(tickScaleX, tickScaleY);
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
        } else if (room instanceof MonsterRoom
                && (isPlayerDecisionPoint() || isCardSelectionBoundary())) {
            boundary = "combat";
        } else {
            return null;
        }
        if ("combat".equals(boundary)) {
            String encounter = encounterName(room);
            if (combatEntry.isEmpty()) {
                // The battle-start callback can run before the map node and
                // monster group are populated. Capture lazily at the first
                // actionable decision so every Silver observation has the
                // same stable combat-entry identity as CTM.
                combatEntry = combatEntryJson(room, encounter);
                combatEntryHash = combatEntry.isEmpty() ? "" : sha256(combatEntry);
            } else if (combatEntry.contains("\"encounter\":\"\"") && !encounter.isEmpty()) {
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
        AbstractRoom mapRoom = AbstractDungeon.currMapNode.room != null
                ? AbstractDungeon.currMapNode.room : AbstractDungeon.getCurrRoom();
        String current = roomClass(mapRoom);
        // The game inserts an EmptyRoom while advancing from boss treasure to
        // the next act.  Native GameContext keeps BOSS_TREASURE as lastRoom;
        // carry that identity across the transitional node.
        if (mapRoom instanceof com.megacrit.cardcrawl.rooms.EmptyRoom
                && "BOSS_TREASURE".equals(lastNodeRoomClass)) {
            current = "BOSS_TREASURE";
        }
        if (x == lastNodeX && y == lastNodeY) return;
        if (lastNodeX >= 0) {
            lastRoomClass = lastNodeRoomClass;
        } else {
            // SaveFile.path_x/path_y are restored into these lists before the
            // room becomes actionable.  The final coordinate is the current
            // node, so a resumed run can recover the actual preceding node
            // without guessing from the encounter or floor number.
            lastRoomClass = previousRoomClassFromPath(x, y);
            if (lastRoomClass.isEmpty()) {
                // NONE is known only at a genuinely fresh run start.  If the
                // persisted path is absent or inconsistent, keep failing
                // closed rather than inventing CTM context.
                boolean freshRun = AbstractDungeon.actNum == 1 && AbstractDungeon.floorNum <= 1;
                lastRoomClass = freshRun ? "NONE" : "";
            }
        }
        lastNodeX = x;
        lastNodeY = y;
        lastNodeRoomClass = current;
    }

    private static String previousRoomClassFromPath(int currentX, int currentY) {
        if (AbstractDungeon.pathX == null || AbstractDungeon.pathY == null
                || AbstractDungeon.map == null
                || AbstractDungeon.pathX.size() != AbstractDungeon.pathY.size()
                || AbstractDungeon.pathX.size() < 2) return "";
        int currentIndex = AbstractDungeon.pathX.size() - 1;
        if (AbstractDungeon.pathX.get(currentIndex) != currentX
                || AbstractDungeon.pathY.get(currentIndex) != currentY) return "";
        int previousX = AbstractDungeon.pathX.get(currentIndex - 1);
        int previousY = AbstractDungeon.pathY.get(currentIndex - 1);
        if (previousY < 0 || previousY >= AbstractDungeon.map.size()) return "";
        List<com.megacrit.cardcrawl.map.MapRoomNode> row = AbstractDungeon.map.get(previousY);
        if (row == null || previousX < 0 || previousX >= row.size()) return "";
        com.megacrit.cardcrawl.map.MapRoomNode previous = row.get(previousX);
        return previous == null || previous.room == null ? "" : roomClass(previous.room);
    }

    private static String roomClass(AbstractRoom room) {
        if (room == null) return "NONE";
        if (room instanceof com.megacrit.cardcrawl.rooms.MonsterRoomBoss) return "BOSS";
        if (room instanceof com.megacrit.cardcrawl.rooms.MonsterRoomElite) return "ELITE";
        if (room instanceof MonsterRoom) return "MONSTER";
        if (room instanceof com.megacrit.cardcrawl.rooms.TreasureRoomBoss) return "BOSS_TREASURE";
        if (room instanceof ShopRoom) return "SHOP";
        if (room instanceof TreasureRoom) return "TREASURE";
        if (room instanceof RestRoom) return "REST";
        if (room instanceof EventRoom) return "EVENT";
        return "NONE";
    }

    private String encounterName(AbstractRoom room) {
        com.megacrit.cardcrawl.monsters.MonsterGroup group = room == null ? null : room.monsters;
        if (group == null) group = AbstractDungeon.getMonsters();
        if (group == null || group.monsters == null || group.monsters.isEmpty()) return "";
        Map<String, Integer> counts = new HashMap<>();
        for (AbstractMonster monster : group.monsters) {
            if (monster == null || monster.id == null) return "";
            Integer count = counts.get(monster.id);
            counts.put(monster.id, count == null ? 1 : count + 1);
        }
        boolean eventRoom = room instanceof EventRoom;
        String multi = multiEncounterName(counts, eventRoom);
        if (!multi.isEmpty()) return multi;
        if (group.monsters.size() != 1) return "";
        String id = group.monsters.get(0).id;
        // AbstractMonster.id is the stable save/runtime identifier.  Do not
        // compare it with MonsterHelper's localized encounter display names.
        if (id.equals("Cultist")) return "CULTIST";
        if (id.equals("JawWorm")) return "JAW_WORM";
        if (id.equals("BlueSlaver")) return "BLUE_SLAVER";
        if (id.equals("Looter")) return "LOOTER";
        if (id.equals("RedSlaver")) return "RED_SLAVER";
        if (id.equals("GremlinNob")) return "GREMLIN_NOB";
        if (id.equals("Lagavulin")) return eventRoom ? "LAGAVULIN_EVENT" : "LAGAVULIN";
        if (id.equals("AcidSlime_L") || id.equals("SpikeSlime_L")) return "LARGE_SLIME";
        if (id.equals("SphericGuardian")) return "SPHERIC_GUARDIAN";
        if (id.equals("Chosen")) return "CHOSEN";
        if (id.equals("ShelledParasite")) return "SHELL_PARASITE";
        if (id.equals("SnakePlant")) return "SNAKE_PLANT";
        if (id.equals("Snecko")) return "SNECKO";
        if (id.equals("Transient")) return "TRANSIENT";
        if (id.equals("Orb Walker")) return "ORB_WALKER";
        if (id.equals("Serpent")) return "SPIRE_GROWTH";
        if (id.equals("Maw")) return "MAW";
        if (id.equals("WrithingMass")) return "WRITHING_MASS";
        if (id.equals("GiantHead")) return "GIANT_HEAD";
        if (id.equals("Nemesis")) return "NEMESIS";
        if (id.equals("SlimeBoss")) return "SLIME_BOSS";
        if (id.equals("TheGuardian")) return "THE_GUARDIAN";
        if (id.equals("Hexaghost")) return "HEXAGHOST";
        if (id.equals("Champ")) return "CHAMP";
        if (id.equals("BookOfStabbing")) return "BOOK_OF_STABBING";
        if (id.equals("BronzeAutomaton")) return "AUTOMATON";
        if (id.equals("TheCollector")) return "COLLECTOR";
        if (id.equals("AwakenedOne")) return "AWAKENED_ONE";
        if (id.equals("TimeEater")) return "TIME_EATER";
        if (id.equals("CorruptHeart")) return "THE_HEART";
        return "";
    }

    private static String multiEncounterName(Map<String, Integer> counts, boolean eventRoom) {
        int total = 0;
        for (Integer value : counts.values()) total += value;
        if (counts.size() == 1) {
            if (count(counts, "Sentry") == 3) return "THREE_SENTRIES";
            if (count(counts, "Cultist") == 3) return "THREE_CULTIST";
            if (count(counts, "Byrd") == 3) return "THREE_BYRDS";
            if (count(counts, "Byrd") == 4) return "FOUR_BYRDS";
            if (count(counts, "Darkling") == 3) return "THREE_DARKLINGS";
            if (count(counts, "FungiBeast") == 2) return "TWO_FUNGI_BEASTS";
            if (count(counts, "FungiBeast") == 3) return "MUSHROOMS_EVENT";
        }
        int louseCount = count(counts, "FuzzyLouseNormal") + count(counts, "FuzzyLouseDefensive");
        int smallSlimes = count(counts, "SpikeSlime_S") + count(counts, "AcidSlime_S");
        int mediumSlimes = count(counts, "SpikeSlime_M") + count(counts, "AcidSlime_M");
        int allSlimes = smallSlimes + mediumSlimes;
        if (smallSlimes == 1 && mediumSlimes == 1 && total == 2) return "SMALL_SLIMES";
        if (allSlimes == 5 && total == 5) return "LOTS_OF_SLIMES";
        if (louseCount == 2 && total == 2) return "TWO_LOUSE";
        if (louseCount == 3 && total == 3) return "THREE_LOUSE";
        if (count(counts, "JawWorm") == 3 && total == 3) return "JAW_WORM_HORDE";
        if (total == 2 && weakWildlifeCount(counts) == 1 && strongHumanoidCount(counts) == 1)
            return "EXORDIUM_THUGS";
        if (total == 2 && weakWildlifeCount(counts) == 1 && strongWildlifeCount(counts) == 1)
            return "EXORDIUM_WILDLIFE";
        if (shapeCount(counts) == 3 && total == 3) return "THREE_SHAPES";
        if (shapeCount(counts) == 4 && total == 4) return "FOUR_SHAPES";
        if (counts.size() == 2) {
            if (count(counts, "Reptomancer") == 1
                    && (count(counts, "SnakeDagger") == 1
                        || count(counts, "SnakeDagger") == 2))
                return "REPTOMANCER";
            if (count(counts, "AwakenedOne") == 1 && count(counts, "Cultist") == 2)
                return "AWAKENED_ONE";
            if (count(counts, "Cultist") == 1 && count(counts, "Chosen") == 1)
                return "CULTIST_AND_CHOSEN";
            if (count(counts, "Chosen") == 1 && count(counts, "Byrd") == 2)
                return "CHOSEN_AND_BYRDS";
            if (count(counts, "Sentry") == 1 && count(counts, "SphericGuardian") == 1)
                return "SENTRY_AND_SPHERE";
            if (count(counts, "Centurion") == 1 && count(counts, "Healer") == 1)
                return "CENTURION_AND_HEALER";
            if (count(counts, "ShelledParasite") == 1 && count(counts, "FungiBeast") == 1)
                return "SHELLED_PARASITE_AND_FUNGI";
            if (count(counts, "Donu") == 1 && count(counts, "Deca") == 1)
                return "DONU_AND_DECA";
            if (count(counts, "SpireShield") == 1 && count(counts, "SpireSpear") == 1)
                return "SHIELD_AND_SPEAR";
            if (count(counts, "Looter") == 1 && count(counts, "Mugger") == 1)
                return "TWO_THIEVES";
            if (count(counts, "Taskmaster") == 1 && count(counts, "GremlinNob") == 1)
                return "COLOSSEUM_EVENT_NOBS";
        }
        if (count(counts, "SlaverBlue") == 1 && count(counts, "SlaverRed") == 1
                && count(counts, "Taskmaster") == 0)
            return "COLOSSEUM_EVENT_SLAVERS";
        if (count(counts, "BanditPointy") == 1 && count(counts, "BanditLeader") == 1
                && count(counts, "BanditBear") == 1)
            return "MASKED_BANDITS_EVENT";
        if (count(counts, "Orb Walker") == 2 && total == 2)
            return "MYSTERIOUS_SPHERE_EVENT";
        if (count(counts, "SphericGuardian") == 1 && shapeCount(counts) == 2 && total == 3)
            return "SPHERE_AND_TWO_SHAPES";
        if (count(counts, "Taskmaster") == 1
                && count(counts, "GremlinNob") == 1 && total == 2)
            return "COLOSSEUM_EVENT_NOBS";
        if (count(counts, "GremlinLeader") == 1 && total == 3) {
            int gremlins = total - count(counts, "GremlinLeader");
            if (gremlins == 2) return "GREMLIN_LEADER";
        }
        if (isGremlinGang(counts)) return "GREMLIN_GANG";
        return "";
    }

    private static int count(Map<String, Integer> counts, String id) {
        Integer value = counts.get(id);
        return value == null ? 0 : value;
    }

    private static int shapeCount(Map<String, Integer> counts) {
        return count(counts, "Exploder") + count(counts, "Repulsor") + count(counts, "Spiker");
    }

    private static int weakWildlifeCount(Map<String, Integer> counts) {
        return count(counts, "FuzzyLouseNormal") + count(counts, "FuzzyLouseDefensive")
                + count(counts, "SpikeSlime_M") + count(counts, "AcidSlime_M");
    }

    private static int strongWildlifeCount(Map<String, Integer> counts) {
        return count(counts, "FungiBeast") + count(counts, "JawWorm");
    }

    private static int strongHumanoidCount(Map<String, Integer> counts) {
        return count(counts, "Cultist") + count(counts, "SlaverBlue")
                + count(counts, "SlaverRed") + count(counts, "Looter");
    }

    private static boolean isGremlinGang(Map<String, Integer> counts) {
        int total = 0;
        for (Map.Entry<String, Integer> entry : counts.entrySet()) {
            String id = entry.getKey();
            if (!id.startsWith("Gremlin") || "GremlinLeader".equals(id)) return false;
            total += entry.getValue();
        }
        return total == 4;
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
                    .append("\",\"data\":").append(relic.counter)
                    .append(",\"usedUp\":").append(relic.usedUp);
            if ("Necronomicon".equals(relic.relicId)) {
                Boolean activated = readBooleanField(relic, "activated");
                if (activated != null) out.append(",\"usedThisTurn\":").append(activated);
            }
            out.append('}');
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
                ",\"cost\":" + card.cost + ",\"costForTurn\":" + card.costForTurn +
                ",\"freeToPlayOnce\":" + (card.freeToPlayOnce ? "true" : "false") +
                ",\"retain\":" + (card.retain ? "true" : "false") + "}";
    }

    private static String cardJson(AbstractCard card, String location) {
        String base = cardJson(card);
        return base.substring(0, base.length() - 1) +
                ",\"location\":\"" + location + "\"}";
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

    private static boolean isCardSelectionBoundary() {
        if (AbstractDungeon.actionManager == null) return false;
        if (AbstractDungeon.screen != AbstractDungeon.CurrentScreen.GRID
                && AbstractDungeon.screen != AbstractDungeon.CurrentScreen.HAND_SELECT)
            return false;
        return cardSelectionJson() != null;
    }

    private static void trackLastTargetedMonster() {
        // BaseMod publishes post-update while the title/menu bootstrap is still
        // active.  getMonsters() dereferences the current room, so do not call
        // it until the dungeon has a map node.
        if (AbstractDungeon.currMapNode == null || AbstractDungeon.actionManager == null
                || AbstractDungeon.getMonsters() == null) return;
        for (com.megacrit.cardcrawl.cards.CardQueueItem item
                : AbstractDungeon.actionManager.cardQueue) {
            if (item == null || item.card == null || item.monster == null) continue;
            int index = AbstractDungeon.getMonsters().monsters.indexOf(item.monster);
            if (index >= 0) trackedLastTargetedMonster = index;
        }
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

    private static boolean isBurningElite() {
        return AbstractDungeon.currMapNode != null
                && AbstractDungeon.currMapNode.hasEmeraldKey;
    }

    private static boolean hasRelic(String id) {
        for (com.megacrit.cardcrawl.relics.AbstractRelic relic : AbstractDungeon.player.relics)
            if (id.equals(relic.relicId)) return true;
        return false;
    }

    private static Integer readIntField(Object object, String... names) {
        if (object == null) return null;
        Class<?> type = object.getClass();
        while (type != null) {
            for (String name : names) {
                try {
                    Field field = type.getDeclaredField(name);
                    field.setAccessible(true);
                    Object value = field.get(object);
                    return value instanceof Number ? ((Number) value).intValue() : null;
                } catch (NoSuchFieldException ignored) {
                    // Continue through the class hierarchy and aliases.
                } catch (IllegalAccessException | SecurityException denied) {
                    return null;
                }
            }
            type = type.getSuperclass();
        }
        return null;
    }

    private static Boolean readBooleanField(Object object, String... names) {
        if (object == null) return null;
        Class<?> type = object.getClass();
        while (type != null) {
            for (String name : names) {
                try {
                    Field field = type.getDeclaredField(name);
                    field.setAccessible(true);
                    Object value = field.get(object);
                    return value instanceof Boolean ? (Boolean) value : null;
                } catch (NoSuchFieldException ignored) {
                    // Continue through the class hierarchy and aliases.
                } catch (IllegalAccessException | SecurityException denied) {
                    return null;
                }
            }
            type = type.getSuperclass();
        }
        return null;
    }

    private static String readStringField(Object object, String... names) {
        if (object == null) return "";
        Class<?> type = object.getClass();
        while (type != null) {
            for (String name : names) {
                try {
                    Field field = type.getDeclaredField(name);
                    field.setAccessible(true);
                    Object value = field.get(object);
                    return value == null ? "" : String.valueOf(value);
                } catch (NoSuchFieldException ignored) {
                    // Continue through the class hierarchy and aliases.
                } catch (IllegalAccessException | SecurityException denied) {
                    return "";
                }
            }
            type = type.getSuperclass();
        }
        return "";
    }

    private static Object readObjectField(Object object, String... names) {
        if (object == null) return null;
        Class<?> type = object.getClass();
        while (type != null) {
            for (String name : names) {
                try {
                    Field field = type.getDeclaredField(name);
                    field.setAccessible(true);
                    return field.get(object);
                } catch (NoSuchFieldException ignored) {
                    // Continue through the class hierarchy and aliases.
                } catch (IllegalAccessException | SecurityException denied) {
                    return null;
                }
            }
            type = type.getSuperclass();
        }
        return null;
    }

    private static Integer monsterMiscInfo(AbstractMonster monster) {
        String id = monster.id;
        if ("FuzzyLouseNormal".equals(id) || "FuzzyLouseDefensive".equals(id))
            return readIntField(monster, "biteDamage", "dmg");
        if ("GremlinWizard".equals(id)) return readIntField(monster, "currentCharge");
        if ("Hexaghost".equals(id)) {
            // Native Silver keeps the per-hit Divider damage in miscInfo. The
            // Java intent damage is the same finalized value once Divider is
            // selected; other Hexaghost moves do not consume miscInfo.
            return monster.nextMove == 1 ? monster.getIntentDmg() : 0;
        }
        if ("TheGuardian".equals(id)) {
            for (AbstractPower power : monster.powers)
                if ("Mode Shift".equals(power.ID)) return power.amount;
            return null;
        }
        if ("BookOfStabbing".equals(id)) return readIntField(monster, "stabCount");
        if ("SlaverRed".equals(id)) {
            Boolean used = readBooleanField(monster, "usedEntangle");
            return used == null ? null : (used ? 1 : 0);
        }
        if ("Champ".equals(id)) {
            Boolean phase2 = readBooleanField(monster, "thresholdReached");
            return phase2 == null ? null : (phase2 ? 1 : 0);
        }
        if ("BronzeOrb".equals(id)) {
            Boolean used = readBooleanField(monster, "usedStasis");
            return used == null ? null : (used ? 1 : 0);
        }
        if ("Spiker".equals(id)) return readIntField(monster, "thornsCount");
        if ("TimeEater".equals(id)) {
            Boolean used = readBooleanField(monster, "usedHaste");
            return used == null ? null : (used ? 1 : 0);
        }
        if ("AwakenedOne".equals(id)) {
            Boolean form1 = readBooleanField(monster, "form1");
            return form1 == null ? null : (form1 ? 0 : 1);
        }
        // Explicit zero is safe only for monsters whose native move logic does
        // not consult miscInfo. Unknown/reflectively inaccessible state is
        // omitted and therefore rejected by the importer.
        if ("Cultist".equals(id) || "JawWorm".equals(id) || "GremlinNob".equals(id)
                || "FungiBeast".equals(id) || "AcidSlime_L".equals(id)
                || "AcidSlime_M".equals(id) || "AcidSlime_S".equals(id)
                || "SpikeSlime_L".equals(id) || "SpikeSlime_M".equals(id)
                || "SpikeSlime_S".equals(id) || "BlueSlaver".equals(id)
                || "Looter".equals(id) || "Mugger".equals(id)
                || "GremlinFat".equals(id) || "GremlinSneaky".equals(id)
                || "GremlinShield".equals(id) || "GremlinThief".equals(id)) return 0;
        return null;
    }

    private static String selectionTask(String text, boolean anyNumber) {
        String lower = text == null ? "" : text.toLowerCase(Locale.ROOT);
        if (lower.contains("exhaust")) return anyNumber ? "EXHAUST_MANY" : "EXHAUST_ONE";
        if (lower.contains("upgrade")) return "ARMAMENTS";
        if (lower.contains("copy") || lower.contains("duplicate")) return "DUAL_WIELD";
        if (lower.contains("top") && lower.contains("draw")) return "HEADBUTT";
        if (lower.contains("discard")) return "GAMBLE";
        if (lower.contains("return") || lower.contains("hand")) return "HOLOGRAM";
        return "";
    }

    private static String selectionJson(String task, boolean anyNumber, int pickCount,
                                        List<AbstractCard> source) {
        StringBuilder out = new StringBuilder("{\"task\":\"")
                .append(task).append("\",\"canPickZero\":false,\"canPickAnyNumber\":")
                .append(anyNumber).append(",\"pickCount\":").append(Math.max(0, pickCount))
                .append(",\"data0\":0,\"setCostToZero\":true,\"selectedBits\":0,\"cards\":[");
        boolean offerCards = "DISCOVERY".equals(task) || "CODEX".equals(task);
        boolean first = true;
        if (offerCards && source != null) {
            int count = 0;
            for (AbstractCard card : source) {
                if (count++ == 3) break;
                if (!first) out.append(',');
                first = false;
                out.append('\"').append(escapeJson(card.cardID)).append('\"');
            }
        }
        return out.append("]}").toString();
    }

    private static String stasisJson() {
        if (AbstractDungeon.getMonsters() != null) {
            for (AbstractMonster monster : AbstractDungeon.getMonsters().monsters) {
                // Bronze Orb's Stasis card is not exposed as a stable public
                // field.  Omit the tracker so the native importer rejects the
                // root instead of accepting an invented empty stasis pile.
                if (monster != null && "BronzeOrb".equals(monster.id)) return null;
            }
        }
        return "[]";
    }

    private static String cardSelectionJson() {
        if (AbstractDungeon.screen == AbstractDungeon.CurrentScreen.GRID
                && AbstractDungeon.gridSelectScreen != null) {
            com.megacrit.cardcrawl.screens.select.GridCardSelectScreen screen =
                    AbstractDungeon.gridSelectScreen;
            Integer amount = readIntField(screen, "numCards", "cardSelectAmount");
            String task = selectionTask(readStringField(screen, "tipMsg", "lastTip"), screen.anyNumber);
            if (task.isEmpty() && screen.forUpgrade) task = "ARMAMENTS";
            if (task.isEmpty()) return null;
            return selectionJson(task, screen.anyNumber, amount == null ? 1 : amount,
                    screen.targetGroup == null ? null : screen.targetGroup.group);
        }
        if (AbstractDungeon.screen == AbstractDungeon.CurrentScreen.HAND_SELECT
                && AbstractDungeon.handCardSelectScreen != null) {
            com.megacrit.cardcrawl.screens.select.HandCardSelectScreen screen =
                    AbstractDungeon.handCardSelectScreen;
            String task = selectionTask(screen.selectionReason, screen.upTo);
            if (task.isEmpty()) return null;
            return selectionJson(task, screen.upTo, screen.numCardsToSelect,
                    AbstractDungeon.player.hand.group);
        }
        return null;
    }

    private static String combatJson() {
        int decisionOrdinal = AbstractDungeon.actionManager.cardsPlayedThisTurn.size();
        String selection = cardSelectionJson();
        String stasis = stasisJson();
        int attacksPlayed = 0;
        int skillsPlayed = 0;
        for (AbstractCard card : AbstractDungeon.actionManager.cardsPlayedThisTurn) {
            if (card.type == AbstractCard.CardType.ATTACK) ++attacksPlayed;
            else if (card.type == AbstractCard.CardType.SKILL) ++skillsPlayed;
        }
        int lastTargetedMonster = trackedLastTargetedMonster;
        for (AbstractPower power : AbstractDungeon.player.powers)
            if ("Vulnerable".equals(power.ID)) trackedPlayerVulnerableSeen = true;
        StringBuilder out = new StringBuilder("{\"turn\":");
        out.append(com.megacrit.cardcrawl.actions.GameActionManager.turn)
                .append(",\"energy\":")
                .append(EnergyPanel.totalCount)
                .append(",\"block\":").append(AbstractDungeon.player.currentBlock)
                .append(",\"cardsPlayedThisTurn\":").append(decisionOrdinal)
                .append(",\"attacksPlayedThisTurn\":").append(attacksPlayed)
                .append(",\"skillsPlayedThisTurn\":").append(skillsPlayed)
                .append(",\"cardsDiscardedThisTurn\":")
                .append(com.megacrit.cardcrawl.actions.GameActionManager.totalDiscardedThisTurn)
                .append(",\"damageTrackingExact\":true")
                .append(",\"lastTargetedMonster\":").append(lastTargetedMonster)
                .append(",\"lastAttackUnblockedDamage\":").append(trackedLastUnblockedDamage)
                .append(",\"timesDamagedThisCombat\":").append(trackedTimesDamaged)
                .append(",\"playerVulnerableSeen\":").append(trackedPlayerVulnerableSeen)
                .append(",\"cardDrawPerTurn\":").append(readIntField(AbstractDungeon.player, "gameHandSize") == null
                        ? 5 : readIntField(AbstractDungeon.player, "gameHandSize"))
                .append(",\"playedThisTurn\":[");
        boolean firstPlayed = true;
        for (AbstractCard card : AbstractDungeon.actionManager.cardsPlayedThisTurn) {
            if (!firstPlayed) out.append(',');
            firstPlayed = false;
            out.append(cardJson(card));
        }
        out.append("]")
                .append(",\"playerPowers\":[");
        boolean firstPower = true;
        for (AbstractPower power : AbstractDungeon.player.powers) {
            if (!firstPower) out.append(',');
            firstPower = false;
            String powerId = power.ID;
            out.append("{\"id\":\"").append(escapeJson(powerId))
                    .append("\",\"amount\":").append(power.amount);
            // Several native statuses have a turn-local justApplied bit.  It
            // is private in vanilla powers, so emit it only when reflection
            // can read the actual field; the importer remains fail-closed if
            // a required power does not expose it.
            Boolean justApplied = readBooleanField(power, "justApplied");
            if (justApplied != null) out.append(",\"justApplied\":").append(justApplied);
            if (powerId.startsWith("TheBomb")) {
                Integer damage = readIntField(power, "damage");
                if (damage != null) out.append(",\"bombDamage\":").append(damage);
            }
            out.append('}');
        }
        out.append("]");
        for (AbstractPower power : AbstractDungeon.player.powers) {
            if ("Combust".equals(power.ID)) {
                Integer value = readIntField(power, "hpLoss");
                if (value != null) out.append(",\"combustHpLoss\":").append(value);
            } else if ("Echo Form".equals(power.ID) || "EchoFormPower".equals(power.ID)) {
                Integer value = readIntField(power, "cardsDoubled", "cardsPlayed");
                if (value != null) out.append(",\"echoFormCardsDoubled\":").append(value);
            } else if ("Panache".equals(power.ID)) {
                Integer value = readIntField(power, "panacheCounter", "cardsUntilTrigger");
                if (value != null) out.append(",\"panacheCounter\":").append(value);
            } else if ("Deva Form".equals(power.ID) || "DevaFormPower".equals(power.ID)) {
                Integer value = readIntField(power, "energyPerTurn", "energyAmount");
                if (value != null) out.append(",\"devaFormEnergyPerTurn\":").append(value);
            } else if ("Orange Pellets".equals(power.ID) || "OrangePelletsPower".equals(power.ID)) {
                int cardTypes = 0;
                for (AbstractCard card : AbstractDungeon.actionManager.cardsPlayedThisTurn) {
                    if (card.type == AbstractCard.CardType.ATTACK) cardTypes |= 1;
                    else if (card.type == AbstractCard.CardType.SKILL) cardTypes |= 2;
                    else if (card.type == AbstractCard.CardType.POWER) cardTypes |= 4;
                }
                out.append(",\"orangePelletsCardTypesPlayed\":")
                        .append(cardTypes == 7 ? 0 : cardTypes);
            }
        }
        out.append(",\"cardSelect\":").append(selection == null ? "false" : selection)
                .append(",\"resolving\":false")
                .append(",\"runicDome\":").append(hasRunicDome())
                .append(",\"frozenEye\":").append(hasRelic("Frozen Eye"))
                .append(",\"hand\":[");
        boolean first = true;
        for (AbstractCard card : AbstractDungeon.player.hand.group) {
            if (!first) out.append(',');
            first = false;
            out.append(cardJson(card, "HAND"));
        }
        out.append("],\"draw\":[");
        first = true;
        List<AbstractCard> draw = new ArrayList<>(AbstractDungeon.player.drawPile.group);
        Collections.sort(draw, Comparator.comparing((AbstractCard card) -> card.cardID)
                .thenComparing(card -> String.valueOf(card.uuid))
                .thenComparingInt(card -> card.misc));
        for (AbstractCard card : draw) {
            if (!first) out.append(',');
            first = false;
            out.append(cardJson(card, "DRAW"));
        }
        out.append("],\"discard\":[");
        first = true;
        for (AbstractCard card : AbstractDungeon.player.discardPile.group) {
            if (!first) out.append(',');
            first = false;
            out.append(cardJson(card, "DISCARD"));
        }
        out.append("],\"exhaust\":[");
        first = true;
        for (AbstractCard card : AbstractDungeon.player.exhaustPile.group) {
            if (!first) out.append(',');
            first = false;
            out.append(cardJson(card, "EXHAUST"));
        }
        out.append("],\"limbo\":[");
        first = true;
        for (AbstractCard card : AbstractDungeon.player.limbo.group) {
            if (!first) out.append(',');
            first = false;
            out.append(cardJson(card, "LIMBO"));
        }
        out.append("],\"stasis\":").append(stasis == null ? "null" : stasis)
                .append(",\"monsters\":[");
        first = true;
        boolean runicDome = hasRunicDome();
        if (AbstractDungeon.getMonsters() != null) {
            for (AbstractMonster monster : AbstractDungeon.getMonsters().monsters) {
                if (monster == null) continue;
                if (!first) out.append(',');
                first = false;
                out.append("{\"id\":\"").append(escapeJson(monster.id))
                        .append("\",\"hp\":").append(monster.currentHealth)
                        .append(",\"maxHp\":").append(monster.maxHealth)
                        .append(",\"block\":").append(monster.currentBlock)
                        .append(",\"dead\":").append(monster.isDeadOrEscaped())
                        .append(",\"escaping\":").append(monster.escaped)
                        .append(",\"nextMove\":").append(monster.nextMove)
                        .append(",\"moveHistory\":[");
                int historyStart = Math.max(0, monster.moveHistory.size() - 2);
                for (int historyIndex = historyStart; historyIndex < monster.moveHistory.size(); ++historyIndex) {
                    if (historyIndex > historyStart) out.append(',');
                    out.append(monster.moveHistory.get(historyIndex));
                }
                out.append(']')
                        .append(",\"powers\":[");
                boolean firstMonsterPower = true;
                for (AbstractPower power : monster.powers) {
                    if (!firstMonsterPower) out.append(',');
                    firstMonsterPower = false;
                    out.append("{\"id\":\"").append(escapeJson(power.ID))
                            .append("\",\"amount\":").append(power.amount).append('}');
                }
                out.append(']');
                Integer miscInfo = monsterMiscInfo(monster);
                if (miscInfo != null) out.append(",\"miscInfo\":").append(miscInfo);
                if (!runicDome) {
                    out.append(",\"intent\":\"")
                            .append(escapeJson(monster.intent == null ? "UNKNOWN" : monster.intent.name()))
                            .append("\",\"intentDamage\":").append(monster.getIntentDmg());
                }
                out.append('}');
            }
        }
        out.append("],\"lastCard\":");
        AbstractCard lastCard = AbstractDungeon.actionManager.lastCard;
        if (decisionOrdinal > 0 && lastCard != null) {
            String serialized = cardJson(lastCard);
            out.append(serialized, 0, serialized.length() - 1)
                    .append(",\"target\":0,\"energyOnUse\":")
                    .append(EnergyPanel.totalCount + lastCard.costForTurn).append('}');
        } else out.append("null");
        out.append(",\"relics\":[");
        first = true;
        for (com.megacrit.cardcrawl.relics.AbstractRelic relic : AbstractDungeon.player.relics) {
            if (!first) out.append(',');
            first = false;
            out.append("{\"id\":\"").append(escapeJson(relic.relicId))
                    .append("\",\"counter\":").append(relic.counter)
                    .append(",\"usedUp\":").append(relic.usedUp);
            if ("Necronomicon".equals(relic.relicId)) {
                Boolean activated = readBooleanField(relic, "activated");
                if (activated != null) out.append(",\"usedThisTurn\":").append(activated);
            }
            out.append('}');
        }
        out.append("],\"potions\":[");
        first = true;
        for (int slot = 0; slot < AbstractDungeon.player.potionSlots; ++slot) {
            if (!first) out.append(',');
            first = false;
            String id = "Potion Slot";
            if (slot < AbstractDungeon.player.potions.size()
                    && AbstractDungeon.player.potions.get(slot) != null)
                id = AbstractDungeon.player.potions.get(slot).ID;
            out.append("{\"slot\":").append(slot).append(",\"id\":\"")
                    .append(escapeJson(id)).append("\"}");
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
                            ctmStatus = "";
                            ctmReason = "";
                            ctmDeath = 0.0;
                            ctmHistogramMin = 1;
                            ctmHistogram = new double[0];
                            silverStatus = "";
                            silverReason = "";
                            silverSelectedAction = "";
                            silverSelectedLabel = "";
                            silverRanking = "";
                            silverPlayerTurn = -1;
                            silverDecisionInTurn = -1;
                            silverRerootExact = false;
                            silverEquivalentCopyReroot = false;
                            silverRerootFallback = false;
                            silverFallbackReason = "";
                            silverInheritedVisits = 0;
                            responseSequence = seq;
                            responseHash = hash;
                            advisorResponseJson = line;
                            advisorStatus = status == null ? "error" : status.toLowerCase();
                            if ("MODEL_UNAVAILABLE".equals(status)
                                    || "SCHEMA_MISMATCH".equals(status)) {
                                ctmStatus = status.toLowerCase().replace('_', ' ');
                                ctmReason = reason == null ? ctmStatus : reason;
                            }
                            if ("ERROR".equals(status)) {
                                advisorReason = (code == null ? "UNKNOWN" : code) +
                                        (message == null || message.isEmpty() ? "" : " - " + message);
                                if ("combat".equals(current.boundary) && ctmStatus.isEmpty()) {
                                    ctmStatus = code == null ? "error" : code.toLowerCase();
                                    ctmReason = message == null ? advisorReason : message;
                                }
                            } else {
                                advisorReason = reason == null ? "" : reason;
                            }
                            if (line.contains("\"id\":\"silver_player_decision_v2\"")) {
                                silverStatus = field(line, "silverStatus");
                                silverReason = field(line, "silverReason");
                                silverSelectedAction = field(line, "selectedAction");
                                silverSelectedLabel = field(line, "selectedLabel");
                                silverRanking = field(line, "silverRanking");
                                silverPlayerTurn = (int) numberField(line, "playerTurn");
                                silverDecisionInTurn = (int) numberField(line, "decisionInTurn");
                                silverRerootExact = booleanField(line, "exact");
                                silverEquivalentCopyReroot = booleanField(line, "equivalentCopy");
                                silverRerootFallback = booleanField(line, "fallback");
                                silverFallbackReason = field(line, "fallbackReason");
                                silverInheritedVisits = numberField(line, "inheritedVisits");
                                if (silverRanking != null) silverRanking = silverRanking.replace("\\n", "\n");
                            }
                            if (line.contains("\"id\":\"ctm_combat_entry_v2\"")) {
                                if (line.contains("\"status\":\"UNSUPPORTED\"")) {
                                    ctmStatus = "unsupported";
                                    ctmReason = reason == null ? "unsupported" : reason;
                                } else if (line.contains("\"deathProbability\":")) {
                                    ctmStatus = "OK";
                                    ctmDeath = doubleField(line, "deathProbability");
                                    ctmHistogramMin = (int) numberField(line, "winningHpHistogramMin");
                                    ctmHistogram = numberArrayField(line, "winningHpHistogram");
                                }
                            }
                            latestPublisher.publishResponse(current);
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

        private boolean booleanField(String json, String key) {
            String needle = "\"" + key + "\":";
            int start = json.indexOf(needle);
            if (start < 0) return false;
            start += needle.length();
            return json.startsWith("true", start);
        }

        private double[] numberArrayField(String json, String key) {
            String needle = "\"" + key + "\":[";
            int start = json.indexOf(needle);
            if (start < 0) return new double[0];
            start += needle.length();
            int end = json.indexOf(']', start);
            if (end < 0) return new double[0];
            String values = json.substring(start, end).trim();
            if (values.isEmpty()) return new double[0];
            String[] parts = values.split(",");
            double[] result = new double[parts.length];
            try {
                for (int i = 0; i < parts.length; ++i) result[i] = Double.parseDouble(parts[i]);
                return result;
            } catch (NumberFormatException error) {
                return new double[0];
            }
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

    private final class LatestPublisher {
        private final Path path = Paths.get(System.getProperty("user.home"),
                ".cache", "sts-model-inspector", "latest.json");
        private final Object lock = new Object();
        private Publication pending;
        private Thread worker;
        private boolean stopping;
        private long generation;
        private Snapshot current;

        void start() {
            synchronized (lock) {
                if (worker != null) return;
                stopping = false;
                worker = new Thread(this::run, "sts-model-inspector-latest-json");
                worker.setDaemon(true);
                worker.start();
            }
        }

        void publishObservation(Snapshot snapshot) {
            if (snapshot == null) return;
            synchronized (lock) {
                if (stopping) return;
                ++generation;
                current = snapshot;
                pending = new Publication(generation, latestJson(snapshot), false);
                lock.notifyAll();
            }
        }

        void publishResponse(Snapshot snapshot) {
            if (snapshot == null) return;
            synchronized (lock) {
                if (stopping || current == null || !sameIdentity(current, snapshot)) return;
                pending = new Publication(generation, latestJson(snapshot), false);
                lock.notifyAll();
            }
        }

        void clear() {
            synchronized (lock) {
                if (stopping) return;
                ++generation;
                current = null;
                pending = new Publication(generation, "", true);
                lock.notifyAll();
            }
        }

        void shutdown() {
            Thread thread;
            synchronized (lock) {
                ++generation;
                current = null;
                stopping = true;
                pending = null;
                lock.notifyAll();
                thread = worker;
            }
            if (thread != null) {
                thread.interrupt();
                try { thread.join(2000L); } catch (InterruptedException ignored) {
                    Thread.currentThread().interrupt();
                }
            }
            try { Files.deleteIfExists(path); } catch (IOException ignored) {
                // Export is diagnostic-only and must never affect shutdown.
            }
        }

        private void run() {
            while (true) {
                Publication publication;
                synchronized (lock) {
                    while (pending == null && !stopping) {
                        try { lock.wait(); } catch (InterruptedException ignored) {}
                    }
                    if (pending == null && stopping) return;
                    publication = pending;
                    pending = null;
                }
                Path temporary = null;
                try {
                    if (!publication.delete) {
                        Files.createDirectories(path.getParent());
                        temporary = path.resolveSibling(path.getFileName().toString()
                                + ".tmp-" + Long.toHexString(System.nanoTime()));
                        Files.write(temporary, publication.json.getBytes(StandardCharsets.UTF_8));
                    }

                    synchronized (lock) {
                        if (publication.generation != generation) {
                            if (temporary != null) Files.deleteIfExists(temporary);
                        } else if (publication.delete) {
                            Files.deleteIfExists(path);
                        } else {
                            try {
                                Files.move(temporary, path,
                                        java.nio.file.StandardCopyOption.ATOMIC_MOVE,
                                        java.nio.file.StandardCopyOption.REPLACE_EXISTING);
                            } catch (java.nio.file.AtomicMoveNotSupportedException unsupported) {
                                Files.move(temporary, path,
                                        java.nio.file.StandardCopyOption.REPLACE_EXISTING);
                            }
                            temporary = null;
                        }
                    }
                } catch (IOException ignored) {
                    // Export is diagnostic-only and must never affect gameplay.
                } finally {
                    if (temporary != null) {
                        try { Files.deleteIfExists(temporary); }
                        catch (IOException ignored) {}
                    }
                }
                synchronized (lock) {
                    if (stopping && pending == null) return;
                }
            }
        }

        private boolean sameIdentity(Snapshot left, Snapshot right) {
            return left.session.equals(right.session)
                    && left.sequence == right.sequence
                    && left.hash.equals(right.hash);
        }

        private String latestJson(Snapshot snapshot) {
            boolean ready = responseSequence == snapshot.sequence
                    && responseHash.equals(snapshot.hash);
            String status = ready ? advisorStatus.toUpperCase(Locale.ROOT) : "WAITING";
            String reason = ready ? advisorReason : "awaiting matching advisor response";
            String responseObservationHash = ready ? responseHash : "";
            StringBuilder out = new StringBuilder();
            out.append("{\"protocol\":\"sts_model_inspector_latest_v1\",\"protocolVersion\":1")
                    .append(",\"session\":\"").append(Snapshot.escape(snapshot.session))
                    .append("\",\"sequence\":").append(snapshot.sequence)
                    .append(",\"observationHash\":\"").append(Snapshot.escape(snapshot.hash))
                    .append("\",\"observation\":").append(snapshot.observationJson)
                    .append(",\"response\":{\"status\":\"").append(Snapshot.escape(status))
                    .append("\",\"ready\":").append(ready)
                    .append(",\"session\":\"").append(ready ? Snapshot.escape(snapshot.session) : "")
                    .append("\",\"sequence\":").append(ready ? snapshot.sequence : -1)
                    .append(",\"observationHash\":\"").append(Snapshot.escape(responseObservationHash))
                    .append("\",\"reason\":\"").append(Snapshot.escape(reason == null ? "" : reason))
                    .append("\",\"advisor\":");
            return out.append(ready && !advisorResponseJson.isEmpty()
                    ? advisorResponseJson : "null").append("}}").toString();
        }

        private final class Publication {
            final long generation;
            final String json;
            final boolean delete;
            Publication(long generation, String json, boolean delete) {
                this.generation = generation;
                this.json = json;
                this.delete = delete;
            }
        }
    }

    private static final class Snapshot {
        final String session, boundary, character, deck, candidates, hash;
        final String combat;
        final String combatEntry, combatEntryHash;
        final String observationJson;
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
            this.observationJson = buildObservationJson();
        }

        Snapshot withSequence(long emittedSequence) {
            return new Snapshot(session, emittedSequence, boundary, character, ascension, act,
                    floor, hp, maxHp, gold, deck, candidates, combat, combatEntry,
                    combatEntryHash, hash);
        }

        String toJson() {
            return "{\"protocol\":\"" + PROTOCOL + "\",\"kind\":\"observation\"" +
                    ",\"session\":\"" + escape(session) + "\",\"sequence\":" + sequence +
                    ",\"observationHash\":\"" + hash + "\",\"observation\":" + observationJson +
                    "}";
        }

        private String buildObservationJson() {
            return "{\"boundary\":\"" + boundary + "\",\"character\":\"" + character +
                    "\",\"ascension\":" + ascension + ",\"act\":" + act +
                    ",\"floor\":" + floor + ",\"hp\":" + hp + ",\"maxHp\":" + maxHp +
                    ",\"gold\":" + gold + ",\"deck\":" + deck +
                    ",\"candidates\":" + candidates +
                    (combat.isEmpty() ? "" : ",\"combat\":" + combat
                        + ",\"combatEntryHash\":\"" + combatEntryHash + "\""
                        + (combatEntry.isEmpty() ? "" : ",\"combatEntry\":" + combatEntry)
                        + (combatEntry.isEmpty() ? "" : ",\"silverRoot\":{\"schemaVersion\":4,\"playerTurn\":"
                            + com.megacrit.cardcrawl.actions.GameActionManager.turn
                            + ",\"decisionInTurn\":" + playedDecisionOrdinal(combat) + ",\"character\":\""
                            + character + "\",\"ascension\":" + ascension + ",\"act\":" + act
                            + ",\"floor\":" + floor + ",\"hp\":" + hp + ",\"maxHp\":" + maxHp
                            + ",\"gold\":" + gold + ",\"potionCapacity\":" +
                            AbstractDungeon.player.potionSlots + ",\"roomClass\":\"" +
                            roomClass(AbstractDungeon.getCurrRoom()) + "\",\"burningElite\":" +
                            isBurningElite() + ",\"combatInstance\":\"" + escape(combatEntryHash)
                            + "\",\"encounter\":\"" + escape(entryEncounter(combatEntry))
                            + "\",\"combat\":" + combat + "}")) + "}";
        }

        private static int playedDecisionOrdinal(String combatJson) {
            String needle = "\"cardsPlayedThisTurn\":";
            int start = combatJson.indexOf(needle);
            if (start < 0) return -1;
            start += needle.length();
            int end = start;
            while (end < combatJson.length() && Character.isDigit(combatJson.charAt(end))) ++end;
            try { return Integer.parseInt(combatJson.substring(start, end)); }
            catch (Exception error) { return -1; }
        }

        private static String entryEncounter(String entryJson) {
            String needle = "\"encounter\":\"";
            int start = entryJson.indexOf(needle);
            if (start < 0) return "";
            start += needle.length();
            int end = entryJson.indexOf('"', start);
            return end < 0 ? "" : entryJson.substring(start, end);
        }

        private static String escape(String s) {
            return s.replace("\\", "\\\\").replace("\"", "\\\"")
                    .replace("\n", "\\n").replace("\r", "\\r");
        }
    }
}
