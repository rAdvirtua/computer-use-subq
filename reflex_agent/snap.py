from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Dict, Optional, Tuple

import httpx

logger = logging.getLogger("reflex.snap")

_SNAP_URL = "https://api.subq.ai/v1/systemone"
_SNAP_MODEL = "subq-snap-preview"
_SNAP_TIMEOUT = 2.5

_CRITERIA = {
    "pause_resume": "User explicitly wants to pause, play, or resume media playback (e.g. 'pause', 'play', 'resume', 'stop playback')",
    "mute_toggle": "User explicitly wants to mute or unmute audio (e.g. 'mute', 'unmute', 'silence audio')",
    "volume_up": "User wants to increase audio volume (e.g. 'volume up', 'turn it up', 'louder')",
    "volume_down": "User wants to decrease audio volume (e.g. 'volume down', 'turn it down', 'softer', 'quieter')",
    "scroll_down": "User wants to scroll down the screen or page (e.g. 'scroll down', 'page down', 'scroll down a bit')",
    "scroll_up": "User wants to scroll up the screen or page (e.g. 'scroll up', 'page up')",
    "close_tab": "User wants to close the current tab or active window (e.g. 'close this', 'close the tab', 'close window')",
    "fullscreen": "User wants to toggle fullscreen mode (e.g. 'fullscreen', 'exit fullscreen', 'make it full screen')",
    "controller": "ANY other request: opening or switching apps, searching websites or YouTube, typing text, clicking items or buttons on screen, visual navigation, questions, or conversation",
}


class SnapReflex:

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.environ.get("SUBQ_API_KEY", "")
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=_SNAP_TIMEOUT,
                limits=httpx.Limits(max_keepalive_connections=5, keepalive_expiry=120.0),
            )
        return self._client

    async def warmup(self) -> None:
        if not self.api_key:
            return
        try:
            client = self._get_client()
            await client.post(
                _SNAP_URL,
                json={
                    "model": _SNAP_MODEL,
                    "state": "startup warmup",
                    "questions": {
                        "action": {
                            "type": "choice",
                            "instructions": "Warmup",
                            "criteria": {"a": "warmup a", "b": "warmup b"},
                        }
                    },
                },
            )
            logger.info("[Snap] Connection pool pre-warmed successfully.")
        except Exception as exc:
            logger.debug("[Snap] Warmup skipped: %s", exc)

    async def decide_action(self, user_text: str) -> Tuple[str, float, float]:
        if not self.api_key:
            return ("controller", 0.0, 0.0)

        t0 = time.perf_counter()

        payload = {
            "model": _SNAP_MODEL,
            "state": f'User said: "{user_text}"',
            "questions": {
                "action": {
                    "type": "choice",
                    "instructions": "Select the single best reflex hotkey or controller category.",
                    "criteria": _CRITERIA,
                }
            },
        }

        try:
            client = self._get_client()
            resp = await client.post(_SNAP_URL, json=payload)
            resp.raise_for_status()
            elapsed = (time.perf_counter() - t0) * 1000

            data = resp.json()
            ans = data.get("answers", {}).get("action", {})
            choice = ans.get("choice", "controller")
            confidence = float(ans.get("confidence", 0.0))
            return (choice, confidence, elapsed)

        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.warning("[Snap Reflex] Error (%s) in %.0fms", exc, elapsed)
            return ("controller", 0.0, elapsed)

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
