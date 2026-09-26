package stsmodelinspector;

import com.megacrit.cardcrawl.core.Settings;
import com.megacrit.cardcrawl.helpers.Hitbox;

/** Physical Leave hover must propagate even outside its separate badge. */
public final class InlineChoicesTest {
    public static void main(String[] args) {
        Settings.scale = 1;
        Settings.WIDTH = 1920;
        Settings.HEIGHT = 1080;
        Hitbox hb = new Hitbox(100, 50);
        hb.move(400, 400);
        for (boolean hovered : new boolean[]{true, false, true}) {
            hb.hovered = hovered;
            InlineChoices.Anchor anchor = InlineChoices.shopLeave(hb);
            if (anchor.hovered != hovered)
                throw new AssertionError("physical Leave hover lost");
            if (!"cancel".equals(anchor.action.get("kind").getAsString())
                    || anchor.action.has("choiceIndex") || !"Leave".equals(anchor.label))
                throw new AssertionError("Leave action binding changed");
            if (anchor.bottom + 32 >= hb.y)
                throw new AssertionError("fixture must place badge outside physical button");
        }
        System.out.println("InlineChoicesTest: Leave hover entry, exit, reentry and action binding passed");
    }
}
