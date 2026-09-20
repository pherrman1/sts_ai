package stsmodelinspector;

import com.evacipated.cardcrawl.modthespire.lib.SpirePatch;
import com.evacipated.cardcrawl.modthespire.lib.SpirePrefixPatch;
import com.megacrit.cardcrawl.cards.AbstractCard;
import com.megacrit.cardcrawl.cards.CardQueueItem;
import com.megacrit.cardcrawl.characters.AbstractPlayer;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.monsters.AbstractMonster;

/** Captures the resolved public queue item immediately before vanilla uses it. */
@SpirePatch(clz = AbstractPlayer.class, method = "useCard")
public final class CardQueueItemTrackerPatch {
    private CardQueueItemTrackerPatch() {}

    @SpirePrefixPatch
    public static void Prefix(AbstractPlayer __instance, AbstractCard c,
                              AbstractMonster monster, int energyOnUse) {
        if (__instance != AbstractDungeon.player || AbstractDungeon.actionManager == null
                || AbstractDungeon.actionManager.cardQueue.isEmpty()) return;
        CardQueueItem item = AbstractDungeon.actionManager.cardQueue.get(0);
        if (item == null || item.card != c || item.monster != monster
                || item.energyOnUse != energyOnUse) return;
        STSModelInspector.recordCardQueueItem(item);
    }
}
