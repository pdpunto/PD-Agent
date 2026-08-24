# PD Agent v0.5 - F9 Semantic Validation + Repair IMP

**Estado:** IMP para auditoria previa; no autoriza implementacion automatica
**Design:** `docs/design/PD_AGENT_V0.5_F9_SEMANTIC_REPAIR_DESIGN.md`
**RFC:** `docs/rfc/PD_AGENT_V0.5_F9_SEMANTIC_REPAIR_RFC.md`

## 1. Regla de seguridad

Este documento no implementa Batch 1, no ejecuta provider/API y no autoriza
F9 live. Cada batch requiere auditoria y validacion antes del siguiente.
Dataset, acceptance, config, fixture, Brain API y Harness permanecen fuera de
este delta.

## 2. Auditoria del repo realizada

La auditoria contra `122e52a73cdc162c499abd8e72f6cf655bcb2de5` encontro:

- `RunStatus` en `src/pd_agent/core/state.py` contiene
  `VALIDATING_ARTIFACT`, pero no `VALIDATING_FUNCTIONAL`;
- las transiciones actuales pasan de artifact a reporting;
- `RunController`/`AgentRuntime` controlan provider, tools, build, artifact y
  reporting;
- `BenchmarkExecutor` ejecuta Minecraft y acceptance despues del controller;
- `acceptance.py` ya evalua resources JSON y observaciones requeridas;
- `MinecraftTestRunner` y sus contratos ya producen evidencia estructurada;
- reporting ya persiste `RunState`, `FinalReport` y eventos JSONL;
- mutation targets ya bloquean build cuando quedan pendientes;
- el runtime persiste razones terminales agent explicitas y el classifier debe
  consumir el catalogo central completo; una razon emitida fuera de ese
  catalogo es un drift de contrato;
- no existe aun un contrato generico de validation ni un repair loop funcional.

La ausencia de `VALIDATING_FUNCTIONAL` es la discrepancia principal. Los lotes
de abajo deben anadirlo solo despues de confirmar el punto exacto de transicion
y serializacion.

## 2.1 Delta de clasificacion terminal

La implementacion debe mantener un catalogo central en el boundary core/runtime
para que `AgentRuntime` y `BenchmarkClassifier` compartan exactamente las
razones agent-terminal. La clasificacion de una razon reconocida tiene
precedencia sobre los gates de evidencia downstream y produce
`COMPLETED + FAIL`, `AGENT`, `AGENT_TASK_FAILURE`, incluso cuando no hay build,
artifact o Minecraft porque la ejecucion termino antes de esas fases.

El runtime publica `diagnosis produced no correction` mediante la constante
central correspondiente. Esta razon representa un fallo atribuible al agente,
no evidencia invalida, y no consume replacement.

El mismo catalogo cubre las terminaciones agent de validacion semantica
repetida, no-op repetido, exploracion estancada y hard gate por mutation targets
pendientes. Las terminaciones de provider, limites, infraestructura y harness
siguen fuera de este catalogo y conservan `BLOCKED`.

La separacion contractual es:

- `FAIL`: terminacion agent explicita o fallo atribuible al cambio del agente;
- `BLOCKED`: provider, limite, build environment o Minecraft harness que
  impiden evaluar;
- `INVALID`: contaminacion, contradiccion o evidencia metodologicamente
  invalida.

El runner solo crea replacements para `BLOCKED` e `INVALID`; un
`COMPLETED + FAIL` no consume replacement.

## 3. Batch 1 - contratos y contexto publico

Objetivo: representar T1/T2/T3 sin leakage y sin loop.

Trabajo previsto:

- ubicar `ValidationStage`, `ValidationStatus`, `ValidationViolation` y
  `ValidationResult` en el boundary core/runtime confirmado por auditoria;
- crear el adapter benchmark que traduzca acceptance a contrato publico;
- excluir `knowledge_needs`, reference data, hidden notes, scoring y Harness
  internals;
- anadir serializacion y reporting minimo;
- anadir tests de contrato, determinismo y leakage.

Acceptance:

- T1, T2 y T3 representan solo hechos user-facing;
- no aparece codigo ni API de referencia;
- provider y Brain no son dependencias del contrato.

Commit independiente sugerido: `feat: add semantic validation contracts`

## 4. Batch 2 - PRE_BUILD y reparacion barata

Objetivo: detectar antes del build archivos, JSON y pointers invalidos.

Trabajo previsto:

- ejecutar checks PRE_BUILD cuando el contrato los declare;
- devolver feedback estructurado;
- entrar en `CORRECTING` y permitir mutacion;
- persistir cada resultado;
- aplicar stall detection a firmas equivalentes;
- mantener Action Gate y mutation targets fisicos.

No se ejecuta Minecraft en este batch.

Tests deterministas: T2/T3 con lang o recipe ausentes, invalidos y reparados.

Commit independiente sugerido: `feat: add prebuild semantic repair`

## 5. Batch 3 - loop post-artifact/runtime

Objetivo: integrar funcionalidad real sin redisenar el Harness.

Trabajo previsto:

- anadir `VALIDATING_FUNCTIONAL` y transiciones validas;
- adaptar acceptance y `MinecraftTestRunner` al contrato generico;
- mapear registry FAIL a `REPAIRABLE_FAIL`;
- mapear infra/timeout/dependencia a BLOCKED;
- mapear PASS a REPORTING;
- conservar identidad, SHA, dependencias y evidence refs.

Antes de editar, confirmar como se comparte el workspace y como se evita que
`BenchmarkExecutor` ejecute una segunda validacion fuera del loop.

Commit independiente sugerido: `feat: add functional validation repair loop`

## 6. Batch 4 - regresion offline

Escenarios fake y deterministas:

- T1: registry incorrecto -> feedback -> reparacion -> PASS;
- T2: item/lang ausente -> feedback -> reparacion -> PASS;
- T3: item lang/recipe ausente -> feedback -> reparacion -> PASS;
- repeticion semantica -> agent failure;
- limites de steps, tools y builds preservados;
- Action Gate preservado;
- evidence retenida;
- provider-neutrality y no leakage;
- regresiones v0.4 y F6/F7.

La suite completa se ejecuta solo despues de los tests focalizados y sin
provider live.

## 7. Batch 5 - readiness live

No se ejecuta automaticamente. Tras Batches 1-4 PASS, 04 debe decidir una
smoke live controlada y separada antes de reabrir la matriz oficial F9.

## 8. Matriz minima de tests

1. contrato publico T1;
2. contrato publico T2;
3. contrato publico T3;
4. exclusion de campos hidden;
5. PRE_BUILD PASS;
6. PRE_BUILD resource FAIL;
7. fallo crea repair turn;
8. repair puede mutar;
9. recurso reparado pasa;
10. build failure conserva comportamiento;
11. artifact validation conserva comportamiento;
12. registry FAIL crea repair;
13. infra Minecraft produce BLOCKED;
14. runtime PASS produce COMPLETED;
15. repeated semantic failure termina;
16. max_agent_steps preservado;
17. max_tool_calls preservado;
18. max_build_attempts preservado;
19. Action Gate preservado;
20. evidence retenida;
21. mutation targets siguen siendo progreso fisico;
22. regresion v0.4;
23. contrato F6-T1;
24. contrato F6-T2;
25. contrato F6-T3;
26. sin dependencia de Brain;
27. sin reference leakage.

## 9. Checklist antes de implementar

- [ ] baseline y working tree verificados;
- [ ] DESIGN/RFC/IMP auditados contra enums y transiciones reales;
- [ ] boundary Controller/Executor confirmado;
- [ ] serializacion y reporting confirmados;
- [ ] acceptance y Minecraft adapter confirmados;
- [ ] discrepancias documentales corregidas;
- [ ] tests del batch escritos antes del cambio funcional;
- [ ] no se toca diagnostics;
- [ ] no se ejecuta provider, F9 live ni Batch 5.

## 10. Criterio de readiness

Este IMP queda listo para Batch 1 documentalmente cuando la auditoria no
encuentra contradicciones sin documentar. La implementacion de Batch 1 sigue
requiriendo una instruccion posterior y commit independiente.
