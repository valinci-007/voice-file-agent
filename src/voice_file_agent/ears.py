"""Ears — microphone capture + local Whisper speech-to-text.

Everything runs on-device: sounddevice (PortAudio) records from the default
input, a simple ambient-calibrated energy gate decides when you stopped
talking, and faster-whisper transcribes. No audio ever leaves the Mac.

Heavy imports (sounddevice, faster_whisper) happen lazily inside methods so
importing this module is cheap and works on machines without audio stacks.
"""

from __future__ import annotations

import collections
import queue
import subprocess
import time
import wave

import numpy as np

SAMPLE_RATE = 16000
BLOCK_SECONDS = 0.03          # 30 ms analysis blocks
CALIBRATION_BLOCKS = 10       # first 300 ms measures room noise
PRE_ROLL_BLOCKS = 10          # keep 300 ms before speech so syllables aren't clipped
MIN_THRESHOLD = 0.010         # RMS floor so dead-silent rooms don't trigger on nothing
MAX_THRESHOLD = 0.070         # ceiling: noisy Bluetooth mics must not drown out speech


def _beep() -> None:
    try:
        subprocess.Popen(
            ["afplay", "/System/Library/Sounds/Pop.aiff"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


class Ears:
    def __init__(self, model_name: str = "base.en"):
        self.model_name = model_name
        self._model = None

    @staticmethod
    def available() -> tuple[bool, str]:
        try:
            import faster_whisper  # noqa: F401
            import sounddevice  # noqa: F401
        except Exception as e:  # missing wheel, no PortAudio, etc.
            return False, f"{type(e).__name__}: {e}"
        return True, ""

    def _get_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            print(f"   (loading speech model '{self.model_name}' — first use downloads it)")
            self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
        return self._model

    def record_until_silence(
        self,
        max_seconds: float = 30.0,
        silence_after: float = 1.2,
        wait_for_speech: float = 8.0,
    ) -> np.ndarray | None:
        """Record from the default mic until the speaker goes quiet.

        Returns float32 mono @16kHz, or None if nothing was said in time.
        """
        import sounddevice as sd

        frames = int(SAMPLE_RATE * BLOCK_SECONDS)
        blocks: queue.Queue = queue.Queue()

        def _cb(indata, _frames, _time, _status):
            blocks.put(indata.copy())

        chunks: list[np.ndarray] = []
        pre_roll: collections.deque = collections.deque(maxlen=PRE_ROLL_BLOCKS)
        ambient: list[float] = []
        threshold = MIN_THRESHOLD * 3
        started = False
        quiet = 0.0
        waited = 0.0

        with sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32",
            blocksize=frames, callback=_cb,
        ):
            t0 = time.time()
            while time.time() - t0 < max_seconds:
                try:
                    data = blocks.get(timeout=2.0)
                except queue.Empty:
                    return None  # stream stalled (device vanished, permission issue)
                rms = float(np.sqrt(np.mean(data ** 2)))

                if len(ambient) < CALIBRATION_BLOCKS:
                    ambient.append(rms)
                    pre_roll.append(data)
                    if len(ambient) == CALIBRATION_BLOCKS:
                        threshold = min(
                            max(float(np.median(ambient)) * 3.0, MIN_THRESHOLD),
                            MAX_THRESHOLD,
                        )
                    continue

                if not started:
                    pre_roll.append(data)
                    if rms >= threshold:
                        started = True
                        chunks.extend(pre_roll)
                    else:
                        waited += BLOCK_SECONDS
                        if waited > wait_for_speech:
                            return None
                else:
                    chunks.append(data)
                    if rms < threshold:
                        quiet += BLOCK_SECONDS
                        if quiet >= silence_after:
                            break
                    else:
                        quiet = 0.0

        if not chunks:
            return None
        return np.concatenate(chunks)[:, 0]

    def transcribe(self, audio: np.ndarray) -> str:
        language = "en" if self.model_name.endswith(".en") else None
        segments, _info = self._get_model().transcribe(
            audio, language=language, beam_size=1, vad_filter=False,
        )
        return " ".join(s.text.strip() for s in segments).strip()

    def listen(self, banner: str = "🎙  listening — speak now (pause to finish)") -> str:
        """One full voice capture: beep, record, transcribe. '' if nothing heard."""
        print(banner)
        _beep()
        audio = self.record_until_silence()
        if audio is None or len(audio) < SAMPLE_RATE * 0.3:
            return ""
        print("   (transcribing…)")
        text = self.transcribe(audio)
        if text:
            print(f"🎙  heard: {text}")
        return text

    def transcribe_wav(self, path: str) -> str:
        """Transcribe a 16-bit PCM wav file — lets tests run without a mic."""
        with wave.open(path, "rb") as w:
            assert w.getsampwidth() == 2, "expected 16-bit PCM"
            raw = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
            if w.getnchannels() > 1:
                raw = raw.reshape(-1, w.getnchannels()).mean(axis=1).astype(np.int16)
            rate = w.getframerate()
        audio = raw.astype(np.float32) / 32768.0
        if rate != SAMPLE_RATE:  # crude resample; test audio is clean speech
            idx = np.round(np.arange(0, len(audio), rate / SAMPLE_RATE)).astype(int)
            audio = audio[idx[idx < len(audio)]]
        return self.transcribe(audio)
