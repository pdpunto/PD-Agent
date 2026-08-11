package dev.pdpunto.l11harness;

import net.minecraft.block.AbstractBlock;
import net.minecraft.block.Block;
import net.minecraft.block.BlockState;
import net.minecraft.util.math.BlockPos;
import net.minecraft.world.World;

final class NeighborUpdateProbeBlock extends Block {
    NeighborUpdateProbeBlock(AbstractBlock.Settings settings) {
        super(settings);
    }

    @Override
    public void neighborUpdate(BlockState state, World world, BlockPos pos, Block sourceBlock, BlockPos sourcePos, boolean notify) {
        HarnessSignals.markNeighborUpdateTriggered();
    }
}
