"""Microphone capture. Records mono 16 kHz PCM and returns a WAV blob in memory.

Also publishes a smoothed 0..1 loudness level while recording, for the
overlay's waveform. `current_level()` is a module-level read because there
is exactly one microphone and one recorder in the app.

ponytail: module global. If a second recorder ever exists, hand the level
through the AudioRecorder instance instead.
"""

from __future__ import annotations

import io
import math
import threading
import wave

import numpy as np
import sounddevice as sd


SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"

_level = 0.0


def current_level() -> float:
    """Smoothed 0..1 loudness of what the mic is hearing right now."""
    return _level


def _publish_level(value: float) -> None:
    global _level
    _level = value


class _LevelNormalizer:
    """Port of the Mac app's LiveAudioLevelNormalizer.

    A raw RMS makes for a dead-looking waveform: speech sits in a narrow dB
    band well above a room's noise floor, and that floor differs per room and
    per mic. So we track the floor and the peak ceiling adaptively and map the
    live level into whatever span currently separates them, then gate out the
    silence below the floor.
    """

    MIN_RMS = 1e-5
    MIN_SPAN_DB = 18.0
    PEAK_HEADROOM_DB = 8.0
    SPEECH_GATE_MARGIN_DB = 3.0
    MIN_VISIBLE_ACTIVE = 0.12
    NOISE_GATE = 0.06
    FLOOR_RISE_WINDOW_DB = 4.0
    FLOOR_FALL_BLEND = 0.12
    FLOOR_RISE_BLEND = 0.02
    PEAK_ATTACK_BLEND = 0.55
    PEAK_RELEASE_BLEND = 0.04
    DISPLAY_ATTACK_BLEND = 0.45
    DISPLAY_RELEASE_BLEND = 0.12

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._floor_db = -55.0
        self._ceiling_db = -37.0
        self._display = 0.0

    def normalized(self, rms: float) -> float:
        level_db = 20.0 * math.log10(max(rms, self.MIN_RMS))
        self._update_floor(level_db)
        self._update_ceiling(level_db)

        display_ceiling = self._ceiling_db + self.PEAK_HEADROOM_DB
        span = max(display_ceiling - self._floor_db,
                   self.MIN_SPAN_DB + self.PEAK_HEADROOM_DB)
        value = min(max((level_db - self._floor_db) / span, 0.0), 1.0)

        speaking = level_db >= self._floor_db + self.SPEECH_GATE_MARGIN_DB
        if value < self.NOISE_GATE and not speaking:
            value = 0.0
        elif speaking:
            value = max(value, self.MIN_VISIBLE_ACTIVE)

        blend = (self.DISPLAY_ATTACK_BLEND if value > self._display
                 else self.DISPLAY_RELEASE_BLEND)
        self._display += (value - self._display) * blend
        return self._display

    def _update_floor(self, level_db: float) -> None:
        capped = min(level_db, self._ceiling_db - self.MIN_SPAN_DB)
        if capped <= self._floor_db:
            self._floor_db += (capped - self._floor_db) * self.FLOOR_FALL_BLEND
        elif capped <= self._floor_db + self.FLOOR_RISE_WINDOW_DB:
            self._floor_db += (capped - self._floor_db) * self.FLOOR_RISE_BLEND

    def _update_ceiling(self, level_db: float) -> None:
        minimum = self._floor_db + self.MIN_SPAN_DB
        if level_db >= self._ceiling_db:
            self._ceiling_db += (level_db - self._ceiling_db) * self.PEAK_ATTACK_BLEND
        else:
            target = max(level_db, minimum)
            self._ceiling_db += (target - self._ceiling_db) * self.PEAK_RELEASE_BLEND
        self._ceiling_db = max(self._ceiling_db, minimum)


class AudioRecorder:
    def __init__(self, sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS):
        self._sample_rate = sample_rate
        self._channels = channels
        self._stream: sd.InputStream | None = None
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._recording = False
        self._normalizer = _LevelNormalizer()

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self) -> None:
        if self._recording:
            return
        self._chunks = []

        self._normalizer.reset()
        _publish_level(0.0)

        def callback(indata, frames, time_info, status):  # noqa: ARG001
            with self._lock:
                self._chunks.append(indata.copy())
            samples = indata.astype(np.float32) / 32768.0
            rms = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0
            _publish_level(self._normalizer.normalized(rms))

        self._stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=self._channels,
            dtype=DTYPE,
            callback=callback,
        )
        self._stream.start()
        self._recording = True

    def stop(self) -> bytes:
        """Stop recording and return a 16-bit mono WAV blob.

        Returns an empty bytes object if no audio was captured.
        """
        if not self._recording:
            return b""
        assert self._stream is not None
        self._stream.stop()
        self._stream.close()
        self._stream = None
        self._recording = False
        _publish_level(0.0)

        with self._lock:
            chunks = self._chunks
            self._chunks = []

        if not chunks:
            return b""

        audio = np.concatenate(chunks, axis=0)
        if audio.size == 0:
            return b""

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(self._channels)
            wav.setsampwidth(2)
            wav.setframerate(self._sample_rate)
            wav.writeframes(audio.tobytes())
        return buffer.getvalue()

    def cancel(self) -> None:
        if not self._recording:
            return
        try:
            self.stop()
        except Exception:
            pass
        with self._lock:
            self._chunks = []
