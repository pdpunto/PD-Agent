package dev.pdpunto.l11harness;

import java.util.concurrent.atomic.AtomicBoolean;
import net.fabricmc.api.DedicatedServerModInitializer;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.Item;
import net.minecraft.world.level.block.Block;

public final class L262HarnessMod implements DedicatedServerModInitializer {
    private final AtomicBoolean executed = new AtomicBoolean();

    @Override
    public void onInitializeServer() {
        ServerLifecycleEvents.SERVER_STARTED.register(server -> {
            if (!executed.compareAndSet(false, true)) return;
            HarnessConfig26_2 config = null;
            HarnessResult26_2 result;
            try {
                config = HarnessConfig26_2.fromSystemProperties();
                HarnessIdentity26_2 identity = HarnessIdentity26_2.inspect(config);
                if (!identity.targetLoaded() || !identity.targetOriginResolved() || !identity.targetShaMatch()) {
                    result = HarnessResult26_2.infra(config, identity, identity.reason());
                } else if (config.observationType().equals("REGISTRY_ENTRY_PRESENT")) {
                    result = registry(config, identity);
                } else {
                    result = association(config, identity);
                }
            } catch (Exception ex) {
                if (config == null) {
                    server.halt(false);
                    return;
                }
                result = HarnessResult26_2.infra(config, HarnessIdentity26_2.missing("harness bootstrap failed"), ex.getMessage());
            }
            try { result.write(); } catch (Exception ignored) { }
            server.halt(false);
        });
    }

    private static HarnessResult26_2 registry(HarnessConfig26_2 config, HarnessIdentity26_2 identity) {
        var identifier = HarnessConfig26_2.parseIdentifier(config.observationIdentifier());
        boolean present;
        if (config.registryKind().equals("block")) present = BuiltInRegistries.BLOCK.getOptional(identifier).isPresent();
        else present = BuiltInRegistries.ITEM.getOptional(identifier).isPresent();
        return HarnessResult26_2.registry(config, identity, present, present ? "registry entry present" : "registry entry missing", identifier.toString());
    }

    private static HarnessResult26_2 association(HarnessConfig26_2 config, HarnessIdentity26_2 identity) {
        var itemId = HarnessConfig26_2.parseIdentifier(config.associationItemId());
        var blockId = HarnessConfig26_2.parseIdentifier(config.associationBlockId());
        Item item = BuiltInRegistries.ITEM.getOptional(itemId).orElse(null);
        boolean isBlockItem = item instanceof BlockItem;
        Block associated = isBlockItem ? ((BlockItem) item).getBlock() : null;
        String actualId = associated == null ? null : BuiltInRegistries.BLOCK.getKey(associated).toString();
        boolean pass = isBlockItem && blockId.toString().equals(actualId);
        String actual = "{\"item_present\":" + (item != null) + ",\"is_block_item\":" + isBlockItem
            + ",\"actual_block_id\":" + (actualId == null ? "null" : "\"" + actualId + "\"") + ",\"associated\":" + pass + "}";
        return HarnessResult26_2.association(config, identity, pass, pass ? "BlockItem association matches" : "BlockItem association mismatch", actual);
    }
}
