# voice-file-agent

An agentic assistant that finds and opens files on your Mac by voice-style
requests — "open my resume", "where's the PDF I downloaded yesterday?" — and
asks you out loud when it needs a decision (which file, which app).

Runs on the **Claude Agent SDK**, which drives your local `claude` CLI — so it
uses your existing Claude Code subscription login. **No API key, no API
credits, no setup.**

## How it works (high level)

```
 you ──speech──▶ EARS (speech-to-text)          [v2: Whisper — typed today]
                     │ text
                     ▼
                 BRAIN (Claude Agent SDK → local `claude` CLI)
                     │  agentic loop: search / ask / open, until done
        ┌────────────┼──────────────┬─────────────┐
        ▼            ▼              ▼             ▼
  search_files   open_path   list_installed   ask_user ──▶ speaks a question,
  (Spotlight     (open /      _apps            waits for your answer
   mdfind)        open -a)   (/Applications)
                     │ final answer (text)
                     ▼
                 MOUTH (macOS `say` TTS) ──speech──▶ you
```

The four tools live in this process as an in-process MCP server (`mac`); the
SDK exposes them to Claude as `mcp__mac__*`. Claude Code's built-in tools
(Bash, file edit, web) are disabled — the agent can *only* search, reveal, and
open, so it can't be talked into destructive actions.

The key design point: **clarification is just another tool.** The model isn't
hard-coded to ask "which app?" — it has an `ask_user` tool and a system prompt
telling it *when* asking beats guessing (multiple matching files, multiple
sensible apps) and that plain-text questions end the turn unanswered. That's
what makes it an agent rather than a command parser.

## Requirements

- Claude Code installed and logged in (if you're reading this, you have it).
- macOS (uses Spotlight `mdfind`, `open`, and `say`).

## Use

```sh
./run.sh                          # interactive; replies are spoken aloud
./run.sh "open my resume"         # one-shot
./run.sh --selftest               # check the macOS tool layer, no Claude needed
./run.sh -q "find tax documents"  # quiet (no TTS)
```

Voice input today: press **fn twice** in the terminal to use macOS dictation —
your speech becomes the typed request. Native mic capture lands in v2.

Options: `--voice Samantha` (TTS voice), `--model sonnet|opus|haiku` (default:
whatever your Claude Code uses), `--scope ~/Desktop` (default search root),
`-q/--quiet`.

## Troubleshooting

- Usage bills against your Claude subscription (like any Claude Code session).
- Don't `export ANTHROPIC_API_KEY` in the shell you run this from — an API key
  overrides the subscription login and needs paid API credits.
- If Claude Code ever warns about an "auth conflict" with an `ant` CLI profile,
  `ant auth logout --all` clears it (that profile isn't needed by this agent).

## Roadmap

- **v1 (this)** — brain + hands + mouth: agent loop, Spotlight search, open
  with app choice, spoken replies and spoken clarifying questions.
- **v2 — ears**: local Whisper speech-to-text with push-to-talk mic capture,
  so answers to `ask_user` are spoken too.
- **v3 — always-on**: wake word ("hey genie"), menu-bar app / launchd service,
  interruptible TTS.
- **v4 — more hands**: recent-apps context, browser tabs, "move/rename with
  confirmation", multi-step requests.
