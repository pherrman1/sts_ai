package stsmodelinspector;

import com.google.gson.JsonObject;
import com.megacrit.cardcrawl.cards.AbstractCard;
import com.megacrit.cardcrawl.core.Settings;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.helpers.Hitbox;
import com.megacrit.cardcrawl.shop.StorePotion;
import com.megacrit.cardcrawl.shop.StoreRelic;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

/** Read-only physical anchors in exactly the same order as MCP choices. */
final class InlineChoices {
    private static final String CHOICES = "mcpthespire.ChoiceScreenUtils";
    static final class Anchor {
        final JsonObject action;
        final String label;
        final float x, bottom, width;
        boolean visible = true;
        Anchor(JsonObject action, String label, float x, float bottom, float width) {
            this.action = action; this.label = label;
            this.width = width;
            this.x = Math.max(4 * Settings.scale, Math.min(Settings.WIDTH - width - 4 * Settings.scale, x));
            this.bottom = Math.max(4 * Settings.scale, Math.min(Settings.HEIGHT - 40 * Settings.scale, bottom));
        }
    }
    static JsonObject action(String kind, int index) {
        JsonObject action = new JsonObject(); action.addProperty("kind", kind);
        if (index > 0) action.addProperty("choiceIndex", index);
        return action;
    }
    static List<Anchor> capture(String screen) {
        List<Anchor> result = new ArrayList<>();
        try {
            float s = Settings.scale;
            if ("event".equals(screen) || "neow".equals(screen)) {
                List<?> buttons = choices("getActiveEventButtons");
                for (int i = 0; i < buttons.size(); ++i)
                    result.add(beside(action("choose", i + 1), "", (Hitbox) field(buttons.get(i), "hb"), 240 * s));
            } else if ("rest".equals(screen)) {
                List<?> buttons = choices("getValidRestRoomButtons");
                for (int i = 0; i < buttons.size(); ++i) {
                    Hitbox hb = (Hitbox)field(buttons.get(i), "hb");
                    result.add(new Anchor(action("choose", i + 1), "", hb.cX - 120 * s, hb.y - 42 * s, 240 * s));
                }
            } else if ("map".equals(screen) && AbstractDungeon.screen == AbstractDungeon.CurrentScreen.MAP) {
                if (Boolean.TRUE.equals(call("bossNodeAvailable"))) {
                    result.add(node(action("choose", 1), AbstractDungeon.dungeonMapScreen.map.bossHb));
                } else for (Object item : choices("getMapScreenNodeChoices")) {
                    com.megacrit.cardcrawl.map.MapRoomNode node = (com.megacrit.cardcrawl.map.MapRoomNode)item;
                    JsonObject action = action("map", 0);
                    action.addProperty("x", node.x); action.addProperty("y", node.y);
                    result.add(node(action, node.hb));
                }
            } else if ("selector".equals(screen) && AbstractDungeon.screen == AbstractDungeon.CurrentScreen.GRID) {
                if (com.megacrit.cardcrawl.ui.buttons.PeekButton.isPeeking) return result;
                if (!AbstractDungeon.gridSelectScreen.confirmScreenUp && !AbstractDungeon.gridSelectScreen.isJustForConfirming) {
                    List<?> cards = choices("getGridScreenCards");
                    for (int i = 0; i < cards.size(); ++i) {
                        AbstractCard card = (AbstractCard)cards.get(i);
                        Anchor anchor = card(action("choose", i + 1), "", card, 44);
                        float bottom = card.current_y - AbstractCard.IMG_HEIGHT * card.drawScale / 2 - 44 * s;
                        anchor.visible = bottom > 40 * s && bottom + 32 * s < Settings.HEIGHT - 90 * s;
                        result.add(anchor);
                    }
                } else {
                    Object button = AbstractDungeon.gridSelectScreen.confirmButton;
                    if (!Boolean.TRUE.equals(field(button, "isHidden")))
                        result.add(beside(action("confirm", 0), "Confirm", (Hitbox)field(button, "hb")));
                }
            } else if ("card_reward".equals(screen)
                    && AbstractDungeon.screen == AbstractDungeon.CurrentScreen.CARD_REWARD) {
                List<AbstractCard> cards = AbstractDungeon.cardRewardScreen.rewardGroup;
                for (int i = 0; i < cards.size(); ++i)
                    result.add(card(action("choose", i + 1), "", cards.get(i), 44));
                Object button = field(AbstractDungeon.cardRewardScreen, "skipButton");
                if (!Boolean.TRUE.equals(field(button, "isHidden"))
                        && !Boolean.TRUE.equals(field(button, "screenDisabled")))
                    result.add(beside(action("skip", 0), "Skip", (Hitbox) field(button, "hb")));
                Object bowl = field(AbstractDungeon.cardRewardScreen, "bowlButton");
                if (!Boolean.TRUE.equals(field(bowl, "isHidden")))
                    result.add(beside(action("choose", cards.size() + 1), "+2 HP", (Hitbox) field(bowl, "hb")));
            } else if ("shop".equals(screen)
                    && AbstractDungeon.screen == AbstractDungeon.CurrentScreen.SHOP) {
                List<?> items = choices("getAvailableShopItems");
                for (int i = 0; i < items.size(); ++i) {
                    Object item = items.get(i); JsonObject action = action("choose", i + 1);
                    if (item instanceof AbstractCard) result.add(card(action, "Buy", (AbstractCard) item, 76));
                    else if (item instanceof StoreRelic) {
                        Hitbox hb = ((StoreRelic)item).relic.hb;
                        result.add(below(action, "Buy", hb.cX, hb.y - 48 * s));
                    } else if (item instanceof StorePotion) {
                        Hitbox hb = ((StorePotion)item).potion.hb;
                        result.add(below(action, "Buy", hb.cX, hb.y - 48 * s));
                    } else if (item instanceof String) {
                        float x = ((Number)field(AbstractDungeon.shopScreen, "purgeCardX")).floatValue();
                        float y = ((Number)field(AbstractDungeon.shopScreen, "purgeCardY")).floatValue();
                        float cardScale = ((Number)field(AbstractDungeon.shopScreen, "purgeCardScale")).floatValue();
                        float priceTop = y - 180 * s - (cardScale / s - .75f) * 200 * s;
                        result.add(new Anchor(action, "Remove", x - 100 * s, priceTop - 62 * s, 200 * s));
                    }
                }
                Object button = AbstractDungeon.overlayMenu.cancelButton;
                if (!Boolean.TRUE.equals(field(button, "isHidden")))
                    result.add(below(action("cancel", 0), "Leave", ((Hitbox)field(button, "hb")).cX,
                            ((Hitbox)field(button, "hb")).y - 40 * s));
            }
        } catch (ReflectiveOperationException | RuntimeException unavailable) {
            // Never guess a choice binding after a mod/API changes. The caller
            // retains unmatched recommendations in its fallback panel.
        }
        return result;
    }
    private static Anchor card(JsonObject action, String label, AbstractCard card, int gap) {
        return below(action, label, card.current_x,
                card.current_y - AbstractCard.IMG_HEIGHT * card.drawScale / 2 - gap * Settings.scale);
    }
    private static Anchor node(JsonObject action, Hitbox hb) {
        float s = Settings.scale;
        Anchor anchor = new Anchor(action, "", hb.cX - 60 * s, hb.y - 34 * s, 120 * s);
        anchor.visible = hb.cY > 80 * s && hb.cY < Settings.HEIGHT - 110 * s;
        return anchor;
    }
    private static Anchor below(JsonObject action, String label, float center, float bottom) {
        float width = 158 * Settings.scale;
        return new Anchor(action, label, center - width / 2, bottom, width);
    }
    static Anchor beside(JsonObject action, String label, Hitbox hb) {
        return beside(action, label, hb, 168 * Settings.scale);
    }
    private static Anchor beside(JsonObject action, String label, Hitbox hb, float width) {
        float gap = 10 * Settings.scale;
        float x = hb.x + hb.width + gap;
        if (x + width > Settings.WIDTH - gap) x = hb.x - width - gap;
        return new Anchor(action, label, x, hb.cY - 16 * Settings.scale, width);
    }
    static Object field(Object object, String name) throws ReflectiveOperationException {
        for (Class<?> type = object.getClass(); type != null; type = type.getSuperclass()) {
            try { Field f = type.getDeclaredField(name); f.setAccessible(true); return f.get(object); }
            catch (NoSuchFieldException absent) { /* Continue through inherited UI fields. */ }
        }
        throw new NoSuchFieldException(name);
    }
    private static List<?> choices(String name) throws ReflectiveOperationException {
        return (List<?>)call(name);
    }
    private static Object call(String name) throws ReflectiveOperationException {
        Method method = Class.forName(CHOICES).getDeclaredMethod(name); method.setAccessible(true);
        return method.invoke(null);
    }
}
