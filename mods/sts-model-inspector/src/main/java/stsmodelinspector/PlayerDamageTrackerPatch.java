package stsmodelinspector;

import com.evacipated.cardcrawl.modthespire.lib.SpirePatch;
import com.evacipated.cardcrawl.modthespire.lib.SpirePostfixPatch;
import com.evacipated.cardcrawl.modthespire.lib.SpirePrefixPatch;
import com.megacrit.cardcrawl.cards.DamageInfo;
import com.megacrit.cardcrawl.characters.AbstractPlayer;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;

/** Records finalized player damage at vanilla's public damage() boundary. */
@SpirePatch(clz = AbstractPlayer.class, method = "damage")
public final class PlayerDamageTrackerPatch {
    private PlayerDamageTrackerPatch() {}
    private static final ThreadLocal<STSModelInspector.PublicDamageSnapshot> BEFORE = new ThreadLocal<>();

    @SpirePrefixPatch
    public static void Prefix(AbstractPlayer __instance, DamageInfo info) {
        BEFORE.set(__instance == AbstractDungeon.player
                ? STSModelInspector.beginPlayerDamage(info, __instance) : null);
    }

    @SpirePostfixPatch
    public static void Postfix(AbstractPlayer __instance, DamageInfo info) {
        if (__instance != AbstractDungeon.player) { BEFORE.remove(); return; }
        STSModelInspector.recordPlayerDamage(info, __instance.lastDamageTaken, BEFORE.get());
        BEFORE.remove();
    }
}
