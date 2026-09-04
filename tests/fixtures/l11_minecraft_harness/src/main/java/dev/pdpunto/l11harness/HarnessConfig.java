package dev.pdpunto.l11harness;

import java.nio.file.Path;
import java.util.Locale;
import java.util.regex.Pattern;

import net.minecraft.util.Identifier;

record HarnessConfig(
    String targetModId,
    String targetSha256,
    String targetEntrypointClass,
    String testId,
    String observationType,
    String observationRegistryKind,
    String observationIdentifier,
    String observationAssociationItemId,
    String observationAssociationBlockId,
    String observationComponentId,
    String observationItemId,
    boolean observationRoundTrip,
    String observationBlockEntityId,
    int observationSlot,
    int observationCount,
    boolean observationMutation,
    String observationTagId,
    String observationMemberId,
    boolean observationExpectedMembership,
    String observationRecipeId,
    String observationInputItemId,
    int observationInputCount,
    String observationExpectedOutputItemId,
    int observationExpectedOutputCount,
    String observationLootTableId,
    String observationLootContextProfile,
    long observationLootSeed,
    String observationLootExpectedItemId,
    int observationLootExpectedCount,
    Path resultPath,
    boolean expectNeighborUpdate
) {
    static final String PROP_TARGET_MOD_ID = "pd.agent.targetModId";
    static final String PROP_TARGET_SHA256 = "pd.agent.targetSha256";
    static final String PROP_TARGET_ENTRYPOINT_CLASS = "pd.agent.targetEntrypointClass";
    static final String PROP_TEST_ID = "pd.agent.testId";
    static final String PROP_OBSERVATION_TYPE = "pd.agent.observationType";
    static final String PROP_OBSERVATION_REGISTRY_KIND = "pd.agent.observationRegistryKind";
    static final String PROP_OBSERVATION_IDENTIFIER = "pd.agent.observationIdentifier";
    static final String PROP_OBSERVATION_ASSOCIATION_ITEM_ID = "pd.agent.observationAssociationItemId";
    static final String PROP_OBSERVATION_ASSOCIATION_BLOCK_ID = "pd.agent.observationAssociationBlockId";
    static final String PROP_OBSERVATION_COMPONENT_ID = "pd.agent.observationComponentId";
    static final String PROP_OBSERVATION_ITEM_ID = "pd.agent.observationItemId";
    static final String PROP_OBSERVATION_ROUND_TRIP = "pd.agent.observationRoundTrip";
    static final String PROP_OBSERVATION_BLOCK_ENTITY_ID = "pd.agent.observationBlockEntityId";
    static final String PROP_OBSERVATION_SLOT = "pd.agent.observationSlot";
    static final String PROP_OBSERVATION_COUNT = "pd.agent.observationCount";
    static final String PROP_OBSERVATION_MUTATION = "pd.agent.observationMutation";
    static final String PROP_OBSERVATION_TAG_ID = "pd.agent.observationTagId";
    static final String PROP_OBSERVATION_MEMBER_ID = "pd.agent.observationMemberId";
    static final String PROP_OBSERVATION_EXPECTED_MEMBERSHIP = "pd.agent.observationExpectedMembership";
    static final String PROP_OBSERVATION_RECIPE_ID = "pd.agent.observationRecipeId";
    static final String PROP_OBSERVATION_INPUT_ITEM_ID = "pd.agent.observationInputItemId";
    static final String PROP_OBSERVATION_INPUT_COUNT = "pd.agent.observationInputCount";
    static final String PROP_OBSERVATION_EXPECTED_OUTPUT_ITEM_ID = "pd.agent.observationExpectedOutputItemId";
    static final String PROP_OBSERVATION_EXPECTED_OUTPUT_COUNT = "pd.agent.observationExpectedOutputCount";
    static final String PROP_OBSERVATION_LOOT_TABLE_ID = "pd.agent.observationLootTableId";
    static final String PROP_OBSERVATION_LOOT_CONTEXT_PROFILE = "pd.agent.observationLootContextProfile";
    static final String PROP_OBSERVATION_LOOT_SEED = "pd.agent.observationLootSeed";
    static final String PROP_OBSERVATION_LOOT_EXPECTED_ITEM_ID = "pd.agent.observationLootExpectedItemId";
    static final String PROP_OBSERVATION_LOOT_EXPECTED_COUNT = "pd.agent.observationLootExpectedCount";
    static final String PROP_RESULT_PATH = "pd.agent.resultPath";
    static final String PROP_EXPECT_NEIGHBOR_UPDATE = "pd.agent.expectNeighborUpdate";
    static final String OBSERVATION_LEGACY_BLOCK_STATE = "LEGACY_BLOCK_STATE";
    static final String OBSERVATION_REGISTRY_ENTRY_PRESENT = "REGISTRY_ENTRY_PRESENT";
    static final String OBSERVATION_BLOCK_ITEM_ASSOCIATION = "BLOCK_ITEM_ASSOCIATION";
    static final String OBSERVATION_ITEM_COMPONENT_STATE = "ITEM_COMPONENT_STATE";
    static final String OBSERVATION_BLOCK_ENTITY_STATE = "BLOCK_ENTITY_STATE";
    static final String OBSERVATION_INVENTORY_STATE = "INVENTORY_STATE";
    static final String OBSERVATION_TAG_MEMBERSHIP = "TAG_MEMBERSHIP";
    static final String OBSERVATION_RECIPE_MATCH = "RECIPE_MATCH";
    static final String OBSERVATION_LOOT_RESULT = "LOOT_RESULT";

    private static final Pattern MOD_ID_RE = Pattern.compile("^[a-z][a-z0-9_.-]*$");
    private static final Pattern SHA256_RE = Pattern.compile("^[0-9a-fA-F]{64}$");
    private static final Pattern JAVA_CLASS_RE = Pattern.compile("^[A-Za-z_$][A-Za-z0-9_$]*(\\.[A-Za-z_$][A-Za-z0-9_$]*)*$");

    HarnessConfig {
        targetModId = normalizeModId(targetModId);
        targetSha256 = normalizeSha256(targetSha256);
        targetEntrypointClass = normalizeEntrypointClass(targetEntrypointClass);
        testId = normalizeTestId(testId);
        observationType = normalizeObservationType(observationType);
        observationRegistryKind = normalizeObservationRegistryKind(observationType, observationRegistryKind);
        observationIdentifier = normalizeObservationIdentifier(observationType, observationIdentifier);
        observationAssociationItemId = normalizeAssociationItemId(observationType, observationAssociationItemId);
        observationAssociationBlockId = normalizeAssociationBlockId(observationType, observationAssociationBlockId);
        observationComponentId = normalizeObservationComponentId(observationType, observationComponentId);
        observationItemId = normalizeObservationItemId(observationType, observationItemId);
        observationBlockEntityId = normalizeBlockEntityId(observationType, observationBlockEntityId);
        observationSlot = normalizeSlot(observationType, observationSlot);
        observationCount = normalizeCount(observationType, observationCount);
        observationTagId = normalizeTagId(observationType, observationTagId);
        observationMemberId = normalizeTagMemberId(observationType, observationMemberId);
        observationRecipeId = normalizeRecipeField(observationType, observationRecipeId, "pdagentl11_harness:i5_marble_lantern");
        observationInputItemId = normalizeRecipeField(observationType, observationInputItemId, "minecraft:diamond");
        observationInputCount = normalizeRecipeCount(observationType, observationInputCount, "input");
        observationExpectedOutputItemId = normalizeRecipeField(observationType, observationExpectedOutputItemId, "minecraft:gold_ingot");
        observationExpectedOutputCount = normalizeRecipeCount(observationType, observationExpectedOutputCount, "output");
        observationLootTableId = normalizeLootField(observationType, observationLootTableId, "pdagentl11_harness:i6_fixed_drop");
        observationLootContextProfile = normalizeLootField(observationType, observationLootContextProfile, "generic");
        observationLootSeed = normalizeLootSeed(observationType, observationLootSeed);
        observationLootExpectedItemId = normalizeLootField(observationType, observationLootExpectedItemId, null);
        observationLootExpectedCount = normalizeLootExpectedCount(observationType, observationLootExpectedCount);
        resultPath = normalizeResultPath(resultPath);
    }

    static HarnessConfig fromSystemProperties() {
        String observationType = requireText(PROP_OBSERVATION_TYPE);
        return new HarnessConfig(
            requireText(PROP_TARGET_MOD_ID),
            requireText(PROP_TARGET_SHA256),
            requireText(PROP_TARGET_ENTRYPOINT_CLASS),
            requireText(PROP_TEST_ID),
            observationType,
            requireObservationText(PROP_OBSERVATION_REGISTRY_KIND, observationType),
            requireObservationText(PROP_OBSERVATION_IDENTIFIER, observationType),
            requireObservationText(PROP_OBSERVATION_ASSOCIATION_ITEM_ID, observationType),
            requireObservationText(PROP_OBSERVATION_ASSOCIATION_BLOCK_ID, observationType),
            requireObservationText(PROP_OBSERVATION_COMPONENT_ID, observationType),
            requireObservationText(PROP_OBSERVATION_ITEM_ID, observationType),
            requireBoolean(PROP_OBSERVATION_ROUND_TRIP, false),
            requireObservationText(PROP_OBSERVATION_BLOCK_ENTITY_ID, observationType),
            requireInteger(PROP_OBSERVATION_SLOT, 0),
            requireInteger(PROP_OBSERVATION_COUNT, 5),
            requireBoolean(PROP_OBSERVATION_MUTATION, true),
            requireObservationText(PROP_OBSERVATION_TAG_ID, observationType),
            requireObservationText(PROP_OBSERVATION_MEMBER_ID, observationType),
            requireBoolean(PROP_OBSERVATION_EXPECTED_MEMBERSHIP, true),
            requireObservationText(PROP_OBSERVATION_RECIPE_ID, observationType),
            requireObservationText(PROP_OBSERVATION_INPUT_ITEM_ID, observationType),
            requireInteger(PROP_OBSERVATION_INPUT_COUNT, 1),
            requireObservationText(PROP_OBSERVATION_EXPECTED_OUTPUT_ITEM_ID, observationType),
            requireInteger(PROP_OBSERVATION_EXPECTED_OUTPUT_COUNT, 1),
            requireObservationText(PROP_OBSERVATION_LOOT_TABLE_ID, observationType),
            requireObservationText(PROP_OBSERVATION_LOOT_CONTEXT_PROFILE, observationType),
            requireLong(PROP_OBSERVATION_LOOT_SEED, 0),
            requireObservationText(PROP_OBSERVATION_LOOT_EXPECTED_ITEM_ID, observationType),
            requireInteger(PROP_OBSERVATION_LOOT_EXPECTED_COUNT, 1),
            Path.of(requireText(PROP_RESULT_PATH)),
            requireBoolean(PROP_EXPECT_NEIGHBOR_UPDATE, false)
        );
    }

    private static String requireText(String key) {
        String value = System.getProperty(key);
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException("missing harness property: " + key);
        }
        return value.trim();
    }

    private static String normalizeModId(String value) {
        if (!MOD_ID_RE.matcher(value).matches()) {
            throw new IllegalArgumentException("invalid target mod id: " + value);
        }
        return value;
    }

    private static String normalizeSha256(String value) {
        if (!SHA256_RE.matcher(value).matches()) {
            throw new IllegalArgumentException("invalid target sha256: " + value);
        }
        return value.toLowerCase(Locale.ROOT);
    }

    private static String normalizeEntrypointClass(String value) {
        if (!JAVA_CLASS_RE.matcher(value).matches()) {
            throw new IllegalArgumentException("invalid target entrypoint class: " + value);
        }
        return value;
    }

    private static String normalizeTestId(String value) {
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException("test id cannot be empty");
        }
        return value.trim();
    }

    private static String normalizeObservationType(String value) {
        String normalized = requireTextValue("observation type", value).toUpperCase(Locale.ROOT);
        if (!OBSERVATION_LEGACY_BLOCK_STATE.equals(normalized)
            && !OBSERVATION_REGISTRY_ENTRY_PRESENT.equals(normalized)
            && !OBSERVATION_ITEM_COMPONENT_STATE.equals(normalized)
            && !OBSERVATION_BLOCK_ENTITY_STATE.equals(normalized)
            && !OBSERVATION_INVENTORY_STATE.equals(normalized)
            && !OBSERVATION_TAG_MEMBERSHIP.equals(normalized)
            && !OBSERVATION_RECIPE_MATCH.equals(normalized)
            && !OBSERVATION_BLOCK_ITEM_ASSOCIATION.equals(normalized)) {
            if (!OBSERVATION_LOOT_RESULT.equals(normalized)) {
                throw new IllegalArgumentException("unsupported observation type: " + value);
            }
        }
        return normalized;
    }

    private static String normalizeObservationRegistryKind(String observationType, String value) {
        if (OBSERVATION_TAG_MEMBERSHIP.equals(observationType)) {
            if (!"item".equals(value)) {
                throw new IllegalArgumentException("TAG_MEMBERSHIP only supports the item registry");
            }
            return value;
        }
        if (!OBSERVATION_REGISTRY_ENTRY_PRESENT.equals(observationType)) {
            return null;
        }
        String normalized = requireTextValue("observation registry kind", value).toLowerCase(Locale.ROOT);
        if (!"block".equals(normalized) && !"item".equals(normalized)) {
            throw new IllegalArgumentException("unsupported registry kind: " + value);
        }
        return normalized;
    }

    private static String normalizeObservationIdentifier(String observationType, String value) {
        if (!OBSERVATION_REGISTRY_ENTRY_PRESENT.equals(observationType)) {
            return null;
        }
        String normalized = requireTextValue("observation identifier", value);
        Identifier parsed = parseIdentifier(normalized);
        return parsed.toString();
    }

    private static String normalizeAssociationItemId(String observationType, String value) {
        if (!OBSERVATION_BLOCK_ITEM_ASSOCIATION.equals(observationType)) {
            return null;
        }
        return parseIdentifier(requireTextValue("association item id", value)).toString();
    }

    private static String normalizeAssociationBlockId(String observationType, String value) {
        if (!OBSERVATION_BLOCK_ITEM_ASSOCIATION.equals(observationType)) {
            return null;
        }
        return parseIdentifier(requireTextValue("association block id", value)).toString();
    }

    private static String normalizeObservationComponentId(String observationType, String value) {
        if (!OBSERVATION_ITEM_COMPONENT_STATE.equals(observationType)) {
            return null;
        }
        return parseIdentifier(requireTextValue("observation component id", value)).toString();
    }

    private static String normalizeObservationItemId(String observationType, String value) {
        if (OBSERVATION_INVENTORY_STATE.equals(observationType)) {
            if (!"minecraft:diamond".equals(value)) {
                throw new IllegalArgumentException("controlled inventory supports minecraft:diamond only");
            }
            return value;
        }
        if (!OBSERVATION_ITEM_COMPONENT_STATE.equals(observationType)) {
            return null;
        }
        return parseIdentifier(requireTextValue("observation item id", value)).toString();
    }

    private static String normalizeBlockEntityId(String observationType, String value) {
        if (!OBSERVATION_BLOCK_ENTITY_STATE.equals(observationType)) {
            return null;
        }
        if (!"minecraft:hopper".equals(value)) {
            throw new IllegalArgumentException("controlled fixture supports minecraft:hopper only");
        }
        return value;
    }

    private static int normalizeSlot(String observationType, int value) {
        if (!OBSERVATION_INVENTORY_STATE.equals(observationType)) {
            return 0;
        }
        if (value < 0 || value >= 5) {
            throw new IllegalArgumentException("inventory slot must be from 0 through 4");
        }
        return value;
    }

    private static int normalizeCount(String observationType, int value) {
        if (!OBSERVATION_INVENTORY_STATE.equals(observationType)) {
            return 5;
        }
        if (value < 1 || value > 64) {
            throw new IllegalArgumentException("inventory count must be from 1 through 64");
        }
        return value;
    }

    private static String normalizeTagId(String observationType, String value) {
        if (!OBSERVATION_TAG_MEMBERSHIP.equals(observationType)) {
            return null;
        }
        if (!"pdagentl11_harness:i4_controlled_members".equals(value)) {
            throw new IllegalArgumentException("unsupported controlled I4 tag");
        }
        return value;
    }

    private static String normalizeTagMemberId(String observationType, String value) {
        if (!OBSERVATION_TAG_MEMBERSHIP.equals(observationType)) {
            return null;
        }
        if (!"minecraft:diamond".equals(value)
            && !"minecraft:gold_ingot".equals(value)
            && !"minecraft:stone".equals(value)) {
            throw new IllegalArgumentException("member is outside the controlled I4 fixture");
        }
        return value;
    }

    private static String normalizeRecipeField(String observationType, String value, String expected) {
        if (!OBSERVATION_RECIPE_MATCH.equals(observationType)) {
            return null;
        }
        if (!expected.equals(value)) {
            throw new IllegalArgumentException("RECIPE_MATCH only supports " + expected);
        }
        return value;
    }

    private static int normalizeRecipeCount(String observationType, int value, String label) {
        if (!OBSERVATION_RECIPE_MATCH.equals(observationType)) {
            return 1;
        }
        if (value != 1) {
            throw new IllegalArgumentException("RECIPE_MATCH " + label + " count must be one");
        }
        return value;
    }

    private static String normalizeLootField(String observationType, String value, String expected) {
        if (!OBSERVATION_LOOT_RESULT.equals(observationType)) {
            return null;
        }
        if (value == null || value.trim().isEmpty() || (expected != null && !expected.equals(value))) {
            throw new IllegalArgumentException("invalid controlled loot field");
        }
        return value;
    }

    private static long normalizeLootSeed(String observationType, long value) {
        if (!OBSERVATION_LOOT_RESULT.equals(observationType)) {
            return 0L;
        }
        return value;
    }

    private static int normalizeLootExpectedCount(String observationType, int value) {
        if (!OBSERVATION_LOOT_RESULT.equals(observationType)) {
            return 1;
        }
        if (value < 0 || value > 64) {
            throw new IllegalArgumentException("loot expected count must be from 0 through 64");
        }
        return value;
    }

    private static String requireTextValue(String label, String value) {
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException(label + " cannot be empty");
        }
        return value.trim();
    }

    private static String requireObservationText(String key, String observationType) {
        String value = System.getProperty(key);
        boolean registryField = PROP_OBSERVATION_REGISTRY_KIND.equals(key)
            || PROP_OBSERVATION_IDENTIFIER.equals(key);
        boolean associationField = PROP_OBSERVATION_ASSOCIATION_ITEM_ID.equals(key)
            || PROP_OBSERVATION_ASSOCIATION_BLOCK_ID.equals(key);
        boolean componentField = PROP_OBSERVATION_COMPONENT_ID.equals(key)
            || PROP_OBSERVATION_ITEM_ID.equals(key);
        boolean blockEntityField = PROP_OBSERVATION_BLOCK_ENTITY_ID.equals(key);
        boolean tagField = PROP_OBSERVATION_TAG_ID.equals(key)
            || PROP_OBSERVATION_MEMBER_ID.equals(key);
        if (registryField && OBSERVATION_REGISTRY_ENTRY_PRESENT.equals(observationType)
            || (componentField && OBSERVATION_ITEM_COMPONENT_STATE.equals(observationType))
            || (PROP_OBSERVATION_ITEM_ID.equals(key) && OBSERVATION_INVENTORY_STATE.equals(observationType))
            || (associationField && OBSERVATION_BLOCK_ITEM_ASSOCIATION.equals(observationType))
            || (blockEntityField && OBSERVATION_BLOCK_ENTITY_STATE.equals(observationType))) {
            return requireTextValue(key, value);
        }
        if (OBSERVATION_RECIPE_MATCH.equals(observationType)
            && (PROP_OBSERVATION_RECIPE_ID.equals(key)
                || PROP_OBSERVATION_INPUT_ITEM_ID.equals(key)
                || PROP_OBSERVATION_EXPECTED_OUTPUT_ITEM_ID.equals(key))) {
            return requireTextValue(key, value);
        }
        if (OBSERVATION_LOOT_RESULT.equals(observationType)
            && (PROP_OBSERVATION_LOOT_TABLE_ID.equals(key)
                || PROP_OBSERVATION_LOOT_CONTEXT_PROFILE.equals(key)
                || PROP_OBSERVATION_LOOT_EXPECTED_ITEM_ID.equals(key))) {
            return requireTextValue(key, value);
        }
        if (tagField && OBSERVATION_TAG_MEMBERSHIP.equals(observationType)) {
            return requireTextValue(key, value);
        }
        return value == null ? null : value.trim();
    }

    private static Identifier parseIdentifier(String value) {
        String[] parts = value.split(":", 2);
        if (parts.length != 2 || parts[0].isBlank() || parts[1].isBlank()) {
            throw new IllegalArgumentException("invalid observation identifier: " + value);
        }
        return Identifier.of(parts[0].trim(), parts[1].trim());
    }

    private static Path normalizeResultPath(Path value) {
        Path path = value.normalize();
        if (!path.isAbsolute()) {
            throw new IllegalArgumentException("result path must be absolute: " + path);
        }
        if (path.getParent() == null) {
            throw new IllegalArgumentException("result path must have a parent directory: " + path);
        }
        return path;
    }

    private static boolean requireBoolean(String key, boolean defaultValue) {
        String value = System.getProperty(key);
        if (value == null || value.trim().isEmpty()) {
            return defaultValue;
        }
        String normalized = value.trim().toLowerCase(Locale.ROOT);
        if ("true".equals(normalized)) {
            return true;
        }
        if ("false".equals(normalized)) {
            return false;
        }
        throw new IllegalArgumentException("invalid boolean harness property: " + key + "=" + value);
    }

    private static int requireInteger(String key, int defaultValue) {
        String value = System.getProperty(key);
        if (value == null || value.trim().isEmpty()) {
            return defaultValue;
        }
        try {
            return Integer.parseInt(value.trim());
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("invalid integer harness property: " + key + "=" + value, ex);
        }
    }

    private static long requireLong(String key, long defaultValue) {
        String value = System.getProperty(key);
        if (value == null || value.trim().isEmpty()) {
            return defaultValue;
        }
        try {
            return Long.parseLong(value.trim());
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("invalid long harness property: " + key + "=" + value, ex);
        }
    }
}
