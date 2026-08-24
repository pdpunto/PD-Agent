# PD Agent v0.5 - Gemini vs Luna Mini A/B Design

Status: DESIGN ONLY. No live execution is authorized by this document.

## Purpose

Measure, descriptively, whether provider/model behavior differs on the same
multi-file Fabric task, with special attention to pipeline depth and semantic
repair convergence. This is an experimental, non-official study and is not
part of the F9 Gemini matrix.

## Scope

- Task: `F6-T2@5`.
- Cell A: `gemini / gemini-3.5-flash-lite`.
- Cell B: `openai / gpt-5.6-luna`, reasoning effort `medium`.
- Brain: ON for both cells.
- Target: 2 valid runs per cell, 4 valid runs total.
- Maximum: 3 attempts per cell, 6 attempts total.
- Frozen order: `Gemini-0, Luna-0, Luna-1, Gemini-1`.
- All runs use fresh experimental execution roots.

The two prior Luna smokes are exploratory evidence only. They are not
repetitions, attempts, replacements, or aggregates for this study.

## Fairness Contract

The following must be byte/semantically identical between providers:

- commit, dataset, task, prompt, acceptance, fixture and Gradle seed;
- Brain, knowledge policy, tools, security and filesystem policy;
- Semantic Repair, PRE_BUILD, runtime repair, build, artifact and harness;
- target mod id, mutation targets and all execution limits;
- evidence schema, validity rules and aggregation rules.

Only provider, model, and the indispensable model-specific reasoning setting
may differ. No provider-specific tuning, prompt changes, threshold changes or
post-result schedule changes are allowed.

## Outcomes and Claims

Execution status and functional outcome are separate:

- `COMPLETED + PASS`: all required evidence and acceptance pass.
- `COMPLETED + FAIL`: a real agent/task failure, including terminal failure
  before downstream evidence that is naturally absent because of that failure.
- `BLOCKED`: provider quota, infrastructure, harness or execution-limit block.
- `INVALID`: contamination, contradictory evidence or methodological invalidity.
- `INCOMPLETE`: the cell has not reached its valid-run target.

Allowed claims are descriptive: PASS counts, pipeline depth, requests, tokens,
repair activation, convergence signals, duration and Luna cost. Statistical
significance, general model superiority, and claims about arbitrary Minecraft
projects are forbidden with `n=2` per provider.

## Isolation and Closure

The experiment must have its own manifest, schedule, state, execution roots and
aggregates. It must not import or mutate F9 execution
`bbfe2a82-fda5-4f7a-bc08-fba8ce66b524`, its schedule, or its evidence.

The study closes only when both cells have 2 valid runs, or when a cell reaches
3 attempts, or when an external quota/infrastructure condition makes further
progress impossible. A rate-limit pause is not a functional failure and keeps
the exact pending attempt for later resume.

