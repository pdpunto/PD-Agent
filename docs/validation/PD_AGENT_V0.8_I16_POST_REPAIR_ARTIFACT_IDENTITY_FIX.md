# PD Agent v0.8 - I16 Post-Repair Artifact Identity Reconciliation

## Incident

The authoritative I16 run `c4c6d0e9-5450-4be9-b0c6-74f0f807820c` reached a
target startup failure, performed a legitimate repair mutation, and produced
a second valid artifact. The second runtime was blocked as
`runtime artifact identity is stale` before Minecraft was invoked.

## Root Cause

`ProductiveMinecraftFunctionalValidator` rejected every artifact identity that
differed from the identity already held by `RunState`. That rejected the
normal post-repair transition even though the supplied artifact had just been
validated and was bound to the latest successful build and source revision.

## Contract and Fix

The v0.8 currentness contract requires:

`repair -> new source revision -> new build -> new valid artifact -> new runtime`

Currentness remains identity-based. The validator now publishes the newly
validated identity as the current `RunState.artifact_identity` before runtime
validation. Previous runtime failures and evidence remain persisted and are
superseded only by objective current evidence; no stale artifact is accepted.
The existing `FabricRuntimeOrchestrator` continues to reject missing,
unvalidated, mismatched, or externally unconfined artifacts.

## Regression Evidence

Offline regression covers artifact A runtime failure, a source mutation, build
B, artifact B validation, replacement of the current identity, and runtime B
PASS. Existing stale-artifact, invalid-artifact, security-boundary, timeout,
and harness-blocking tests remain applicable.

The historical execution and its evidence remain unchanged. No live/API,
Minecraft live, or benchmark execution is part of this fix.
