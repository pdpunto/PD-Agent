# PD Agent v0.8 - I14 Offline Adversarial Validation

## Baseline and scope

- Baseline: `e1dffe1cdf89e9e07593aa8f947c823084d256a6`
- Scope: offline/adversarial validation of I1-I13.
- No provider, API, Minecraft live, benchmark live, or historical evidence
  mutation was performed.

## Adversarial matrix

The dedicated I14 regression file covers:

- duplicate requirement IDs and dangling/missing ledger evidence;
- invalid `ACTIVE`/`RESOLVED` failure transitions and resolution evidence;
- contract revision mismatch and legacy `COMPLETED` state;
- build/artifact/runtime currentness after source revision changes;
- readable-but-stale evidence that cannot satisfy CompletionGate;
- traversal, absolute paths, and shell-like path inputs;
- reporting events that cannot control completion;
- product completion separated from benchmark outcome;
- finite agent/tool limits;
- reporting payloads without benchmark oracle leakage.

Existing regression suites additionally cover Brain OFF/ON, build and artifact
normalization, runtime and semantic repair, bootstrap, benchmark isolation,
redaction, and the I13 reporting lifecycle.

## Results

- Dedicated adversarial tests: `12 passed`
- I13 observability tests: `7 passed`
- No product defect demonstrated.
- No architectural or documentation delta required.
- CompletionGate remains the sole deterministic completion authority.
- Historical evidence and `scripts/benchmark/diagnostics/` remain untouched.

## Checks

The complete test suite, `compileall`, and `git diff --check` are run as the
I14 release gate. Live counters are all zero:

- Network external: `0`
- OpenAI: `0`
- Gemini: `0`
- Minecraft live: `0`
- Benchmark live: `0`

## Verdict

`V0_8_I14_PASS`
