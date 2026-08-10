package dev.pdpunto.l11harness;

import java.nio.file.Path;

record HarnessIdentity(
    boolean targetLoaded,
    boolean targetOriginResolved,
    Path runtimeTargetPath,
    String runtimeTargetSha256,
    boolean targetShaMatch,
    String reason
) {
    static HarnessIdentity missing(String reason) {
        return new HarnessIdentity(false, false, null, null, false, reason);
    }

    static HarnessIdentity unresolved(String reason) {
        return new HarnessIdentity(true, false, null, null, false, reason);
    }

    static HarnessIdentity resolved(Path path, String runtimeSha256, boolean shaMatch) {
        return new HarnessIdentity(true, true, path, runtimeSha256, shaMatch, shaMatch ? "target verified" : "target sha mismatch");
    }
}
