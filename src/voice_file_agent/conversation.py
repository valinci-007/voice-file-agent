"""Conversation — the human side of the loop: voice/typed input, spoken output.

Owns the input policy: voice-first with typed fallback, hands-free listening
for answers to the agent's questions, and EOF -> "quit".
"""

from __future__ import annotations

import asyncio

from .config import Settings
from .ears import Ears
from .mouth import Mouth


class Conversation:
    def __init__(self, settings: Settings, mouth: Mouth, ears: Ears | None,
                 no_voice_reason: str = ""):
        self.settings = settings
        self.mouth = mouth
        self.ears = ears  # None -> typed mode
        self.no_voice_reason = no_voice_reason

    @property
    def voice_on(self) -> bool:
        return self.ears is not None

    def status_line(self) -> str:
        if self.voice_on:
            return f"🎙 voice input on (whisper {self.ears.model_name})"
        return f"⌨️ typed mode ({self.no_voice_reason})"

    def speak(self, text: str) -> None:
        self.mouth.speak(text)

    async def aspeak(self, text: str) -> None:
        await self.mouth.aspeak(text)

    def hear(self, prompt: str = "🎤 you> ", auto_listen: bool = False) -> str:
        """Get the user's next utterance.

        Voice mode: Enter starts the mic and recording stops when you pause;
        typing text instead still works. With auto_listen=True (answers to
        ask_user) the mic opens immediately — no keypress needed. Falls back
        to typed input whenever nothing was heard.
        """
        if self.voice_on:
            if not auto_listen:
                try:
                    typed = input(f"{prompt}(Enter = 🎙 speak, or type) ").strip()
                except EOFError:
                    return "quit"
                if typed:
                    return typed
            text = self.ears.listen()
            if text:
                return text
            print("   (didn't catch that — type it instead)")
        try:
            return input(prompt).strip()
        except EOFError:
            return "quit"

    async def ahear(self, prompt: str = "🎤 you> ", auto_listen: bool = False) -> str:
        return await asyncio.to_thread(self.hear, prompt, auto_listen)


def build_conversation(settings: Settings) -> Conversation:
    """Wire mouth + ears according to settings and availability."""
    mouth = Mouth(settings)
    if settings.typed:
        return Conversation(settings, mouth, None, "--typed flag")
    ok, why = Ears.available()
    if not ok:
        return Conversation(settings, mouth, None, why)
    return Conversation(settings, mouth, Ears(settings.stt_model))
