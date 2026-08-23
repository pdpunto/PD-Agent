# PD Agent v0.5 - F9 Semantic Validation + Repair DESIGN

**Estado:** DESIGN para RFC
**Milestone:** PD Agent v0.5 - Fabric Agent Capability Foundation
**Area:** 04 - Fabric Agent
**Baseline auditada:** `122e52a73cdc162c499abd8e72f6cf655bcb2de5`

## 1. Problema

La matriz F9 demostro que el agente puede editar, compilar, producir un
artifacto y lanzar Minecraft, pero no puede reparar un fallo funcional que
aparece despues de esos pasos. `mutation targets` indican presencia y
progreso fisico; no indican que el registro, recurso, recipe o comportamiento
sean correctos.

El flujo actual termina el `RunController` antes de que `BenchmarkExecutor`
ejecute Minecraft y acceptance. El resultado funcional llega demasiado tarde
para abrir otro turno del agente.

## 2. Objetivo

El runtime debe poder:

1. implementar una tarea;
2. ejecutar validaciones baratas y observables;
3. producir feedback estructurado cuando el fallo sea reparable;
4. volver a `CORRECTING` y permitir otra edicion;
5. reconstruir y revalidar dentro de los limites existentes;
6. terminar solo con PASS funcional, BLOCKED real o fallo/limite legitimo.

## 3. Flujo objetivo

```text
EDITING
  -> PRE_BUILD validation
  -> BUILDING
  -> VALIDATING_ARTIFACT
  -> VALIDATING_FUNCTIONAL
  -> REPORTING
```

Cuando una validacion reparable falla:

```text
validation fail
  -> structured feedback
  -> CORRECTING
  -> EDITING
  -> PRE_BUILD validation again
```

`VALIDATING_FUNCTIONAL` es una decision de arquitectura futura. No existe
todavia en `RunStatus` y no debe presentarse como implementada.

## 4. Alcance

Incluido:

- contrato generico de validacion publica;
- validacion semantica PRE_BUILD y POST_ARTIFACT;
- adapter de acceptance para el runtime;
- feedback reparable corto y estructurado;
- validacion funcional con Minecraft existente;
- persistencia de resultados, violaciones y evidencia;
- limites y deteccion de estancamiento.

Fuera de este delta:

- soporte de `KnowledgeType.API` o redisenio del Brain;
- nuevo provider o modelo;
- Multi-Agent o planner nuevo;
- cambios de dataset, acceptance, fixture o reference solution;
- redisenio del Minecraft Harness;
- generalizacion fuera de Fabric.

## 5. Principios

- provider-neutral;
- benchmark-neutral en el runtime core;
- cheapest validation first;
- sin reference leakage;
- evidencia real como autoridad;
- limites acotados y fail closed;
- no inferir correccion desde `mutation targets`;
- no convertir un fallo de infraestructura en reparacion del agente.

## 6. Contrato publico

El modelo puede recibir hechos user-facing que ya forman parte del resultado
solicitado: identificadores, paths, keys, values, comportamiento observable e
invariantes de preservacion.

Ejemplos congelados para F6:

- T1: item `examplemod:signal_charm`.
- T2: bloque e item `examplemod:marble_lantern`, y las dos claves de
  `assets/examplemod/lang/en_us.json`.
- T3: bloque e item `examplemod:server_core`, las dos claves de idioma y el
  recipe `data/examplemod/recipe/server_core.json` con resultado y cantidad.

El contrato no debe exponer implementacion de referencia, APIs exactas,
layout de clases, helper oculto, detalles del Harness, scoring interno,
`knowledge_needs` ni hints que sean un solution path.

## 7. Resultado esperado

La validacion debe distinguir:

- PASS: todos los requisitos observables satisfechos;
- REPAIRABLE_FAIL: el artefacto o runtime funciona lo suficiente y el agente
  puede intentar corregirlo;
- BLOCKED: infraestructura, entorno o evidencia no permiten evaluar;
- terminal agent failure: limite agotado, rechazo fatal o estancamiento.

La correccion de un requisito semantico no revierte la finalizacion fisica de
un mutation target. Son dimensiones distintas.

## 8. Criterios de exito

- T1, T2 y T3 tienen contratos publicos sin leakage;
- un recurso JSON ausente o incorrecto genera feedback reparable;
- un registro ausente genera feedback reparable;
- una infraestructura Minecraft indisponible produce BLOCKED;
- los limites actuales siguen siendo autoridad;
- la evidencia permite reconstruir cada intento y su reparacion;
- F9 solo se reabre despues de pasar los lotes offline.
