# PD Agent v0.4 --- Benchmark Foundation --- DESIGN

**Status:** DESIGN\
**Version:** 1.0\
**Milestone:** PD Agent v0.4 --- Benchmark Foundation\
**Baseline de diseño:** `18ba103a978c8199cf944fac1cb25091471e415d`

## 1. Propósito

PD Agent v0.4 introduce una Benchmark Foundation local, reproducible y
trazable para medir configuraciones reales de PD Agent mediante tareas
Fabric/Minecraft con criterios objetivos de éxito.

El benchmark debe permitir responder con evidencia:

-   qué configuraciones funcionan;
-   dónde fallan;
-   cuánto tardan;
-   cuántas acciones necesitan;
-   qué conocimiento utilizan;
-   qué usage/coste generan cuando puede medirse de forma fiable;
-   si una diferencia observada se repite suficientemente como para ser
    útil.

La primera comparación obligatoria será **Brain OFF vs Brain ON**.

El objetivo de v0.4 no es demostrar que Brain ON sea superior. Un empate
o una ventaja de Brain OFF también son resultados válidos.

## 2. Problema

Hasta v0.3, PD Agent ha validado capacidades individuales mediante
acceptance runners específicos.

v0.3 ya realizó una comparación controlada Brain OFF/ON, pero una sola
tarea y una sola observación por configuración no permiten concluir
superioridad general.

Además:

-   parte de la información de benchmark existe en `RunState`,
    `FinalReport`, eventos, traces y validation evidence;
-   provider/model/usage no se persisten todavía de forma uniforme;
-   no existe identidad formal de benchmark task/dataset/config;
-   no existe agregador genérico;
-   no existe clasificación benchmark unificada de fallos;
-   no existe política formal de repeticiones e inconclusos.

v0.4 debe cubrir esos gaps sin crear un runtime paralelo.

## 3. Objetivo de producto

Al cerrar v0.4 debe ser posible ejecutar:

`Benchmark Dataset` → `Benchmark Task` → `Benchmark Config` → workspace
aislado → runtime normal de PD Agent → provider/tools/build → Minecraft
Test Harness cuando corresponda → evidence → resultado normalizado →
repeticiones → agregación → comparación

y afirmar:

> PD Agent dispone de una infraestructura reproducible capaz de ejecutar
> varias tareas reales, conservar evidencia, producir métricas
> comparables y comparar Brain OFF vs Brain ON sin depender de juicio
> humano para determinar el PASS principal.

## 4. Principios

### 4.1 Evidencia antes que opinión

El PASS principal debe derivarse de comprobaciones objetivas.

Según la tarea puede exigir:

-   modificación esperada;
-   build correcto;
-   JAR válido;
-   Minecraft Test Harness PASS;
-   comportamiento observable.

No se usará evaluación humana como criterio principal cuando exista una
comprobación automática.

### 4.2 Runtime único

Benchmark Foundation no implementará un agente alternativo.

Las tareas benchmark deben ejecutar el runtime normal de PD Agent y
correlacionarse con su `run_id`.

### 4.3 Reutilización

Se reutilizarán como fuentes de evidencia, según corresponda:

-   `RunStorage`;
-   `RunState`;
-   `FinalReport`;
-   `events.jsonl`;
-   build logs;
-   artifact validation;
-   `KnowledgeTrace`;
-   provider responses;
-   `MinecraftTestRunner`.

Los validation runners existentes son referencia y fuente de patrones,
no la API del benchmark.

### 4.4 Comparación justa

Para Brain OFF vs Brain ON se mantendrán constantes:

-   tarea;
-   prompt;
-   fixture;
-   commit de PD Agent;
-   provider;
-   modelo;
-   límites;
-   configuración de generación aplicable;
-   versiones Minecraft/Fabric/Yarn;
-   criterio de aceptación.

La variable experimental principal será `brain_enabled`.

Brain OFF debe significar Brain realmente desactivado. No debe ejecutar
retrieval externo innecesario que altere artificialmente tiempo, usage o
coste.

### 4.5 Resultados negativos son válidos

No se descartarán tareas porque una configuración pierda.

No se modificarán criterios de aceptación después de observar resultados
sin versionar la tarea/dataset.

## 5. Alcance v0.4

v0.4 incluye:

1.  catálogo pequeño de benchmark tasks versionadas;
2.  configuración benchmark versionable;
3.  identidad y resultado normalizado por run;
4.  aislamiento por ejecución;
5.  captura de métricas;
6.  clasificación de fallos;
7.  repetición controlada;
8.  agregación descriptiva;
9.  comparación Brain OFF/ON;
10. dataset inicial de tres tareas;
11. conservación de raw evidence;
12. ejecución local;
13. documentación y validación reproducible.

## 6. Fuera de alcance

v0.4 NO incluye:

-   leaderboard público;
-   UI;
-   servicio cloud;
-   sistema distribuido;
-   cientos o miles de tareas;
-   Auto/Hybrid;
-   selección automática de modelo;
-   training/RL;
-   benchmark multi-agent;
-   `.Fuzzer`;
-   PD-Ecosystem;
-   Paper/NeoForge/Velocity;
-   client-side Test Harness;
-   nuevo provider salvo necesidad imprescindible;
-   nuevas capacidades del Minecraft Brain salvo requisito mínimo del
    benchmark;
-   score compuesto subjetivo 0--100.

## 7. Modelo conceptual

### 7.1 BenchmarkDataset

Representa una colección versionada e inmutable semánticamente de
tareas.

Debe identificar:

-   dataset ID;
-   versión;
-   lista exacta de tareas;
-   metadata necesaria para reproducibilidad.

Cambiar la composición o significado del dataset requiere nueva versión.

### 7.2 BenchmarkTask

Representa una tarea reproducible.

Conceptualmente contiene:

-   `id`;
-   `version`;
-   descripción;
-   prompt;
-   fixture;
-   identidad/hash de fixture;
-   tipo de validación;
-   requisitos de build/artifact/Minecraft;
-   criterio de aceptación;
-   requisitos de entorno;
-   tags.

Una modificación semántica de prompt, fixture o PASS requiere nueva
versión.

### 7.3 BenchmarkConfig

Representa la configuración de PD Agent bajo prueba.

Conceptualmente contiene:

-   ID;
-   provider;
-   model;
-   Brain ON/OFF;
-   model config;
-   provider config pública relevante;
-   execution limits;
-   knowledge config;
-   repetition count.

Debe disponer de una identidad/hash estable excluyendo secretos.

### 7.4 BenchmarkRun

Representa una ejecución de una tarea con una configuración concreta.

Debe correlacionar:

-   task/version;
-   config/hash;
-   repetition index;
-   commit de PD Agent;
-   fixture identity;
-   environment snapshot;
-   `run_id` real de PD Agent;
-   timestamps/duración;
-   execution status;
-   task outcome;
-   failure classification;
-   métricas;
-   evidence refs.

### 7.5 BenchmarkComparison

Representa agregación sobre runs ya ejecutadas.

No debe modificar raw evidence ni reinterpretar manualmente resultados
individuales.

Debe mostrar:

-   dataset;
-   configuraciones;
-   runs esperadas;
-   válidas;
-   bloqueadas;
-   inválidas;
-   resultados por tarea;
-   agregados;
-   estado de la comparación.

## 8. Estados de ejecución y resultado

Se separan dos conceptos.

### Execution Status

-   `COMPLETED`: ejecución válida para comparación.
-   `BLOCKED`: no pudo evaluarse correctamente por causa externa al
    comportamiento que se intenta medir.
-   `INVALID`: evidencia inconsistente, contaminación o violación del
    contrato benchmark.

### Task Outcome

-   `PASS`;
-   `FAIL`;
-   `NOT_EVALUATED`.

Una ejecución `BLOCKED` o `INVALID` no debe transformarse
automáticamente en FAIL del agente.

## 9. Clasificación de fallos

La clasificación debe conservar como mínimo el origen:

-   `AGENT`;
-   `PROVIDER`;
-   `BUILD_ENVIRONMENT`;
-   `MINECRAFT_HARNESS`;
-   `BENCHMARK_INFRA`;
-   `CONFIGURATION`;
-   `UNKNOWN`.

Debe permitir códigos específicos, entre ellos:

-   `AGENT_TASK_FAILURE`;
-   `AGENT_BUILD_FAILURE`;
-   `AGENT_FUNCTIONAL_FAILURE`;
-   `PROVIDER_AUTH`;
-   `PROVIDER_RATE_LIMIT`;
-   `PROVIDER_TIMEOUT`;
-   `PROVIDER_UNAVAILABLE`;
-   `BUILD_ENV_FAILURE`;
-   `HARNESS_CRASH`;
-   `HARNESS_TIMEOUT`;
-   `HARNESS_INFRA_ERROR`;
-   `EXECUTION_LIMIT`;
-   `BENCHMARK_CONTAMINATION`.

La clasificación final deberá basarse en evidencia existente y no en
interpretación textual libre del modelo.

## 10. Métricas

### 10.1 Identidad

-   benchmark dataset/version;
-   task/version;
-   config/hash;
-   benchmark run ID;
-   underlying PD Agent run ID;
-   repetition index.

### 10.2 Resultado

-   execution status;
-   task outcome;
-   failure origin;
-   failure code;
-   final build PASS/FAIL;
-   artifact/JAR validation;
-   Minecraft Harness PASS/FAIL cuando aplique.

### 10.3 Ejecución

-   tool-call count;
-   tools utilizadas;
-   build count;
-   agent steps/iteraciones;
-   errores/reintentos observables;
-   duración total.

### 10.4 Configuración

-   provider;
-   model;
-   Brain ON/OFF;
-   configuración pública relevante;
-   execution limits;
-   seed cuando exista y sea aplicable.

### 10.5 Knowledge

Separar obligatoriamente:

-   retrieved;
-   selected;
-   injected;
-   provenance.

Retrieval bookkeeping no equivale a conocimiento inyectado.

### 10.6 Usage y coste

Cuando el provider exponga usage:

-   conservarlo;
-   normalizar los campos comunes útiles;
-   mantener evidencia del dato original cuando sea necesario.

No se inventará usage ausente.

Coste será opcional.

Solo se calculará cuando exista una tabla/snapshot de pricing
identificable y versionado que permita reproducir el cálculo.

### 10.7 Version identity

Registrar cuando aplique:

-   PD Agent commit;
-   fixture hash/version;
-   Minecraft;
-   Fabric Loader;
-   Fabric API;
-   mappings/Yarn;
-   Java;
-   Python;
-   provider;
-   model;
-   configuración relevante.

## 11. Aislamiento

Cada benchmark run debe partir de estado controlado.

Debe usar:

-   workspace nuevo;
-   fixture canónica no modificada;
-   run ID nuevo;
-   outputs propios;
-   build outputs propios;
-   Minecraft runtime/world propio cuando aplique;
-   cleanup controlado;
-   caches con política explícita.

Nunca se benchmarkeará modificando directamente la fixture canónica.

Los procesos Minecraft/Gradle deben cerrarse de forma controlada.

La contaminación detectable debe producir `INVALID`, no un resultado
aparentemente válido.

## 12. Nondeterminismo

Una única ejecución no es suficiente para concluir superioridad.

v0.4 utilizará por defecto:

**3 runs válidas por Task × Config.**

Con tres tareas y Brain OFF/ON:

`3 tasks × 2 configs × 3 valid runs = 18 valid runs objetivo`

El número debe ser configurable para evolución futura.

### 12.1 Orden

Las ejecuciones OFF/ON se intercalarán para reducir sesgos temporales.

No se ejecutarán sistemáticamente todas las OFF y después todas las ON.

### 12.2 Seed

Cuando el provider soporte seed:

-   puede controlarse;
-   debe registrarse.

Una seed idéntica no se tratará como garantía de determinismo.

### 12.3 Fallos transitorios

Una run bloqueada por provider/infraestructura no entra en el
denominador del success rate del agente.

Ejemplo:

`PASS / RATE_LIMIT / PASS`

significa:

-   2 runs válidas;
-   1 bloqueada;
-   success válido `2/2`;
-   celda incompleta respecto al objetivo de 3 runs válidas.

El sistema podrá reintentar obtener la cantidad objetivo dentro de
límites explícitos.

Nunca ocultará las runs bloqueadas originales.

## 13. Agregación

La unidad primaria de análisis es:

`Task × Config`

Para cada celda se mostrarán al menos:

-   valid runs;
-   PASS;
-   FAIL;
-   blocked;
-   invalid;
-   success rate;
-   mediana de duración;
-   rango de duración;
-   mediana/rango de tool calls;
-   mediana/rango de builds;
-   mediana/rango de agent steps;
-   usage/tokens cuando exista;
-   coste cuando sea válido.

La comparación global se realizará después de la comparación por tarea.

Cada tarea tendrá el mismo peso en el macro-agregado inicial.

v0.4 no utilizará estadística inferencial compleja ni afirmaciones de
significancia.

Los resultados mixtos o con runs válidas insuficientes deberán poder
declararse `INCONCLUSIVE`.

## 14. Dataset inicial

Dataset:

`PD_AGENT_BENCHMARK_DATASET_V0.4_1`

Contendrá tres tareas.

### B001 --- Registry lookup

Basada en el escenario conocido de v0.3.

Debe requerir una modificación Fabric/Minecraft sensible a
API/versionado.

PASS objetivo:

`modificación → build PASS → JAR válido → Minecraft Harness PASS`

### B002 --- Version-sensitive API change

Segunda tarea distinta que utilice otra parte de la API
Minecraft/Fabric/Yarn.

Debe ser razonablemente sensible al conocimiento de versión, pero no
construida para garantizar que Brain ON gane.

PASS automático.

### B003 --- Multi-symbol/version-sensitive change

Tarea pequeña pero algo más compleja que requiera relacionar múltiples
símbolos/API.

Debe seguir siendo acotada y automáticamente verificable.

Cuando el comportamiento sea materialmente runtime:

`build + artifact + Minecraft Harness`

serán obligatorios.

### Reglas del dataset

-   selección previa a resultados;
-   fixtures reseteables;
-   criterios objetivos;
-   tareas suficientemente diferentes;
-   ninguna eliminación posterior por resultados desfavorables;
-   cambios semánticos implican nueva versión.

## 15. Brain OFF vs Brain ON

Esta es la aceptación comparativa obligatoria de v0.4.

Ambas configuraciones deben ser idénticas salvo Brain.

Brain OFF:

-   no recibe knowledge externo;
-   no debe ejecutar retrieval externo innecesario para simular
    simetría;
-   registra `brain_enabled=false`.

Brain ON:

-   puede recuperar, seleccionar e inyectar knowledge según el pipeline
    real;
-   debe conservar provenance;
-   registra `brain_enabled=true`.

El benchmark debe permitir que:

-   ambos ganen tareas distintas;
-   empaten;
-   Brain ON empeore;
-   Brain ON mejore.

No existe resultado esperado prefijado.

## 16. Raw evidence y auditabilidad

La evidencia original de una run es inmutable desde la perspectiva del
benchmark.

La agregación referencia evidencia; no la reemplaza.

Cada resultado debe poder rastrearse hasta:

`comparison` → `BenchmarkRun` → PD Agent `run_id` →
`run.json/events/final-report/evidence/builds` → harness evidence cuando
corresponda.

Los summaries son derivados y no deben sustituir a la evidencia
primaria.

## 17. Compatibilidad futura

Las entidades de v0.4 deben permitir posteriormente comparar:

-   Brain strategies;
-   modelos;
-   providers;
-   context strategies;
-   Build/Debug;
-   futuras capacidades.

Esto no significa implementar esas comparaciones ahora.

La extensibilidad se consigue manteniendo `BenchmarkConfig` genérico y
evitando contratos exclusivos de Brain.

## 18. Criterios de aceptación del milestone

v0.4 solo podrá cerrarse cuando exista evidencia de que:

1.  el dataset contiene varias tareas versionadas;
2.  cada run está aislada;
3.  cada run conserva identidad completa;
4.  PASS/FAIL principal es automático;
5.  fallos de infraestructura/provider no se mezclan con FAIL del
    agente;
6.  Brain OFF/ON puede ejecutarse sobre el mismo dataset;
7.  existen múltiples runs válidas por celda;
8.  raw evidence se conserva;
9.  existe agregación por tarea;
10. existe comparación global descriptiva;
11. usage se conserva cuando está disponible;
12. coste no se inventa;
13. la comparación real Brain OFF/ON se ejecuta;
14. regresiones v0.1--v0.3 siguen pasando;
15. tests de v0.4 pasan;
16. documentación reproduce el proceso;
17. commit y push quedan confirmados.

## 19. No objetivos de éxito

No se exige:

-   que Brain ON gane;
-   que exista significancia estadística académica;
-   que todos los providers soporten las mismas métricas;
-   que exista coste para todas las runs;
-   que el benchmark sea público;
-   que exista un ranking universal.

## 20. Decisión de diseño

PD Agent v0.4 será una **Benchmark Foundation local, pequeña y basada en
composición sobre el runtime existente**.

No será un segundo runtime.

Su responsabilidad será:

`definir → aislar → ejecutar → observar → normalizar → repetir → agregar → comparar`

sin alterar el comportamiento que pretende medir.
