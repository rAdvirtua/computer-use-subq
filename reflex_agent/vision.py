from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
import time
from typing import Optional

from PIL import Image
from google.genai import types
import pyautogui
import pytweening

logger = logging.getLogger("reflex.vision")

_VISION_PROMPT = """You are an autonomous computer-use vision agent controlling a Windows PC.
User Instruction: "{goal}"

The screenshot shows the user's active screen.
Coordinates are normalized from 0 to 1000 across width (X) and height (Y):
- (0, 0) is top-left, (1000, 1000) is bottom-right, (500, 500) is center.

Choose the single best action to execute the user's instruction:
1. "click": {"action": "click", "x": <int 0-1000>, "y": <int 0-1000>, "reason": "why clicking here"}
2. "double_click": {"action": "double_click", "x": <int 0-1000>, "y": <int 0-1000>, "reason": "why double clicking"}
3. "press_key": {"action": "press_key", "key": "enter|space|esc|tab|up|down|left|right|w|a|s|d", "reason": "why pressing key"}
4. "type": {"action": "type", "text": "...", "press_enter": true, "reason": "what to type"}
5. "done": {"action": "done", "reason": "goal is already accomplished"}

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
            logger.warning("[Vision] Screen capture failed: %s", exc)
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
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def perceive_and_act(self, goal: str) -> str:
        screen = capture_screen()
        if screen is None:
            return "Could not capture screen to see what to do."

        sw, sh = pyautogui.size()
        jpeg = _screen_to_jpeg_bytes(screen)

        prompt = _VISION_PROMPT.replace("{goal}", goal)
        client = self._get_client()

        logger.info("[Vision] Analyzing screen for goal: '%s'...", goal)
        print(f"\n  👁️ [Vision] Looking at screen for: '{goal}'...", flush=True)
        t0 = time.perf_counter()

        config = types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=1000,
            response_mime_type="application/json",
        )

        models = ["gemini-3-flash-preview", "gemini-3.5-flash-lite", "gemini-3.5-flash"]
        data = None
        raw = ""

        for m in models:
            try:
                resp = await asyncio.to_thread(
                    client.models.generate_content,
                    model=m,
                    contents=[
                        types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"),
                        prompt,
                    ],
                    config=config,
                )
                raw = resp.text.strip()
                elapsed_ms = (time.perf_counter() - t0) * 1000
                logger.info("[Vision] Decision via %s in %.0fms: %s", m, elapsed_ms, raw[:100])
                data = _extract_json(raw)
                break
            except Exception as exc:
                logger.warning("[Vision] Model %s failed: %s", m, exc)
                continue

        if not data:
            return "Vision analysis failed to identify action."

        return self._execute_action(data, sw, sh)

    def _execute_action(self, data: dict, screen_w: int, screen_h: int) -> str:
        action = data.get("action", "done")
        reason = data.get("reason", "")

        if action in ("click", "double_click"):
            norm_x = data.get("x", 500)
            norm_y = data.get("y", 500)
            target_x = int((norm_x / 1000.0) * screen_w)
            target_y = int((norm_y / 1000.0) * screen_h)

            logger.info("[Vision] %s at (%d, %d): %s", action, target_x, target_y, reason)
            print(f"  🎯 [Vision Action] {action} at ({target_x}, {target_y}) — {reason}", flush=True)

            pyautogui.moveTo(target_x, target_y, duration=0.5, tween=pytweening.easeInOutQuad)
            time.sleep(0.12)

            if action == "double_click":
                pyautogui.doubleClick()
            else:
                pyautogui.mouseDown()
                time.sleep(0.06)
                pyautogui.mouseUp()

            time.sleep(0.15)
            return f"Clicked at ({target_x}, {target_y}): {reason}"

        elif action == "press_key":
            key = data.get("key", "enter").lower()
            logger.info("[Vision] Press key '%s': %s", key, reason)
            print(f"  ⌨️ [Vision Action] Pressing key '{key}' — {reason}", flush=True)
            pyautogui.press(key)
            return f"Pressed '{key}': {reason}"

        elif action == "type":
            text = data.get("text", "")
            press_enter = data.get("press_enter", True)
            logger.info("[Vision] Typing '%s': %s", text, reason)
            print(f"  ⌨️ [Vision Action] Typing '{text}' — {reason}", flush=True)
            pyautogui.write(text, interval=0.03)
            if press_enter:
                time.sleep(0.12)
                pyautogui.press("enter")
            return f"Typed '{text}' : {reason}"

        elif action == "done":
            return f"Goal completed: {reason}"

        return f"Completed visual action: {action}"
