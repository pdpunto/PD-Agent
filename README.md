# PD Agent

PD Agent is an AI agent system for Minecraft Fabric projects.

Status: v0.2 Minecraft Test Harness validated.

v0.1 focus: existing Minecraft Fabric projects.
v0.2 adds the server-side Minecraft test harness and validation flow.

Run:

```text
pd-agent run --project <path> --task "<text>"
```

Config:

- `OPENAI_API_KEY` for the OpenAI adapter;
- `PD_AGENT_MODEL` for the model;
- `PD_AGENT_RUNS_DIR` for run artifacts.

v0.1 PASS means:

- final build exit code is `0`;
- the Fabric JAR is valid;
- the final report is persisted and traceable.

v0.1 does not validate Minecraft runtime behavior.

Docs:
- [Design](docs/design/PD_AGENT_V0.1_DESIGN.md)
- [Architecture](docs/architecture/PD_AGENT_V0.1_ARCHITECTURE.md)
- [RFC](docs/rfc/PD_AGENT_V0.1_RFC.md)
- [IMP](docs/implementation/PD_AGENT_V0.1_IMP.md)
- [v0.2 Design](docs/design/PD_AGENT_V0.2_MINECRAFT_TEST_HARNESS_DESIGN.md)
- [v0.2 RFC](docs/rfc/PD_AGENT_V0.2_MINECRAFT_TEST_HARNESS_RFC.md)
- [v0.2 IMP](docs/implementation/PD_AGENT_V0.2_MINECRAFT_TEST_HARNESS_IMP.md)
- [v0.2 Validation](docs/validation/PD_AGENT_V0.2_VALIDATION.md)
