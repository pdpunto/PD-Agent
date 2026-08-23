# PD Agent v0.5 - F9 Semantic Validation + Repair RFC

**Estado:** RFC para IMP, pendiente de implementacion
**Design:** `docs/design/PD_AGENT_V0.5_F9_SEMANTIC_REPAIR_DESIGN.md`
**Baseline auditada:** `122e52a73cdc162c499abd8e72f6cf655bcb2de5`

## 1. Boundary

`AgentRuntime` no importara acceptance ni modelos de benchmark. Consumira una
interfaz generica de validacion. La capa benchmark convertira:

```text
BenchmarkTask.acceptance.spec
  -> PublicValidationContract
  -> validator adapter
```

El adapter sera responsable de conocer acceptance y de traducir sus resultados
a contratos genericos. `MinecraftTestRunner` conservara su autoridad sobre
identidad, dependencias, observaciones y evidencia.

## 2. Contratos

Los nombres finales deben vivir en el modulo que confirme el IMP, pero el
contrato minimo es:

```text
ValidationStage = PRE_BUILD | POST_ARTIFACT | RUNTIME
ValidationStatus = PASS | REPAIRABLE_FAIL | BLOCKED

ValidationViolation:
  code
  requirement
  observed
  message
  evidence_refs

ValidationResult:
  stage
  status
  summary
  violations
  evidence_refs
```

La firma determinista de una violacion usa `stage + code + requirement
identifier/path + observed category`. No usa timestamps ni paths temporales.

## 3. PRE_BUILD

El adapter puede revisar, antes de gastar un build:

- existencia de archivos;
- paths de recursos;
- JSON valido;
- JSON pointer presente;
- JSON pointer igual a un valor publico.

PASS permite `BUILDING`. `REPAIRABLE_FAIL` devuelve feedback y entra en
`CORRECTING`. BLOCKED detiene la ejecucion sin fingir un fallo del agente.
PRE_BUILD no intenta demostrar registros ni runtime.

## 4. Build y artifact

El Gradle Wrapper sigue siendo la autoridad de compilacion. El comportamiento
actual de build fail -> diagnostico -> correccion -> rebuild se conserva.

`ArtifactValidator` sigue siendo la autoridad del JAR. Un artifact invalido no
se convierte en semantic PASS. El IMP debe decidir, usando los contratos
existentes, cuales errores de artifact son reparables y cuales son terminales.

## 5. Validacion funcional

Se planifica anadir `VALIDATING_FUNCTIONAL` entre artifact y reporting. La
auditoria encontro que `RunStatus` actual solo contiene
`VALIDATING_ARTIFACT` y que sus transiciones no contemplan el nuevo estado.
Eso es una discrepancia de implementacion futura, no una razon para alterar el
runtime durante este lote documental.

El estado ejecutara primero checks POST_ARTIFACT y despues Minecraft solo si el
contrato lo requiere. Un fallo funcional reparable debe volver a
`CORRECTING`; un PASS debe continuar a `REPORTING`.

## 6. Minecraft

No se redisenia `MinecraftTestRunner`. Se reutilizan:

- `MinecraftTestSpec` y `MinecraftTestResult`;
- target identity y SHA;
- runtime dependencies;
- `REGISTRY_ENTRY_PRESENT`;
- `MinecraftRuntimeEvidence`;
- resultados de observacion estructurados.

Un registro ausente o una observacion funcional fallida es
`REPAIRABLE_FAIL` cuando el target arranco y la evidencia permite atribuir el
fallo al cambio del agente. Un crash de startup del target puede ser feedback
reparable si el error es determinista del cambio y el contrato lo soporta.
Un fallo de infraestructura, timeout o dependencia no disponible es BLOCKED.

## 7. Feedback

El mensaje al provider debe ser corto, determinista y no prescribir codigo:

```text
Functional validation failed:
assets/examplemod/lang/en_us.json is missing required value
/item.examplemod.server_core = "Server Core".
```

Debe contener requisito, observado, razon y evidencia util. No debe contener
la implementacion de referencia ni una API concreta.

## 8. Persistencia y reporting

Cada resultado debe conservar:

- stage y status;
- violaciones y firma determinista;
- evidence refs;
- turno de reparacion posterior;
- build posterior;
- resultado final.

La persistencia debe extender `RunState`, `FinalReport`, `RunEvent` y
serializacion solo en la medida minima. El reporte final debe poder explicar
por que se reparo, bloqueo o termino el run.

## 9. Limits y stall

No se crea un sistema de budget paralelo. Siguen siendo autoridad:

- `max_agent_steps`;
- `max_tool_calls`;
- `max_build_attempts`.

Para la misma firma de violacion, dos repeticiones consecutivas sin progreso
relevante deben terminar como agent failure, siguiendo el patron de presion y
rechazos recuperables ya existente. El IMP debe confirmar el punto exacto de
integracion y evitar doble conteo de limites.

## 10. Action Gate

El Action Gate se conserva. Una validacion semantica fallida:

- puede resetear la presion al entrar en correccion;
- puede ofrecer herramientas adecuadas;
- no crea mutation targets artificiales;
- no revierte targets fisicos completados.

El build sigue bloqueado si quedan mutation targets pendientes, tal como exige
el runtime actual.

## 11. Leakage boundary

Visible: requisitos user-facing, identifiers, paths, keys, values,
comportamiento observable e invariantes relevantes.

Hidden: reference implementation, source de referencia, APIs exactas, layout de
clases, Harness internals, answer key, knowledge hints y detalles de scoring.

La regla es que un hecho concreto necesario para el PASS puede ser publico si
forma parte del resultado que el usuario solicito; el camino para obtenerlo no
lo es.

## 12. Contratos F6

### T1

- observar item `examplemod:signal_charm`;
- PASS de runtime;
- `Item id not set` debe producir feedback reparable cuando sea un error del
  target y no infraestructura.

### T2

- observar bloque e item `examplemod:marble_lantern`;
- validar las dos claves de `en_us.json`.

### T3

- observar bloque e item `examplemod:server_core`;
- validar idioma block/item;
- validar recipe, `result.id` y `result.count`.

## 13. Dependencia Brain

Este RFC no implementa Brain API support. F9 demostro que
`KnowledgeType.API -> Yarn UNSUPPORTED_NEED`; la reparacion semantica debe
funcionar aun con cero elementos recuperados, seleccionados o inyectados.
Compiler, acceptance y runtime feedback son suficientes para el primer loop.

## 14. Criterio de cierre RFC

El RFC queda listo para IMP cuando los contratos no filtran referencias, los
boundaries coinciden con el repo auditado, las discrepancias de estados quedan
explicitamente pendientes de implementacion y los tests planificados cubren
PASS, reparacion, BLOCKED, limites, evidencia y regresiones.
