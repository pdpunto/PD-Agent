# PD Agent v0.1.1 - Provider Continuation Metadata

**Estado:** Auditoria y alineacion documental  
**Base:** `8c5af965def541fe160b420b4e7d7bc076090e2c`

## 1. Objetivo

PD Agent sigue siendo un runtime pequeno, single-agent y provider-neutral.
La nueva necesidad es soportar Gemini 3 sin meter `thought_signature` en el
core.

## 2. Causa concreta

Gemini 2.5 ya no es viable para esta key en Free Tier. Gemini 3 si responde,
pero su function calling exige conservar metadata de continuation opaca,
incluida la thought signature, en el `Part` correcto y en el orden correcto.

## 3. Decision de diseno

La solucion aprobada es una continuation opaca y neutral, transportada por el
core y entendida solo por el adapter correspondiente.

Principios:

- `ModelProvider` sigue provider-neutral;
- `AgentRuntime` sigue provider-neutral;
- el core no interpreta metadata del provider;
- el runtime solo transporta metadata;
- solo `GeminiProvider` interpreta la continuation;
- `OpenAIProvider` conserva su comportamiento actual;
- no se crea un tipo Gemini en el core;
- no se introduce un framework universal de protocolos;
- no se modela `thought_signature` como concepto de producto.

## 4. Forma conceptual

Se introduce un contrato neutral pequeno, llamado `ProviderContinuation`,
para transportar metadata opaca asociada a un elemento concreto de la
respuesta del provider.

Campos conceptuales:

- `provider`
- `kind`
- `target_type`
- `target_id`
- `payload` JSON-safe

La identidad real no depende solo de `target_id` cuando el protocolo usa
posicion u orden. El adapter puede necesitar una referencia positional
adicional, pero el core sigue sin interpretar nada.

## 5. Reglas de semantica

- la continuation pertenece al provider que la genero;
- el payload es opaco para el core;
- el payload debe ser serializable;
- si falta o esta corrupto, el provider debe fallar de forma explicita;
- si no hace falta, el provider puede devolver lista vacia;
- OpenAI no necesita cambio funcional;
- la evidence no debe exponer el payload opaco completo salvo necesidad
  estricta.

## 6. Alcance de v0.1.1

v0.1.1 queda reducido a la alineacion documental de este contrato y a su
posterior implementacion en un lote pequeno.
No cambia el alcance del producto ni introduce nuevos providers.

## 7. Cierre

Este diseno confirma que la continuidad opaca es una extension pequena y
evolutiva del modelo actual. Si la implementacion confirma lo mismo, puede
entrar en un unico lote posterior.
