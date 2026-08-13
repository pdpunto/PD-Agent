# PD Agent v0.4 — RFC Delta: Reproducible Gradle Benchmark Environment

**Status:** PROPOSED  
**Milestone:** PD Agent v0.4 — Benchmark Foundation  
**Baseline audited:** `ae4702b6f5a1d3ac731facb8e1661166592af94a`

## 1. Motivo

La validación live de B001 ya demostró progreso operativo del Fabric Agent, pero el benchmark queda bloqueado por el entorno Gradle.

El fixture usa Gradle Wrapper 8.14.3 y Fabric Loom 1.13.3. El wrapper almacena su distribución bajo `GRADLE_USER_HOME`, y `GradleBuildRunner` hereda el entorno del proceso sin imponer un home aislado. Como consecuencia, las runs pueden depender del estado, locks y permisos del `~/.gradle` del host.

El benchmark debe disponer de un `GRADLE_USER_HOME` writable, aislado y reproducible, preparado antes de ejecutar el wrapper.

## 2. Objetivos

1. Aislar Gradle por benchmark execution.
2. Evitar locks y permisos del `~/.gradle` mutable del usuario.
3. Permitir `gradlew.bat --version` y `gradlew.bat build --offline` una vez preparado el entorno.
4. Reutilizar un seed determinista sin copiar caches arbitrarias o gigabytes completos.
5. Clasificar explícitamente como infraestructura cualquier seed incompleto.
6. Mantener dataset, fixture identity, acceptance y seguridad sin cambios.

## 3. No objetivos

No implementar mirror Maven, servidor de artifacts, cambio de versiones Fabric/Gradle, modificación del Fabric Agent, relajación de `SecurePathResolver`, dependencia runtime directa de `~/.gradle`, bootstrap online silencioso durante una benchmark run ni las 18 runs oficiales.

## 4. Arquitectura

Se introduce una responsabilidad benchmark-local: `Benchmark Gradle Environment`.

Flujo:

`BenchmarkExecutionRunner`
→ preparar execution root
→ `BenchmarkGradleEnvironment.prepare(...)`
→ obtener `isolated_gradle_user_home`
→ `BenchmarkExecutor`
→ `GradleBuildRunner` con environment explícito
→ wrapper/build offline.

La política Fabric/Loom/seed pertenece a la capa benchmark. `GradleBuildRunner` puede aceptar environment overrides genéricos, pero no debe conocer Fabric ni Loom.

## 5. Seed

El seed es un snapshot del material Gradle/Fabric necesario para el environment exacto del benchmark.

Debe identificarse por un descriptor canónico con al menos:

- Gradle `8.14.3`
- Minecraft `1.21.11`
- Fabric Loom `1.13.3`
- Fabric Loader `0.19.3`
- Yarn `1.21.11+build.6:v2`
- Java major `21`
- versión del algoritmo de seed.

El seed no forma parte de la fixture identity. Es environment identity y se registra en evidence.

## 6. Contenido del seed

No se fija una lista de paths Gradle ad hoc.

El seed MUST derivarse de un build offline conocido y verificado. El bootstrap:

1. prepara un home controlado;
2. resuelve las coordenadas exactas autorizadas;
3. valida que `--offline` funciona;
4. snapshottea únicamente el material requerido;
5. genera manifest con hashes y tamaños.

El manifest del seed es autoridad sobre su contenido.

No se copia el `~/.gradle` completo.

## 7. Estrategia de bootstrap

Estrategia recomendada: bootstrap online controlado una vez, fuera de la run oficial, y reutilización de un seed controlado por PD Agent.

Como mecanismo transitorio de desarrollo se puede importar material desde cache del host únicamente para construir el seed, nunca como dependencia directa de la run, y siempre verificando después el build offline.

## 8. Lifecycle

Estados conceptuales:

- `MISSING`
- `PREPARING`
- `READY`
- `INVALID`

`READY` exige manifest y hashes válidos, home materializado writable, wrapper version check PASS y build offline PASS.

Una run no auto-bootstrappea con red.

## 9. Aislamiento

Cada benchmark execution recibe su propio `GRADLE_USER_HOME`, por ejemplo:

`<execution_root>/environment/gradle-user-home`

Las runs de esa execution pueden compartirlo secuencialmente porque v0.4 no ejecuta en paralelo.

No se comparte con `~/.gradle`.
Si `MinecraftTestRunner` o el harness asociado lanzan Gradle, deben recibir el mismo
`GRADLE_USER_HOME` aislado de esa execution; no pueden caer en una política ambiental distinta.

## 10. Offline

Tras preparar el environment, el benchmark oficial MUST ejecutar Gradle en modo offline.

## 11. Fallos

Seed ausente, manifest/hash inválido, material faltante, wrapper que no arranca o build offline sin dependencias => infraestructura bloqueada, no FAIL funcional.

No se permite fallback silencioso a `~/.gradle` o red.

## 12. Seguridad

- El seed se materializa dentro de root controlado.
- No se escribe en `~/.gradle`.
- No se relaja `SecurePathResolver`.
- Los environment overrides son explícitos.
- El bootstrap no introduce secretos.
- Seed paths/hashes se registran como evidence.

## 13. Reproducibilidad e identity

Environment snapshot registra:

- seed id/version;
- seed manifest hash;
- Gradle/Java;
- Minecraft/Loom/Loader/Yarn;
- offline mode;
- isolated `GRADLE_USER_HOME`.

OFF y ON usan el mismo seed.

## 14. Propietario

Un helper benchmark-local (`BenchmarkGradleEnvironment` o equivalente) posee seed resolution, validation, materialization y environment mapping.

`BenchmarkExecutor` consume el environment.

`GradleBuildRunner` solo ejecuta Gradle con environment explícito.

## 15. Criterios de aceptación

1. B001 workspace `ProjectInspector = READY`.
2. isolated `GRADLE_USER_HOME` writable.
3. `gradlew.bat --version` PASS.
4. `gradlew.bat build --offline` PASS.
5. Loom resuelve sin `~/.gradle`.
6. JAR válido generado.
7. repetición con mismo seed PASS sin red.
8. seed corrupto/incompleto produce error de infraestructura.
9. fixture canónica no cambia.
10. security boundaries intactos.
11. suite completa PASS.
