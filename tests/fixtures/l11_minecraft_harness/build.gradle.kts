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
    compileOnly(files("../l11_fabric_fixture/build/classes/java/main"))
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

    mods.from(files(targetJar, harnessJar))
    this.runDir = runDir
    doFirst {
        runDir.mkdirs()
        runDir.resolve("eula.txt").writeText("eula=true\n", Charsets.UTF_8)
        runDir.resolve("server.properties").writeText(
            "motd=PD Agent\n",
            Charsets.UTF_8,
        )
    }
    programArgs.add("--nogui")
    jvmArgs.add("-Dpd.agent.targetModId=${providers.gradleProperty("pd.agent.targetModId").get()}")
    jvmArgs.add("-Dpd.agent.targetSha256=${providers.gradleProperty("pd.agent.targetSha256").get()}")
    jvmArgs.add("-Dpd.agent.testId=${providers.gradleProperty("pd.agent.testId").get()}")
    jvmArgs.add("-Dpd.agent.resultPath=${providers.gradleProperty("pd.agent.resultPath").get()}")
    jvmArgs.add("-Dpd.agent.resultMode=${providers.gradleProperty("pd.agent.resultMode").orElse("pass").get()}")
    jvmArgs.add("-Dpd.agent.expectedBlockStateId=${providers.gradleProperty("pd.agent.expectedBlockStateId").orElse("diamond_block").get()}")
    jvmArgs.add("-Dpd.agent.expectNeighborUpdate=${providers.gradleProperty("pd.agent.expectNeighborUpdate").orElse("false").get()}")
    jvmArgs.add("-Dpd.agent.hangMillis=${providers.gradleProperty("pd.agent.hangMillis").orElse("600000").get()}")
    javaLauncher = javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}
