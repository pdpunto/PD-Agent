package dev.pdpunto.l11harness;

import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;
import java.util.Optional;

import net.fabricmc.loader.api.FabricLoader;
import net.fabricmc.loader.api.ModContainer;
import net.fabricmc.loader.api.metadata.ModOrigin;

final class TargetIdentityProbe {
    private TargetIdentityProbe() {
    }

    static HarnessIdentity inspect(String targetModId, String expectedSha256) {
        FabricLoader loader = FabricLoader.getInstance();
        if (!loader.isModLoaded(targetModId)) {
            return HarnessIdentity.missing("target mod not loaded: " + targetModId);
        }

        Optional<ModContainer> container = loader.getModContainer(targetModId);
        if (container.isEmpty()) {
            return HarnessIdentity.missing("target mod container missing: " + targetModId);
        }

        ModOrigin origin = container.get().getOrigin();
        if (origin.getKind() != ModOrigin.Kind.PATH) {
            return HarnessIdentity.unresolved("target origin is not path-based: " + origin.getKind());
        }

        List<Path> paths = origin.getPaths();
        if (paths.size() != 1) {
            return HarnessIdentity.unresolved("target origin paths are ambiguous: " + paths.size());
        }

        Path runtimePath = paths.get(0).toAbsolutePath().normalize();
        if (!Files.isRegularFile(runtimePath)) {
            return HarnessIdentity.unresolved("target runtime path is not a file: " + runtimePath);
        }

        String runtimeSha256 = sha256(runtimePath);
        boolean shaMatch = runtimeSha256.equalsIgnoreCase(expectedSha256);
        return HarnessIdentity.resolved(runtimePath, runtimeSha256, shaMatch);
    }

    private static String sha256(Path path) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] bytes = Files.readAllBytes(path);
            return HexFormat.of().formatHex(digest.digest(bytes));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        } catch (java.io.IOException ex) {
            throw new IllegalStateException("cannot read target jar: " + path, ex);
        }
    }
}
