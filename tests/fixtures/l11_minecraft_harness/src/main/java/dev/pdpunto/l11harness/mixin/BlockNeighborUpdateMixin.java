package dev.pdpunto.l11harness.mixin;

import dev.pdpunto.l11harness.HarnessSignals;
import net.minecraft.block.AbstractBlock;
import net.minecraft.block.Block;
import net.minecraft.block.BlockState;
import net.minecraft.util.math.BlockPos;
import net.minecraft.world.World;
import net.minecraft.world.block.WireOrientation;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(AbstractBlock.class)
abstract class BlockNeighborUpdateMixin {
    @Inject(
        method = "neighborUpdate(Lnet/minecraft/block/BlockState;Lnet/minecraft/world/World;Lnet/minecraft/util/math/BlockPos;Lnet/minecraft/block/Block;Lnet/minecraft/world/block/WireOrientation;Z)V",
        at = @At("HEAD")
    )
    private void pdagent$markNeighborUpdate(
        BlockState state,
        World world,
        BlockPos pos,
        Block sourceBlock,
        WireOrientation wireOrientation,
        boolean notify,
        CallbackInfo ci
    ) {
        if (!world.isClient()) {
            HarnessSignals.markNeighborUpdateTriggered(pos);
        }
    }
}
