"""Runtime settings, resolved once at startup and passed explicitly."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    quiet: bool = False          # suppress TTS output
    voice: str | None = None     # macOS `say` voice name (None = system default)
    scope: str = "~"             # default Spotlight search root
    typed: bool = False          # keyboard input only, no mic
    model: str | None = None     # Claude model; None = the user's Claude Code default
    stt_model: str = "base.en"   # faster-whisper model name
    max_turns: int = 30          # safety cap on agent-loop turns per request
