from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import AsyncIterator

from yapwrap.transports.local import LocalTransport

logger = logging.getLogger("reflex.transport")


class EchoSafeLocalTransport(LocalTransport):

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._last_playback_time: float = 0.0

    @property
    def is_playing(self) -> bool:
        with self._playback_lock:
            if len(self._playback) > 0:
                return True
        return (time.time() - self._last_playback_time) < 0.45

    def _read_playback(self, size: int) -> bytes:
        with self._playback_lock:
            if self._playback:
                self._last_playback_time = time.time()
                data = bytes(self._playback[:size])
                del self._playback[:size]
                return data.ljust(size, b"\x00")
            return b"\x00" * size

    async def audio_in(self) -> AsyncIterator[bytes]:
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise ImportError("EchoSafeLocalTransport requires `pip install 'yapwrap[local]'`.") from exc

        loop = asyncio.get_running_loop()

        def mic_callback(indata, frames, time_info, status):
            if status:
                logger.debug("Microphone status: %s", status)
            data_bytes = bytes(indata)
            if self.is_playing:
                data_bytes = b"\x00" * len(data_bytes)
            loop.call_soon_threadsafe(self._input_queue.put_nowait, data_bytes)

        def speaker_callback(outdata, frames, time_info, status):
            if status:
                logger.debug("Speaker status: %s", status)
            outdata[:] = self._read_playback(frames * 2)
            loop.call_soon_threadsafe(self._space.set)

        options = dict(samplerate=self.sample_rate, blocksize=self.frame_bytes // 2, dtype="int16", channels=1)
        try:
            with sd.RawInputStream(callback=mic_callback, **options), sd.RawOutputStream(callback=speaker_callback, **options):
                print("Session online. Start speaking (Ctrl+C to stop).", flush=True)
                while self._is_open:
                    chunk = await self._input_queue.get()
                    if chunk is None:
                        break
                    yield chunk
        finally:
            self.stop()
