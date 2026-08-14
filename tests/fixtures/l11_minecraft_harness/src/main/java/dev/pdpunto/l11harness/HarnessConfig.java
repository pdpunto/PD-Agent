package dev.pdpunto.l11harness;

import java.nio.file.Path;
import java.util.regex.Pattern;

record HarnessConfig(
    String targetModId,
    String targetSha256,
    String targetEntrypointClass,
    String testId,
    Path resultPath,
    boolean expectNeighborUpdate
) {
    static final String PROP_TARGET_MOD_ID = "pd.agent.targetModId";
    static final String PROP_TARGET_SHA256 = "pd.agent.targetSha256";
    static final String PROP_TARGET_ENTRYPOINT_CLASS = "pd.agent.targetEntrypointClass";
    static final String PROP_TEST_ID = "pd.agent.testId";
    static final String PROP_RESULT_PATH = "pd.agent.resultPath";
    static final String PROP_EXPECT_NEIGHBOR_UPDATE = "pd.agent.expectNeighborUpdate";

    private static final Pattern MOD_ID_RE = Pattern.compile("^[a-z][a-z0-9_.-]*$");
    private static final Pattern SHA256_RE = Pattern.compile("^[0-9a-fA-F]{64}$");
    private static final Pattern JAVA_CLASS_RE = Pattern.compile("^[A-Za-z_$][A-Za-z0-9_$]*(\\.[A-Za-z_$][A-Za-z0-9_$]*)*$");

    HarnessConfig {
        targetModId = normalizeModId(targetModId);
        targetSha256 = normalizeSha256(targetSha256);
        targetEntrypointClass = normalizeEntrypointClass(targetEntrypointClass);
        testId = normalizeTestId(testId);
        resultPath = normalizeResultPath(resultPath);
    }

    static HarnessConfig fromSystemProperties() {
        return new HarnessConfig(
            requireText(PROP_TARGET_MOD_ID),
            requireText(PROP_TARGET_SHA256),
            requireText(PROP_TARGET_ENTRYPOINT_CLASS),
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
