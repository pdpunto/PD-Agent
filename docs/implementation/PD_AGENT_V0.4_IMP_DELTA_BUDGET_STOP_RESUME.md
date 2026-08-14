# PD Agent v0.4 --- IMP Delta: Budget Stop + Cross-Session Resume

**Status:** Implementation Plan  
**Version:** 1.0  
**Milestone:** PD Agent v0.4 --- Benchmark Foundation  
**Depends on:** RFC Delta Budget Stop + Cross-Session Resume  
**Audited baseline before planning:** `0b13c54cebca5b9b4fbc958232e590aa5369a000`

## 1. Objetivo

Implementar el contrato de budget stop y resume cross-session con el minimo cambio posible.

No se autoriza implementacion inmediata fuera del plan.

No hace falta un design delta adicional.

## 2. Principios de implementacion

1. Reutilizar el runner, scheduler, manifest y schedule existentes.
2. No crear un scheduler paralelo.
3. No introducir background service.
4. No tocar dataset, acceptance, provider/model, Brain ni max_agent_steps.
5. No confundir pause de budget con fail del agente.
6. No duplicar usage, evidence ni attempts.
7. La autoridad de pause/continue vive en `BenchmarkExecutionRunner`.
8. `BenchmarkRequestPacer` conserva pacing y contador logico, pero no decide pause.

## 3. Archivos previsibles

### Codigo

Los archivos mas probables son:

- `scripts/benchmark/run_v0_4.py`
- `src/pd_agent/benchmark/runner.py`
- `src/pd_agent/benchmark/models.py`
- `src/pd_agent/benchmark/pacing.py` solo si hace falta exponer un snapshot o helper extra
- `src/pd_agent/benchmark/scheduler.py` solo si hace falta leer estado nuevo sin cambiar order

### Tests

Los tests existentes a reforzar o ampliar son:

- `tests/unit/test_benchmark_runner.py`
- `tests/unit/test_benchmark_run_v0_4.py`
- `tests/unit/test_benchmark_scheduler.py`
- `tests/unit/test_benchmark_models.py`
- `tests/unit/test_benchmark_pacing.py`
- `tests/unit/test_benchmark_collector.py` si hace falta validar evidencia nueva

Si el crecimiento del diff lo justifica, se puede crear un test especifico de resume, pero solo si mejora claridad.

## 4. Lote A --- Models / status / evidence

### Objetivo

Persistir el nuevo contrato sin romper compatibilidad innecesaria.

### Implementar

- un estado de budget pause para el nivel de ejecucion de batch o envelope equivalente;
- metadata de budget configurado;
- metadata de budget usado;
- metadata de budget restante;
- metadata de attempt reservation;
- metadata de pause reason;
- metadata de session/resume identity;
- serializacion round-trip de los nuevos campos.

### Recomendacion de modelo minimo

No overloadar `BenchmarkRun` con un synthetic fail.

Lo mas limpio es introducir un estado de ejecucion de batch o un envelope equivalente para representar `BUDGET_PAUSED`.

La evidencia de contador logico debe seguir viniendo de `RunState`, con `MODEL_CALLED` como cross-check en el collector, sin doble conteo.

### Tests

1. round-trip de nuevos campos;
2. compatibilidad con payloads viejos sin los campos nuevos;
3. `BUDGET_PAUSED` no se confunde con `BLOCKED` ni `INVALID`;
4. el schedule y el manifest siguen serializando igual cuando no hay pausa.

### Aceptacion

La metadata de budget puede persistirse y reconstruirse sin perder compatibilidad con los payloads actuales.

## 5. Lote B --- Budget stop

### Objetivo

Parar la ejecucion antes de iniciar un nuevo attempt si el presupuesto logico restante es insuficiente.

### Implementar

En `BenchmarkExecutionRunner`:

1. leer el budget logico configurado;
2. calcular `remaining_logical_budget`;
3. antes de cada attempt, comprobar `remaining_logical_budget >= max_agent_steps`;
4. si no se cumple, persistir estado `BUDGET_PAUSED`;
5. cerrar limpiamente sin ejecutar `executor.execute(...)`;
6. no consumir attempt, replacement ni valid repetition;
7. persistir schedule y estado de ejecucion.

### Regla esencial

El check debe ocurrir antes de llamar al executor.

### Tests

- attempt starts when sufficient budget;
- attempt does not start when remaining < reservation;
- pause persists;
- pause consumes no attempt;
- pause consumes no replacement;
- schedule remains identical after pause.

### Aceptacion

Una ejecucion con budget insuficiente termina en pausa limpia sin contaminar el schedule.

## 6. Lote C --- Resume loading

### Objetivo

Reanudar una ejecucion existente usando su batch directory y su schedule persistido.

### Implementar

1. `--resume <execution_dir>` en `scripts/benchmark/run_v0_4.py`;
2. cargar `manifest.json`;
3. cargar `schedule.json`;
4. no crear un schedule nuevo;
5. revalidar drift;
6. reconstruir el estado minimo necesario;
7. continuar el siguiente pending item exacto.

### Drift checks obligatorios

Comparar y rechazar si cambian:

- dataset id/version;
- task id/version;
- fixture identity;
- config id/hash;
- provider/model;
- `brain_enabled`;
- `execution_limits`;
- `target_valid_repetitions`;
- `max_attempts_per_cell`;
- `scheduling_seed`;
- canonical schedule;
- Gradle seed identity / manifest;
- baseline/commit si la politica lo exige.

### Tests

- resume continues exact next pending item;
- dataset drift rejected;
- config hash drift rejected;
- fixture drift rejected;
- provider/model drift rejected;
- Gradle seed drift rejected;
- schedule drift rejected;
- completed execution + resume is safe no-op.

### Aceptacion

Un batch pausado puede reanudarse sin regenerar order ni cambiar identidades.

## 7. Lote D --- Idempotence / replacements

### Objetivo

Hacer que resume y replacements no dupliquen informacion.

### Implementar

- no repetir completed attempts;
- conservar replacement history;
- no duplicar usage;
- no duplicar evidence;
- no reutilizar run IDs completados;
- mantener el orden canonico entre sesiones;
- asegurar que una replacement ya persistida sigue visible en resume.

### Tests

- completed attempts not repeated;
- usage not double-counted;
- replacements preserved;
- new session budget permits continuation;
- canonical OFF/ON order preserved across sessions;
- worst-case 30 attempts can span sessions without changing identities/order.

### Aceptacion

El estado persistido permite continuar sin doble conteo ni reordenamiento.

## 8. Lote E --- Tests y regresion

### Objetivo

Validar la implementacion completa sin API live.

### Ejecutar

- `python -m compileall src tests`
- tests focalizados de benchmark runner, scheduler, models, pacing y run_v0_4
- suite completa

### Casos minimos

1. budget stop antes del attempt;
2. pause limpia;
3. resume desde el siguiente pending exacto;
4. schedule estable;
5. replacement estable;
6. idempotencia;
7. drift rejection;
8. completed no-op.

### Aceptacion

Todo PASS y sin cambios en dataset, acceptance o Brain.

## 9. Semantica de implementacion por archivo

### `scripts/benchmark/run_v0_4.py`

- parsear `--resume`;
- cargar batch existente si se usa resume;
- seguir validando provider/model y pacing;
- no inventar nuevo schedule en modo resume.

### `src/pd_agent/benchmark/runner.py`

- decidir pause/continue;
- persistir state y schedule;
- reanudar desde el siguiente pending exacto;
- rechazar drift.

### `src/pd_agent/benchmark/models.py`

- introducir el estado/envelope necesario para `BUDGET_PAUSED`;
- mantener compatibilidad JSON con payloads actuales.

### `src/pd_agent/benchmark/pacing.py`

- conservar pacing monotono;
- conservar logical request accounting;
- exponer snapshot si el runner lo necesita para evidence.

### `src/pd_agent/benchmark/scheduler.py`

- no cambiar order policy;
- solo leer/usar el schedule persistido.

## 10. Contratos que no deben cambiar

- `PD_AGENT_BENCHMARK_DATASET_V0.4_2`
- B001/B002/B003
- Brain OFF/ON
- 3 valid repetitions
- acceptance
- `max_agent_steps = 25`
- provider/model
- pacing minimo de benchmark
- `RunState` como persistencia primaria del contador logico
- `MODEL_CALLED` como cross-check

## 11. Riesgos a vigilar

1. usar `BLOCKED` para una pausa limpia;
2. regenerar schedule al reanudar;
3. duplicar attempts o usage;
4. perder replacement history;
5. permitir drift silencioso;
6. mezclar pause de budget con failure del agente;
7. introducir un estado que rompa compatibilidad con payloads anteriores sin migracion.

## 12. Gate final de este lote

Este IMP solo autoriza implementacion despues de que:

- RFC e IMP queden aprobados;
- no exista contradiccion material con el repo real;
- el working tree siga limpio salvo los docs aprobados;
- el delta de budget stop/resume pueda implementarse sin otro decision point arquitectonico.
