package dev.pdpunto.l11;

import net.fabricmc.api.ModInitializer;
import net.minecraft.block.Block;
import net.minecraft.block.BlockState;
import net.minecraft.block.Blocks;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.math.BlockPos;

public final class ExampleMod implements ModInitializer {
    public static final String MOD_ID = "pdagentl11";
    private static final BlockState PROBE_STATE = Blocks.DIAMOND_BLOCK.getDefaultState();

    @Override
    public void onInitialize() {
        // Intentionally empty. The batch-B acceptance uses the public server-side helper below.
    }

    public static boolean applyProbeState(ServerWorld world, BlockPos pos) {
        return world.setBlockState(pos, PROBE_STATE, Block.NOTIFY_ALL);
    }

    public static BlockState expectedProbeState() {
        return PROBE_STATE;
    }
}
