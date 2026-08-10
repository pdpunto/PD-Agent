# PD Agent v0.1.1 Validation

- Fecha: 2026-08-09T20:36:14.179582+00:00
- Commit validado: d0e3d2d4e596bff59d3ecad4e42db09efc9c9822
- Gemini model ID: gemini-3.1-flash-lite
- SDK version: google-genai 1.75.0
- Fixture: `tests/fixtures/l11_fabric_fixture`
- Run id: `1bfcb794-92d8-4117-848a-ec1b125c6adc`
- Tool calls observadas en runtime: 2
- Tool call count en `run.json`: 1
- Nota: `run.json.tool_call_count` cuenta solo `function_call` serializados en requests; la escritura real fue solicitada por Gemini en el segundo turno y ejecutada por `ToolExecutor`, visible en `events.jsonl`.
- Source path: `src/main/java/dev/pdpunto/l11/ExampleMod.java`
- Source hash before: `434e1ca042f913ed4777c005824b6d99be9c2554375d4b1458737a397a5826b3`
- Source hash after: `1b6e055f58eb7e293a686e90e1fed95a58c4bbce0909d252f95bd65c9f456267`
- ProviderContinuation detectada: true
- Continuation replay: true
- Raw thought signature: not stored
- Gradle result: BUILD SUCCESSFUL
- ArtifactResult: VALID
- JAR: `C:\Users\Usuario\AppData\Local\Temp\pd-agent-v0.1.1-validation\working\live-e2e\build\libs\pd-agent-l11-fixture.jar`
- RunState: COMPLETED
- evaluate_pass: PASS
- Usage: {}
- Secret scan: false
- OpenAI live: NOT RUN (blocked by billing)
- Repair live: NOT RUN
- Minecraft runtime: NOT VALIDATED

## Notes

- Project validation passed with a real Gemini 3 request and a real tool-driven source edit.
- The write was produced by a Gemini tool call, not by harness-side injection.
- No raw continuation payloads or keys are stored here.

## Current Re-run

- Status: BLOCKED
- Reason: `PD_AGENT_PROVIDER` and `GEMINI_API_KEY` are missing in the current environment.
- Re-run date: 2026-08-10
