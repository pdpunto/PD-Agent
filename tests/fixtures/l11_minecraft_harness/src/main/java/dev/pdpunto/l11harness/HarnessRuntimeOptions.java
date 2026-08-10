package dev.pdpunto.l11harness;

import java.util.Locale;

import net.minecraft.block.BlockState;
import net.minecraft.block.Blocks;

import dev.pdpunto.l11.ExampleMod;

record HarnessRuntimeOptions(ResultMode resultMode, String expectedBlockStateId, long hangMillis) {
    static final String PROP_RESULT_MODE = "pd.agent.resultMode";
    static final String PROP_EXPECTED_BLOCK_STATE_ID = "pd.agent.expectedBlockStateId";
    static final String PROP_HANG_MILLIS = "pd.agent.hangMillis";

    enum ResultMode {
        PASS,
        FUNCTIONAL_FAIL,
        CRASH,
        MISSING_RESULT,
        MALFORMED_RESULT,
        HANG;

        static ResultMode fromProperty(String value) {
            String normalized = value == null ? "pass" : value.trim().toLowerCase(Locale.ROOT);
            return switch (normalized) {
                case "pass" -> PASS;
                case "functional_fail", "fail" -> FUNCTIONAL_FAIL;
                case "crash" -> CRASH;
                case "missing_result", "missing" -> MISSING_RESULT;
                case "malformed_result", "malformed" -> MALFORMED_RESULT;
                case "hang", "timeout" -> HANG;
                default -> throw new IllegalArgumentException("invalid result mode: " + value);
            };
        }
    }

    HarnessRuntimeOptions {
        resultMode = resultMode == null ? ResultMode.PASS : resultMode;
        expectedBlockStateId = normalizeBlockStateId(expectedBlockStateId);
        hangMillis = Math.max(0L, hangMillis);
    }

    static HarnessRuntimeOptions fromSystemProperties() {
        return new HarnessRuntimeOptions(
            ResultMode.fromProperty(System.getProperty(PROP_RESULT_MODE)),
            System.getProperty(PROP_EXPECTED_BLOCK_STATE_ID, "diamond_block"),
            parseLong(System.getProperty(PROP_HANG_MILLIS), 600_000L)
        );
    }

    BlockState expectedBlockState() {
        return switch (expectedBlockStateId) {
            case "air" -> Blocks.AIR.getDefaultState();
            case "diamond_block" -> ExampleMod.expectedProbeState();
            default -> throw new IllegalArgumentException("unsupported expected block state id: " + expectedBlockStateId);
        };
    }

    private static String normalizeBlockStateId(String value) {
        String normalized = value == null ? "diamond_block" : value.trim().toLowerCase(Locale.ROOT);
        if (normalized.isEmpty()) {
            return "diamond_block";
        }
        return normalized;
    }

    private static long parseLong(String value, long fallback) {
        if (value == null || value.trim().isEmpty()) {
            return fallback;
        }
        try {
            return Long.parseLong(value.trim());
        } catch (NumberFormatException exc) {
            throw new IllegalArgumentException("invalid hang millis: " + value, exc);
        }
    }
}
