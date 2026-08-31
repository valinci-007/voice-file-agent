# voice-file-agent

An agentic assistant that finds and opens files on your Mac by voice — "open my
resume", "where's the PDF I downloaded yesterday?" — and asks you out loud when
it needs a decision (which file, which app), then listens for your answer.

Runs on the **Claude Agent SDK**, which drives your local `claude` CLI — so it
uses your existing Claude Code subscription login. **No API key, no API
credits.** Speech-to-text is **local Whisper** (faster-whisper): no audio ever
leaves the Mac.

## How it works (high level)

```
 you ──speech──▶ EARS (ears.py: mic + silence endpointing + local Whisper)
                     │ text
                     ▼
                 BRAIN (Claude Agent SDK → local `claude` CLI)
                     │  agentic loop: search / ask / open, until done
        ┌────────────┼──────────────┬─────────────┐
        ▼            ▼              ▼             ▼
  search_files   open_path   list_installed   ask_user ──▶ speaks a question,
  (Spotlight     (open /      _apps            then LISTENS for your answer
   mdfind)        open -a)   (/Applications)   (hands-free)
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
- macOS (uses Spotlight `mdfind`, `open`, `say`, and the default microphone).
- First voice use: macOS will ask to allow microphone access for your terminal
  — approve it. The Whisper model (~150MB for `base.en`) downloads on first
  use and is cached.

## Use

```sh
./run.sh                          # interactive; Enter = speak, or just type
./run.sh "open my resume"         # one-shot
./run.sh --typed                  # keyboard only (v1 behavior)
./run.sh --selftest               # test tools + speech-to-text, no Claude needed
```

Voice UX: at the prompt, press **Enter**, speak, and pause — recording stops on
silence. When the agent asks *you* something, the mic opens automatically after
the question (beep = listening). Typing still works everywhere, and it falls
back to typing whenever it couldn't hear you. Say "quit" to exit.

Options: `--stt-model tiny.en|base.en|small.en` (bigger = more accurate,
slower; default `base.en`), `--voice Samantha` (TTS voice), `--model
sonnet|opus|haiku` (default: whatever your Claude Code uses), `--scope
~/Desktop` (default search root), `-q/--quiet` (no TTS).

## Project structure

```
├── pyproject.toml            packaging, deps, entry point, ruff + pytest config
├── run.sh                    convenience launcher (creates venv on first run)
├── Makefile                  setup / run / test / integration / lint / fmt
├── .github/workflows/ci.yml  lint + unit tests on every push
├── src/voice_file_agent/
│   ├── cli.py                argparse → Settings → wiring → run
│   ├── config.py             frozen Settings dataclass
│   ├── brain.py              Claude Agent SDK session + agentic loop
│   ├── ears.py               mic capture, silence endpointing, Whisper STT
│   ├── mouth.py              macOS say TTS
│   ├── conversation.py       input policy: voice-first, typed fallback
│   ├── hands.py              Spotlight search, open/reveal, app list (pure seams)
│   ├── tools.py              MCP server: the model's entire capability surface
│   ├── prompts.py            the system prompt (wording is test-proven)
│   └── diagnostics.py        offline --selftest
└── tests/                    hermetic unit tests + local-only integration marker
```

Installed as a console script: `voice-file-agent` (also `python -m voice_file_agent`).

## Development

```sh
make setup          # venv + editable install with dev tools
make test           # hermetic unit tests (no mic, no Spotlight, no Claude)
make integration    # local-only: Whisper closed-loop STT test
make lint           # ruff
```

CI (GitHub Actions) runs ruff + the unit suite on every push; integration
tests stay local because CI runners have no Spotlight index or audio stack.

## Troubleshooting

- **Mic permission**: System Settings → Privacy & Security → Microphone →
  enable your terminal app.
- **Bluetooth earbuds**: their mics are compressed and switch audio into
  call mode while recording. The Mac's internal mic usually works better —
  System Settings → Sound → Input.
- **It doesn't hear you / cuts you off**: tune the constants at the top of
  `ears.py` (`MIN_THRESHOLD`, `MAX_THRESHOLD`, `silence_after`).
- Usage bills against your Claude subscription (like any Claude Code session).
- Don't `export ANTHROPIC_API_KEY` in the shell you run this from — an API key
  overrides the subscription login and needs paid API credits.

## Roadmap

- **v1 — done**: brain + hands + mouth: agent loop, Spotlight search, open with
  app choice, spoken replies and spoken clarifying questions.
- **v2 — done**: ears: local Whisper speech-to-text, silence endpointing,
  hands-free answers to the agent's questions, typed fallback.
- **v3 — always-on**: wake word ("hey genie"), menu-bar app / launchd service,
  interruptible TTS.
- **v4 — more hands**: recent-apps context, browser tabs, "move/rename with
  confirmation", multi-step requests.
