"""Self-test of the non-Claude layers (hands + ears) — runs offline, opens
nothing, speaks nothing. Kept as a CLI convenience alongside the pytest suite."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile

from . import hands
from .config import Settings
from .ears import Ears


def run(settings: Settings) -> None:
    print("1) search_files('resume', scope='~') ...")
    r = json.loads(hands.search_files("resume", scope="~", limit=5))
    print(f"   found {r.get('total_found')} — top hits:")
    for item in r.get("results", []):
        print(f"     {item['modified']}  {item['name']}  ({item['path']})")

    print("2) search_files('pdf' extension filter, Desktop, last 90 days) ...")
    r = json.loads(hands.search_files(""))
    assert "error" in r, "criteria-less search should error"
    r = json.loads(hands.search_files("a", "name", "~/Desktop", 90, "pdf", 5))
    print(f"   found {r.get('total_found', 0)} recent PDFs on Desktop")

    print("3) list_installed_apps() ...")
    apps = json.loads(hands.list_installed_apps())
    sample = ", ".join(apps["apps"][:8])
    print(f"   {apps['count']} apps, e.g.: {sample}")

    print("4) open_path on a bogus path (should error cleanly) ...")
    msg = hands.open_path("/no/such/file.xyz")
    assert msg.startswith("Error"), msg
    print(f"   {msg}")

    print("5) speech-to-text closed loop (say → wav → whisper, no mic needed) ...")
    ok, why = Ears.available()
    if not ok:
        print(f"   skipped: {why}")
    else:
        phrase = "open my latest resume from the downloads folder"
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav = f.name
        subprocess.run(
            ["say", "-o", wav, "--data-format=LEI16@16000", "--", phrase],
            check=True,
        )
        heard = Ears(settings.stt_model).transcribe_wav(wav)
        os.unlink(wav)
        print(f"   said:  {phrase}")
        print(f"   heard: {heard}")
        strip = str.maketrans("", "", ".,!?")
        overlap = set(phrase.split()) & set(heard.lower().translate(strip).split())
        assert len(overlap) >= 5, f"transcription too far off ({overlap})"

    print("\nSelf-test passed. Tool layer is working.")
