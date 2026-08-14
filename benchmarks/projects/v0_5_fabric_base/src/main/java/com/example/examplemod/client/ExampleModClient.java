package com.example.examplemod.client;

import com.example.examplemod.ExampleMod;
import net.fabricmc.api.ClientModInitializer;

public final class ExampleModClient implements ClientModInitializer {
    @Override
    public void onInitializeClient() {
        ExampleMod.LOGGER.info("Example Mod client initialized.");
    }
}
