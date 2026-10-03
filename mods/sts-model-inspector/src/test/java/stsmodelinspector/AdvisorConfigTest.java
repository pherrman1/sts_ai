package stsmodelinspector;

import java.util.Properties;

public final class AdvisorConfigTest {
    public static void main(String[] args) {
        Properties properties = new Properties();
        properties.setProperty("ctmModel", "  /configured/model  ");
        for (String explicit : new String[]{"", "  ", "/explicit/model", " /literal path "}) {
            if (!explicit.equals(STSModelInspector.ctmPrimaryModel(properties, explicit)))
                throw new AssertionError("explicit CTM override was replaced or trimmed");
        }
        if (!"/configured/model".equals(STSModelInspector.ctmPrimaryModel(properties, null)))
            throw new AssertionError("missing override did not use configured model");
        properties.setProperty("ctmModel", "  ");
        if (STSModelInspector.ctmPrimaryModel(properties, null) != null)
            throw new AssertionError("blank property should retain absent-model behavior");
        properties.clear();
        if (STSModelInspector.ctmPrimaryModel(properties, null) != null)
            throw new AssertionError("missing property should retain absent-model behavior");
        System.out.println("AdvisorConfigTest passed");
    }
}
