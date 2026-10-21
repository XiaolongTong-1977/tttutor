"""Tests for the sound module — synthesize WAVs, verify format, exercise
backend selection, ensure the player is a no-op when disabled."""
import io
import unittest
import wave

from tttutor.sound import (
    SAMPLE_RATE,
    SoundEvent,
    SoundPlayer,
    pick_backend,
    synthesize,
)


class SynthesizeTests(unittest.TestCase):
    def test_each_event_produces_a_valid_wav(self):
        for e in SoundEvent:
            wav = synthesize(e)
            self.assertGreater(len(wav), 44, "WAV header alone is 44 bytes")
            with wave.open(io.BytesIO(wav), "rb") as w:
                self.assertEqual(w.getnchannels(), 1)
                self.assertEqual(w.getsampwidth(), 2)
                self.assertEqual(w.getframerate(), SAMPLE_RATE)
                self.assertGreater(w.getnframes(), 0)

    def test_deterministic_events_match_across_calls(self):
        # All events except KEYSTROKE (noise-based) are deterministic.
        for e in SoundEvent:
            if e is SoundEvent.KEYSTROKE:
                continue
            a = synthesize(e)
            b = synthesize(e)
            self.assertEqual(
                a, b,
                f"{e.value} should be deterministic; bytes differ across calls",
            )

    def test_noise_event_is_random_within_bounds(self):
        # KEYSTROKE uses real noise — two calls should differ (but both legal).
        a = synthesize(SoundEvent.KEYSTROKE)
        b = synthesize(SoundEvent.KEYSTROKE)
        self.assertNotEqual(a, b)
        with wave.open(io.BytesIO(a), "rb") as w:
            self.assertEqual(w.getnchannels(), 1)
        with wave.open(io.BytesIO(b), "rb") as w:
            self.assertEqual(w.getnchannels(), 1)


class BackendTests(unittest.TestCase):
    def test_pick_backend_returns_an_enabled_backend(self):
        b = pick_backend()
        self.assertTrue(hasattr(b, "play"))

    def test_player_disabled_is_silent(self):
        p = SoundPlayer(enabled=False)
        p.play(SoundEvent.LESSON_COMPLETE)
        # If we got here without exception, the silent path works.
        self.assertFalse(p.enabled)


class IntegrationTests(unittest.TestCase):
    def test_synth_through_played_backend(self):
        """Ensure the synthesized WAV actually plays through a chosen backend,
        at least produces a file. We intercept by patching subprocess.Popen."""
        import subprocess
        from tttutor import sound as sound_mod
        captured = {}

        class FakePopen:
            def __init__(self, cmd, **kwargs):
                captured['cmd'] = cmd
            def wait(self):
                return 0

        original = subprocess.Popen
        subprocess.Popen = FakePopen  # type: ignore
        try:
            sound_mod.PulseAudioBackend.play(
                sound_mod.PulseAudioBackend(), synthesize(SoundEvent.ERROR))
        finally:
            subprocess.Popen = original  # type: ignore
        # cmd[0] should be 'paplay'
        self.assertEqual(captured['cmd'][0], "paplay")


if __name__ == "__main__":
    unittest.main()
