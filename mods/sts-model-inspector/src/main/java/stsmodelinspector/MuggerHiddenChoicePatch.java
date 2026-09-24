package stsmodelinspector;

import com.evacipated.cardcrawl.modthespire.lib.SpirePatch;
import com.evacipated.cardcrawl.modthespire.lib.SpirePostfixPatch;
import com.evacipated.cardcrawl.modthespire.lib.SpirePrefixPatch;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.monsters.city.Mugger;

/** Keeps Mugger’s post-second-Mug random choice deferred under Runic Dome. */
@SpirePatch(clz = Mugger.class, method = "takeTurn")
public final class MuggerHiddenChoicePatch {
    private MuggerHiddenChoicePatch() {}

    @SpirePrefixPatch
    public static void Prefix(Mugger monster) {
        if (AbstractDungeon.actionManager != null && AbstractDungeon.actionManager.turn >= 2
                && monster.nextMove == 1) {
            STSModelInspector.beginHiddenDirectTurn(monster, 2);
        }
    }

    @SpirePostfixPatch
    public static void Postfix(Mugger monster) {
        STSModelInspector.finishHiddenDirectTurn(monster);
    }
}
