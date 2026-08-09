# PD Agent v0.1.1 - Implementation Plan

**Estado:** Auditoria previa  
**Base:** `b96dae19524f8a520292702e3d8e880f39a72bfd`

## Lote A - Configuracion y secretos

Archivos previstos:

- `src/pd_agent/config.py`
- `src/pd_agent/cli.py`
- `src/pd_agent/bootstrap.py`
- `src/pd_agent/reporting/store.py`

Objetivo:

- leer BYOK/entorno real desde CLI;
- propagar secretos a redaccion de persistencia;
- fijar `store=false` en el provider.

Tests reutilizables:

- `tests/unit/test_l0_foundation.py`
- `tests/unit/test_l2_reporting.py`
- `tests/unit/test_l10_cli.py`
- `tests/unit/test_l8_openai_provider.py`

## Lote B - Responses continuation

Archivos previstos:

- `src/pd_agent/runtime/engine.py`
- `src/pd_agent/providers/openai_provider.py`
- tests de runtime/provider.

Objetivo:

- continuar tool loop con `function_call_output` / `call_id`;
- conservar core provider-neutral.

## Lote C - Harness live E2E

Archivos previstos:

- `scripts/validation/validate_v0_1.py`
- `docs/validation/PD_AGENT_V0.1.1_VALIDATION.md`
- fixtures de prueba si hacen falta.

Objetivo:

- demostrar runtime real + OpenAI real + tools + build + JAR + report.

## Lote D - Regresion y cierre

Objetivo:

- suite de regresion;
- validacion final;
- docs cerradas.
