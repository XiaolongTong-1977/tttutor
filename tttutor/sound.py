"""Sound effects — fully procedural, cross-platform, stdlib only.

Synthesizes each `SoundEvent` to a WAV byte stream and plays it through the
best available backend:

* Linux   — `paplay` (PulseAudio), `aplay` (ALSA), or terminal bell
* macOS   — `afplay`
* Windows — `winsound` (PlaySound via built-in C extension)

None of the audio bytes are stored on disk — every playback is generated on
demand. No external assets, no PyPI deps.
"""
from __future__ import annotations

import math
import os
import io
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import wave
from enum import Enum
from typing import Optional


SAMPLE_RATE = 22050            # mono, 16-bit signed LE
DEFAULT_VOLUME = 0.30          # safe level so loud loops aren't ear-piercing


class SoundEvent(Enum):
    KEYSTROKE = "keystroke"             # tap on each correct key
    ERROR = "error"                     # wrong key
    DRILL_COMPLETE = "drill_complete"   # line done
    LESSON_COMPLETE = "lesson_complete" # whole lesson
    GAME_HIT = "game_hit"               # Letter Invaders destroyed
    GAME_MISS = "game_miss"             # letter reached the ground
    GAME_OVER = "game_over"             # out of lives


# ----- synthesis --------------------------------------------------------

def _envelope(i: int, total: int, attack: float, release: float) -> float:
    t = i / SAMPLE_RATE
    dur = total / SAMPLE_RATE
    if t < attack:
        return t / attack
    if t > dur - release:
        return max(0.0, (dur - t) / max(release, 1e-9))
    return 1.0


def _sine(freq: float, dur_s: float, vol: float = DEFAULT_VOLUME,
         attack: float = 0.005, release: float = 0.005) -> bytes:
    n = int(SAMPLE_RATE * dur_s)
    out = bytearray()
    for i in range(n):
        env = _envelope(i, n, attack, release)
        v = vol * env * math.sin(2 * math.pi * freq * (i / SAMPLE_RATE))
        s = int(v * 32767)
        out += struct.pack('<h', max(-32768, min(32767, s)))
    return bytes(out)


def _square(freq: float, dur_s: float, vol: float = DEFAULT_VOLUME,
           attack: float = 0.005, release: float = 0.005) -> bytes:
    n = int(SAMPLE_RATE * dur_s)
    out = bytearray()
    for i in range(n):
        env = _envelope(i, n, attack, release)
        v = vol * env * (1.0 if math.sin(2 * math.pi * freq * (i / SAMPLE_RATE)) > 0 else -1.0)
        s = int(v * 32767)
        out += struct.pack('<h', max(-32768, min(32767, s)))
    return bytes(out)


def _sweep(f_start: float, f_end: float, dur_s: float, kind: str = "sine",
          vol: float = DEFAULT_VOLUME, attack: float = 0.005, release: float = 0.005) -> bytes:
    """Frequency-swept tone, exponential sweep to sound natural."""
    n = int(SAMPLE_RATE * dur_s)
    out = bytearray()
    # ensure f_start > 0 to avoid log(0)
    f_start = max(f_start, 1.0)
    f_end = max(f_end, 1.0)
    log0, log1 = math.log(f_start), math.log(f_end)
    phase = 0.0
    for i in range(n):
        t = i / SAMPLE_RATE
        f = math.exp(log0 + (log1 - log0) * (i / SAMPLE_RATE / dur_s))
        phase += 2 * math.pi * f / SAMPLE_RATE
        if phase > 2 * math.pi:
            phase -= 2 * math.pi
        env = _envelope(i, n, attack, release)
        if kind == "square":
            v = vol * env * (1.0 if math.sin(phase) > 0 else -1.0)
        else:
            v = vol * env * math.sin(phase)
        s = int(v * 32767)
        out += struct.pack('<h', max(-32768, min(32767, s)))
    return bytes(out)


def _noise(dur_s: float, vol: float = 0.2,
           attack: float = 0.005, release: float = 0.020) -> bytes:
    """White noise burst, useful for click/clack sounds."""
    import random
    n = int(SAMPLE_RATE * dur_s)
    out = bytearray()
    for i in range(n):
        env = _envelope(i, n, attack, release)
        v = vol * env * (random.uniform(-1.0, 1.0))
        s = int(v * 32767)
        out += struct.pack('<h', max(-32768, min(32767, s)))
    return bytes(out)


# ----- per-event synthesis --------------------------------------------

def _keystroke() -> bytes:
    """Short click — like a real keyboard under a finger."""
    return _noise(0.030, vol=0.20)


def _error() -> bytes:
    """Descending square — an ear-catching buzz."""
    return _sweep(f_start=380, f_end=120, dur_s=0.18, kind="square", vol=0.35)


def _drill_complete() -> bytes:
    """Two-note ascending ding."""
    return _sine(660, 0.10, vol=0.40) + _sine(880, 0.20, vol=0.40)


def _lesson_complete() -> bytes:
    """C major arpeggio."""
    a = _sine(523.25, 0.20, vol=0.35)   # C5
    b = _sine(659.25, 0.20, vol=0.35)   # E5
    c = _sine(783.99, 0.25, vol=0.35)   # G5
    d = _sine(1046.50, 0.50, vol=0.40)  # C6
    return a + b + c + d


def _game_hit() -> bytes:
    """Downward pew — Letter Invaders destroyed."""
    return _sweep(f_start=1200, f_end=200, dur_s=0.10, kind="square", vol=0.30)


def _game_miss() -> bytes:
    """Low thud — letter reached the ground."""
    return _square(80, 0.20, vol=0.30)


def _game_over() -> bytes:
    """Sad descending tritone."""
    a = _sine(523.25, 0.30, vol=0.35)
    b = _sine(349.23, 0.30, vol=0.35)
    c = _sine(207.65, 0.60, vol=0.40)
    return a + b + c


SYNTH = {
    SoundEvent.KEYSTROKE: _keystroke,
    SoundEvent.ERROR: _error,
    SoundEvent.DRILL_COMPLETE: _drill_complete,
    SoundEvent.LESSON_COMPLETE: _lesson_complete,
    SoundEvent.GAME_HIT: _game_hit,
    SoundEvent.GAME_MISS: _game_miss,
    SoundEvent.GAME_OVER: _game_over,
}


def synthesize(event: SoundEvent) -> bytes:
    """Return raw 16-bit PCM mono WAV bytes for one event."""
    pcm = SYNTH[event]()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


# ----- backends --------------------------------------------------------

class Backend:
    name: str = "base"

    def play(self, wav: bytes) -> None:
        raise NotImplementedError

    @staticmethod
    def available() -> bool:
        return True


class PulseAudioBackend(Backend):
    name = "paplay (PulseAudio)"

    @staticmethod
    def available() -> bool:
        return shutil.which("paplay") is not None

    def play(self, wav: bytes) -> None:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav)
            path = f.name
        try:
            # subprocess.run waits for the player to finish before we
            # delete the temp file; the worker thread keeps this off the
            # typing loop, and no zombie processes are left behind.
            subprocess.run(
                ["paplay", path],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except Exception:
            pass
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass


class AlsaBackend(Backend):
    name = "aplay (ALSA)"

    @staticmethod
    def available() -> bool:
        return shutil.which("aplay") is not None

    def play(self, wav: bytes) -> None:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav)
            path = f.name
        try:
            subprocess.run(
                ["aplay", "-q", path],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except Exception:
            pass
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass


class AfplayBackend(Backend):
    name = "afplay (macOS)"

    @staticmethod
    def available() -> bool:
        return sys.platform == "darwin" or shutil.which("afplay") is not None

    def play(self, wav: bytes) -> None:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav)
            path = f.name
        try:
            subprocess.run(
                ["afplay", path],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
        except Exception:
            pass
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass


class WindowsBeepBackend(Backend):
    """Last-ditch Windows fallback — short winsound.MessageBeep."""
    name = "winsound.MessageBeep"

    @staticmethod
    def available() -> bool:
        return sys.platform == "win32"

    def play(self, wav: bytes) -> None:
        # winsound.MessageBeep doesn't accept WAV data, but works in headless
        # trial contexts where no other backend exists.
        try:
            import winsound            # built-in on Windows
            winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            pass


class BellBackend(Backend):
    """Universal fallback — terminal bell."""
    name = "terminal bell (\\a)"

    @staticmethod
    def available() -> bool:
        return True

    def play(self, wav: bytes) -> None:
        # '\a' is BEL; very short, never blocks.
        sys.stdout.write("\a")
        sys.stdout.flush()


def pick_backend() -> Backend:
    for cls in (PulseAudioBackend, AlsaBackend, AfplayBackend, WindowsBeepBackend, BellBackend):
        if cls.available():
            return cls()
    return BellBackend()


# ----- public interface ------------------------------------------------

class SoundPlayer:
    """Async sound playback. Use `play(event)` from anywhere."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.backend = pick_backend()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    def backend_name(self) -> str:
        return self.backend.name

    def toggle(self) -> bool:
        self.enabled = not self.enabled
        return self.enabled

    def play(self, event: SoundEvent) -> None:
        if not self.enabled:
            return
        wav = synthesize(event)
        # Use a worker thread per playback so the typing loop never blocks.
        t = threading.Thread(
            target=self._safe_play, args=(wav,), daemon=True
        )
        t.start()

    def _safe_play(self, wav: bytes) -> None:
        try:
            self.backend.play(wav)
        except Exception:
            pass
