package dev.pdpunto.l11harness;

import net.minecraft.block.Block;
import net.minecraft.block.BlockState;
import net.minecraft.block.Blocks;
import net.minecraft.block.FacingBlock;
import net.minecraft.block.ObserverBlock;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.math.Direction;
import net.minecraft.util.math.BlockPos;

import dev.pdpunto.l11.ExampleMod;

final class HarnessRunner {
    private static final BlockPos CONTROLLED_POS = new BlockPos(8, 64, 8);
    private static final BlockPos SIGNAL_POS = CONTROLLED_POS.east();

    private HarnessRunner() {
    }

    static HarnessResult run(MinecraftServer server, HarnessConfig config, HarnessRuntimeOptions options) {
        HarnessIdentity identity = TargetIdentityProbe.inspect(config.targetModId(), config.targetSha256());
        if (!identity.targetLoaded()) {
            return HarnessResult.infraError(config, identity.reason(), identity);
        }
        if (!identity.targetOriginResolved()) {
            return HarnessResult.infraError(config, identity.reason(), identity);
        }
        if (!identity.targetShaMatch()) {
            return HarnessResult.infraError(config, identity.reason(), identity);
        }

        ServerWorld world = waitForOverworld(server, options.hangMillis());
        if (world == null) {
            return HarnessResult.infraError(config, "overworld not available", identity);
        }

        HarnessSignals.reset();
        world.setBlockState(
            SIGNAL_POS,
            Blocks.OBSERVER.getDefaultState()
                .with(FacingBlock.FACING, Direction.WEST)
                .with(ObserverBlock.POWERED, false),
            Block.NOTIFY_ALL
        );
        world.setBlockState(CONTROLLED_POS, Blocks.AIR.getDefaultState(), Block.NOTIFY_ALL);
        if (config.expectNeighborUpdate()) {
            waitForObserverPowered(world, false, options.hangMillis());
        }
        HarnessSignals.reset();
        boolean changed = ExampleMod.applyProbeState(world, CONTROLLED_POS);
        BlockState actual = world.getBlockState(CONTROLLED_POS);
        boolean neighborTriggered = config.expectNeighborUpdate() && waitForObserverPowered(world, true, options.hangMillis());
        if (neighborTriggered) {
            HarnessSignals.markNeighborUpdateTriggered();
        }
        boolean statePass = changed && actual.equals(options.expectedBlockState());
        boolean neighborPass = !config.expectNeighborUpdate() || neighborTriggered;
        boolean functionalPass = statePass && neighborPass;

        if (!functionalPass) {
            String reason;
            if (!statePass && !neighborPass) {
                reason = "expected block state and neighbor update were not observed";
            } else if (!statePass) {
                reason = "expected block state was not observed";
            } else {
                reason = "neighbor update was not observed";
            }
            return HarnessResult.fail(config, identity, reason, neighborTriggered);
        }

        return HarnessResult.pass(config, identity, neighborTriggered);
    }

    private static ServerWorld waitForOverworld(MinecraftServer server, long timeoutMillis) {
        long deadline = System.nanoTime() + java.util.concurrent.TimeUnit.MILLISECONDS.toNanos(Math.max(1000L, timeoutMillis));
        while (System.nanoTime() < deadline) {
            ServerWorld world = server.getOverworld();
            if (world != null) {
                return world;
            }
            try {
                Thread.sleep(50L);
            } catch (InterruptedException exc) {
                Thread.currentThread().interrupt();
                throw new RuntimeException("interrupted while waiting for overworld", exc);
            }
        }
        return null;
    }

    private static boolean waitForObserverPowered(ServerWorld world, boolean powered, long timeoutMillis) {
        long deadline = System.nanoTime() + java.util.concurrent.TimeUnit.MILLISECONDS.toNanos(Math.max(250L, timeoutMillis));
        while (System.nanoTime() < deadline) {
            BlockState signalState = world.getBlockState(SIGNAL_POS);
            if (signalState.isOf(Blocks.OBSERVER) && signalState.get(ObserverBlock.POWERED) == powered) {
                return true;
            }
            try {
                Thread.sleep(50L);
            } catch (InterruptedException exc) {
                Thread.currentThread().interrupt();
                throw new RuntimeException("interrupted while waiting for observer state", exc);
            }
        }
        BlockState signalState = world.getBlockState(SIGNAL_POS);
        return signalState.isOf(Blocks.OBSERVER) && signalState.get(ObserverBlock.POWERED) == powered;
    }
}
