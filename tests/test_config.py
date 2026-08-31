"""CLI parsing -> Settings mapping."""

from voice_file_agent.cli import parse_args, settings_from_args


def test_defaults():
    s = settings_from_args(parse_args([]))
    assert s.scope == "~"
    assert s.stt_model == "base.en"
    assert not s.typed
    assert not s.quiet
    assert s.model is None
    assert s.max_turns == 30


def test_flags_map_to_settings():
    s = settings_from_args(parse_args(
        ["--typed", "-q", "--scope", "~/Desktop", "--stt-model", "small.en", "--model", "sonnet"]
    ))
    assert s.typed and s.quiet
    assert s.scope == "~/Desktop"
    assert s.stt_model == "small.en"
    assert s.model == "sonnet"


def test_selftest_forces_quiet():
    s = settings_from_args(parse_args(["--selftest"]))
    assert s.quiet


def test_one_shot_query_collects_all_words():
    args = parse_args(["open", "my", "resume"])
    assert " ".join(args.query) == "open my resume"
