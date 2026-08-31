"""Closed-loop speech-to-text test: say -> wav -> Whisper. Local-only
(needs macOS + the Whisper model); excluded from the default pytest run.
Run with: pytest -m integration
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from voice_file_agent.ears import Ears

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform != "darwin", reason="needs macOS `say`"),
]


def test_say_roundtrip_transcription():
    ok, why = Ears.available()
    if not ok:
        pytest.skip(why)

    phrase = "open my latest resume from the downloads folder"
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav = f.name
    try:
        subprocess.run(
            ["say", "-o", wav, "--data-format=LEI16@16000", "--", phrase],
            check=True,
        )
        heard = Ears("base.en").transcribe_wav(wav)
    finally:
        Path(wav).unlink(missing_ok=True)

    strip = str.maketrans("", "", ".,!?")
    overlap = set(phrase.split()) & set(heard.lower().translate(strip).split())
    assert len(overlap) >= 5, f"transcription too far off: {heard!r}"
