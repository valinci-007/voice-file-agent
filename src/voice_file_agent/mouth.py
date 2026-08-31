"""Mouth — macOS `say` text-to-speech."""

from __future__ import annotations

import asyncio
import re
import subprocess

from .config import Settings


class Mouth:
    def __init__(self, settings: Settings):
        self.settings = settings

    def speak(self, text: str) -> None:
        """Print the assistant's words and read them aloud."""
        clean = re.sub(r"[*#`]", "", text).strip()  # keep _ — it appears in filenames
        if not clean:
            return
        print(f"\n🤖 {clean}\n")
        if self.settings.quiet:
            return
        cmd = ["say"]
        if self.settings.voice:
            cmd += ["-v", self.settings.voice]
        try:
            subprocess.run(cmd + ["--", clean], timeout=120)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass  # never let TTS take the agent down

    async def aspeak(self, text: str) -> None:
        """speak() without blocking the event loop that pumps the Claude session."""
        await asyncio.to_thread(self.speak, text)
