"""CLI foundation for PD Agent."""

from __future__ import annotations

import argparse
from typing import Sequence

from . import __version__
from .config import load_config
from .logging import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pd-agent",
        description="PD Agent v0.1 foundation.",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        help="Override log level from environment.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"pd-agent {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    config = load_config()
    if args.log_level:
        config = load_config({"PD_AGENT_LOG_LEVEL": args.log_level})
    configure_logging(config.log_level)

    if argv is None:
        return 0

    return 0

