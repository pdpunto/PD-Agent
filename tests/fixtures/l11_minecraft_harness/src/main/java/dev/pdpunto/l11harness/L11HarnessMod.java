package dev.pdpunto.l11harness;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.concurrent.TimeUnit;

import net.fabricmc.api.DedicatedServerModInitializer;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.server.MinecraftServer;

public final class L11HarnessMod implements DedicatedServerModInitializer {
    @Override
    public void onInitializeServer() {
        HarnessSignals.reset();
        Thread waiter = Thread.ofPlatform().daemon().name("pd-agent-l11-harness").start(this::waitForServerStart);
        if (waiter == null) {
            throw new IllegalStateException("failed to start harness waiter thread");
        }
    }

    private void waitForServerStart() {
        while (true) {
            Object gameInstance = FabricLoader.getInstance().getGameInstance();
            if (gameInstance instanceof MinecraftServer server) {
                if (server.isRunning()) {
                    onServerStarted(server);
                    return;
                }
            }
            sleepShort(50L);
        }
    }

    private void onServerStarted(MinecraftServer server) {
        HarnessConfig config;
        HarnessRuntimeOptions options;
        HarnessResult result;
        try {
            config = HarnessConfig.fromSystemProperties();
            options = HarnessRuntimeOptions.fromSystemProperties();
            if (options.resultMode() == HarnessRuntimeOptions.ResultMode.CRASH) {
                System.exit(1);
                return;
            }
            if (options.resultMode() == HarnessRuntimeOptions.ResultMode.HANG) {
                sleepLong(options.hangMillis());
                return;
            }
            result = HarnessRunner.run(server, config, options);
        } catch (RuntimeException ex) {
            config = fallbackConfig();
            options = new HarnessRuntimeOptions(HarnessRuntimeOptions.ResultMode.PASS, "diamond_block", 0L);
            result = HarnessResult.infraError(config, ex.getMessage() == null ? ex.getClass().getSimpleName() : ex.getMessage(), HarnessIdentity.missing("harness bootstrap failed"));
        }

        try {
            if (options.resultMode() == HarnessRuntimeOptions.ResultMode.MISSING_RESULT) {
                // Intentionally skip result file for negative evidence.
            } else if (options.resultMode() == HarnessRuntimeOptions.ResultMode.MALFORMED_RESULT) {
                writeMalformedResult(config.resultPath());
            } else {
                HarnessResultWriter.writeAtomically(config.resultPath(), result);
            }
        } catch (IOException ex) {
            throw new RuntimeException("failed to write harness result", ex);
        } finally {
            server.stop(false);
        }
    }

    private HarnessConfig fallbackConfig() {
        return new HarnessConfig(
            "pdagentl11",
            "0000000000000000000000000000000000000000000000000000000000000000",
            "dev.pdpunto.l11.ExampleMod",
            "harness_bootstrap_fallback",
            HarnessConfig.OBSERVATION_LEGACY_BLOCK_STATE,
            null,
            null,
            null,
            null,
            false,
            null,
            0,
            5,
            true,
            null,
            null,
            true,
            java.nio.file.Path.of(System.getProperty("java.io.tmpdir"), "harness-result.json").toAbsolutePath(),
            false
        );
    }

    private void writeMalformedResult(java.nio.file.Path resultPath) throws IOException {
        java.nio.file.Path parent = resultPath.getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }
        Files.writeString(resultPath, "{not-json", StandardCharsets.UTF_8);
    }

    private void sleepLong(long millis) {
        try {
            TimeUnit.MILLISECONDS.sleep(millis);
        } catch (InterruptedException exc) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("harness sleep interrupted", exc);
        }
    }

    private void sleepShort(long millis) {
        try {
            TimeUnit.MILLISECONDS.sleep(millis);
        } catch (InterruptedException exc) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("harness wait interrupted", exc);
        }
    }
}
