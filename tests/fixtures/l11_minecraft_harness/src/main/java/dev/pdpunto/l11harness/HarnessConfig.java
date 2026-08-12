package dev.pdpunto.l11harness;

import java.nio.file.Path;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;

record HarnessConfig(String targetModId, String targetSha256, String testId, Path resultPath, boolean expectNeighborUpdate) {
    static final String PROP_TARGET_MOD_ID = "pd.agent.targetModId";
    static final String PROP_TARGET_SHA256 = "pd.agent.targetSha256";
    static final String PROP_TEST_ID = "pd.agent.testId";
    static final String PROP_RESULT_PATH = "pd.agent.resultPath";
    static final String PROP_EXPECT_NEIGHBOR_UPDATE = "pd.agent.expectNeighborUpdate";
    static final String SUPPORTED_TEST_ID = "block_state_probe";
    static final Set<String> SUPPORTED_TEST_IDS = Set.of(
        SUPPORTED_TEST_ID,
        "block_state_probe_with_signal"
    );

    private static final Pattern MOD_ID_RE = Pattern.compile("^[a-z][a-z0-9_.-]*$");
    private static final Pattern SHA256_RE = Pattern.compile("^[0-9a-fA-F]{64}$");

    HarnessConfig {
        targetModId = normalizeModId(targetModId);
        targetSha256 = normalizeSha256(targetSha256);
        testId = normalizeTestId(testId);
        resultPath = normalizeResultPath(resultPath);
    }

    static HarnessConfig fromSystemProperties() {
        return new HarnessConfig(
            requireText(PROP_TARGET_MOD_ID),
            requireText(PROP_TARGET_SHA256),
            requireText(PROP_TEST_ID),
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

    private static String normalizeTestId(String value) {
        if (!SUPPORTED_TEST_IDS.contains(value)) {
            throw new IllegalArgumentException("unsupported test id: " + value);
        }
        return value;
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
