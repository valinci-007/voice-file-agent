"""Tools — what Claude is allowed to do, exposed as an in-process MCP server.

Thin wrappers over hands.py plus ask_user (the clarification channel). This is
deliberately the agent's *entire* capability surface: no delete, move, or
rename exists here, so the model can't be talked into destructive actions.
"""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from . import __version__, hands
from .config import Settings
from .conversation import Conversation

SERVER_NAME = "mac"
TOOL_NAMES = [
    f"mcp__{SERVER_NAME}__{n}"
    for n in ("search_files", "open_path", "list_installed_apps", "ask_user")
]


def _text(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def build_tools(settings: Settings, convo: Conversation) -> list:
    """Create the four tool objects, closing over settings and the conversation.

    Split from build_mac_server so tests can call tool handlers directly.
    """

    @tool(
        "search_files",
        "Search this Mac for files and folders using the Spotlight index (fast). "
        "Returns JSON with results ranked newest-first, preferring Desktop, "
        "Documents, and Downloads.",
        {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Filename fragment for search_by=name, or text that "
                                   "appears inside documents for search_by=content. May be "
                                   "omitted when file_extension or modified_within_days is "
                                   "set (e.g. 'all PDFs on my Desktop').",
                },
                "search_by": {
                    "type": "string",
                    "enum": ["name", "content"],
                    "description": "name matches file/folder names; content matches text inside files.",
                },
                "scope": {
                    "type": "string",
                    "description": "Directory to search under, e.g. ~/Desktop. Empty = whole home folder.",
                },
                "modified_within_days": {
                    "type": "integer",
                    "description": "If > 0, only files changed in the last N days "
                                   "(for 'the file from yesterday' use 2).",
                },
                "file_extension": {
                    "type": "string",
                    "description": "Optional filter like pdf or docx.",
                },
                "limit": {"type": "integer", "description": "Max results (default 12)."},
            },
            "required": [],
        },
    )
    async def search_files(args: dict[str, Any]) -> dict[str, Any]:
        return _text(hands.search_files(
            args.get("query", ""),
            args.get("search_by", "name"),
            args.get("scope", "") or settings.scope,
            int(args.get("modified_within_days", 0) or 0),
            args.get("file_extension", ""),
            int(args.get("limit", 12) or 12),
        ))

    @tool(
        "open_path",
        "Open a file, folder, or app on the Mac — with a specific application, the "
        "system default app, or revealed in Finder.",
        {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path of the file or folder (from search_files).",
                },
                "app": {
                    "type": "string",
                    "description": "Optional app name to open it with, e.g. Preview, "
                                   "Google Chrome, Visual Studio Code. Empty = default app.",
                },
                "reveal": {
                    "type": "boolean",
                    "description": "If true, show the file in Finder instead of opening it.",
                },
            },
            "required": ["path"],
        },
    )
    async def open_path(args: dict[str, Any]) -> dict[str, Any]:
        return _text(hands.open_path(
            args.get("path", ""), args.get("app", ""), bool(args.get("reveal", False))
        ))

    @tool(
        "list_installed_apps",
        "List the names of applications installed on this Mac. Use before offering "
        "the user a choice of app, so you only offer apps that exist.",
        {"type": "object", "properties": {}},
    )
    async def list_installed_apps(args: dict[str, Any]) -> dict[str, Any]:
        return _text(hands.list_installed_apps())

    @tool(
        "ask_user",
        "Ask the user a clarifying question out loud and wait for their spoken/typed "
        "answer. Use when several files match, when more than one sensible app could "
        "open the file, or when a detail is missing.",
        {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "One short spoken-style sentence, e.g. 'I found three "
                                   "resumes. The newest is resume-2026 in Documents. "
                                   "Open that one?'",
                },
            },
            "required": ["question"],
        },
    )
    async def ask_user(args: dict[str, Any]) -> dict[str, Any]:
        await convo.aspeak(args.get("question", "Sorry, which one did you mean?"))
        answer = await convo.ahear("🎤 answer> ", auto_listen=True)
        return _text(answer if answer else "(no answer given)")

    return [search_files, open_path, list_installed_apps, ask_user]


def build_mac_server(settings: Settings, convo: Conversation):
    """The in-process MCP server handed to the Claude Agent SDK."""
    return create_sdk_mcp_server(
        name=SERVER_NAME, version=__version__,
        tools=build_tools(settings, convo),
    )
