package dev.pdpunto.l11harness;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

import net.minecraft.util.math.BlockPos;

public final class HarnessSignals {
    private static final AtomicBoolean NEIGHBOR_UPDATE_TRIGGERED = new AtomicBoolean(false);
    private static final AtomicReference<BlockPos> ARMED_NEIGHBOR_UPDATE_POS = new AtomicReference<>();

    private HarnessSignals() {
    }

    public static void reset() {
        NEIGHBOR_UPDATE_TRIGGERED.set(false);
        ARMED_NEIGHBOR_UPDATE_POS.set(null);
    }

    public static void armNeighborUpdateProbe(BlockPos pos) {
        ARMED_NEIGHBOR_UPDATE_POS.set(pos.toImmutable());
    }

    public static void disarmNeighborUpdateProbe() {
        ARMED_NEIGHBOR_UPDATE_POS.set(null);
    }

    public static void markNeighborUpdateTriggered(BlockPos pos) {
        BlockPos armedPos = ARMED_NEIGHBOR_UPDATE_POS.get();
        if (armedPos != null && armedPos.equals(pos)) {
            NEIGHBOR_UPDATE_TRIGGERED.set(true);
        }
    }

    public static boolean neighborUpdateTriggered() {
        return NEIGHBOR_UPDATE_TRIGGERED.get();
    }
}
