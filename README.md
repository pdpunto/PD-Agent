# PD Agent

PD Agent is an AI agent system for Minecraft Fabric projects.

Status: pre-implementation.

v0.1 focus: existing Minecraft Fabric projects.

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
