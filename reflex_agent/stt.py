from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import AsyncIterator, List, Optional
from urllib.parse import urlencode

from yapwrap.stt.deepgram import DeepgramSTT
from yapwrap.core.events import TranscriptEvent

logger = logging.getLogger("reflex.stt")


class ResilientDeepgramSTT(DeepgramSTT):

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "nova-3",
        language: str = "en",
        smart_format: bool = True,
        sample_rate: int = 16000,
        endpointing: Optional[int] = None,
        keyterms: Optional[List[str]] = None,
        open_timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            language=language,
            smart_format=smart_format,
            sample_rate=sample_rate,
            endpointing=endpointing,
            keyterms=keyterms,
        )
        self.open_timeout = open_timeout
        self.max_retries = max_retries

    async def transcribe(self, audio: AsyncIterator[bytes]) -> AsyncIterator[TranscriptEvent]:
        try:
            from websockets.asyncio.client import connect
        except ImportError as exc:
            raise ImportError("DeepgramSTT requires `pip install 'yapwrap[deepgram]'`.") from exc

        if not self.api_key:
            raise ValueError("DeepgramSTT requires an api_key or DEEPGRAM_API_KEY environment variable.")

        url = self._build_url()
        headers = {"Authorization": f"Token {self.api_key}"}

        audio_chunks: List[bytes] = []
        is_buffering = True

        for attempt in range(self.max_retries + 1):
            try:
                async with connect(
                    url,
                    additional_headers=headers,
                    open_timeout=self.open_timeout,
                    ping_interval=20.0,
                    ping_timeout=20.0,
                ) as ws:

                    async def send_audio() -> None:
                        try:
                            for c in audio_chunks:
                                await ws.send(c)
                            async for chunk in audio:
                                await ws.send(chunk)
                            await ws.send(json.dumps({"type": "CloseStream"}))
                        except Exception:
                            await ws.close()
                            raise

                    sender = asyncio.create_task(send_audio())
                    try:
                        async for message in ws:
                            data = json.loads(message)
                            if data.get("type") == "Error":
                                logger.warning("[stt] deepgram error: %s", data.get("description"))
                                break
                            channel = data.get("channel", {})
                            alternatives = channel.get("alternatives", [])
                            if alternatives:
                                transcript = alternatives[0].get("transcript", "")
                                if transcript:
                                    yield TranscriptEvent(
                                        text=transcript,
                                        is_final=data.get("is_final", False),
                                    )
                        if sender.done():
                            await sender
                    finally:
                        if not sender.done():
                            sender.cancel()
                        await asyncio.gather(sender, return_exceptions=True)

                return

            except (TimeoutError, asyncio.CancelledError, OSError) as exc:
                logger.warning("[stt] websocket handshake timeout (attempt %d/%d): %s", attempt + 1, self.max_retries + 1, exc)
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5)
                    continue
                else:
                    print(f"[stt] timeout ({exc})", flush=True)
                    return
            except Exception as exc:
                logger.error("[stt] error: %s", exc)
                print(f"[stt] error: {exc}", flush=True)
                return
