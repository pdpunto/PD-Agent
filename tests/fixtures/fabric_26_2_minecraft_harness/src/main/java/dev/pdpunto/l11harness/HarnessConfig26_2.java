package dev.pdpunto.l11harness;

import java.nio.file.Path;
import net.minecraft.resources.Identifier;

record HarnessConfig26_2(
    String targetModId,
    String targetSha256,
    String targetEntrypointClass,
    String testId,
    String observationType,
    String registryKind,
    String observationIdentifier,
    String observationRecipeId,
    String associationItemId,
    String associationBlockId,
    Path resultPath
) {
    static HarnessConfig26_2 fromSystemProperties() {
        String observationType = required("pd.agent.observationType");
        if (!observationType.equals("REGISTRY_ENTRY_PRESENT")
            && !observationType.equals("BLOCK_ITEM_ASSOCIATION")
            && !observationType.equals("RECIPE_LOADED")) {
            throw new IllegalArgumentException("unsupported 26.2 observation type: " + observationType);
        }
        String registryKind = property("pd.agent.observationRegistryKind");
        String identifier = property("pd.agent.observationIdentifier");
        String recipeId = property("pd.agent.observationRecipeId");
        String itemId = property("pd.agent.observationAssociationItemId");
        String blockId = property("pd.agent.observationAssociationBlockId");
        if (observationType.equals("REGISTRY_ENTRY_PRESENT")) {
            if (!registryKind.equals("block") && !registryKind.equals("item")) {
                throw new IllegalArgumentException("26.2 registry kind must be block or item");
            }
            parseIdentifier(identifier);
        } else if (observationType.equals("RECIPE_LOADED")) {
            parseIdentifier(recipeId);
        } else {
            parseIdentifier(itemId);
            parseIdentifier(blockId);
        }
        return new HarnessConfig26_2(
            required("pd.agent.targetModId"),
            required("pd.agent.targetSha256"),
            required("pd.agent.targetEntrypointClass"),
            required("pd.agent.testId"),
            observationType,
            registryKind,
            identifier,
            recipeId,
            itemId,
            blockId,
            Path.of(required("pd.agent.resultPath")).toAbsolutePath().normalize()
        );
    }

    private static String required(String key) {
        String value = property(key);
        if (value.isBlank()) throw new IllegalArgumentException("missing " + key);
        return value;
    }

    private static String property(String key) {
        return System.getProperty(key, "").trim();
    }

    static Identifier parseIdentifier(String value) {
        Identifier parsed = Identifier.tryParse(value);
        if (parsed == null || !parsed.toString().equals(value)) {
            throw new IllegalArgumentException("invalid namespaced identifier: " + value);
        }
        return parsed;
    }
}
