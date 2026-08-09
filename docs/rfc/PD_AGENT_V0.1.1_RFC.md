# PD Agent v0.1.1 - RFC tecnico

**Estado:** Auditoria y alineacion documental  
**Base:** `8c5af965def541fe160b420b4e7d7bc076090e2c`

## 1. Propósito

Definir la minima extension neutral necesaria para transportar metadata de
continuation del provider, sin meter conceptos Gemini en el core.

## 2. Contrato neutral

Se propone `ProviderContinuation`.

Campos:

- `provider`: identificador del adapter propietario
- `kind`: tipo semanticamente opaco, por ejemplo `thought_signature`
- `target_type`: tipo del elemento destino, por ejemplo `content_part`
- `target_id`: id estable del elemento destino si existe
- `payload`: mapa JSON-safe, opaco para core/runtime
- `position`: referencia positional opcional cuando el protocolo depende del
  orden real de parts

Reglas:

- el core transporta;
- el adapter produce e interpreta;
- el runtime no interpreta;
- el payload debe ser serializable;
- si no lo es, el provider falla antes de persistirlo;
- no se aceptan diccionarios ad-hoc como contrato publico;
- no se almacenan tipos del SDK en el core.

## 3. Gemini 3 mapping

Gemini 3 expone `thought_signature` en `Part` de respuesta.
La documentacion oficial indica:

- para function calling, la firma va en el primer `functionCall` de la step
  actual;
- en calls paralelas, solo el primer `functionCall` lleva signature;
- en steps secuenciales, cada step nuevo vuelve a requerir la firma del
  primer `functionCall`;
- el orden exacto de `Content.parts` importa;
- si la signature falta o se reordena, Gemini devuelve 4xx.

Implicacion:

- `target_id` solo no basta;
- se necesita asociacion exacta al `Part` original;
- el adapter puede usar `position` o equivalente interno para reenviar la
  metadata en el mismo sitio;
- el core no decide nada sobre la estructura interna del payload.

## 4. Lifecycle

1. GeminiProvider recibe una respuesta.
2. Extrae continuations opacas desde los `Part` relevantes.
3. Las expone en `AgentResponse.provider_continuations`.
4. AgentRuntime las transporta al siguiente `AgentRequest`.
5. GeminiProvider reconstruye el historial Gemini exacto.
6. OpenAIProvider ignora el campo si no lo usa.

Las continuations solo deben vivir mientras duren los turnos que las necesitan.
No hace falta guardarlas en historico largo si el provider no las consume.

## 5. Error model

Fallo explicito, normalizado, antes que reconstruccion inventada.

Casos:

- continuation ausente cuando Gemini la necesita -> `ProviderError(kind=protocol)`
- provider incorrecto -> `ProviderError(kind=protocol)`
- target inexistente -> `ProviderError(kind=protocol)`
- payload corrupto -> `ProviderError(kind=protocol)`
- payload no serializable -> `ProviderError(kind=protocol)`
- duplicados conflictivos -> `ProviderError(kind=protocol)`
- Gemini rechaza replay -> `ProviderError(kind=protocol)`

## 6. Security y reporting

La evidence no debe volcar payload opaco completo por defecto.
Se recomienda persistir solo:

- provider
- kind
- target_type
- target_id o position
- presencia/ausencia
- hash seguro opcional

Si el payload tiene contenido sensible, el redactor debe tratarlo como parte
de la superficie secreta del provider.

## 7. OpenAI compatibility

OpenAIProvider no cambia de semantica.
Si el campo llega vacio, se ignora.
Si en algun momento OpenAI necesitara metadata opaca, se maneja con el mismo
contrato neutral, no con tipos OpenAI dentro del core.

## 8. Acceptance

La extension se considera pequena si:

- no cambia el rol del runtime;
- no mete tipos Gemini en core;
- no toca SecurityPolicy ni ToolExecutor;
- no obliga a un framework universal;
- solo anade transporte neutral y mapping de adapter.
