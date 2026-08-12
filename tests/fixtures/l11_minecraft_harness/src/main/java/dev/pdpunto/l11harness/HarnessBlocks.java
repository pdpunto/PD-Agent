package dev.pdpunto.l11harness;

import net.minecraft.block.AbstractBlock;
import net.minecraft.block.Block;
import net.minecraft.registry.RegistryKey;
import net.minecraft.registry.Registries;
import net.minecraft.registry.Registry;
import net.minecraft.util.Identifier;

final class HarnessBlocks {
    private static final Identifier NEIGHBOR_UPDATE_PROBE_ID = Identifier.of("pdagentl11_harness", "neighbor_update_probe");
    private static final Block NEIGHBOR_UPDATE_PROBE = Registry.register(
        Registries.BLOCK,
        NEIGHBOR_UPDATE_PROBE_ID,
        new NeighborUpdateProbeBlock(
            AbstractBlock.Settings.create().registryKey(
                RegistryKey.<Block>of(
                    RegistryKey.ofRegistry(Identifier.of("minecraft", "block")),
                    NEIGHBOR_UPDATE_PROBE_ID
                )
            )
        )
    );

    private HarnessBlocks() {
    }

    static Block neighborUpdateProbe() {
        return NEIGHBOR_UPDATE_PROBE;
    }
}
