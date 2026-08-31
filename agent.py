#!/usr/bin/env python3
"""voice-file-agent v1 — an agentic assistant that finds and opens files on your Mac.

Runs on the Claude Agent SDK, which drives your local `claude` CLI — so it uses
your existing Claude Code subscription login. No API key, no API credits.

Architecture (each part is swappable):
  Ears   hear()          -> where the user's words come from (v1: typed; v2: Whisper mic)
  Brain  ClaudeSDKClient -> Claude in an agentic tool loop; decides search/ask/open
  Hands  @tool funcs     -> thin wrappers over macOS: mdfind (Spotlight), open, /Applications
  Mouth  speak()         -> macOS `say` text-to-speech

Usage:
  ./run.sh                          interactive session (speaks replies aloud)
  ./run.sh "open my resume"         one-shot request
  ./run.sh --selftest               test the macOS tool layer, no Claude needed
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ClaudeSDKClient,
        ResultMessage,
        TextBlock,
        ToolUseBlock,
        create_sdk_mcp_server,
        tool,
    )
except ImportError:
    sys.exit(
        "The 'claude-agent-sdk' package is missing. Run this via ./run.sh (uses the\n"
        "project venv), or install with: .venv/bin/pip install claude-agent-sdk"
    )

# ---------------------------------------------------------------------------
# Config (set from CLI args in main)
# ---------------------------------------------------------------------------

CFG = argparse.Namespace(quiet=False, voice=None, scope="~")

HOME = Path.home()

# Folders a person usually means when they say "my files" — ranked up.
PREFERRED_DIRS = [
    str(HOME / d) for d in ("Desktop", "Documents", "Downloads", "Pictures", "Movies", "Music")
]

# Path fragments that are almost never what the user wants — ranked down hard.
NOISE_FRAGMENTS = [
    "/Library/", "/.git/", "/node_modules/", "/.Trash/", "/site-packages/",
    ".app/", "/System/", "/private/", "/.venv/", "/venv/", "/__pycache__/",
    "/.cache/", "/Caches/",
]

# ---------------------------------------------------------------------------
# Mouth + Ears
# ---------------------------------------------------------------------------


def speak(text: str) -> None:
    """Print the assistant's words and read them aloud with macOS `say`."""
    clean = re.sub(r"[*#`]", "", text).strip()  # keep _ — it appears in filenames
    if not clean:
        return
    print(f"\n🤖 {clean}\n")
    if CFG.quiet:
        return
    cmd = ["say"]
    if CFG.voice:
        cmd += ["-v", CFG.voice]
    try:
        subprocess.run(cmd + ["--", clean], timeout=120)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass  # never let TTS take the agent down


async def aspeak(text: str) -> None:
    """speak() without blocking the event loop that pumps the Claude session."""
    await asyncio.to_thread(speak, text)


def hear(prompt: str = "🎤 you> ") -> str:
    """Get the user's next utterance. v1 reads typed input (tip: press fn twice
    to use macOS dictation); v2 will swap this for Whisper mic capture."""
    try:
        return input(prompt).strip()
    except EOFError:
        return "quit"


async def ahear(prompt: str = "🎤 you> ") -> str:
    return await asyncio.to_thread(hear, prompt)


# ---------------------------------------------------------------------------
# Hands — macOS primitives (plain functions, testable without Claude)
# ---------------------------------------------------------------------------


def _sh(cmd: list[str], timeout: int = 20) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n}B"


def _score(path: str) -> int:
    score = 0
    if any(path.startswith(d) for d in PREFERRED_DIRS):
        score += 50
    elif path.startswith(str(HOME)):
        score += 10
    if any(frag in path for frag in NOISE_FRAGMENTS):
        score -= 100
    score -= path.count("/")  # shallow paths beat deeply buried ones
    return score


def _search_files(
    query: str,
    search_by: str = "name",
    scope: str = "",
    modified_within_days: int = 0,
    file_extension: str = "",
    limit: int = 12,
) -> str:
    query = query.replace('"', "").replace("\\", "").strip()
    ext = file_extension.lower().lstrip(".") if file_extension else ""
    scope_dir = os.path.expanduser(scope or CFG.scope)

    clauses = []
    if query:
        attr = "kMDItemDisplayName" if search_by == "name" else "kMDItemTextContent"
        clauses.append(f'{attr} == "*{query}*"c')
    if ext:
        clauses.append(f'kMDItemFSName == "*.{ext}"c')
    if modified_within_days > 0:
        clauses.append(f"kMDItemFSContentChangeDate >= $time.today(-{int(modified_within_days)})")
    if not clauses:
        return json.dumps({"error": "give at least a query, file_extension, or modified_within_days"})

    if query and not ext and modified_within_days <= 0:
        # single-term searches: mdfind's native modes match Spotlight's own behavior best
        cmd = ["mdfind", "-onlyin", scope_dir] + (
            ["-name", query] if search_by == "name" else [query]
        )
    else:
        cmd = ["mdfind", "-onlyin", scope_dir, " && ".join(clauses)]

    try:
        out = _sh(cmd).stdout
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "Spotlight search timed out"})

    paths = [p for p in out.splitlines() if p.strip()]
    if file_extension:
        ext = "." + file_extension.lower().lstrip(".")
        paths = [p for p in paths if p.lower().endswith(ext)]

    def mtime(p: str) -> float:
        try:
            return os.stat(p).st_mtime
        except OSError:
            return 0.0

    ranked = sorted(paths, key=lambda p: (-_score(p), -mtime(p)))
    results = []
    for p in ranked[: max(1, min(limit, 30))]:
        try:
            st = os.stat(p)
            is_dir = os.path.isdir(p)
            results.append({
                "path": p,
                "name": os.path.basename(p),
                "kind": "folder" if is_dir else (os.path.splitext(p)[1].lstrip(".").lower() or "file"),
                "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
                "size": "" if is_dir else _human_size(st.st_size),
            })
        except OSError:
            continue

    return json.dumps(
        {"total_found": len(paths), "showing": len(results), "results": results},
        ensure_ascii=False,
    )


def _list_installed_apps() -> str:
    apps: set[str] = set()
    roots = [
        Path("/Applications"), Path("/System/Applications"),
        Path("/System/Applications/Utilities"), HOME / "Applications",
    ]
    for root in roots:
        if not root.is_dir():
            continue
        for entry in root.iterdir():
            if entry.suffix == ".app":
                apps.add(entry.stem)
            elif entry.is_dir() and not entry.name.startswith("."):
                for sub in entry.glob("*.app"):
                    apps.add(sub.stem)
    return json.dumps({"count": len(apps), "apps": sorted(apps)}, ensure_ascii=False)


def _open_path(path: str, app: str = "", reveal: bool = False) -> str:
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return f"Error: no such path: {path}"
    if reveal:
        cmd = ["open", "-R", path]
    elif app:
        cmd = ["open", "-a", app, path]
    else:
        cmd = ["open", path]
    try:
        proc = _sh(cmd, timeout=30)
    except subprocess.TimeoutExpired:
        return "Error: open command timed out"
    if proc.returncode != 0:
        return f"Error: {proc.stderr.strip() or 'open failed'}"
    if reveal:
        return f"Revealed {path} in Finder"
    return f"Opened {path}" + (f" with {app}" if app else " with its default app")


# ---------------------------------------------------------------------------
# Tools — the schema Claude sees (in-process MCP server over the functions above)
# ---------------------------------------------------------------------------


def _text_result(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


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
    return _text_result(_search_files(
        args.get("query", ""),
        args.get("search_by", "name"),
        args.get("scope", ""),
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
    return _text_result(_open_path(
        args.get("path", ""), args.get("app", ""), bool(args.get("reveal", False))
    ))


@tool(
    "list_installed_apps",
    "List the names of applications installed on this Mac. Use before offering "
    "the user a choice of app, so you only offer apps that exist.",
    {"type": "object", "properties": {}},
)
async def list_installed_apps(args: dict[str, Any]) -> dict[str, Any]:
    return _text_result(_list_installed_apps())


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
    await aspeak(args.get("question", "Sorry, which one did you mean?"))
    answer = await ahear("🎤 answer> ")
    return _text_result(answer if answer else "(no answer given)")


MAC_SERVER = create_sdk_mcp_server(
    name="mac", version="1.0.0",
    tools=[search_files, open_path, list_installed_apps, ask_user],
)

TOOL_NAMES = [f"mcp__mac__{n}" for n in
              ("search_files", "open_path", "list_installed_apps", "ask_user")]

# ---------------------------------------------------------------------------
# Brain — Claude Agent SDK session (uses your Claude Code login)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a voice-controlled file assistant running on the user's Mac.
The user speaks a request; everything you write outside tool calls is read aloud
by text-to-speech (and printed). Your job: find files/folders with search_files,
then open them with open_path — in the right app when it matters.

You have exactly four tools: search_files, open_path, list_installed_apps, and
ask_user. Never attempt any other tool.

The ONLY way to ask the user anything is the ask_user tool. A question written
as plain text ends your turn and will NEVER be answered — the job dies there.
Whenever you need input to finish (which file, which app, a missing detail),
call ask_user, get the answer, and keep working in the same turn until the job
is done.

Voice style:
- Replies are spoken. Keep them to one or two short sentences, plain words, no
  markdown, no lists. Never read a full slash-path aloud; say "resume dot pdf in
  your Documents folder" instead.
- Do not narrate tool use ("let me search..."). Call tools silently; speak only
  results, questions, and confirmations.

Finding:
- Search before ever saying a file doesn't exist. Try at least two name variants
  (e.g. "resume" then "cv"; people also use hyphens/underscores/abbreviations).
- Prefer recently modified files and files in Desktop, Documents, or Downloads.
- If results are junk or empty, broaden: search_by="content", a wider scope, or
  ask_user for a hint (file type, rough location, when they last used it).

Deciding:
- Exactly one clear best match: open it right away and confirm in one sentence,
  naming the file and its folder.
- Several plausible matches: never guess between siblings like "resume-v1" and
  "resume-final". Use ask_user, offering the top two to four briefly (name,
  folder, date).
- Any time you need an answer from the user to finish the job, call the ask_user
  tool. Never end your turn with a question written as plain text — once your
  turn ends the user may not be able to reply. ask_user speaks the question,
  waits, and hands you the answer so you can finish in the same turn.
- App choice: if the user named an app, use it. If the file type has more than
  one sensible app actually installed (check list_installed_apps when unsure),
  use ask_user to offer two or three. If there's one obvious choice, just open it.
- When using ask_user, put the question only in the tool input — no duplicate text.

Boundaries:
- You only search, reveal, and open. You never move, rename, edit, or delete
  anything; if asked, say that's not something you can do yet.
- "Where is it?" means reveal=true in Finder rather than opening the file.
"""


def _tool_call_summary(name: str, tool_input: dict) -> str:
    short = name.removeprefix("mcp__mac__")
    parts = [f"{k}={v!r}" for k, v in tool_input.items() if v not in ("", 0, False, None)]
    return f"{short}({', '.join(parts)})"


def build_options(args) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        model=args.model,                # None = your Claude Code default model
        mcp_servers={"mac": MAC_SERVER},
        allowed_tools=TOOL_NAMES,        # auto-approved
        tools=[],                        # no built-in Claude Code tools
        disallowed_tools=[               # belt and suspenders on top of tools=[]
            "Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebFetch",
            "WebSearch", "Task", "TodoWrite", "NotebookEdit",
        ],
        permission_mode="dontAsk",       # anything not pre-approved is denied
        setting_sources=[],              # ignore CLAUDE.md, user hooks, etc.
        max_turns=30,
        cwd=str(HOME),
    )


async def stream_reply(client: ClaudeSDKClient) -> None:
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
                await aspeak(text)
        elif isinstance(message, ResultMessage):
            reason = getattr(message, "terminal_reason", None) or getattr(message, "subtype", "")
            if reason and reason not in ("success", "end_turn", "completed"):
                detail = getattr(message, "result", "") or ""
                print(f"   (turn ended: {reason} {detail})".rstrip())


async def repl_async(args) -> None:
    one_shot = " ".join(args.query).strip()
    try:
        async with ClaudeSDKClient(options=build_options(args)) as client:
            if not one_shot:
                print(
                    "voice-file-agent v1  ·  Claude Agent SDK "
                    f"(model: {args.model or 'your Claude Code default'})  ·  scope {CFG.scope}\n"
                    "Type a request (press fn twice to dictate with your voice). "
                    "'quit' to exit.\n"
                )
            while True:
                user_text = one_shot or await ahear()
                if not user_text:
                    continue
                if user_text.lower() in {"quit", "exit", "q", "bye", "stop"}:
                    await aspeak("Bye!")
                    break
                try:
                    await client.query(user_text)
                    await stream_reply(client)
                except KeyboardInterrupt:
                    print("\n(interrupted)")
                    try:
                        await client.interrupt()
                    except Exception:
                        pass
                if one_shot:
                    break
    except Exception as e:
        name = type(e).__name__
        if "CLINotFound" in name:
            sys.exit(
                "Could not find the `claude` CLI. Install Claude Code first "
                "(https://claude.com/claude-code) — this agent runs on its login."
            )
        raise


# ---------------------------------------------------------------------------
# Self-test: exercises the macOS tool layer only — no Claude, no TTS, no windows
# ---------------------------------------------------------------------------


def selftest() -> None:
    print("1) search_files('resume', scope='~') ...")
    r = json.loads(_search_files("resume", scope="~", limit=5))
    print(f"   found {r.get('total_found')} — top hits:")
    for item in r.get("results", []):
        print(f"     {item['modified']}  {item['name']}  ({item['path']})")

    print("2) search_files('pdf' extension filter, Desktop, last 90 days) ...")
    r = json.loads(_search_files("", "name", "", 0, "", 5))  # empty-query guard
    assert "error" in r, "empty query should error"
    r = json.loads(_search_files("a", "name", "~/Desktop", 90, "pdf", 5))
    print(f"   found {r.get('total_found', 0)} recent PDFs on Desktop")

    print("3) list_installed_apps() ...")
    apps = json.loads(_list_installed_apps())
    sample = ", ".join(apps["apps"][:8])
    print(f"   {apps['count']} apps, e.g.: {sample}")

    print("4) open_path on a bogus path (should error cleanly) ...")
    msg = _open_path("/no/such/file.xyz")
    assert msg.startswith("Error"), msg
    print(f"   {msg}")

    print("\nSelf-test passed. Tool layer is working.")


def main() -> None:
    p = argparse.ArgumentParser(description="Voice-driven file finder/opener for macOS")
    p.add_argument("query", nargs="*", help="one-shot request; omit for interactive mode")
    p.add_argument("-q", "--quiet", action="store_true", help="don't speak replies aloud")
    p.add_argument("--voice", default=os.environ.get("SAY_VOICE"), help="macOS say voice name")
    p.add_argument("--model", default=os.environ.get("FILE_AGENT_MODEL"),
                   help="e.g. sonnet, opus, haiku; default = your Claude Code model")
    p.add_argument("--scope", default="~", help="default folder to search under")
    p.add_argument("--selftest", action="store_true", help="test macOS tools without Claude")
    args = p.parse_args()

    CFG.quiet = args.quiet or args.selftest
    CFG.voice = args.voice
    CFG.scope = args.scope

    if args.selftest:
        selftest()
        return
    try:
        asyncio.run(repl_async(args))
    except KeyboardInterrupt:
        print("\nBye!")


if __name__ == "__main__":
    main()
