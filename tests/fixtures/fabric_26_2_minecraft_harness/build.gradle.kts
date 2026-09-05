import java.io.File
import net.fabricmc.loom.task.prod.ServerProductionRunTask

plugins {
    id("net.fabricmc.fabric-loom") version "1.17-SNAPSHOT"
}

repositories {
    mavenCentral()
    maven("https://maven.fabricmc.net/")
}

dependencies {
    minecraft("com.mojang:minecraft:${property("minecraft_version")}")
    implementation("net.fabricmc:fabric-loader:${property("loader_version")}")
    implementation("net.fabricmc.fabric-api:fabric-api:${property("fabric_api_version")}")
}

sourceSets {
    main {
        java.srcDir("src/main/java")
    }
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(25))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(25)
}

tasks.register<ServerProductionRunTask>("productionServerRun") {
    dependsOn(tasks.named("jar"))
    installerVersion = "1.1.0"
    val targetJar = file(providers.gradleProperty("pd.agent.targetJar").get())
    val harnessJar = layout.buildDirectory.file("libs/${project.name}.jar")
    val runDir = file(providers.gradleProperty("pd.agent.runDir").get())
    val runtimeModJars = providers.gradleProperty("pd.agent.runtimeModJars").orNull
        ?.split(File.pathSeparatorChar)
        ?.filter { it.isNotBlank() }
        ?.map(::file)
        ?: emptyList()
    val fabricRuntimeMods = configurations.named("runtimeClasspath").map { classpath ->
        classpath.filter { it.name.startsWith("fabric-") }
    }

    mods.from(files(targetJar, harnessJar, *runtimeModJars.toTypedArray(), fabricRuntimeMods))
    this.runDir = runDir
    doFirst {
        runDir.mkdirs()
        runDir.resolve("eula.txt").writeText("eula=true\n")
    }
    programArgs.add("--nogui")
    providers.gradleProperty("pd.agent.targetModId").orNull?.let { jvmArgs.add("-Dpd.agent.targetModId=$it") }
    providers.gradleProperty("pd.agent.targetSha256").orNull?.let { jvmArgs.add("-Dpd.agent.targetSha256=$it") }
    providers.gradleProperty("pd.agent.targetEntrypointClass").orNull?.let { jvmArgs.add("-Dpd.agent.targetEntrypointClass=$it") }
    providers.gradleProperty("pd.agent.testId").orNull?.let { jvmArgs.add("-Dpd.agent.testId=$it") }
    providers.gradleProperty("pd.agent.observationType").orNull?.let { jvmArgs.add("-Dpd.agent.observationType=$it") }
    providers.gradleProperty("pd.agent.observationRegistryKind").orNull?.let { jvmArgs.add("-Dpd.agent.observationRegistryKind=$it") }
    providers.gradleProperty("pd.agent.observationIdentifier").orNull?.let { jvmArgs.add("-Dpd.agent.observationIdentifier=$it") }
    providers.gradleProperty("pd.agent.observationRecipeId").orNull?.let { jvmArgs.add("-Dpd.agent.observationRecipeId=$it") }
    providers.gradleProperty("pd.agent.observationAssociationItemId").orNull?.let { jvmArgs.add("-Dpd.agent.observationAssociationItemId=$it") }
    providers.gradleProperty("pd.agent.observationAssociationBlockId").orNull?.let { jvmArgs.add("-Dpd.agent.observationAssociationBlockId=$it") }
    jvmArgs.add("-Dpd.agent.resultPath=${providers.gradleProperty("pd.agent.resultPath").get()}")
    javaLauncher = javaToolchains.launcherFor { languageVersion.set(JavaLanguageVersion.of(25)) }
}
