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
    static final String PROP_RESULT_PATH = "pd.agent.resultPath";
    static final String PROP_EXPECT_NEIGHBOR_UPDATE = "pd.agent.expectNeighborUpdate";
    static final String OBSERVATION_LEGACY_BLOCK_STATE = "LEGACY_BLOCK_STATE";
    static final String OBSERVATION_REGISTRY_ENTRY_PRESENT = "REGISTRY_ENTRY_PRESENT";

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
        if (!OBSERVATION_LEGACY_BLOCK_STATE.equals(normalized) && !OBSERVATION_REGISTRY_ENTRY_PRESENT.equals(normalized)) {
            throw new IllegalArgumentException("unsupported observation type: " + value);
        }
        return normalized;
    }

    private static String normalizeObservationRegistryKind(String observationType, String value) {
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

    private static String requireTextValue(String label, String value) {
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException(label + " cannot be empty");
        }
        return value.trim();
    }

    private static String requireObservationText(String key, String observationType) {
        String value = System.getProperty(key);
        if (OBSERVATION_REGISTRY_ENTRY_PRESENT.equals(observationType)) {
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
}
