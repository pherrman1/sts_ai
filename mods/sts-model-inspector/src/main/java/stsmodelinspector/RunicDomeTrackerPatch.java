package stsmodelinspector;

import com.evacipated.cardcrawl.modthespire.lib.*;
import com.megacrit.cardcrawl.monsters.AbstractMonster;
import com.megacrit.cardcrawl.monsters.MonsterGroup;
import com.megacrit.cardcrawl.monsters.exordium.Cultist;
import com.megacrit.cardcrawl.monsters.exordium.JawWorm;

/** Hooks precede initial RNG and publish only actually executing audited moves. */
public final class RunicDomeTrackerPatch {
    @SpirePatch(clz=MonsterGroup.class,method="init")
    public static class GroupInit {
        @SpirePrefixPatch public static void prefix(MonsterGroup __instance) { RunicDomeCapture.begin(__instance); }
    }
    @SpirePatch(clz=AbstractMonster.class,method="rollMove")
    public static class Roll {
        @SpirePrefixPatch public static void prefix(AbstractMonster __instance) { RunicDomeCapture.beginRoll(__instance); }
        @SpirePostfixPatch public static void postfix(AbstractMonster __instance) { RunicDomeCapture.endRoll(__instance); }
    }
    @SpirePatch(clz=AbstractMonster.class,method="setMove",paramtypez={String.class,byte.class,
            AbstractMonster.Intent.class,int.class,int.class,boolean.class})
    public static class Move {
        @SpirePrefixPatch public static void prefix(AbstractMonster __instance) { RunicDomeCapture.setMove(__instance); }
    }
    @SpirePatch(clz=JawWorm.class,method="takeTurn")
    public static class JawTurn {
        @SpirePrefixPatch public static void prefix(JawWorm __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=Cultist.class,method="takeTurn")
    public static class CultistTurn {
        @SpirePrefixPatch public static void prefix(Cultist __instance) { RunicDomeCapture.execute(__instance); }
    }
}
