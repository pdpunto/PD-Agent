package dev.pdpunto.l11harness;

import java.nio.file.Files;
import java.nio.file.Path;

final class HarnessResult26_2 {
    private final HarnessConfig26_2 config;
    private final HarnessIdentity26_2 identity;
    private final boolean pass;
    private final String outcome;
    private final String reason;
    private final String actualIdentifier;
    private final String associationActual;

    private HarnessResult26_2(HarnessConfig26_2 config, HarnessIdentity26_2 identity, boolean pass, String outcome,
            String reason, String actualIdentifier, String associationActual) {
        this.config = config; this.identity = identity; this.pass = pass; this.outcome = outcome;
        this.reason = reason; this.actualIdentifier = actualIdentifier; this.associationActual = associationActual;
    }

    static HarnessResult26_2 registry(HarnessConfig26_2 config, HarnessIdentity26_2 identity, boolean pass,
            String reason, String actualIdentifier) {
        return new HarnessResult26_2(config, identity, pass, pass ? "PASS" : "FAIL", reason, actualIdentifier, null);
    }

    static HarnessResult26_2 recipeLoaded(HarnessConfig26_2 config, HarnessIdentity26_2 identity, boolean pass,
            String reason, String actualIdentifier) {
        return new HarnessResult26_2(config, identity, pass, pass ? "PASS" : "FAIL", reason, actualIdentifier, null);
    }

    static HarnessResult26_2 association(HarnessConfig26_2 config, HarnessIdentity26_2 identity, boolean pass,
            String reason, String actual) {
        return new HarnessResult26_2(config, identity, pass, pass ? "PASS" : "FAIL", reason, null, actual);
    }

    static HarnessResult26_2 infra(HarnessConfig26_2 config, HarnessIdentity26_2 identity, String reason) {
        return new HarnessResult26_2(config, identity, false, "INFRA_ERROR", reason, null, null);
    }

    void write() throws Exception {
        Path parent = config.resultPath().getParent();
        if (parent != null) Files.createDirectories(parent);
        Path temp = Files.createTempFile(parent, config.resultPath().getFileName().toString(), ".tmp");
        try { Files.writeString(temp, toJson()); Files.move(temp, config.resultPath(), java.nio.file.StandardCopyOption.REPLACE_EXISTING); }
        finally { Files.deleteIfExists(temp); }
    }

    private String toJson() {
        StringBuilder json = new StringBuilder("{");
        field(json, "schema_version", "1"); field(json, "test_id", config.testId());
        field(json, "observation_type", config.observationType()); field(json, "observation_pass", Boolean.toString(pass));
        field(json, "registry_kind", config.registryKind()); field(json, "observed_identifier", actualIdentifier);
        field(json, "target_mod_id", config.targetModId()); field(json, "target_loaded", Boolean.toString(identity.targetLoaded()));
        field(json, "target_origin_resolved", Boolean.toString(identity.targetOriginResolved()));
        field(json, "runtime_target_path", identity.runtimeTargetPath() == null ? null : identity.runtimeTargetPath().toString());
        field(json, "runtime_target_sha256", identity.runtimeTargetSha256()); field(json, "target_sha_match", Boolean.toString(identity.targetShaMatch()));
        field(json, "server_started", "true"); field(json, "functional_test_result", outcome);
        field(json, "reason", reason); field(json, "shutdown_requested", "true");
        if (config.observationType().equals("RECIPE_LOADED")) {
            field(json, "observation_expected", "{\"loaded\":true}");
            field(json, "observation_actual", "{\"recipe_id\":\"" + actualIdentifier + "\",\"loaded\":" + pass + "}");
        } else {
            field(json, "observation_expected", "{\"present\":true}");
            if (associationActual != null) field(json, "observation_actual", associationActual);
            else field(json, "observation_actual", "{\"present\":" + pass + "}");
        }
        if (!pass) {
            String errorCode = outcome.equals("INFRA_ERROR") ? "INFRA_ERROR"
                : config.observationType().equals("BLOCK_ITEM_ASSOCIATION")
                    ? "BLOCK_ITEM_ASSOCIATION_MISMATCH" : "OBSERVATION_FAILED";
            field(json, "error_code", errorCode);
        }
        return json.append('}').toString();
    }

    private static void field(StringBuilder json, String key, String value) {
        if (json.length() > 1) json.append(',');
        json.append('"').append(escape(key)).append("\":");
        if (value == null) json.append("null");
        else if (value.startsWith("{") || value.equals("true") || value.equals("false") || value.matches("-?\\d+")) json.append(value);
        else json.append('"').append(escape(value)).append('"');
    }

    private static String escape(String value) { return value.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n"); }
}
