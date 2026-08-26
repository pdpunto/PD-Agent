package dev.pdpunto.l11harness;

import com.google.gson.JsonElement;
import com.mojang.serialization.JsonOps;
import net.minecraft.block.Block;
import net.minecraft.block.BlockState;
import net.minecraft.block.Blocks;
import net.minecraft.component.ComponentType;
import net.minecraft.component.DataComponentTypes;
import net.minecraft.item.Item;
import net.minecraft.item.ItemStack;
import net.minecraft.registry.Registries;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.Identifier;
import net.minecraft.util.math.BlockPos;

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

        if (HarnessConfig.OBSERVATION_REGISTRY_ENTRY_PRESENT.equals(config.observationType())) {
            return runRegistryObservation(config, identity);
        }
        if (HarnessConfig.OBSERVATION_ITEM_COMPONENT_STATE.equals(config.observationType())) {
            return runItemComponentObservation(config, identity);
        }

        return runLegacyBlockStateObservation(config, identity, world, options);
    }

    private static HarnessResult runLegacyBlockStateObservation(
        HarnessConfig config,
        HarnessIdentity identity,
        ServerWorld world,
        HarnessRuntimeOptions options
    ) {
        HarnessSignals.reset();
        world.setBlockState(SIGNAL_POS, Blocks.DIAMOND_BLOCK.getDefaultState(), Block.NOTIFY_ALL);
        world.setBlockState(CONTROLLED_POS, Blocks.AIR.getDefaultState(), Block.NOTIFY_ALL);
        HarnessSignals.reset();
        HarnessSignals.armNeighborUpdateProbe(SIGNAL_POS);
        boolean changed;
        try {
            changed = TargetBridge.applyProbeState(config.targetEntrypointClass(), world, CONTROLLED_POS);
        } finally {
            HarnessSignals.disarmNeighborUpdateProbe();
        }
        BlockState actual = world.getBlockState(CONTROLLED_POS);
        boolean neighborTriggered = config.expectNeighborUpdate() && HarnessSignals.neighborUpdateTriggered();
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
            return HarnessResult.failLegacy(config, identity, reason, neighborTriggered);
        }

        return HarnessResult.passLegacy(config, identity, neighborTriggered);
    }

    private static HarnessResult runRegistryObservation(HarnessConfig config, HarnessIdentity identity) {
        Identifier identifier = parseIdentifier(config.observationIdentifier());
        boolean present = isRegistryEntryPresent(config.observationRegistryKind(), identifier);
        String observedIdentifier = identifier.toString();
        if (!present) {
            return HarnessResult.failRegistry(
                config,
                identity,
                config.observationRegistryKind(),
                observedIdentifier,
                "registry entry was not observed: " + config.observationRegistryKind() + " " + observedIdentifier
            );
        }
        return HarnessResult.passRegistry(config, identity, config.observationRegistryKind(), observedIdentifier);
    }

    private static HarnessResult runItemComponentObservation(HarnessConfig config, HarnessIdentity identity) {
        Identifier itemId = parseIdentifier(config.observationItemId());
        Item item = Registries.ITEM.get(itemId);
        if (item == null) {
            return HarnessResult.failItemComponent(config, identity, "unknown item: " + itemId);
        }
        Identifier componentId = parseIdentifier(config.observationComponentId());
        ComponentType<?> component = Registries.DATA_COMPONENT_TYPE.get(componentId);
        if (component == null) {
            return HarnessResult.failItemComponent(config, identity, "unknown component: " + componentId);
        }
        if (component != DataComponentTypes.DAMAGE) {
            return HarnessResult.failItemComponent(config, identity, "controlled fixture supports minecraft:damage only");
        }
        return observeDamageComponent(config, identity, item, componentId);
    }

    private static HarnessResult observeDamageComponent(
        HarnessConfig config,
        HarnessIdentity identity,
        Item item,
        Identifier componentId
    ) {
        ItemStack stack = new ItemStack(item);
        boolean absentBefore = !stack.contains(DataComponentTypes.DAMAGE);
        JsonElement afterMutationJson;
        JsonElement afterJson;
        JsonElement restoredJson = null;
        boolean roundTripPass = true;
        try {
            stack.set(DataComponentTypes.DAMAGE, 7);
            afterMutationJson = encodeDamage(stack.get(DataComponentTypes.DAMAGE));
            stack.set(DataComponentTypes.DAMAGE, 11);
            afterJson = encodeDamage(stack.get(DataComponentTypes.DAMAGE));
            if (config.observationRoundTrip()) {
                stack.set(DataComponentTypes.DAMAGE, decodeDamage(afterMutationJson));
                restoredJson = encodeDamage(stack.get(DataComponentTypes.DAMAGE));
                roundTripPass = afterMutationJson.equals(restoredJson);
            }
        } catch (RuntimeException ex) {
            return HarnessResult.blockedItemComponent(config, identity, "component codec failure: " + ex.getMessage());
        }
        boolean pass = absentBefore && stack.contains(DataComponentTypes.DAMAGE)
            && "11".equals(afterJson.toString()) && roundTripPass;
        return HarnessResult.itemComponent(
            config,
            identity,
            componentId.toString(),
            config.observationItemId(),
            absentBefore,
            afterMutationJson,
            afterJson,
            restoredJson,
            config.observationRoundTrip(),
            pass,
            pass ? "controlled item component mutation and codec round-trip observed" : "controlled item component observation mismatch"
        );
    }

    private static JsonElement encodeDamage(Integer value) {
        return DataComponentTypes.DAMAGE.getCodec().encodeStart(JsonOps.INSTANCE, value)
            .getOrThrow();
    }

    private static Integer decodeDamage(JsonElement json) {
        return DataComponentTypes.DAMAGE.getCodec().parse(JsonOps.INSTANCE, json)
            .getOrThrow();
    }

    private static boolean isRegistryEntryPresent(String registryKind, Identifier identifier) {
        return switch (registryKind) {
            case "block" -> Registries.BLOCK.containsId(identifier);
            case "item" -> Registries.ITEM.containsId(identifier);
            default -> throw new IllegalArgumentException("unsupported registry kind: " + registryKind);
        };
    }

    private static Identifier parseIdentifier(String value) {
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException("observation identifier cannot be empty");
        }
        String[] parts = value.trim().split(":", 2);
        if (parts.length != 2 || parts[0].isBlank() || parts[1].isBlank()) {
            throw new IllegalArgumentException("invalid observation identifier: " + value);
        }
        return Identifier.of(parts[0].trim(), parts[1].trim());
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
}
