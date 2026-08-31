"""Hermetic unit tests for the hands layer — no Spotlight, no subprocesses."""

import json
from pathlib import Path

from voice_file_agent import hands

HOME = str(Path.home())
SCOPE = HOME


def test_human_size():
    assert hands.human_size(512) == "512B"
    assert hands.human_size(2048) == "2.0KB"
    assert hands.human_size(5 * 1024 * 1024) == "5.0MB"


def test_score_prefers_user_folders_over_buried_noise():
    good = hands.score(f"{HOME}/Desktop/resume.pdf")
    plain_home = hands.score(f"{HOME}/somewhere/resume.pdf")
    noisy = hands.score(f"{HOME}/Library/Caches/deep/deep/deep/resume.pdf")
    assert good > plain_home > noisy


def test_rank_orders_by_score_then_recency():
    a = f"{HOME}/Desktop/new.pdf"
    b = f"{HOME}/Desktop/old.pdf"
    c = f"{HOME}/Library/anything.pdf"
    mtimes = {a: 200.0, b: 100.0, c: 900.0}
    assert hands.rank([c, b, a], mtime=mtimes.get) == [a, b, c]


def test_build_command_name_only_uses_native_mode():
    cmd = hands.build_search_command("resume", "name", SCOPE)
    assert cmd == ["mdfind", "-onlyin", SCOPE, "-name", "resume"]


def test_build_command_content_only_uses_broad_query():
    cmd = hands.build_search_command("invoice total", "content", SCOPE)
    assert cmd == ["mdfind", "-onlyin", SCOPE, "invoice total"]


def test_build_command_extension_only():
    cmd = hands.build_search_command("", "name", SCOPE, file_extension="pdf")
    assert cmd is not None
    assert 'kMDItemFSName == "*.pdf"c' in cmd[-1]


def test_build_command_combines_clauses():
    cmd = hands.build_search_command("report", "name", SCOPE, 7, "docx")
    raw = cmd[-1]
    assert 'kMDItemDisplayName == "*report*"c' in raw
    assert 'kMDItemFSName == "*.docx"c' in raw
    assert "$time.today(-7)" in raw
    assert " && " in raw


def test_build_command_sanitizes_query():
    cmd = hands.build_search_command('re"po\\rt', "name", SCOPE)
    assert cmd == ["mdfind", "-onlyin", SCOPE, "-name", "report"]


def test_build_command_without_criteria_is_none():
    assert hands.build_search_command("", "name", SCOPE) is None


def test_search_files_without_criteria_errors_before_subprocess():
    result = json.loads(hands.search_files(""))
    assert "error" in result


def test_open_path_missing_file_errors_cleanly():
    assert hands.open_path("/no/such/file.xyz").startswith("Error")
