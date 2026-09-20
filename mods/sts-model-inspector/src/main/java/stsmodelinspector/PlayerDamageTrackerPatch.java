package stsmodelinspector;

import com.evacipated.cardcrawl.modthespire.lib.SpirePatch;
import com.evacipated.cardcrawl.modthespire.lib.SpirePostfixPatch;
import com.megacrit.cardcrawl.cards.DamageInfo;
import com.megacrit.cardcrawl.characters.AbstractPlayer;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;

/** Records finalized player damage at vanilla's public damage() boundary. */
@SpirePatch(clz = AbstractPlayer.class, method = "damage")
public final class PlayerDamageTrackerPatch {
    private PlayerDamageTrackerPatch() {}

    @SpirePostfixPatch
    public static void Postfix(AbstractPlayer __instance, DamageInfo info) {
        if (__instance != AbstractDungeon.player) return;
        STSModelInspector.recordPlayerDamage(info, __instance.lastDamageTaken);
    }
}
