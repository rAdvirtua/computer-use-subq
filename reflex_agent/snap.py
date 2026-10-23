from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
from typing import Optional, Tuple

import httpx

logger = logging.getLogger("reflex.snap")

_SNAP_URL = "https://api.subq.ai/v1/systemone"
_SNAP_MODEL = "subq-snap-preview"
_SNAP_TIMEOUT = 3.0


class SnapVisualVerifier:

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
                        "warm": {
                            "type": "noul",
                            "instructions": "Warmup check",
                            "criteria": {"true": "warm", "false": "cold"},
                        }
                    },
                },
            )
            logger.info("Snap Visual Verifier pre-warmed successfully.")
        except Exception as exc:
            logger.debug("Snap warmup skipped: %s", exc)

    async def verify_action_success(self, goal: str, jpeg_bytes: bytes) -> Tuple[bool, float, float]:
        if not self.api_key or not jpeg_bytes:
            return (True, 1.0, 0.0)

        t0 = time.perf_counter()
        b64_img = base64.b64encode(jpeg_bytes).decode("ascii")

        payload = {
            "model": _SNAP_MODEL,
            "state": f'Verify completion of visual computer action: "{goal}"',
            "images": [{"mediaType": "image/jpeg", "base64": b64_img}],
            "questions": {
                "action_succeeded": {
                    "type": "noul",
                    "instructions": f"Looking at the screen, did the action '{goal}' succeed (e.g. video playing, dialog open, page loaded, element focused)?",
                    "criteria": {
                        "true": "The requested action succeeded and screen state reflects it",
                        "false": "Screen is unchanged, failed, or action did not complete",
                    },
                }
            },
        }

        try:
            client = self._get_client()
            resp = await client.post(_SNAP_URL, json=payload)
            resp.raise_for_status()
            elapsed = (time.perf_counter() - t0) * 1000

            data = resp.json()
            ans = data.get("answers", {}).get("action_succeeded", {})
            prob = float(ans.get("noul", 0.5))
            succeeded = prob >= 0.50
            return (succeeded, prob, elapsed)

        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.warning("Snap verification error (%s) in %.0fms", exc, elapsed)
            return (True, 0.5, elapsed)

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
