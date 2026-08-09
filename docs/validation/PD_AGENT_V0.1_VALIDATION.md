# PD Agent v0.1 Validation

Validacion externa reproducible.

Estado actual:

- L0-L10: aprobados
- L11: validado con Fabric Loom real
- PASS: declarado

## Runner

- Script: `scripts/validation/validate_v0_1.py`
- Fixture principal: `tests/fixtures/l11_fabric_fixture`

## Fixture

- Fabric Loom: `1.13.3`
- Minecraft: `1.21.11`
- Fabric Loader: `0.19.3`
- Mappings: `1.21.11+build.6`
- Fabric API: no necesaria
- Gradle Wrapper: `8.14.3`
- Java: `21`
- Artifact: `build/libs/pd-agent-l11-fixture.jar`

## Resultados

- Baseline Fabric build: `PASS`
- Fake provider + real Gradle: `PASS`
- Repair: `PASS`
- Security: `PASS`
- Negative artifact: `PASS`
- Suite PD Agent: `PASS`
- OpenAI live: `NOT RUN`
- Minecraft runtime: `NOT VALIDATED`

## Run IDs

- Acceptance main: `64bfd3a1-2e36-468d-9941-4a82ce4685c7`
- Repair: `39d77ea8-34f6-4a01-9608-ef16a6e40a80`
- Security: `5b944be2-0401-4594-ad09-37d057bb1491`

## Evidencia

- Directorio de evidencia: `%TEMP%\pd-agent-v0.1-validation`
- Archivos clave:
  - `summary.json`
  - `summary.md`
  - `baseline-build.json`
  - `pytest-suite.json`
  - `acceptance-main/evaluation.json`
  - `repair/evaluation.json`
  - `security/evaluation.json`
  - `negative-artifact/evaluation.json`

## Nota

PASS aqui solo cubre build, artefacto, trazabilidad y validacion externa del harness. Minecraft runtime sigue fuera de v0.1.
