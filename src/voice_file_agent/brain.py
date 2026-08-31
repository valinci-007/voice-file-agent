"""Brain — the Claude Agent SDK session and the interactive loop.

Uses the local `claude` CLI (your Claude Code subscription login): no API key.
Claude Code's built-in tools are disabled; the agent's whole world is the four
MCP tools from tools.py.
"""

from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

from .config import Settings
from .conversation import Conversation
from .prompts import SYSTEM_PROMPT
from .tools import SERVER_NAME, TOOL_NAMES, build_mac_server

QUIT_WORDS = {"quit", "exit", "q", "bye", "stop"}


def build_options(settings: Settings, convo: Conversation) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        model=settings.model,            # None = your Claude Code default model
        mcp_servers={SERVER_NAME: build_mac_server(settings, convo)},
        allowed_tools=TOOL_NAMES,        # auto-approved
        tools=[],                        # no built-in Claude Code tools
        disallowed_tools=[               # belt and suspenders on top of tools=[]
            "Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebFetch",
            "WebSearch", "Task", "TodoWrite", "NotebookEdit",
        ],
        permission_mode="dontAsk",       # anything not pre-approved is denied
        setting_sources=[],              # ignore CLAUDE.md, user hooks, etc.
        max_turns=settings.max_turns,
        cwd=str(Path.home()),
    )


def _tool_call_summary(name: str, tool_input: dict) -> str:
    short = name.removeprefix(f"mcp__{SERVER_NAME}__")
    parts = [f"{k}={v!r}" for k, v in tool_input.items() if v not in ("", 0, False, None)]
    return f"{short}({', '.join(parts)})"


async def stream_reply(client: ClaudeSDKClient, convo: Conversation) -> None:
    """Consume one full agent turn: print tool activity, speak text replies."""
    async for message in client.receive_response():
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock) and not block.name.endswith("ask_user"):
                    print(f"   ⚙ {_tool_call_summary(block.name, block.input)}")
            text = "".join(
                b.text for b in message.content if isinstance(b, TextBlock)
            ).strip()
            if text:
                await convo.aspeak(text)
        elif isinstance(message, ResultMessage):
            reason = getattr(message, "terminal_reason", None) or getattr(message, "subtype", "")
            if reason and reason not in ("success", "end_turn", "completed"):
                detail = getattr(message, "result", "") or ""
                print(f"   (turn ended: {reason} {detail})".rstrip())


async def run_session(settings: Settings, convo: Conversation, one_shot: str = "") -> None:
    try:
        async with ClaudeSDKClient(options=build_options(settings, convo)) as client:
            if not one_shot:
                print(
                    "voice-file-agent v2  ·  Claude Agent SDK "
                    f"(model: {settings.model or 'your Claude Code default'})"
                    f"  ·  {convo.status_line()}\n"
                    "Press Enter and speak, or type a request. Say or type 'quit' to exit.\n"
                )
            while True:
                user_text = one_shot or await convo.ahear()
                if not user_text:
                    continue
                if user_text.lower().strip(" .!") in QUIT_WORDS:
                    await convo.aspeak("Bye!")
                    break
                try:
                    await client.query(user_text)
                    await stream_reply(client, convo)
                except KeyboardInterrupt:
                    print("\n(interrupted)")
                    try:
                        await client.interrupt()
                    except Exception:
                        pass
                if one_shot:
                    break
    except Exception as e:
        if "CLINotFound" in type(e).__name__:
            raise SystemExit(
                "Could not find the `claude` CLI. Install Claude Code first "
                "(https://claude.com/claude-code) — this agent runs on its login."
            ) from e
        raise
