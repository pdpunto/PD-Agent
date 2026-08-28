# PD Agent v0.8 - I16 Post-Runtime PASS Reconciliation Fix

## Scope

This validation records the correction required after the single authorized
I16 live execution `e239eb5d-3877-4735-9e1a-455c4a32cc72`, run
`781b5d69-7db9-4c92-a624-3d0edfdcbf2e`. The historical evidence remains
unchanged and remains `V0_8_I16_FINAL_050_LIVE_FAIL`.

## Root Cause

After the repaired runtime produced `Minecraft #2 PASS`, an observation
mapping-invalid branch constructed `ValidationViolation` without its required
`message` argument. The resulting `TypeError` stopped failure reconciliation
and prevented the CompletionGate from evaluating the resolved failure.

`ValidationViolation.message` is mandatory. All producers now satisfy that
contract, including the mapping-invalid runtime path.

The post-runtime contract is:

`failure -> repair -> rebuild -> current artifact -> runtime PASS -> new PASS
evidence -> resolve the same failure -> requirements satisfied -> CompletionGate`.

The original failure remains append-only as historical `ACTIVE` evidence and
is followed by a matching `RESOLVED` fact with current runtime evidence.

## Flags

The I16 manifest derives `experimental` and `non_official` from CLI flags.
The shared economic session is deliberately false by default because it is
also used by official paths. I16 now passes its explicit CLI values into the
budget guard, so provider response metadata and the manifest use the same
execution provenance without hardcoding `true`.

## Validation

Offline regressions cover the invalid observation mapping, runtime failure
reconciliation, current artifact requirements, CompletionGate, and I16 flag
propagation. Adversarial coverage continues to reject stale/invalid artifacts,
wrong failure identities, missing PASS evidence, generic crashes, timeouts,
and infrastructure failures.

The live execution is not rewritten or converted into PASS. No new API or
Minecraft execution is authorized by this document.
