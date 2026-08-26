package dev.pdpunto.l11harness;

import com.google.gson.JsonElement;

final class HarnessResult {
    private final int schemaVersion;
    private final String testId;
    private final String observationType;
    private final boolean observationPass;
    private final String registryKind;
    private final String observedIdentifier;
    private final String targetModId;
    private final boolean targetLoaded;
    private final boolean targetOriginResolved;
    private final String runtimeTargetPath;
    private final String runtimeTargetSha256;
    private final boolean targetShaMatch;
    private final boolean serverStarted;
    private final String functionalTestResult;
    private final boolean neighborUpdateTriggered;
    private final String reason;
    private final boolean shutdownRequested;
    private final String componentId;
    private final String itemId;
    private final Boolean componentAbsentBefore;
    private final JsonElement componentJsonAfterMutation;
    private final JsonElement componentJsonAfter;
    private final JsonElement componentJsonRestored;
    private final Boolean componentRoundTrip;
    private final Boolean componentMutationPass;

    HarnessResult(
        int schemaVersion,
        String testId,
        String observationType,
        boolean observationPass,
        String registryKind,
        String observedIdentifier,
        String targetModId,
        boolean targetLoaded,
        boolean targetOriginResolved,
        String runtimeTargetPath,
        String runtimeTargetSha256,
        boolean targetShaMatch,
        boolean serverStarted,
        String functionalTestResult,
        boolean neighborUpdateTriggered,
        String reason,
        boolean shutdownRequested,
        String componentId,
        String itemId,
        Boolean componentAbsentBefore,
        JsonElement componentJsonAfterMutation,
        JsonElement componentJsonAfter,
        JsonElement componentJsonRestored,
        Boolean componentRoundTrip,
        Boolean componentMutationPass
    ) {
        this.schemaVersion = schemaVersion;
        this.testId = testId;
        this.observationType = observationType;
        this.observationPass = observationPass;
        this.registryKind = registryKind;
        this.observedIdentifier = observedIdentifier;
        this.targetModId = targetModId;
        this.targetLoaded = targetLoaded;
        this.targetOriginResolved = targetOriginResolved;
        this.runtimeTargetPath = runtimeTargetPath;
        this.runtimeTargetSha256 = runtimeTargetSha256;
        this.targetShaMatch = targetShaMatch;
        this.serverStarted = serverStarted;
        this.functionalTestResult = functionalTestResult;
        this.neighborUpdateTriggered = neighborUpdateTriggered;
        this.reason = reason;
        this.shutdownRequested = shutdownRequested;
        this.componentId = componentId;
        this.itemId = itemId;
        this.componentAbsentBefore = componentAbsentBefore;
        this.componentJsonAfterMutation = componentJsonAfterMutation;
        this.componentJsonAfter = componentJsonAfter;
        this.componentJsonRestored = componentJsonRestored;
        this.componentRoundTrip = componentRoundTrip;
        this.componentMutationPass = componentMutationPass;
    }

    static HarnessResult passLegacy(HarnessConfig config, HarnessIdentity identity, boolean neighborUpdateTriggered) {
        return create(
            config,
            identity,
            config.observationType(),
            true,
            null,
            null,
            "PASS",
            neighborUpdateTriggered,
            identity.reason()
            , null, null, null, null, null, null, null, null
        );
    }

    static HarnessResult failLegacy(HarnessConfig config, HarnessIdentity identity, String reason, boolean neighborUpdateTriggered) {
        return create(
            config,
            identity,
            config.observationType(),
            false,
            null,
            null,
            "FAIL",
            neighborUpdateTriggered,
            reason
            , null, null, null, null, null, null, null, null
        );
    }

    static HarnessResult passRegistry(
        HarnessConfig config,
        HarnessIdentity identity,
        String registryKind,
        String observedIdentifier
    ) {
        return create(
            config,
            identity,
            config.observationType(),
            true,
            registryKind,
            observedIdentifier,
            "PASS",
            false,
            identity.reason()
            , null, null, null, null, null, null, null, null
        );
    }

    static HarnessResult failRegistry(
        HarnessConfig config,
        HarnessIdentity identity,
        String registryKind,
        String observedIdentifier,
        String reason
    ) {
        return create(
            config,
            identity,
            config.observationType(),
            false,
            registryKind,
            observedIdentifier,
            "FAIL",
            false,
            reason
            , null, null, null, null, null, null, null, null
        );
    }

    static HarnessResult infraError(HarnessConfig config, String reason, HarnessIdentity identity) {
        return create(
            config,
            identity,
            config.observationType(),
            false,
            config.observationRegistryKind(),
            config.observationIdentifier(),
            "INFRA_ERROR",
            false,
            reason
            , null, null, null, null, null, null, null, null
        );
    }

    static HarnessResult failItemComponent(HarnessConfig config, HarnessIdentity identity, String reason) {
        return itemComponentError(config, identity, "INVALID", reason);
    }

    static HarnessResult blockedItemComponent(HarnessConfig config, HarnessIdentity identity, String reason) {
        return itemComponentError(config, identity, "BLOCKED", reason);
    }

    private static HarnessResult itemComponentError(HarnessConfig config, HarnessIdentity identity, String outcome, String reason) {
        return create(
            config, identity, config.observationType(), false, null, null, outcome, false, reason,
            config.observationComponentId(), config.observationItemId(), null, null, null, null,
            config.observationRoundTrip(), false
        );
    }

    static HarnessResult itemComponent(
        HarnessConfig config,
        HarnessIdentity identity,
        String componentId,
        String itemId,
        boolean absentBefore,
        JsonElement afterMutation,
        JsonElement after,
        JsonElement restored,
        boolean roundTrip,
        boolean pass,
        String reason
    ) {
        return create(
            config, identity, config.observationType(), pass, null, null, pass ? "PASS" : "FAIL", false, reason,
            componentId, itemId, absentBefore, afterMutation, after, restored, roundTrip, pass
        );
    }

    private static HarnessResult create(
        HarnessConfig config,
        HarnessIdentity identity,
        String observationType,
        boolean observationPass,
        String registryKind,
        String observedIdentifier,
        String functionalTestResult,
        boolean neighborUpdateTriggered,
        String reason,
        String componentId,
        String itemId,
        Boolean componentAbsentBefore,
        JsonElement componentJsonAfterMutation,
        JsonElement componentJsonAfter,
        JsonElement componentJsonRestored,
        Boolean componentRoundTrip,
        Boolean componentMutationPass
    ) {
        return new HarnessResult(
            1,
            config.testId(),
            observationType,
            observationPass,
            registryKind,
            observedIdentifier,
            config.targetModId(),
            identity.targetLoaded(),
            identity.targetOriginResolved(),
            identity.runtimeTargetPath() == null ? null : identity.runtimeTargetPath().toString(),
            identity.runtimeTargetSha256(),
            identity.targetShaMatch(),
            true,
            functionalTestResult,
            neighborUpdateTriggered,
            reason,
            true,
            componentId,
            itemId,
            componentAbsentBefore,
            componentJsonAfterMutation,
            componentJsonAfter,
            componentJsonRestored,
            componentRoundTrip,
            componentMutationPass
        );
    }

    String toJson() {
        StringBuilder builder = new StringBuilder();
        builder.append("{\n");
        appendField(builder, "schema_version", schemaVersion).append(",\n");
        appendField(builder, "test_id", testId).append(",\n");
        appendField(builder, "observation_type", observationType).append(",\n");
        appendField(builder, "observation_pass", observationPass).append(",\n");
        appendField(builder, "registry_kind", registryKind).append(",\n");
        appendField(builder, "observed_identifier", observedIdentifier).append(",\n");
        appendField(builder, "target_mod_id", targetModId).append(",\n");
        appendField(builder, "target_loaded", targetLoaded).append(",\n");
        appendField(builder, "target_origin_resolved", targetOriginResolved).append(",\n");
        appendField(builder, "runtime_target_path", runtimeTargetPath).append(",\n");
        appendField(builder, "runtime_target_sha256", runtimeTargetSha256).append(",\n");
        appendField(builder, "target_sha_match", targetShaMatch).append(",\n");
        appendField(builder, "server_started", serverStarted).append(",\n");
        appendField(builder, "functional_test_result", functionalTestResult).append(",\n");
        appendField(builder, "neighbor_update_triggered", neighborUpdateTriggered).append(",\n");
        appendField(builder, "reason", reason).append(",\n");
        appendField(builder, "shutdown_requested", shutdownRequested).append(",\n");
        appendField(builder, "component_id", componentId).append(",\n");
        appendField(builder, "item_id", itemId).append(",\n");
        appendField(builder, "component_absent_before", componentAbsentBefore).append(",\n");
        appendJsonField(builder, "component_json_after_mutation", componentJsonAfterMutation).append(",\n");
        appendJsonField(builder, "component_json_after", componentJsonAfter).append(",\n");
        appendJsonField(builder, "component_json_restored", componentJsonRestored).append(",\n");
        appendField(builder, "component_round_trip", componentRoundTrip).append(",\n");
        appendField(builder, "component_mutation_pass", componentMutationPass).append("\n");
        builder.append("}");
        return builder.toString();
    }

    private static StringBuilder appendField(StringBuilder builder, String name, Object value) {
        builder.append("  \"").append(name).append("\": ");
        if (value == null) {
            builder.append("null");
        } else if (value instanceof Boolean || value instanceof Number) {
            builder.append(value);
        } else {
            builder.append("\"").append(escapeJson(value.toString())).append("\"");
        }
        return builder;
    }

    private static StringBuilder appendJsonField(StringBuilder builder, String name, JsonElement value) {
        builder.append("  \"").append(name).append("\": ");
        builder.append(value == null ? "null" : value.toString());
        return builder;
    }

    private static String escapeJson(String value) {
        return value
            .replace("\\", "\\\\")
            .replace("\"", "\\\"")
            .replace("\b", "\\b")
            .replace("\f", "\\f")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t");
    }
}
