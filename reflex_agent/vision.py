from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import re
import time
from typing import Optional

from PIL import Image
import pyautogui
import pytweening
import httpx

from .snap import SnapVisualVerifier
from .memory import global_memory

logger = logging.getLogger("reflex.vision")

_VISION_PROMPT = """You are an autonomous computer-use vision agent controlling a Windows PC.
User Instruction: "{goal}"

The screenshot shows the user's active screen.
Coordinates are normalized from 0 to 1000 across width (X) and height (Y):
- (0, 0) is top-left, (1000, 1000) is bottom-right, (500, 500) is center.

Actions:
1. "click": {"action": "click", "x": <int 0-1000>, "y": <int 0-1000>, "reason": "why clicking"}
2. "double_click": {"action": "double_click", "x": <int 0-1000>, "y": <int 0-1000>, "reason": "why double clicking"}
3. "press_key": {"action": "press_key", "key": "enter|space|esc|tab|win+d|c|e|up|down|left|right|w|a|s|d", "reason": "why pressing key"}
4. "hold_key": {"action": "hold_key", "key": "w|a|s|d|shift+w|space", "duration": <float 0.5-5.0>, "reason": "why holding key"}
5. "repeat_key": {"action": "repeat_key", "key": "down|up|space|enter", "times": <int 1-10>, "reason": "why repeating key"}
6. "type": {"action": "type", "text": "...", "press_enter": true, "reason": "what to type"}
7. "done": {"action": "done", "reason": "goal is accomplished"}

Return ONLY a valid JSON object matching this schema."""


def attach_to_input_desktop() -> bool:
    try:
        import ctypes
        user32 = ctypes.windll.user32
        h_input = user32.OpenInputDesktop(0, False, 0x01FF)
        if h_input:
            user32.SetThreadDesktop(h_input)
            return True
    except Exception:
        pass
    return False


def capture_screen() -> Optional[Image.Image]:
    attach_to_input_desktop()
    try:
        from PIL import ImageGrab
        return ImageGrab.grab()
    except Exception:
        try:
            import mss
            with mss.MSS() as sct:
                mon = sct.monitors[1]
                s = sct.grab(mon)
                return Image.frombytes("RGB", s.size, s.bgra, "raw", "BGRX")
        except Exception as exc:
            logger.warning("[vision] capture failed: %s", exc)
            return None


def _screen_to_jpeg_bytes(screen: Image.Image, max_dim: int = 1280, quality: int = 75) -> bytes:
    img = screen
    if max(img.width, img.height) > max_dim:
        scale = max_dim / max(img.width, img.height)
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _extract_json(raw: str) -> dict:
    text = raw.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()
    m2 = re.search(r"(\{.*\})", text, re.DOTALL)
    if m2:
        text = m2.group(1).strip()
    return json.loads(text)


class VisionComputerUse:

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.subq_key = os.environ.get("SUBQ_API_KEY", "")
        self.gemini_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self._http_client: Optional[httpx.AsyncClient] = None
        self._gemini_client = None
        self.verifier = SnapVisualVerifier()

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                headers={"Authorization": f"Bearer {self.subq_key}"},
                timeout=30.0,
                limits=httpx.Limits(max_keepalive_connections=5, keepalive_expiry=120.0),
            )
        return self._http_client

    def _get_gemini_client(self):
        if self._gemini_client is None and self.gemini_key:
            from google import genai
            self._gemini_client = genai.Client(api_key=self.gemini_key)
        return self._gemini_client

    async def warmup(self) -> None:
        await self.verifier.warmup()

    async def perceive_and_act(self, goal: str) -> str:
        screen = capture_screen()
        if screen is None:
            return "Could not capture screen."

        sw, sh = pyautogui.size()
        jpeg = _screen_to_jpeg_bytes(screen)
        b64_img = base64.b64encode(jpeg).decode("ascii")

        prompt = _VISION_PROMPT.replace("{goal}", goal)
        learned_ctx = global_memory.get_learned_prompt_context(goal)
        if learned_ctx:
            prompt += f"\n\n{learned_ctx}"

        print(f"[vision] perceiving screen for: '{goal}'", flush=True)
        t0 = time.perf_counter()

        data = None
        raw = ""

        if self.subq_key:
            try:
                client = self._get_http_client()
                payload = {
                    "model": "subq-savant-1.4",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}},
                            ],
                        }
                    ],
                }
                resp = await client.post("https://api.subq.ai/v1/chat/completions", json=payload)
                if resp.status_code == 200:
                    resp_json = resp.json()
                    raw = resp_json["choices"][0]["message"].get("content", "").strip()
                    elapsed_ms = (time.perf_counter() - t0) * 1000
                    logger.info("[vision] subq decision in %.0fms: %s", elapsed_ms, raw[:100])
                    data = _extract_json(raw)
            except Exception as exc:
                logger.warning("[vision] subq call failed: %s", exc)

        if not data and self.gemini_key:
            g_client = self._get_gemini_client()
            if g_client:
                from google.genai import types
                config = types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=1000,
                    response_mime_type="application/json",
                )
                for m in ("gemini-3.5-flash-lite", "gemini-3.5-flash"):
                    try:
                        resp = await asyncio.to_thread(
                            g_client.models.generate_content,
                            model=m,
                            contents=[
                                types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"),
                                prompt,
                            ],
                            config=config,
                        )
                        raw = resp.text.strip()
                        data = _extract_json(raw)
                        break
                    except Exception as exc:
                        logger.warning("[vision] gemini model %s failed: %s", m, exc)

        if not data:
            return "Vision analysis failed."

        action_summary = self._execute_action(data, sw, sh)

        time.sleep(0.2)
        post_screen = capture_screen()
        if post_screen:
            post_jpeg = _screen_to_jpeg_bytes(post_screen, max_dim=800, quality=65)
            succeeded, prob, snap_ms = await self.verifier.verify_action_success(goal, post_jpeg)
            print(f"[snap] verified outcome: {prob:.0%} ({snap_ms:.0f}ms)", flush=True)
            global_memory.record_action_outcome("active_app", goal, action_summary, succeeded)

        return action_summary

    def _execute_action(self, data: dict, screen_w: int, screen_h: int) -> str:
        action = data.get("action", "done")
        reason = data.get("reason", "")

        if action in ("click", "double_click"):
            norm_x = data.get("x", 500)
            norm_y = data.get("y", 500)
            target_x = int((norm_x / 1000.0) * screen_w)
            target_y = int((norm_y / 1000.0) * screen_h)

            print(f"[vision] {action} ({target_x}, {target_y})", flush=True)

            pyautogui.moveTo(target_x, target_y, duration=0.3, tween=pytweening.easeInOutQuad)
            time.sleep(0.08)

            if action == "double_click":
                pyautogui.click()
                time.sleep(0.08)
                pyautogui.click()
            else:
                pyautogui.mouseDown()
                time.sleep(0.05)
                pyautogui.mouseUp()

            time.sleep(0.08)
            return f"Clicked at ({target_x}, {target_y}): {reason}"

        elif action == "press_key":
            key = data.get("key", "enter").lower()
            print(f"[vision] press_key '{key}'", flush=True)
            from .desktop import press_key
            press_key(key)
            return f"Pressed '{key}': {reason}"

        elif action == "hold_key":
            key = data.get("key", "w").lower()
            duration = float(data.get("duration", 1.5))
            print(f"[vision] hold_key '{key}' ({duration:.1f}s)", flush=True)
            from .desktop import hold_key
            hold_key(key, duration=duration)
            return f"Held '{key}' for {duration:.1f}s: {reason}"

        elif action == "repeat_key":
            key = data.get("key", "space").lower()
            times = int(data.get("times", 1))
            print(f"[vision] repeat_key '{key}' x{times}", flush=True)
            from .desktop import repeat_key
            repeat_key(key, times=times)
            return f"Pressed '{key}' {times} times: {reason}"

        elif action == "type":
            text = data.get("text", "")
            press_enter = data.get("press_enter", True)
            print(f"[vision] type '{text[:40]}'", flush=True)
            from .desktop import type_text
            type_text(text, press_enter=press_enter)
            return f"Typed '{text}': {reason}"

        elif action == "done":
            return f"Goal completed: {reason}"

        return f"Action completed: {action}"

    async def close(self) -> None:
        await self.verifier.close()
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None
