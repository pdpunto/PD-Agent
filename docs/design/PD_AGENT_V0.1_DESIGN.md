# PD Agent v0.1 --- DESIGN

**Estado:** Aprobado\
**Versión:** 1.0\
**Proyecto:** PD Agent\
**Documento:** Design de producto --- v0.1

## 1. Objetivo

PD Agent v0.1 debe recibir:

`Proyecto Fabric existente + tarea escrita por el usuario`

y ser capaz de llevarla hasta:

`cambio de código + BUILD SUCCESSFUL + JAR generado + informe verificable`

sin que el usuario tenga que dirigir técnicamente cada iteración.

## 2. Flujo funcional

El comportamiento esperado será:

`Recibir tarea → inspeccionar proyecto → crear plan → modificar archivos → ejecutar build → analizar resultado → corregir si falla → repetir → validar → entregar resultado`

Habrá límites de seguridad y de iteraciones. No se permitirán loops
infinitos.

## 3. Capacidades obligatorias

v0.1 deberá poder:

-   Abrir un proyecto Fabric existente.
-   Entender su estructura básica.
-   Leer archivos relevantes.
-   Buscar código dentro del proyecto.
-   Crear, modificar y eliminar archivos cuando la tarea lo requiera.
-   Consultar contexto técnico disponible.
-   Utilizar un LLM mediante una interfaz desacoplada del proveedor.
-   Ejecutar comandos estrictamente relacionados con el proyecto.
-   Ejecutar Gradle.
-   Capturar stdout, stderr y códigos de salida.
-   Detectar un build fallido.
-   Proporcionar el error al agente.
-   Intentar corregirlo.
-   Repetir el ciclo dentro de límites definidos.
-   Detectar `BUILD SUCCESSFUL`.
-   Localizar el JAR producido.
-   Registrar acciones importantes.
-   Generar un informe final.

## 4. Autonomía

El usuario define qué quiere conseguir.

PD Agent decide técnicamente:

-   qué archivos inspeccionar;
-   qué código modificar;
-   qué comandos necesarios ejecutar;
-   cómo resolver errores;
-   cuándo repetir el build.

Debe detenerse cuando necesite una decisión genuina del usuario o cuando
alcance límites de seguridad o iteraciones.

## 5. Knowledge Base en v0.1

No se construirá todavía el Minecraft Brain completo.

Pero tampoco se diseñará v0.1 suponiendo que el conocimiento interno del
LLM es suficiente.

Debe existir una capacidad mínima de proporcionar contexto externo al
agente. La Knowledge Base completa y versionada llegará en v0.2.

## 6. Providers

El sistema debe nacer model-agnostic.

v0.1 necesita solamente un provider funcional para demostrar el flujo
completo.

No se implementarán todavía selección automática de modelos ni Hybrid.

La arquitectura posterior decidirá el provider inicial concreto.

## 7. Seguridad

El agente no tendrá libertad ilimitada sobre el ordenador.

Como requisito de producto:

-   trabajo limitado al proyecto autorizado;
-   comandos controlados;
-   protección frente a operaciones destructivas;
-   límites de iteraciones;
-   logs de acciones;
-   errores críticos provocan parada segura.

El mecanismo exacto pertenece al RFC.

## 8. Git

Git forma parte del flujo desde v0.1.

PD Agent debe poder trabajar sobre proyectos Git sin destruir su estado
existente.

La estrategia concreta de snapshots, ramas, commits o rollback se
decidirá posteriormente en arquitectura/RFC.

## 9. Resultado final

Una ejecución satisfactoria debe producir como mínimo:

-   resumen de la tarea;
-   archivos modificados;
-   builds realizados;
-   resultado final del build;
-   ruta del JAR;
-   errores relevantes encontrados y corregidos;
-   advertencias o limitaciones restantes.

## 10. No objetivos

Quedan explícitamente fuera de v0.1:

-   crear proyectos Fabric desde cero;
-   ejecutar Minecraft;
-   comprobar comportamiento dentro del juego;
-   Minecraft Test Harness;
-   multiagente;
-   `.Fuzzer`;
-   fuzzing;
-   Paper;
-   NeoForge;
-   Velocity;
-   UI comercial/final;
-   marketplace;
-   Auto/Hybrid avanzado;
-   memoria avanzada;
-   Knowledge Base completa;
-   benchmarks entre modelos;
-   integración con PD-Ecosystem.

## 11. Criterio de aceptación principal

Se preparará una tarea Fabric real y reproducible.

PD Agent deberá completarla consiguiendo:

**`BUILD SUCCESSFUL`**

y deberá existir un **JAR válido generado por Gradle** correspondiente
al proyecto modificado.

Además, los cambios y acciones deben quedar trazables.

Esto será el PASS principal de PD Agent v0.1.

## 12. Qué NO demuestra un PASS

Un build correcto no demuestra que el mod funciona correctamente dentro
de Minecraft.

Esa garantía llegará con Minecraft Test Harness.

Por tanto:

`v0.1 PASS = correcto a nivel de modificación/build`

no:

`v0.1 PASS = comportamiento Minecraft demostrado`

Esta distinción será obligatoria en los informes del agente.
