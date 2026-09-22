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
import com.megacrit.cardcrawl.characters.AbstractPlayer;
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
    private static final String TOGGLE = "stsmodelinspector.toggle";
    private static final Color PANEL_BACKGROUND = new Color(0.015f, 0.075f, 0.115f, 0.96f);
    private static final Color PANEL_INNER = new Color(0.02f, 0.12f, 0.18f, 0.94f);
    private static final Color CARD_BACKGROUND = new Color(0.015f, 0.10f, 0.16f, 0.92f);
    private static final Color CARD_BORDER = new Color(0.10f, 0.48f, 0.66f, 0.85f);
    private static final Color CYAN = new Color(0.0f, 0.92f, 0.88f, 1.0f);
    private static final Color CYAN_DIM = new Color(0.0f, 0.62f, 0.68f, 1.0f);
    private static final Color MUTED = new Color(0.60f, 0.76f, 0.82f, 1.0f);
    private static final Color WARNING = new Color(1.0f, 0.67f, 0.20f, 1.0f);
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
    private static final IdentityHashMap<AbstractMonster, Integer> guardianPublicThreshold =
            new IdentityHashMap<>();
    private static final IdentityHashMap<AbstractMonster, HiddenIntentSnapshot> hiddenIntentSnapshots =
            new IdentityHashMap<>();
    // Candidate bits come only from publicly observed player damage. A zero
    // mask means that the public observation could not be represented safely.
    private static final IdentityHashMap<AbstractMonster, Integer> hiddenMiscMasks =
            new IdentityHashMap<>();
    private static final Set<AbstractMonster> hiddenDirectTurnMarkers =
            Collections.newSetFromMap(new IdentityHashMap<AbstractMonster, Boolean>());

    static final class HiddenIntentSnapshot {
        final int[] publicMoveHistory = new int[]{0, 0};
        int publicMoveHistoryCount;
        int publicMiscInfo;
        int pendingMoveRolls;
        int pendingDirectMoveChoice;
        int generation;
        int curHp, maxHp, knightCurHp, knightMaxHp, monsterTurnNumber, aliveCount, monstersAlive;
        int miscInfo;
        boolean knightAlive, playerConstricted, asleep, halfDead;
    }

    /**
     * Vanilla removes a CardQueueItem before the stable player boundary is
     * published.  Retain the item while it is public so v4 can describe the
     * exact item that was processed, including the resolved target object.
     */
    private static final class TrackedCardQueueItem {
        boolean present;
        String cardJson;
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
    private volatile long silverTotalSimulations;
    private volatile long silverRootVisits;
    private long silverSearchBudget = DEFAULT_SILVER_SEARCH_BUDGET;
    private String silverBudgetStateFingerprint = "";
    private volatile double ctmDeath = 0.0;
    static final class HistogramSnapshot {
        final int min;
        final double[] values;

        HistogramSnapshot(int min, double[] values) {
            this.min = min;
            this.values = values.clone();
        }
    }
    static int[] histogramNonzeroRange(HistogramSnapshot snapshot) {
        int first = -1;
        int last = -1;
        final double[] values = snapshot.values;
        for (int i = 0; i < values.length; ++i) {
            if (values[i] > 0.000001) {
                if (first < 0) first = i;
                last = i;
            }
        }
        return new int[]{first, last};
    }
    private volatile HistogramSnapshot ctmHistogram = new HistogramSnapshot(1, new double[0]);
    private volatile OocOverlay oocOverlay;
    private volatile PotionOverlay potionOverlay;
    private volatile boolean panelVisible = true;
    private volatile String combatEntry = "";
    private volatile String combatEntryHash = "";
    private final LatestPublisher latestPublisher = new LatestPublisher();
    private String lastRoomClass = "";
    private String lastNodeRoomClass = "";
    private int lastNodeX = -1, lastNodeY = -1;
    private static String liveEncounter = "";
    private boolean toggleDown;

    private void resetSilverBudget() {
        silverSearchBudget = DEFAULT_SILVER_SEARCH_BUDGET;
        silverBudgetStateFingerprint = "";
        silverTotalSimulations = 0;
        silverRootVisits = 0;
    }

    public static void initialize() {
        BaseMod.subscribe(INSTANCE);
    }

    static final class PublicDamageSnapshot {
        final int hp, block;
        final AbstractMonster owner;
        final int[] candidateOutputs;
        final boolean publicAmountQualified;
        PublicDamageSnapshot(int hp, int block, AbstractMonster owner, int[] candidateOutputs,
                             boolean publicAmountQualified) {
            this.hp = hp;
            this.block = block;
            this.owner = owner;
            this.candidateOutputs = candidateOutputs;
            this.publicAmountQualified = publicAmountQualified;
        }
    }

    static int hiddenMiscMinimum(String monsterId, int ascension) {
        if ("FuzzyLouseNormal".equals(monsterId) || "FuzzyLouseDefensive".equals(monsterId))
            return ascension >= 2 ? 6 : 5;
        if ("Darkling".equals(monsterId)) return ascension >= 2 ? 11 : 7;
        return -1;
    }

    static int hiddenMiscCount(String monsterId) {
        return "Darkling".equals(monsterId) ? 5 : runicPrivateMiscInfo(monsterId) ? 3 : 0;
    }

    static int compatiblePrivateMiscMask(int prior, int[] outputs, int publicDamage) {
        int compatible = 0;
        for (int i = 0; i < outputs.length; ++i)
            if (outputs[i] == publicDamage) compatible |= 1 << i;
        return prior & compatible;
    }

    static PublicDamageSnapshot beginPlayerDamage(DamageInfo info, AbstractPlayer player) {
        AbstractMonster owner = info != null && info.owner instanceof AbstractMonster
                ? (AbstractMonster)info.owner : null;
        int[] predicted = null;
        if (owner != null && hasRunicDome() && runicPrivateMiscInfo(owner.id)) {
            int minimum = hiddenMiscMinimum(owner.id, AbstractDungeon.ascensionLevel);
            int count = hiddenMiscCount(owner.id);
            predicted = new int[count];
            for (int i = 0; i < count; ++i) {
                DamageInfo candidate = new DamageInfo(owner, minimum + i, info.type);
                candidate.applyPowers(owner, player);
                predicted[i] = candidate.output;
            }
        }
        // Buffer, Torii and Tungsten Rod can change the visible HP/block delta
        // after DamageInfo's power calculation. Do not condition on those hits.
        boolean qualified = !player.hasPower("Buffer") && !player.hasRelic("Torii")
                && !player.hasRelic("TungstenRod");
        return new PublicDamageSnapshot(player.currentHealth, player.currentBlock,
                owner, predicted, qualified);
    }

    /** Called by the post-AbstractPlayer.damage ModTheSpire patch. */
    static void recordPlayerDamage(DamageInfo info, int finalDamage, PublicDamageSnapshot before) {
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
        if (before != null && before.candidateOutputs != null && before.owner != null) {
            int all = (1 << before.candidateOutputs.length) - 1;
            int prior = hiddenMiscMasks.containsKey(before.owner)
                    ? hiddenMiscMasks.get(before.owner) : all;
            int publicDamage = before.block - AbstractDungeon.player.currentBlock + finalDamage;
            if (!before.publicAmountQualified || before.hp <= finalDamage
                    || publicDamage < 0 || AbstractDungeon.player.currentBlock > before.block) {
                hiddenMiscMasks.put(before.owner, 0);
                return;
            }
            hiddenMiscMasks.put(before.owner, compatiblePrivateMiscMask(
                    prior, before.candidateOutputs, publicDamage));
        }
    }

    static void recordHiddenIntentRoll(AbstractMonster monster) {
        // This hook can run before relic initialization publishes Runic Dome.
        // Capture the pre-roll boundary regardless; serialization decides
        // whether the snapshot is relevant to the current combat.
        if (monster == null || AbstractDungeon.getMonsters() == null) return;
        HiddenIntentSnapshot previous = hiddenIntentSnapshots.get(monster);
        if (previous != null && previous.pendingMoveRolls > 0) {
            recordHiddenMoveHistory(previous, monster.moveHistory);
            return;
        }
        HiddenIntentSnapshot snapshot = new HiddenIntentSnapshot();
        recordHiddenMoveHistory(snapshot, monster.moveHistory);
        Integer publicMisc = runicPrivateMiscInfo(monster.id)
                ? null : monsterMiscInfo(monster);
        snapshot.publicMiscInfo = publicMisc == null ? 0 : publicMisc;
        snapshot.curHp = monster.currentHealth;
        snapshot.maxHp = monster.maxHealth;
        snapshot.miscInfo = snapshot.publicMiscInfo;
        snapshot.monsterTurnNumber = Math.max(1,
                AbstractDungeon.actionManager == null ? 1 : AbstractDungeon.actionManager.turn);
        snapshot.playerConstricted = AbstractDungeon.player != null
                && AbstractDungeon.player.hasPower("Constricted");
        snapshot.asleep = monster.hasPower("Sleep");
        snapshot.halfDead = monster.halfDead;
        int alive = 0;
        for (AbstractMonster candidate : AbstractDungeon.getMonsters().monsters)
            if (candidate != null && !candidate.isDeadOrEscaped()) ++alive;
        snapshot.aliveCount = alive;
        snapshot.monstersAlive = alive;
        if (!AbstractDungeon.getMonsters().monsters.isEmpty()) {
            AbstractMonster knight = AbstractDungeon.getMonsters().monsters.get(0);
            snapshot.knightCurHp = knight.currentHealth;
            snapshot.knightMaxHp = knight.maxHealth;
            snapshot.knightAlive = !knight.isDeadOrEscaped();
        }
        snapshot.generation = previous == null ? 1 : previous.generation + 1;
        hiddenIntentSnapshots.put(monster, snapshot);
    }

    static void recordHiddenMoveHistory(HiddenIntentSnapshot snapshot,
                                        List<Byte> moveHistory) {
        if (snapshot.pendingMoveRolls > 0) {
            // Preserve the first public pre-roll snapshot. An intermediate
            // move and its history are hidden until the chained reroll resolves.
            snapshot.pendingMoveRolls = snapshot.pendingMoveRolls + 1;
            return;
        }
        capturePublicMoveHistory(snapshot, moveHistory);
        snapshot.pendingMoveRolls = 1;
    }

    private static void capturePublicMoveHistory(HiddenIntentSnapshot snapshot,
                                                   List<Byte> moveHistory) {
        int historySize = moveHistory == null ? 0 : moveHistory.size();
        snapshot.publicMoveHistoryCount = Math.min(2, historySize);
        if (historySize > 0) snapshot.publicMoveHistory[0] = moveHistory.get(historySize - 1);
        if (historySize > 1) snapshot.publicMoveHistory[1] = moveHistory.get(historySize - 2);
    }

    static boolean runicPrivateMiscInfo(String monsterId) {
        // These randomized damage parameters normally become public through
        // visible intent damage. Runic Dome hides that damage, so the private
        // Java fields cannot be copied into Silver's root.
        return "FuzzyLouseNormal".equals(monsterId)
                || "FuzzyLouseDefensive".equals(monsterId)
                || "Darkling".equals(monsterId);
    }

    static void recordKnownIntent(AbstractMonster monster) {
        if (monster == null || !hasRunicDome()) return;
        HiddenIntentSnapshot snapshot = hiddenIntentSnapshots.get(monster);
        if (snapshot == null) {
            snapshot = new HiddenIntentSnapshot();
            hiddenIntentSnapshots.put(monster, snapshot);
        }
        snapshot.pendingMoveRolls = 0;
        capturePublicMoveHistory(snapshot, monster.moveHistory);
        snapshot.publicMiscInfo = monsterMiscInfo(monster) == null ? 0 : monsterMiscInfo(monster);
        snapshot.miscInfo = snapshot.publicMiscInfo;
        snapshot.pendingMoveRolls = 0;
        snapshot.pendingDirectMoveChoice = 0;
    }

    static void beginHiddenDirectTurn(AbstractMonster monster, int choice) {
        if (monster == null || !hasRunicDome()) return;
        HiddenIntentSnapshot snapshot = hiddenIntentSnapshots.get(monster);
        if (snapshot == null) {
            snapshot = new HiddenIntentSnapshot();
            hiddenIntentSnapshots.put(monster, snapshot);
        }
        capturePublicMoveHistory(snapshot, monster.moveHistory);
        snapshot.publicMiscInfo = monsterMiscInfo(monster) == null ? 0 : monsterMiscInfo(monster);
        snapshot.miscInfo = snapshot.publicMiscInfo;
        snapshot.pendingMoveRolls = 0;
        snapshot.pendingDirectMoveChoice = choice;
        hiddenDirectTurnMarkers.add(monster);
    }

    static void finishHiddenDirectTurn(AbstractMonster monster) {
        if (monster == null || !hasRunicDome()) return;
        if (!hiddenDirectTurnMarkers.remove(monster)) recordKnownIntent(monster);
    }

    static void finishHiddenIntentRoll(AbstractMonster monster) {
        if (monster == null || !hasRunicDome()) return;
        HiddenIntentSnapshot snapshot = hiddenIntentSnapshots.get(monster);
        if (snapshot != null) snapshot.pendingDirectMoveChoice = 0;
    }

    @Override
    public void receiveOnBattleStart(AbstractRoom room) {
        resetSilverBudget();
        hiddenMiscMasks.clear();
        monsterSlots.clear();
        replacedMonsterParents.clear();
        hexaghostDividerDamage.clear();
        guardianPublicThreshold.clear();
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
        resetSilverBudget();
        monsterSlots.clear();
        replacedMonsterParents.clear();
        hexaghostDividerDamage.clear();
        guardianPublicThreshold.clear();
        hiddenIntentSnapshots.clear();
        hiddenMiscMasks.clear();
        hiddenDirectTurnMarkers.clear();
        liveEncounter = "";
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
        trackedLastTargetedMonster = null;
        trackedLastCardQueueItem.clear();
        silverRerootExact = false;
        silverEquivalentCopyReroot = false;
        silverRerootFallback = false;
        silverFallbackReason = "";
        silverInheritedVisits = 0;
        silverTotalSimulations = 0;
        silverRootVisits = 0;
        ctmDeath = 0.0;
        ctmHistogram = new HistogramSnapshot(1, new double[0]);
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
        if (!"combat".equals(snapshot.boundary)
                || !snapshot.combatEntryHash.equals(combatEntryHash)) {
            ctmStatus = "";
            ctmReason = "";
            ctmDeath = 0.0;
            ctmHistogram = new HistogramSnapshot(1, new double[0]);
        }
        advisorStatus = "waiting";
        advisorReason = "";
        advisor.send(emitted);
        latestPublisher.publishObservation(emitted);
    }

    @Override
    public void receiveRender(SpriteBatch sb) {
        if (!panelVisible || newest == null) return;
        renderAdvisorPanel(sb);
        renderPotionBadges(sb, Settings.scale);
        sb.setColor(Color.WHITE);
    }

    private void renderAdvisorPanel(SpriteBatch sb) {
        float scale = Settings.scale;
        float x = 24.0f * scale;
        float top = Settings.HEIGHT - 170.0f * scale;
        boolean combat = "combat".equals(newest.boundary);
        OocOverlay overlay = currentOocOverlay();
        if (!combat && renderInlineChoices(sb, overlay, scale)) {
            sb.setColor(Color.WHITE);
            return;
        }
        float width = (combat ? 500.0f : 420.0f) * scale;
        int rows = overlay == null ? 0 : overlay.panelChoices().size();
        float height = (combat ? COMBAT_PANEL_HEIGHT : rows == 0 ? 220.0f : 130.0f + 44.0f * rows) * scale;
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
            renderSilverActionBadges(sb, scale);
        } else {
            renderNonCombatPanel(sb, x, top, width, bottom, scale);
        }
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

        renderSmallText(sb, "Death chance", leftX + 14.0f * scale,
                cardTop - 13.0f * scale, Color.WHITE, 0.92f);
        String death = "OK".equals(ctmStatus)
                ? String.format(Locale.ROOT, "%.1f%%", 100.0 * ctmDeath) : "—";
        FontHelper.renderFontLeftTopAligned(sb, FontHelper.tipHeaderFont, death,
                leftX + 14.0f * scale, cardTop - 38.0f * scale,
                "OK".equals(ctmStatus) ? CYAN : WARNING);
        renderSmallText(sb, "(this combat)", leftX + 14.0f * scale,
                cardBottom + 17.0f * scale,
                "OK".equals(ctmStatus) ? MUTED : WARNING, 0.82f);

        renderSmallText(sb, "Surviving final HP", rightX + 14.0f * scale,
                cardTop - 13.0f * scale, Color.WHITE, 0.92f);
        renderHistogram(sb, rightX + 12.0f * scale, cardBottom + 14.0f * scale,
                rightWidth - 24.0f * scale, cardHeight - 38.0f * scale, scale);

        String silver = silverSummary();
        renderSmallText(sb, silverBudgetSummary(), x + 16.0f * scale, bottom + 68.0f * scale,
                CYAN_DIM, 0.70f);
        renderSmallText(sb, silver, x + 16.0f * scale, bottom + 48.0f * scale,
                "OK".equals(silverStatus) ? CYAN : WARNING, 0.78f);
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
            List<AbstractMonster> monsters = AbstractDungeon.getMonsters().monsters;
            for (int i = 0; i < monsters.size(); ++i) {
                Integer slot = monsterSlots.get(monsters.get(i));
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

    private boolean silverBoostButtonHit() {
        float scale = Settings.scale;
        float x = 24.0f * scale + SILVER_BOOST_BUTTON_X * scale;
        float panelBottom = Settings.HEIGHT - (170.0f + COMBAT_PANEL_HEIGHT) * scale;
        float bottom = panelBottom + SILVER_BOOST_BUTTON_BOTTOM * scale;
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
            renderInlineBadge(sb, anchor.x, anchor.bottom, anchor.width, label,
                    choice != null && choice.selected, choice != null, scale, detail);
        }
        String status = view == null ? "Waiting for advisor" : "OK".equals(view.status)
                ? "V4 · amber = recommended" : "UNSUPPORTED".equals(view.status)
                ? "V4 · no supported recommendation" : "Advisor unavailable";
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
                return String.format(Locale.ROOT, "Next: %s · Q %.2f", card.name, choice.followUp.get("q").getAsDouble());
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

    private void renderPotionBadges(SpriteBatch sb, float scale) {
        if (AbstractDungeon.player == null || AbstractDungeon.topPanel == null) return;
        com.megacrit.cardcrawl.ui.panels.PotionPopUp popup = AbstractDungeon.topPanel.potionUi;
        if (popup != null && popup.targetMode) return;
        PotionOverlay view = potionOverlay;
        if (view == null || !responseReady() || !view.matches(newest.session, newest.sequence, newest.hash)) view = null;
        float width = 220 * scale;
        float gap = 8 * scale;
        float groupWidth = AbstractDungeon.player.potions.size() * (width + gap) - gap;
        float firstX = AbstractDungeon.player.potions.isEmpty() ? 0 : Math.max(8 * scale,
                Math.min(Math.max(540 * scale, AbstractDungeon.player.potions.get(0).hb.cX - width / 2),
                        Settings.WIDTH - groupWidth - 8 * scale));
        for (int slot = 0; slot < AbstractDungeon.player.potions.size(); ++slot) {
            com.megacrit.cardcrawl.potions.AbstractPotion potion = AbstractDungeon.player.potions.get(slot);
            if (potion == null || "Potion Slot".equals(potion.ID)) continue;
            try {
                // Persistent columns identify the physical slot and stay readable
                // even when several potions have ranked use/discard actions.
                float x = firstX + slot * (width + gap);
                float bottom = Settings.HEIGHT - 190 * scale;
                if (popup != null && !popup.isHidden) {
                    com.megacrit.cardcrawl.helpers.Hitbox menuBottom =
                            (com.megacrit.cardcrawl.helpers.Hitbox)InlineChoices.field(popup, "hbBot");
                    bottom = Math.min(bottom, menuBottom.y - 74 * scale);
                }
                renderFittedText(sb, "P" + (slot + 1) + " · " + potion.name,
                        x + 8 * scale, bottom + 52 * scale, width - 16 * scale, MUTED, .68f);
                List<PotionOverlay.Entry> use = view == null ? Collections.emptyList() : view.forSlot(slot + 1, false);
                List<PotionOverlay.Entry> discard = view == null ? Collections.emptyList() : view.forSlot(slot + 1, true);
                if (!potion.canUse() || use.isEmpty()) {
                    renderInlineBadge(sb, x, bottom, width, "Use · " + (potion.canUse() ? "not scored" : "unavailable"),
                            false, false, scale);
                    bottom -= 36 * scale;
                } else for (PotionOverlay.Entry entry : use) {
                    renderInlineBadge(sb, x, bottom, width, entry.text(TargetLabels.name(liveMonsterNames(true), entry.target)), entry.selected, entry.q != null, scale);
                    bottom -= 36 * scale;
                }
                if (!potion.canDiscard() || discard.isEmpty())
                    renderInlineBadge(sb, x, bottom, width, "Discard · " + (potion.canDiscard() ? "not scored" : "unavailable"),
                            false, false, scale);
                else for (PotionOverlay.Entry entry : discard) {
                    renderInlineBadge(sb, x, bottom, width, entry.text(TargetLabels.name(liveMonsterNames(true), entry.target)), entry.selected, entry.q != null, scale);
                    bottom -= 36 * scale;
                }
            } catch (ReflectiveOperationException | RuntimeException unavailable) { /* Hide unbound UI. */ }
        }
    }

    private void renderNonCombatPanel(SpriteBatch sb, float x, float top, float width,
                                      float bottom, float scale) {
        OocOverlay view = currentOocOverlay();
        String subtitle = view == null ? "Waiting for current choices" :
                ("v4_q".equals(view.policy) ? "V4" : view.policy.toUpperCase(Locale.ROOT))
                + "  ·  " + capitalize(view.screen.replace('_', ' '));
        renderSmallText(sb, subtitle, x + 16 * scale, top - 69 * scale, MUTED, .82f);
        if (view != null && "OK".equals(view.status) && !view.choices.isEmpty()) {
            List<OocOverlay.Choice> panelChoices = view.panelChoices();
            for (int row = 0; row < panelChoices.size(); ++row) {
                OocOverlay.Choice choice = panelChoices.get(row);
                int rank = view.choices.indexOf(choice);
                float rowBottom = top - (122 + 44 * row) * scale;
                drawCard(sb, x + 14 * scale, rowBottom, width - 28 * scale, 38 * scale, scale);
                if (choice.selected) drawBorder(sb, x + 14 * scale, rowBottom,
                        width - 28 * scale, 38 * scale, WARNING, 2 * scale);
                renderFittedText(sb, (choice.selected ? "▶ " : "") + "#" + (rank + 1) + "  " + choice.label,
                        x + 23 * scale, rowBottom + 26 * scale, width - 150 * scale,
                        choice.selected ? CYAN : Color.WHITE, .78f);
                renderSmallText(sb, String.format(Locale.ROOT, "N %d · Q %.3f", choice.visits, choice.q),
                        x + width - 104 * scale, rowBottom + 26 * scale, MUTED, .72f);
            }
            if ("card_reward".equals(view.screen))
                renderSmallText(sb, "Scores below cards", x + 16 * scale, bottom + 22 * scale, MUTED, .72f);
            else if (view.choices.size() > 6) renderSmallText(sb, "+ " + (view.choices.size() - 6) + " more choices",
                    x + 16 * scale, bottom + 22 * scale, MUTED, .72f);
            renderOocCardBadges(sb, view, scale);
        } else {
            renderSmallText(sb, view == null ? (responseReady() ? "Advisor unavailable" : "Waiting for advisor") :
                    "UNSUPPORTED".equals(view.status) ? "No supported recommendation" : "Advisor unavailable",
                    x + 18 * scale, top - 105 * scale, WARNING, .86f);
            String reason = view == null ? "Scores appear when the current response is ready." : view.reason.replace('_', ' ');
            renderFittedText(sb, reason, x + 18 * scale, top - 138 * scale, width - 36 * scale, MUTED, .72f);
        }
        renderSmallText(sb, Keyboard.getKeyName(loadToggleKey()) + " hide",
                x + width - 78 * scale, bottom + 22 * scale, MUTED, .78f);
    }

    private void renderOocCardBadges(SpriteBatch sb, OocOverlay view, float scale) {
        if (AbstractDungeon.screen != AbstractDungeon.CurrentScreen.CARD_REWARD
                || AbstractDungeon.cardRewardScreen == null) return;
        List<AbstractCard> cards = AbstractDungeon.cardRewardScreen.rewardGroup;
        if (cards == null) return;
        for (int rank = 0; rank < view.choices.size(); ++rank) {
            OocOverlay.Choice choice = view.choices.get(rank);
            if (!"choose".equals(choice.kind) || choice.index < 1 || choice.index > cards.size()) continue;
            AbstractCard card = cards.get(choice.index - 1);
            float width = 166 * scale;
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
        for (int i = 0; i < hand.size(); ++i) {
            if (used[i]) continue;
            AbstractCard card = hand.get(i);
            if (name.equalsIgnoreCase(card.name) || name.equalsIgnoreCase(card.cardID)
                    || card.cardID.toLowerCase(Locale.ROOT).contains(name.toLowerCase(Locale.ROOT)))
                return i;
        }
        return -1;
    }

    private void renderHistogram(SpriteBatch sb, float x, float bottom, float width,
                                 float height, float scale) {
        final HistogramSnapshot snapshot = ctmHistogram;
        final double[] histogram = snapshot.values;
        if (histogram.length == 0) {
            renderFittedText(sb, ctmStatus.isEmpty() ? "Awaiting forecast" : "Forecast unavailable",
                    x, bottom + height - 12.0f * scale, width, WARNING, 0.78f);
            if (!ctmStatus.isEmpty()) renderFittedText(sb,
                    (ctmReason.isEmpty() ? ctmStatus : ctmReason).replace('_', ' '),
                    x, bottom + height - 36.0f * scale, width, MUTED, 0.65f);
            return;
        }
        int[] range = histogramNonzeroRange(snapshot);
        int first = range[0];
        int last = range[1];
        if (first < 0) return;
        final int span = last - first + 1;
        final int buckets = Math.min(14, span);
        double maximum = 0.0;
        for (int bucket = 0; bucket < buckets; ++bucket) {
            int begin = first + bucket * span / buckets;
            int end = first + (bucket + 1) * span / buckets;
            double probability = 0.0;
            for (int i = begin; i < end; ++i) probability += histogram[i];
            maximum = Math.max(maximum, probability);
        }
        if (maximum <= 0.0) return;
        float chartX = x + 8.0f * scale;
        float chartWidth = width - 58.0f * scale;
        float chartHeight = height - 5.0f * scale;
        float chartBottom = bottom + 5.0f * scale;
        float barWidth = chartWidth / buckets;
        sb.setColor(0.35f, 0.78f, 0.80f, 0.20f);
        for (int tick = 1; tick <= 3; ++tick) {
            float gridY = chartBottom + chartHeight * tick / 4.0f;
            sb.draw(ImageMaster.WHITE_SQUARE_IMG, chartX, gridY,
                    chartWidth, scale);
        }
        sb.setColor(CYAN_DIM);
        sb.draw(ImageMaster.WHITE_SQUARE_IMG, chartX, chartBottom, chartWidth, scale);
        for (int bucket = 0; bucket < buckets; ++bucket) {
            int begin = first + bucket * span / buckets;
            int end = first + (bucket + 1) * span / buckets;
            double probability = 0.0;
            for (int i = begin; i < end; ++i) probability += histogram[i];
            float barHeight = (float) (chartHeight * probability / maximum);
            sb.setColor(bucket < buckets / 2 ? CYAN_DIM : CYAN);
            sb.draw(ImageMaster.WHITE_SQUARE_IMG, chartX + bucket * barWidth,
                    chartBottom, Math.max(scale, barWidth - scale), barHeight);
        }
        int firstHp = snapshot.min + first;
        int lastHp = snapshot.min + last;
        renderSmallText(sb, Integer.toString(firstHp), chartX,
                bottom + 1.0f * scale, MUTED, 0.70f);
        renderSmallText(sb, Integer.toString(lastHp), chartX + chartWidth - 12.0f * scale,
                bottom + 1.0f * scale, MUTED, 0.70f);
        double mean = 0.0;
        double mass = 0.0;
        for (int i = first; i <= last; ++i) {
            mean += (snapshot.min + i) * histogram[i];
            mass += histogram[i];
        }
        if (mass > 0.0 && newest.maxHp > 0) {
            renderSmallText(sb, "Mean", x + width - 42.0f * scale,
                    bottom + height - 12.0f * scale, CYAN, 0.70f);
            renderSmallText(sb, String.format(Locale.ROOT, "%.0f%%",
                            100.0 * mean / mass / newest.maxHp),
                    x + width - 42.0f * scale, bottom + height - 29.0f * scale,
                    CYAN, 0.88f);
        }
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
                isPlayerDecisionPoint(), isCardSelectionBoundary())) {
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
                silverSearchBudget, sha256(raw), capturedNanos);
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

    static int gremlinReplacementSlot(Set<Integer> deadKnown, Set<Integer> livingKnown) {
        int replacement = -1;
        for (int slot = 1; slot <= 2; ++slot) {
            if (deadKnown.contains(slot) && !livingKnown.contains(slot)) {
                if (replacement >= 0) return -1;
                replacement = slot;
            }
        }
        return replacement;
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

    private static boolean replacedSlimeBossParent(String encounter,
                                                    AbstractMonster candidate,
                                                    List<AbstractMonster> monsters) {
        if (!"SLIME_BOSS".equals(encounter) || candidate == null
                || !"SlimeBoss".equals(candidate.id) || !candidate.isDeadOrEscaped()) return false;
        for (AbstractMonster monster : monsters) {
            if (monster == null || monster == candidate) continue;
            if (slimeBossDescendant(monster.id)) return true;
        }
        return false;
    }

    static boolean slimeBossDescendant(String id) {
        return "SpikeSlime_L".equals(id) || "AcidSlime_L".equals(id)
                || "SpikeSlime_M".equals(id) || "AcidSlime_M".equals(id);
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

    private static IdentityHashMap<AbstractMonster, Integer> emittedMonsterSlots(String encounter) {
        IdentityHashMap<AbstractMonster, Integer> emitted = new IdentityHashMap<>();
        if (AbstractDungeon.getMonsters() == null
                || AbstractDungeon.getMonsters().monsters == null) return emitted;
        Map<String, Integer> seenMonsterIds = new HashMap<>();
        int nonLeaderOrdinal = 0;
        Set<Integer> usedMonsterSlots = new HashSet<>();
        List<AbstractMonster> monsters = AbstractDungeon.getMonsters().monsters;
        Set<Integer> deadGremlinSlots = new HashSet<>();
        Set<Integer> livingGremlinSlots = new HashSet<>();
        if ("GREMLIN_LEADER".equals(encounter)) {
            for (AbstractMonster monster : monsters) {
                if (monster == null || "GremlinLeader".equals(monster.id)) continue;
                Integer known = monsterSlots.get(monster);
                if (known == null || known < 1 || known > 2) continue;
                if (monster.isDeadOrEscaped()) deadGremlinSlots.add(known);
                else livingGremlinSlots.add(known);
            }
        }
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
            boolean gremlinReplacement = "GREMLIN_LEADER".equals(encounter)
                    && !"GremlinLeader".equals(monster.id) && nonLeaderOrdinal >= 2
                    && !monster.isDeadOrEscaped() && !monsterSlots.containsKey(monster);
            if (gremlinReplacement)
                preferred = gremlinReplacementSlot(deadGremlinSlots, livingGremlinSlots);
            if (!"GremlinLeader".equals(monster.id)) ++nonLeaderOrdinal;
            int slot;
            if (gremlinReplacement && preferred < 0) {
                // A summoned gremlin has no unique native slot without a
                // recorded dead predecessor; fail closed instead of claiming
                // the leader's reserved slot or guessing another position.
                slot = -1;
            } else if (("SLIME_BOSS".equals(encounter) || gremlinReplacement) && preferred >= 0) {
                // Slime Boss and its large-child splits use a fixed native
                // layout (0, 1, 2). Java leaves replaced parents in its
                // monster list, so retain the native slot rather than the
                // stale Java-object assignment from before the split.
                slot = preferred;
                monsterSlots.put(monster, slot);
                usedMonsterSlots.add(slot);
                if (gremlinReplacement) livingGremlinSlots.add(slot);
            } else {
                slot = monsterSlot(monster, preferred >= 0 ? preferred : monsterIndex,
                        usedMonsterSlots);
            }
            emitted.put(monster, slot);
        }
        // Summoned gremlins reuse physical slots. Java may retain the dead
        // predecessor in its monster list; the native root has one monster
        // state per slot, with the living replacement taking precedence.
        Set<Integer> livingSlots = new HashSet<>();
        for (Map.Entry<AbstractMonster, Integer> entry : emitted.entrySet())
            if (entry.getValue() >= 0 && entry.getKey().currentHealth > 0
                    && !entry.getKey().isDeadOrEscaped()) livingSlots.add(entry.getValue());
        emitted.entrySet().removeIf(entry -> entry.getValue() >= 0
                && entry.getKey().isDeadOrEscaped() && livingSlots.contains(entry.getValue()));
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
            case "B": return "BOSS";
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

    static String ctmResponseJson(String response) {
        com.google.gson.JsonObject root = new com.google.gson.JsonParser().parse(response).getAsJsonObject();
        if (root.has("evaluators")) for (com.google.gson.JsonElement item : root.getAsJsonArray("evaluators")) {
            com.google.gson.JsonObject evaluator = item.getAsJsonObject();
            if ("ctm_combat_entry_v2".equals(evaluator.get("id").getAsString())) return evaluator.toString();
        }
        return "";
    }

    static int combatEntryRelicData(String id, int counter, boolean usedUp) {
        // Java's spent Neow's Lament uses -2; native CTM stores remaining
        // charges in [0, 3]. Keep every other value exact and fail closed.
        return "NeowsBlessing".equals(id) && usedUp && counter == -2 ? 0 : counter;
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

    private static String cardQueueItemJson() {
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
                + ",\"exhaustOnUse\":" + item.exhaustOnUse + "}";
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

    static boolean isCombatBoundary(AbstractRoom.RoomPhase phase, AbstractDungeon.CurrentScreen screen,
                                    boolean playerDecision, boolean selectionAvailable) {
        // EventRoom fights are combat too. Serializer support is a separate
        // question: an unknown selection must reach Silver as UNSUPPORTED.
        return phase == AbstractRoom.RoomPhase.COMBAT
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

    private static int bronzeAutomatonMiscInfo(AbstractMonster monster) {
        Object raw = readObjectField(monster, "moveHistory");
        if (!(raw instanceof List<?>)) return 0;
        List<?> history = (List<?>) raw;
        if (history.size() < 2) return 0;
        Object current = history.get(history.size() - 1);
        Object previous = history.get(history.size() - 2);
        if (!(current instanceof Number) || !(previous instanceof Number)) return 0;
        int currentByte = ((Number) current).intValue();
        int previousByte = ((Number) previous).intValue();
        // Native Silver's miscInfo is lastBoostWasFlail.  It is not a hidden
        // Java field, but the public move history determines it exactly at a
        // stable decision boundary: Boost->Flail and Flail->Boost are the two
        // states in which the native toggle is true.
        return (currentByte == 1 && previousByte == 5)
                || (currentByte == 5 && previousByte == 1) ? 1 : 0;
    }

    private static Integer monsterUniquePower0(AbstractMonster monster) {
        if ("Hexaghost".equals(monster.id))
            return readIntField(monster, "orbActiveCount");
        return null;
    }

    static Integer guardianThresholdFromPublicPower(Integer previous, Integer visibleAmount) {
        if (visibleAmount == null || visibleAmount <= 0) return previous;
        return previous == null ? visibleAmount : Math.max(previous, visibleAmount);
    }

    static boolean nativeMiscZeroForId(String id) {
        return ("AcidSlime_L".equals(id) || "AcidSlime_M".equals(id)
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
                || "GremlinNob".equals(id) || "GremlinWarrior".equals(id)
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
                || "Transient".equals(id));
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
            Integer threshold = guardianPublicThreshold.get(monster);
            for (AbstractPower power : monster.powers)
                if ("Mode Shift".equals(power.ID))
                    threshold = guardianThresholdFromPublicPower(threshold, power.amount);
            if (threshold != null) guardianPublicThreshold.put(monster, threshold);
            return threshold;
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
            return form1 == null ? null : (form1 ? 0 : 1);
        }
        if ("WrithingMass".equals(id)) {
            Boolean used = readBooleanField(monster, "usedMegaDebuff");
            return used == null ? null : (used ? 1 : 0);
        }
        if ("Looter".equals(id) || "Mugger".equals(id))
            return readIntField(monster, "stolenGold");
        // Explicit zero is safe only for monsters whose native move logic does
        // not consult miscInfo. Unknown/reflectively inaccessible state is
        // omitted and therefore rejected by the importer.
        if (nativeMiscZeroForId(id)) return 0;
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

    static String selectionJson(String task, boolean canPickZero, boolean anyNumber, int pickCount,
                                        List<AbstractCard> source) {
        return selectionJson(task, canPickZero, anyNumber, pickCount, 0, source);
    }

    static String selectionJson(String task, boolean canPickZero, boolean anyNumber, int pickCount,
                                        int data0, List<AbstractCard> source) {
        StringBuilder out = new StringBuilder("{\"task\":\"")
                .append(task).append("\",\"canPickZero\":").append(canPickZero)
                .append(",\"canPickAnyNumber\":")
                .append(anyNumber).append(",\"pickCount\":").append(Math.max(0, pickCount))
                .append(",\"data0\":").append(data0)
                .append(",\"setCostToZero\":true,\"selectedBits\":0,\"cards\":[");
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
        out.append("],\"liveUuids\":[");
        first = true;
        if (source != null) for (AbstractCard card : source) {
            if (!first) out.append(',');
            first = false;
            out.append('"').append(escapeJson(String.valueOf(card.uuid))).append('"');
        }
        return out.append("]}").toString();
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
                    Integer slot = "BronzeOrb".equals(monster.id)
                            ? readIntField(monster, "count") : null;
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

    private static String cardSelectionJson() {
        if (AbstractDungeon.screen == AbstractDungeon.CurrentScreen.CARD_REWARD
                && AbstractDungeon.cardRewardScreen != null) {
            com.megacrit.cardcrawl.screens.CardRewardScreen screen = AbstractDungeon.cardRewardScreen;
            Object current = AbstractDungeon.actionManager == null ? null
                    : AbstractDungeon.actionManager.currentAction;
            Boolean discovery = readBooleanField(screen, "discovery");
            Boolean skippable = readBooleanField(screen, "skippable");
            Integer copyCount = current instanceof com.megacrit.cardcrawl.actions.unique.DiscoveryAction
                    ? readIntField(current, "amount") : null;
            // DiscoveryAction holds the native copy count while its modal is open.
            // An unknown combat card reward still reaches Silver as unsupported.
            if (qualifiedDiscoverySelection(discovery, skippable, copyCount,
                    screen.rewardGroup == null ? -1 : screen.rewardGroup.size()))
                return selectionJson("DISCOVERY", skippable, false, 1, copyCount, screen.rewardGroup);
            return selectionJson("", false, false, 1, screen.rewardGroup);
        }
        if (AbstractDungeon.screen == AbstractDungeon.CurrentScreen.GRID
                && AbstractDungeon.gridSelectScreen != null) {
            com.megacrit.cardcrawl.screens.select.GridCardSelectScreen screen =
                    AbstractDungeon.gridSelectScreen;
            Integer amount = readIntField(screen, "numCards", "cardSelectAmount");
            Object current = AbstractDungeon.actionManager == null ? null
                    : AbstractDungeon.actionManager.currentAction;
            String task = liquidMemoriesSelection(current) ? "LIQUID_MEMORIES_POTION"
                    : selectionTask(readStringField(screen, "tipMsg", "lastTip"), screen.anyNumber);
            if (task.isEmpty() && screen.forUpgrade) task = "ARMAMENTS";
            return selectionJson(task, false, screen.anyNumber, amount == null ? 1 : amount,
                    screen.targetGroup == null ? null : screen.targetGroup.group);
        }
        if (AbstractDungeon.screen == AbstractDungeon.CurrentScreen.HAND_SELECT
                && AbstractDungeon.handCardSelectScreen != null) {
            com.megacrit.cardcrawl.screens.select.HandCardSelectScreen screen =
                    AbstractDungeon.handCardSelectScreen;
            Boolean anyNumber = readBooleanField(screen, "anyNumber");
            boolean canPickAnyNumber = anyNumber != null ? anyNumber : screen.upTo;
            // DiscardAction(-1), used by Gambler's Brew and Gambling Chip,
            // opens the hand selector with an empty selection reason and the
            // vanilla sentinel amount 99.  That is the native GAMBLE task,
            // not an unknown combat screen.
            String task = handSelectionTask(screen.selectionReason, canPickAnyNumber,
                    screen.canPickZero, screen.numCardsToSelect);
            return selectionJson(task, screen.canPickZero, canPickAnyNumber, screen.numCardsToSelect,
                    AbstractDungeon.player.hand.group);
        }
        return null;
    }

    static boolean qualifiedDiscoverySelection(Boolean discovery, Boolean skippable,
                                               Integer copyCount, int offerCount) {
        return Boolean.TRUE.equals(discovery) && skippable != null
                && copyCount != null && (copyCount == 1 || copyCount == 2)
                && offerCount == 3;
    }

    private static boolean liquidMemoriesSelection(Object current) {
        return zeroCostDiscardReturn(
                current instanceof com.megacrit.cardcrawl.actions.common.BetterDiscardPileToHandAction,
                readBooleanField(current, "setCost"), readIntField(current, "newCost"));
    }

    static boolean zeroCostDiscardReturn(boolean discardReturnAction, Boolean setCost, Integer newCost) {
        return discardReturnAction && Boolean.TRUE.equals(setCost) && Integer.valueOf(0).equals(newCost);
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
        int declaredMonsterCount = 0;
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
                if (!emittedSlots.containsKey(monster)) continue;
                if (replacedLargeSlimeParent(encounter, monster, monsters)) continue;
                if (replacedSlimeBossParent(encounter, monster, monsters)) continue;
                if (!first) out.append(',');
                first = false;
                int slot = emittedSlots.containsKey(monster) ? emittedSlots.get(monster) : -1;
                out.append("{\"id\":\"").append(escapeJson(monster.id))
                        .append("\",\"slot\":").append(slot)
                        .append(",\"idx\":").append(slot)
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
                HiddenIntentSnapshot hidden = runicDome ? hiddenIntentSnapshots.get(monster) : null;
                boolean hiddenPrivateMisc = runicDome && runicPrivateMiscInfo(monster.id);
                Integer miscInfo = hiddenPrivateMisc ? null : monsterMiscInfo(monster);
                if (miscInfo != null) out.append(",\"miscInfo\":").append(miscInfo);
                if (hiddenPrivateMisc) {
                    int all = (1 << hiddenMiscCount(monster.id)) - 1;
                    int mask = hiddenMiscMasks.containsKey(monster)
                            ? hiddenMiscMasks.get(monster) : all;
                    out.append(",\"privateMiscInfoUnderRunic\":true")
                            .append(",\"publicMiscCandidateMask\":").append(mask);
                }
                Integer uniquePower0 = monsterUniquePower0(monster);
                if (uniquePower0 != null) out.append(",\"uniquePower0\":").append(uniquePower0);
                if (runicDome) {
                    if (hidden != null) {
                        out.append(",\"publicMoveHistory\":[")
                                .append(hidden.publicMoveHistory[0]).append(',')
                                .append(hidden.publicMoveHistory[1]).append(']')
                                .append(",\"publicMoveHistoryCount\":")
                                .append(hidden.publicMoveHistoryCount)
                                .append(",\"pendingMoveRolls\":").append(hidden.pendingMoveRolls)
                                .append(",\"pendingDirectMoveChoice\":")
                                .append(hidden.pendingDirectMoveChoice)
                                .append(",\"pendingRollInputs\":{")
                                .append("\"curHp\":").append(hidden.curHp)
                                .append(",\"maxHp\":").append(hidden.maxHp)
                                .append(",\"knightCurHp\":").append(hidden.knightCurHp)
                                .append(",\"knightMaxHp\":").append(hidden.knightMaxHp)
                                .append(",\"monsterTurnNumber\":").append(hidden.monsterTurnNumber);
                        if (!hiddenPrivateMisc)
                            out.append(",\"miscInfo\":").append(hidden.miscInfo);
                        out.append(",\"aliveCount\":").append(hidden.aliveCount)
                                .append(",\"monstersAlive\":").append(hidden.monstersAlive)
                                .append(",\"knightAlive\":").append(hidden.knightAlive)
                                .append(",\"playerConstricted\":").append(hidden.playerConstricted)
                                .append(",\"asleep\":").append(hidden.asleep)
                                .append(",\"halfDead\":").append(hidden.halfDead)
                                .append('}');
                    }
                }
                if (!runicDome) {
                    out.append(",\"intent\":\"")
                            .append(escapeJson(monster.intent == null ? "UNKNOWN" : monster.intent.name()))
                            .append("\",\"intentDamage\":").append(monster.getIntentDmg());
                }
                out.append('}');
            }
        }
        out.append("],\"curCardQueueItem\":").append(cardQueueItemJson())
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
                String executable = environmentFirst(p, "STS_MODEL_INSPECTOR_ADVISOR", "advisor");
                if (executable == null) {
                    advisorStatus = "disconnected";
                    advisorReason = "set STS_MODEL_INSPECTOR_ADVISOR or advisor in the inspector config";
                    return;
                }
                ProcessBuilder builder = new ProcessBuilder(executable);
                String ctmModel = environmentFirst(p, "STS_CTM_MODEL", "ctmModel");
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
                            ctmHistogram = new HistogramSnapshot(1, new double[0]);
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
                                silverTotalSimulations = numberField(line, "totalSimulations");
                                silverRootVisits = numberField(line, "rootVisits");
                                if (silverRanking != null) silverRanking = silverRanking.replace("\\n", "\n");
                            }
                            String ctm = ctmResponseJson(line);
                            if (!ctm.isEmpty()) {
                                String forecastStatus = field(ctm, "status");
                                ctmStatus = "OK".equals(forecastStatus) ? "OK" :
                                        forecastStatus == null ? "error" : forecastStatus.toLowerCase(Locale.ROOT);
                                String forecastReason = field(ctm, "reason");
                                ctmReason = forecastReason == null ? ctmStatus : forecastReason;
                                if ("OK".equals(ctmStatus)) {
                                    ctmDeath = doubleField(ctm, "deathProbability");
                                    ctmHistogram = new HistogramSnapshot(
                                            (int) numberField(ctm, "winningHpHistogramMin"),
                                            numberArrayField(ctm, "winningHpHistogram"));
                                }
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
                String line;
                while ((line = r.readLine()) != null)
                    System.err.println("sts-model-inspector advisor stderr: " + line);
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
                    .append(",\"latencyMicros\":").append(ready ? Long.toString(snapshot.responseLatencyMicros) : "null")
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
        final String combat, ooc;
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
                 String hash, long capturedNanos) {
            this.session = session; this.sequence = sequence; this.boundary = boundary;
            this.capturedNanos = capturedNanos;
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
                    combatEntryHash, ooc, silverSearchBudget, hash, capturedNanos);
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
