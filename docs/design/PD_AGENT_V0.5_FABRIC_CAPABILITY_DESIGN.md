# PD Agent v0.5 --- Fabric Agent Capability Foundation --- DESIGN

**Estado:** DRAFT FOR RFC\
**Milestone:** PD Agent v0.5 --- Fabric Agent Capability Foundation\
**Área propietaria:** 04 --- Fabric Agent\
**Predecesor:** PD Agent v0.4 --- Benchmark Foundation ---
IMPLEMENTADO + LIVE VALIDATED + PASS

## 1. Propósito

PD Agent v0.5 debe demostrar la primera capacidad Fabric representativa
y útil para un usuario real, construida sobre la cadena E2E ya validada
en v0.1--v0.4.

El incremento mínimo seleccionado es:

> Dado un proyecto Fabric existente, válido y compilable, y un requisito
> funcional en lenguaje natural, PD Agent debe poder implementar una
> feature Fabric server-observable no trivial, preservando contratos no
> relacionados, compilando el proyecto, generando un JAR válido y
> demostrando el comportamiento solicitado en Minecraft real.

v0.5 no pretende resolver todavía creación de proyectos desde cero ni
reparación general de proyectos arbitrariamente rotos.

## 2. Problema

v0.1--v0.4 prueban que PD Agent puede ejecutar un ciclo real:

requisito → provider → tools → modificación → Gradle → JAR → Minecraft →
evidencia → PASS/FAIL.

Sin embargo, la evidencia se ha obtenido principalmente con fixtures y
tareas controladas.

Falta demostrar que la misma arquitectura puede trabajar sobre un
proyecto Fabric representativo y realizar una modificación funcional
semejante a una petición real de usuario.

## 3. Objetivo de producto

Validar una capability base de **Existing Fabric Feature Development**.

PD Agent debe recibir:

1.  un proyecto Fabric existente;
2.  un proyecto inicialmente válido y compilable;
3.  un requisito funcional expresado por comportamiento deseado;
4.  límites de ejecución y seguridad existentes.

Y debe ser capaz de:

1.  inspeccionar el proyecto;
2.  comprender la estructura relevante;
3.  localizar los archivos/símbolos afectados;
4.  modificar archivos existentes;
5.  crear archivos nuevos cuando la feature lo requiera;
6.  preservar estructura y contratos no relacionados;
7.  ejecutar Gradle mediante el wrapper autorizado;
8.  diagnosticar errores introducidos por su propia implementación;
9.  corregirlos dentro de los límites existentes;
10. producir un JAR válido;
11. ejecutar/validar la feature en Minecraft real;
12. producir evidencia reproducible.

## 4. No objetivos

Quedan explícitamente fuera de v0.5:

-   creación/scaffolding completo de un proyecto Fabric desde cero;
-   selección automática general de versiones Minecraft/Fabric/Loom;
-   reparación general de proyectos arbitrariamente rotos antes de
    recibir la tarea;
-   Multi-Agent;
-   Model Router;
-   SaaS/backend;
-   billing/créditos;
-   UI;
-   .Fuzzer;
-   Paper;
-   NeoForge;
-   Velocity;
-   expansión general del Minecraft Brain sin necesidad demostrada;
-   shell libre;
-   relajación del filesystem confinado;
-   sustitución del Gradle Wrapper como autoridad;
-   optimización comercial de coste/model routing.

## 5. Precondiciones del proyecto objetivo

Un proyecto aceptado por v0.5 debe:

-   existir antes del run;
-   ser reconocido como proyecto Fabric por `ProjectInspector`;
-   disponer de Gradle Wrapper válido;
-   tener configuración Fabric/Loom válida;
-   tener metadata Fabric válida;
-   contener source roots utilizables;
-   compilar correctamente en su baseline;
-   ser compatible con el entorno de validación definido para v0.5;
-   no depender de secretos o servicios externos para su baseline;
-   poder copiarse a un workspace confinado para la ejecución.

Si el proyecto baseline no compila, el caso no pertenece a la capability
principal de v0.5 y debe clasificarse como precondition/infra failure,
no convertirse silenciosamente en una tarea de reparación general.

## 6. Unidad de trabajo de v0.5

La unidad de trabajo es una **feature Fabric server-observable pequeña
pero no trivial** sobre un proyecto existente.

Debe exigir razonamiento sobre el proyecto real y no reducirse a
sustituir un literal conocido.

Una feature puede requerir:

-   editar uno o varios archivos Java;
-   crear nuevas clases;
-   modificar o crear resources/data;
-   usar APIs Fabric/Minecraft;
-   registrar contenido o comportamiento;
-   preservar metadata/entrypoints existentes;
-   integrar el cambio con la estructura ya presente.

No todas las tareas deben exigir todas estas operaciones.

## 7. Qué significa "representativo"

El proyecto base no debe diseñarse alrededor de una solución concreta de
PD Agent.

Preferencias:

1.  proyecto Fabric pequeño y convencional;
2.  estructura semejante a proyectos reales;
3.  baseline compilable;
4.  metadata y entrypoints reales;
5.  Gradle Wrapper real;
6.  ausencia de helpers que revelen la solución;
7.  posibilidad de fijar una revisión/versiones para reproducibilidad.

Se prefiere partir de un proyecto/template Fabric representativo y
**pinned**, adaptándolo solo cuando sea imprescindible para la
validación reproducible.

La adaptación para el Test Harness no debe convertir el proyecto en una
fixture que regale al agente la implementación.

## 8. Comportamiento esperado del agente

### 8.1 Inspección

El agente debe inspeccionar únicamente lo necesario para entender:

-   estructura;
-   entrypoints;
-   package/layout;
-   código relacionado;
-   recursos relevantes;
-   APIs necesarias.

La inspección no es un fin.

### 8.2 Selección del target

Debe favorecer:

-   archivos/símbolos implicados por el requisito;
-   evidencia obtenida del proyecto;
-   cambios mínimos;
-   preservación de contratos no relacionados.

No debe modificar configuración, manifests o entrypoints solo por
presión de acción.

### 8.3 Implementación

Debe poder combinar:

-   `write_file` para archivos existentes;
-   `create_file` para archivos nuevos;
-   `delete_file` únicamente cuando esté justificado.

### 8.4 Build

Tras una implementación suficiente debe intentar build temprano mediante
el Gradle Wrapper.

### 8.5 Diagnóstico y corrección

Los errores derivados de la implementación del agente forman parte de
v0.5.

El agente puede:

build → leer error real → inspección dirigida → corregir → rebuild.

Si se demuestra que errores Fabric/Gradle ordinarios no pueden
resolverse por limitaciones estructurales del subsistema actual de
build/debug, esa evidencia se deriva a **05 --- Build & Debug Agent**.
v0.5 no debe absorber silenciosamente un rediseño general de ese
subsistema.

### 8.6 Validación

Un build exitoso no basta.

La feature debe validarse mediante Minecraft real cuando el requisito
sea runtime-observable.

## 9. Preservación del proyecto

v0.5 introduce como requisito explícito de capability:

> Implementar la feature solicitada sin destruir comportamiento,
> estructura o contratos no relacionados necesarios para que el proyecto
> siga siendo un mod válido y evaluable.

Esto incluye, cuando existan:

-   mod id;
-   metadata;
-   entrypoints;
-   package structure;
-   clases existentes no implicadas;
-   contratos públicos usados por validación;
-   recursos no relacionados.

No significa que estos archivos sean inmutables. Pueden modificarse si
el requisito lo necesita y existe justificación.

## 10. Minecraft Brain

Brain mantiene su función actual:

-   aportar conocimiento externo versionado cuando sea necesario;
-   no sustituir la inspección factual del proyecto;
-   no controlar la Action Transition;
-   no convertirse en memoria del workspace.

v0.5 no autoriza una expansión general del Brain.

Si una tarea representativa demuestra un gap concreto y reproducible de
conocimiento Fabric/Minecraft, se documentará antes de ampliar sus
fuentes o contratos.

## 11. Build & Debug

v0.5 reutiliza el build/repair loop existente.

**Frontera contractual de alcance:** v0.5 asume un proyecto base
aceptable, existente y compilable antes de ejecutar la tarea funcional.
El diagnóstico y reparación incluidos en v0.5 se limitan a fallos
introducidos o descubiertos como consecuencia directa de la
implementación de esa tarea.

Dentro del alcance:

-   compilation errors causados por el cambio;
-   errores de imports;
-   errores de API;
-   errores de tipos;
-   errores sencillos de integración;
-   corrección y rebuild.

Fuera del alcance:

-   recuperación general de Gradle roto en baseline;
-   reparación arbitraria de dependencias;
-   migraciones complejas;
-   corrupción de wrapper;
-   diagnóstico general de entornos;
-   convertir una precondición baseline fallida en una tarea implícita
    de reparación.

Si la estructura, configuración, wrapper, dependencias o entorno del
proyecto impiden alcanzar una baseline aceptable antes de entrar en la
tarea funcional, esa parte se detiene y se deriva a **05 --- Build &
Debug Agent** con evidencia. v0.5 no ampliará silenciosamente su alcance
para resolverla.

## 12. Minecraft Test Harness

v0.5 reutiliza **el Minecraft Test Harness actual y su contrato
existente** como autoridad de evidencia runtime. No se autoriza en este
milestone sustituirlo, reescribirlo ni convertirlo en un nuevo harness
genérico.

Solo podrá introducirse una **extensión mínima** cuando una tarea
representativa no pueda observarse mediante el contrato actual. Esa
extensión deberá:

-   ser imprescindible para observar el comportamiento solicitado;
-   permanecer separada de la lógica del Fabric Agent;
-   ser genérica respecto a la solución concreta de la tarea;
-   preservar los boundaries y contratos de seguridad actuales;
-   no exigir al mod target helpers artificiales que revelen cómo
    implementar la feature;
-   no proporcionar al agente un camino privilegiado o `cheat path`
    hacia el PASS.

Principio:

> La instrumentación de validación puede observar el comportamiento del
> mod, pero no debe proporcionar al agente la implementación de la
> feature.

Si validar una tarea exigiera un rediseño material del runner o de su
arquitectura, esa parte se detendrá y se derivará a **06 --- Minecraft
Test Harness** antes de continuar v0.5.

## 13. Benchmarks

La infraestructura v0.4 se reutiliza para ejecutar y comparar la
capability v0.5.

No se modifica el benchmark para convertir una solución incorrecta en
PASS.

Las tareas v0.5 deben:

-   expresar comportamiento esperado;
-   ocultar detalles de implementación innecesarios;
-   usar acceptance independiente de la estrategia concreta;
-   conservar evidencia de build, artifact y runtime;
-   distinguir fallo funcional de fallo infra.

## 14. Familia de aceptación

v0.5 debe validarse con **al menos 3 tareas distintas** pertenecientes a
la misma familia de Existing Fabric Feature Development.

Las tareas deben cubrir conjuntamente:

1.  modificación de source existente;
2.  creación de al menos un archivo nuevo en alguna tarea;
3.  interacción real con API Minecraft/Fabric;
4.  build;
5.  runtime Minecraft;
6.  preservación del proyecto.

Familias candidatas para concretar en RFC/benchmark design:

-   registro de contenido simple;
-   comportamiento server-side pequeño;
-   feature que combine source + resource/data.

No se fijan aquí nombres de clases, APIs concretas ni implementación.

## 15. Reglas para diseñar las tareas

Los prompts de aceptación deben describir **qué quiere el usuario**, no
cómo programarlo.

Correcto:

> Añade una feature X que produzca el comportamiento observable Y.

Incorrecto:

> Crea `Foo.java`, llama a una API concreta con estos argumentos y añade
> exactamente estas líneas.

Las tareas no deben:

-   mencionar la solución de referencia;
-   revelar archivos concretos salvo que un usuario real razonablemente
    los especificaría;
-   depender de hardcodes del runtime;
-   diseñarse para explotar conocimiento especial del benchmark;
-   exigir cambios fuera de la capability declarada.

## 16. Criterios de aceptación por run

Un run candidato a PASS debe demostrar:

1.  precondition baseline válida;
2.  ejecución dentro del workspace confinado;
3.  proyecto inspeccionado correctamente;
4.  al menos una mutación relevante;
5.  preservación de contratos requeridos;
6.  `BUILD SUCCESSFUL`;
7.  JAR generado;
8.  artifact válido;
9.  mod cargable en Minecraft;
10. Minecraft runtime sin crash infra atribuible al harness;
11. comportamiento solicitado observado;
12. evidencia suficiente para reproducir y clasificar el resultado.

Un run que compila pero no cumple el comportamiento solicitado es
**functional FAIL**, no PASS.

Un run que destruye el proyecto de forma que impide una evaluación que
el baseline permitía es failure del agente, no infra, salvo evidencia
contraria.

## 17. Criterio de aceptación del milestone

v0.5 no se cerrará por una única demostración manual.

Para cerrar el milestone se requiere:

-   mínimo 3 tareas representativas;
-   ejecución reproducible;
-   provider real;
-   build real;
-   artifact real;
-   Minecraft real;
-   evidencia persistida;
-   ausencia de hardcodes específicos de las tareas en runtime/policy;
-   suite offline completa PASS;
-   smoke/live validation PASS;
-   commit y push del estado validado.

El RFC definirá:

-   número exacto de repeticiones;
-   threshold de éxito requerido;
-   tratamiento de blocked/invalid;
-   configuración Brain OFF/ON si procede;
-   dataset/catálogo exacto.

## 18. Seguridad

Se preservan las garantías actuales:

-   filesystem confinado;
-   `SecurePathResolver`;
-   ToolExecutor como boundary;
-   mutation tools explícitas;
-   Action Gate;
-   Gradle Wrapper authority;
-   sin shell libre;
-   límites de steps/tools/builds/time;
-   secretos fuera de evidencia persistida;
-   providers desacoplados del runtime.

v0.5 no relajará seguridad para mejorar tasa de éxito.

## 19. Provider neutrality

La capability se define independientemente de Gemini/OpenAI u otro
proveedor.

Los prompts, tools, contexto, evidencias y acceptance pertenecen a PD
Agent.

Un provider concreto puede usarse para live validation, pero no forma
parte del contrato funcional de v0.5.

## 20. Estado y observabilidad

La evidencia debe permitir reconstruir:

-   requisito recibido;
-   project identity/baseline;
-   provider/model config no secreta;
-   Brain mode/context provenance cuando aplique;
-   archivos inspeccionados;
-   mutaciones;
-   tool rejections;
-   Action Gate;
-   builds;
-   errores y correcciones;
-   artifact;
-   Minecraft execution;
-   resultado funcional;
-   termination reason;
-   límites consumidos.

## 21. Compatibilidad inicial

v0.5 seguirá siendo Fabric-first y se validará sobre una combinación de
versiones **pinned** compatible con la infraestructura actual.

No se declara soporte general multi-version en este milestone.

La matriz exacta de Minecraft/Fabric Loader/Loom/Yarn/Java se fija en
RFC tras auditoría del repo y del proyecto base seleccionado.

## 22. Riesgos principales

### R1 --- Sobreajuste a tres tareas

Mitigación: prompts conductuales, proyectos representativos y ausencia
de hardcodes.

### R2 --- Harness demasiado acoplado

Mitigación: validar comportamiento externo y mantener instrumentación
separada de la solución.

### R3 --- Scope creep hacia scaffolding

Mitigación: proyecto existente y compilable como precondición.

### R4 --- Scope creep hacia Build & Debug general

Mitigación: solo reparar errores introducidos durante la feature;
escalar bloqueos estructurales a 05.

### R5 --- Brain convertido en parche

Mitigación: ampliar conocimiento solo ante gap concreto demostrado.

### R6 --- Build PASS confundido con feature PASS

Mitigación: Minecraft runtime obligatorio para features observables.

## 23. Condiciones de salida de DESIGN

Este DESIGN queda listo para RFC cuando:

-   el alcance se mantiene en Existing Fabric Feature Development;
-   creación desde cero permanece fuera;
-   reparación general permanece fuera;
-   se acepta proyecto existente compilable como precondición;
-   se acepta validación multi-tarea;
-   se acepta Minecraft real como evidencia funcional;
-   no aparece una dependencia estructural que obligue a trasladar el
    milestone a 05.

## 24. Resultado esperado de v0.5

Al cerrar v0.5 debe poder afirmarse con evidencia:

> PD Agent puede recibir un proyecto Fabric existente y una petición
> funcional representativa, desarrollar una feature real sobre ese
> proyecto mediante tools controladas, compilarla, producir un mod
> válido y demostrar en Minecraft que el comportamiento solicitado
> funciona.

Eso será la primera **Fabric Agent Capability** orientada directamente
al trabajo que posteriormente podrá ofrecer el producto.
