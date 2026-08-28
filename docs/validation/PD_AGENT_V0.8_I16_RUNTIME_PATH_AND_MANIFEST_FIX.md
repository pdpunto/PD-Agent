# PD Agent v0.8 - I16 Runtime Path and Manifest Fix

## Triggering execution

The historical I16 execution `681a53fa-dc13-42ce-a60c-bfc528bd9404` reached
PRE_BUILD repair, a passing build, and a valid current artifact. It stopped
before Minecraft with `SecurityViolation: absolute paths are not allowed`.
Its evidence remains unchanged and is not reinterpreted as a pass.

## Path boundary

`ProductiveMinecraftFunctionalValidator` received the physical absolute path
of the valid artifact, while `MinecraftTestRunner` consumes a path reference
through `SecurePathResolver`. The validator now canonicalizes the physical
path, requires it to remain inside the authorized project root, converts it
to a relative reference, and validates that reference through the existing
resolver. External absolute paths, traversal, missing files, and symlink
escapes remain rejected. `SecurePathResolver` was not weakened.

The runtime handoff is therefore:

```text
valid internal artifact
  -> canonical containment check
  -> relative artifact reference
  -> SecurePathResolver
  -> MinecraftRunner
```

This is an implementation gap only; DESIGN/RFC/IMP architecture is unchanged.

## Manifest flags

The I16 driver previously hardcoded `experimental=false` and
`non_official=false` when writing its redacted manifest. The driver now
accepts explicit `--experimental` and `--non-official` switches, defaults both
to the official values, and persists the effective values without affecting
provider or runtime behavior. Secrets remain excluded from the manifest.

## Validation

- Path boundary, productive runtime, completion, repair, and I16 driver tests:
  `72 passed`.
- No OpenAI or Gemini API was called.
- No Minecraft or benchmark live run was executed.
- The shared economic ledger was read only; no attempt was created.
- The historical execution and its evidence were not modified.
