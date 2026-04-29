"""Microphone capture. Records mono 16 kHz PCM and returns a WAV blob in memory."""

from __future__ import annotations

import io
import threading
import wave

import numpy as np
import sounddevice as sd


SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"


class AudioRecorder:
    def __init__(self, sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS):
        self._sample_rate = sample_rate
        self._channels = channels
        self._stream: sd.InputStream | None = None
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._recording = False

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self) -> None:
        if self._recording:
            return
        self._chunks = []

        def callback(indata, frames, time_info, status):  # noqa: ARG001
            with self._lock:
                self._chunks.append(indata.copy())

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
