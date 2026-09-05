package dev.pdpunto.l11harness;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.mojang.serialization.JsonOps;
import net.minecraft.block.Block;
import net.minecraft.block.BlockState;
import net.minecraft.block.Blocks;
import net.minecraft.block.HopperBlock;
import net.minecraft.block.entity.BlockEntity;
import net.minecraft.block.entity.HopperBlockEntity;
import net.minecraft.component.ComponentType;
import net.minecraft.component.DataComponentTypes;
import net.minecraft.item.Item;
import net.minecraft.item.BlockItem;
import net.minecraft.item.ItemStack;
import net.minecraft.item.Items;
import net.minecraft.inventory.Inventory;
import net.minecraft.registry.Registries;
import net.minecraft.registry.RegistryKeys;
import net.minecraft.registry.RegistryWrapper;
import net.minecraft.registry.entry.RegistryEntry;
import net.minecraft.registry.entry.RegistryEntryList;
import net.minecraft.registry.tag.TagKey;
import net.minecraft.recipe.CraftingRecipe;
import net.minecraft.recipe.RecipeEntry;
import net.minecraft.recipe.input.CraftingRecipeInput;
import net.minecraft.registry.RegistryKey;
import net.minecraft.loot.LootTable;
import net.minecraft.loot.context.LootWorldContext;
import net.minecraft.loot.context.LootContextParameters;
import net.minecraft.util.math.Vec3d;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.Identifier;
import net.minecraft.util.math.BlockPos;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import net.minecraft.world.chunk.WorldChunk;

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

        String persistencePhase = System.getProperty("pd.agent.persistencePhase");
        if ("PHASE_1".equals(persistencePhase) || "PHASE_2".equals(persistencePhase)) {
            return runPersistence(server, config, identity, world, persistencePhase, options);
        }

        String commandProfile = System.getProperty("pd.agent.commandProfile");
        if ("i7_inventory_mark".equals(commandProfile)) {
            return runCommandAction(server, config, identity, world);
        }

        if (HarnessConfig.OBSERVATION_REGISTRY_ENTRY_PRESENT.equals(config.observationType())) {
            return runRegistryObservation(config, identity);
        }
        if (HarnessConfig.OBSERVATION_BLOCK_ITEM_ASSOCIATION.equals(config.observationType())) {
            return runBlockItemAssociationObservation(config, identity);
        }
        if (HarnessConfig.OBSERVATION_ITEM_COMPONENT_STATE.equals(config.observationType())) {
            return runItemComponentObservation(config, identity);
        }
        if (HarnessConfig.OBSERVATION_BLOCK_ENTITY_STATE.equals(config.observationType())) {
            return runBlockEntityObservation(config, identity, world);
        }
        if (HarnessConfig.OBSERVATION_INVENTORY_STATE.equals(config.observationType())) {
            return runInventoryObservation(config, identity, world);
        }
        if (HarnessConfig.OBSERVATION_TAG_MEMBERSHIP.equals(config.observationType())) {
            return runTagMembershipObservation(server, config, identity);
        }
        if (HarnessConfig.OBSERVATION_RECIPE_MATCH.equals(config.observationType())) {
            return runRecipeMatchObservation(server, config, identity, world);
        }
        if (HarnessConfig.OBSERVATION_RECIPE_LOADED.equals(config.observationType())) {
            return runRecipeLoadedObservation(server, config, identity);
        }
        if (HarnessConfig.OBSERVATION_LOOT_RESULT.equals(config.observationType())) {
            return runLootResultObservation(server, config, identity, world);
        }

        return runLegacyBlockStateObservation(config, identity, world, options);
    }

    private static HarnessResult runPersistence(
        MinecraftServer server,
        HarnessConfig config,
        HarnessIdentity identity,
        ServerWorld world,
        String phase,
        HarnessRuntimeOptions options
    ) {
        CompletableFuture<HarnessResult> result = new CompletableFuture<>();
        server.execute(() -> {
            try {
                result.complete(runPersistenceOnServer(server, config, identity, world, phase, options));
            } catch (RuntimeException ex) {
                result.completeExceptionally(ex);
            }
        });
        try {
            return result.get();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("persistence execution interrupted", ex);
        } catch (ExecutionException ex) {
            throw new IllegalStateException("persistence execution failed", ex.getCause());
        }
    }

    private static HarnessResult runPersistenceOnServer(
        MinecraftServer server,
        HarnessConfig config,
        HarnessIdentity identity,
        ServerWorld world,
        String phase,
        HarnessRuntimeOptions options
    ) {
        if ("PHASE_1".equals(phase)) {
            PersistenceSignals.mark("SETUP_STARTED");
            world.getChunk(CONTROLLED_POS);
            world.setBlockState(CONTROLLED_POS, Blocks.HOPPER.getDefaultState(), Block.NOTIFY_ALL);
            BlockEntity blockEntity = ((WorldChunk) world.getChunk(CONTROLLED_POS)).getBlockEntity(
                CONTROLLED_POS, WorldChunk.CreationType.IMMEDIATE
            );
            if (!(blockEntity instanceof HopperBlockEntity hopper)) {
                return HarnessResult.inventory(config, identity, new JsonObject(), new JsonObject(), false,
                    "controlled persistence hopper was not present");
            }
            int count = config.observationCount();
            hopper.setStack(config.observationSlot(), new ItemStack(Items.DIAMOND, count));
            hopper.markDirty();
            PersistenceSignals.mark("MUTATION_COMPLETED");
            JsonObject expected = new JsonObject();
            expected.addProperty("slot", config.observationSlot());
            expected.addProperty("item_id", "minecraft:diamond");
            expected.addProperty("count", count);
            JsonObject actual = new JsonObject();
            actual.addProperty("slot", config.observationSlot());
            actual.addProperty("item_id", String.valueOf(Registries.ITEM.getId(hopper.getStack(config.observationSlot()).getItem())));
            actual.addProperty("count", hopper.getStack(config.observationSlot()).getCount());
            PersistenceSignals.mark("PRE_SAVE_OBSERVATION");
            PersistenceSignals.mark("SAVE_REQUESTED");
            server.save(false, true, true);
            if (!PersistenceSignals.has("AFTER_SAVE")) {
                return HarnessResult.inventory(config, identity, expected, actual, false,
                    "AFTER_SAVE was not observed").withError("SAVE_COMPLETION_MISSING");
            }
            PersistenceSignals.mark("SAVE_COMPLETED");
            HarnessResult result = HarnessResult.inventory(config, identity, expected, actual, true,
                "persistence phase 1 saved controlled inventory");
            PersistenceSignals.mark("SHUTDOWN_INITIATED");
            server.stop(false);
            return result;
        }

        PersistenceSignals.mark("REOPEN_STARTED");
        BlockEntity blockEntity = ((WorldChunk) world.getChunk(CONTROLLED_POS)).getBlockEntity(
            CONTROLLED_POS, WorldChunk.CreationType.IMMEDIATE
        );
        if (!(blockEntity instanceof HopperBlockEntity hopper)) {
            return HarnessResult.inventory(config, identity, new JsonObject(), new JsonObject(), false,
                "persisted hopper was not found during reopen").withError("PERSISTED_STATE_MISMATCH");
        }
        JsonObject expected = new JsonObject();
        expected.addProperty("slot", config.observationSlot());
        expected.addProperty("item_id", "minecraft:diamond");
        expected.addProperty("count", config.observationCount());
        ItemStack stack = hopper.getStack(config.observationSlot());
        JsonObject actual = new JsonObject();
        actual.addProperty("slot", config.observationSlot());
        actual.addProperty("item_id", stack.isEmpty() ? "minecraft:air" : String.valueOf(Registries.ITEM.getId(stack.getItem())));
        actual.addProperty("count", stack.isEmpty() ? 0 : stack.getCount());
        PersistenceSignals.mark("FIRST_PERSISTED_OBSERVATION");
        boolean pass = "minecraft:diamond".equals(actual.get("item_id").getAsString())
            && actual.get("count").getAsInt() == config.observationCount();
        HarnessResult result = HarnessResult.inventory(config, identity, expected, actual, pass,
            pass ? "persisted inventory reopened" : "persisted inventory mismatch");
        if (!pass) {
            result.withError("PERSISTED_STATE_MISMATCH");
        }
        PersistenceSignals.mark("SHUTDOWN_INITIATED");
        server.stop(false);
        return result;
    }

    private static HarnessResult runCommandAction(
        MinecraftServer server,
        HarnessConfig config,
        HarnessIdentity identity,
        ServerWorld world
    ) {
        String invocationId = System.getProperty("pd.agent.commandInvocationId", "i7-command");
        String countText = System.getProperty("pd.agent.commandCount", "1");
        int count;
        try {
            count = Integer.parseInt(countText);
        } catch (NumberFormatException ex) {
            return HarnessResult.command(config, identity, invocationId, false, false, false, null, false,
                "count is not an integer", world);
        }
        if (count < 1 || count > 5) {
            return HarnessResult.command(config, identity, invocationId, true, true, false, null, false,
                "count is outside the closed range", world);
        }
        boolean registered = server.getCommandManager().getDispatcher().getRoot().getChild("pdagent_i7") != null;
        if (!registered) {
            return HarnessResult.command(config, identity, invocationId, false, false, false, null, false,
                "I7 command was not registered", world);
        }
        String command = "pdagent_i7 mark " + count;
        try {
            int returnCode = server.getCommandManager().getDispatcher().execute(command, server.getCommandSource());
            BlockEntity blockEntity = ((WorldChunk) world.getChunk(new BlockPos(8, 64, 8))).getBlockEntity(
                new BlockPos(8, 64, 8), WorldChunk.CreationType.IMMEDIATE
            );
            boolean sideEffect = blockEntity instanceof HopperBlockEntity hopper
                && hopper.getStack(0).isOf(Items.DIAMOND)
                && hopper.getStack(0).getCount() == count;
            boolean success = returnCode == count && sideEffect;
            return HarnessResult.command(config, identity, invocationId, true, true, true, returnCode,
                success, success ? null : "command return code or inventory side effect mismatch", world);
        } catch (Exception ex) {
            return HarnessResult.command(config, identity, invocationId, true, false, false, null, false,
                ex.getClass().getSimpleName() + ": " + ex.getMessage(), world);
        }
    }

    private static HarnessResult runRecipeMatchObservation(
        MinecraftServer server,
        HarnessConfig config,
        HarnessIdentity identity,
        ServerWorld world
    ) {
        Identifier recipeId = parseIdentifier(config.observationRecipeId());
        RegistryKey<net.minecraft.recipe.Recipe<?>> key = RegistryKey.of(RegistryKeys.RECIPE, recipeId);
        java.util.Optional<RecipeEntry<?>> entry = server.getRecipeManager().get(key);
        JsonObject expected = new JsonObject();
        expected.addProperty("recipe_id", recipeId.toString());
        expected.addProperty("input_item_id", config.observationInputItemId());
        expected.addProperty("input_count", config.observationInputCount());
        expected.addProperty("output_item_id", config.observationExpectedOutputItemId());
        expected.addProperty("output_count", config.observationExpectedOutputCount());
        JsonObject actual = new JsonObject();
        actual.addProperty("recipe_id", recipeId.toString());
        actual.addProperty("recipe_resolved", entry.isPresent());
        if (entry.isEmpty() || !(entry.get().value() instanceof CraftingRecipe recipe)) {
            return HarnessResult.recipeMatch(config, identity, expected, actual, "INVALID", "controlled crafting recipe was not resolved");
        }
        Item item = Registries.ITEM.get(parseIdentifier(config.observationInputItemId()));
        if (item == null) {
            return HarnessResult.recipeMatch(config, identity, expected, actual, "INVALID", "controlled input item was not resolved");
        }
        CraftingRecipeInput input = CraftingRecipeInput.create(1, 1,
            java.util.List.of(new ItemStack(item, config.observationInputCount())));
        boolean matched = recipe.matches(input, world);
        ItemStack output = matched ? recipe.craft(input, server.getRegistryManager()) : ItemStack.EMPTY;
        String outputId = output.isEmpty() ? "minecraft:air" : String.valueOf(Registries.ITEM.getId(output.getItem()));
        actual.addProperty("matched", matched);
        actual.addProperty("output_item_id", outputId);
        actual.addProperty("output_count", output.isEmpty() ? 0 : output.getCount());
        boolean pass = matched && config.observationExpectedOutputItemId().equals(outputId)
            && config.observationExpectedOutputCount() == output.getCount();
        return HarnessResult.recipeMatch(config, identity, expected, actual, pass ? "PASS" : "FAIL",
            pass ? "real RecipeManager recipe match observed" : "recipe match or output mismatch");
    }

    private static HarnessResult runRecipeLoadedObservation(
        MinecraftServer server,
        HarnessConfig config,
        HarnessIdentity identity
    ) {
        Identifier recipeId = parseIdentifier(config.observationRecipeId());
        RegistryKey<net.minecraft.recipe.Recipe<?>> key = RegistryKey.of(RegistryKeys.RECIPE, recipeId);
        boolean loaded = server.getRecipeManager().get(key).isPresent();
        JsonObject expected = new JsonObject();
        expected.addProperty("recipe_id", recipeId.toString());
        expected.addProperty("loaded", true);
        JsonObject actual = new JsonObject();
        actual.addProperty("recipe_id", recipeId.toString());
        actual.addProperty("loaded", loaded);
        HarnessResult result = HarnessResult.recipeLoaded(
            config, identity, expected, actual, loaded ? "PASS" : "FAIL",
            loaded ? "recipe was loaded by RecipeManager" : "recipe was not loaded by RecipeManager"
        );
        return result;
    }

    private static HarnessResult runLootResultObservation(
        MinecraftServer server,
        HarnessConfig config,
        HarnessIdentity identity,
        ServerWorld world
    ) {
        Identifier tableId = parseIdentifier(config.observationLootTableId());
        RegistryKey<LootTable> key = RegistryKey.of(RegistryKeys.LOOT_TABLE, tableId);
        java.util.Optional<RegistryEntry.Reference<LootTable>> entry = server.getReloadableRegistries()
            .createRegistryLookup().getOrThrow(RegistryKeys.LOOT_TABLE).getOptional(key);
        JsonObject expected = new JsonObject();
        expected.addProperty("loot_table_id", tableId.toString());
        expected.addProperty("context_profile", config.observationLootContextProfile());
        expected.addProperty("seed", config.observationLootSeed());
        JsonObject expectedItem = new JsonObject();
        expectedItem.addProperty("item_id", config.observationLootExpectedItemId());
        expectedItem.addProperty("count", config.observationLootExpectedCount());
        expected.add("expected_item", expectedItem);
        JsonObject actual = new JsonObject();
        actual.addProperty("loot_table_id", tableId.toString());
        actual.addProperty("table_resolved", entry.isPresent());
        actual.addProperty("context_profile", config.observationLootContextProfile());
        actual.addProperty("seed", config.observationLootSeed());
        if (entry.isEmpty()) {
            return HarnessResult.lootResult(config, identity, expected, actual, "INVALID", "controlled loot table was not resolved");
        }
        LootWorldContext context = new LootWorldContext.Builder(world)
            .add(LootContextParameters.ORIGIN, Vec3d.ZERO)
            .add(LootContextParameters.THIS_ENTITY, null)
            .add(LootContextParameters.ATTACKING_ENTITY, null)
            .add(LootContextParameters.DIRECT_ATTACKING_ENTITY, null)
            .add(LootContextParameters.LAST_DAMAGE_PLAYER, null)
            .add(LootContextParameters.BLOCK_ENTITY, null)
            .add(LootContextParameters.BLOCK_STATE, null)
            .add(LootContextParameters.TOOL, null)
            .add(LootContextParameters.EXPLOSION_RADIUS, null)
            .add(LootContextParameters.DAMAGE_SOURCE, null)
            .build(LootTable.GENERIC);
        java.util.List<ItemStack> generated = entry.get().value().generateLoot(context, config.observationLootSeed());
        com.google.gson.JsonArray generatedJson = new com.google.gson.JsonArray();
        for (ItemStack stack : generated) {
            JsonObject itemJson = new JsonObject();
            itemJson.addProperty("item_id", String.valueOf(Registries.ITEM.getId(stack.getItem())));
            itemJson.addProperty("count", stack.getCount());
            generatedJson.add(itemJson);
        }
        actual.add("generated_items", generatedJson);
        boolean pass = generated.size() == 1
            && config.observationLootExpectedItemId().equals(generated.get(0).isEmpty() ? "minecraft:air" : String.valueOf(Registries.ITEM.getId(generated.get(0).getItem())))
            && generated.get(0).getCount() == config.observationLootExpectedCount();
        return HarnessResult.lootResult(config, identity, expected, actual, pass ? "PASS" : "FAIL",
            pass ? "deterministic loot result observed" : "generated loot result mismatch");
    }

    private static HarnessResult runTagMembershipObservation(
        MinecraftServer server,
        HarnessConfig config,
        HarnessIdentity identity
    ) {
        server.reloadResources(server.getDataPackManager().getEnabledIds()).join();
        Identifier tagId = parseIdentifier(config.observationTagId());
        Identifier memberId = parseIdentifier(config.observationMemberId());
        TagKey<Item> tagKey = TagKey.of(RegistryKeys.ITEM, tagId);
        RegistryWrapper.Impl<Item> itemLookup = server.getReloadableRegistries()
            .createRegistryLookup()
            .getOrThrow(RegistryKeys.ITEM);
        java.util.Optional<RegistryEntryList.Named<Item>> tag = itemLookup.getOptional(tagKey);
        java.util.Optional<RegistryEntry.Reference<Item>> member = Registries.ITEM.getEntry(memberId);
        JsonObject expected = new JsonObject();
        expected.addProperty("registry_kind", config.observationRegistryKind());
        expected.addProperty("tag_id", tagId.toString());
        expected.addProperty("member_id", memberId.toString());
        expected.addProperty("expected_membership", config.observationExpectedMembership());
        JsonObject actual = new JsonObject();
        actual.addProperty("registry_kind", "item");
        actual.addProperty("tag_id", tagId.toString());
        actual.addProperty("member_id", memberId.toString());
        actual.addProperty("tag_resolved", tag.isPresent());
        actual.addProperty("member_resolved", member.isPresent());
        if (tag.isEmpty()) {
            actual.addProperty("is_member", false);
            return HarnessResult.tagMembershipError(
                config, identity, expected, actual, "INVALID", "controlled tag was not resolved"
            );
        }
        if (member.isEmpty()) {
            actual.addProperty("is_member", false);
            return HarnessResult.tagMembershipError(
                config, identity, expected, actual, "INVALID", "controlled member was not resolved"
            );
        }
        boolean isMember = tag.get().contains(member.get());
        actual.addProperty("is_member", isMember);
        boolean pass = isMember == config.observationExpectedMembership();
        return HarnessResult.tagMembership(
            config, identity, expected, actual, pass,
            pass ? "runtime item tag membership observed" : "tag membership did not match expectation"
        );
    }

    private static HarnessResult runBlockEntityObservation(
        HarnessConfig config,
        HarnessIdentity identity,
        ServerWorld world
    ) {
        world.getChunk(CONTROLLED_POS);
        world.setBlockState(CONTROLLED_POS, Blocks.HOPPER.getDefaultState(), Block.NOTIFY_ALL);
        BlockEntity blockEntity = ((WorldChunk) world.getChunk(CONTROLLED_POS)).getBlockEntity(
            CONTROLLED_POS,
            WorldChunk.CreationType.IMMEDIATE
        );
        if (!(blockEntity instanceof HopperBlockEntity hopper)) {
            return HarnessResult.blockEntity(config, identity, new JsonObject(), new JsonObject(), false,
                "controlled hopper BlockEntity was not present");
        }
        String typeId = String.valueOf(Registries.BLOCK_ENTITY_TYPE.getId(hopper.getType()));
        String blockId = String.valueOf(Registries.BLOCK.getId(world.getBlockState(CONTROLLED_POS).getBlock()));
        String facingBefore = world.getBlockState(CONTROLLED_POS).get(HopperBlock.FACING).asString();
        boolean enabledBefore = world.getBlockState(CONTROLLED_POS).get(HopperBlock.ENABLED);
        boolean enabledAfter = config.observationMutation() ? false : enabledBefore;
        if (config.observationMutation()) {
            world.setBlockState(
                CONTROLLED_POS,
                world.getBlockState(CONTROLLED_POS).with(HopperBlock.ENABLED, false),
                Block.NOTIFY_ALL
            );
        }
        BlockState afterState = world.getBlockState(CONTROLLED_POS);
        JsonObject expected = new JsonObject();
        expected.addProperty("block_entity_type", config.observationBlockEntityId());
        expected.addProperty("block_id", "minecraft:hopper");
        expected.addProperty("enabled", enabledAfter);
        JsonObject actual = new JsonObject();
        actual.addProperty("present", true);
        actual.addProperty("block_entity_type", typeId);
        actual.addProperty("block_id", blockId);
        actual.addProperty("facing_before", facingBefore);
        actual.addProperty("enabled_before", enabledBefore);
        actual.addProperty("enabled_after", afterState.get(HopperBlock.ENABLED));
        boolean pass = typeId.equals(config.observationBlockEntityId())
            && "minecraft:hopper".equals(blockId)
            && afterState.get(HopperBlock.ENABLED) == enabledAfter;
        return HarnessResult.blockEntity(
            config, identity, expected, actual, pass,
            pass ? "controlled HopperBlockEntity state observed" : "BlockEntity type or state mismatch"
        );
    }

    private static HarnessResult runInventoryObservation(
        HarnessConfig config,
        HarnessIdentity identity,
        ServerWorld world
    ) {
        world.getChunk(CONTROLLED_POS);
        world.setBlockState(CONTROLLED_POS, Blocks.HOPPER.getDefaultState(), Block.NOTIFY_ALL);
        BlockEntity blockEntity = ((WorldChunk) world.getChunk(CONTROLLED_POS)).getBlockEntity(
            CONTROLLED_POS,
            WorldChunk.CreationType.IMMEDIATE
        );
        if (!(blockEntity instanceof Inventory inventory)) {
            return HarnessResult.inventory(config, identity, new JsonObject(), new JsonObject(), false,
                "controlled hopper inventory was not present");
        }
        ItemStack before = inventory.getStack(config.observationSlot());
        boolean eventDrivenObservation = "i8_world_load_effect".equals(System.getProperty("pd.agent.eventProfile"));
        if (config.observationMutation() && !eventDrivenObservation) {
            inventory.setStack(config.observationSlot(), new ItemStack(Items.DIAMOND, config.observationCount()));
            inventory.markDirty();
        }
        ItemStack after = inventory.getStack(config.observationSlot());
        String itemId = after.isEmpty() ? "minecraft:air" : String.valueOf(Registries.ITEM.getId(after.getItem()));
        JsonObject expected = new JsonObject();
        expected.addProperty("inventory_present", true);
        expected.addProperty("size", 5);
        expected.addProperty("selected_slot", config.observationSlot());
        expected.addProperty("item_id", "minecraft:diamond");
        expected.addProperty("count", config.observationCount());
        JsonObject actual = new JsonObject();
        actual.addProperty("inventory_present", true);
        actual.addProperty("size", inventory.size());
        actual.addProperty("selected_slot", config.observationSlot());
        actual.addProperty("empty_before", before.isEmpty());
        actual.addProperty("item_id_after", itemId);
        actual.addProperty("count_after", after.isEmpty() ? 0 : after.getCount());
        actual.addProperty("world_load_callback_executed", HarnessSignals.worldLoadCallbackExecuted());
        boolean pass = inventory.size() == 5
            && "minecraft:diamond".equals(itemId)
            && after.getCount() == config.observationCount();
        if (eventDrivenObservation) {
            pass = pass && HarnessSignals.worldLoadCallbackExecuted();
        } else {
            pass = pass && before.isEmpty();
        }
        return HarnessResult.inventory(
            config, identity, expected, actual, pass,
            pass ? "controlled HopperBlockEntity inventory mutation observed" : "inventory state mismatch"
        );
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

    private static HarnessResult runBlockItemAssociationObservation(HarnessConfig config, HarnessIdentity identity) {
        Identifier itemId = parseIdentifier(config.observationAssociationItemId());
        Identifier blockId = parseIdentifier(config.observationAssociationBlockId());
        Item item = Registries.ITEM.get(itemId);
        boolean itemPresent = item != null;
        boolean isBlockItem = item instanceof BlockItem;
        Block associatedBlock = isBlockItem ? ((BlockItem) item).getBlock() : null;
        Identifier actualBlockId = associatedBlock == null ? null : Registries.BLOCK.getId(associatedBlock);
        boolean blockPresent = Registries.BLOCK.containsId(blockId);
        boolean associated = itemPresent && isBlockItem && blockPresent && blockId.equals(actualBlockId);
        return HarnessResult.blockItemAssociation(
            config,
            identity,
            itemPresent,
            isBlockItem,
            actualBlockId == null ? null : actualBlockId.toString(),
            associated,
            associated ? "BlockItem association observed" : "BlockItem association did not match expected block"
        );
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
