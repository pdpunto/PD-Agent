package dev.pdpunto.l11harness;

import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import net.fabricmc.loader.api.FabricLoader;
import net.fabricmc.loader.api.ModContainer;

record HarnessIdentity26_2(
    boolean targetLoaded,
    boolean targetOriginResolved,
    Path runtimeTargetPath,
    String runtimeTargetSha256,
    boolean targetShaMatch,
    String reason
) {
    static HarnessIdentity26_2 inspect(HarnessConfig26_2 config) {
        FabricLoader loader = FabricLoader.getInstance();
        if (!loader.isModLoaded(config.targetModId())) return missing("target mod not loaded: " + config.targetModId());
        ModContainer container = loader.getModContainer(config.targetModId()).orElse(null);
        if (container == null || container.getOrigin().getPaths().size() != 1) return unresolved("target origin is not a single path");
        Path path = container.getOrigin().getPaths().get(0).toAbsolutePath().normalize();
        if (!Files.isRegularFile(path)) return unresolved("target runtime path is not a file: " + path);
        String sha = sha256(path);
        return new HarnessIdentity26_2(true, true, path, sha, sha.equalsIgnoreCase(config.targetSha256()),
            sha.equalsIgnoreCase(config.targetSha256()) ? "target verified" : "target sha mismatch");
    }

    static HarnessIdentity26_2 missing(String reason) { return new HarnessIdentity26_2(false, false, null, null, false, reason); }
    static HarnessIdentity26_2 unresolved(String reason) { return new HarnessIdentity26_2(true, false, null, null, false, reason); }

    private static String sha256(Path path) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path))); }
        catch (Exception ex) { throw new IllegalStateException("cannot hash target jar", ex); }
    }
}
