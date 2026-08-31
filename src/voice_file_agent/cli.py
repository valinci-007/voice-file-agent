"""Command-line entry point: parse args, wire the pieces, run the loop."""

from __future__ import annotations

import argparse
import asyncio
import os

from . import __version__, brain, diagnostics
from .config import Settings
from .conversation import build_conversation


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="voice-file-agent",
        description="Voice-driven file finder/opener for macOS",
    )
    p.add_argument("query", nargs="*", help="one-shot request; omit for interactive mode")
    p.add_argument("-q", "--quiet", action="store_true", help="don't speak replies aloud")
    p.add_argument("--voice", default=os.environ.get("SAY_VOICE"), help="macOS say voice name")
    p.add_argument("--model", default=os.environ.get("FILE_AGENT_MODEL"),
                   help="e.g. sonnet, opus, haiku; default = your Claude Code model")
    p.add_argument("--scope", default="~", help="default folder to search under")
    p.add_argument("--typed", action="store_true", help="keyboard input only (no mic)")
    p.add_argument("--stt-model", default=os.environ.get("FILE_AGENT_STT", "base.en"),
                   help="whisper model: tiny.en, base.en (default), small.en, ...")
    p.add_argument("--selftest", action="store_true", help="test macOS tools without Claude")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p.parse_args(argv)


def settings_from_args(args: argparse.Namespace) -> Settings:
    return Settings(
        quiet=args.quiet or args.selftest,
        voice=args.voice,
        scope=args.scope,
        typed=args.typed,
        model=args.model,
        stt_model=args.stt_model,
    )


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    settings = settings_from_args(args)

    if args.selftest:
        diagnostics.run(settings)
        return

    convo = build_conversation(settings)
    one_shot = " ".join(args.query).strip()
    try:
        asyncio.run(brain.run_session(settings, convo, one_shot))
    except KeyboardInterrupt:
        print("\nBye!")
