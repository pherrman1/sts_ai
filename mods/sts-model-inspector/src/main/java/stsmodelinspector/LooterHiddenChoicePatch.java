package stsmodelinspector;

import com.evacipated.cardcrawl.modthespire.lib.SpirePatch;
import com.evacipated.cardcrawl.modthespire.lib.SpirePostfixPatch;
import com.evacipated.cardcrawl.modthespire.lib.SpirePrefixPatch;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.monsters.AbstractMonster;
import com.megacrit.cardcrawl.monsters.exordium.Looter;

/** Keeps Looter’s post-second-Mug random choice deferred under Runic Dome. */
@SpirePatch(clz = Looter.class, method = "takeTurn")
public final class LooterHiddenChoicePatch {
    private LooterHiddenChoicePatch() {}

    @SpirePrefixPatch
    public static void Prefix(Looter monster) {
        if (AbstractDungeon.actionManager != null && AbstractDungeon.actionManager.turn >= 2
                && monster.nextMove == 1) {
            STSModelInspector.beginHiddenDirectTurn(monster, 1);
        }
    }

    @SpirePostfixPatch
    public static void Postfix(Looter monster) {
        STSModelInspector.finishHiddenDirectTurn(monster);
    }
}
