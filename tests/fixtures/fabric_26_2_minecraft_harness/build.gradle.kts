plugins {
    id("net.fabricmc.fabric-loom") version "1.17-SNAPSHOT"
}

repositories {
    mavenCentral()
    maven("https://maven.fabricmc.net/")
}

dependencies {
    minecraft("com.mojang:minecraft:${property("minecraft_version")}")
    modImplementation("net.fabricmc:fabric-loader:${property("loader_version")}")
    modImplementation("net.fabricmc.fabric-api:fabric-api:${property("fabric_api_version")}")
    modRuntimeOnly("net.fabricmc.fabric-api:fabric-api:${property("fabric_api_version")}")
}

sourceSets {
    main {
        java.srcDir("../l11_minecraft_harness/src/main/java")
        resources.srcDir("../l11_minecraft_harness/src/main/resources/data")
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
