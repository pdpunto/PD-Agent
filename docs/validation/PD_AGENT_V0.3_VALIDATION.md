# PD Agent v0.3 Validation

Status: PASS
Date: 2026-08-10

## Repository

- Repository: `pdpunto/PD-Agent`
- Branch: `main`
- Commit validated: `162c652355a011579e750bb66dd27b44adcc5340`

## Validation Command

```text
python .\scripts\validation\validate_v0_3.py
```

## Runtime Environment

- Java: `21.0.11`
- Minecraft: `1.21.11`
- Fabric Loader: `0.19.3`
- Loom: `1.13.3`
- Mappings: `1.21.11+build.6`
- Mappings namespace: `yarn`
- Target mod id: `pdagentl11`
- Target JAR: `build/libs/pd-agent-l11-fixture.jar`

## Validation Root

- `%TEMP%\pd-agent-v0.3-validation`

## Brain Comparison

| Aspect            | Brain OFF | Brain ON |
| ------------------ | --------- | -------- |
| External knowledge | `0` | `1` |
| Provenance         | no external provenance | Yarn provenance preserved |
| Retrieved items    | `5` | `5` |
| Selected/context   | `3 / 3` | `3 / 3` |
| Tool calls         | `3` | `2` |
| Build              | PASS | PASS |
| JAR                | VALID | VALID |
| Minecraft          | PASS | PASS |
| Functional result  | PASS | PASS |
| Final result       | PASS | PASS |

## Brain OFF

- Provider: `gemini`
- Model: `gemini-3.1-flash-lite`
- External knowledge count: `0`
- Tool calls: `3`
- Diff produced:
  - `Blocks.DIAMOND_BLOCK` -> `Registries.BLOCK.get(Identifier.ofVanilla("diamond_block")).getDefaultState()`
- Build: `BUILD SUCCESSFUL`
- JAR: `VALID`
- Minecraft runtime: `PASS`
- Behaviour: the agent completed the same source edit without external context.
- Result: `PASS`

## Brain ON

- Provider: `gemini`
- Model: `gemini-3.1-flash-lite`
- Yarn artifact: `net.fabricmc:yarn:1.21.11+build.6:v2`
- Yarn checksum: `e8112359716235dc4fd7f0bd4a6162fd728e0d1067d9fa02f289edaaccd37718`
- Provenance:
  - source id: `net.fabricmc:yarn`
  - source kind: `yarn-mappings`
  - revision: `1.21.11+build.6`
  - license: `CC0-1.0`
- Retrieved items: `5`
- Selected items: `3`
- Context items: `3`
- Rejected items: `2`
- Rejection reason: `CONTEXT_BUDGET`
- Tool calls: `2`
- Diff produced:
  - `Blocks.DIAMOND_BLOCK` -> `Registries.BLOCK.get(Identifier.of("minecraft", "diamond_block")).getDefaultState()`
- Build: `BUILD SUCCESSFUL`
- JAR: `VALID`
- Minecraft runtime: `PASS`
- Behaviour: retrieved Yarn knowledge was added to context and used to produce the registry-based fix.
- Result: `PASS`

## Criterion Rector

`SATISFIED`

- external knowledge: yes, Yarn 1.21.11+build.6
- version match: yes, Minecraft 1.21.11 / Loader 0.19.3 / Loom 1.13.3
- provenance: yes, CC0-1.0 and checksum recorded
- ContextSource: yes, external knowledge entered the agent context
- real provider: yes, `GeminiProvider`
- code modification: yes, real source edit in `ExampleMod.java`
- build: yes, `BUILD SUCCESSFUL`
- JAR: yes, `VALID`
- Minecraft: yes, runtime harness PASS
- behavior: yes, same target state validated by the harness

## Evidence

- Validation summary: `%TEMP%\pd-agent-v0.3-validation\evidence\summary.json`
- Brain OFF code evidence: `%TEMP%\pd-agent-v0.3-validation\evidence\acceptance\brain-off\61e6527b-e26f-4ff5-b6c9-6a7104d3122b\build.json`
- Brain ON code evidence: `%TEMP%\pd-agent-v0.3-validation\evidence\acceptance\brain-on\0ddcfd30-d9d7-463d-b9ee-a03f5fc17640\build.json`
- Knowledge traces:
  - `%TEMP%\pd-agent-v0.3-validation\evidence\acceptance\brain-on\0ddcfd30-d9d7-463d-b9ee-a03f5fc17640\evidence\0001-knowledge-trace.json`
  - `%TEMP%\pd-agent-v0.3-validation\evidence\acceptance\brain-on\0ddcfd30-d9d7-463d-b9ee-a03f5fc17640\evidence\0002-knowledge-trace.json`

## Scope Notes

- Brain OFF and Brain ON were both executed.
- Regression suite passed.
- Minecraft runtime was validated.
- No new capability beyond the documented v0.3 acceptance was added.
