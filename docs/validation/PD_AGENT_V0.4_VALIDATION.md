# PD Agent v0.4 Validation

Status: PASS
Date: 2026-08-14

## Repository

- Repository: `pdpunto/PD-Agent`
- Branch: `main`
- Commit validated: `d2966403ded33e9f7100002fddf452718a8bf78a`

## Validation Scope

Official post-wiring benchmark matrix for PD Agent v0.4.

## Dataset

- Dataset ID: `PD_AGENT_BENCHMARK_DATASET_V0.4_2`
- Dataset version: `0.4.2`

## Official Matrix

- Runs expected: `18`
- Runs valid: `18`
- Runs invalid: `0`
- Runs blocked: `0`
- Replacements: `0`
- Comparison status: `COMPLETE`
- Batch status: `COMPLETED`

## Execution Root

- `C:\Users\Usuario\AppData\Local\Temp\pd-agent-v0.4-official-launch-20260814-204850-235\execution\e86d7abe-aae4-4f5d-bd37-8b751be6323c`

## Configuration

| Config | Provider | Model | Brain | Config hash |
| ------ | -------- | ----- | ----- | ----------- |
| `cfg-off` | `gemini` | `gemini-3.5-flash-lite` | `false` | `3b2c765710adc73cdb1cd1cccbf99343a03c731bca65edc3f58e1af80d18987e` |
| `cfg-on` | `gemini` | `gemini-3.5-flash-lite` | `true` | `afd454ee706caad7a8723184f65b6d68ee91a9cf8eeaca5dbe5c82cf20fd0009` |

## Aggregated Result

### Brain OFF

- Valid runs: `9/9`
- Task success: `100%`
- Requests: `54`
- Total tokens: `221731`
- Brain retrieval / selection / injection: `0 / 0 / 0`

### Brain ON

- Valid runs: `9/9`
- Task success: `100%`
- Requests: `57`
- Total tokens: `335599`
- Brain retrieval / selection / injection: `5 / 3 / 3` on B001/B003 where Brain applied

### Batch Totals

- Logical requests: `111`
- Total tokens: `557330`
- Builds: `18`
- 429 responses: `0`
- Provider errors: `0`
- Logical session cap: `400`
- Logical budget used: `111`
- Logical budget remaining: `289`

## Descriptive Delta

- Requests per run: OFF `6.0`, ON `6.333...`
- Tokens per run: OFF `24636.778...`, ON `37288.778...`
- Approximate delta requests/run: `+5.56%`
- Approximate delta total tokens/run: `+51.32%`
- Approximate delta duration/run: `+5.42%`

## Brain Summary

- Brain OFF: no external knowledge injected; retained evidence and runtime context did not contaminate the provider with Brain knowledge.
- Brain ON: Yarn retrieval/provenance was valid where applicable and external knowledge was injected only through the Brain path.
- The official matrix shows the expected fairness split: same task, same dataset, same provider/model, same limits, only `brain_enabled` differs.

## Historical Matrix Treatment

The pre-fix matrix is superseded and should be treated as diagnostic history, not as valid OFF vs ON evidence. The blocking bug was that Brain OFF omitted `ExternalContextSource` from the runtime path, so OFF and ON were not operating under the same runtime context contract.

## Budget / Resume

- Logical session cap: `400`
- Official matrix used: `111`
- Budget pause was not required for the official matrix
- Budget-stop / resume is implemented and validated offline
- Multi-day operation remains a safety option, not a requirement for the official matrix

## Cost Status

No pricing snapshot was persisted for this closure, so monetary cost is not calculated.

## Evidence

- Execution summary: [`execution_state.json`](C:/Users/Usuario/AppData/Local/Temp/pd-agent-v0.4-official-launch-20260814-204850-235/execution/e86d7abe-aae4-4f5d-bd37-8b751be6323c/execution_state.json)
- Manifest: [`manifest.json`](C:/Users/Usuario/AppData/Local/Temp/pd-agent-v0.4-official-launch-20260814-204850-235/execution/e86d7abe-aae4-4f5d-bd37-8b751be6323c/manifest.json)
- Comparison: [`comparison.json`](C:/Users/Usuario/AppData/Local/Temp/pd-agent-v0.4-official-launch-20260814-204850-235/execution/e86d7abe-aae4-4f5d-bd37-8b751be6323c/comparison.json)
- Human-readable comparison: [`comparison.md`](C:/Users/Usuario/AppData/Local/Temp/pd-agent-v0.4-official-launch-20260814-204850-235/execution/e86d7abe-aae4-4f5d-bd37-8b751be6323c/comparison.md)

## Scope Notes

- The official matrix is the authoritative closure evidence for v0.4.
- No new benchmark runs were executed in this documentation closure step.
- No provider API calls were made while preparing this document.
