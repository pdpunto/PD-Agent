package dev.pdpunto.l11harness;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.concurrent.TimeUnit;

import net.fabricmc.api.DedicatedServerModInitializer;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.server.MinecraftServer;
import com.mojang.brigadier.arguments.IntegerArgumentType;
import net.fabricmc.fabric.api.command.v2.CommandRegistrationCallback;
import net.minecraft.server.command.CommandManager;
import net.minecraft.server.command.ServerCommandSource;
import net.minecraft.block.Block;
import net.minecraft.block.Blocks;
import net.minecraft.block.entity.BlockEntity;
import net.minecraft.block.entity.HopperBlockEntity;
import net.minecraft.item.ItemStack;
import net.minecraft.item.Items;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.math.BlockPos;
import net.minecraft.world.chunk.WorldChunk;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerWorldEvents;

public final class L11HarnessMod implements DedicatedServerModInitializer {
    @Override
    public void onInitializeServer() {
        HarnessSignals.reset();
        CommandRegistrationCallback.EVENT.register((dispatcher, registryAccess, environment) ->
            dispatcher.register(CommandManager.literal("pdagent_i7")
                .then(CommandManager.literal("mark")
                    .then(CommandManager.argument("count", IntegerArgumentType.integer(1, 5))
                        .requires(source -> source.getEntity() == null)
                        .executes(context -> markInventory(context.getSource(), IntegerArgumentType.getInteger(context, "count"))))))
        );
        ServerWorldEvents.LOAD.register((server, world) -> {
            if (!"i8_world_load_effect".equals(System.getProperty("pd.agent.eventProfile"))) {
                return;
            }
            BlockPos position = new BlockPos(8, 64, 8);
            world.getChunk(position);
            world.setBlockState(position, Blocks.HOPPER.getDefaultState(), Block.NOTIFY_ALL);
            BlockEntity blockEntity = ((WorldChunk) world.getChunk(position)).getBlockEntity(
                position, WorldChunk.CreationType.IMMEDIATE
            );
            if (blockEntity instanceof HopperBlockEntity hopper) {
                hopper.setStack(0, new ItemStack(Items.DIAMOND, 3));
                hopper.markDirty();
                HarnessSignals.markWorldLoadCallbackExecuted();
            }
        });
        Thread waiter = Thread.ofPlatform().daemon().name("pd-agent-l11-harness").start(this::waitForServerStart);
        if (waiter == null) {
            throw new IllegalStateException("failed to start harness waiter thread");
        }
    }

    private static int markInventory(ServerCommandSource source, int count) {
        MinecraftServer server = source.getServer();
        ServerWorld world = server.getOverworld();
        BlockPos position = new BlockPos(8, 64, 8);
        world.getChunk(position);
        world.setBlockState(position, Blocks.HOPPER.getDefaultState(), Block.NOTIFY_ALL);
        BlockEntity blockEntity = ((WorldChunk) world.getChunk(position)).getBlockEntity(
            position, WorldChunk.CreationType.IMMEDIATE
        );
        if (!(blockEntity instanceof HopperBlockEntity hopper)) {
            return 0;
        }
        hopper.setStack(0, new ItemStack(Items.DIAMOND, count));
        hopper.markDirty();
        return count;
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
            null,
            null,
            1,
            null,
            1,
            null,
            null,
            0L,
            null,
            1,
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
