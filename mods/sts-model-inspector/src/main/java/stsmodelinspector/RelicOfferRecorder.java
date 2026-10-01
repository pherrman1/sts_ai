package stsmodelinspector;

import basemod.BaseMod;
import basemod.abstracts.CustomSavable;
import basemod.interfaces.PostUpdateSubscriber;
import basemod.interfaces.PreStartGameSubscriber;
import com.evacipated.cardcrawl.modthespire.lib.SpireInitializer;
import com.evacipated.cardcrawl.modthespire.lib.SpirePatch;
import com.evacipated.cardcrawl.modthespire.lib.SpirePrefixPatch;
import com.google.gson.Gson;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.megacrit.cardcrawl.core.CardCrawlGame;
import com.megacrit.cardcrawl.core.Settings;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.relics.AbstractRelic;
import com.megacrit.cardcrawl.rewards.RewardItem;
import com.megacrit.cardcrawl.rooms.AbstractRoom;
import com.megacrit.cardcrawl.rooms.ShopRoom;
import com.megacrit.cardcrawl.screens.CombatRewardScreen;
import com.megacrit.cardcrawl.screens.select.BossRelicSelectScreen;
import com.megacrit.cardcrawl.shop.ShopScreen;
import com.megacrit.cardcrawl.shop.StoreRelic;
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.Map;
import java.util.Collections;
import java.util.List;

/** Public offers only; the checkpoint travels with the game's own save. */
@SpireInitializer
public final class RelicOfferRecorder implements CustomSavable<RelicOfferRecorder.SaveData>,
        PreStartGameSubscriber, PostUpdateSubscriber {
    private static final RelicOfferRecorder INSTANCE = new RelicOfferRecorder();
    private static SaveData pending;
    private static boolean loading;
    private static Object observedRoom;
    private static int observedFloor = -1;
    private static int revealedShopFloor = -1;
    private static boolean unseenShop;
    // Only an absent/older combat field may be migrated from metrics. A
    // malformed or explicitly incomplete checkpoint is never silently healed.
    private static boolean legacyCombatRecoveryAllowed = true;

    public static final class SaveData {
        Integer version;
        Long seed;
        Integer floor, ascension;
        String character;
        Boolean complete, currentShopRevealed;
        List<String> offers;
        Integer combatAct;
        Boolean combatComplete;
        List<Map<String,Object>> combatEntries;
        Integer questionVersion;
        List<Map<String,Object>> questionEntries;
    }

    public static void initialize() {
        BaseMod.subscribe(INSTANCE);
        BaseMod.addSaveField("stsmodelinspector:relicOffersV1", INSTANCE);
    }

    @Override public void receivePreStartGame() {
        LiveOocCapture.seenRelicOffers.clear();
        LiveOocCapture.combatClassHistory.clear();
        QuestionRoomObserver.clear();
        pending = null; loading = false;
        observedRoom = null; observedFloor = -1; unseenShop = false;
        revealedShopFloor = -1;
        legacyCombatRecoveryAllowed = true;
    }

    @Override public void onLoad(SaveData data) {
        receivePreStartGame();
        pending = data;
        loading = true;
    }

    @Override public void onLoadRaw(JsonElement raw) {
        // BaseMod's default Gson adapter coerces strings/fractions into some
        // primitive fields. Reject malformed checkpoints before that adapter.
        SaveData decoded = decodeCheckpoint(raw);
        onLoad(decoded);
        legacyCombatRecoveryAllowed = raw == null || raw.isJsonNull()
                || (decoded != null && decoded.combatAct == null
                    && decoded.combatComplete == null && decoded.combatEntries == null);
    }

    static SaveData decodeCheckpoint(JsonElement raw) {
        try {
            if (raw == null || !raw.isJsonObject()) return null;
            JsonObject value = raw.getAsJsonObject();
            for (String field : new String[]{"version", "seed", "floor", "ascension"}) {
                JsonElement n = value.get(field);
                if (n == null || !n.isJsonPrimitive() || !n.getAsJsonPrimitive().isNumber()) return null;
                long integer = n.getAsBigDecimal().toBigIntegerExact().longValueExact();
                if (!"seed".equals(field) && (integer < 0 || integer > Integer.MAX_VALUE)) return null;
            }
            if (value.get("version").getAsInt() != 1) return null;
            JsonElement character = value.get("character");
            if (character == null || !character.isJsonPrimitive()
                    || !character.getAsJsonPrimitive().isString() || character.getAsString().isEmpty()) return null;
            for (String field : new String[]{"complete", "currentShopRevealed"}) {
                JsonElement flag = value.get(field);
                if (flag == null || !flag.isJsonPrimitive() || !flag.getAsJsonPrimitive().isBoolean()) return null;
            }
            JsonElement offers = value.get("offers");
            if (offers == null || !offers.isJsonArray() || offers.getAsJsonArray().size() > 181) return null;
            for (JsonElement offer : offers.getAsJsonArray())
                if (!offer.isJsonPrimitive() || !offer.getAsJsonPrimitive().isString()
                        || offer.getAsString().isEmpty()) return null;
            if (value.has("combatAct") || value.has("combatComplete") || value.has("combatEntries")) {
                JsonElement act = value.get("combatAct"), complete = value.get("combatComplete"), entries = value.get("combatEntries");
                if (act == null || !act.isJsonPrimitive() || !act.getAsJsonPrimitive().isNumber()
                        || complete == null || !complete.isJsonPrimitive() || !complete.getAsJsonPrimitive().isBoolean()
                        || entries == null || !entries.isJsonArray() || entries.getAsJsonArray().size() > 20) return null;
                int actValue = act.getAsBigDecimal().toBigIntegerExact().intValueExact();
                // -1 is an explicitly unobserved ledger, never a qualified act.
                if (actValue < -1 || actValue > 4 || (complete.getAsBoolean() && actValue < 1)) return null;
            }
            if(value.has("questionVersion") || value.has("questionEntries")) {
                JsonElement version=value.get("questionVersion"), entries=value.get("questionEntries");
                if(version==null || !version.isJsonPrimitive() || !version.getAsJsonPrimitive().isNumber()
                        || version.getAsBigDecimal().toBigIntegerExact().intValueExact()!=1
                        || entries==null || !entries.isJsonArray() || entries.getAsJsonArray().size()>51)return null;
            }
            SaveData decoded=new Gson().fromJson(value, SaveData.class);
            if(decoded.questionVersion!=null && !new QuestionRoomObserver.Ledger().restore(
                    new Object(),0,decoded.floor,decoded.questionEntries))return null;
            return decoded;
        } catch (RuntimeException invalid) { return null; }
    }

    @Override public SaveData onSave() {
        bind();
        observe();
        if (AbstractDungeon.player == null || Settings.seed == null) return null;
        // A shop can consume its pool before the player opens the merchant.
        // Leaving it unseen cannot qualify a complete public offer history.
        if (unseenShop && AbstractDungeon.floorNum != observedFloor)
            LiveOocCapture.seenRelicOffers.invalidate();
        SaveData data = new SaveData();
        data.version = 1; data.seed = Settings.seed; data.floor = AbstractDungeon.floorNum;
        data.character = AbstractDungeon.player.chosenClass.name();
        data.ascension = AbstractDungeon.ascensionLevel;
        data.complete = LiveOocCapture.seenRelicOffers.complete();
        data.currentShopRevealed = revealedShopFloor == data.floor;
        data.offers = LiveOocCapture.seenRelicOffers.snapshot();
        data.combatAct = LiveOocCapture.combatClassHistory.act();
        data.combatComplete = LiveOocCapture.combatClassHistory.complete();
        data.combatEntries = LiveOocCapture.combatClassHistory.snapshot();
        data.questionVersion=1;
        data.questionEntries=QuestionRoomObserver.ledger.snapshot();
        return data;
    }

    static boolean matches(SaveData data, long seed, int floor, String character, int ascension) {
        return data != null && Integer.valueOf(1).equals(data.version)
                && Long.valueOf(seed).equals(data.seed) && Integer.valueOf(floor).equals(data.floor)
                && floor >= 0 && character != null && character.equals(data.character)
                && Integer.valueOf(ascension).equals(data.ascension)
                && data.complete != null && data.currentShopRevealed != null;
    }

    static List<Integer> completedCombatFloors(int act, int floor) {
        List<Integer> result = new ArrayList<>();
        if (CardCrawlGame.metricData == null || CardCrawlGame.metricData.damage_taken == null) return null;
        int start = act <= 1 ? 0 : act == 2 ? 17 : act == 3 ? 34 : 51;
        for (Object raw : CardCrawlGame.metricData.damage_taken) {
            if (!(raw instanceof Map) || !(((Map<?,?>)raw).get("floor") instanceof Number)) return null;
            Number number = (Number)((Map<?,?>)raw).get("floor");
            int f = number.intValue();
            if (number.doubleValue() != f || f > floor) return null;
            if (f > start) result.add(f);
        }
        return result;
    }

    static void bind() {
        if (AbstractDungeon.player == null || Settings.seed == null) return;
        if (loading) {
            restorePending(AbstractDungeon.player, Settings.seed, AbstractDungeon.floorNum,
                    AbstractDungeon.player.chosenClass.name(), AbstractDungeon.ascensionLevel,
                    AbstractDungeon.actNum, completedCombatFloors(AbstractDungeon.actNum, AbstractDungeon.floorNum));
        }
        boolean fresh = AbstractDungeon.floorNum == 0 && CardCrawlGame.metricData != null
                && CardCrawlGame.metricData.path_taken != null
                && CardCrawlGame.metricData.path_taken.isEmpty();
        LiveOocCapture.seenRelicOffers.observe(AbstractDungeon.player, Settings.seed,
                AbstractDungeon.floorNum, fresh, "", Collections.emptyMap());
    }

    static void restorePending(Object player, long seed, int floor, String character,
            int ascension, int act, List<Integer> completed) {
        if (!loading) return;
        if (pending != null && !matches(pending, seed, floor, character, ascension))
            legacyCombatRecoveryAllowed = false;
        boolean restored = LiveOocCapture.seenRelicOffers.restore(player, seed,
                floor, pending, character, ascension);
        if (restored && pending.currentShopRevealed) revealedShopFloor = floor;
        if (matches(pending, seed, floor, character, ascension) && completed != null)
            LiveOocCapture.combatClassHistory.restoreCheckpoint(player, seed, act, floor, pending, completed);
        if(matches(pending,seed,floor,character,ascension) && Integer.valueOf(1).equals(pending.questionVersion))
            QuestionRoomObserver.ledger.restore(player,seed,floor,pending.questionEntries);
        pending = null; loading = false;
    }

    static boolean canRecoverLegacyCombat() { return legacyCombatRecoveryAllowed; }
    static void finishLegacyCombatRecovery() { legacyCombatRecoveryAllowed = false; }

    @Override public void receivePostUpdate() { observe(); }

    static boolean projectionComplete() {
        // Merchant construction consumes the pool before the player opens
        // the shop. This temporary gap may be repaired by viewing it, but it
        // must already block a map decision made from inside the same room.
        return LiveOocCapture.seenRelicOffers.complete() && !unseenShop;
    }

    static void observeRoom(Object room, int floor, boolean shop) {
        if (room != observedRoom || floor != observedFloor) {
            if (unseenShop) LiveOocCapture.seenRelicOffers.invalidate();
            observedRoom = room; observedFloor = floor;
            unseenShop = shop && revealedShopFloor != floor;
        }
    }

    static void shopRevealed(int floor) {
        unseenShop = false;
        revealedShopFloor = floor;
    }

    static void observe() {
        if (AbstractDungeon.player == null || AbstractDungeon.currMapNode == null
                || Settings.seed == null || AbstractDungeon.isFadingIn || AbstractDungeon.isFadingOut)
            return;
        bind();
        AbstractRoom room = AbstractDungeon.getCurrRoom();
        observeRoom(room, AbstractDungeon.floorNum, room instanceof ShopRoom);
        try {
            switch (AbstractDungeon.screen) {
                case SHOP:
                    // This field is read only while the shop is publicly open.
                    Field field = ShopScreen.class.getDeclaredField("relics");
                    field.setAccessible(true);
                    for (Object raw : (List<?>)field.get(AbstractDungeon.shopScreen)) {
                        StoreRelic relic = (StoreRelic)raw;
                        if (!relic.isPurchased) LiveOocCapture.seenRelicOffers.add(relic.relic.relicId);
                    }
                    shopRevealed(AbstractDungeon.floorNum);
                    break;
                case COMBAT_REWARD:
                    for (RewardItem reward : AbstractDungeon.combatRewardScreen.rewards)
                        if (reward.relic != null) LiveOocCapture.seenRelicOffers.add(reward.relic.relicId);
                    break;
                case BOSS_REWARD:
                    for (AbstractRelic relic : AbstractDungeon.bossRelicScreen.relics)
                        LiveOocCapture.seenRelicOffers.add(relic.relicId);
                    break;
                default: break;
            }
        } catch (ReflectiveOperationException | RuntimeException failure) {
            LiveOocCapture.seenRelicOffers.invalidate();
        }
    }

    // Record before the screen processes a click, independently of MCP command
    // readiness, optional capture support, and the advisor's search latency.
    @SpirePatch(clz = ShopScreen.class, method = "update")
    public static class ShopOffers {
        @SpirePrefixPatch public static void beforeUpdate() { observe(); }
    }
    @SpirePatch(clz = CombatRewardScreen.class, method = "update")
    public static class RewardOffers {
        @SpirePrefixPatch public static void beforeUpdate() { observe(); }
    }
    @SpirePatch(clz = BossRelicSelectScreen.class, method = "update")
    public static class BossOffers {
        @SpirePrefixPatch public static void beforeUpdate() { observe(); }
    }
}
