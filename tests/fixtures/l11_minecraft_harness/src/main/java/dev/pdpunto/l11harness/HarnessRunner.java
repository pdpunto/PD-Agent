package dev.pdpunto.l11harness;

import net.minecraft.block.Block;
import net.minecraft.block.BlockState;
import net.minecraft.block.Blocks;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.math.BlockPos;

import dev.pdpunto.l11.ExampleMod;

final class HarnessRunner {
    private static final BlockPos CONTROLLED_POS = new BlockPos(8, 64, 8);

    private HarnessRunner() {
    }

    static HarnessResult run(MinecraftServer server, HarnessConfig config) {
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

        ServerWorld world = server.getOverworld();
        if (world == null) {
            return HarnessResult.infraError(config, "overworld not available", identity);
        }

        world.setBlockState(CONTROLLED_POS, Blocks.AIR.getDefaultState(), Block.NOTIFY_ALL);
        boolean changed = ExampleMod.applyProbeState(world, CONTROLLED_POS);
        BlockState actual = world.getBlockState(CONTROLLED_POS);
        boolean functionalPass = changed && actual.equals(ExampleMod.expectedProbeState());

        if (!functionalPass) {
            return new HarnessResult(
                1,
                config.testId(),
                config.targetModId(),
                true,
                true,
                identity.runtimeTargetPath() == null ? null : identity.runtimeTargetPath().toString(),
                identity.runtimeTargetSha256(),
                true,
                true,
                "FAIL",
                "expected block state was not observed",
                true
            );
        }

        return HarnessResult.pass(config, identity);
    }
}
