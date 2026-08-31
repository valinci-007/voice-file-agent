"""voice-file-agent — a voice-driven agentic file finder/opener for macOS.

The package follows the metaphor used throughout the docs:
  ears.py          mic capture + local Whisper speech-to-text
  brain.py         Claude Agent SDK session and the agentic loop
  hands.py         macOS primitives: Spotlight search, open/reveal, app list
  mouth.py         macOS `say` text-to-speech
  conversation.py  the human side: voice/typed input, spoken output
  tools.py         exposes hands + ask_user to Claude as an MCP server
"""

__version__ = "0.2.0"
