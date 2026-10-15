package stsmodelinspector;

public final class SilverBudgetTest {
    public static void main(String[] args) {
        long budget = 1000L;
        budget = STSModelInspector.nextSilverSearchBudget(budget);
        if (budget != 10000L) throw new AssertionError("first boost must be 1k -> 10k");
        budget = STSModelInspector.nextSilverSearchBudget(budget);
        if (budget != 20000L) throw new AssertionError("second boost must add 10k");
        budget = STSModelInspector.nextSilverSearchBudget(budget);
        if (budget != 30000L) throw new AssertionError("later boosts must add 10k");
        System.out.println("SilverBudgetTest: 1k -> 10k -> 20k -> 30k passed");
    }
}
