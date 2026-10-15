package stsmodelinspector;

import com.evacipated.cardcrawl.modthespire.lib.*;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.rewards.RewardItem;
import com.megacrit.cardcrawl.screens.CardRewardScreen;
import com.megacrit.cardcrawl.ui.buttons.SkipCardButton;
import javassist.*;
import javassist.expr.*;
import java.util.*;

/** A public skip is an agent decision even though vanilla retains its reward icon. */
public final class CardRewardSkipObserver {
    static final class Ledger {
        private Object player; private int floor;
        private final Set<Object> skipped=Collections.newSetFromMap(new IdentityHashMap<Object,Boolean>());
        void bind(Object player,int floor) {
            if(this.player!=player || this.floor!=floor) { skipped.clear();this.player=player;this.floor=floor; }
        }
        void skip(Object reward) { if(reward!=null)skipped.add(reward); }
        void reopen(Object reward) { skipped.remove(reward); }
        boolean contains(Object reward) { return skipped.contains(reward); }
    }
    private static final Ledger ledger=new Ledger();
    static boolean skipped(RewardItem reward) {
        ledger.bind(AbstractDungeon.player,AbstractDungeon.floorNum);return ledger.contains(reward);
    }
    public static void record() {
        ledger.bind(AbstractDungeon.player,AbstractDungeon.floorNum);
        RewardItem reward=AbstractDungeon.cardRewardScreen.rItem;
        if(AbstractDungeon.screen==AbstractDungeon.CurrentScreen.CARD_REWARD && reward!=null
                && reward.type==RewardItem.RewardType.CARD && AbstractDungeon.getCurrRoom()!=null
                && AbstractDungeon.getCurrRoom().phase!=com.megacrit.cardcrawl.rooms.AbstractRoom.RoomPhase.COMBAT
                && AbstractDungeon.combatRewardScreen.rewards.contains(reward)) ledger.skip(reward);
    }
    public static void reopen(RewardItem reward) {
        ledger.bind(AbstractDungeon.player,AbstractDungeon.floorNum);ledger.reopen(reward);
    }
    @SpirePatch(clz=SkipCardButton.class,method="update")
    public static class Skip {
        @SpireRawPatch public static void raw(CtBehavior method) throws CannotCompileException {
            final int[] sites={0};
            method.instrument(new ExprEditor() {
                @Override public void edit(MethodCall call) throws CannotCompileException {
                    if(call.getClassName().equals(AbstractDungeon.class.getName()) && call.getMethodName().equals("closeCurrentScreen")) {
                        ++sites[0];call.replace("{ stsmodelinspector.CardRewardSkipObserver.record(); $proceed($$); }");
                    }
                }
            });
            if(sites[0]!=1)throw new CannotCompileException("unqualified public card skip hook");
        }
    }
    @SpirePatch(cls="mcpthespire.ChoiceScreenUtils",method="pressCancelButton",paramtypez={},optional=true)
    public static class McpSkip {
        @SpirePrefixPatch public static void prefix() { record(); }
    }
    @SpirePatch(clz=CardRewardScreen.class,method="open",paramtypez={ArrayList.class,RewardItem.class,String.class})
    public static class Open {
        @SpireRawPatch public static void raw(CtBehavior method) throws CannotCompileException {
            method.insertBefore("{ stsmodelinspector.CardRewardSkipObserver.reopen($2); }");
        }
    }
}
