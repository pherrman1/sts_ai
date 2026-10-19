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
import com.megacrit.cardcrawl.cards.CardQueueItem;
import com.megacrit.cardcrawl.map.MapRoomNode;
import com.megacrit.cardcrawl.monsters.AbstractMonster;
import com.megacrit.cardcrawl.powers.AbstractPower;
import com.megacrit.cardcrawl.helpers.FontHelper;
import com.megacrit.cardcrawl.helpers.ImageMaster;
import com.megacrit.cardcrawl.helpers.input.InputHelper;
import com.megacrit.cardcrawl.rooms.EventRoom;
import com.megacrit.cardcrawl.rooms.MonsterRoom;
import com.megacrit.cardcrawl.rooms.ShopRoom;
import com.megacrit.cardcrawl.rooms.RestRoom;
import com.megacrit.cardcrawl.rooms.TreasureRoom;
import com.megacrit.cardcrawl.rooms.AbstractRoom;
import com.megacrit.cardcrawl.core.CardCrawlGame;
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
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.HashSet;
import java.util.Properties;

/** Read-only observer. It never calls an AbstractDungeon action or mutates game state. */
@SpireInitializer
public final class STSModelInspector implements PostInitializeSubscriber,
        PostUpdateSubscriber, RenderSubscriber, OnStartBattleSubscriber,
        PostBattleSubscriber {
    private static final String PROTOCOL = "sts_model_inspector_v1";
    private static final int PROTOCOL_VERSION = 1;
    private static final long DEFAULT_SILVER_SEARCH_BUDGET = 1000L;
    private static final float SILVER_BOOST_BUTTON_X = 16.0f;
    private static final float SILVER_BOOST_BUTTON_WIDTH = 90.0f;
    private static final float COMBAT_PANEL_HEIGHT = 288.0f;
    private static final float SILVER_BOOST_BUTTON_BOTTOM = 12.0f;
    private static final float GRAPH_BUTTON_WIDTH = 112.0f;
    private static final String TOGGLE = "stsmodelinspector.toggle";
    private static final Color PANEL_BACKGROUND = new Color(0.015f, 0.075f, 0.115f, 0.96f);
    private static final Color PANEL_INNER = new Color(0.02f, 0.12f, 0.18f, 0.94f);
    private static final Color CARD_BACKGROUND = new Color(0.015f, 0.10f, 0.16f, 0.92f);
    private static final Color CARD_BORDER = new Color(0.10f, 0.48f, 0.66f, 0.85f);
    private static final Color CYAN = new Color(0.0f, 0.92f, 0.88f, 1.0f);
    private static final Color CYAN_DIM = new Color(0.0f, 0.62f, 0.68f, 1.0f);
    private static final Color MUTED = new Color(0.60f, 0.76f, 0.82f, 1.0f);
    private static final Color WARNING = new Color(1.0f, 0.67f, 0.20f, 1.0f);
    private static final Color DEATH = new Color(0.86f, 0.24f, 0.24f, 1.0f);
    private static int trackedLastUnblockedDamage;
    private static int trackedTimesDamaged;
    private static boolean trackedPlayerVulnerableSeen;
    private static AbstractMonster trackedLastTargetedMonster;
    private static final TrackedCardQueueItem trackedLastCardQueueItem =
            new TrackedCardQueueItem();
    // AbstractMonster has no stable public slot number.  Keep object identity
    // for the life of one combat so a surviving monster is never renumbered
    // merely because another list entry died or escaped.  A newly-created
    // object may reuse the current Java list position only when that position
    // is not occupied by a live object in the current snapshot.
    private static final IdentityHashMap<AbstractMonster, Integer> monsterSlots =
            new IdentityHashMap<>();
    private static final Set<AbstractMonster> replacedMonsterParents =
            Collections.newSetFromMap(new IdentityHashMap<AbstractMonster, Boolean>());
    private static final IdentityHashMap<AbstractMonster, Integer> hexaghostDividerDamage =
            new IdentityHashMap<>();

    /**
     * Vanilla removes a CardQueueItem before the stable player boundary is
     * published.  Retain the item while it is public so v4 can describe the
     * exact item that was processed, including the resolved target object.
     */
    private static final class TrackedCardQueueItem {
        boolean present;
        String cardJson;
        AbstractCard physicalCard;
        CardQueueItem physicalItem;
        int target;
        int energyOnUse;
        boolean isEndTurn;
        boolean triggerOnUse = true;
        boolean ignoreEnergyTotal;
        boolean freeToPlay;
        boolean randomTarget;
        boolean autoplay;
        int regretCardCount;
        boolean purgeOnUse;
        boolean exhaustOnUse;

        void clear() {
            present = false;
            cardJson = null;
            physicalCard = null;
            physicalItem = null;
            target = 0;
            energyOnUse = 0;
            isEndTurn = false;
            triggerOnUse = true;
            ignoreEnergyTotal = false;
            freeToPlay = false;
            randomTarget = false;
            autoplay = false;
            regretCardCount = 0;
            purgeOnUse = false;
            exhaustOnUse = false;
        }
    }

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
    private volatile long silverTotalSimulations;
    private volatile long silverRootVisits;
    private long silverSearchBudget = DEFAULT_SILVER_SEARCH_BUDGET;
    private String silverBudgetStateFingerprint = "";
    private volatile CombatHpOverlay combatHpOverlay;
    private volatile OocOverlay oocOverlay;
    private OocOverlay.Choice hoveredOocChoice;
    private volatile PotionOverlay potionOverlay;
    private volatile boolean panelVisible = true;
    private volatile boolean showAdvisorPanel = true;
    private volatile boolean showActionRecommendations = true;
    private volatile boolean showSelectedActionSummary = true;
    private volatile String combatEntry = "";
    private volatile String combatEntryHash = "";
    private final LatestPublisher latestPublisher = new LatestPublisher();
    private String lastRoomClass = "";
    private String lastNodeRoomClass = "";
    private int lastNodeX = -1, lastNodeY = -1;
    private static String liveEncounter = "";
    private boolean toggleDown;
    private volatile String graphStatus = "";
    private volatile boolean graphExportRunning;
    private float graphButtonX = Float.NaN;
    private float graphButtonBottom = Float.NaN;
    private long graphButtonLayoutSequence = -1;

    private void resetSilverBudget() {
        silverSearchBudget = DEFAULT_SILVER_SEARCH_BUDGET;
        silverBudgetStateFingerprint = "";
        silverTotalSimulations = 0;
        silverRootVisits = 0;
    }

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
        resetSilverBudget();
        monsterSlots.clear();
        replacedMonsterParents.clear();
        hexaghostDividerDamage.clear();
        liveEncounter = encounterName(room);
        trackedLastUnblockedDamage = 0;
        trackedTimesDamaged = 0;
        trackedPlayerVulnerableSeen = false;
        trackedLastTargetedMonster = null;
        trackedLastCardQueueItem.clear();
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
        RunicDomeCapture.clear();
        resetSilverBudget();
        monsterSlots.clear();
        replacedMonsterParents.clear();
        hexaghostDividerDamage.clear();
        liveEncounter = "";
        combatEntry = "";
        combatEntryHash = "";
        combatHpOverlay = null;
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
        trackedLastTargetedMonster = null;
        trackedLastCardQueueItem.clear();
        silverRerootExact = false;
        silverEquivalentCopyReroot = false;
        silverRerootFallback = false;
        silverFallbackReason = "";
        silverInheritedVisits = 0;
        silverTotalSimulations = 0;
        silverRootVisits = 0;
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
        observeRoomTransition();
        boolean down = Keyboard.isKeyDown(loadToggleKey());
        if (down && !toggleDown) panelVisible = !panelVisible;
        toggleDown = down;
        handleSilverBoostClick();
        handleGraphButtonClick();

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
        if ("combat".equals(snapshot.boundary)
                && snapshot.silverSearchBudget == DEFAULT_SILVER_SEARCH_BUDGET) {
            silverTotalSimulations = 0;
            silverRootVisits = 0;
        }
        newest = emitted;
        responseSequence = -1;
        responseHash = "";
        advisorResponseJson = "";
        advisorStatus = "waiting";
        advisorReason = "";
        advisor.send(emitted);
        latestPublisher.publishObservation(emitted);
    }

    @Override
    public void receiveRender(SpriteBatch sb) {
        if (!panelVisible || newest == null) return;
        float scale = Settings.scale;
        hoveredOocChoice = null;
        if (showAdvisorPanel) {
            renderAdvisorPanel(sb);
        } else {
            renderStandaloneControls(sb, scale);
            if (showActionRecommendations) {
                if ("combat".equals(newest.boundary)) renderSilverActionBadges(sb, scale);
                else renderInlineChoices(sb, currentOocOverlay(), scale);
            }
        }
        if (showActionRecommendations) renderPotionBadges(sb, scale);
        sb.setColor(Color.WHITE);
    }

    private void renderStandaloneControls(SpriteBatch sb, float scale) {
        graphButtonX = 24.0f * scale;
        graphButtonBottom = 12.0f * scale;
        graphButtonLayoutSequence = newest.sequence;
        renderGraphButton(sb, graphButtonX, graphButtonBottom, scale);
        if ("combat".equals(newest.boundary))
            renderSilverBoostButton(sb, 24.0f * scale + (GRAPH_BUTTON_WIDTH + 8.0f) * scale,
                    graphButtonBottom, scale);
    }

    private void renderAdvisorPanel(SpriteBatch sb) {
        float scale = Settings.scale;
        float x = 24.0f * scale;
        float top = Settings.HEIGHT - 170.0f * scale;
        boolean combat = "combat".equals(newest.boundary);
        OocOverlay overlay = currentOocOverlay();
        boolean inlineOoc = showActionRecommendations && !combat && renderInlineChoices(sb, overlay, scale);
        if (inlineOoc && (overlay == null || overlay.distribution == null)) {
            graphButtonX = 24.0f * scale;
            graphButtonBottom = 50.0f * scale;
            graphButtonLayoutSequence = newest.sequence;
            renderGraphButton(sb, graphButtonX, graphButtonBottom, scale);
            sb.setColor(Color.WHITE);
            return;
        }
        float width = (combat ? 500.0f : 420.0f) * scale;
        int rows = overlay == null || inlineOoc ? 0 : overlay.panelChoices().size();
        boolean histogram = !combat && overlay != null && overlay.distribution != null;
        float height = (combat ? COMBAT_PANEL_HEIGHT : histogram ? 292.0f + 54.0f * rows
                : rows == 0 ? 220.0f : 136.0f + 54.0f * rows) * scale;
        float bottom = top - height;

        // Use the game's existing white texture for the glass panels so the mod
        // stays self-contained and scales with the game's UI coordinates.
        drawRect(sb, x + 5.0f * scale, bottom - 5.0f * scale, width, height,
                new Color(0.0f, 0.0f, 0.0f, 0.42f));
        drawRect(sb, x, bottom, width, height, PANEL_BACKGROUND);
        drawBorder(sb, x, bottom, width, height, CYAN_DIM, 1.5f * scale);
        drawRect(sb, x + 1.5f * scale, top - 56.0f * scale,
                width - 3.0f * scale, 54.0f * scale, PANEL_INNER);
        drawRect(sb, x + 2.0f * scale, top - 3.0f * scale,
                width - 4.0f * scale, 2.0f * scale, CYAN_DIM);

        renderAdvisorIcon(sb, x + 16.0f * scale, top - 18.0f * scale, scale);
        renderHeaderText(sb, combat ? "STS Model Advisor" : "OOC Advisor", x + 70.0f * scale,
                top - 14.0f * scale, Color.WHITE, 0.82f);
        renderStatusPill(sb, x + width - 164.0f * scale, top - 12.0f * scale, scale);
        renderGearIcon(sb, x + width - 31.0f * scale, top - 27.0f * scale, scale);

        if ("combat".equals(newest.boundary)) {
            renderCombatPanel(sb, x, top, width, bottom, scale);
            if (showActionRecommendations) renderSilverActionBadges(sb, scale);
        } else {
            renderNonCombatPanel(sb, x, top, width, bottom, scale, inlineOoc);
        }
        graphButtonX = x + (SILVER_BOOST_BUTTON_X + SILVER_BOOST_BUTTON_WIDTH + 10.0f) * scale;
        graphButtonBottom = bottom + SILVER_BOOST_BUTTON_BOTTOM * scale;
        graphButtonLayoutSequence = newest.sequence;
        renderGraphButton(sb, graphButtonX, graphButtonBottom, scale);
        sb.setColor(Color.WHITE);
    }

    private void renderCombatPanel(SpriteBatch sb, float x, float top, float width,
                                   float bottom, float scale) {
        float cardTop = top - 70.0f * scale;
        float cardHeight = 118.0f * scale;
        float cardBottom = cardTop - cardHeight;
        float leftX = x + 14.0f * scale;
        float leftWidth = 172.0f * scale;
        float rightX = x + 198.0f * scale;
        float rightWidth = width - 212.0f * scale;
        drawCard(sb, leftX, cardBottom, leftWidth, cardHeight, scale);
        drawCard(sb, rightX, cardBottom, rightWidth, cardHeight, scale);

        // Silver's end-of-combat samples at the current root, refreshed after
        // every play; hovering a card or End Turn outlines that action's share.
        CombatHpOverlay view = currentCombatHpOverlay();
        String[] hoveredLabel = {""};
        CombatHpOverlay.Layer hovered = view == null ? null : hoveredCombatLayer(view, hoveredLabel);
        renderSmallText(sb, "Sampled deaths", leftX + 14.0f * scale,
                cardTop - 13.0f * scale, Color.WHITE, 0.92f);
        FontHelper.renderFontLeftTopAligned(sb, FontHelper.tipHeaderFont,
                view == null ? "—" : view.root.deathLabel(),
                leftX + 14.0f * scale, cardTop - 38.0f * scale, view == null ? WARNING : CYAN);
        if (hovered != null) renderFittedText(sb, hoveredLabel[0] + "  " + hovered.deathLabel(),
                leftX + 14.0f * scale, cardTop - 68.0f * scale, leftWidth - 28.0f * scale, WARNING, 0.72f);
        String sampleNote = view != null
                ? "of " + compactSimulations(view.root.count) + " search sims"
                : "OK".equals(silverStatus) || silverStatus == null || silverStatus.isEmpty()
                ? "searching…" : silverStatus.toLowerCase(Locale.ROOT);
        renderFittedText(sb, sampleNote, leftX + 14.0f * scale, cardBottom + 21.0f * scale,
                leftWidth - 28.0f * scale, view == null ? WARNING : MUTED, 0.72f);

        renderSmallText(sb, "HP at combat end", rightX + 14.0f * scale,
                cardTop - 13.0f * scale, Color.WHITE, 0.92f);
        if (view == null || view.root.count == 0) {
            float textTop = cardBottom + cardHeight - 38.0f * scale;
            renderFittedText(sb, view == null ? "Awaiting Silver search" : "No resolved simulations",
                    rightX + 12.0f * scale, textTop, rightWidth - 24.0f * scale, WARNING, 0.78f);
            if (view == null && silverReason != null && !silverReason.isEmpty()) renderFittedText(sb,
                    silverReason.replace('_', ' '), rightX + 12.0f * scale, textTop - 24.0f * scale,
                    rightWidth - 24.0f * scale, MUTED, 0.65f);
        } else renderHpHistogram(sb, view.axis(), view.root, hovered, rightX + 12.0f * scale,
                cardBottom + 14.0f * scale, rightWidth - 24.0f * scale, cardHeight - 38.0f * scale, scale);

        renderSmallText(sb, silverBudgetSummary(), x + 16.0f * scale, bottom + 68.0f * scale,
                CYAN_DIM, 0.70f);
        if (showSelectedActionSummary) {
            String silver = showActionRecommendations ? silverSummary()
                    : "Silver  ·  " + ("OK".equals(silverStatus) ? "ready" : silverStatus.toLowerCase(Locale.ROOT));
            renderSmallText(sb, silver, x + 16.0f * scale, bottom + 48.0f * scale,
                    "OK".equals(silverStatus) ? CYAN : WARNING, 0.78f);
        }
        renderSilverBoostButton(sb, x, bottom, scale);
        renderSmallText(sb, Keyboard.getKeyName(loadToggleKey()) + " hide",
                x + width - 78.0f * scale, bottom + 22.0f * scale, MUTED, 0.78f);
    }

    private static List<String> liveMonsterNames(boolean livingOnly) {
        List<String> names = new ArrayList<>();
        if (AbstractDungeon.getMonsters() != null)
            for (AbstractMonster monster : AbstractDungeon.getMonsters().monsters) {
                if (livingOnly && (monster == null || monster.isDeadOrEscaped())) continue;
                names.add(monster == null ? "" : monster.name);
            }
        return names;
    }

    private String displaySilverLabel(String label) {
        Map<Integer, Integer> indices = new HashMap<>();
        if (AbstractDungeon.getMonsters() != null) {
            // The same slot map the observation exports. monsterSlots alone is
            // empty once the Runic Dome tracker binds the slots (every combat),
            // which made every target read "Unknown target".
            IdentityHashMap<AbstractMonster, Integer> emitted = emittedMonsterSlots(liveEncounter);
            List<AbstractMonster> monsters = AbstractDungeon.getMonsters().monsters;
            for (int i = 0; i < monsters.size(); ++i) {
                Integer slot = emitted.get(monsters.get(i));
                if (slot != null) indices.put(slot, i + 1);
            }
        }
        return TargetLabels.silver(label, indices, liveMonsterNames(false));
    }

    private String silverSummary() {
        if ("OK".equals(silverStatus)) {
            String label = displaySilverLabel(silverSelectedLabel == null ? "" : silverSelectedLabel);
            if (!label.isEmpty()) return "Silver  ·  " + label;
            return "Silver  ·  ready";
        }
        if (silverStatus == null || silverStatus.isEmpty()) return "Silver  ·  waiting";
        return "Silver  ·  " + silverStatus.toLowerCase(Locale.ROOT);
    }

    private String silverBudgetSummary() {
        return "Silver budget " + compactSimulations(silverSearchBudget)
                + "  ·  visits " + compactSimulations(silverRootVisits)
                + "  ·  total " + compactSimulations(silverTotalSimulations);
    }

    private void renderSilverBoostButton(SpriteBatch sb, float x, float bottom, float scale) {
        float buttonX = x + SILVER_BOOST_BUTTON_X * scale;
        float buttonBottom = bottom + SILVER_BOOST_BUTTON_BOTTOM * scale;
        float buttonHeight = 30.0f * scale;
        drawRect(sb, buttonX, buttonBottom,
                SILVER_BOOST_BUTTON_WIDTH * scale, buttonHeight, PANEL_INNER);
        drawBorder(sb, buttonX, buttonBottom,
                SILVER_BOOST_BUTTON_WIDTH * scale, buttonHeight, CYAN_DIM, scale);
        String increment = silverSearchBudget == DEFAULT_SILVER_SEARCH_BUDGET ? "+9k" : "+10k";
        renderSmallText(sb, "Silver " + increment, buttonX + 8.0f * scale,
                buttonBottom + 23.0f * scale, CYAN, 0.66f);
    }

    private void handleSilverBoostClick() {
        if (!panelVisible || newest == null || !"combat".equals(newest.boundary)
                || !InputHelper.justClickedLeft || !silverBoostButtonHit()) return;
        silverSearchBudget = nextSilverSearchBudget(silverSearchBudget);
        // This diagnostic control must not also activate an underlying game UI
        // element when the click lands in the panel header.
        InputHelper.justClickedLeft = false;
    }

    private void renderGraphButton(SpriteBatch sb, float x, float bottom, float scale) {
        float buttonX = x;
        float buttonBottom = bottom;
        drawRect(sb, buttonX, buttonBottom, GRAPH_BUTTON_WIDTH * scale, 30.0f * scale, PANEL_INNER);
        drawBorder(sb, buttonX, buttonBottom, GRAPH_BUTTON_WIDTH * scale, 30.0f * scale, CYAN_DIM, scale);
        String label = graphExportRunning ? "Opening graph…" : graphStatus.isEmpty() ? "Open MCTS graph" : graphStatus;
        renderSmallText(sb, label, buttonX + 7.0f * scale, buttonBottom + 23.0f * scale,
                graphExportRunning ? MUTED : CYAN, 0.62f);
    }

    private void handleGraphButtonClick() {
        if (!panelVisible || newest == null || graphButtonLayoutSequence != newest.sequence
                || !InputHelper.justClickedLeft || !graphButtonHit()) return;
        InputHelper.justClickedLeft = false;
        if (graphExportRunning) return;
        Snapshot snapshot = newest;
        String pinnedSnapshotJson = graphSnapshotJson(snapshot.session, snapshot.sequence, snapshot.hash,
                snapshot.observationJson, responseSequence, responseHash, advisorResponseJson,
                advisorReason, snapshot.responseLatencyMicros);
        if (pinnedSnapshotJson == null) {
            graphStatus = "Waiting for ready response";
            return;
        }
        final boolean combat = "combat".equals(snapshot.boundary);
        graphExportRunning = true;
        graphStatus = "";
        Thread worker = new Thread(() -> exportAndOpenGraph(combat, pinnedSnapshotJson),
                "sts-model-inspector-graph");
        worker.setDaemon(true);
        worker.start();
    }

    private boolean graphButtonHit() {
        float scale = Settings.scale;
        return !Float.isNaN(graphButtonX) && !Float.isNaN(graphButtonBottom)
                && InputHelper.mX >= graphButtonX && InputHelper.mX <= graphButtonX + GRAPH_BUTTON_WIDTH * scale
                && InputHelper.mY >= graphButtonBottom && InputHelper.mY <= graphButtonBottom + 30.0f * scale;
    }

    private void exportAndOpenGraph(boolean combat, String pinnedSnapshotJson) {
        Path pinnedSnapshot = null;
        try {
            Properties properties = new Properties();
            String configOverride = System.getenv("STS_MODEL_INSPECTOR_CONFIG");
            Path config = configOverride == null || configOverride.trim().isEmpty()
                    ? Paths.get(System.getProperty("user.home"), ".sts-model-inspector.properties")
                    : Paths.get(configOverride.trim());
            if (Files.isRegularFile(config)) try (BufferedReader reader = Files.newBufferedReader(config)) {
                properties.load(reader);
            }
            String toolsDir = System.getenv("STS_MODEL_INSPECTOR_GRAPH_TOOLS");
            if (toolsDir == null || toolsDir.trim().isEmpty()) toolsDir = properties.getProperty("graphToolsDir");
            if (toolsDir == null || toolsDir.trim().isEmpty())
                throw new IOException("set graphToolsDir in ~/.sts-model-inspector.properties");
            Path tools = Paths.get(toolsDir.trim()).toAbsolutePath().normalize();
            Path cacheDir = Paths.get(System.getProperty("user.home"), ".cache", "sts-model-inspector");
            Path outputDir = cacheDir.resolve("graphs");
            Files.createDirectories(outputDir);
            pinnedSnapshot = Files.createTempFile(outputDir, ".graph-snapshot-", ".json");
            Files.write(pinnedSnapshot, pinnedSnapshotJson.getBytes(StandardCharsets.UTF_8));
            String graphType = combat ? "silver-mcts" : "ooc-mcts";
            String timestamp = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss-SSS"));
            String filename = graphType + "-" + timestamp + ".html";
            Path output = outputDir.resolve(filename);
            for (int collision = 2; Files.exists(output); collision++)
                output = outputDir.resolve(graphType + "-" + timestamp + "-" + collision + ".html");
            String python = properties.getProperty("python", "python3").trim();
            List<String> command = new ArrayList<>();
            command.add(python);
            command.add(tools.resolve(combat ? "render_combat_decision.py" : "render_ooc_mcts.py").toString());
            command.add("--snapshot"); command.add(pinnedSnapshot.toString());
            command.add("--output"); command.add(output.toString());
            command.add("--open");
            Process process = new ProcessBuilder(command).redirectErrorStream(true).start();
            StringBuilder result = new StringBuilder();
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) result.append(line).append(' ');
            }
            int exit = process.waitFor();
            if (exit != 0) throw new IOException(result.toString().trim().isEmpty()
                    ? "renderer exited " + exit : result.toString().trim());
            graphStatus = "Graph opened";
        } catch (Exception error) {
            graphStatus = "Graph unavailable";
            System.err.println("STS Model Inspector graph export: " + error);
        } finally {
            if (pinnedSnapshot != null) try { Files.deleteIfExists(pinnedSnapshot); }
            catch (IOException ignored) {}
            graphExportRunning = false;
        }
    }

    static String graphSnapshotJson(String session, long sequence, String hash,
                                    String observationJson, long responseSequence,
                                    String responseHash, String advisorResponseJson,
                                    String responseReason,
                                    long responseLatencyMicros) {
        if (advisorResponseJson == null || advisorResponseJson.trim().isEmpty()) return null;
        final com.google.gson.JsonObject advisorResponse;
        try {
            advisorResponse = new com.google.gson.JsonParser().parse(advisorResponseJson).getAsJsonObject();
        } catch (RuntimeException invalidJson) {
            return null;
        }
        String advisorKind = jsonStringProperty(advisorResponse, "kind");
        String advisorSession = jsonStringProperty(advisorResponse, "session");
        String advisorHash = jsonStringProperty(advisorResponse, "observationHash");
        Long advisorSequence = jsonLongProperty(advisorResponse, "sequence");
        String status = jsonStringProperty(advisorResponse, "status");
        if (session == null || hash == null || observationJson == null
                || sequence < 0 || responseSequence != sequence || !hash.equals(responseHash)
                || !"analysis".equals(advisorKind)
                || !session.equals(advisorSession)
                || advisorSequence == null || sequence != advisorSequence
                || !hash.equals(advisorHash))
            return null;
        String reason = responseReason == null ? "" : responseReason;
        return "{\"protocol\":\"sts_model_inspector_latest_v1\",\"protocolVersion\":1"
                + ",\"session\":\"" + Snapshot.escape(session) + "\",\"sequence\":" + sequence
                + ",\"observationHash\":\"" + Snapshot.escape(hash) + "\",\"observation\":"
                + observationJson + ",\"response\":{\"status\":\""
                + Snapshot.escape(status == null ? "ERROR" : status)
                + "\",\"ready\":true,\"latencyMicros\":"
                + (responseLatencyMicros < 0 ? "null" : Long.toString(responseLatencyMicros))
                + ",\"session\":\"" + Snapshot.escape(session) + "\",\"sequence\":" + sequence
                + ",\"observationHash\":\"" + Snapshot.escape(hash) + "\",\"reason\":\""
                + Snapshot.escape(reason) + "\",\"advisor\":" + advisorResponseJson + "}}";
    }

    private static String jsonStringProperty(com.google.gson.JsonObject object, String key) {
        com.google.gson.JsonElement value = object.get(key);
        return value != null && value.isJsonPrimitive() && value.getAsJsonPrimitive().isString()
                ? value.getAsString() : null;
    }

    private static Long jsonLongProperty(com.google.gson.JsonObject object, String key) {
        com.google.gson.JsonElement value = object.get(key);
        if (value == null || !value.isJsonPrimitive() || !value.getAsJsonPrimitive().isNumber()) return null;
        try { return value.getAsLong(); }
        catch (NumberFormatException invalid) { return null; }
    }

    private boolean silverBoostButtonHit() {
        float scale = Settings.scale;
        float x;
        float bottom;
        if (showAdvisorPanel) {
            x = 24.0f * scale + SILVER_BOOST_BUTTON_X * scale;
            bottom = Settings.HEIGHT - (170.0f + COMBAT_PANEL_HEIGHT) * scale
                    + SILVER_BOOST_BUTTON_BOTTOM * scale;
        } else {
            x = 24.0f * scale + (GRAPH_BUTTON_WIDTH + 8.0f + SILVER_BOOST_BUTTON_X) * scale;
            bottom = 12.0f * scale + SILVER_BOOST_BUTTON_BOTTOM * scale;
        }
        return InputHelper.mX >= x && InputHelper.mX <= x + SILVER_BOOST_BUTTON_WIDTH * scale
                && InputHelper.mY >= bottom && InputHelper.mY <= bottom + 30.0f * scale;
    }

    static long nextSilverSearchBudget(long current) {
        return current <= DEFAULT_SILVER_SEARCH_BUDGET ? 10000L : current + 10000L;
    }

    private static String compactSimulations(long simulations) {
        if (simulations <= 0) return "0";
        if (simulations % 1000L == 0) return (simulations / 1000L) + "k";
        return Long.toString(simulations);
    }

    private OocOverlay currentOocOverlay() {
        OocOverlay view = oocOverlay;
        Snapshot snapshot = newest;
        return snapshot != null && view != null && responseReady()
                && view.matches(snapshot.session, snapshot.sequence, snapshot.hash) ? view : null;
    }

    private boolean renderInlineChoices(SpriteBatch sb, OocOverlay view, float scale) {
        String screen;
        try {
            screen = new com.google.gson.JsonParser().parse(newest.observationJson).getAsJsonObject()
                    .getAsJsonObject("ooc").get("screen").getAsString();
        } catch (RuntimeException unavailable) { return false; }
        if ("selector".equals(screen) && com.megacrit.cardcrawl.ui.buttons.PeekButton.isPeeking) return true;
        List<InlineChoices.Anchor> anchors = InlineChoices.capture(screen);
        if (anchors.isEmpty()) return false;
        // Keep the existing panel as a fail-safe if an API change prevents a
        // scored action from being attached to its exact physical control.
        if (view != null) for (OocOverlay.Choice choice : view.choices) {
            boolean bound = false;
            for (InlineChoices.Anchor anchor : anchors) if (anchor.action.equals(choice.action)) bound = true;
            if (!bound) return false;
        }
        for (InlineChoices.Anchor anchor : anchors) {
            if (!anchor.visible) continue;
            OocOverlay.Choice choice = view == null ? null : view.forAction(anchor.action);
            String prefix = anchor.label.isEmpty() ? "" : anchor.label + " · ";
            String label = choice == null ? prefix + (view == null ? "Waiting" : "Not scored")
                    : prefix + choice.scoreLabel(view.choices.indexOf(choice) + 1);
            String detail = followUpText(choice);
            if (choice != null && (anchor.hovered || mouseIn(anchor.x, anchor.bottom - (detail.isEmpty() ? 0 : 22 * scale),
                    anchor.width, (detail.isEmpty() ? 32 : 54) * scale))) hoveredOocChoice = choice;
            renderInlineBadge(sb, anchor.x, anchor.bottom, anchor.width, label,
                    choice != null && choice.selected, choice != null, scale, detail);
        }
        String status = view == null ? "Waiting for advisor" : "OK".equals(view.status)
                ? "Amber = recommended" : "UNSUPPORTED".equals(view.status)
                ? "No supported recommendation" : "Advisor unavailable";
        renderSmallText(sb, status + " · " + Keyboard.getKeyName(loadToggleKey()) + " hide",
                24 * scale, 28 * scale, MUTED, .72f);
        return true;
    }

    private void renderInlineBadge(SpriteBatch sb, float x, float bottom, float width,
                                   String label, boolean selected, boolean scored, float scale) {
        renderInlineBadge(sb, x, bottom, width, label, selected, scored, scale, "");
    }

    private String followUpText(OocOverlay.Choice choice) {
        if (choice == null || choice.followUpUuid.isEmpty() || AbstractDungeon.player == null) return "";
        for (AbstractCard card : AbstractDungeon.player.masterDeck.group)
            if (choice.followUpUuid.equals(String.valueOf(card.uuid)))
                return String.format(Locale.ROOT, "Next: %s · V4 score %.2f", card.name, choice.followUp.get("q").getAsDouble());
        return "";
    }

    private void renderInlineBadge(SpriteBatch sb, float x, float bottom, float width,
                                   String label, boolean selected, boolean scored, float scale, String detail) {
        float extra = detail.isEmpty() ? 0 : 22 * scale;
        drawRect(sb, x, bottom - extra, width, 32 * scale + extra, PANEL_INNER);
        drawBorder(sb, x, bottom - extra, width, 32 * scale + extra, selected ? WARNING : CARD_BORDER,
                (selected ? 2 : 1) * scale);
        renderFittedText(sb, label, x + 8 * scale, bottom + 23 * scale, width - 16 * scale,
                selected ? CYAN : scored ? Color.WHITE : MUTED, .70f);
        if (!detail.isEmpty()) renderFittedText(sb, detail, x + 8 * scale, bottom + 2 * scale,
                width - 16 * scale, MUTED, .65f);
    }

    /**
     * One rank badge under each combat potion icon: its best-ranked Silver use
     * or discard action. Hovering the potion (or its open menu) shows that
     * action's final-HP samples in the combat panel.
     */
    private void renderPotionBadges(SpriteBatch sb, float scale) {
        if (AbstractDungeon.player == null || AbstractDungeon.topPanel == null
                || newest == null || !"combat".equals(newest.boundary)) return;
        com.megacrit.cardcrawl.ui.panels.PotionPopUp popup = AbstractDungeon.topPanel.potionUi;
        if (popup != null && !popup.isHidden) return;
        PotionOverlay view = potionOverlay;
        if (view == null || !responseReady() || !view.matches(newest.session, newest.sequence, newest.hash)) return;
        float width = 96 * scale, height = 24 * scale;
        for (int slot = 0; slot < AbstractDungeon.player.potions.size(); ++slot) {
            com.megacrit.cardcrawl.potions.AbstractPotion potion = AbstractDungeon.player.potions.get(slot);
            if (potion == null || "Potion Slot".equals(potion.ID) || potion.hb == null) continue;
            PotionOverlay.Entry entry = view.best(slot + 1);
            if (entry == null) continue;
            float x = Math.max(0, Math.min(Settings.WIDTH - width, potion.hb.cX - width / 2));
            float bottom = potion.hb.y - height - 4 * scale;
            drawRect(sb, x, bottom, width, height, PANEL_INNER);
            drawBorder(sb, x, bottom, width, height, entry.selected ? WARNING : CARD_BORDER,
                    (entry.selected ? 2 : 1) * scale);
            renderFittedText(sb, entry.badge(), x + 6 * scale, bottom + height - 4 * scale,
                    width - 12 * scale, entry.selected ? CYAN : Color.WHITE, .62f);
        }
    }

    private boolean mouseIn(float x, float bottom, float width, float height) {
        return InputHelper.mX >= x && InputHelper.mX <= x + width
                && InputHelper.mY >= bottom && InputHelper.mY <= bottom + height;
    }

    private void renderNonCombatPanel(SpriteBatch sb, float x, float top, float width,
                                      float bottom, float scale, boolean inline) {
        OocOverlay view = currentOocOverlay();
        String subtitle = view == null ? "Waiting for current choices" :
                (!view.choices.isEmpty() && "forced_no_search".equals(view.choices.get(0).valueSemantics)
                        ? "Forced choice" : "v4_q".equals(view.policy) ? "V4 action score" : "Mean search value")
                + " · " + capitalize(view.screen.replace('_', ' '));
        renderSmallText(sb, subtitle, x + 16 * scale, top - 69 * scale, MUTED, .78f);
        boolean histogram = view != null && view.distribution != null;
        float listTop = top - (histogram ? 178 : 0) * scale;
        if (view != null && showActionRecommendations && "OK".equals(view.status)) {
            if (!inline) {
                List<OocOverlay.Choice> panelChoices = view.panelChoices();
                for (int row = 0; row < panelChoices.size(); ++row) {
                    OocOverlay.Choice choice = panelChoices.get(row);
                    int rank = view.choices.indexOf(choice);
                    float rowBottom = listTop - (128 + 54 * row) * scale;
                    if (mouseIn(x + 14 * scale, rowBottom, width - 28 * scale, 48 * scale))
                        hoveredOocChoice = choice;
                    drawCard(sb, x + 14 * scale, rowBottom, width - 28 * scale, 48 * scale, scale);
                    if (choice.selected) drawBorder(sb, x + 14 * scale, rowBottom,
                            width - 28 * scale, 48 * scale, WARNING, 2 * scale);
                    renderFittedText(sb, (choice.selected ? "▶ " : "") + "#" + (rank + 1) + " " + choice.label,
                            x + 23 * scale, rowBottom + 37 * scale, width - 160 * scale,
                            choice.selected ? CYAN : Color.WHITE, .74f);
                    String value = "forced_no_search".equals(choice.valueSemantics) ? "Forced"
                            : "mean_backed_up_value_0_1".equals(choice.valueSemantics)
                            ? choice.visits == 0 ? "No samples" : String.format(Locale.ROOT, "Mean %.3f", choice.q)
                            : String.format(Locale.ROOT, "Score %.3f", choice.q);
                    renderFittedText(sb, value, x + width - 133 * scale, rowBottom + 37 * scale,
                            110 * scale, MUTED, .70f);
                    if ("mean_backed_up_value_0_1".equals(choice.valueSemantics))
                        renderSmallText(sb, String.format(Locale.ROOT, "N %d · visits %.1f%% · prior %.1f%%",
                                choice.visits, 100 * choice.visitShare, 100 * choice.prior),
                                x + 23 * scale, rowBottom + 17 * scale, MUTED, .65f);
                }
            }
            renderOocCardBadges(sb, view, scale, !inline);
        } else if (!histogram) {
            renderSmallText(sb, !showActionRecommendations ? "Recommendations hidden"
                    : view == null ? "Waiting for advisor" : "No supported recommendation",
                    x + 18 * scale, top - 105 * scale, MUTED, .82f);
            if (view != null) renderFittedText(sb, view.reason.replace('_', ' '),
                    x + 18 * scale, top - 138 * scale, width - 36 * scale, MUTED, .72f);
        }
        if (histogram) renderOocDistribution(sb, view, hoveredOocChoice, x, top - 96 * scale, width, scale);
        renderSmallText(sb, Keyboard.getKeyName(loadToggleKey()) + " hide",
                x + width - 78 * scale, bottom + 22 * scale, MUTED, .78f);
    }

    /**
     * Two boxes like the combat panel. Left: the search's mean value (a model
     * estimate, not a calibrated probability) and, on hover, the choice's gap to
     * the recommended one with its search-noise error. Right: player HP where
     * each simulation was evaluated, on a fixed 0..max HP axis.
     */
    private void renderOocDistribution(SpriteBatch sb, OocOverlay view, OocOverlay.Choice hovered,
                                       float x, float top, float width, float scale) {
        float cardTop = top + 4 * scale, cardHeight = 150 * scale, cardBottom = cardTop - cardHeight;
        float leftX = x + 14 * scale, leftWidth = 172 * scale;
        float rightX = x + 198 * scale, rightWidth = width - 212 * scale;
        drawCard(sb, leftX, cardBottom, leftWidth, cardHeight, scale);
        drawCard(sb, rightX, cardBottom, rightWidth, cardHeight, scale);

        OocOverlay.Distribution all = view.distribution;
        renderSmallText(sb, "Win estimate", leftX + 14 * scale, cardTop - 13 * scale, Color.WHITE, .92f);
        FontHelper.renderFontLeftTopAligned(sb, FontHelper.tipHeaderFont,
                all.mean == null ? "—" : String.format(Locale.ROOT, "%.3f", all.mean),
                leftX + 14 * scale, cardTop - 38 * scale, CYAN);
        renderFittedText(sb, "model value · n " + all.count, leftX + 14 * scale, cardTop - 66 * scale,
                leftWidth - 28 * scale, MUTED, .66f);
        OocOverlay.Choice best = null;
        for (OocOverlay.Choice choice : view.choices) if (choice.selected) best = choice;
        if (hovered != null) {
            renderFittedText(sb, hovered.label, leftX + 14 * scale, cardTop - 92 * scale,
                    leftWidth - 28 * scale, WARNING, .70f);
            renderFittedText(sb, valueGap(hovered, best), leftX + 14 * scale, cardTop - 112 * scale,
                    leftWidth - 28 * scale, WARNING, .70f);
            renderFittedText(sb, String.format(Locale.ROOT, "N %d · visits %.0f%%", hovered.visits,
                    100 * hovered.visitShare), leftX + 14 * scale, cardTop - 131 * scale,
                    leftWidth - 28 * scale, MUTED, .62f);
        } else renderFittedText(sb, "Hover a choice to compare", leftX + 14 * scale, cardTop - 92 * scale,
                leftWidth - 28 * scale, MUTED, .64f);

        renderSmallText(sb, view.hpHorizon.isEmpty() ? "HP ahead" : view.hpHorizon,
                rightX + 14 * scale, cardTop - 13 * scale, Color.WHITE, .92f);
        float textTop = cardTop - 44 * scale;
        if (view.hpRoot == null || view.hpRoot.count == 0) {
            renderFittedText(sb, view.hpRoot == null ? "No HP samples from this advisor" : "No resolved simulations",
                    rightX + 12 * scale, textTop, rightWidth - 24 * scale, MUTED, .72f);
        } else if (view.hpUnchanged() && (hovered == null || hovered.hp == null
                || hovered.hp.count == 0 || hovered.hp.share(view.hpAxis.currentHp, view.hpAxis.currentHp) == 1.0)) {
            renderFittedText(sb, "No HP change within the search horizon",
                    rightX + 12 * scale, textTop, rightWidth - 24 * scale, MUTED, .72f);
            renderFittedText(sb, "every sample stays at " + view.hpAxis.currentHp + " HP",
                    rightX + 12 * scale, textTop - 22 * scale, rightWidth - 24 * scale, MUTED, .64f);
        } else {
            renderHpHistogram(sb, view.hpAxis, view.hpRoot, hovered == null ? null : hovered.hp,
                    rightX + 12 * scale, cardBottom + 14 * scale, rightWidth - 24 * scale, cardHeight - 54 * scale, scale);
            renderFittedText(sb, "Deaths " + view.hpRoot.deathLabel() + (hovered != null && hovered.hp != null
                    ? "  ·  hover " + hovered.hp.deathLabel() : ""), rightX + 12 * scale, cardTop - 30 * scale,
                    rightWidth - 90 * scale, MUTED, .60f);
        }
    }

    /** "best", or the gap to the recommended choice with ±1 standard error of the difference. */
    private static String valueGap(OocOverlay.Choice hovered, OocOverlay.Choice best) {
        if (hovered.distribution == null || hovered.distribution.mean == null) return "No samples";
        if (best == null || best == hovered) return String.format(Locale.ROOT, "%.3f · recommended", hovered.q);
        if (best.distribution == null || best.distribution.mean == null) return String.format(Locale.ROOT, "%.3f", hovered.q);
        double gap = hovered.distribution.mean - best.distribution.mean;
        double error = Math.hypot(hovered.distribution.standardError(), best.distribution.standardError());
        if (!Double.isFinite(error)) return String.format(Locale.ROOT, "%+.3f vs #1", gap);
        return String.format(Locale.ROOT, "%+.3f ± %.3f%s", gap, error, Math.abs(gap) < 2 * error ? "  ≈ tie" : "");
    }

    private void renderOocCardBadges(SpriteBatch sb, OocOverlay view, float scale, boolean drawBadges) {
        if (AbstractDungeon.screen != AbstractDungeon.CurrentScreen.CARD_REWARD
                || AbstractDungeon.cardRewardScreen == null) return;
        List<AbstractCard> cards = AbstractDungeon.cardRewardScreen.rewardGroup;
        if (cards == null) return;
        for (int rank = 0; rank < view.choices.size(); ++rank) {
            OocOverlay.Choice choice = view.choices.get(rank);
            if (!"choose".equals(choice.kind) || choice.index < 1 || choice.index > cards.size()) continue;
            AbstractCard card = cards.get(choice.index - 1);
            if (card.hb.hovered) hoveredOocChoice = choice;
            if (!drawBadges) continue;
            float width = 206 * scale;
            float x = Math.max(0, Math.min(Settings.WIDTH - width, card.current_x - width / 2));
            float bottom = Math.max(95 * scale, card.current_y - AbstractCard.IMG_HEIGHT * card.drawScale / 2 - 48 * scale);
            drawRect(sb, x, bottom, width, 34 * scale, PANEL_INNER);
            drawBorder(sb, x, bottom, width, 34 * scale, choice.selected ? WARNING : CARD_BORDER, 2 * scale);
            renderSmallText(sb, choice.scoreLabel(rank + 1),
                    x + 10 * scale, bottom + 24 * scale, choice.selected ? CYAN : Color.WHITE, .76f);
        }
    }

    private void renderFittedText(SpriteBatch sb, String text, float x, float top,
                                  float maxWidth, Color color, float factor) {
        float oldX = FontHelper.tipBodyFont.getData().scaleX;
        float oldY = FontHelper.tipBodyFont.getData().scaleY;
        FontHelper.tipBodyFont.getData().setScale(oldX * factor, oldY * factor);
        com.badlogic.gdx.graphics.g2d.GlyphLayout layout = new com.badlogic.gdx.graphics.g2d.GlyphLayout();
        layout.setText(FontHelper.tipBodyFont, text);
        if (layout.width > maxWidth) {
            String shortened = text;
            do {
                shortened = shortened.substring(0, Math.max(0, shortened.length() - 1));
                layout.setText(FontHelper.tipBodyFont, shortened + "…");
            } while (!shortened.isEmpty() && layout.width > maxWidth);
            text = shortened + "…";
        }
        FontHelper.renderFontLeftTopAligned(sb, FontHelper.tipBodyFont, text, x, top, color);
        FontHelper.tipBodyFont.getData().setScale(oldX, oldY);
    }

    private void renderSilverActionBadges(SpriteBatch sb, float scale) {
        if (!"OK".equals(silverStatus) || silverRanking.isEmpty()
                || AbstractDungeon.player == null || AbstractDungeon.player.hand == null) return;
        List<AbstractCard> hand = AbstractDungeon.player.hand.group;
        if (hand.isEmpty()) return;
        String[] rows = silverRanking.split("\\n");
        boolean[] used = new boolean[hand.size()];
        float badgeBottom = 248.0f * scale;
        float badgeWidth = 132.0f * scale;
        float badgeHeight = 54.0f * scale;
        for (int rank = 0; rank < rows.length && rank < 5; ++rank) {
            String[] fields = rows[rank].split("\\|", -1);
            if (fields.length < 3) continue;
            String action = fields[0];
            if (action.startsWith("End Turn")) {
                float endTurnCenter = Settings.WIDTH - 290.0f * scale;
                float endTurnX = endTurnCenter - badgeWidth / 2.0f;
                renderSilverBadge(sb, endTurnX, badgeBottom, badgeWidth,
                        30.0f * scale, rank, fields, "", scale);
                continue;
            }
            if (action.startsWith("Select ")) {
                // Hand selections (Armaments, True Grit+, Dual Wield ...) keep
                // their choices in the hand: badge every picked card. Grid
                // selections show only in the summary line.
                for (String picked : action.substring("Select ".length()).split(", ")) {
                    int pickedIndex = findHandCard(hand, used, picked);
                    if (pickedIndex < 0) continue;
                    used[pickedIndex] = true;
                    AbstractCard card = hand.get(pickedIndex);
                    renderSilverBadge(sb, card.current_x - badgeWidth / 2.0f, badgeBottom, badgeWidth,
                            badgeHeight, rank, fields, "select", scale);
                }
                continue;
            }
            int handIndex = findHandCard(hand, used, action);
            if (handIndex < 0) continue;
            used[handIndex] = true;
            AbstractCard card = hand.get(handIndex);
            float badgeX = card.current_x - badgeWidth / 2.0f;
            String target = displaySilverLabel(action);
            int arrow = target.indexOf(" -> ");
            if (arrow >= 0) target = target.substring(arrow + 4);
            renderSilverBadge(sb, badgeX, badgeBottom, badgeWidth, badgeHeight,
                    rank, fields, target, scale);
        }
    }

    private void renderSilverBadge(SpriteBatch sb, float x, float bottom, float width,
                                   float height, int rank, String[] fields,
                                   String target, float scale) {
        boolean best = rank == 0;
        Color border = best ? WARNING : CARD_BORDER;
        drawRect(sb, x + 3.0f * scale, bottom - 3.0f * scale,
                width, height, new Color(0.0f, 0.0f, 0.0f, 0.35f));
        drawRect(sb, x, bottom, width, height,
                best ? new Color(0.10f, 0.14f, 0.18f, 0.97f) : PANEL_INNER);
        drawBorder(sb, x, bottom, width, height, border,
                best ? 2.0f * scale : scale);
        renderSmallText(sb, "#" + (rank + 1) + "  ·  " + fields[1]
                        + "v  ·  Q " + compactScore(fields[2]),
                x + 8.0f * scale, bottom + (target.isEmpty() ? 20.0f : 43.0f) * scale,
                best ? Color.WHITE : MUTED, 0.62f);
        if (!target.isEmpty()) {
            renderFittedText(sb, "→ " + target, x + 8.0f * scale,
                    bottom + 20.0f * scale, width - 16 * scale, best ? CYAN : Color.WHITE, 0.70f);
        }
    }

    private static String compactScore(String value) {
        try {
            return String.format(Locale.ROOT, "%.1f", Double.parseDouble(value));
        } catch (NumberFormatException ignored) {
            return value;
        }
    }

    private static int findHandCard(List<AbstractCard> hand, boolean[] used, String action) {
        String name = action;
        int arrow = name.indexOf(" -> ");
        if (arrow >= 0) name = name.substring(0, arrow);
        // Upgraded labels end in "+"; Searing Blow's in-game name is "+N".
        String base = name.endsWith("+") ? name.substring(0, name.length() - 1) : name;
        for (int i = 0; i < hand.size(); ++i) {
            if (used[i]) continue;
            AbstractCard card = hand.get(i);
            if (name.equalsIgnoreCase(card.name) || name.equalsIgnoreCase(card.cardID)
                    || (card.upgraded && base.equalsIgnoreCase(card.cardID))
                    || card.cardID.toLowerCase(Locale.ROOT).contains(name.toLowerCase(Locale.ROOT)))
                return i;
        }
        return -1;
    }

    private CombatHpOverlay currentCombatHpOverlay() {
        Snapshot snapshot = newest;
        CombatHpOverlay view = combatHpOverlay;
        return snapshot != null && view != null && responseReady()
                && view.matches(snapshot.session, snapshot.sequence, snapshot.hash) ? view : null;
    }

    /** The hovered hand card (narrowed to the targeted monster while aiming) or End Turn. */
    private CombatHpOverlay.Layer hoveredCombatLayer(CombatHpOverlay view, String[] label) {
        com.megacrit.cardcrawl.characters.AbstractPlayer player = AbstractDungeon.player;
        if (player == null) return null;
        CombatHpOverlay.Layer potion = hoveredPotionLayer(view, player, label);
        if (potion != null) return potion;
        Object dragged = optionalField(player, "hoveredCard");
        AbstractCard card = dragged instanceof AbstractCard ? (AbstractCard) dragged : null;
        if (card == null && player.hand != null)
            for (AbstractCard candidate : player.hand.group)
                if (candidate.hb != null && candidate.hb.hovered) { card = candidate; break; }
        if (card != null) {
            Object aimed = AbstractDungeon.getMonsters() == null ? null
                    : optionalField(AbstractDungeon.getMonsters(), "hoveredMonster");
            AbstractMonster monster = aimed instanceof AbstractMonster ? (AbstractMonster) aimed : null;
            int target = liveTargetIndex(monster);
            CombatHpOverlay.Layer layer = target > 0 ? view.forCard(String.valueOf(card.uuid), target) : null;
            if (layer != null) {
                label[0] = card.name + " → " + monster.name;
                return layer;
            }
            label[0] = card.name;
            return view.forCard(String.valueOf(card.uuid), -1);
        }
        Object button = AbstractDungeon.overlayMenu == null ? null : AbstractDungeon.overlayMenu.endTurnButton;
        Object hb = button == null ? null : optionalField(button, "hb");
        if (hb instanceof com.megacrit.cardcrawl.helpers.Hitbox && ((com.megacrit.cardcrawl.helpers.Hitbox) hb).hovered) {
            label[0] = "End Turn";
            return view.forEndTurn();
        }
        return null;
    }

    /** The open potion menu's slot (Discard when its lower button is hovered), else a hovered potion icon. */
    private CombatHpOverlay.Layer hoveredPotionLayer(CombatHpOverlay view,
            com.megacrit.cardcrawl.characters.AbstractPlayer player, String[] label) {
        if (AbstractDungeon.topPanel == null || player.potions == null) return null;
        com.megacrit.cardcrawl.ui.panels.PotionPopUp popup = AbstractDungeon.topPanel.potionUi;
        if (popup != null && !popup.isHidden) {
            Object slotValue = optionalField(popup, "slot");
            if (!(slotValue instanceof Integer)) return null;
            int slot = (Integer) slotValue;
            if (slot < 0 || slot >= player.potions.size() || player.potions.get(slot) == null) return null;
            String name = player.potions.get(slot).name;
            if (popup.targetMode) {
                Object aimed = optionalField(popup, "hoveredMonster");
                AbstractMonster monster = aimed instanceof AbstractMonster ? (AbstractMonster) aimed : null;
                int target = liveTargetIndex(monster);
                CombatHpOverlay.Layer layer = target > 0 ? view.forPotion(slot + 1, false, target) : null;
                if (layer != null) {
                    label[0] = name + " → " + monster.name;
                    return layer;
                }
                label[0] = name;
                return view.forPotion(slot + 1, false, -1);
            }
            Object discard = optionalField(popup, "hbBot");
            if (discard instanceof com.megacrit.cardcrawl.helpers.Hitbox
                    && ((com.megacrit.cardcrawl.helpers.Hitbox) discard).hovered) {
                label[0] = "Discard " + name;
                return view.forPotion(slot + 1, true, -1);
            }
            label[0] = name;
            return view.forPotion(slot + 1, false, -1);
        }
        for (int slot = 0; slot < player.potions.size(); ++slot) {
            com.megacrit.cardcrawl.potions.AbstractPotion potion = player.potions.get(slot);
            if (potion == null || potion.hb == null || !potion.hb.hovered) continue;
            label[0] = potion.name;
            return view.forPotion(slot + 1, false, -1);
        }
        return null;
    }

    private static Object optionalField(Object object, String name) {
        try { return InlineChoices.field(object, name); }
        catch (ReflectiveOperationException | RuntimeException unavailable) { return null; }
    }

    /** 1-based index among living monsters, as Silver's live actions number targets; -1 if none. */
    private static int liveTargetIndex(AbstractMonster target) {
        if (target == null || target.isDeadOrEscaped() || AbstractDungeon.getMonsters() == null) return -1;
        int index = 0;
        for (AbstractMonster monster : AbstractDungeon.getMonsters().monsters) {
            if (monster == null || monster.isDeadOrEscaped()) continue;
            ++index;
            if (monster == target) return index;
        }
        return -1;
    }

    /** Cyan root samples on a fixed 0..max HP axis, the hovered layer as an amber outline. */
    private void renderHpHistogram(SpriteBatch sb, HpAxis view, CombatHpOverlay.Layer root,
                                   CombatHpOverlay.Layer hovered, float x, float bottom, float width,
                                   float height, float scale) {
        final int buckets = view.buckets();
        final double maximum = Math.max(1e-9, view.maxShare(buckets));
        float statsWidth = 66.0f * scale;
        float chartX = x + 4.0f * scale;
        float chartWidth = width - statsWidth - 8.0f * scale;
        float chartBottom = bottom + 14.0f * scale;
        float chartHeight = height - 16.0f * scale;
        float barWidth = chartWidth / (buckets + 1);
        sb.setColor(0.35f, 0.78f, 0.80f, 0.20f);
        for (int tick = 1; tick <= 3; ++tick)
            sb.draw(ImageMaster.WHITE_SQUARE_IMG, chartX, chartBottom + chartHeight * tick / 4.0f, chartWidth, scale);
        sb.setColor(CYAN_DIM);
        sb.draw(ImageMaster.WHITE_SQUARE_IMG, chartX, chartBottom, chartWidth, scale);
        for (int bucket = 0; bucket <= buckets; ++bucket) {
            int[] range = view.bucketRange(bucket, buckets);
            float bx = chartX + bucket * barWidth;
            float baseHeight = (float) (chartHeight * root.share(range[0], range[1]) / maximum);
            if (baseHeight > 0) drawRect(sb, bx + scale * 0.5f, chartBottom,
                    Math.max(scale, barWidth - scale), baseHeight, bucket == 0 ? DEATH : CYAN_DIM);
            if (hovered != null && hovered.count > 0) {
                float overlayHeight = (float) (chartHeight * hovered.share(range[0], range[1]) / maximum);
                if (overlayHeight > 0) drawBorder(sb, bx + scale * 0.5f, chartBottom,
                        Math.max(scale, barWidth - scale), overlayHeight, WARNING,
                        Math.min(1.5f * scale, overlayHeight));
            }
        }
        // Current HP marker.
        float markerX = chartX + barWidth + (float) (view.currentHp - 1) / Math.max(1, view.axisMaxHp)
                * (chartWidth - barWidth);
        sb.setColor(Color.WHITE);
        sb.draw(ImageMaster.WHITE_SQUARE_IMG, markerX, chartBottom, scale, chartHeight);
        renderSmallText(sb, "0", chartX, chartBottom - 1.0f * scale, MUTED, 0.66f);
        renderSmallText(sb, Integer.toString(view.axisMaxHp), chartX + chartWidth - 18.0f * scale,
                chartBottom - 1.0f * scale, MUTED, 0.66f);
        renderSmallText(sb, "now " + view.currentHp, Math.max(chartX + 16.0f * scale, Math.min(
                markerX - 14.0f * scale, chartX + chartWidth - 70.0f * scale)),
                chartBottom - 1.0f * scale, Color.WHITE, 0.66f);
        // Expected final HP (deaths as 0) and its change from now: all, then hover.
        float statsX = x + width - statsWidth;
        renderFinalHpStats(sb, root, view.currentHp, statsX, bottom + height, statsWidth, CYAN, scale);
        if (hovered != null)
            renderFinalHpStats(sb, hovered, view.currentHp, statsX, bottom + height - 40.0f * scale,
                    statsWidth, WARNING, scale);
    }

    private void renderFinalHpStats(SpriteBatch sb, CombatHpOverlay.Layer layer, int currentHp,
                                    float x, float top, float width, Color color, float scale) {
        if (layer.count == 0) {
            renderFittedText(sb, "no samples", x, top, width, color, 0.66f);
            return;
        }
        double mean = layer.meanHp();
        renderFittedText(sb, String.format(Locale.ROOT, "≈%.0f HP", mean), x, top, width, color, 0.80f);
        renderFittedText(sb, String.format(Locale.ROOT, "%+.0f exp.", mean - currentHp),
                x, top - 17.0f * scale, width, color, 0.66f);
    }

    private void renderStatusPill(SpriteBatch sb, float x, float top, float scale) {
        boolean online = responseReady() || "connected".equals(advisorStatus);
        boolean waiting = !online && ("waiting".equals(advisorStatus)
                || "disconnected".equals(advisorStatus));
        String label = online ? "ONLINE" : waiting ? "WAITING"
                : advisorStatus.toUpperCase(Locale.ROOT);
        float width = 101.0f * scale;
        float height = 30.0f * scale;
        drawRect(sb, x, top - height, width, height,
                online ? new Color(0.0f, 0.34f, 0.32f, 0.88f)
                        : new Color(0.35f, 0.22f, 0.07f, 0.88f));
        drawBorder(sb, x, top - height, width, height,
                online ? CYAN_DIM : WARNING, scale);
        drawRect(sb, x + 12.0f * scale, top - 19.0f * scale,
                8.0f * scale, 8.0f * scale, online ? CYAN : WARNING);
        renderSmallText(sb, label,
                x + 28.0f * scale, top - 7.0f * scale,
                online ? CYAN : WARNING, 0.82f);
    }

    private void renderAdvisorIcon(SpriteBatch sb, float x, float top, float scale) {
        drawRect(sb, x, top - 28.0f * scale, 7.0f * scale, 28.0f * scale, CYAN);
        drawRect(sb, x + 11.0f * scale, top - 22.0f * scale,
                7.0f * scale, 22.0f * scale, CYAN);
        drawRect(sb, x + 22.0f * scale, top - 14.0f * scale,
                7.0f * scale, 14.0f * scale, CYAN);
    }

    private void renderGearIcon(SpriteBatch sb, float x, float top, float scale) {
        Color gear = new Color(0.55f, 0.76f, 0.83f, 0.95f);
        drawRect(sb, x - 8.0f * scale, top - 4.0f * scale,
                16.0f * scale, 8.0f * scale, gear);
        drawRect(sb, x - 4.0f * scale, top - 8.0f * scale,
                8.0f * scale, 16.0f * scale, gear);
        drawRect(sb, x - 3.0f * scale, top - 3.0f * scale,
                6.0f * scale, 6.0f * scale, PANEL_INNER);
    }

    private void drawCard(SpriteBatch sb, float x, float bottom, float width,
                          float height, float scale) {
        drawRect(sb, x, bottom, width, height, CARD_BACKGROUND);
        drawBorder(sb, x, bottom, width, height, CARD_BORDER, scale);
    }

    private static void drawBorder(SpriteBatch sb, float x, float bottom, float width,
                                   float height, Color color, float thickness) {
        drawRect(sb, x, bottom, width, thickness, color);
        drawRect(sb, x, bottom + height - thickness, width, thickness, color);
        drawRect(sb, x, bottom, thickness, height, color);
        drawRect(sb, x + width - thickness, bottom, thickness, height, color);
    }

    private static void drawRect(SpriteBatch sb, float x, float bottom, float width,
                                 float height, Color color) {
        sb.setColor(color);
        sb.draw(ImageMaster.WHITE_SQUARE_IMG, x, bottom, width, height);
    }

    private void renderSmallText(SpriteBatch sb, String text, float x, float top,
                                 Color color, float factor) {
        float oldX = FontHelper.tipBodyFont.getData().scaleX;
        float oldY = FontHelper.tipBodyFont.getData().scaleY;
        FontHelper.tipBodyFont.getData().setScale(oldX * factor, oldY * factor);
        FontHelper.renderFontLeftTopAligned(sb, FontHelper.tipBodyFont, text, x, top, color);
        FontHelper.tipBodyFont.getData().setScale(oldX, oldY);
    }

    private void renderHeaderText(SpriteBatch sb, String text, float x, float top,
                                  Color color, float factor) {
        float oldX = FontHelper.tipHeaderFont.getData().scaleX;
        float oldY = FontHelper.tipHeaderFont.getData().scaleY;
        FontHelper.tipHeaderFont.getData().setScale(oldX * factor, oldY * factor);
        FontHelper.renderFontLeftTopAligned(sb, FontHelper.tipHeaderFont, text, x, top, color);
        FontHelper.tipHeaderFont.getData().setScale(oldX, oldY);
    }

    private boolean responseReady() {
        return newest != null && responseSequence == newest.sequence
                && responseHash.equals(newest.hash);
    }

    private static String capitalize(String value) {
        if (value == null || value.isEmpty()) return "State";
        return Character.toUpperCase(value.charAt(0)) + value.substring(1);
    }

    private Snapshot captureStableSnapshot() {
        final long capturedNanos = System.nanoTime();
        if (AbstractDungeon.player == null
                || AbstractDungeon.currMapNode == null
                || AbstractDungeon.getCurrRoom() == null) return null;
        AbstractRoom room = AbstractDungeon.getCurrRoom();
        try {
            LiveOocCapture.observeCombatRoom(room);
        } catch (RuntimeException failure) {
            // Observation never alters the game; a malformed metric or room
            // leaves advisor history unsupported rather than breaking input.
            LiveOocCapture.invalidateCombatRoomHistory();
        }
        String boundary;
        String ooc = "";
        if (isCombatBoundary(room.phase, AbstractDungeon.screen,
                isPlayerDecisionPoint(), isCardSelectionBoundary(),
                isCombatEnding(room.isBattleOver, room.smoked, AbstractDungeon.player.isEscaping))) {
            boundary = "combat";
        } else {
            ooc = LiveOocCapture.capture();
            if (ooc == null) return null;
            boundary = "ooc";
        }
        if ("combat".equals(boundary)) {
            String encounter = encounterName(room);
            if (liveEncounter.isEmpty() && !encounter.isEmpty()) liveEncounter = encounter;
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
        String stateRaw = boundary + "|" + character + "|" + AbstractDungeon.ascensionLevel +
                "|" + act + "|" + floor + "|" + hp + "|" + maxHp + "|" + gold +
                "|" + room.getClass().getName() + "|" + AbstractDungeon.screen.name() +
                "|" + deck + "|" + candidates + "|" + combat + "|" + ooc;
        if ("combat".equals(boundary)) {
            String stateFingerprint = sha256(stateRaw);
            if (!stateFingerprint.equals(silverBudgetStateFingerprint)) {
                silverSearchBudget = DEFAULT_SILVER_SEARCH_BUDGET;
                silverBudgetStateFingerprint = stateFingerprint;
            }
        } else {
            silverSearchBudget = DEFAULT_SILVER_SEARCH_BUDGET;
            silverBudgetStateFingerprint = "";
        }
        String raw = stateRaw + "|silverSearchBudget=" + silverSearchBudget;
        return new Snapshot(session, 0, boundary, character,
                AbstractDungeon.ascensionLevel, act, floor, hp, maxHp, gold,
                deck, candidates, combat, "combat".equals(boundary) ? combatEntry : "",
                "combat".equals(boundary) ? combatEntryHash : "", ooc,
                silverSearchBudget, sha256(raw), capturedNanos, DebugRngCapture.json());
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
                || AbstractDungeon.pathX.isEmpty()) return "";
        int currentIndex = AbstractDungeon.pathX.size() - 1;
        if (AbstractDungeon.pathX.get(currentIndex) != currentX
                || AbstractDungeon.pathY.get(currentIndex) != currentY) return "";
        if (currentIndex == 0) return previousRoomAtActEntry(AbstractDungeon.actNum,
                AbstractDungeon.floorNum, currentY,
                CardCrawlGame.metricData == null ? null : CardCrawlGame.metricData.path_per_floor,
                RelicOfferRecorder.completedCombatFloors(AbstractDungeon.actNum-1, AbstractDungeon.floorNum));
        int previousX = AbstractDungeon.pathX.get(currentIndex - 1);
        int previousY = AbstractDungeon.pathY.get(currentIndex - 1);
        if (previousY < 0 || previousY >= AbstractDungeon.map.size()) return "";
        List<com.megacrit.cardcrawl.map.MapRoomNode> row = AbstractDungeon.map.get(previousY);
        if (row == null || previousX < 0 || previousX >= row.size()) return "";
        com.megacrit.cardcrawl.map.MapRoomNode previous = row.get(previousX);
        return previous == null || previous.room == null ? "" : roomClass(previous.room);
    }

    static String previousRoomAtActEntry(int act, int floor, int currentY,
            List<String> resolved, List<Integer> completedCombatFloors) {
        if (act < 2 || act > 3 || currentY != 0 || floor != 17*(act-1)+1
                || resolved == null || completedCombatFloors == null
                || resolved.size() < floor-1 || resolved.size() > floor) return "";
        // A one-node current-act path has no preceding map coordinate. Its
        // public metrics must instead prove the boss and omitted boss chest.
        if (resolved.get(floor-2) != null
                || !"BOSS".equals(metricRoomClass(resolved.get(floor-3)))
                || !completedCombatFloors.contains(floor-2)) return "";
        return "BOSS_TREASURE";
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

    static String encounterName(AbstractRoom room) {
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
        return singleEncounterName(group.monsters.get(0).id, eventRoom);
    }

    static String singleEncounterName(String id, boolean eventRoom) {
        // AbstractMonster.id is the stable save/runtime identifier.  Do not
        // compare it with MonsterHelper's localized encounter display names.
        if (id.equals("Cultist")) return "CULTIST";
        if (id.equals("JawWorm")) return "JAW_WORM";
        if (id.equals("BlueSlaver") || id.equals("SlaverBlue")) return "BLUE_SLAVER";
        if (id.equals("Looter")) return "LOOTER";
        if (id.equals("RedSlaver") || id.equals("SlaverRed")) return "RED_SLAVER";
        if (id.equals("GremlinNob")) return "GREMLIN_NOB";
        if (id.equals("Lagavulin")) return eventRoom ? "LAGAVULIN_EVENT" : "LAGAVULIN";
        if (id.equals("AcidSlime_L") || id.equals("SpikeSlime_L")) return "LARGE_SLIME";
        if (id.equals("SphericGuardian")) return "SPHERIC_GUARDIAN";
        if (id.equals("Chosen")) return "CHOSEN";
        if (id.equals("Shelled Parasite") || id.equals("ShelledParasite")) return "SHELL_PARASITE";
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

    private static int monsterSlot(AbstractMonster monster, int fallback, Set<Integer> used) {
        Integer known = monsterSlots.get(monster);
        if (known != null) {
            used.add(known);
            return known;
        }
        int candidate = fallback >= 0 && fallback < 5 && !used.contains(fallback)
                ? fallback : -1;
        if (candidate < 0) {
            for (int i = 0; i < 5; ++i) {
                if (!used.contains(i)) {
                    candidate = i;
                    break;
                }
            }
        }
        if (candidate < 0) return -1;
        monsterSlots.put(monster, candidate);
        used.add(candidate);
        return candidate;
    }

    private static Integer reflectedEncounterSlot(String encounter, AbstractMonster candidate) {
        if (AbstractDungeon.getMonsters() == null
                || AbstractDungeon.getMonsters().monsters == null) return null;
        if ("AUTOMATON".equals(encounter) && "BronzeOrb".equals(candidate.id)) {
            Integer count = readIntField(candidate, "count");
            if (count != null && (count == 0 || count == 1)) return count == 0 ? 0 : 2;
        }
        AbstractMonster owner = null;
        for (AbstractMonster monster : AbstractDungeon.getMonsters().monsters) {
            if (monster == null) continue;
            if (("COLLECTOR".equals(encounter) && "TheCollector".equals(monster.id))
                    || ("REPTOMANCER".equals(encounter) && "Reptomancer".equals(monster.id))) {
                owner = monster;
                break;
            }
        }
        if (owner == null) return null;
        if ("COLLECTOR".equals(encounter)) {
            Object raw = readObjectField(owner, "enemySlots");
            if (!(raw instanceof Map<?, ?>)) return null;
            for (Map.Entry<?, ?> entry : ((Map<?, ?>) raw).entrySet()) {
                if (entry.getValue() == candidate && entry.getKey() instanceof Number)
                    return ((Number) entry.getKey()).intValue();
            }
        } else {
            Object raw = readObjectField(owner, "daggers");
            if (!(raw instanceof Object[])) return null;
            int[] slots = {1, 4, 3, 0};
            Object[] daggers = (Object[]) raw;
            for (int i = 0; i < daggers.length && i < slots.length; ++i)
                if (daggers[i] == candidate) return slots[i];
        }
        return null;
    }

    private static boolean replacedLargeSlimeParent(String encounter,
                                                     AbstractMonster candidate,
                                                     List<AbstractMonster> monsters) {
        if (!("LARGE_SLIME".equals(encounter) || "SLIME_BOSS".equals(encounter))
                || candidate == null
                || !("AcidSlime_L".equals(candidate.id)
                    || "SpikeSlime_L".equals(candidate.id))) return false;
        if (replacedMonsterParents.contains(candidate)) return true;
        if (candidate.currentHealth > 0 || !candidate.isDeadOrEscaped()) return false;
        String childId = "AcidSlime_L".equals(candidate.id) ? "AcidSlime_M" : "SpikeSlime_M";
        for (AbstractMonster monster : monsters) {
            if (monster == null || monster == candidate || !childId.equals(monster.id)) continue;
            if (monster.currentHealth > 0 && !monster.isDeadOrEscaped()) {
                // Vanilla's SpawnMonsterAction leaves the replaced parent in
                // MonsterGroup.monsters. Native largeSlimeSplit instead
                // replaces it in-place at slots 0 and 1. Remember the
                // identity so a later snapshot cannot resurrect the parent
                // after both children have become dead/escaped.
                replacedMonsterParents.add(candidate);
                return true;
            }
        }
        return false;
    }

    static <T> boolean replacedSlimeBossParent(String encounter, String id, T identity,
            boolean dead, boolean liveLargeChild, Set<T> replaced) {
        if (!"SLIME_BOSS".equals(encounter) || !"SlimeBoss".equals(id) || identity == null || !dead) return false;
        // The original Java parent stays in MonsterGroup after replacement.
        // Keep its retirement when the large children later split or die.
        if (liveLargeChild) replaced.add(identity);
        return replaced.contains(identity);
    }

    private static boolean replacedSlimeBossParent(String encounter,
                                                    AbstractMonster candidate,
                                                    List<AbstractMonster> monsters) {
        if (candidate == null) return false;
        boolean liveLargeChild=false;
        for (AbstractMonster monster : monsters) {
            if (monster == null || monster == candidate || monster.isDeadOrEscaped()) continue;
            if ("SpikeSlime_L".equals(monster.id) || "AcidSlime_L".equals(monster.id)) liveLargeChild=true;
        }
        return replacedSlimeBossParent(encounter,candidate.id,candidate,candidate.isDeadOrEscaped(),
                liveLargeChild,replacedMonsterParents);
    }

    private static int preferredMonsterSlot(String encounter, String id, int sameIdOrdinal,
                                            int nonLeaderOrdinal) {
        // MonsterGroup reserves physical array positions for bosses and for
        // summon slots.  The Java monster list is not that array: a newly
        // summoned TorchHead, BronzeOrb, or SnakeDagger can otherwise shift
        // every later target by one.  Prefer the native layout when the
        // encounter is known, then let monsterSlot retain object identity.
        if ("AUTOMATON".equals(encounter)) {
            if ("BronzeAutomaton".equals(id)) return 1;
            if ("BronzeOrb".equals(id)) return sameIdOrdinal == 0 ? 0 : (sameIdOrdinal == 1 ? 2 : -1);
        } else if ("COLLECTOR".equals(encounter)) {
            if ("TheCollector".equals(id)) return 2;
            if ("TorchHead".equals(id)) return sameIdOrdinal == 0 ? 1 : (sameIdOrdinal == 1 ? 0 : -1);
        } else if ("REPTOMANCER".equals(encounter)) {
            if ("Reptomancer".equals(id)) return 2;
            if ("Dagger".equals(id) || "SnakeDagger".equals(id)) {
                int[] slots = {1, 4, 3, 0};
                return sameIdOrdinal < slots.length ? slots[sameIdOrdinal] : -1;
            }
        } else if ("AWAKENED_ONE".equals(encounter)) {
            if ("AwakenedOne".equals(id)) return 2;
            if ("Cultist".equals(id)) return sameIdOrdinal < 2 ? sameIdOrdinal : -1;
        } else if ("GREMLIN_LEADER".equals(encounter)) {
            if ("GremlinLeader".equals(id)) return 3;
            if (nonLeaderOrdinal < 2) return 1 + nonLeaderOrdinal;
        } else if ("CHOSEN_AND_BYRDS".equals(encounter)) {
            if ("Chosen".equals(id)) return 1;
            if ("Byrd".equals(id)) return sameIdOrdinal < 2 ? sameIdOrdinal : -1;
        } else if ("SENTRY_AND_SPHERE".equals(encounter)) {
            if ("Sentry".equals(id)) return 0;
            if ("SphericGuardian".equals(id)) return 1;
        } else if ("CENTURION_AND_HEALER".equals(encounter)) {
            if ("Centurion".equals(id)) return 0;
            if ("Healer".equals(id)) return 1;
        } else if ("SHELLED_PARASITE_AND_FUNGI".equals(encounter)) {
            if ("Shelled Parasite".equals(id) || "ShelledParasite".equals(id)) return 0;
            if ("FungiBeast".equals(id)) return 1;
        } else if ("DONU_AND_DECA".equals(encounter)) {
            if ("Deca".equals(id)) return 0;
            if ("Donu".equals(id)) return 1;
        } else if ("SHIELD_AND_SPEAR".equals(encounter)) {
            if ("SpireShield".equals(id)) return 0;
            if ("SpireSpear".equals(id)) return 1;
        } else if ("TWO_THIEVES".equals(encounter)) {
            if ("Looter".equals(id)) return 0;
            if ("Mugger".equals(id)) return 1;
        } else if ("SLAVERS".equals(encounter)) {
            if ("SlaverBlue".equals(id)) return 0;
            if ("Taskmaster".equals(id) || "SlaverBoss".equals(id)) return 1;
            if ("SlaverRed".equals(id)) return 2;
        } else if ("COLOSSEUM_EVENT_SLAVERS".equals(encounter)) {
            if ("SlaverBlue".equals(id)) return 0;
            if ("SlaverRed".equals(id)) return 1;
        } else if ("COLOSSEUM_EVENT_NOBS".equals(encounter)) {
            if ("Taskmaster".equals(id) || "SlaverBoss".equals(id)) return 0;
            if ("GremlinNob".equals(id)) return 1;
        } else if ("MASKED_BANDITS_EVENT".equals(encounter)) {
            if ("BanditPointy".equals(id) || "BanditChild".equals(id)) return 0;
            if ("BanditLeader".equals(id)) return 1;
            if ("BanditBear".equals(id)) return 2;
        } else if ("MYSTERIOUS_SPHERE_EVENT".equals(encounter)) {
            if ("Orb Walker".equals(id)) return sameIdOrdinal < 2 ? sameIdOrdinal : -1;
        } else if ("LARGE_SLIME".equals(encounter)) {
            if ("AcidSlime_M".equals(id) || "SpikeSlime_M".equals(id))
                return sameIdOrdinal == 0 ? 0 : (sameIdOrdinal == 1 ? 1 : -1);
        } else if ("SLIME_BOSS".equals(encounter)) {
            if ("SpikeSlime_L".equals(id)) return 0;
            if ("AcidSlime_L".equals(id)) return 2;
            if ("SpikeSlime_M".equals(id)) return sameIdOrdinal < 2 ? sameIdOrdinal : -1;
            if ("AcidSlime_M".equals(id)) return sameIdOrdinal < 2 ? 2 + sameIdOrdinal : -1;
        }
        return -1;
    }

    static IdentityHashMap<AbstractMonster, Integer> emittedMonsterSlots(String encounter) {
        IdentityHashMap<AbstractMonster,Integer> bound=RunicDomeCapture.emittedSlots();
        if(bound!=null)return bound;
        IdentityHashMap<AbstractMonster, Integer> emitted = new IdentityHashMap<>();
        if (AbstractDungeon.getMonsters() == null
                || AbstractDungeon.getMonsters().monsters == null) return emitted;
        Map<String, Integer> seenMonsterIds = new HashMap<>();
        int nonLeaderOrdinal = 0;
        Set<Integer> usedMonsterSlots = new HashSet<>();
        List<AbstractMonster> monsters = AbstractDungeon.getMonsters().monsters;
        for (int monsterIndex = 0; monsterIndex < monsters.size(); ++monsterIndex) {
            AbstractMonster monster = monsters.get(monsterIndex);
            if (monster == null) continue;
            if (replacedLargeSlimeParent(encounter, monster, monsters)) continue;
            if (replacedSlimeBossParent(encounter, monster, monsters)) continue;
            int sameIdOrdinal = seenMonsterIds.containsKey(monster.id)
                    ? seenMonsterIds.get(monster.id) : 0;
            seenMonsterIds.put(monster.id, sameIdOrdinal + 1);
            Integer reflected = reflectedEncounterSlot(encounter, monster);
            int preferred = reflected != null ? reflected : preferredMonsterSlot(
                    encounter, monster.id, sameIdOrdinal,
                    "GremlinLeader".equals(monster.id) ? -1 : nonLeaderOrdinal);
            if (!"GremlinLeader".equals(monster.id)) ++nonLeaderOrdinal;
            int slot;
            if ("SLIME_BOSS".equals(encounter) && preferred >= 0) {
                // Slime Boss and its large-child splits use a fixed native
                // layout (0, 1, 2). Java leaves replaced parents in its
                // monster list, so retain the native slot rather than the
                // stale Java-object assignment from before the split.
                slot = preferred;
                monsterSlots.put(monster, slot);
                usedMonsterSlots.add(slot);
            } else {
                slot = monsterSlot(monster, preferred >= 0 ? preferred : monsterIndex,
                        usedMonsterSlots);
            }
            emitted.put(monster, slot);
        }
        return emitted;
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
        if (count(counts, "BronzeAutomaton") == 1
                && count(counts, "BronzeOrb") == total - 1
                && total >= 1 && total <= 3)
            return "AUTOMATON";
        if (total == 2 && weakWildlifeCount(counts) == 1 && strongHumanoidCount(counts) == 1)
            return "EXORDIUM_THUGS";
        if (total == 2 && strongWildlifeCount(counts) == 1
                && weakWildlifeCount(counts) == 1)
            return "EXORDIUM_WILDLIFE";
        if (shapeCount(counts) == 3 && total == 3) return "THREE_SHAPES";
        if (shapeCount(counts) == 4 && total == 4) return "FOUR_SHAPES";
        if (counts.size() == 2) {
            int daggerCount = count(counts, "Dagger") + count(counts, "SnakeDagger");
            int taskmasterCount = count(counts, "Taskmaster") + count(counts, "SlaverBoss");
            if (count(counts, "Reptomancer") == 1
                    && daggerCount >= 1 && daggerCount <= 4)
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
            if ((count(counts, "Shelled Parasite") + count(counts, "ShelledParasite")) == 1
                    && count(counts, "FungiBeast") == 1)
                return "SHELLED_PARASITE_AND_FUNGI";
            if (count(counts, "Donu") == 1 && count(counts, "Deca") == 1)
                return "DONU_AND_DECA";
            if (count(counts, "SpireShield") == 1 && count(counts, "SpireSpear") == 1)
                return "SHIELD_AND_SPEAR";
            if (count(counts, "Looter") == 1 && count(counts, "Mugger") == 1)
                return "TWO_THIEVES";
            if (taskmasterCount == 1 && count(counts, "GremlinNob") == 1)
                return "COLOSSEUM_EVENT_NOBS";
        }
        if (count(counts, "SlaverBlue") == 1 && count(counts, "SlaverRed") == 1
                && (count(counts, "Taskmaster") + count(counts, "SlaverBoss")) == 1 && total == 3)
            return "SLAVERS";
        if (count(counts, "SlaverBlue") == 1 && count(counts, "SlaverRed") == 1
                && count(counts, "Taskmaster") + count(counts, "SlaverBoss") == 0)
            return "COLOSSEUM_EVENT_SLAVERS";
        if ((count(counts, "BanditPointy") + count(counts, "BanditChild")) == 1
                && count(counts, "BanditLeader") == 1
                && count(counts, "BanditBear") == 1)
            return "MASKED_BANDITS_EVENT";
        if (count(counts, "Orb Walker") == 2 && total == 2)
            return "MYSTERIOUS_SPHERE_EVENT";
        if (count(counts, "SphericGuardian") == 1 && shapeCount(counts) == 2 && total == 3)
            return "SPHERE_AND_TWO_SHAPES";
        if (count(counts, "TheCollector") == 1
                && count(counts, "TorchHead") >= 0
                && total >= 1 && total <= 3) {
            int nonCollector = total - count(counts, "TheCollector");
            if (nonCollector == count(counts, "TorchHead")) return "COLLECTOR";
        }
        if ((count(counts, "Taskmaster") + count(counts, "SlaverBoss")) == 1
                && count(counts, "GremlinNob") == 1 && total == 2)
            return "COLOSSEUM_EVENT_NOBS";
        if (count(counts, "GremlinLeader") == 1 && total >= 2 && total <= 3) {
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
        String previous = lastRoomClass;
        if (previous.isEmpty()) previous = previousRoomClassFromPath(
                AbstractDungeon.currMapNode.x, AbstractDungeon.currMapNode.y);
        // A freshly started inspector can observe a saved run directly inside
        // the act boss before observeRoomTransition has rebuilt its in-memory
        // latch. The persisted metric path includes the boss sentinel, so use
        // the last preceding non-boss room identity.
        if (previous.isEmpty() && room instanceof com.megacrit.cardcrawl.rooms.MonsterRoomBoss
                && CardCrawlGame.metricData != null
                && CardCrawlGame.metricData.path_taken != null
                && !CardCrawlGame.metricData.path_taken.isEmpty()) {
            List<String> pathTaken = CardCrawlGame.metricData.path_taken;
            for (int i = pathTaken.size() - 1; i >= 0 && previous.isEmpty(); --i) {
                String candidate = metricRoomClass(pathTaken.get(i));
                if (!"BOSS".equals(candidate)) previous = candidate;
            }
        }
        if (previous.isEmpty() && room instanceof com.megacrit.cardcrawl.rooms.MonsterRoomBoss) {
            List<MapRoomNode> parents = AbstractDungeon.currMapNode.getParents();
            if (parents != null) {
                for (MapRoomNode parent : parents) {
                    if (parent != null && parent.taken && parent.room != null) {
                        previous = roomClass(parent.room);
                        break;
                    }
                }
                if (previous.isEmpty() && parents.size() == 1 && parents.get(0) != null)
                    previous = roomClass(parents.get(0).room);
            }
        }
        if (previous.isEmpty() && room instanceof com.megacrit.cardcrawl.rooms.MonsterRoomBoss
                && AbstractDungeon.pathX != null && AbstractDungeon.pathY != null
                && AbstractDungeon.pathX.size() == AbstractDungeon.pathY.size()
                && !AbstractDungeon.pathX.isEmpty()) {
            int last = AbstractDungeon.pathX.size() - 1;
            int x = AbstractDungeon.pathX.get(last), y = AbstractDungeon.pathY.get(last);
            if (AbstractDungeon.map != null && y >= 0 && y < AbstractDungeon.map.size()) {
                List<MapRoomNode> row = AbstractDungeon.map.get(y);
                if (row != null && x >= 0 && x < row.size() && row.get(x) != null)
                    previous = roomClass(row.get(x).room);
            }
        }
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
                .append("\",\"previousRoomClass\":\"").append(previous)
                .append("\",\"encounter\":\"").append(encounter)
                .append("\",\"potionKeepValue\":4.0,\"isBurningElite\":")
                .append(burningElite)
                .append(",\"potionCapacity\":").append(AbstractDungeon.player.potionSlots)
                .append(",\"deck\":").append(deckEntryJson())
                .append(",\"relics\":").append(relicEntryJson())
                .append(",\"potions\":").append(potionEntryJson()).append('}');
        return out.toString();
    }

    private static String metricRoomClass(String symbol) {
        if (symbol == null || "N".equals(symbol)) return "NONE";
        switch (symbol) {
            case "$": return "SHOP";
            case "R": return "REST";
            case "?": return "EVENT";
            case "E": return "ELITE";
            case "M": return "MONSTER";
            case "T": return "TREASURE";
            case "B": case "BOSS": return "BOSS";
            default: return "";
        }
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

    static int combatEntryRelicData(String id, int counter, boolean usedUp) {
        // A spent Neow's Lament or Omamori may report Java's -2 used-up
        // sentinel; native CTM stores remaining charges (0 when spent).
        // Keep every other value exact and fail closed.
        final boolean spentCharges = "NeowsBlessing".equals(id) || "Omamori".equals(id);
        // Ancient Tea Set is charged (vanilla counter -2) from entering a rest
        // site until the next combat; native stores 1 when charged, else 0.
        if ("Ancient Tea Set".equals(id)) return counter == -2 ? 1 : 0;
        return spentCharges && usedUp && counter == -2 ? 0 : counter;
    }

    private static String relicEntryJson() {
        StringBuilder out = new StringBuilder("["); boolean first = true;
        for (com.megacrit.cardcrawl.relics.AbstractRelic relic : AbstractDungeon.player.relics) {
            if (!first) out.append(','); first = false;
            out.append("{\"id\":\"").append(escapeJson(relic.relicId))
                    .append("\",\"data\":").append(combatEntryRelicData(relic.relicId, relic.counter, relic.usedUp))
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

    static int combatCardMisc(String id, int misc, int timesUpgraded, int baseDamage) {
        if ("Searing Blow".equals(id)) return timesUpgraded;
        if ("Rampage".equals(id)) return baseDamage - 8;
        return misc;
    }

    private static String cardJson(AbstractCard card) {
        return "{\"id\":\"" + escapeJson(card.cardID) + "\",\"uuid\":\"" +
                escapeJson(String.valueOf(card.uuid)) + "\",\"upgraded\":" +
                (card.upgraded ? "true" : "false") + ",\"misc\":" +
                combatCardMisc(card.cardID, card.misc, card.timesUpgraded, card.baseDamage) +
                ",\"cost\":" + card.cost + ",\"costForTurn\":" + card.costForTurn +
                ",\"freeToPlayOnce\":" + (card.freeToPlayOnce ? "true" : "false") +
                ",\"retain\":" + (card.retain ? "true" : "false") + "}";
    }

    private static String cardJson(AbstractCard card, String location) {
        String base = cardJson(card);
        return base.substring(0, base.length() - 1) +
                ",\"location\":\"" + location + "\"}";
    }

    private static String cardQueueItemJson(boolean qualifiedSourceCleanup) {
        if (!trackedLastCardQueueItem.present) return "null";
        TrackedCardQueueItem item = trackedLastCardQueueItem;
        return "{\"card\":" + item.cardJson
                + ",\"target\":" + item.target
                + ",\"energyOnUse\":" + item.energyOnUse
                + ",\"isEndTurn\":" + item.isEndTurn
                + ",\"triggerOnUse\":" + item.triggerOnUse
                + ",\"ignoreEnergyTotal\":" + item.ignoreEnergyTotal
                + ",\"freeToPlay\":" + item.freeToPlay
                + ",\"randomTarget\":" + item.randomTarget
                + ",\"autoplay\":" + item.autoplay
                + ",\"regretCardCount\":" + item.regretCardCount
                + ",\"purgeOnUse\":" + item.purgeOnUse
                + ",\"exhaustOnUse\":" + (qualifiedSourceCleanup?sourceCleanupExhaust():item.exhaustOnUse) + "}";
    }

    private static List<PendingCardQueueCapture.Item> pendingCardQueueItems(IdentityHashMap<AbstractMonster,Integer> slots) {
        List<PendingCardQueueCapture.Item> snapshot = new ArrayList<>();
        for (CardQueueItem item : AbstractDungeon.actionManager.cardQueue) {
            if (item == null) { snapshot.add(null); continue; }
            PendingCardQueueCapture.Item observed = new PendingCardQueueCapture.Item();
            observed.identity = item;
            observed.vanilla = item.getClass() == CardQueueItem.class;
            observed.hasMonster = item.monster != null;
            observed.target = item.monster == null ? null : slots.get(item.monster);
            observed.endTurnAutoPlay = item.isEndTurnAutoPlay;
            observed.energyOnUse = item.energyOnUse;
            observed.ignoreEnergyTotal = item.ignoreEnergyTotal;
            observed.randomTarget = item.randomTarget;
            observed.autoplay = item.autoplayCard;
            if (item.card != null) {
                AbstractCard card = item.card;
                observed.cardJson = cardJson(card);
                observed.cardId = card.cardID;
                observed.vanillaEndTurnCard = card.getClass() == com.megacrit.cardcrawl.cards.status.Burn.class
                        || card.getClass() == com.megacrit.cardcrawl.cards.curses.Decay.class
                        || card.getClass() == com.megacrit.cardcrawl.cards.curses.Doubt.class
                        || card.getClass() == com.megacrit.cardcrawl.cards.curses.Shame.class
                        || card.getClass() == com.megacrit.cardcrawl.cards.curses.Regret.class;
                if (card.getClass() == com.megacrit.cardcrawl.cards.curses.Regret.class
                        && card.magicNumber == card.baseMagicNumber)
                    observed.regretCardCount = card.magicNumber;
                for(AbstractCard handCard:AbstractDungeon.player.hand.group) if(handCard==card) observed.inHand=true;
                observed.uuid = card.uuid == null ? null : card.uuid.toString();
                observed.requiresTarget = card.target == AbstractCard.CardTarget.ENEMY
                        || card.target == AbstractCard.CardTarget.SELF_AND_ENEMY;
                observed.triggerOnUse = !card.dontTriggerOnUseCard;
                observed.freeToPlay = card.freeToPlayOnce;
                observed.purgeOnUse = card.purgeOnUse;
                observed.exhaustOnUse = card.exhaust || card.exhaustOnUseOnce || card.exhaustOnFire;
            }
            snapshot.add(observed);
        }
        return snapshot;
    }

    private static PendingCardQueueCapture.Result pendingCardQueue(IdentityHashMap<AbstractMonster,Integer> slots,
                                                                   boolean codexEndTurn) {
        return PendingCardQueueCapture.capture(pendingCardQueueItems(slots), trackedLastCardQueueItem.physicalItem,
                codexEndTurn,hasRelic("Unceasing Top"));
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

    // A Smoke Bomb escape keeps the room in COMBAT with an idle action queue
    // while the player runs off (isEscaping), then endBattle() runs (which
    // clears the Runic Dome occupant binding) before the phase leaves COMBAT.
    // Native combat already ended when the potion was used; neither window is
    // a player decision.
    static boolean isCombatEnding(boolean battleOver, boolean smoked, boolean playerEscaping) {
        return battleOver || smoked || playerEscaping;
    }

    static boolean isCombatBoundary(AbstractRoom.RoomPhase phase, AbstractDungeon.CurrentScreen screen,
                                    boolean playerDecision, boolean selectionAvailable, boolean combatEnding) {
        // EventRoom fights are combat too. Serializer support is a separate
        // question: an unknown selection must reach Silver as UNSUPPORTED.
        return phase == AbstractRoom.RoomPhase.COMBAT && !combatEnding
                && ((screen == AbstractDungeon.CurrentScreen.NONE && playerDecision)
                    || ((screen == AbstractDungeon.CurrentScreen.GRID
                         || screen == AbstractDungeon.CurrentScreen.HAND_SELECT
                         || screen == AbstractDungeon.CurrentScreen.CARD_REWARD) && selectionAvailable));
    }

    private static boolean isCardSelectionBoundary() {
        if (AbstractDungeon.actionManager == null) return false;
        return (AbstractDungeon.screen == AbstractDungeon.CurrentScreen.GRID
                    && AbstractDungeon.gridSelectScreen != null)
                || (AbstractDungeon.screen == AbstractDungeon.CurrentScreen.HAND_SELECT
                    && AbstractDungeon.handCardSelectScreen != null)
                || (AbstractDungeon.screen == AbstractDungeon.CurrentScreen.CARD_REWARD
                    && AbstractDungeon.cardRewardScreen != null);
    }

    static void recordCardQueueItem(CardQueueItem item) {
        if (item == null || (item.card == null && !item.isEndTurnAutoPlay)) return;
        String encounter = liveEncounter;
        if (encounter.isEmpty() && AbstractDungeon.getCurrRoom() != null)
            encounter = INSTANCE.encounterName(AbstractDungeon.getCurrRoom());
        IdentityHashMap<AbstractMonster, Integer> emittedSlots =
                emittedMonsterSlots(encounter);
        if (item.monster != null && AbstractDungeon.getMonsters() != null
                && AbstractDungeon.getMonsters().monsters.indexOf(item.monster) >= 0)
            trackedLastTargetedMonster = item.monster;

        trackedLastCardQueueItem.present = true;
        trackedLastCardQueueItem.physicalCard = item.card;
        trackedLastCardQueueItem.physicalItem = item;
        trackedLastCardQueueItem.cardJson = item.card == null ? "null" : cardJson(item.card);
        Integer target = item.monster == null ? null : emittedSlots.get(item.monster);
        if (target == null && item.monster != null) target = monsterSlots.get(item.monster);
        trackedLastCardQueueItem.target = target == null || target < 0 ? 0 : target;
        trackedLastCardQueueItem.energyOnUse = item.energyOnUse;
        trackedLastCardQueueItem.isEndTurn = item.isEndTurnAutoPlay;
        trackedLastCardQueueItem.triggerOnUse = item.card == null
                || !item.card.dontTriggerOnUseCard;
        trackedLastCardQueueItem.ignoreEnergyTotal = item.ignoreEnergyTotal;
        trackedLastCardQueueItem.freeToPlay = item.card != null && item.card.freeToPlayOnce;
        trackedLastCardQueueItem.randomTarget = item.randomTarget;
        trackedLastCardQueueItem.autoplay = item.autoplayCard;
        Integer regretCount = readIntField(item, "regretCardCount", "regretCount");
        if (regretCount == null && item.card != null)
            regretCount = readIntField(item.card, "regretCardCount", "regretCount");
        trackedLastCardQueueItem.regretCardCount = regretCount == null ? 0 : regretCount;
        trackedLastCardQueueItem.purgeOnUse = item.card != null && item.card.purgeOnUse;
        trackedLastCardQueueItem.exhaustOnUse = item.card != null
                && (item.card.exhaust || item.card.exhaustOnUseOnce || item.card.exhaustOnFire);
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

    static Integer awakenedNativePhase(Boolean form1, boolean halfDead) {
        // Vanilla flips form1 in damage(), before the rebirth move executes.
        // Native remains in phase zero through the half-dead interval.
        return form1 == null ? null : (form1 || halfDead ? 0 : 1);
    }

    static Integer guardianNativeThreshold(Integer threshold, Integer increase, Boolean isOpen) {
        // Vanilla increments on Defensive Mode; native increments on Twin Slam.
        // The remaining Mode Shift power is exported separately as a status.
        if (threshold == null || increase == null || isOpen == null || increase != 10)
            return null;
        int nativeThreshold = threshold - (isOpen ? 0 : increase);
        return nativeThreshold > 0 ? nativeThreshold : null;
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

    private static Boolean monsterPowerJustApplied(AbstractPower power) {
        Boolean justApplied = readBooleanField(power, "justApplied");
        if (justApplied != null) return justApplied;
        // RitualPower uses its own turn-local name for the same public
        // contract represented natively by MonsterStatus::RITUAL's
        // just-applied bit.
        if ("Ritual".equals(power.ID) || "RitualPower".equals(power.ID))
            return readBooleanField(power, "skipFirst");
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

    static Integer bronzeAutomatonNativeTurns(Integer numTurns) {
        // Native now follows vanilla's getMove counter directly. Dome reconstructs
        // its pre-roll counter from public executions and bypasses this accessor.
        return numTurns == null || numTurns < 0 || numTurns > 4 ? null : numTurns;
    }

    private static Integer bronzeAutomatonMiscInfo(AbstractMonster monster) {
        return bronzeAutomatonNativeTurns(readIntField(monster, "numTurns"));
    }

    private static Integer monsterUniquePower0(AbstractMonster monster) {
        if ("Hexaghost".equals(monster.id))
            return readIntField(monster, "orbActiveCount");
        return null;
    }

    private static Integer monsterMiscInfo(AbstractMonster monster) {
        String id = monster.id;
        if ("FuzzyLouseNormal".equals(id) || "FuzzyLouseDefensive".equals(id))
            return readIntField(monster, "biteDamage", "dmg");
        if ("Darkling".equals(id)) return readIntField(monster, "nipDmg");
        if ("GremlinWizard".equals(id)) return readIntField(monster, "currentCharge");
        if ("Hexaghost".equals(id)) {
            // Native Silver keeps the per-hit Divider damage in miscInfo. The
            // Java intent damage is the same finalized value once Divider is
            // selected. Native keeps that value after Divider resolves, so
            // retain the observed public value for this monster object until
            // the next Activate move replaces it.
            if (monster.nextMove == 1) {
                hexaghostDividerDamage.put(monster, monster.getIntentDmg());
            }
            Integer dividerDamage = hexaghostDividerDamage.get(monster);
            return dividerDamage == null ? 0 : dividerDamage;
        }
        if ("TheGuardian".equals(id)) {
            return guardianNativeThreshold(readIntField(monster, "dmgThreshold"),
                    readIntField(monster, "dmgThresholdIncrease"),
                    readBooleanField(monster, "isOpen"));
        }
        if ("BookOfStabbing".equals(id)) return readIntField(monster, "stabCount");
        if ("SlaverBlue".equals(id)) return 0;
        if ("SlaverRed".equals(id)) {
            Boolean used = readBooleanField(monster, "usedEntangle");
            return used == null ? null : (used ? 1 : 0);
        }
        if ("Champ".equals(id)) {
            Boolean phase2 = readBooleanField(monster, "thresholdReached");
            if (phase2 == null) return null;
            Integer forgeTimes = readIntField(monster, "forgeTimes");
            if (forgeTimes == null) return null;
            return (phase2 ? 4 : 0) | Math.min(3, forgeTimes);
        }
        if ("BronzeAutomaton".equals(id)) return bronzeAutomatonMiscInfo(monster);
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
            return awakenedNativePhase(form1, monster.halfDead);
        }
        if ("WrithingMass".equals(id)) {
            Boolean used = readBooleanField(monster, "usedMegaDebuff");
            return used == null ? null : (used ? 1 : 0);
        }
        if ("Looter".equals(id) || "Mugger".equals(id))
            return readIntField(monster, "stolenGold");
        return statelessMonsterMiscInfo(id);
    }

    static Integer publicMonsterMiscInfo(boolean runicDome, java.util.function.Supplier<Integer> visible) {
        return runicDome ? Integer.valueOf(0) : visible.get();
    }

    static Integer statelessMonsterMiscInfo(String id) {
        // Explicit zero is safe only for monsters whose native move logic does
        // not consult miscInfo. Unknown/reflectively inaccessible state is
        // omitted and therefore rejected by the importer.
        if ("AcidSlime_L".equals(id) || "AcidSlime_M".equals(id)
                || "AcidSlime_S".equals(id) || "AwakenedOne".equals(id)
                || "BanditBear".equals(id) || "BanditChild".equals(id)
                || "BanditLeader".equals(id) || "Bear".equals(id)
                || "BlueSlaver".equals(id) || "BronzeOrb".equals(id)
                || "Byrd".equals(id) || "Centurion".equals(id)
                || "Chosen".equals(id) || "CorruptHeart".equals(id)
                || "Cultist".equals(id) || "Dagger".equals(id)
                || "Deca".equals(id) || "Donu".equals(id)
                || "Exploder".equals(id) || "FungiBeast".equals(id)
                || "GiantHead".equals(id) || "JawWorm".equals(id)
                || "GremlinFat".equals(id) || "GremlinLeader".equals(id)
                || "GremlinWarrior".equals(id) || "GremlinTsundere".equals(id)
                || "GremlinNob".equals(id)
                || "SpikeSlime_L".equals(id) || "SpikeSlime_M".equals(id)
                || "SpikeSlime_S".equals(id) || "Lagavulin".equals(id)
                || "Healer".equals(id) || "Reptomancer".equals(id)
                || "SlimeBoss".equals(id)
                || "MadGremlin".equals(id) || "Mystic".equals(id)
                || "Nemesis".equals(id) || "Orb Walker".equals(id)
                || "Pointy".equals(id) || "RedSlaver".equals(id)
                || "Repulsor".equals(id) || "Romeo".equals(id)
                || "Sentry".equals(id) || "Shelled Parasite".equals(id)
                || "ShelledParasite".equals(id) || "GremlinSneaky".equals(id)
                || "GremlinShield".equals(id) || "GremlinThief".equals(id)
                || "SnakePlant".equals(id) || "Snecko".equals(id)
                || "SphericGuardian".equals(id) || "SpireGrowth".equals(id)
                || "Serpent".equals(id) || "SpireShield".equals(id)
                || "SpireSpear".equals(id) || "Taskmaster".equals(id)
                || "SlaverBoss".equals(id) || "TheCollector".equals(id)
                || "TheMaw".equals(id) || "Maw".equals(id)
                || "TimeEater".equals(id) || "TorchHead".equals(id)
                || "Transient".equals(id)) return 0;
        return null;
    }

    private static String selectionTask(String text, boolean anyNumber) {
        String lower = text == null ? "" : text.toLowerCase(Locale.ROOT);
        if (lower.contains("exhaust")) return anyNumber ? "EXHAUST_MANY" : "EXHAUST_ONE";
        if (lower.contains("upgrade")) return "ARMAMENTS";
        if (lower.contains("copy") || lower.contains("duplicate")) return "DUAL_WIELD";
        if (lower.contains("exhume") || lower.contains("exhaust pile")) return "EXHUME";
        if (lower.contains("warcry") || lower.contains("war cry")) return "WARCRY";
        if (lower.contains("liquid memories")) return "LIQUID_MEMORIES_POTION";
        if (lower.contains("gambler") || lower.contains("gamble")) return "GAMBLE";
        if (lower.contains("top") && lower.contains("draw")) return "HEADBUTT";
        if (lower.contains("discard")) return "GAMBLE";
        if (lower.contains("return") || lower.contains("hand")) return "HOLOGRAM";
        return "";
    }

    static String handSelectionTask(String reason, boolean anyNumber, boolean canPickZero, int count) {
        String task = selectionTask(reason, anyNumber);
        if (task.isEmpty() && anyNumber && canPickZero && count == 99) return "GAMBLE";
        return task;
    }

    // These vanilla action classes own the selection until its cards are
    // returned. Their identity is independent of localized prompt text.
    // null means no qualified override; empty means a known unsupported shape.
    static String actionSelectionTask(String actionClass, boolean hand, boolean anyNumber, int count) {
        if ("com.megacrit.cardcrawl.actions.common.BetterDiscardPileToHandAction".equals(actionClass))
            return !hand && !anyNumber && (count == 1 || count == 2) ? "LIQUID_MEMORIES_POTION" : "";
        if ("com.megacrit.cardcrawl.actions.unique.DualWieldAction".equals(actionClass))
            return hand && !anyNumber && count == 1 ? "DUAL_WIELD" : "";
        if ("com.megacrit.cardcrawl.actions.unique.ArmamentsAction".equals(actionClass))
            return hand && !anyNumber && count == 1 ? "ARMAMENTS" : "";
        if ("com.megacrit.cardcrawl.actions.unique.ExhumeAction".equals(actionClass))
            return !hand && !anyNumber && count == 1 ? "EXHUME" : "";
        if ("com.megacrit.cardcrawl.actions.common.ExhaustAction".equals(actionClass))
            return !hand ? "" : !anyNumber && count == 1 ? "EXHAUST_ONE"
                    : anyNumber && (count == 3 || count == 5 || count == 99) ? "EXHAUST_MANY" : "";
        if ("com.megacrit.cardcrawl.actions.unique.GamblingChipAction".equals(actionClass))
            return hand && anyNumber && count == 99 ? "GAMBLE" : "";
        if ("com.megacrit.cardcrawl.actions.common.DiscardAction".equals(actionClass)) return "";
        if ("com.megacrit.cardcrawl.actions.unique.DiscardPileToTopOfDeckAction".equals(actionClass))
            return !hand && !anyNumber && count == 1 ? "HEADBUTT" : "";
        if ("com.megacrit.cardcrawl.actions.common.PutOnDeckAction".equals(actionClass))
            return hand && !anyNumber && count == 1 ? "WARCRY" : "";
        if ("com.megacrit.cardcrawl.actions.unique.ForethoughtAction".equals(actionClass))
            return hand && ((!anyNumber && count == 1) || (anyNumber && count == 99)) ? "FORETHOUGHT" : "";
        if ("com.megacrit.cardcrawl.actions.unique.SkillFromDeckToHandAction".equals(actionClass))
            return !hand && !anyNumber && count == 1 ? "SECRET_TECHNIQUE" : "";
        if ("com.megacrit.cardcrawl.actions.unique.AttackFromDeckToHandAction".equals(actionClass))
            return !hand && !anyNumber && count == 1 ? "SECRET_WEAPON" : "";
        return null;
    }

    private static String currentActionSelectionTask(boolean hand, boolean anyNumber, int count) {
        Object action = AbstractDungeon.actionManager == null ? null : AbstractDungeon.actionManager.currentAction;
        return actionSelectionTask(action == null ? "" : action.getClass().getName(), hand, anyNumber, count);
    }

    static String selectionJson(String task, boolean canPickZero, boolean anyNumber, int pickCount,
                                        List<AbstractCard> source) {
        StringBuilder out = new StringBuilder("{\"task\":\"")
                .append(task).append("\",\"canPickZero\":").append(canPickZero)
                .append(",\"canPickAnyNumber\":")
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

    static String singleSelectionJson(String task, String origin, boolean canPickZero,
                                      boolean anyNumber, int count, int selectedCount,
                                      List<String> uuids, int liveChoiceCount) {
        boolean hand = "HAND_SELECT".equals(origin);
        boolean qualified = hand ? "WARCRY".equals(task) || "FORETHOUGHT".equals(task) || "EXHAUST_ONE".equals(task) || "ARMAMENTS".equals(task) || "DUAL_WIELD".equals(task) || "GAMBLE".equals(task) || "EXHAUST_MANY".equals(task)
                : "GRID".equals(origin) && ("SECRET_TECHNIQUE".equals(task) || "SECRET_WEAPON".equals(task) || "HEADBUTT".equals(task) || "EXHUME".equals(task) || "LIQUID_MEMORIES_POTION".equals(task));
        boolean multiForethought = hand && canPickZero && anyNumber
                && (("FORETHOUGHT".equals(task) || "GAMBLE".equals(task)) && count == 99
                    || "EXHAUST_MANY".equals(task) && (count == 3 || count == 5 || count == 99));
        boolean liquidPair = !hand && "LIQUID_MEMORIES_POTION".equals(task) && !canPickZero && !anyNumber && count == 2;
        if (!qualified || (!multiForethought && !liquidPair && (canPickZero || anyNumber || count != 1)) || selectedCount != 0
                || uuids == null || uuids.isEmpty() || uuids.size() != liveChoiceCount
                || ("LIQUID_MEMORIES_POTION".equals(task) && uuids.size() <= count)
                || uuids.contains(null) || uuids.contains("")
                || new java.util.HashSet<String>(uuids).size() != uuids.size())
            return "{\"task\":\"\",\"unsupportedReason\":\"silver_selection_live_choices\"}";
        String base = selectionJson(task, canPickZero, anyNumber, count, null);
        StringBuilder out = new StringBuilder(base.substring(0, base.length() - 1));
        out.append(",\"origin\":\"").append(origin).append("\",\"selectedCount\":0");
        if (multiForethought) out.append(",\"actionClass\":\"").append("FORETHOUGHT".equals(task)
                ? "com.megacrit.cardcrawl.actions.unique.ForethoughtAction" : "GAMBLE".equals(task)
                ? "com.megacrit.cardcrawl.actions.unique.GamblingChipAction" : "com.megacrit.cardcrawl.actions.common.ExhaustAction").append("\"");
        out.append(",\"liveChoices\":[");
        for (int i = 0; i < uuids.size(); ++i) {
            if (i != 0) out.append(',');
            out.append("{\"uuid\":\"").append(escapeJson(uuids.get(i)))
                    .append("\",\"choiceIndex\":").append(i + 1).append('}');
        }
        return out.append("]}").toString();
    }

    static String completedSingleSelectionJson(String task, String actionClass, int pickCount,
                                                List<String> selected, int choiceCount,
                                                boolean canProceed, boolean canCancel) {
        if (!("WARCRY".equals(task) || "FORETHOUGHT".equals(task) || "EXHAUST_ONE".equals(task) || "ARMAMENTS".equals(task) || "DUAL_WIELD".equals(task))
                || !task.equals(actionSelectionTask(actionClass, true, false, pickCount))
                || pickCount != 1 || selected == null || selected.size() != 1
                || selected.get(0) == null || selected.get(0).isEmpty()
                || choiceCount != 0 || !canProceed || canCancel) return null;
        return "{\"task\":\"" + task + "\",\"origin\":\"HAND_SELECT\","
                + "\"mechanicalTransition\":\"single_select_confirm\",\"actionClass\":\"" + escapeJson(actionClass)
                + "\",\"pickCount\":1,\"selectedCount\":1,\"selectedUuid\":\"" + escapeJson(selected.get(0))
                + "\",\"liveChoiceCount\":0,\"canProceed\":true,\"canCancel\":false}";
    }

    private static String liveSingleSelectionJson(String task, boolean hand, boolean canPickZero,
                                                  boolean anyNumber, int count, int selectedCount) {
        List<String> uuids = new ArrayList<>();
        int choiceCount = -1;
        try {
            // These are the same list and indices used by MCPTheSpire's choose
            // implementation. Grid order is not the native draw-pile order.
            Class<?> choices = Class.forName("mcpthespire.ChoiceScreenUtils");
            Object labels = choices.getMethod("getCurrentChoiceList").invoke(null);
            Object cards = hand ? AbstractDungeon.player.hand.group
                    : choices.getMethod("getGridScreenCards").invoke(null);
            if (labels instanceof List && cards instanceof List) {
                choiceCount = ((List<?>) labels).size();
                if (hand && !canPickZero && !anyNumber && selectedCount == 1) {
                    List<String> selected = new ArrayList<>();
                    for (AbstractCard card : AbstractDungeon.handCardSelectScreen.selectedCards.group)
                        selected.add(card.uuid == null ? null : card.uuid.toString());
                    Object action = AbstractDungeon.actionManager == null ? null : AbstractDungeon.actionManager.currentAction;
                    String confirmation = completedSingleSelectionJson(task, action == null ? "" : action.getClass().getName(),
                            count, selected, choiceCount,
                            Boolean.TRUE.equals(choices.getMethod("isConfirmButtonAvailable").invoke(null)),
                            Boolean.TRUE.equals(choices.getMethod("isCancelButtonAvailable").invoke(null)));
                    if (confirmation != null) return confirmation;
                }
                for (Object value : (List<?>) cards) {
                    if (!(value instanceof AbstractCard)) { uuids.add(null); continue; }
                    AbstractCard card = (AbstractCard) value;
                    uuids.add(card.uuid == null ? null : card.uuid.toString());
                }
            }
        } catch (ReflectiveOperationException | LinkageError error) {
            // Missing or changed MCP contracts cannot be replaced by pile order.
        }
        String result = singleSelectionJson(task, hand ? "HAND_SELECT" : "GRID", canPickZero,
                anyNumber, count, selectedCount, uuids, choiceCount);
        if ("LIQUID_MEMORIES_POTION".equals(task)) {
            Object action = AbstractDungeon.actionManager.currentAction;
            if (!Integer.valueOf(count).equals(readIntField(action,"numberOfCards"))
                    || !Boolean.FALSE.equals(readBooleanField(action,"optional"))
                    || !Boolean.TRUE.equals(readBooleanField(action,"setCost"))
                    || !Integer.valueOf(0).equals(readIntField(action,"newCost"))
                    || handMultiContinuation("GAMBLE")==null)
                return "{\"task\":\"\",\"unsupportedReason\":\"silver_selection_pending_actions\"}";
            result = result.substring(0,result.length()-1) + ",\"actionClass\":\"" + action.getClass().getName()
                    + "\",\"continuation\":\"" + handMultiContinuation("GAMBLE") + "\",\"optional\":false,\"newCost\":0}";
        }
        boolean sourceOwned=trackedLastCardQueueItem.physicalCard!=null
                && sourceSelectionOwner(task,trackedLastCardQueueItem.physicalCard.getClass().getName())
                && hasPendingUseCard();
        if ("GAMBLE".equals(task) || "EXHAUST_MANY".equals(task) && !sourceOwned) {
            String continuation = handMultiContinuation(task);
            if (continuation == null) return "{\"task\":\"\",\"unsupportedReason\":\"silver_selection_pending_actions\"}";
            result = result.substring(0,result.length()-1) + ",\"continuation\":\"" + continuation + "\"}";
        }
        if ("ARMAMENTS".equals(task) || "EXHUME".equals(task) || "DUAL_WIELD".equals(task)) {
            Object action = AbstractDungeon.actionManager.currentAction;
            boolean armaments = "ARMAMENTS".equals(task), dualWield = "DUAL_WIELD".equals(task);
            Integer copies = dualWield ? readIntField(action,"dupeAmount") : Integer.valueOf(0);
            Object held = readObjectField(action, armaments ? "cannotUpgrade" : dualWield ? "cannotDuplicate" : "exhumes");
            if (!(held instanceof List) || (dualWield ? copies == null || copies < 1 || copies > 2
                    : !Boolean.FALSE.equals(readBooleanField(action, armaments ? "upgraded" : "upgrade"))))
                return "{\"task\":\"\",\"unsupportedReason\":\"silver_selection_held_cards\"}";
            StringBuilder cards = new StringBuilder("[");
            for (Object item : (List<?>) held) {
                if (!(item instanceof AbstractCard)) return "{\"task\":\"\"}";
                AbstractCard card = (AbstractCard)item;
                if (armaments ? card.canUpgrade() : dualWield ? card.type == AbstractCard.CardType.ATTACK || card.type == AbstractCard.CardType.POWER : !"Exhume".equals(card.cardID)) return "{\"task\":\"\"}";
                if (cards.length() > 1) cards.append(','); cards.append(cardJson(card));
            }
            if (dualWield) result = result.replace("\"data0\":0", "\"data0\":" + copies);
            result = result.substring(0,result.length()-1) + ",\"actionClass\":\"" + action.getClass().getName()
                    + "\",\"upgradeVariant\":false,\"heldCards\":" + cards.append(']') + "}";
        }
        if(sourceOwned) {
            if(publicPendingActionsJson(false,task)==null)
                return "{\"task\":\"\",\"unsupportedReason\":\"silver_selection_pending_actions\"}";
            result=result.substring(0,result.length()-1)+",\"continuation\":\"source_card_actions\"}";
        }
        return result;
    }

    static boolean sourceSelectionOwner(String task,String cardClass) {
        String base="com.megacrit.cardcrawl.cards.";
        if("WARCRY".equals(task)) return (base+"red.Warcry").equals(cardClass) || (base+"colorless.ThinkingAhead").equals(cardClass);
        if("EXHAUST_ONE".equals(task)) return (base+"red.TrueGrit").equals(cardClass) || (base+"red.BurningPact").equals(cardClass);
        String suffix="ARMAMENTS".equals(task)?"red.Armaments":"DUAL_WIELD".equals(task)?"red.DualWield"
                :"EXHUME".equals(task)?"red.Exhume":"HEADBUTT".equals(task)?"red.Headbutt"
                :"FORETHOUGHT".equals(task)?"colorless.Forethought":"EXHAUST_MANY".equals(task)?"colorless.Purity"
                :"SECRET_TECHNIQUE".equals(task)?"colorless.SecretTechnique":"SECRET_WEAPON".equals(task)?"colorless.SecretWeapon"
                :"DISCOVERY".equals(task)?"colorless.Discovery":null;
        return suffix!=null && (base+suffix).equals(cardClass);
    }

    private static boolean hasPendingUseCard() {
        if(AbstractDungeon.actionManager==null)return false;
        for(Object action:AbstractDungeon.actionManager.actions)
            if("com.megacrit.cardcrawl.actions.utility.UseCardAction".equals(action.getClass().getName()))return true;
        return false;
    }

    private static boolean sourceCopyInPendingQueue(AbstractCard card) {
        if(card==null || card==trackedLastCardQueueItem.physicalCard || !card.purgeOnUse
                || !card.uuid.equals(trackedLastCardQueueItem.physicalCard.uuid))return false;
        for(CardQueueItem item:AbstractDungeon.actionManager.cardQueue)
            if(item.getClass()==CardQueueItem.class && item.card==card && item.autoplayCard
                    && item.ignoreEnergyTotal && !item.isEndTurnAutoPlay && !card.dontTriggerOnUseCard)return true;
        return false;
    }

    static boolean zeroCopyPower(String id,String className,int amount) {
        return amount==0 && (("Double Tap".equals(id) && "com.megacrit.cardcrawl.powers.DoubleTapPower".equals(className))
                || ("DuplicationPower".equals(id) && "com.megacrit.cardcrawl.powers.DuplicationPower".equals(className)));
    }

    private static boolean zeroCopyPowerRemoval(Object action) {
        if(!"com.megacrit.cardcrawl.actions.common.RemoveSpecificPowerAction".equals(action.getClass().getName())
                || readObjectField(action,"target")!=AbstractDungeon.player || readObjectField(action,"source")!=AbstractDungeon.player
                || readObjectField(action,"powerInstance")!=null)return false;
        String id=readStringField(action,"powerToRemove");
        AbstractPower power=id==null?null:AbstractDungeon.player.getPower(id);
        return power!=null && zeroCopyPower(power.ID,power.getClass().getName(),power.amount);
    }

    private static boolean projectedZeroCopyPower(AbstractPower power,String selection) {
        if(selection==null || !selection.contains("\"continuation\":\"source_card_actions\"")
                || !zeroCopyPower(power.ID,power.getClass().getName(),power.amount))return false;
        for(Object action:AbstractDungeon.actionManager.actions)
            if(zeroCopyPowerRemoval(action) && power.ID.equals(readStringField(action,"powerToRemove")))return true;
        return false;
    }

    static boolean sourceCleanupExhaust(boolean trackedExhaust,boolean skill,String powerClass) {
        return trackedExhaust || (skill && "com.megacrit.cardcrawl.powers.CorruptionPower".equals(powerClass));
    }

    private static boolean sourceCleanupExhaust() {
        AbstractCard card=trackedLastCardQueueItem.physicalCard;
        AbstractPower corruption=AbstractDungeon.player.getPower("Corruption");
        return sourceCleanupExhaust(trackedLastCardQueueItem.exhaustOnUse,card!=null && card.type==AbstractCard.CardType.SKILL,
                corruption==null?null:corruption.getClass().getName());
    }

    private static String pendingUseCardJson(Object action,String task) {
        AbstractCard card=trackedLastCardQueueItem.physicalCard;
        if(!trackedLastCardQueueItem.present || card==null || card.uuid==null || !trackedLastCardQueueItem.triggerOnUse
                || trackedLastCardQueueItem.isEndTurn || !sourceSelectionOwner(task,card.getClass().getName())
                || readObjectField(action,"targetCard")!=card
                || !Float.valueOf(0.15f).equals(readObjectField(action,"duration"))
                || !Boolean.FALSE.equals(readBooleanField(action,"returnToHand"))
                || !Boolean.FALSE.equals(readBooleanField(action,"reboundCard"))
                || !Boolean.valueOf(sourceCleanupExhaust()).equals(readBooleanField(action,"exhaustCard"))
                || card.purgeOnUse!=trackedLastCardQueueItem.purgeOnUse
                || AbstractDungeon.player.hand.group.contains(card) || AbstractDungeon.player.drawPile.group.contains(card)
                || AbstractDungeon.player.discardPile.group.contains(card) || AbstractDungeon.player.exhaustPile.group.contains(card)) return null;
        for(AbstractCard pending:AbstractDungeon.player.limbo.group)
            if(pending!=card && !sourceCopyInPendingQueue(pending))return null;
        return "{\"kind\":\"USE_CARD\",\"uuid\":\""+card.uuid+"\",\"actionClass\":\"com.megacrit.cardcrawl.actions.utility.UseCardAction\","
                + "\"unstarted\":true,\"returnToHand\":false,\"reboundCard\":false,\"triggerOnUse\":true,\"exhaustOnUse\":"
                + sourceCleanupExhaust() + ",\"purgeOnUse\":"+trackedLastCardQueueItem.purgeOnUse
                + ",\"autoplay\":"+trackedLastCardQueueItem.autoplay+"}";
    }

    // Values here describe unresolved public effects, never an RNG result or a
    // hidden card. Native samples random upgrade/target effects when executed.
    static String publicPendingActionJson(String kind, Integer amount, String power) {
        if (kind == null) return null;
        if ("GAMBLE".equals(kind) || "UPGRADE_RANDOM".equals(kind)
                || "REMOVE_PEN_NIB".equals(kind) || "REMOVE_PLAYER_DEBUFFS".equals(kind))
            return "{\"kind\":\"" + kind + "\"}";
        if (amount == null || amount < 0 || amount > 999) return null;
        if ("DRAW".equals(kind) && amount > 10) return null;
        if ("BUFF_PLAYER".equals(kind)) {
            if (!java.util.Arrays.asList("Strength","Dexterity","Artifact","Buffer","Plated Armor","Thorns","Vigor","IntangiblePlayer","Pen Nib").contains(power)
                    || amount == 0 || "Pen Nib".equals(power) && amount!=1) return null;
        } else if ("DEBUFF_PLAYER".equals(kind)) {
            if (!("Flex".equals(power) || "Weakened".equals(power) && amount==1) || amount == 0) return null;
        } else if ("DEBUFF_ALL_ENEMY".equals(kind)) {
            if (!("Vulnerable".equals(power) && amount==1 || "Weakened".equals(power) && amount==1 || "Poison".equals(power) && amount==4)) return null;
        } else if ("SHUFFLE_WOUNDS".equals(kind)) {
            if (amount != 2) return null;
        } else if (!java.util.Arrays.asList("DRAW","GAIN_BLOCK","GAIN_ENERGY","DAMAGE_ALL","DAMAGE_RANDOM").contains(kind)) return null;
        return "{\"kind\":\"" + kind + "\",\"amount\":" + amount
                + (power == null ? "" : ",\"power\":\"" + power + "\",\"sourceMonster\":false") + "}";
    }

    private static int allEnemyPowerBatch(List<?> actions,int first,String power,int amount) {
        String relic="Vulnerable".equals(power)?"Bag of Marbles":"Weakened".equals(power)?"Red Mask":"Poison".equals(power)?"TwistedFunnel":"";
        String className="Vulnerable".equals(power)?"VulnerablePower":"Weakened".equals(power)?"WeakPower":"PoisonPower";
        if(relic.isEmpty() || !hasRelic(relic) || publicPendingActionJson("DEBUFF_ALL_ENEMY",amount,power)==null
                || AbstractDungeon.getMonsters()==null || AbstractDungeon.getMonsters().monsters.isEmpty()) return -1;
        int index=first;
        for(AbstractMonster target:AbstractDungeon.getMonsters().monsters) {
            while(index<actions.size() && "com.megacrit.cardcrawl.actions.common.RelicAboveCreatureAction".equals(actions.get(index).getClass().getName()))++index;
            if(index>=actions.size())return -1;
            Object action=actions.get(index++), value=readObjectField(action,"powerToApply");
            if(!"com.megacrit.cardcrawl.actions.common.ApplyPowerAction".equals(action.getClass().getName())
                    || !Boolean.FALSE.equals(readBooleanField(action,"isDone"))
                    || readObjectField(action,"target")!=target || readObjectField(action,"source")!=AbstractDungeon.player
                    || !(value instanceof AbstractPower) || !value.getClass().getName().equals("com.megacrit.cardcrawl.powers."+className)
                    || !Integer.valueOf(amount).equals(readIntField(action,"amount")))return -1;
            AbstractPower applied=(AbstractPower)value;
            if(applied.owner!=target || !power.equals(applied.ID) || applied.amount!=amount
                    || (!"Poison".equals(power) && !Boolean.FALSE.equals(readBooleanField(applied,"justApplied"))))return -1;
        }
        return index;
    }

    // Vanilla sets monsterAttacksQueued after dispatching enemies and leaves
    // it true throughout the following player turn. AbstractRoom$1 resets it
    // only when the player ends that turn; it is not pending enemy work.
    // Actual enemy/pre-turn queues are checked separately by each continuation.
    static boolean playerSelectionTurn(boolean turnHasEnded, boolean endTurnQueued, boolean isEndingTurn) {
        return !turnHasEnded && !endTurnQueued && !isEndingTurn;
    }

    private static String publicPendingActionsJson(boolean opening) {
        return publicPendingActionsJson(opening,null);
    }

    private static String publicPendingActionsJson(boolean opening,String sourceTask) {
        com.megacrit.cardcrawl.actions.GameActionManager manager=AbstractDungeon.actionManager;
        if(manager==null || !playerSelectionTurn(manager.turnHasEnded, AbstractDungeon.player.endTurnQueued, AbstractDungeon.player.isEndingTurn)
                || !manager.preTurnActions.isEmpty() || !manager.monsterQueue.isEmpty()
                || (sourceTask==null && (!manager.cardQueue.isEmpty() || !AbstractDungeon.player.limbo.isEmpty()))
                || manager.actions.size()>128) return null;
        StringBuilder out=new StringBuilder("["); int draws=0,enables=0,cleanups=0;
        for(int actionIndex=0;actionIndex<manager.actions.size();++actionIndex) {
            Object action=manager.actions.get(actionIndex);
            String name=action.getClass().getName(), kind=null, power=null;
            Integer amount=readIntField(action,"amount");
            if(!Boolean.FALSE.equals(readBooleanField(action,"isDone"))) return null;
            if("com.megacrit.cardcrawl.actions.common.EnableEndTurnButtonAction".equals(name)) {++enables;continue;}
            if("com.megacrit.cardcrawl.actions.common.RelicAboveCreatureAction".equals(name)
                    || "com.megacrit.cardcrawl.actions.utility.WaitAction".equals(name)) continue;
            // Vanilla decrements copy charges synchronously, then queues a
            // removal with no onRemove override. The zero charge and its
            // visual removal are jointly omitted from the native projection.
            if(sourceTask!=null && zeroCopyPowerRemoval(action))continue;
            if("com.megacrit.cardcrawl.actions.utility.UseCardAction".equals(name)) {
                if(sourceTask==null || ++cleanups!=1)return null;
                String item=pendingUseCardJson(action,sourceTask);
                if(item==null)return null;
                if(out.length()>1)out.append(',');out.append(item);continue;
            }
            if("com.megacrit.cardcrawl.actions.common.RemoveSpecificPowerAction".equals(name)) {
                if(readObjectField(action,"target")!=AbstractDungeon.player || readObjectField(action,"source")!=AbstractDungeon.player
                        || readObjectField(action,"powerInstance")!=null || !"Pen Nib".equals(readStringField(action,"powerToRemove"))
                        || !hasRelic("Pen Nib"))return null;
                AbstractPower nib=AbstractDungeon.player.getPower("Pen Nib");
                if(nib==null || !"com.megacrit.cardcrawl.powers.PenNibPower".equals(nib.getClass().getName()))return null;
                kind="REMOVE_PEN_NIB";
            } else if("com.megacrit.cardcrawl.actions.unique.RemoveDebuffsAction".equals(name)) {
                if(readObjectField(action,"c")!=AbstractDungeon.player || !hasRelic("OrangePellets"))return null;
                kind="REMOVE_PLAYER_DEBUFFS";
            } else if("com.megacrit.cardcrawl.actions.common.DrawCardAction".equals(name)) {
                if(!Boolean.FALSE.equals(readBooleanField(action,"shuffleCheck"))
                        || !Boolean.TRUE.equals(readBooleanField(action,"clearDrawHistory"))
                        || readObjectField(action,"followUpAction")!=null) return null;
                kind="DRAW";if(amount!=null && amount>0)++draws;
            } else if("com.megacrit.cardcrawl.actions.common.GainBlockAction".equals(name)) {
                if(readObjectField(action,"target")!=AbstractDungeon.player) return null;
                kind="GAIN_BLOCK";
            } else if("com.megacrit.cardcrawl.actions.common.GainEnergyAction".equals(name)) kind="GAIN_ENERGY";
            else if("com.megacrit.cardcrawl.actions.unique.GamblingChipAction".equals(name)) kind="GAMBLE";
            else if("com.megacrit.cardcrawl.actions.common.UpgradeRandomCardAction".equals(name)) kind="UPGRADE_RANDOM";
            else if("com.megacrit.cardcrawl.actions.common.DamageAllEnemiesAction".equals(name)) {
                Object values=readObjectField(action,"damage");
                if(!(values instanceof int[]) || (readObjectField(action,"source")!=null && readObjectField(action,"source")!=AbstractDungeon.player)
                        || !Boolean.TRUE.equals(readBooleanField(action,"firstFrame"))
                        || !Boolean.FALSE.equals(readBooleanField(action,"utilizeBaseDamage"))
                        || !"THORNS".equals(String.valueOf(readObjectField(action,"damageType")))) return null;
                int[] damage=(int[])values;
                if(damage.length!=AbstractDungeon.getMonsters().monsters.size() || damage.length==0) return null;
                amount=damage[0];for(int value:damage) if(value!=amount) return null;
                kind="DAMAGE_ALL";
            } else if("com.megacrit.cardcrawl.actions.common.DamageRandomEnemyAction".equals(name)) {
                Object info=readObjectField(action,"info");
                if(info==null || !"THORNS".equals(String.valueOf(readObjectField(info,"type")))) return null;
                Object owner=readObjectField(info,"owner");
                if(owner!=null && owner!=AbstractDungeon.player) return null;
                amount=readIntField(info,"output");
                if(amount==null || !amount.equals(readIntField(info,"base"))) return null;
                kind="DAMAGE_RANDOM";
            } else if("com.megacrit.cardcrawl.actions.common.MakeTempCardInDrawPileAction".equals(name)) {
                Object value=readObjectField(action,"cardToMake");
                if(!hasRelic("Mark of Pain") || !(value instanceof AbstractCard)
                        || !value.getClass().getName().equals("com.megacrit.cardcrawl.cards.status.Wound")
                        || !Boolean.TRUE.equals(readBooleanField(action,"randomSpot"))
                        || !Boolean.FALSE.equals(readBooleanField(action,"toBottom")))return null;
                AbstractCard card=(AbstractCard)value;
                if(card.upgraded || card.timesUpgraded!=0 || card.misc!=0 || card.cost!=-2
                        || card.costForTurn!=-2 || card.freeToPlayOnce || card.retain) return null;
                kind="SHUFFLE_WOUNDS";
            } else if("com.megacrit.cardcrawl.actions.common.ApplyPowerAction".equals(name)) {
                Object value=readObjectField(action,"powerToApply");
                if(!(value instanceof AbstractPower)) return null;
                AbstractPower applied=(AbstractPower)value;
                if(readObjectField(action,"target") instanceof AbstractMonster) {
                    int next=allEnemyPowerBatch(manager.actions,actionIndex,applied.ID,applied.amount);
                    if(next<0)return null;
                    String item=publicPendingActionJson("DEBUFF_ALL_ENEMY",applied.amount,applied.ID);
                    if(out.length()>1)out.append(',');out.append(item);actionIndex=next-1;continue;
                }
                if(readObjectField(action,"target")!=AbstractDungeon.player)return null;
                if(applied.owner!=AbstractDungeon.player || amount==null || amount!=applied.amount
                        || !java.util.Arrays.asList("StrengthPower","DexterityPower","ArtifactPower","BufferPower","PlatedArmorPower",
                            "ThornsPower","VigorPower","IntangiblePlayerPower","LoseStrengthPower","WeakPower","PenNibPower")
                            .contains(applied.getClass().getSimpleName())
                        || !applied.getClass().getName().equals("com.megacrit.cardcrawl.powers."+applied.getClass().getSimpleName())) return null;
                if("Pen Nib".equals(applied.ID) && !hasRelic("Pen Nib"))return null;
                if("Weakened".equals(applied.ID) && !Boolean.FALSE.equals(readBooleanField(applied,"justApplied")))return null;
                power=applied.ID;kind=applied.type==AbstractPower.PowerType.DEBUFF?"DEBUFF_PLAYER":"BUFF_PLAYER";
            }
            Object source=readObjectField(action,"source");
            if(source!=null && source!=AbstractDungeon.player) return null;
            String item=publicPendingActionJson(kind,amount,power);
            if(item==null)return null;
            if(out.length()>1)out.append(',');out.append(item);
        }
        if((opening && (draws==0 || enables!=1)) || (sourceTask!=null && cleanups!=1))return null;
        return out.append(']').toString();
    }

    private static String handMultiContinuation(String task) {
        String publicTail=publicPendingActionsJson(false);
        if(publicTail!=null) return publicTail.equals("[]") ? "none" : "public_actions";
        com.megacrit.cardcrawl.actions.GameActionManager actions = AbstractDungeon.actionManager;
        if (actions == null || !playerSelectionTurn(actions.turnHasEnded, AbstractDungeon.player.endTurnQueued, AbstractDungeon.player.isEndingTurn)
                || !actions.preTurnActions.isEmpty() || !actions.monsterQueue.isEmpty()) return null;
        int cleanups = 0;
        for (Object pending : actions.actions) {
            String name = pending.getClass().getName();
            if ("com.megacrit.cardcrawl.actions.utility.WaitAction".equals(name)
                    || "com.megacrit.cardcrawl.actions.common.EnableEndTurnButtonAction".equals(name)
                    || "com.megacrit.cardcrawl.actions.common.RelicAboveCreatureAction".equals(name)) continue;
            if (!"EXHAUST_MANY".equals(task) || ++cleanups != 1
                    || !"com.megacrit.cardcrawl.actions.utility.UseCardAction".equals(name)) return null;
            Object target = readObjectField(pending,"targetCard");
            if (!(target instanceof AbstractCard) || target != trackedLastCardQueueItem.physicalCard
                    || !"Purity".equals(((AbstractCard)target).cardID)
                    || !Boolean.FALSE.equals(readBooleanField(pending,"returnToHand"))
                    || !Boolean.FALSE.equals(readBooleanField(pending,"reboundCard"))
                    || !Boolean.valueOf(trackedLastCardQueueItem.exhaustOnUse).equals(readBooleanField(pending,"exhaustCard"))) return null;
        }
        if (cleanups == 0) return AbstractDungeon.player.limbo.isEmpty() && actions.cardQueue.isEmpty() ? "none" : null;
        return "purity_card";
    }

    private static String stasisJson() {
        StringBuilder out = new StringBuilder("[");
        boolean first = true;
        if (AbstractDungeon.getMonsters() != null) {
            for (AbstractMonster monster : AbstractDungeon.getMonsters().monsters) {
                if (monster == null) continue;
                for (AbstractPower power : monster.powers) {
                    if (!"Stasis".equals(power.ID)) continue;
                    Object card = readObjectField(power, "card");
                    Integer physical=emittedMonsterSlots(liveEncounter).get(monster);
                    Integer slot = "BronzeOrb".equals(monster.id) && physical!=null && (physical==0 || physical==2)?physical/2:null;
                    if (!(card instanceof AbstractCard) || slot == null || slot < 0 || slot > 1)
                        return null;
                    if (!first) out.append(',');
                    first = false;
                    String serialized = cardJson((AbstractCard) card);
                    out.append(serialized, 0, serialized.length() - 1)
                            .append(",\"slot\":").append(slot).append('}');
                }
            }
        }
        return out.append(']').toString();
    }

    static String cardRewardSelectionJson(String actionClass, Integer copies, Boolean skippable,
                                          String continuation, List<String> cards, boolean plainCards) {
        String reason = "";
        boolean codex = "com.megacrit.cardcrawl.actions.unique.CodexAction".equals(actionClass);
        if (codex && (!"codex_end_turn".equals(continuation) || !Boolean.TRUE.equals(skippable)))
            reason = "silver_card_reward_end_turn_continuation";
        else if (!codex && !"com.megacrit.cardcrawl.actions.unique.DiscoveryAction".equals(actionClass)
                && !"com.megacrit.cardcrawl.actions.utility.ChooseOneColorless".equals(actionClass))
            reason = "silver_card_reward_unknown_action";
        else if (skippable == null)
            reason = "silver_card_reward_skip_unobserved";
        else if (!codex && (copies == null || copies < 1 || copies > 2))
            reason = "silver_card_reward_copy_count";
        else if (!codex && !"none".equals(continuation) && !"discovery_card".equals(continuation) && !"source_card_actions".equals(continuation)
                && !(("toolbox_draw".equals(continuation) || "toolbox_actions".equals(continuation))
                    && "com.megacrit.cardcrawl.actions.utility.ChooseOneColorless".equals(actionClass)))
            reason = "silver_card_reward_pending_actions";
        else if (!plainCards || cards == null || cards.size() != 3
                || new java.util.HashSet<String>(cards).size() != 3 || cards.contains(null)
                || cards.contains(""))
            reason = "silver_card_reward_option_state";
        if (!reason.isEmpty())
            return "{\"task\":\"\",\"origin\":\"CARD_REWARD\",\"unsupportedReason\":\"" + reason + "\"}";
        boolean toolbox = "com.megacrit.cardcrawl.actions.utility.ChooseOneColorless".equals(actionClass);
        if (toolbox && (copies != 1 || skippable))
            return "{\"task\":\"\",\"unsupportedReason\":\"silver_card_reward_option_state\"}";
        StringBuilder out = new StringBuilder("{\"task\":\"" + (codex ? "CODEX" : "DISCOVERY") + "\",\"origin\":\"CARD_REWARD\","
                + "\"canPickZero\":" + skippable + ",\"canPickAnyNumber\":false,\"pickCount\":1,"
                + "\"setCostToZero\":" + (!toolbox && !codex) + ",\"selectedBits\":0,\"data0\":");
        out.append(codex ? 0 : copies).append(",\"continuation\":\"").append(continuation).append("\",\"cards\":[");
        for (int i = 0; i < cards.size(); ++i) {
            if (i != 0) out.append(',');
            out.append('"').append(escapeJson(cards.get(i))).append('"');
        }
        return out.append("]}").toString();
    }

    private static String cardRewardContinuation() {
        com.megacrit.cardcrawl.actions.GameActionManager actions = AbstractDungeon.actionManager;
        if (actions == null || !playerSelectionTurn(actions.turnHasEnded, AbstractDungeon.player.endTurnQueued, AbstractDungeon.player.isEndingTurn)
                || !actions.preTurnActions.isEmpty() || !actions.cardQueue.isEmpty()
                || !actions.monsterQueue.isEmpty()) return "unsupported";
        if (actions.actions.isEmpty() && AbstractDungeon.player.limbo.isEmpty()) return "none";
        // The existing native interrupted-card replay can restore this sole
        // remainder. Other card/action queues need a separate continuation
        // contract and must not be discarded when a popup is imported.
        if (actions.actions.size() != 1 || !trackedLastCardQueueItem.present) return "unsupported";
        Object pending = actions.actions.get(0);
        if (!"com.megacrit.cardcrawl.actions.utility.UseCardAction".equals(pending.getClass().getName()))
            return "unsupported";
        Object target = readObjectField(pending, "targetCard");
        if (!(target instanceof AbstractCard)) return "unsupported";
        AbstractCard card = (AbstractCard) target;
        if (!"Discovery".equals(card.cardID) || trackedLastCardQueueItem.physicalCard != card
                || AbstractDungeon.player.hand.group.contains(card)
                || AbstractDungeon.player.drawPile.group.contains(card)
                || AbstractDungeon.player.discardPile.group.contains(card)
                || AbstractDungeon.player.exhaustPile.group.contains(card)
                || AbstractDungeon.player.limbo.size() > 1
                || (AbstractDungeon.player.limbo.size() == 1 && AbstractDungeon.player.limbo.group.get(0) != card)
                || !Boolean.FALSE.equals(readBooleanField(pending, "returnToHand"))
                || !Boolean.FALSE.equals(readBooleanField(pending, "reboundCard"))
                || !Boolean.valueOf(trackedLastCardQueueItem.exhaustOnUse).equals(readBooleanField(pending, "exhaustCard"))
                || trackedLastCardQueueItem.purgeOnUse || trackedLastCardQueueItem.autoplay) return "unsupported";
        return "discovery_card";
    }

    static int toolboxDrawAfter(List<String> classes, Integer amount, boolean ordinaryDraw) {
        return classes != null && classes.equals(java.util.Arrays.asList(
                "com.megacrit.cardcrawl.actions.common.DrawCardAction",
                "com.megacrit.cardcrawl.actions.common.EnableEndTurnButtonAction"))
                && ordinaryDraw && amount != null && amount >= 1 && amount <= 10 ? amount : -1;
    }

    static List<Integer> toolboxDrawsAfter(List<String> classes, List<Integer> amounts, boolean ordinaryDraws) {
        if (classes == null || amounts == null || !ordinaryDraws || classes.size() > 128) return null;
        List<Integer> result = new ArrayList<>();
        int enables = 0;
        for (String name : classes) {
            if ("com.megacrit.cardcrawl.actions.common.DrawCardAction".equals(name)) {
                if (result.size() >= amounts.size()) return null;
                Integer amount = amounts.get(result.size());
                if (amount == null || amount < 1 || amount > 10) return null;
                result.add(amount);
            } else if ("com.megacrit.cardcrawl.actions.common.EnableEndTurnButtonAction".equals(name)) ++enables;
            else if (!"com.megacrit.cardcrawl.actions.common.RelicAboveCreatureAction".equals(name)) return null;
        }
        return enables == 1 && !result.isEmpty() && result.size() == amounts.size() ? result : null;
    }
    private static List<Integer> toolboxDrawsAfter() {
        com.megacrit.cardcrawl.actions.GameActionManager actions = AbstractDungeon.actionManager;
        if (actions == null || !playerSelectionTurn(actions.turnHasEnded, AbstractDungeon.player.endTurnQueued, AbstractDungeon.player.isEndingTurn)
                || !actions.preTurnActions.isEmpty() || !actions.cardQueue.isEmpty()
                || !actions.monsterQueue.isEmpty() || !AbstractDungeon.player.limbo.isEmpty()) return null;
        List<String> classes = new ArrayList<>(); List<Integer> amounts = new ArrayList<>();
        boolean ordinary = true;
        for (Object action : actions.actions) {
            String name = action.getClass().getName(); classes.add(name);
            if ("com.megacrit.cardcrawl.actions.common.DrawCardAction".equals(name)) {
                amounts.add(readIntField(action, "amount"));
                ordinary &= Boolean.FALSE.equals(readBooleanField(action, "shuffleCheck"))
                        && Boolean.TRUE.equals(readBooleanField(action, "clearDrawHistory"))
                        && readObjectField(action, "followUpAction") == null;
            }
        }
        return toolboxDrawsAfter(classes, amounts, ordinary);
    }

    static boolean codexEndTurnContinuation(List<String> classes, boolean endTurnQueued,
                                            boolean queuesEmpty, boolean noOrbs) {
        return endTurnQueued && queuesEmpty && noOrbs && classes != null && classes.equals(java.util.Arrays.asList(
                "com.megacrit.cardcrawl.actions.defect.TriggerEndOfTurnOrbsAction"));
    }

    private static boolean stoneCalendarDamage(Object action) {
        Object values = readObjectField(action, "damage");
        if (!hasRelic("StoneCalendar") || !(values instanceof int[])
                || readObjectField(action, "source") != null
                || !Boolean.TRUE.equals(readBooleanField(action, "firstFrame"))
                || !Boolean.FALSE.equals(readBooleanField(action, "utilizeBaseDamage"))
                || !"THORNS".equals(String.valueOf(readObjectField(action, "damageType")))) return false;
        int[] damage = (int[]) values;
        if (damage.length != AbstractDungeon.getMonsters().monsters.size()) return false;
        for (int amount : damage) if (amount != 52) return false;
        return true;
    }

    private static boolean codexEndTurnContinuation() {
        com.megacrit.cardcrawl.actions.GameActionManager actions = AbstractDungeon.actionManager;
        if (actions == null) return false;
        List<String> classes = new ArrayList<>();
        boolean damageSeen = false, blockSeen = false;
        for (Object action : actions.actions) {
            String name = action.getClass().getName();
            if ("com.megacrit.cardcrawl.actions.common.DamageAllEnemiesAction".equals(name)) {
                if (damageSeen || blockSeen || !classes.isEmpty() || !stoneCalendarDamage(action)) return false;
                damageSeen = true;
            } else if ("com.megacrit.cardcrawl.actions.common.GainBlockAction".equals(name)) {
                blockSeen = true;
                Integer amount = readIntField(action, "amount");
                if (readObjectField(action, "target") != AbstractDungeon.player
                        || (readObjectField(action, "source") != null && readObjectField(action, "source") != AbstractDungeon.player)
                        || amount == null || amount < 0 || amount > 999 || !classes.isEmpty()) return false;
            } else if (!"com.megacrit.cardcrawl.actions.common.RelicAboveCreatureAction".equals(name)) classes.add(name);
        }
        return actions.actions.size() <= 128 && hasRelic("Nilry's Codex") && codexEndTurnContinuation(classes,
                AbstractDungeon.player.endTurnQueued && !AbstractDungeon.player.isEndingTurn,
                !actions.turnHasEnded && actions.preTurnActions.isEmpty()
                    && pendingCardQueue(new IdentityHashMap<AbstractMonster,Integer>(),true).error==null
                    && actions.monsterQueue.isEmpty() && AbstractDungeon.player.limbo.isEmpty(),
                AbstractDungeon.player.maxOrbs == 0 && AbstractDungeon.player.orbs.isEmpty());
    }

    private static String combatCardRewardJson() {
        com.megacrit.cardcrawl.screens.CardRewardScreen screen = AbstractDungeon.cardRewardScreen;
        Object action = AbstractDungeon.actionManager == null ? null : AbstractDungeon.actionManager.currentAction;
        List<String> ids = new ArrayList<>();
        boolean plain = screen != null && screen.rewardGroup != null
                && screen.discoveryCard == null && !hasRelic("PrismaticShard")
                && !AbstractDungeon.player.hasPower("MasterRealityPower");
        if (screen != null && screen.rewardGroup != null) for (AbstractCard card : screen.rewardGroup) {
            if (card == null) { plain = false; continue; }
            ids.add(card.cardID);
            plain &= !card.upgraded && card.timesUpgraded == 0 && card.misc == 0
                    && card.costForTurn == card.cost && !card.freeToPlayOnce && !card.retain;
        }
        Boolean skippable = readBooleanField(screen, "skippable");
        if (Boolean.TRUE.equals(skippable)) {
            try {
                if (!Boolean.TRUE.equals(Class.forName("mcpthespire.ChoiceScreenUtils")
                        .getMethod("isCancelButtonAvailable").invoke(null))) skippable = null;
            } catch (ReflectiveOperationException | LinkageError error) { skippable = null; }
        }
        String actionClass = action == null ? "" : action.getClass().getName();
        String continuation = cardRewardContinuation();
        if("com.megacrit.cardcrawl.actions.unique.DiscoveryAction".equals(actionClass)
                && trackedLastCardQueueItem.physicalCard!=null && hasPendingUseCard()
                && sourceSelectionOwner("DISCOVERY",trackedLastCardQueueItem.physicalCard.getClass().getName())) {
            continuation=publicPendingActionsJson(false,"DISCOVERY")!=null?"source_card_actions":"unsupported";
        }
        List<Integer> drawsAfter = null;
        List<Integer> blocksAfter = new ArrayList<>();
        int damageAllBeforeBlocks = 0;
        if ("com.megacrit.cardcrawl.actions.unique.CodexAction".equals(actionClass) && codexEndTurnContinuation()) {
            continuation = "codex_end_turn";
            for (Object pending : AbstractDungeon.actionManager.actions) {
                if ("com.megacrit.cardcrawl.actions.common.GainBlockAction".equals(pending.getClass().getName()))
                    blocksAfter.add(readIntField(pending, "amount"));
                else if ("com.megacrit.cardcrawl.actions.common.DamageAllEnemiesAction".equals(pending.getClass().getName()))
                    damageAllBeforeBlocks = 52;
            }
        }
        if ("com.megacrit.cardcrawl.actions.utility.ChooseOneColorless".equals(actionClass)
                && "unsupported".equals(continuation)) {
            drawsAfter = toolboxDrawsAfter();
            if (drawsAfter != null) continuation = "toolbox_draw";
            else if(publicPendingActionsJson(true)!=null) continuation="toolbox_actions";
        }
        String selection = cardRewardSelectionJson(actionClass, readIntField(action, "amount"),
                skippable, continuation, ids, plain);
        if (drawsAfter != null && "toolbox_draw".equals(continuation))
            selection = selection.substring(0, selection.length() - 1) + ",\"drawsAfter\":" + drawsAfter + "}";
        if (!blocksAfter.isEmpty() && "codex_end_turn".equals(continuation))
            selection = selection.substring(0, selection.length() - 1) + ",\"blocksAfter\":" + blocksAfter + "}";
        if (damageAllBeforeBlocks > 0 && "codex_end_turn".equals(continuation))
            selection = selection.substring(0, selection.length() - 1) + ",\"damageAllBeforeBlocks\":" + damageAllBeforeBlocks + "}";
        return selection;
    }

    private static String cardSelectionJson() {
        if (AbstractDungeon.screen == AbstractDungeon.CurrentScreen.CARD_REWARD
                && AbstractDungeon.cardRewardScreen != null) return combatCardRewardJson();
        if (AbstractDungeon.screen == AbstractDungeon.CurrentScreen.GRID
                && AbstractDungeon.gridSelectScreen != null) {
            com.megacrit.cardcrawl.screens.select.GridCardSelectScreen screen =
                    AbstractDungeon.gridSelectScreen;
            Integer amount = readIntField(screen, "numCards", "cardSelectAmount");
            String task = currentActionSelectionTask(false, screen.anyNumber, amount == null ? -1 : amount);
            if (task != null) return liveSingleSelectionJson(task, false, false, screen.anyNumber,
                    amount == null ? -1 : amount, screen.selectedCards.size());
            if (task == null) {
                task = selectionTask(readStringField(screen, "tipMsg", "lastTip"), screen.anyNumber);
                if (task.isEmpty() && screen.forUpgrade) task = "ARMAMENTS";
            }
            return selectionJson(task, false, screen.anyNumber, amount == null ? 1 : amount,
                    screen.targetGroup == null ? null : screen.targetGroup.group);
        }
        if (AbstractDungeon.screen == AbstractDungeon.CurrentScreen.HAND_SELECT
                && AbstractDungeon.handCardSelectScreen != null) {
            com.megacrit.cardcrawl.screens.select.HandCardSelectScreen screen =
                    AbstractDungeon.handCardSelectScreen;
            Boolean anyNumber = readBooleanField(screen, "anyNumber");
            boolean canPickAnyNumber = anyNumber != null ? anyNumber : screen.upTo;
            // Action ownership distinguishes redraw from ordinary discard.
            String task = currentActionSelectionTask(true, canPickAnyNumber, screen.numCardsToSelect);
            if (task != null) return liveSingleSelectionJson(task, true, screen.canPickZero,
                    canPickAnyNumber, screen.numCardsToSelect, screen.selectedCards.size());
            if (task == null) task = handSelectionTask(screen.selectionReason, canPickAnyNumber,
                    screen.canPickZero, screen.numCardsToSelect);
            return selectionJson(task, screen.canPickZero, canPickAnyNumber, screen.numCardsToSelect,
                    AbstractDungeon.player.hand.group);
        }
        return null;
    }

    static boolean orphanedHandSelection(boolean playerDecision, boolean retrieved, int selectedCount) {
        return playerDecision && !retrieved && selectedCount > 0;
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
        String encounter = liveEncounter.isEmpty()
                ? INSTANCE.encounterName(AbstractDungeon.getCurrRoom()) : liveEncounter;
        IdentityHashMap<AbstractMonster, Integer> emittedSlots = emittedMonsterSlots(encounter);
        int declaredMonsterCount = RunicDomeCapture.declaredCapacity();
        int monstersAlive = 0;
        for (Map.Entry<AbstractMonster, Integer> entry : emittedSlots.entrySet()) {
            AbstractMonster monster = entry.getKey();
            int slot = entry.getValue() == null ? -1 : entry.getValue();
            if (slot < 0) continue;
            declaredMonsterCount = Math.max(declaredMonsterCount, slot + 1);
            if (monster.currentHealth > 0 && !monster.isDeadOrEscaped()) ++monstersAlive;
        }
        // The native Automaton layout reserves both orb positions before the
        // Java BronzeOrb objects are spawned: orb 0, Automaton 1, orb 2.
        if ("AUTOMATON".equals(encounter)) declaredMonsterCount = Math.max(3, declaredMonsterCount);
        Integer targetedSlot = trackedLastTargetedMonster == null
                ? null : emittedSlots.get(trackedLastTargetedMonster);
        int lastTargetedMonster = targetedSlot == null || targetedSlot < 0 ? 1 : targetedSlot;
        for (AbstractPower power : AbstractDungeon.player.powers)
            if ("Vulnerable".equals(power.ID)) trackedPlayerVulnerableSeen = true;
        StringBuilder out = new StringBuilder("{");
        // A timed-out selection owner can disappear while its selected cards
        // remain outside every pile. Do not search this apparently stable but
        // incomplete root (or later reinterpret those cards as new copies).
        if (AbstractDungeon.handCardSelectScreen != null
                && orphanedHandSelection(isPlayerDecisionPoint(),
                    AbstractDungeon.handCardSelectScreen.wereCardsRetrieved,
                    AbstractDungeon.handCardSelectScreen.selectedCards.size()))
            out.append("\"orphanedHandSelection\":true,");
        if(RunicDomeCapture.bindingFailure()!=null)out.append("\"occupantBindingError\":\"").append(escapeJson(RunicDomeCapture.bindingFailure())).append("\",");
        out.append("\"turn\":");
        out.append(com.megacrit.cardcrawl.actions.GameActionManager.turn)
                .append(",\"energy\":")
                .append(EnergyPanel.totalCount)
                // energyMaster includes base/relic energy. Berserk remains a
                // separate power and is folded into native turn energy there.
                .append(",\"energyPerTurn\":").append(AbstractDungeon.player.energy.energyMaster)
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
            if(projectedZeroCopyPower(power,selection))continue;
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
            // Vanilla IntangiblePlayerPower always expires at end of round
            // and has no justApplied field; native uses a false expiry bit.
            if ("IntangiblePlayer".equals(powerId)) justApplied = false;
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
            } else if ("DevaForm".equals(power.ID) || "Deva Form".equals(power.ID) || "DevaFormPower".equals(power.ID)) {
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
                .append(hasRunicDome() ? ",\"runicDomeKnowledge\":" + RunicDomeCapture.snapshot() : "")
                .append(",\"frozenEye\":").append(hasRelic("Frozen Eye"))
                // At this stable player boundary vanilla has completed all
                // monster-turn bookkeeping. Make the known zero explicit so
                // the native importer does not silently invent it.
                .append(",\"extraRollMoveOnTurn\":0")
                .append(",\"skipMonsterTurnBits\":0")
                .append(",\"monsterCount\":").append(declaredMonsterCount)
                .append(",\"monstersAlive\":").append(monstersAlive)
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
        if (!hasRelic("Frozen Eye")) {
            Collections.sort(draw, Comparator.comparing((AbstractCard card) -> card.cardID)
                    .thenComparing(card -> String.valueOf(card.uuid))
                    .thenComparingInt(card -> card.misc));
        }
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
            // Queued purge copies are represented by pendingCardQueue. Their
            // shared UUID is not another permanent physical pile occurrence.
            if(selection!=null && selection.contains("\"continuation\":\"source_card_actions\"")
                    && (sourceCopyInPendingQueue(card) || (card==trackedLastCardQueueItem.physicalCard
                        && trackedLastCardQueueItem.purgeOnUse && trackedLastCardQueueItem.autoplay)))continue;
            if (!first) out.append(',');
            first = false;
            out.append(cardJson(card, "LIMBO"));
        }
        out.append("],\"stasis\":").append(stasis == null ? "null" : stasis)
                .append(",\"monsters\":[");
        first = true;
        boolean runicDome = hasRunicDome();
        if (AbstractDungeon.getMonsters() != null) {
            List<AbstractMonster> monsters = AbstractDungeon.getMonsters().monsters;
            for (AbstractMonster monster : monsters) {
                if (monster == null) continue;
                if (replacedLargeSlimeParent(encounter, monster, monsters)) continue;
                if (replacedSlimeBossParent(encounter, monster, monsters)) continue;
                // SpawnMonsterAction adds the new object without removing the
                // old corpse. Its native slot now belongs to the verified new
                // occupant; never serialize the retired corpse at slot -1.
                if (RunicDomeCapture.retiredDeadOccupant(monster)) continue;
                if (!first) out.append(',');
                first = false;
                int slot = emittedSlots.containsKey(monster) ? emittedSlots.get(monster) : -1;
                out.append("{\"id\":\"").append(escapeJson(monster.id))
                        .append("\",\"slot\":").append(slot)
                        .append(",\"idx\":").append(slot)
                        .append(",\"occupantGeneration\":").append(RunicDomeCapture.occupantGeneration(monster))
                        .append(",\"hp\":").append(monster.currentHealth)
                        .append(",\"maxHp\":").append(monster.maxHealth)
                        .append(",\"block\":").append(monster.currentBlock)
                        .append(",\"dead\":").append(monster.isDeadOrEscaped())
                        .append(",\"escaping\":").append(monster.escaped)
                        .append(",\"halfDead\":").append(monster.halfDead)
                        .append(",\"escapeNext\":").append(monster.escapeNext);
                if (!runicDome) {
                    out.append(",\"nextMove\":").append(monster.nextMove)
                            .append(",\"moveHistory\":[");
                    int historyStart = Math.max(0, monster.moveHistory.size() - 2);
                    for (int historyIndex = historyStart; historyIndex < monster.moveHistory.size(); ++historyIndex) {
                        if (historyIndex > historyStart) out.append(',');
                        out.append(monster.moveHistory.get(historyIndex));
                    }
                    out.append(']');
                }
                out.append(",\"powers\":[");
                boolean firstMonsterPower = true;
                for (AbstractPower power : monster.powers) {
                    // SplitPower is vanilla's UI marker for the large-slime
                    // split intent (amount is -1). Native Silver represents
                    // this through the translated nextMove, not a status bit.
                    if ("Split".equals(power.ID)) continue;
                    if (!firstMonsterPower) out.append(',');
                    firstMonsterPower = false;
                    out.append("{\"id\":\"").append(escapeJson(power.ID))
                            .append("\",\"amount\":").append(power.amount);
                    Boolean justApplied = monsterPowerJustApplied(power);
                    if (justApplied != null) out.append(",\"justApplied\":").append(justApplied);
                    out.append('}');
                }
                out.append(']');
                // A post-roll private counter can disclose a hidden intent.
                // Dome counters are reconstructed from the separately captured
                // public history; never export the live post-roll counter.
                Integer miscInfo = publicMonsterMiscInfo(runicDome, () -> monsterMiscInfo(monster));
                if (miscInfo != null) out.append(",\"miscInfo\":").append(miscInfo);
                Integer uniquePower0 = runicDome ? null : monsterUniquePower0(monster);
                if (uniquePower0 != null) out.append(",\"uniquePower0\":").append(uniquePower0);
                if (!runicDome) {
                    out.append(",\"intent\":\"")
                            .append(escapeJson(monster.intent == null ? "UNKNOWN" : monster.intent.name()))
                            .append("\",\"intentDamage\":").append(monster.getIntentDmg());
                }
                out.append('}');
            }
        }
        out.append(']');
        if (selection != null) {
            PendingCardQueueCapture.Result pending = pendingCardQueue(emittedSlots,
                    selection.contains("\"continuation\":\"codex_end_turn\""));
            if (pending.error != null) out.append(",\"pendingCardQueueError\":\"")
                    .append(escapeJson(pending.error)).append('"');
            else out.append(",\"pendingCardQueue\":").append(pending.json);
        }
        if(selection!=null && (selection.contains("\"continuation\":\"public_actions\"")
                || selection.contains("\"continuation\":\"toolbox_actions\"")
                || selection.contains("\"continuation\":\"source_card_actions\""))) {
            String sourceTask=null;
            if(selection.contains("source_card_actions")) {
                sourceTask=new com.google.gson.JsonParser().parse(selection).getAsJsonObject().get("task").getAsString();
            }
            String pending=publicPendingActionsJson(selection.contains("toolbox_actions"),sourceTask);
            if(pending==null) out.append(",\"pendingActionQueueError\":\"silver_selection_pending_actions\"");
            else out.append(",\"pendingActionQueue\":").append(pending);
        }
        out.append(",\"curCardQueueItem\":").append(cardQueueItemJson(selection!=null && selection.contains("\"continuation\":\"source_card_actions\"")))
                .append(",\"lastCard\":");
        AbstractCard lastCard = AbstractDungeon.actionManager.lastCard;
        if (decisionOrdinal > 0 && trackedLastCardQueueItem.present
                && trackedLastCardQueueItem.cardJson != null
                && !"null".equals(trackedLastCardQueueItem.cardJson)) {
            String serialized = trackedLastCardQueueItem.cardJson;
            out.append(serialized, 0, serialized.length() - 1)
                    .append(",\"target\":").append(trackedLastCardQueueItem.target)
                    .append(",\"energyOnUse\":")
                    .append(trackedLastCardQueueItem.energyOnUse).append('}');
        } else if (decisionOrdinal > 0 && lastCard != null) {
            String serialized = cardJson(lastCard);
            out.append(serialized, 0, serialized.length() - 1)
                    .append(",\"target\":").append(targetedSlot == null ? 0 : targetedSlot)
                    .append(",\"energyOnUse\":")
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

    static String ctmPrimaryModel(Properties properties, String environmentValue) {
        // Presence is intentional even for an empty/whitespace override: let
        // the native loader report the invalid artifact instead of substituting.
        if (environmentValue != null) return environmentValue;
        String value = properties.getProperty("ctmModel");
        return value == null || value.trim().isEmpty() ? null : value.trim();
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

        private String environmentFirst(Properties properties, String environmentName, String propertyName) {
            String value = System.getenv(environmentName);
            if (value != null && !value.trim().isEmpty()) return value.trim();
            value = properties.getProperty(propertyName);
            return value == null || value.trim().isEmpty() ? null : value.trim();
        }

        synchronized void start() {
            try {
                Properties p = new Properties();
                String configOverride = System.getenv("STS_MODEL_INSPECTOR_CONFIG");
                Path config = configOverride == null || configOverride.trim().isEmpty()
                        ? Paths.get(System.getProperty("user.home"), ".sts-model-inspector.properties")
                        : Paths.get(configOverride.trim());
                if (Files.isRegularFile(config)) try (BufferedReader r = Files.newBufferedReader(config)) { p.load(r); }
                showAdvisorPanel = Boolean.parseBoolean(
                        p.getProperty("showAdvisorPanel", "true").trim());
                showActionRecommendations = Boolean.parseBoolean(
                        p.getProperty("showActionRecommendations", "true").trim());
                showSelectedActionSummary = Boolean.parseBoolean(
                        p.getProperty("showSelectedActionSummary", "true").trim());
                String executable = environmentFirst(p, "STS_MODEL_INSPECTOR_ADVISOR", "advisor");
                if (executable == null) {
                    advisorStatus = "disconnected";
                    advisorReason = "set STS_MODEL_INSPECTOR_ADVISOR or advisor in the inspector config";
                    return;
                }
                ProcessBuilder builder = new ProcessBuilder(executable);
                String ctmModel = ctmPrimaryModel(p, System.getenv("STS_CTM_MODEL"));
                if (ctmModel != null)
                    builder.environment().put("STS_CTM_MODEL", ctmModel);
                String oocModel = environmentFirst(p, "STS_LIVE_OOC_MODEL", "oocModel");
                if (oocModel != null)
                    builder.environment().put("STS_LIVE_OOC_MODEL", oocModel);
                String oocWinModel = environmentFirst(p, "STS_LIVE_OOC_WIN_MODEL", "oocWinModel");
                if (oocWinModel != null)
                    builder.environment().put("STS_LIVE_OOC_WIN_MODEL", oocWinModel);
                String oocFloorModel = environmentFirst(p, "STS_LIVE_OOC_FLOOR_MODEL", "oocFloorModel");
                if (oocFloorModel != null)
                    builder.environment().put("STS_LIVE_OOC_FLOOR_MODEL", oocFloorModel);
                if (Boolean.parseBoolean(p.getProperty("captureMctsGraphs", "false").trim())) {
                    builder.environment().put("STS_SILVER_DEBUG_TREE", "1");
                    builder.environment().put("STS_OOC_DEBUG_TREE", "1");
                }
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
                            silverTotalSimulations = 0;
                            silverRootVisits = 0;
                            current.responseLatencyMicros = Math.max(0L,
                                    (System.nanoTime() - current.capturedNanos) / 1000L);
                            responseSequence = seq;
                            responseHash = hash;
                            advisorResponseJson = line;
                            advisorStatus = status == null ? "error" : status.toLowerCase();
                            if ("ERROR".equals(status)) {
                                advisorReason = (code == null ? "UNKNOWN" : code) +
                                        (message == null || message.isEmpty() ? "" : " - " + message);
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
                                silverTotalSimulations = numberField(line, "totalSimulations");
                                silverRootVisits = numberField(line, "rootVisits");
                                if (silverRanking != null) silverRanking = silverRanking.replace("\\n", "\n");
                            }
                            if ("combat".equals(current.boundary)) {
                                try { combatHpOverlay = CombatHpOverlay.parse(line); }
                                catch (RuntimeException invalidDisplay) { combatHpOverlay = null; }
                            }
                            try { potionOverlay = PotionOverlay.parse(line); }
                            catch (RuntimeException invalidDisplay) { potionOverlay = null; }
                            if (!"combat".equals(current.boundary)) {
                                try { oocOverlay = OocOverlay.parse(line, current.observationJson); }
                                catch (RuntimeException invalidDisplay) { oocOverlay = null; }
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
                    .append(",\"latencyMicros\":").append(ready ? Long.toString(snapshot.responseLatencyMicros) : "null")
                    .append(",\"session\":\"").append(ready ? Snapshot.escape(snapshot.session) : "")
                    .append("\",\"sequence\":").append(ready ? snapshot.sequence : -1)
                    .append(",\"observationHash\":\"").append(Snapshot.escape(responseObservationHash))
                    .append("\",\"reason\":\"").append(Snapshot.escape(reason == null ? "" : reason))
                    .append("\",\"advisor\":");
            out.append(ready && !advisorResponseJson.isEmpty()
                    ? advisorResponseJson : "null").append("}");
            // Deliberately outside observation/observationHash and advisor
            // request: hidden state is debug-only and cannot affect policy.
            String debugRng = snapshot.debugRng;
            if (!debugRng.isEmpty()) out.append(",\"debugRng\":").append(debugRng);
            if (DebugRngCapture.enabled())
                out.append(",\"runtime\":").append(DebugRngCapture.runtimeJson());
            return out.append("}").toString();
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
        final String combat, ooc, debugRng;
        final String combatEntry, combatEntryHash;
        final String observationJson;
        final long sequence, capturedNanos;
        final long silverSearchBudget;
        volatile long responseLatencyMicros = -1L;
        final int ascension, act, floor, hp, maxHp, gold;

        Snapshot(String session, long sequence, String boundary, String character,
                 int ascension, int act, int floor, int hp, int maxHp, int gold,
                 String deck, String candidates, String combat, String combatEntry,
                 String combatEntryHash, String ooc, long silverSearchBudget,
                 String hash, long capturedNanos, String debugRng) {
            this.session = session; this.sequence = sequence; this.boundary = boundary;
            this.capturedNanos = capturedNanos;
            this.debugRng = debugRng;
            this.character = character; this.ascension = ascension; this.act = act;
            this.floor = floor; this.hp = hp; this.maxHp = maxHp; this.gold = gold;
            this.deck = deck; this.candidates = candidates; this.hash = hash;
            this.combat = combat; this.ooc = ooc; this.combatEntry = combatEntry;
            this.combatEntryHash = combatEntryHash;
            this.silverSearchBudget = silverSearchBudget;
            this.observationJson = buildObservationJson();
        }

        Snapshot withSequence(long emittedSequence) {
            return new Snapshot(session, emittedSequence, boundary, character, ascension, act,
                    floor, hp, maxHp, gold, deck, candidates, combat, combatEntry,
                    combatEntryHash, ooc, silverSearchBudget, hash, capturedNanos, debugRng);
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
                    (ooc.isEmpty() ? "" : ",\"ooc\":" + ooc) +
                    (combat.isEmpty() ? "" : ",\"combat\":" + combat
                        + ",\"combatEntryHash\":\"" + combatEntryHash + "\""
                        + ",\"silverSearchBudget\":" + silverSearchBudget
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
