# PD Agent v0.8 - I16 ObservationRequest Runtime Fix

## Incident

Execution `f7a845b8-4afe-4cc9-85ec-f5f9b26214af`, run
`8c9216f8-827b-4460-b42b-921a6f37f39b`, reached Semantic Repair, PRE_BUILD
PASS, a successful build, and a valid current artifact. It then stopped before
Minecraft with:

`ValueError: ObservationRequest contains unknown fields: ['observation_params', 'required']`

The historical execution remains unchanged and is still recorded as
`V0_8_I16_FINAL_LIVE_INDETERMINATE`.

## Root Cause

The I16 driver copied benchmark acceptance fields into the productive runtime
observation payload. `ObservationRequest` is a closed envelope and accepts
`observation_id`, `observation_type`, `profile`, `selector`, `expected`,
`parameters`, `phase`, and `metadata`. `required` belongs to the enclosing
`FabricValidationRequirement`, while `observation_params` belongs to the
Minecraft runner specification, not to `ObservationRequest`.

## Correct Mapping

For the registry observation, the driver now maps `observation_params` to the
typed `selector`, uses `{"present": true}` as the expected semantic result,
and keeps the requirement relationship in the orchestrator's explicit
`observation_requirements` mapping. The Minecraft runner still receives the
original `observation_type` and `observation_params` through the validation
spec. No benchmark-only schema is imported into the productive runtime
boundary.

## Validation

- Offline regression verifies both I16 observations construct as valid
  `ObservationRequest` instances and preserve their requirement mapping.
- No OpenAI or Gemini API was called.
- No Minecraft or benchmark live run was executed.
- The shared I16 ledger was read only; no attempt was created.

The only remaining I16 evidence after this offline fix is a newly authorized
Minecraft-integrated execution that reaches `CompletionGate PASS`.

## Economic Ceiling Configuration

The I16 driver does not hardcode an operational shared-budget ceiling. Every
PRECHECK and LIVE invocation must provide `--global-budget-ceiling` explicitly.
The driver validates that value against the persisted shared ledger before
constructing a live provider session, and uses the same value for the LIVE
load. A mismatch, malformed value, non-positive value, or invalid ledger is
fail-closed; no migration or automatic adoption of the ledger ceiling occurs.
The previously supported `0.30` ceiling remains valid when explicitly passed,
and the current I16 ledger is validated with `0.35`.
