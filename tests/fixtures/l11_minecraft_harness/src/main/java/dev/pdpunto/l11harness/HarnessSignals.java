package dev.pdpunto.l11harness;

import java.util.concurrent.atomic.AtomicBoolean;

final class HarnessSignals {
    private static final AtomicBoolean NEIGHBOR_UPDATE_TRIGGERED = new AtomicBoolean(false);

    private HarnessSignals() {
    }

    static void reset() {
        NEIGHBOR_UPDATE_TRIGGERED.set(false);
    }

    static void markNeighborUpdateTriggered() {
        NEIGHBOR_UPDATE_TRIGGERED.set(true);
    }

    static boolean neighborUpdateTriggered() {
        return NEIGHBOR_UPDATE_TRIGGERED.get();
    }
}
