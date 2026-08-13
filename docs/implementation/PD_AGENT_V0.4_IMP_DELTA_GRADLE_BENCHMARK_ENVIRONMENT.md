# PD Agent v0.4 — IMP Delta: Reproducible Gradle Benchmark Environment

**Status:** PROPOSED  
**Depends on:** RFC Delta — Reproducible Gradle Benchmark Environment  
**Milestone:** PD Agent v0.4 — Benchmark Foundation  
**Baseline:** `ae4702b6f5a1d3ac731facb8e1661166592af94a`

## 1. Objetivo

Implementar el mínimo entorno Gradle reproducible necesario para reanudar la smoke B001 OFF/ON.

No ejecutar las 18 runs.

## 2. Lote A — inventario exacto del seed

Antes de código:

1. usar un home controlado;
2. producir un build offline conocido de B001/L11;
3. identificar el material efectivamente requerido;
4. medir tamaño;
5. generar propuesta de manifest;
6. confirmar que no se necesita copiar `~/.gradle` completo.

Si el sandbox no permite derivar este inventario, preparar comando externo reproducible y usar esa evidencia antes de continuar.

## 3. Lote B — contratos

Añadir contratos mínimos benchmark-local para seed identity/manifest, estado `MISSING/READY/INVALID`, environment materializado y environment mapping para subprocess.

No incluir blobs/caches pesados en Git sin decisión explícita.

## 4. Lote C — GradleBuildRunner environment

Extender `GradleBuildRunner` de forma genérica para aceptar environment overrides explícitos:

- merge seguro sobre entorno base;
- `GRADLE_USER_HOME` inyectable;
- sin hardcode Fabric/Loom;
- tests de subprocess environment;
- comportamiento sin override preservado.

## 5. Lote D — benchmark Gradle environment

Crear helper benchmark-local responsable de:

- localizar seed;
- validar manifest/hashes;
- materializar home aislado bajo execution root;
- garantizar writability;
- devolver environment overrides;
- registrar metadata/evidence.

No usar `~/.gradle` durante la run.

## 6. Lote E — integración

`run_v0_4.py` / runner prepara el environment antes de smoke/matriz.

El mismo environment se comparte secuencialmente entre OFF y ON de una execution.

`BenchmarkExecutor` usa un `GradleBuildRunner` configurado con el environment aislado.
Si el `MinecraftTestRunner`/harness ejecuta Gradle para validar el artifact, debe
recibir el mismo `GRADLE_USER_HOME` aislado de esa execution.

Auditar Minecraft/harness si también lanza Gradle.

## 7. Lote F — offline

La build benchmark usa offline cuando seed está READY.

No permitir fallback silencioso a red.

Si `GradleBuildRunner` necesita argumentos cerrados adicionales, añadir solo soporte explícito/allowlisted.

## 8. Lote G — failure classification

Seed ausente/inválido o build offline que no resuelve artifacts se clasifica como infraestructura, nunca como FAIL funcional.

Persistir evidencia exacta.

## 9. Tests

1. environment override llega a subprocess.
2. home aislado writable.
3. manifest válido materializa seed.
4. hash incorrecto -> bloqueado.
5. seed missing -> error explícito.
6. no dependencia directa de `~/.gradle`.
7. fixture identity no incluye caches.
8. OFF/ON comparten seed id.
9. preparación idempotente/reproducible.
10. no se copian dirs no declarados.
11. `--offline` activo.
12. tests existentes de GradleBuildRunner siguen PASS.

## 10. Validación real

Con seed preparado:

- `gradlew.bat --version` con home aislado -> PASS.
- `gradlew.bat build --offline` B001 -> PASS.
- JAR generado.
- segundo environment materializado desde mismo seed -> PASS.

## 11. Evidence

Persistir seed manifest/hash, materialization root, Gradle home identity, `offline=true`, logs y artifact result.

## 12. Git

Commits por hitos coherentes. No versionar caches Gradle o blobs grandes sin autorización.

## 13. Gate

Solo después de suite PASS, build offline real PASS, environment repeatable PASS, `HEAD == origin/main` y tree limpio, volver a smoke B001 OFF/ON.

No lanzar las 18 runs.
