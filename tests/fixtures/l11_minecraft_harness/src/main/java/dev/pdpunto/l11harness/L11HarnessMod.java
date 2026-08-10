package dev.pdpunto.l11harness;

import java.io.IOException;

import net.fabricmc.api.DedicatedServerModInitializer;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.minecraft.server.MinecraftServer;

public final class L11HarnessMod implements DedicatedServerModInitializer {
    @Override
    public void onInitializeServer() {
        ServerLifecycleEvents.SERVER_STARTED.register(this::onServerStarted);
    }

    private void onServerStarted(MinecraftServer server) {
        HarnessConfig config;
        HarnessResult result;
        try {
            config = HarnessConfig.fromSystemProperties();
            result = HarnessRunner.run(server, config);
        } catch (RuntimeException ex) {
            config = fallbackConfig();
            result = HarnessResult.infraError(config, ex.getMessage() == null ? ex.getClass().getSimpleName() : ex.getMessage(), HarnessIdentity.missing("harness bootstrap failed"));
        }

        try {
            HarnessResultWriter.writeAtomically(config.resultPath(), result);
        } catch (IOException ex) {
            throw new RuntimeException("failed to write harness result", ex);
        } finally {
            server.stop(false);
        }
    }

    private HarnessConfig fallbackConfig() {
        return new HarnessConfig("pdagentl11", "0000000000000000000000000000000000000000000000000000000000000000", HarnessConfig.SUPPORTED_TEST_ID, java.nio.file.Path.of(System.getProperty("java.io.tmpdir"), "harness-result.json").toAbsolutePath());
    }
}
