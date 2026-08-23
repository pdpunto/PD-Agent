# GPT-5.6 Luna Experimental Smoke

This is a non-official, one-run experiment for `F6-T2@5`. It is isolated from
the F9 scheduler and never contributes repetitions, attempts, replacements or
official aggregates.

The launcher is `scripts/benchmark/run_luna_experimental.py`. It requires a
new `LaunchRoot`, creates a new `ExecutionRoot`, validates the frozen task and
limits, and writes `experimental-manifest.json` with `experimental=true` and
`non_official=true`.

`pd_agent.experimental.LunaBudgetGuard` is deliberately provider-local and
experimental. It reserves the conservative cost of the actual serialized
request plus the 128K output maximum before every physical OpenAI request.
Retries use the same gate. A response must contain coherent usage; missing or
incoherent usage, unknown billable failures, unknown context bounds, and an
accumulated cost above `$1.00` fail closed as `budget_blocked`.

The pricing snapshot is embedded only in this experimental module. Reasoning
tokens are reported separately and charged once as output tokens. API keys and
encrypted reasoning content are never written to the experimental manifest.

No live execution is authorized by this document.
