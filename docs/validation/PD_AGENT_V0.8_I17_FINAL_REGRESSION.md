# PD Agent v0.8 - I17 Final Regression Evidence

## Scope and status

This document records the I17 technical regression gate for the v0.8
Autonomous Fabric Agent Foundation. It does not declare formal v0.8 closure;
that decision belongs to 00 Direccion.

- Baseline: `8f6fcd53cf4671587a7c9a5003846d33fc171d3f`
- Branch: `main`
- HEAD and `origin/main`: identical at the baseline above
- Tracked working tree: clean
- `scripts/benchmark/diagnostics/`: pre-existing untracked directory, untouched

## Regression suite

- Full suite: `1125 passed, 3 skipped`
- The skips are environment-capability skips for symlink/console-script
  conditions; no new `xfail` or failure was introduced.
- The suite emitted only the known pytest cache warning caused by protected
  `.pytest_cache` access; it did not affect test results.
- Focused v0.8 acceptance: `377 passed, 1 skipped`
- Compileall: PASS (`python -m compileall -q src tests`)
- `git diff --check`: PASS

## Acceptance coverage

The focused set covers the following v0.8 gates:

- `FabricTaskContract`, execution plan and `TaskProgressLedger`.
- Identity-based currentness, build normalization/orchestration and
  `ArtifactValidator`.
- Brain normal-run wiring, knowledge/repair integration and security tools.
- Runtime validation, target-crash normalization, generic crash, timeout and
  infrastructure blocking semantics.
- Semantic Repair, failure reconciliation and `CompletionGate`.
- Normal Fabric orchestration, pinned bootstrap and benchmark adapter
  isolation.
- Observability/reporting and productive Minecraft runtime wiring.
- Runtime artifact path security and stale/invalid artifact rejection.
- Artifact A-to-B replacement and post-runtime PASS reconciliation.
- Runtime observation mapping, including
  `REGISTRY_ENTRY_PRESENT -> ObservationResult`.
- Economic lifecycle, pure preview and `experimental`/`non_official`
  propagation.

## Deterministic end-to-end regression

The offline regression suite validates the complete evidence chain:

`requirement -> plan -> Brain context -> mutation -> PRE_BUILD -> repair ->`
`build A -> artifact A VALID/current -> runtime A REPAIRABLE_FAIL ->`
`Semantic Repair -> build B -> artifact B VALID/current -> runtime B ->`
`structured observations -> current evidence -> failure reconciliation ->`
`requirements satisfied -> CompletionGate PASS`.

The tests retain the critical boundaries rather than replacing them with a
single mock result. Runtime failures remain classified and repaired only with
new source/build/artifact/runtime evidence.

## v0.7 regression and security

Existing v0.7 compatibility coverage remains PASS for Knowledge Pack loading,
Brain ON/OFF semantics, selection/injection, security gates, Gradle
seed/materialization contracts, artifact validation, Harness result handling,
and benchmark compatibility. No F9 execution was resumed or reinterpreted.

Security regression coverage remains PASS for traversal and external-path
rejection, stale/invalid artifacts, secret redaction, fail-closed economic
uncertainty, and CompletionGate bypass prevention.

## Economic state

The shared I16 ledger was read-only during this gate and remains:

- ceiling: `$0.56`
- confirmed: `$0.5207284500`
- remaining: `$0.0392715500`
- reserved: `$0`
- uncertain: `$0`
- active attempt: `None`
- attempt ceiling: `$0.10`
- reconciliation: `CLEAR`
- physical requests: `128`
- logical provider turns: `130`
- retries: `0`

No migration, preview, provider request or external API call was made.

## Historical I16 evidence

The historical execution remains immutable:

- Execution: `21d95008-58e2-46b5-9239-95ae14939ed2`
- Run: `abe36ac0-91b4-4e48-b06d-eea8c2993c9e`
- Historical status: `V0_8_I16_FINAL_056_LIVE_INDETERMINATE`
- Historical runtime artifact SHA: `8bc1cc60aaafa8a0a6dcc47281cac88e027986d6659833840cabd8c509ab1317`

The historical artifact is evidence of the prior live execution and is not
claimed as a newly produced artifact for the current HEAD. The post-fix
runtime observation mapping is covered by the current deterministic tests and
the closure-equivalence rationale previously audited.

## I17 result

All I17 gates pass: regression suite, focused acceptance, compileall,
diff-check, v0.7 protection, security, economic read-only integrity,
historical evidence integrity, observation mapping and CompletionGate
semantics. No product defect or capability gap was demonstrated.

Technical verdict: `V0_8_I17_FINAL_REGRESSION_PASS`

Formal v0.8 closure remains pending the decision of 00 Direccion.
