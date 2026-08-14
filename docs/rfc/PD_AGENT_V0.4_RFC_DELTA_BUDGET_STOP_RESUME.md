# PD Agent v0.4 --- RFC Delta: Budget Stop + Cross-Session Resume

**Status:** PROPOSED  
**Milestone:** PD Agent v0.4 --- Benchmark Foundation  
**Scope:** delta sobre el benchmark existente. No billing, no credits, no SaaS, no background scheduler, no Model Router.

## 1. Contexto y hallazgos de auditoria

La auditoria contra el repo real confirma que el presupuesto y el resume cruz-session son un delta de benchmark, no un nuevo diseno.

Hechos relevantes del repositorio actual:

- `scripts/benchmark/run_v0_4.py` ya crea un `BenchmarkRequestPacer` con cadencia minima y budget logico, pero hoy solo pacea llamadas y no decide cuando pausar una ejecucion.
- `BenchmarkExecutionRunner` ya escribe `manifest.json` y `schedule.json`, recorre una lista canonica de attempts y persiste `completed_runs`, pero hoy no tiene contrato de pausa/resume.
- `BenchmarkSchedule` y `BenchmarkScheduleCell` ya serializan order, attempts y replacement history.
- `RunState` ya persiste `logical_provider_request_count`.
- `BenchmarkCollector` ya usa `MODEL_CALLED` solo como cross-check contra `RunState`.
- `BenchmarkRequestPacer` usa reloj monotono, contabiliza requests logicas y no ve retries internos del SDK.
- No existe hoy un `--resume` en `scripts/benchmark/run_v0_4.py`.

Conclusiones de auditoria:

- No hace falta un design delta nuevo.
- Si hace falta un delta de RFC e IMP.
- La pausa por presupuesto debe ser una decision del runner de benchmark, no del scheduler.

## 2. Objetivo

Definir un contrato de ejecucion que permita:

1. parar de forma limpia una ejecucion cuando el presupuesto logico restante no alcanza para iniciar otro attempt;
2. persistir el estado necesario para reanudar la misma ejecucion en otra sesion;
3. evitar doble conteo de requests, attempts y evidence;
4. conservar el orden canonico del schedule;
5. mantener intactos dataset, Brain OFF/ON, acceptance, repetitions y max_agent_steps.

## 3. No objetivos

Este delta no introduce:

- billing real;
- pricing real;
- credits;
- Stripe;
- background daemon;
- servicio de reanudacion automatico;
- nuevo provider;
- nuevo dataset;
- nuevas tasks;
- cambios en acceptance;
- cambios en `max_agent_steps`;
- cambios en Brain OFF/ON;
- matriz oficial de 18 runs;
- cambios en `ToolExecutor` o en el boundary de seguridad;
- cambios en `SecurePathResolver`.

## 4. Terminologia

### 4.1 Logical provider request

Una invocacion logica de PD Agent a `ModelProvider.execute(AgentRequest)`.

Es la unidad que PD Agent puede controlar de forma directa.

### 4.2 Physical provider request

Request real de transporte/API enviado por el SDK o el provider.

Puede ser mayor que la cuenta logica por retries internos opacos.

### 4.3 Session budget

Presupuesto logico disponible para una sesion de benchmark.

Se expresa en numero de logical provider requests.

### 4.4 Observed provider quota

Cuota observada para un provider/model/account/project concreto.

No es una propiedad universal del provider.

### 4.5 Attempt reservation

Cantidad minima de budget logico que debe reservarse antes de iniciar un nuevo attempt.

Para v0.4, la reserva es `max_agent_steps`.

### 4.6 Canonical schedule

El orden persistido en `schedule.json` para una ejecucion concreta.

No se regenera al reanudar.

### 4.7 Resume

Reanudar una ejecucion ya creada usando su execution directory existente, su manifest persistido y su schedule persistido.

## 5. Budget authority

### 5.1 Autoridad principal

`BenchmarkExecutionRunner` es la autoridad de pause/continue.

### 5.2 Autoridad de pacing y contador logico

`BenchmarkRequestPacer` es la autoridad de:

- pacing minimo entre requests logicas;
- contador de logical provider requests de la sesion.

### 5.3 Autoridad que no decide budget

`BenchmarkScheduler` no decide budget.

Solo crea y persiste el orden canonico de attempts.

### 5.4 Persistencia primaria del contador

`RunState` sigue siendo la persistencia primaria de `logical_provider_request_count`.

`MODEL_CALLED` sigue siendo cross-check y no autoridad normativa.

## 6. Budget policy

La politica de presupuesto es benchmark-local y configurable.

No se interpreta como limite universal de Gemini ni de ningun provider.

Para la ejecucion observada de v0.4:

- `logical_daily_cap = 400`
- `attempt_reservation = max_agent_steps = 25`

Regla de inicio de attempt:

```text
can_start_attempt = remaining_logical_budget >= attempt_reservation
```

Donde:

```text
remaining_logical_budget = logical_daily_cap - logical_provider_request_count
```

Si `can_start_attempt` es false, el runner debe pausar la ejecucion de forma limpia.

### 6.1 Importante sobre retries

El cap de 400 es conservador sobre llamadas logicas.

No garantiza por si solo un maximo fisico de 500 RPD, porque los retries internos del SDK pueden elevar el coste fisico sin cambiar la cuenta logica.

## 7. Semantica de `BUDGET_PAUSED`

`BUDGET_PAUSED` es un estado de ejecucion de batch, no un fallo sintetico de una run individual.

### 7.1 Propiedades obligatorias

Cuando se activa:

- la ejecucion termina limpiamente;
- el `schedule.json` queda persistido;
- la comparacion o summary indica pausa;
- la celda pendiente no se consume;
- no se marca PASS, FAIL, BLOCKED o INVALID de forma sintentica;
- no se inventa un fallo de agente para representar budget.

### 7.2 Efectos que no deben ocurrir

La pausa no debe:

- consumir un attempt;
- consumir una replacement;
- duplicar usage;
- duplicar evidence;
- alterar el orden canonico del schedule;
- reescribir completions ya persistidas.

## 8. Resume contract

### 8.1 CLI

El contrato propuesto es:

```text
scripts/benchmark/run_v0_4.py --resume <execution_dir>
```

### 8.2 Reglas del resume

Al reanudar:

- se carga el `manifest.json` existente;
- se carga el `schedule.json` existente;
- no se crea un schedule nuevo;
- no se reordena el schedule;
- no se regenara el dataset;
- no se reinicia el contador de completados;
- se continua exactamente desde el siguiente pending item valido.

### 8.3 Reglas de entrada

El resume debe usar la misma batch identity y el mismo execution directory ya creado.

Si se pasa un `--resume` contra un directorio ajeno, inexistente o incompatible, el comando debe rechazarlo explicitamente.

## 9. Drift validation

El resume debe rechazar drift si cambia cualquiera de estos identificadores o contratos:

- dataset id;
- dataset version;
- task id/version;
- fixture identity;
- config id/hash;
- provider;
- model;
- `brain_enabled`;
- `execution_limits`;
- `target_valid_repetitions`;
- `max_attempts_per_cell`;
- `scheduling_seed`;
- canonical schedule;
- Gradle seed identity / manifest identity;
- PD Agent commit o baseline, segun la politica final acordada para resume.

Si el drift es material, el resume debe fallar de forma explicita con un error de drift, no con un BLOCKED generico.

## 10. Canonical schedule policy

El schedule canonico es fuente de verdad para el orden de attempts.

Reglas:

1. cargar `schedule.json` existente;
2. no reshuffle;
3. no regenerar;
4. conservar completed runs;
5. conservar replacement history;
6. continuar el siguiente pending exacto.

Si el schedule ya esta completo, el resume debe ser no-op y devolver COMPLETE o estado equivalente.

## 11. Idempotence policy

La reanudacion debe ser idempotente respecto a lo ya cerrado.

Reglas:

- completed attempts no se repiten;
- evidence ya escrita no se sobrescribe;
- usage ya persistido no se duplica;
- run IDs ya completados no se reutilizan;
- replacements ya generadas se conservan;
- el orden de ejecucion no cambia entre sesiones.

## 12. Crash policy

### 12.1 Budget pause limpia

Si la ejecucion se detiene por budget, el resume continua desde el siguiente pending item.

### 12.2 Crash entre attempts

Si la ejecucion cae entre attempts, el resume reanuda desde el siguiente pending que no este marcado como completed.

### 12.3 Crash durante un attempt

Si un attempt quedo incompleto y no existe completion formal persistida, puede repetirse desde cero.

### 12.4 Regla de cierre

Solo cuentan como completed los attempts con cierre formal persistido.

## 13. Multi-day

El flujo multi-day es manual y simple:

1. dia N: ejecutar schedule canonico hasta budget pause;
2. dia N+1: el usuario lanza `--resume`;
3. se aplica un nuevo session budget;
4. se continua el mismo schedule exacto;
5. no existe background service.

## 14. Error / status taxonomy

El contrato necesita estados/codigos minimos para diferenciar:

- `BUDGET_PAUSED`
- `RESUME_DRIFT`
- `RESUME_INVALID_STATE`

Si el implementor prefiere otros nombres equivalentes, deben conservar la misma semantica.

No se debe usar `BLOCKED` para representar una pausa limpia por budget.

## 15. Evidence

La evidencia de pausa y resume debe persistir como minimo:

- budget logico configurado;
- budget logico usado;
- budget restante;
- attempt reservation;
- pause reason;
- timestamp de pausa;
- resume count;
- session identity;
- prior execution identity;
- next pending item;
- schedule identity;
- manifest identity;
- commit/baseline usado por la ejecucion.

No se debe fingir physical request count cuando no exista observacion fiable.

## 16. Auditoria contra repo real

El repo actual es compatible con este delta en lo esencial:

- ya existe schedule persistido;
- ya existe manifest persistido;
- ya existe contador logico en `RunState`;
- ya existe cross-check por `MODEL_CALLED`;
- ya existe pacing monotono;
- ya existe batch runner secuencial.

Discrepancias no bloqueantes para la documentacion:

- no existe hoy `--resume`;
- no existe hoy estado de budget pause en el batch envelope;
- no existe hoy persistencia explicita de `budget_state`.

Estas discrepancias son del lote de implementacion, no un conflicto conceptual del RFC.

## 17. Criterios de aceptacion del delta

Este RFC queda listo para implementacion cuando la documentacion y la implementacion puedan demostrar:

1. budget stop antes de iniciar un nuevo attempt;
2. pausa limpia sin synthetic failure;
3. schedule persistido intacto;
4. resume exacto desde el siguiente pending correcto;
5. drift detectado y rechazado;
6. idempotencia sin doble conteo;
7. OFF/ON y dataset intactos;
8. no design delta adicional.

## 18. Gate posterior

Este RFC no autoriza la matriz oficial completa.

Primero debe existir la implementacion minima de budget stop/resume y luego la validacion con evidence nueva.
