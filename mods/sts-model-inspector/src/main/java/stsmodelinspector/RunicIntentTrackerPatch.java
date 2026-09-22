package stsmodelinspector;

import com.evacipated.cardcrawl.modthespire.lib.SpirePatch;
import com.evacipated.cardcrawl.modthespire.lib.SpirePostfixPatch;
import com.evacipated.cardcrawl.modthespire.lib.SpirePrefixPatch;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.monsters.AbstractMonster;

/** Captures only public pre-roll state for Runic Dome's hidden intents. */
@SpirePatch(clz = AbstractMonster.class, method = "rollMove")
public final class RunicIntentTrackerPatch {
    private RunicIntentTrackerPatch() {}

    @SpirePrefixPatch
    public static void Prefix(AbstractMonster monster) {
        STSModelInspector.recordHiddenIntentRoll(monster);
    }

    @SpirePostfixPatch
    public static void Postfix(AbstractMonster monster) {
        STSModelInspector.finishHiddenIntentRoll(monster);
    }
}
