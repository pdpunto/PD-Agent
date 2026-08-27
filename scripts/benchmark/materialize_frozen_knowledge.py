"""Materialize the approved offline v0.7 I16 knowledge pack."""

from __future__ import annotations

import argparse
from pathlib import Path

from pd_agent.brain import (
    FabricApiKnowledgeSource,
    FabricConceptPatternKnowledgeSource,
    KnowledgeEnvironment,
    KnowledgePackStore,
    YarnKnowledgeSource,
    materialize_frozen_knowledge_pack,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize a frozen v0.7 I16 knowledge pack")
    parser.add_argument("--yarn-artifact", required=True, type=Path)
    parser.add_argument("--fabric-api-artifact", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    environment = KnowledgeEnvironment(
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        loom_version="1.13.3",
        mappings_namespace="yarn",
        mappings_version="1.21.11+build.6",
        fabric_api_version="0.141.6+1.21.11",
        java_version="21",
    )
    pack = materialize_frozen_knowledge_pack(
        (
            YarnKnowledgeSource(artifact_bytes=args.yarn_artifact.read_bytes()),
            FabricApiKnowledgeSource(artifact_bytes=args.fabric_api_artifact.read_bytes()),
            FabricConceptPatternKnowledgeSource(),
        ),
        environment=environment,
        target=args.output,
    )
    print(pack.manifest.pack_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
