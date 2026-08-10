# PD Agent v0.2 — Validation

Status: PASS
Date: 2026-08-10

## Repository

- Repository: `pdpunto/PD-Agent`
- Branch: `main`
- Commit validated: `86ab5e32e40da4619e655853a9b3d7b94d43f60a`

## Validation Command

```text
.venv-l0fix\Scripts\python.exe scripts\validation\validate_v0_2.py --validation-root %TEMP%\pd-agent-v0.2-batch-d-3
```

## Runtime Environment

- Java: `21`
- Minecraft: `1.21.11`
- Fabric Loader: `0.19.3`
- Target mod id: `pdagentl11`
- Target JAR: `tests/fixtures/l11_fabric_fixture/build/libs/pd-agent-l11-fixture.jar`

## Validation Root

- `C:\Users\Usuario\AppData\Local\Temp\pd-agent-v0.2-batch-d-3`

## Evidence

- Target build: PASS
- Harness build: PASS
- Positive runtime #1: PASS
- Positive runtime #2: PASS
- Wrong mod id: PASS
- Wrong SHA: PASS
- Functional fail: PASS
- Crash: PASS
- Timeout: PASS
- Missing result: PASS
- Malformed result: PASS
- Final status: PASS

## Final Runtime Evidence

- Target SHA-256: `12b44bc9266867c2f10d392752322209e2826063dcbd6abd3715cabdbf96d82e`
- Target jar path: `C:\Users\Usuario\AppData\Local\Temp\pd-agent-v0.2-batch-d-3\workspace\tests\fixtures\l11_fabric_fixture\build\libs\pd-agent-l11-fixture.jar`
- Runtime result path: `C:\Users\Usuario\AppData\Local\Temp\pd-agent-v0.2-batch-d-3\evidence\pass-1\result.json`
- Harness result path: `C:\Users\Usuario\AppData\Local\Temp\pd-agent-v0.2-batch-d-3\evidence\pass-1\harness-result.json`
- Server-ready evidence: present
- Runtime target hash match: true
- Functional test: PASS
- Clean shutdown: yes
- Process exit: `0`
- Total duration: `466.156167s`

## Scope Notes

- Validation is server-side only.
- Minecraft client runtime, GUI, rendering and human interaction remain out of scope.
- OpenAI live was not part of this batch validation.
