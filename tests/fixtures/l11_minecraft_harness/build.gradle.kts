import java.io.File

import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.jvm.toolchain.JavaLanguageVersion

import net.fabricmc.loom.task.prod.ServerProductionRunTask

plugins {
    id("fabric-loom") version "1.13.3"
}

version = ""

repositories {
    mavenCentral()
    maven("https://maven.fabricmc.net/")
}

dependencies {
    minecraft("com.mojang:minecraft:${property("minecraft_version")}")
    mappings("net.fabricmc:yarn:${property("mappings_version")}:v2")
    modImplementation("net.fabricmc:fabric-loader:${property("loader_version")}")
    modImplementation("net.fabricmc.fabric-api:fabric-api:0.141.6+1.21.11")
    modRuntimeOnly("net.fabricmc.fabric-api:fabric-api:0.141.6+1.21.11")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(21)
}

tasks.jar {
    archiveBaseName.set("pd-agent-l11-harness")
    archiveVersion.set("")
}

tasks.register<ServerProductionRunTask>("productionServerRun") {
    dependsOn(tasks.named("jar"))
    installerVersion = "1.0.1"
    val targetJar = file(providers.gradleProperty("pd.agent.targetJar").get())
    val harnessJar = layout.buildDirectory.file("libs/pd-agent-l11-harness.jar")
    val runDir = file(providers.gradleProperty("pd.agent.runDir").get())
    val runtimeModJars = providers.gradleProperty("pd.agent.runtimeModJars").orNull
    val runtimeModJarFiles = runtimeModJars
        ?.split(File.pathSeparatorChar)
        ?.map { it.trim() }
        ?.filter { it.isNotEmpty() }
        ?.map { file(it) }
        ?: emptyList()
    val fabricApiModFiles = configurations.getByName("modRuntimeOnly").resolve()
        .filter { it.name.startsWith("fabric-") }

    mods.from(files(targetJar, harnessJar, *runtimeModJarFiles.toTypedArray(), *fabricApiModFiles.toTypedArray()))
    this.runDir = runDir
    doFirst {
        runDir.mkdirs()
        runDir.resolve("eula.txt").writeText("eula=true\n", Charsets.UTF_8)
        runDir.resolve("server.properties").writeText(
            "motd=PD Agent\n",
            Charsets.UTF_8,
        )
        val datapackRoot = runDir.resolve("world/datapacks/i4-controlled")
        datapackRoot.resolve("data/pdagentl11_harness/tags/item").mkdirs()
        datapackRoot.resolve("pack.mcmeta").writeText(
            "{\"pack\":{\"pack_format\":94,\"min_format\":94,\"max_format\":94,\"description\":\"PD Agent I4 controlled tag\"}}",
            Charsets.UTF_8,
        )
        datapackRoot.resolve("data/pdagentl11_harness/tags/item/i4_controlled_members.json").writeText(
            "{\"replace\":false,\"values\":[\"minecraft:diamond\",\"minecraft:gold_ingot\"]}",
            Charsets.UTF_8,
        )
        datapackRoot.resolve("data/pdagentl11_harness/recipe").mkdirs()
        datapackRoot.resolve("data/pdagentl11_harness/recipe/i5_marble_lantern.json").writeText(
            "{\"type\":\"minecraft:crafting_shaped\",\"pattern\":[\"A\"],\"key\":{\"A\":\"minecraft:diamond\"},\"result\":{\"id\":\"minecraft:gold_ingot\",\"count\":1}}",
            Charsets.UTF_8,
        )
        datapackRoot.resolve("data/pdagentl11_harness/loot_table").mkdirs()
        datapackRoot.resolve("data/pdagentl11_harness/loot_table/i6_fixed_drop.json").writeText(
            "{\"type\":\"minecraft:generic\",\"pools\":[{\"rolls\":1,\"entries\":[{\"type\":\"minecraft:item\",\"name\":\"minecraft:gold_ingot\"}]}]}",
            Charsets.UTF_8,
        )
    }
    programArgs.add("--nogui")
    jvmArgs.add("-Dpd.agent.targetModId=${providers.gradleProperty("pd.agent.targetModId").get()}")
    jvmArgs.add("-Dpd.agent.targetSha256=${providers.gradleProperty("pd.agent.targetSha256").get()}")
    jvmArgs.add("-Dpd.agent.targetEntrypointClass=${providers.gradleProperty("pd.agent.targetEntrypointClass").get()}")
    jvmArgs.add("-Dpd.agent.testId=${providers.gradleProperty("pd.agent.testId").get()}")
    jvmArgs.add("-Dpd.agent.observationType=${providers.gradleProperty("pd.agent.observationType").get()}")
    jvmArgs.add("-Dpd.agent.resultPath=${providers.gradleProperty("pd.agent.resultPath").get()}")
    jvmArgs.add("-Dpd.agent.resultMode=${providers.gradleProperty("pd.agent.resultMode").orElse("pass").get()}")
    jvmArgs.add("-Dpd.agent.expectedBlockStateId=${providers.gradleProperty("pd.agent.expectedBlockStateId").orElse("diamond_block").get()}")
    jvmArgs.add("-Dpd.agent.expectNeighborUpdate=${providers.gradleProperty("pd.agent.expectNeighborUpdate").orElse("false").get()}")
    jvmArgs.add("-Dpd.agent.hangMillis=${providers.gradleProperty("pd.agent.hangMillis").orElse("600000").get()}")
    providers.gradleProperty("pd.agent.observationRegistryKind").orNull?.let {
        jvmArgs.add("-Dpd.agent.observationRegistryKind=$it")
    }
    providers.gradleProperty("pd.agent.observationIdentifier").orNull?.let {
        jvmArgs.add("-Dpd.agent.observationIdentifier=$it")
    }
    providers.gradleProperty("pd.agent.observationComponentId").orNull?.let {
        jvmArgs.add("-Dpd.agent.observationComponentId=$it")
    }
    providers.gradleProperty("pd.agent.observationItemId").orNull?.let {
        jvmArgs.add("-Dpd.agent.observationItemId=$it")
    }
    jvmArgs.add("-Dpd.agent.observationRoundTrip=${providers.gradleProperty("pd.agent.observationRoundTrip").orElse("false").get()}")
    providers.gradleProperty("pd.agent.observationBlockEntityId").orNull?.let {
        jvmArgs.add("-Dpd.agent.observationBlockEntityId=$it")
    }
    providers.gradleProperty("pd.agent.observationTagId").orNull?.let {
        jvmArgs.add("-Dpd.agent.observationTagId=$it")
    }
    providers.gradleProperty("pd.agent.observationMemberId").orNull?.let {
        jvmArgs.add("-Dpd.agent.observationMemberId=$it")
    }
    jvmArgs.add("-Dpd.agent.observationExpectedMembership=${providers.gradleProperty("pd.agent.observationExpectedMembership").orElse("true").get()}")
    providers.gradleProperty("pd.agent.observationRecipeId").orNull?.let { jvmArgs.add("-Dpd.agent.observationRecipeId=$it") }
    providers.gradleProperty("pd.agent.observationInputItemId").orNull?.let { jvmArgs.add("-Dpd.agent.observationInputItemId=$it") }
    jvmArgs.add("-Dpd.agent.observationInputCount=${providers.gradleProperty("pd.agent.observationInputCount").orElse("1").get()}")
    providers.gradleProperty("pd.agent.observationExpectedOutputItemId").orNull?.let { jvmArgs.add("-Dpd.agent.observationExpectedOutputItemId=$it") }
    jvmArgs.add("-Dpd.agent.observationExpectedOutputCount=${providers.gradleProperty("pd.agent.observationExpectedOutputCount").orElse("1").get()}")
    providers.gradleProperty("pd.agent.observationLootTableId").orNull?.let { jvmArgs.add("-Dpd.agent.observationLootTableId=$it") }
    providers.gradleProperty("pd.agent.observationLootContextProfile").orNull?.let { jvmArgs.add("-Dpd.agent.observationLootContextProfile=$it") }
    jvmArgs.add("-Dpd.agent.observationLootSeed=${providers.gradleProperty("pd.agent.observationLootSeed").orElse("0").get()}")
    providers.gradleProperty("pd.agent.observationLootExpectedItemId").orNull?.let { jvmArgs.add("-Dpd.agent.observationLootExpectedItemId=$it") }
    jvmArgs.add("-Dpd.agent.observationLootExpectedCount=${providers.gradleProperty("pd.agent.observationLootExpectedCount").orElse("1").get()}")
    jvmArgs.add("-Dpd.agent.observationSlot=${providers.gradleProperty("pd.agent.observationSlot").orElse("0").get()}")
    jvmArgs.add("-Dpd.agent.observationCount=${providers.gradleProperty("pd.agent.observationCount").orElse("5").get()}")
    jvmArgs.add("-Dpd.agent.observationMutation=${providers.gradleProperty("pd.agent.observationMutation").orElse("true").get()}")
    providers.gradleProperty("pd.agent.persistencePhase").orNull?.let { jvmArgs.add("-Dpd.agent.persistencePhase=$it") }
    providers.gradleProperty("pd.agent.persistenceScenarioId").orNull?.let { jvmArgs.add("-Dpd.agent.persistenceScenarioId=$it") }
    providers.gradleProperty("pd.agent.persistenceWorldId").orNull?.let { jvmArgs.add("-Dpd.agent.persistenceWorldId=$it") }
    providers.gradleProperty("pd.agent.persistenceEvidencePath").orNull?.let { jvmArgs.add("-Dpd.agent.persistenceEvidencePath=$it") }
    providers.gradleProperty("pd.agent.commandProfile").orNull?.let { jvmArgs.add("-Dpd.agent.commandProfile=$it") }
    providers.gradleProperty("pd.agent.commandInvocationId").orNull?.let { jvmArgs.add("-Dpd.agent.commandInvocationId=$it") }
    providers.gradleProperty("pd.agent.commandCount").orNull?.let { jvmArgs.add("-Dpd.agent.commandCount=$it") }
    providers.gradleProperty("pd.agent.eventProfile").orNull?.let { jvmArgs.add("-Dpd.agent.eventProfile=$it") }
    javaLauncher = javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}
