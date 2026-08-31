"""The MCP tool surface: wiring, schemas, and the ask_user round trip.

Uses a fake conversation object — no mic, no TTS, no Claude.
"""

import json

from voice_file_agent import tools
from voice_file_agent.config import Settings


class FakeConvo:
    def __init__(self, answer="the amex one"):
        self.spoken = []
        self.answer = answer
        self.auto_listen = None

    async def aspeak(self, text):
        self.spoken.append(text)

    async def ahear(self, prompt="", auto_listen=False):
        self.auto_listen = auto_listen
        return self.answer


def build(answer="the amex one"):
    convo = FakeConvo(answer)
    by_name = {t.name: t for t in tools.build_tools(Settings(), convo)}
    return convo, by_name


def test_exactly_four_tools_with_expected_names():
    _, by_name = build()
    assert set(by_name) == {"search_files", "open_path", "list_installed_apps", "ask_user"}
    assert tools.TOOL_NAMES == [
        "mcp__mac__search_files", "mcp__mac__open_path",
        "mcp__mac__list_installed_apps", "mcp__mac__ask_user",
    ]


async def test_ask_user_speaks_question_and_returns_answer():
    convo, by_name = build(answer="the newest one")
    result = await by_name["ask_user"].handler({"question": "Which resume?"})
    assert convo.spoken == ["Which resume?"]
    assert convo.auto_listen is True  # answers are hands-free
    assert result["content"][0]["text"] == "the newest one"


async def test_ask_user_handles_silence():
    _, by_name = build(answer="")
    result = await by_name["ask_user"].handler({"question": "Which one?"})
    assert result["content"][0]["text"] == "(no answer given)"


async def test_search_tool_reports_missing_criteria_as_json_error():
    _, by_name = build()
    result = await by_name["search_files"].handler({})
    payload = json.loads(result["content"][0]["text"])
    assert "error" in payload


async def test_open_tool_reports_bogus_path():
    _, by_name = build()
    result = await by_name["open_path"].handler({"path": "/no/such/file.xyz"})
    assert result["content"][0]["text"].startswith("Error")
